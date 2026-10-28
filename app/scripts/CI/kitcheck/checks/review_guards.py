# app/scripts/CI/kitcheck/checks/review_guards.py
"""Сторожа по разбору замечаний к миграции КК (план П1, 2026-10-22): только ⚠ и i,
вердикт не меняют. Каждый ловит класс недочёта, который прошёл при зелёном приборе:
страница-копия как своя, способ показа в тексте контроля, вызыватель без ссылки при
существующей карточке, строка паспорта вне таблицы, счётчик открытых вопросов."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, blank_code, code_line_flags, read_frontmatter
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, blank_code, code_line_flags, read_frontmatter  # type: ignore

_LIMIT = 30
# строки, которые selfcheck пишет только в файл отчёта --out (тот же префикс, что
# selfcheck.OUT_ONLY): полные перечни под сводной строкой комплекта
_OUT_ONLY = "   · "


def _fm(md: Path) -> Dict[str, str]:
    return {k: str(v).strip().strip("'\"") for k, v in (read_frontmatter(md) or {}).items()}


def _text(md: Path) -> str:
    try:
        return _fs.read_text(md, encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _listing(head: str, rows: List[str]) -> List[str]:
    out = [head]
    out.extend(f"   {r}" for r in rows[:_LIMIT])
    if len(rows) > _LIMIT:
        out.append(f"   … и ещё {len(rows) - _LIMIT}")
    return out


# --- B2 (Т5): страница-«Копия» перенесена как своя ---
_COPY_RE = re.compile(r"^(?:\[[^\]]*\]\s*)?Копия\b|\(Копия\)", re.I)


def check_copy_titles(docs: Path) -> List[str]:
    rows = []
    for md in _kit_md(docs):
        title = _fm(md).get("title", "")
        if title and _COPY_RE.search(title):
            rows.append(f"{md.relative_to(docs).as_posix()} — «{title[:90]}»")
    if not rows:
        return []
    return _listing(f"⚠ страница-копия перенесена как своя ×{len(rows)}: правило копий "
                    "(prompt-plan шаг 2а) — вне SRS или OQ", rows)


# --- B4 (Т7): способ показа в тексте контроля ---
_ERR_FIELD_RE = re.compile(r"^\s*[-*]\s+\*\*Сообщение об ошибке:?\*\*:?(.*)$")
_DISPLAY_RE = re.compile(r"(?i)способ\w*\s+отображени|отображается\s+под\s+полем|модальн|информер")
_QUOTED_RE = re.compile(r"«[^»\n]*»|\"[^\"\n]*\"")


def check_control_display_mode(docs: Path) -> List[str]:
    rows, total = [], 0
    for md in _kit_md(docs):
        rel = md.relative_to(docs).as_posix()
        if _fm(md).get("type") != "control" and "/control/" not in "/" + rel:
            continue
        lines = _text(md).splitlines()
        n = 0
        for ln, code in zip(lines, code_line_flags(lines)):
            m = None if code else _ERR_FIELD_RE.match(ln)
            # текст сообщения в кавычках — литерал, его слова не способ показа
            if m and _DISPLAY_RE.search(_QUOTED_RE.sub(" ", m.group(1))):
                n += 1
        if n:
            rows.append(f"{rel} ×{n}")
            total += n
    if not rows:
        return []
    return _listing(f"⚠ способ показа в контроле — дом §7 ЭФ (controls.md): мест {total} "
                    f"в {len(rows)} файлах (поле «Сообщение об ошибке»)", rows)


# --- B5 (Т8-б): «Вызов функции» без ссылки при существующей цели ---
_TAG_RE = re.compile(r"^\[[^\]]+\]\s*")
_CALLER_SEC_RE = re.compile(r"^##\s+(?:\d+\.\s*)?Вызов функции\s*$", re.M)
_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")
_MIN_TITLE = 12  # короткие названия («Отчёты») совпадают случайно — не сторожатся
# кто может вызывать функцию: ЭФ, функция, процесс, агент, уведомление (не сущность и не контроль)
_CALLER_TYPES = {"function", "screen-form", "process", "agent", "notification"}


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[«»\"“”„']", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _titles(docs: Path) -> List[Tuple[str, str, Path]]:
    """(нормализованный титул, ID, файл) — с тегом и без тега, длинные первыми."""
    out: List[Tuple[str, str, Path]] = []
    for md in _kit_md(docs):
        fm = _fm(md)
        title, cid = fm.get("title", ""), fm.get("id", "")
        if not title or not cid or fm.get("type") not in _CALLER_TYPES:
            continue
        for t in {_norm(title), _norm(_TAG_RE.sub("", title))}:
            if len(_TAG_RE.sub("", t)) >= _MIN_TITLE:
                out.append((t, cid, md))
    return sorted(out, key=lambda x: -len(x[0]))


def check_caller_links(docs: Path) -> List[str]:
    titles = _titles(docs)
    rows: List[str] = []
    for md in _kit_md(docs):
        fm = _fm(md)
        if fm.get("type") != "function":
            continue
        text = _text(md)
        m = _CALLER_SEC_RE.search(text)
        if not m:
            continue
        rest = text[m.end():]
        nxt = re.search(r"^## ", rest, re.M)
        sec = rest[:nxt.start()] if nxt else rest
        for ln in sec.splitlines():
            im = _ITEM_RE.match(ln)
            if not im or "](" in im.group(1):
                continue
            item = _norm(im.group(1))
            for t, cid, f in titles:
                if f == md or cid == fm.get("id"):
                    continue
                pos = item.find(t)
                if pos < 0:
                    continue
                before = item[pos - 1] if pos else " "
                after = item[pos + len(t)] if pos + len(t) < len(item) else " "
                if before.isalnum() or after.isalnum():
                    continue  # часть другого слова
                rows.append(f"{md.relative_to(docs).as_posix()}: {cid} «{im.group(1).strip()[:80]}»")
                break
    if not rows:
        return []
    return _listing(f"⚠ вызыватель есть в комплекте, ссылки нет ×{len(rows)} — проставить "
                    "ссылку в разделе «Вызов функции»", rows)


# --- B7 (Т10): строка паспорта вне таблицы ---
_PASSPORT_TYPES = {"internal-contract", "contract-call", "data-model"}
_PASSPORT_LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?(Где используется|Привилегии|Реализация)(?::\*\*|\*\*:|:)")


def check_passport_after_table(docs: Path) -> List[str]:
    rows: List[str] = []
    for md in _kit_md(docs):
        if _fm(md).get("type") not in _PASSPORT_TYPES:
            continue
        lines = _text(md).splitlines()
        flags = code_line_flags(lines)
        after_table, prev_table, found = False, False, []
        for ln, code in zip(lines, flags):
            if code:
                continue
            st = ln.strip()
            if st.startswith("#"):
                after_table = False
            is_table = st.startswith("|")
            if prev_table and not is_table:
                after_table = True
            prev_table = is_table
            lm = _PASSPORT_LABEL_RE.match(ln) if after_table and not is_table else None
            if lm and lm.group(1) not in found:
                found.append(lm.group(1))
        if found:
            rows.append(f"{md.relative_to(docs).as_posix()}: "
                        + ", ".join(f"«{x}»" for x in found))
    if not rows:
        return []
    return _listing(f"⚠ строка паспорта вне таблицы — вернуть в таблицу: файлов {len(rows)}", rows)


# --- B9 (Т13): счётчик открытых вопросов по классам ---
# запись журнала — любой заголовок «## OQ-NNN…»: граница записи одна для сторожа B9, гейта
# переноса и порядка реестра link_debts; формат заголовка проверяется отдельно. Прежняя
# регулярка требовала ISO-дату и молча теряла записи без неё (FB-39 КК, 12 записей, 2026-10-28)
OQ_ENTRY_RE = re.compile(r"^##\s+OQ-(\d+)\b([^\n]*)$", re.M)
# две формы заголовка по норме гида: «## OQ-NNN — ГГГГ-ММ-ДД — …» (рекомендуется: дата нужна
# счёту давности) и «## OQ-NNN. …» (стенд, эталон, команды); прочие — строкой ⚠ (FB-39 КК)
_OQ_CANON_HEAD_RE = re.compile(r"^\s+—\s+\d{4}-\d{2}-\d{2}\s+—\s+\S")
_OQ_DOT_HEAD_RE = re.compile(r"^\.\s+\S")
# дата — первым словом после номера, в двух формах: ГГГГ-ММ-ДД и ДД.ММ.ГГГГ
_OQ_HEAD_DATE_RE = re.compile(
    r"^(\s*[—–-]*\s*)(?:(\d{4})-(\d{2})-(\d{2})|(\d{2})\.(\d{2})\.(\d{4}))(?![\d.-])(\s*[—–-]*\s*)")
# строка статуса записи журнала в обеих формах: «- **Статус:** …» (шаблон канона) и
# «- Статус: …» (КК, 331 запись); один дом — здесь, гейт переноса импортирует (Д-49 п. 3)
OQ_STATUS_RE = re.compile(r"^\s*-\s*(?:\*\*Статус:?\*\*:?|Статус:)\s*([^\n]+)$", re.M)
_OQ_STATUS_RE = OQ_STATUS_RE
_CLOSED = ("закрыт", "решен", "решён", "реализован", "реализовано", "снят")


def _oq_class(status: str) -> str:
    w = re.split(r"[\s,.;:(—–-]+", status.strip().lower())[0].replace("ё", "е")
    if w.startswith("открыт"):
        return "открыт"
    if w.startswith("частично"):
        return "частично"
    if w.startswith("зафиксир"):
        return "зафиксировано"
    if any(w.startswith(c.replace("ё", "е")) for c in _CLOSED):
        return "закрыт"
    return "прочие"


# класс статуса записи журнала (открыт / частично / зафиксировано / закрыт / прочие) —
# общий для сторожа B9 и гейта переноса (Д-49 п. 3)
oq_status_class = _oq_class


def oq_entries(text: str) -> List[Tuple[str, str, str]]:
    """Записи журнала открытых вопросов: (номер, остаток заголовка, тело до следующей записи).
    Заголовок-образец в блоке кода записью не является (общее правило блоков кода прибора)."""
    text = blank_code(text, repl="", inline=False)
    heads = list(OQ_ENTRY_RE.finditer(text))
    return [(h.group(1), h.group(2),
             text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)])
            for i, h in enumerate(heads)]


def _sep_defect(sep: str) -> Optional[str]:
    if re.fullmatch(r"\s+—\s+", sep):
        return None
    s = sep.strip()
    if s == "—":
        return "разделитель «—» без пробелов"
    return f"разделитель «{s}»" if s else "нет разделителя «—»"


def _oq_head_check(rest: str) -> Tuple[Optional[date], Optional[str]]:
    """Дата заголовка записи (или None) и причина несоответствия обеим формам нормы
    (None — по форме). Причина — первая из: нет даты, разделитель, нет формулировки,
    дата не ISO."""
    m = _OQ_HEAD_DATE_RE.match(rest)
    d = None
    if m:
        y, mo, dd = m.group(2, 3, 4) if m.group(2) else m.group(7, 6, 5)
        try:
            d = date(int(y), int(mo), int(dd))
        except ValueError:
            pass
    if _OQ_CANON_HEAD_RE.match(rest) or _OQ_DOT_HEAD_RE.match(rest):
        return d, None
    if not m:
        return None, "нет даты"
    tail = rest[m.end():].strip()
    defect = _sep_defect(m.group(1)) or (
        "нет формулировки" if not tail else _sep_defect(m.group(8)))
    if defect:
        return d, defect
    if m.group(5):
        return d, f"дата {m.group(5)}.{m.group(6)}.{m.group(7)}"
    return d, "не по формату"


def _oq_runs(bad: List[Tuple[int, str, str]]) -> List[str]:
    """Номера записей подряд с одной причиной — диапазоном «OQ-a…OQ-b (причина)»."""
    out: List[str] = []
    i = 0
    while i < len(bad):
        j = i
        while j + 1 < len(bad) and bad[j + 1][2] == bad[i][2] and bad[j + 1][0] == bad[j][0] + 1:
            j += 1
        a, b = f"OQ-{bad[i][1]}", f"OQ-{bad[j][1]}"
        ids = a if j == i else (f"{a}, {b}" if j == i + 1 else f"{a}…{b}")
        out.append(f"{ids} ({bad[i][2]})")
        i = j + 1
    return out


def oq_class_counter(oq: Path, today: Optional[date] = None) -> List[str]:
    if not oq.is_file():
        return []
    entries = oq_entries(_text(oq))
    if not entries:
        return []
    today = today or date.today()
    counts = {"открыт": 0, "частично": 0, "зафиксировано": 0, "закрыт": 0, "прочие": 0}
    stale = 0
    bad: List[Tuple[int, str, str]] = []
    for num, rest, body in entries:
        sm = _OQ_STATUS_RE.search(body)
        cls = _oq_class(sm.group(1)) if sm else "прочие"
        counts[cls] += 1
        d, defect = _oq_head_check(rest)
        if defect:
            bad.append((int(num), num, defect))
        if cls == "открыт" and d and (today - d).days > 30:
            stale += 1
    line = (f"i OQ: всего {len(entries)}, открыт {counts['открыт']}, частично {counts['частично']}, "
            f"зафиксировано {counts['зафиксировано']}, закрыт {counts['закрыт']}")
    if counts["прочие"]:
        line += f", прочие {counts['прочие']}"
    out = [line + f"; открытых старше 30 дней — {stale}"]
    if bad:
        # ⚠, не i: запись с таким заголовком прежде терялась молча — сигнал приёмке (FB-39 КК)
        runs = _oq_runs(bad)
        shown = runs[:_LIMIT] + ([f"… и ещё {len(runs) - _LIMIT}"] if len(runs) > _LIMIT else [])
        out.append(f"⚠ заголовки реестра OQ не по формату «## OQ-NNN — ГГГГ-ММ-ДД — …» или «## OQ-NNN. …»: "
                   f"{len(bad)} — "
                   + ", ".join(shown))
    return out


# ================================================================ срез 2

# --- B1 (Т1): кнопки ЭФ не по шаблону, сообщения списком ---
_BUTTON_RE = re.compile(r"^### +B-(\d+)\b.*?(?=^### |^## |\Z)", re.M | re.S)
_MSG_SEC_RE = re.compile(r"^## +(?:\d+\.\s*)?Сообщения\s*$(.*?)(?=^## |\Z)", re.M | re.S)


def check_button_fields(docs: Path) -> List[str]:
    rows: List[str] = []
    msg_rows: List[str] = []
    for md in _kit_md(docs):
        if _fm(md).get("type") != "screen-form":
            continue
        text = _text(md)
        rel = md.relative_to(docs).as_posix()
        for m in _BUTTON_RE.finditer(text):
            body = m.group(0)
            # поле — «ярлык: значение» в начале строки (пункт списка или абзац, ярлык
            # жирным или нет): «- **При нажатии:** …», «Видимость: …». Проза «При нажатии
            # проводятся проверки…» и видимость в скобках заголовка — не поле шаблона
            lost = [f for f in ("Видимость", "При нажатии")
                    if not re.search(rf"^\s*(?:[-*]\s+)?(?:\*\*)?{f}(?::\*\*|\*\*:|:)",
                                     body, re.M)]
            if lost:
                rows.append(f"{rel}: B-{m.group(1)} — нет " + ", ".join(f"«{f}»" for f in lost))
        sm = _MSG_SEC_RE.search(text)
        if (sm and re.search(r"^\s*[-*]\s+(?:\*\*)?MSG-\d+", sm.group(1), re.M)
                and not re.search(r"^\|\s*MSG-\d+", sm.group(1), re.M)):
            msg_rows.append(rel)
    out: List[str] = []
    if rows:
        out += _listing(f"⚠ кнопка B-N без полей шаблона (Видимость / При нажатии) ×{len(rows)} "
                        "(screen-form.md §6)", rows)
    if msg_rows:
        out += _listing(f"⚠ сообщения ЭФ списком, а не таблицей «ID | Тип | Показ | Содержание»: "
                        f"файлов {len(msg_rows)} (screen-form.md §7)", msg_rows)
    return out


# --- B3 (Т6): карточка вызова не тонкая ---
_BASE_LINK_RE = re.compile(r"Базовый контракт[^\n]*?\b(?:EXTINT|INTC|MOD|LIBC)-")
# закрытый перечень разделов базового контракта, которых в карточке вызова быть не должно
# («Логика работы» — поведение внешней системы, содержание базы); расширять только по примеру
_BASE_SECTION_RE = re.compile(
    r"^#{2,4} +(?:\d+(?:\.\d+)*\.?\s*)?(Паспорт метода взаимодействия|Атрибутный состав|"
    r"Структура запроса|Структура ответа|Логика работы)\b", re.M)


def check_thick_calls(docs: Path) -> List[str]:
    rows: List[str] = []
    for md in _kit_md(docs):
        if _fm(md).get("type") != "contract-call" or md.name.lower() == "readme.md":
            continue
        text = _text(md)
        if not _BASE_LINK_RE.search(text):
            continue
        heads = []
        for m in _BASE_SECTION_RE.finditer(text):
            if m.group(1) not in heads:
                heads.append(m.group(1))
        if heads:
            rows.append(f"{md.relative_to(docs).as_posix()}: " + ", ".join(f"«{h}»" for h in heads))
    if not rows:
        return []
    return _listing(f"⚠ карточка вызова не тонкая: разделы базового контракта дублируются, "
                    f"истончить (contract-call.md, раздел B) ×{len(rows)}", rows)


# --- B6 (Т9): склейка абзацев ячейки источника ---
# (а) узкий симптом: имя типа, длина и сразу заглавная буква нового абзаца — «Строка(19)Допустимый»
_GLUE_RE = re.compile(r"(?:Строка|Число|Дата|Логический)\(\d+(?:,\d+)?\)[А-ЯЁA-Z]")


def check_cell_glue(docs: Path) -> List[str]:
    rows, total = [], 0
    for md in _kit_md(docs):
        lines = _text(md).splitlines()
        n = sum(len(_GLUE_RE.findall(ln)) for ln, code in zip(lines, code_line_flags(lines))
                if not code and ln.lstrip().startswith("|"))
        if n:
            rows.append(f"{md.relative_to(docs).as_posix()} ×{n}")
            total += n
    if not rows:
        return []
    return _listing(f"⚠ склейка абзацев ячейки источника — вставить <br>: мест {total} в "
                    f"{len(rows)} файлах", rows)


# (б) причина: ячейки перенесены не из нормализованной копии (протокол §5)
_PIDS_RE = re.compile(r"^confluence_page_ids:\s*\[([^\]]*)\]", re.M)
_PID1_RE = re.compile(r"^confluence_page_id:\s*['\"]?(\d+)", re.M)


def _normalized_dir(docs: Path) -> Optional[Path]:
    for base in (docs.parent, docs):
        d = base / "sandbox" / "normalized"
        if d.is_dir():
            return d
    return None


def check_unnormalized_sources(docs: Path, idx: Dict[str, Path]) -> List[str]:
    """Reverse-карточка с таблицей, чья главная страница-источник несёт HTML-таблицы, а
    нормализованной копии страницы в sandbox/normalized нет. Каталога нет — молчим
    (комплект не по протоколу нормализации, судить не по чему)."""
    ndir = _normalized_dir(docs)
    if ndir is None or not idx:
        return []
    have = set()
    for p in ndir.rglob("*.md"):
        if p.name.endswith(".tables.md"):
            continue
        m = _PID1_RE.search(_text(p))
        if m:
            have.add(m.group(1))
        elif re.fullmatch(r"\d+", p.stem):
            have.add(p.stem)
    rows: List[str] = []
    html_cache: Dict[str, bool] = {}
    for md in _kit_md(docs):
        if md.name.lower() == "readme.md":
            continue
        text = _text(md)
        m = _PIDS_RE.search(text)
        ids = re.findall(r"\d+", m.group(1)) if m else []
        if not ids or ids[0] in have or ids[0] not in idx:
            continue
        pid = ids[0]
        if pid not in html_cache:
            html_cache[pid] = "<table" in _text(idx[pid]).lower()
        if html_cache[pid] and re.search(r"^\s*\|.*\|\s*$", text, re.M):
            rows.append(f"{md.relative_to(docs).as_posix()} ← {pid}")
    if not rows:
        return []
    # одна сводная строка на комплект: масштаб бывает большим (КК — 86), перечень — в --out
    head = ", ".join(r.split(" ← ")[0] for r in rows[:3])
    more = f", и ещё {len(rows) - 3}" if len(rows) > 3 else ""
    return ([f"⚠ источник с таблицами перенесён без нормализованной копии (протокол §5): "
             f"{len(rows)} карточек ({head}{more})"]
            + [f"{_OUT_ONLY}{r}" for r in rows])


# --- B8 (Т4): подозрение на неверный тип function ---
_NOT_FUNCTION_TITLE_RE = re.compile(r"СПП|Состав подписываем|Параметры вызова|\bСостав\b")
_BEHAVIOUR_RE = re.compile(r"^## +(?:\d+\.\s*)?Поведение\s*$(.*?)(?=^## |\Z)", re.M | re.S)


def check_function_kind_suspect(docs: Path) -> List[str]:
    rows: List[str] = []
    for md in _kit_md(docs):
        fm = _fm(md)
        if fm.get("type") != "function" or fm.get("kind", "operation") != "operation":
            continue
        title = fm.get("title", "")
        if not _NOT_FUNCTION_TITLE_RE.search(title):
            continue
        beh = _BEHAVIOUR_RE.search(_text(md))
        if beh and re.search(r"Шаг\s*№?\s*\d", beh.group(1)):
            continue  # поведение с шагами есть — функция
        rows.append(f"{md.relative_to(docs).as_posix()} — «{title[:80]}»")
    if not rows:
        return []
    return _listing(f"⚠ похоже не функция ×{len(rows)}: СПП → dictionaries.md, параметры вызова → "
                    "CALL-INT (create-artifact, дерево метода)", rows)
