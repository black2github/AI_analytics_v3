# app/scripts/CI/kitcheck/checks/call_contract_props.py
"""Сторож свойств контракта и кодов параметров в карточке вызова (шаблон contract-call.md, раздел B;
решения владельца канона 13.11.2026, постановка прибору 2026-11-13). Норма шаблона:

1. Свойств контракта в карточке вызова нет: тип, обязательность, кратность параметра живут в
   базовом контракте поставщика. Пока описания метода у владельца нет, свойства временно остаются
   в карточке.
2. Параметр в таблицах привязки называется кодом из базового контракта, наименование — в скобках
   после кода. Строка с одним наименованием допустима, только пока у владельца нет описания метода.

Признак «у карточки есть базовый контракт» (объявлен здесь и в тексте строк отчёта): значение строки
шапки тела «**Базовый контракт:** …» начинается со ссылки markdown. Строки «отсутствует — …» и
«ссылка не ставится — …» начинаются со слова: базового контракта нет, даже если ссылка стоит дальше
в пояснении (КК: «ссылка не ставится — …; дословно [страница](…)»). Нет строки — базового контракта нет.

А. Колонки свойств контракта — в любой таблице карточки (не только с первой колонкой «Параметр…»):
   колонка шапки из перечня `_PROP_COLUMNS` (объявленная эвристика: текст ячейки шапки целиком, не
   содержимое строк — строка данных «Тип адреса» колонкой не считается).
   - базовый контракт есть → ✗ строкой на карточку: разделы и названия колонок — свойства записаны
     второй раз;
   - базового контракта нет → ⚠ одной строкой комплекта с числом и первыми ID, перечень — в --out.
Б. Строки привязки без кода — только у карточек с базовым контрактом: в таблицах привязки шаблона
   («Параметр контракта | Правило сервиса», «Параметр контракта | Куда записывается в сервисе»)
   ячейка «Параметр контракта» без фрагмента в обратных кавычках и не латинский идентификатор или
   путь (`data.cards[].id`) → ⚠ одной строкой комплекта с числом строк и карточек, перечень — в
   --out. Вердикт от Б не меняется; у карточки без базового контракта код взять неоткуда — молчит.

Вне проверки: блоки кода и HTML-комментарии, README реестров, документы других типов (базовый
контракт `internal-contract` / `external-integration`, функция — у них колонки «Тип | Обяз.» по
своему шаблону). Таблицы параметров с шапкой не по шаблону без колонок свойств («Параметр |
Описание параметра | Заполнение», «Параметр | Значение», коды ошибок) сторож не трогает (решение
владельца 13.11); правая колонка таблиц привязки не проверяется.

Слой — ядро: проверка читает только комплект и без выгрузки работает полностью."""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, code_line_flags, table_cells
    from kitcheck.checks.call_algorithms import _COMMENT_RE, _HEAD_RE, _LINK_RE, _card_id, _is_call_card
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, code_line_flags, table_cells  # type: ignore
    from .call_algorithms import _COMMENT_RE, _HEAD_RE, _LINK_RE, _card_id, _is_call_card  # type: ignore

# строки, которые selfcheck пишет только в файл отчёта --out (тот же префикс, что selfcheck.OUT_ONLY)
_OUT_ONLY = "   · "
LF = chr(10)

# Колонки свойств контракта — текст ячейки шапки целиком, без разметки, без учёта регистра и «ё».
# Перечень — замер 13.11.2026 по карточкам вызова трёх комплектов (КК 4e86b8c8, пример
# docs-account-opening-request 5230ec9, эталон канона): «Кратность», «Тип», «Обяз.», «Тип данных»,
# «Обязательность», «Тип и формат данных», «Тип поля»; «Тип параметра» — из шаблона базового
# контракта. Не колонки: «Тип документа», «Тип сообщения (квитанции)», «Тип контента» — данные.
_PROP_COLUMNS = ("тип", "тип данных", "тип параметра", "тип поля", "тип и формат данных",
                 "обяз.", "обязательность", "кратность")
# Голое «Тип» — свойство контракта всегда, есть ли в шапке обязательность и кратность или нет (решение
# владельца 13.11). Колонку другого смысла называют полностью («Тип сообщения») — правится карточка.

# таблицы привязки шаблона: колонка «Параметр контракта», за ней одна из двух правых колонок
_BIND_LEFT = "параметр контракта"
_BIND_RIGHT = ("правило сервиса", "куда записывается в сервисе")

_BASE_LABEL_RE = re.compile(r"^\*\*Базовый контракт:\*\*\s*(.*)$")
_SEP_ROW_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_CODE_FRAG_RE = re.compile(r"`[^`]+`")
# латинский идентификатор или путь: CLIENT_ID, data.cards[].id, Receipt/ErrorCode, header:X-Request-Id
_LATIN_ID_RE = re.compile(r"^[A-Za-z_$@][A-Za-z0-9_.\[\]{}/:@$-]*$")
_EMPTY_CELL = {"", "—", "–", "-", "…", "..."}


def _plain(cell: str) -> str:
    """Текст ячейки без переносов <br> и выделения «*»; обратные кавычки и «_» сохраняются."""
    t = re.sub(r"<br\s*/?>", " ", cell).replace("*", "")
    return re.sub(r"\s+", " ", t).strip()


def _head_key(cell: str) -> str:
    t = re.sub(r"<br\s*/?>", " ", cell).replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", t).strip().lower().replace("ё", "е")


def base_contract(lines: List[str]) -> Optional[str]:
    """Ссылка базового контракта (текст метки ссылки) или None — базового контракта нет. Признак —
    значение строки «**Базовый контракт:** …» начинается со ссылки markdown."""
    for ln in lines:
        m = _BASE_LABEL_RE.match(ln.strip())
        if not m:
            continue
        val = m.group(1).strip()
        link = _LINK_RE.match(val)
        if not link:
            return None
        txt = link.group(0)
        return txt[1:txt.rfind("](")]
    return None


def has_code(cell: str) -> bool:
    """Ячейка «Параметр контракта» называет параметр кодом: фрагмент в обратных кавычках или вся
    ячейка — латинский идентификатор либо путь."""
    if _CODE_FRAG_RE.search(cell):
        return True
    return bool(_LATIN_ID_RE.match(_plain(cell)))


def analyse(text: str) -> Dict[str, object]:
    """Находки одной карточки: base — метка ссылки базового контракта или None; props —
    [(строка шапки с 1, раздел, [колонки])]; nocode — [(строка с 1, ячейка)] строк таблиц привязки
    без кода."""
    lines = _COMMENT_RE.sub(lambda m: LF * m.group(0).count(LF), text).splitlines()
    code = code_line_flags(lines)
    body_from = 0
    if lines and lines[0].strip() == "---":
        body_from = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    live = [ln if i >= body_from and not code[i] else "" for i, ln in enumerate(lines)]
    props: List[Tuple[int, str, List[str]]] = []
    nocode: List[Tuple[int, str]] = []
    section = ""
    i = 0
    while i < len(live):
        ln = live[i]
        m = _HEAD_RE.match(ln)
        if m:
            section = m.group(2).strip()
        if ln.lstrip().startswith("|") and i + 1 < len(live) and _SEP_ROW_RE.match(live[i + 1]):
            head = table_cells(ln)
            keys = [_head_key(c) for c in head]
            cols = [_plain(head[k]) for k, key in enumerate(keys) if key in _PROP_COLUMNS]
            if cols:
                props.append((i + 1, section, cols))
            bind = next((k for k in range(len(keys) - 1)
                         if keys[k] == _BIND_LEFT and keys[k + 1] in _BIND_RIGHT), None)
            j = i + 2
            while j < len(live) and live[j].lstrip().startswith("|"):
                if bind is not None:
                    cells = table_cells(live[j])
                    cell = cells[bind] if bind < len(cells) else ""
                    if _plain(cell) not in _EMPTY_CELL and not has_code(cell):
                        nocode.append((j + 1, cell))
                j += 1
            i = j
            continue
        i += 1
    return {"base": base_contract(live), "props": props, "nocode": nocode}


def _ids(rows: List[Tuple[str, str]]) -> str:
    head = ", ".join(cid for cid, _ in rows[:3])
    return head + (f", и ещё {len(rows) - 3}" if len(rows) > 3 else "")


def check_call_contract_props(docs: Path) -> Tuple[List[str], bool]:
    """Строки отчёта и ok (False — есть ✗). ✗ — строка на карточку с базовым контрактом и колонками
    свойств; ⚠ — по строке комплекта на «свойства без базового контракта» и «строки привязки без
    кода»; полные перечни — в --out."""
    bad: List[str] = []
    temp: List[Tuple[str, str, List[Tuple[int, str, List[str]]]]] = []
    nocode: List[Tuple[str, str, List[Tuple[int, str]]]] = []
    for md in _kit_md(docs):
        if not _is_call_card(md):
            continue
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        res = analyse(text)
        rel = md.relative_to(docs).as_posix()
        cid = _card_id(md)
        props = res["props"]
        if res["base"] is not None:
            if props:
                where = "; ".join(f"«{sec or 'без раздела'}» — " + ", ".join(f"«{c}»" for c in cols)
                                  for _n, sec, cols in props)
                bad.append(f"✗ карточка вызова {cid} ({rel}): свойства контракта записаны второй раз — "
                           f"у карточки есть базовый контракт ({res['base']}); {where} — тип, "
                           "обязательность и кратность живут в базовом контракте, колонки убрать "
                           "(шаблон contract-call.md)")
            if res["nocode"]:
                nocode.append((cid, rel, res["nocode"]))
        elif props:
            temp.append((cid, rel, props))
    rep = list(bad)
    if temp:
        rep.append(f"⚠ свойства контракта временно живут в карточке вызова — до появления базового "
                   f"контракта: {len(temp)} карточек ({_ids([(c, r) for c, r, _ in temp])}) — признак "
                   "базового контракта: значение строки «Базовый контракт» начинается со ссылки")
        rep += [f"{_OUT_ONLY}{rel}:{n} — «{sec or 'без раздела'}»: " + ", ".join(f"«{c}»" for c in cols)
                for _c, rel, props in temp for n, sec, cols in props]
    if nocode:
        total = sum(len(rows) for _c, _r, rows in nocode)
        lst = ", ".join(f"{c} ×{len(rows)}" for c, _r, rows in nocode[:3])
        more = f", и ещё {len(nocode) - 3}" if len(nocode) > 3 else ""
        rep.append(f"⚠ строки привязки без кода параметра у карточек вызова с базовым контрактом: "
                   f"{total} строк в {len(nocode)} карточках ({lst}{more}) — параметр назвать кодом "
                   "из базового контракта, наименование — в скобках после кода (шаблон contract-call.md)")
        rep += [f"{_OUT_ONLY}{rel}:{n} — {cell}" for _c, rel, rows in nocode for n, cell in rows]
    return rep, not bad
