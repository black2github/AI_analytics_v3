# app/scripts/CI/link_debts.py
#
# Сторож долгов ссылок: URL несёт два смысла — семантический (связь) и
# навигационный (переход). Семантику держит матрица трассировки; навигацию
# восстанавливает заход-создатель цели (правило create-artifact «закрытие
# входящих долгов»). Утилита проверяет, что механизм не молчит:
#
#   1) ПРОСРОЧКА: долг, чья цель уже существует в комплекте, — брак
#      (заход-создатель не закрыл входящие долги: ссылка не проставлена).
#   2) ИСПОЛНИМОСТЬ: дословное имя долга находится в документе-ожидателе
#      (иначе долг нельзя закрыть механической заменой «имя → ссылка» —
#      нарушена дословность упоминания, чинить в документе).
#
# Формат строки долга в матрице (create-artifact, шаг 6):
#   | <FROM-ID[, FROM-ID…]> | — | нет целевого артефакта <тип> «<дословное имя>» — требуется заход <скилл> |
# Имя опционально для однофайловых типов (rbac): существование проверяется
# по типу в реестре ID. Диапазоны FROM («FUN-BNK-01…05») разворачиваются.
#
# Второй формат (решение 2026-10-14, комментарии платформы AI Factory: реестр
# долгов должен включать все известные проблемы, не только отсутствующие
# ссылки) — долг БЕЗ отсутствующей цели:
#   | <FROM-ID[, …]> | — | долг <вид>: «<формулировка>» — причина: <…>; ответственный: <кто>;
#     ограничение: <какое поведение нельзя разрабатывать>; закрытие: <условие>[; источник: OQ-NNN] |
# Виды — закрытый перечень: открытый вопрос, противоречие, правило на
# изображении, источник недоступен. Поля ответственный / ограничение /
# закрытие обязательны; у вида «открытый вопрос» обязателен источник OQ-NNN
# (журнал open-questions.md в docs-репозиторий не переезжает — вопрос должен
# жить в строке целиком). Просрочка и исполнимость к таким строкам не
# применяются (цели нет); сторожится полнота полей и наличие FROM-ID в
# реестре. Раньше такие строки раздел тихо игнорировал.
#
# Вид «вне плана» (FB-29 КК, решение владельца канона 2026-10-20): цель
# ссылки не появится по решению — подсервис вне плана миграции; долг
# остаётся видимым, снятия открытого долга нет:
#   | <FROM-ID> | — | долг вне плана: «<дословное имя>» — причина: подсервис <слаг>
#     вне плана миграции (OQ-NNN); ответственный: владелец комплекта;
#     ограничение: <…>; закрытие: включение подсервиса в план |
# OQ-NNN обязателен (решение владельца комплекта записано). Ограничитель:
# видом нельзя спрятать исполнимый долг — слаг из причины сверяется с
# подсервисами migration-plan.md комплекта (только ⚠).
#
# Стадии запуска (одна утилита, три рубежа): самопроверка агента в заходе →
# приёмка эксперта → CI docs-репо (после переезда комплекта).
#
# Мягкий гейт: код 0 и отчёт; --strict — код 2 при нарушениях.

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
try:
    from kitcheck import fs as _fs  # noqa: E402
    from kitcheck.fence import issues as fence_issues  # noqa: E402
    from kitcheck.md import blank_code, split_cells  # noqa: E402
    from source_coverage import find_kit_file, is_zone_row, plan_slugs, read_inventory  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck import fs as _fs  # type: ignore  # noqa: E402
    from .kitcheck.fence import issues as fence_issues  # type: ignore  # noqa: E402
    from .kitcheck.md import blank_code, split_cells  # type: ignore  # noqa: E402
    from .source_coverage import find_kit_file, is_zone_row, plan_slugs, read_inventory  # type: ignore  # noqa: E402

_DEBT_RE = re.compile(
    r"нет целевого артефакта\s+([\w./-]+)(?:\s+«([^»]+)»)?", re.IGNORECASE)
# Межсервисный долг: цель принадлежит другому сервису Экосистемы —
# владелец указывается в строке долга («…«имя» у владельца <service-id>…»,
# create-artifact «Недостающая цель ссылки», микро-волна 2026-08-23).
# Локальная просрочка для таких долгов не проверяется (цель живёт в
# чужом репозитории), исполнимость имени — как обычно.
_OWNER_RE = re.compile(r"»\s+у\s+владельца\s+([\w.-]+)", re.IGNORECASE)
_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
OUT_OF_PLAN_KIND = "вне плана"
ISSUE_KINDS = ("открытый вопрос", "противоречие", "правило на изображении",
               "источник недоступен", OUT_OF_PLAN_KIND)
# слаг подсервиса в причине долга «вне плана»: «подсервис bc-widget» / «зона bc-widget»
_CAUSE_SLUG_RE = re.compile(r"(?:подсервис|зона)\s+`?([a-z0-9][a-z0-9-]*)", re.IGNORECASE)
_OQ_ANY_RE = re.compile(r"\bOQ-\d+\b")
_ISSUE_RE = re.compile(
    r"долг\s+(" + "|".join(ISSUE_KINDS) + r")\s*:\s*«([^»]+)»", re.IGNORECASE)
_ISSUE_FIELD_RES = {
    "cause": re.compile(r"причина:\s*([^;|]+)", re.IGNORECASE),
    "responsible": re.compile(r"ответственный:\s*([^;|]+)", re.IGNORECASE),
    "constraint": re.compile(r"ограничение:\s*([^;|]+)", re.IGNORECASE),
    "closure": re.compile(r"закрытие:\s*([^;|]+)", re.IGNORECASE),
    # OQ-NNN — журнал рабочего репозитория; T-<JIRA-ID>[-NN] — постановка
    # tasks/<JIRA-ID>.md режима C (в docs-репозитории журнала нет; полигон 15.10)
    "source": re.compile(r"источник:\s*(OQ-\d+|T-[A-Z][A-Z0-9]*-\d+(?:-\d+)?)", re.IGNORECASE),
}
ISSUE_REQUIRED = {"responsible": "ответственный", "constraint": "ограничение",
                  "closure": "закрытие"}

# Третий формат — пробел НФТ (шаблон nfr.md, скилл create-nfr): это не
# отсутствующий артефакт, а названное в колонке «Не задано» значение:
#   | nfr-<код> | — | «<текст пробела>» |
# Просрочка «цель уже существует» к пробелу не применяется — тексту и
# положено стоять на странице. Исполнимость та же: цитата находится в
# файле страницы типа.
_GAP_RE = re.compile(r"—\s+«([^»]+)»\s*$")

# Четвёртый формат — обязательный долг настраиваемого параметра (скилл
# create-artifact: «параметр <ключ> не зафиксирован — требуется дозаход
# create-data-model»). До 2026-10-15 раздел такие строки молча пропускал
# (ЗК-29 реестра замечаний ОНБ-В: матрица ОНБ-В:227). Просрочка — ключ уже
# есть в data-model/dictionaries.md; исполнимость — ключ назван в
# документе-ожидателе.
_PARAM_DEBT_RE = re.compile(r"параметр\s+(.+?)\s+не\s+зафиксирован", re.IGNORECASE)
_DEBTS_HEADING = "Долги по ссылкам"
# раздел узнаётся и под нестандартным именем («Долги ссылок» у КК, 16.10):
# иначе строки не сторожатся и гейт показывает ложную чистоту; отклонение
# имени от нормы — отдельное предупреждение (имя раздела — структурный факт,
# по нему раздел читают гейт переноса и платформа)
_DEBTS_HEADING_RE = re.compile(r"долг\w*\s+(?:по\s+)?ссыл", re.IGNORECASE)
_SEP_CELL_RE = re.compile(r"^:?-{3,}:?$")
# закрытый долг: во 2-й колонке ID появившейся цели — голый или markdown-ссылкой
# «[ID](путь)» / «[ID Название](путь)» (форма 5; КК 16.10 — 43 строки ссылками)
_CLOSED_TARGET_RE = re.compile(
    r"^\[?(?:[A-ZА-Я]{2,}[-\w]*|nfr(?:-[a-z]{3}(?:-\d{3})?)?)(?:\.\d+)*(?:\.\.\d+)?(?:[^\]]*\])?(?:\([^)]*\))?$")
_LINK_ONLY_RE = re.compile(r"^(?:\[[^\]]+\]\([^)]+\)\s*,?\s*)+$")


def _closed_debt(cells: List[str]) -> bool:
    """Закрытый долг (цель появилась): во 2-й колонке ID цели — голый, ссылкой,
    перечнем или диапазоном (`FUN-SYS-07, FUN-SYS-08`, `EXTINT-F1-008..013`);
    либо «—» во 2-й и только ссылки на карточки в 3-й (КК, 16.10)."""
    if len(cells) < 2:
        return False
    if cells[1] != "—":
        toks = [t.strip() for t in cells[1].split(",") if t.strip()]
        return bool(toks) and all(_CLOSED_TARGET_RE.match(t) for t in toks)
    return len(cells) >= 3 and bool(_LINK_ONLY_RE.match(cells[2]))
# базовый контракт внешней АС (docs-external-contracts): «нет базового контракта
# «<имя>» [у владельца <код АС>] — требуется контур base» — форма 1 с типом
# base-contract; владелец — внешняя система, в каталоге сервисов её нет
_BASE_DEBT_RE = re.compile(r"нет\s+базового\s+контракта\s+«([^»]+)»", re.IGNORECASE)


# Волна 9 ОНБ-В (ЗК-10, ЗК-11): долг «требуется заход create-data-model /
# create-internal-contracts» на цель, которая похоже принадлежит другому сервису или
# внешней системе (команда ОНБ-В завела 9 таких долгов на чужие данные и 8 — на чужие
# методы; формула «у владельца» не применялась). Только ⚠: квалификацию цели делает
# аналитик (create-artifact, правило долга).
_FOREIGN_SKILL_RE = re.compile(r"требуется\s+заход\s+(create-data-model|create-internal-contracts)",
                               re.IGNORECASE)
_FOREIGN_DM_WORDS = ("справочник", "подразделени", "классификатор", "внешн")
_FOREIGN_STOP = {"сервис", "сервиса", "система", "системы", "банк", "банка", "банке",
                 "функция", "функции", "концепция"}
# общие основы, которые в каталоге редки, но в именах целей обычны («Заявка на управление …»)
_FOREIGN_STOP_STEMS = {"управ"}
_LETTER = r"A-Za-zА-Яа-яЁё"


def _word_re(tok: str):
    return re.compile(r"(?<![" + _LETTER + r"])" + re.escape(tok) + r"(?![" + _LETTER + r"])",
                      re.IGNORECASE)


def _stem(word: str) -> str:
    """Основа слова для сравнения форм («заявка», «заявки», «заявок» → «заявк»)."""
    return word.lower().replace("ё", "е")[:5]


def foreign_target_signs(catalog: Optional[List[dict]], own: Optional[str]):
    """Признаки чужих сервисов из каталога: ([(регулярка, признак, service-id)], теги
    своего сервиса). Слово названия значимо, если длиной от 5 букв, не общее и его
    основа встречается в названии только одного сервиса каталога; тег в квадратных
    скобках — от 3 букв. Свой сервис (`service:` комплекта — код или ключ каталога)
    признаков не даёт."""
    if not catalog:
        return [], set()
    names = [(s.get("code") or "", s.get("key") or "", s.get("name") or "")
             for s in catalog if isinstance(s, dict)]
    freq: Dict[str, int] = {}
    for _c, _k, nm in names:
        for st in {_stem(w) for w in re.findall(r"[" + _LETTER + r"]{5,}", nm)}:
            freq[st] = freq.get(st, 0) + 1
    out = []
    own_tags = set()
    for code, key, nm in names:
        if not code:
            continue
        if own and own in (code, key):
            own_tags |= {t.strip() for t in re.findall(r"\[([^\]]+)\]", nm)}
            continue
        out.append((_word_re(code), f"код сервиса {code}", code))
        if len(key) >= 2:
            out.append((_word_re(key), f"ключ сервиса {key} ({code})", code))
        for tag in re.findall(r"\[([^\]]{3,})\]", nm):
            out.append((_word_re(tag.strip()), f"тег сервиса [{tag.strip()}] ({code})", code))
        for w in {w for w in re.findall(r"[" + _LETTER + r"]{5,}", nm)}:
            if (w.lower() not in _FOREIGN_STOP and _stem(w) not in _FOREIGN_STOP_STEMS
                    and freq.get(_stem(w), 0) <= 1):
                rx = re.compile(r"(?<![" + _LETTER + r"])" + re.escape(_stem(w)) + r"[" + _LETTER + r"]*",
                                re.IGNORECASE)
                out.append((rx, f"слово «{w}» названия сервиса {code}", code))
    return out, own_tags


def _own_service(docs_root: Path) -> Optional[str]:
    """Код документируемого сервиса — самый частый `service:` в шапках комплекта."""
    seen: Dict[str, int] = {}
    for p in list(docs_root.rglob("*.md"))[:400]:
        try:
            head = _fs.read_text(p, encoding="utf-8", errors="replace")[:600]
        except OSError:
            continue
        m = re.search(r"^service:\s*['\"]?([\w.-]+)", head, re.M)
        if m:
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
    return max(seen, key=seen.get) if seen else None


def foreign_target_sign(name: str, skill: str, signs, own_tags=frozenset()) -> Optional[str]:
    """Первый признак чужой цели в имени долга либо None. Имя с тегом своего сервиса
    или его подсервиса («[КК]», «[КК_ЛК] …») — своя цель."""
    tag = re.match(r"\s*\[([^\]]+)\]", name)
    if tag and any(tag.group(1).strip() == t or tag.group(1).strip().startswith(t + "_")
                   for t in own_tags):
        return None
    # для данных сначала признаки внешней системы и справочника — они точнее слова
    # из названия чужого сервиса
    if skill.lower() == "create-data-model":
        if re.search(r"(?<![" + _LETTER + r"])АС\s", name):
            return "«АС » — внешняя система"
        low = name.lower()
        for w in _FOREIGN_DM_WORDS:
            if w in low:
                return f"слово «{w}…»"
    for rx, label, _code in signs:
        if rx.search(name):
            return label
    return None


def debts_heading(matrix_text: str) -> Optional[str]:
    """Фактический заголовок раздела долгов (текст без «#» и номера) или None."""
    for ln in matrix_text.splitlines():
        if ln.startswith("#") and _DEBTS_HEADING_RE.search(ln):
            return re.sub(r"^#+\s*(?:\d+\.\s*)?", "", ln).strip()
    return None


def _zone_target(name: str, zone_titles: List[str]) -> Optional[str]:
    """Титул страницы зоны «вне Экосистемы» (дословно по описи), с которым совпадает
    имя цели долга: дословно, без тега «[…]» или как хвост «…: <имя>» (ЭФ виджета
    «ЭФ Клиента: X» у долга названа «[тег] X»). Только для ⚠ — широта совпадения
    допустима."""
    untag = lambda s: re.sub(r"^\[[^\]]+\]\s*", "", s)  # noqa: E731
    nn = _norm(name)
    for title in zone_titles:
        t = _norm(title)
        if nn == t or untag(nn) == untag(t) or untag(t).endswith(": " + untag(nn)):
            return title
    return None


def issue_fields(row: str) -> Optional[dict]:
    """Поля строки долга без цели (None — строка не этого формата):
    kind, statement, cause, responsible, constraint, closure, source, missing
    (перечень обязательных полей, которых нет, русскими именами)."""
    m = _ISSUE_RE.search(row)
    if not m:
        return None
    out = {"kind": m.group(1).lower(), "statement": m.group(2).strip()}
    for key, rx in _ISSUE_FIELD_RES.items():
        fm = rx.search(row)
        out[key] = fm.group(1).strip() if fm else None
    missing = [name for key, name in ISSUE_REQUIRED.items() if not out[key]]
    if out["kind"] == "открытый вопрос" and not out["source"]:
        missing.append("источник OQ-NNN или T-<JIRA-ID>")
    # «вне плана»: решение владельца комплекта записано в журнале — OQ-NNN в
    # строке обязателен (в причине «(OQ-NNN)» или полем «источник:»)
    if out["kind"] == OUT_OF_PLAN_KIND and not _OQ_ANY_RE.search(row):
        missing.append("источник OQ-NNN")
    out["missing"] = missing
    return out

_RANGE_RE = re.compile(r"^(.*?)(\d+)\s*(?:…|\.\.\.)\s*(\d+)$")
_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$")
_TYPE_RE = re.compile(r"^type:\s*['\"]?([a-z][a-z-]*)['\"]?\s*$")


def _norm(s: str) -> str:
    s = re.sub(r"[«»\"'`]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _expand_from(cell: str) -> List[str]:
    ids: List[str] = []
    for tok in re.split(r"[,;]\s*", cell.strip()):
        tok = tok.strip().strip("*").strip()
        if not tok or tok in "—-":
            continue
        m = _RANGE_RE.match(tok)
        if m:
            prefix, a, b = m.group(1), m.group(2), m.group(3)
            width = len(a)
            ids.extend(f"{prefix}{i:0{width}d}"
                       for i in range(int(a), int(b) + 1))
        else:
            ids.append(tok)
    return ids


def _doc_title(path: Path) -> Optional[str]:
    """title из frontmatter; YAML-перенос длинного значения склеивается."""
    try:
        text = _fs.read_text(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return None
    lines = body.splitlines()
    for i, ln in enumerate(lines[1:60], start=1):
        if ln.strip() == "---":
            return None
        m = _TITLE_RE.match(ln)
        if not m:
            continue
        v = m.group(1)
        q = v[0] if v and v[0] in "'\"" else None
        closed = (q is None or (len(v) >= 2 and v.endswith(q)
                                and not v.endswith(q * 2)))
        j = i + 1
        while not closed and j < len(lines) and lines[j].startswith(" "):
            v += " " + lines[j].strip()
            closed = v.endswith(q) and not v.endswith(q * 2)
            j += 1
        if q and len(v) >= 2 and v.endswith(q):
            v = v[1:-1]
            if q == "'":
                v = v.replace("''", "'")
        return v
    return None


def _doc_type(path: Path) -> str:
    """type из frontmatter карточки (матрица по шаблону канона колонки «Тип»
    в реестре не имеет — тип карточки берётся из её шапки)."""
    try:
        text = _fs.read_text(path, encoding="utf-8", errors="replace")
    except OSError:
        return ""
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return ""
    for ln in body.splitlines()[1:60]:
        if ln.strip() == "---":
            return ""
        m = _TYPE_RE.match(ln)
        if m:
            return m.group(1).lower()
    return ""


def parse_matrix(matrix_text: str):
    """(реестр: ID -> (тип, файл),
    долги: [(from_ids, тип, имя|None, владелец|None, строка)])."""
    registry, debts, _unrec = parse_matrix_full(matrix_text)
    return registry, debts


def parse_matrix_full(matrix_text: str):
    """То же плюс третий элемент — строки раздела «Долги по ссылкам», не
    подошедшие ни под один формат долга (без заголовка таблицы и
    разделителя). Раздел узнаётся по заголовку (имя раздела — структурный
    факт SF-02); вне раздела нераспознанные строки не собираются: в других
    разделах матрицы ячейка «—» законна (покрытие процессов). Молчаливый
    пропуск строки долга — потеря обязательства (ЗК-29 ОНБ-В, 2026-10-15)."""
    registry: Dict[str, Tuple[str, str]] = {}
    debts: List[Tuple[List[str], str, Optional[str], Optional[str], str]] = []
    unrecognized: List[str] = []
    in_debts = False
    header_seen = False
    for ln in matrix_text.splitlines():
        if ln.startswith("#"):
            in_debts = bool(_DEBTS_HEADING_RE.search(ln))
            header_seen = False
            continue
        row = _ROW_RE.match(ln)
        if not row:
            continue
        cells = [c.strip() for c in split_cells(row.group(1))]
        joined = " ".join(cells)
        if in_debts:
            if all(_SEP_CELL_RE.match(c) for c in cells if c):
                continue
            if not header_seen:
                header_seen = True
                continue
            # закрытый долг: во второй колонке — ID появившейся цели
            # (lk-mp, ОНБ-В: «| ENT-001 | FUN-CL-03 | <название> |»), долга
            # больше нет — строка не сторожится и не считается нераспознанной
            if _closed_debt(cells):
                continue
        issue = issue_fields(joined)
        if issue:
            # долг без цели: тип — «долг:<вид>», имя — формулировка,
            # владелец — ответственный (межсервисным не считается)
            debts.append((_expand_from(cells[0]), "долг:" + issue["kind"],
                          issue["statement"], None, ln.strip()))
            continue
        gap = _GAP_RE.search(joined)
        if gap and cells[0].lower().startswith("nfr"):
            debts.append((_expand_from(cells[0]), "nfr-gap", gap.group(1),
                          None, ln.strip()))
            continue
        m = _DEBT_RE.search(joined)
        if m:
            owner = _OWNER_RE.search(joined)
            debts.append((_expand_from(cells[0]), m.group(1), m.group(2),
                          owner.group(1) if owner else None, ln.strip()))
            continue
        bm = _BASE_DEBT_RE.search(joined)
        if bm:
            owner = _OWNER_RE.search(joined)
            debts.append((_expand_from(cells[0]), "base-contract", bm.group(1).strip(),
                          owner.group(1) if owner else "внешняя АС", ln.strip()))
            continue
        pm = _PARAM_DEBT_RE.search(joined)
        if pm:
            debts.append((_expand_from(cells[0]), "параметр", pm.group(1).strip(),
                          None, ln.strip()))
            continue
        if in_debts:
            unrecognized.append(ln.strip())
            continue
        # реестр ID: первая ячейка — ID, любая другая несёт путь .md
        # (голый или внутри markdown-ссылки). Жёсткая 4-колонная форма
        # «| ID | Тип | Наименование | Файл |» видела 7 записей из ~40:
        # реальные реестры матрицы разноколонны («| ID | Название |
        # Файл |», у функций «| ID | page_id | Файл |») и пишут файл
        # ссылкой — слепая зона жила до первого именованного долга от
        # FUN-ID (пилот-3, 2026-08-19). Тип — только если ячейка после
        # ID выглядит словом типа (латиница с дефисом: data-model, rbac).
        # суб-ID с точкой (SCR-CL-01.0, SCR-BNK-05.1) — легальные ID
        # реестра (FRAME-01 2026-08-31: парсер их не принимал, и долги
        # групп нельзя было переписать на карточку-носитель); точка —
        # только перед цифрами, чтобы не принять имя файла за ID
        if (len(cells) >= 2
                and re.match(
                    # nfr / nfr-<код> / nfr-<код>-<номер> — строчные ID
                    # каталога НФТ (шаблон nfr.md); прежний класс [A-Z…]
                    # их не видел, и долг от страницы типа не находил свой
                    # файл в реестре
                    r"^(?:[A-ZА-Я]{2,}[-\w]*"
                    r"|nfr(?:-[a-z]{3}(?:-\d{3})?)?)"
                    r"(?:\.\d+)*$",
                    cells[0])):
            fpath = next((fm.group(0) for c in cells[1:]
                          for fm in [re.search(r"[\w./-]+\.md\b", c)]
                          if fm), None)
            if fpath:
                typ = (cells[1]
                       if re.fullmatch(r"[a-z][a-z-]*", cells[1]) else "")
                registry.setdefault(cells[0], (typ, fpath))
    return registry, debts, unrecognized


def check(matrix_path: Path, docs_root: Path,
          catalog_codes: Optional[set] = None,
          catalog: Optional[List[dict]] = None):
    """catalog_codes — коды сервисов каталога (`code` в services.json);
    None — каталог недоступен, владелец долга не сверяется. catalog — записи
    каталога (code, key, name) для признаков чужой цели долга (волна 9 ОНБ-В);
    без каталога признаки — только слова data-model."""
    foreign_signs, own_tags = foreign_target_signs(catalog, _own_service(docs_root))
    foreign: List[str] = []
    registry, debts, unrecognized = parse_matrix_full(
        _fs.read_text(matrix_path, encoding="utf-8", errors="replace"))
    dict_text = ""
    for dp in docs_root.rglob("dictionaries.md"):
        dict_text += _norm(_fs.read_text(dp, encoding="utf-8", errors="replace"))
    # титулы и типы существующих артефактов комплекта
    titles: Dict[Path, str] = {}
    for p in docs_root.rglob("*.md"):
        t = _doc_title(p)
        if t:
            titles[p] = _norm(t)
    # тип карточки по файлу (из реестра матрицы) — для сверки с типом долга
    type_of: Dict[str, str] = {}
    for _id, (typ, fpath) in registry.items():
        if typ:
            type_of[fpath.replace("\\", "/").lstrip("./")] = typ.lower()

    def _card_type(path: Path) -> str:
        rel = path.relative_to(docs_root).as_posix()
        typ = next((t for f, t in type_of.items()
                    if rel == f or rel.endswith("/" + f)), "")
        # реестр по шаблону канона колонки «Тип» не несёт — тип из шапки
        # карточки (FB-23 КК: долг dictionary совпадал с моделью статусов
        # того же названия и ложно считался просроченным)
        return typ or _doc_type(path)
    types_present = {t for t, _f in registry.values()}
    report: List[str] = []
    ok = True
    cross: Dict[str, int] = {}
    n_issue = 0
    n_gap = 0
    n_param = 0
    unknown_owners: Dict[str, int] = {}
    n_out_of_plan = 0
    out_of_plan_warn: List[str] = []
    plan = find_kit_file(docs_root, "migration-plan.md")
    slugs = plan_slugs(plan)[0] if plan is not None else set()
    # Д-46: титулы страниц зоны «вне Экосистемы» по описи — цель долга формы 1 в зоне
    inv_file = find_kit_file(docs_root, "inventory.md")
    zone_titles = ([r["title"] for r in read_inventory(inv_file).values()
                    if r.get("title") and is_zone_row(r)] if inv_file is not None else [])
    zone_warn: List[str] = []
    for from_ids, typ, name, owner, raw in debts:
        if typ.startswith("долг:"):
            # долг без цели: полнота полей и FROM-ID в реестре; просрочка
            # и исполнимость не применяются — цели нет
            n_issue += 1
            fields = issue_fields(raw) or {"missing": []}
            if fields["missing"]:
                report.append(f"долг без цели НЕПОЛОН: нет полей "
                              f"{', '.join(fields['missing'])} ✗ — {raw[:100]}")
                ok = False
            for fid in from_ids:
                if fid not in registry:
                    report.append(f"долг от {fid}: ID отсутствует в реестре "
                                  f"матрицы ✗ — {raw[:80]}")
                    ok = False
            if fields.get("kind") == OUT_OF_PLAN_KIND:
                n_out_of_plan += 1
                who = ", ".join(from_ids)
                sm = _CAUSE_SLUG_RE.search(fields.get("cause") or "")
                if sm and slugs and sm.group(1).lower() in slugs:
                    out_of_plan_warn.append(
                        f"⚠ долг «вне плана» от {who}: подсервис «{sm.group(1)}» есть в плане "
                        "миграции — вид не подходит, долг по ссылке формой 1")
                elif not sm:
                    out_of_plan_warn.append(
                        f"⚠ долг «вне плана» от {who}: причина не называет подсервис — "
                        "проверить приёмкой")
                elif plan is None:
                    out_of_plan_warn.append(
                        f"⚠ долг «вне плана» от {who}: план миграции (migration-plan.md) не "
                        "найден — проверить приёмкой")
                elif not slugs:
                    out_of_plan_warn.append(
                        f"⚠ долг «вне плана» от {who}: план миграции не называет подсервисов — "
                        "проверить приёмкой")
            continue
        # 1) просрочка: цель существует? (межсервисный долг — цель в
        # чужом репозитории, локальная просрочка не проверяется; пробел
        # НФТ — цели-артефакта нет, цитата обязана быть на странице)
        if typ == "nfr-gap":
            n_gap += 1
        elif typ == "параметр":
            n_param += 1
            if name and _norm(name) in dict_text:
                report.append(f"ПРОСРОЧЕН долг: параметр «{name}» уже зафиксирован в "
                              f"dictionaries.md, долг не снят ✗ — {raw[:100]}")
                ok = False
        elif owner is not None:
            cross[owner] = cross.get(owner, 0) + 1
            if (catalog_codes is not None and owner not in catalog_codes
                    and typ != "base-contract"):
                unknown_owners[owner] = unknown_owners.get(owner, 0) + 1
        else:
            zt = _zone_target(name, zone_titles) if name else None
            if zt:
                zone_warn.append(
                    f"⚠ долг {', '.join(from_ids)} «{name}» — цель в зоне «вне Экосистемы» "
                    f"(опись: «{zt}»): долг формы 1 не заводится, цель — мини-комплект "
                    "modules/<имя>/ (Д-46)")
            fm = _FOREIGN_SKILL_RE.search(raw)
            sign = foreign_target_sign(name, fm.group(1), foreign_signs, own_tags) if (fm and name) else None
            if sign:
                foreign.append(f"⚠ долг {', '.join(from_ids)} «{name}» — похоже на чужую цель "
                               f"({sign}): данные/метод другого сервиса — формула «у владельца "
                               "<service-id>», справочник платформы — EXT в dictionaries.md, "
                               "внешняя АС — карточка вызова (create-artifact, правило долга)")
            target = None
            if name:
                # FB-02 common-dictionary (2026-10-14): «цель существует» —
                # карточка с ТЕМ ЖЕ заголовком (с тегом или без) и, если тип
                # известен, того же типа; поиск подстрокой ловил чужой
                # заголовок («…что пользователь является УЛ» для долга
                # data-model «Пользователь») и останавливал приёмку этапа
                nname = _norm(name)
                want = typ.lower()
                for p, t in titles.items():
                    tagless = re.sub(r"^\[[^\]]+\]\s*", "", t)
                    if t != nname and tagless != nname:
                        continue
                    ct = _card_type(p)
                    if ct and want and ct != want:
                        continue
                    target = p
                    break
            elif not name:
                target = typ if typ.lower() in {t.lower()
                                                for t in types_present} \
                    else None
            if target:
                report.append(f"ПРОСРОЧЕН долг: цель существует "
                              f"({target if isinstance(target, str) else target.name}), "
                              f"ссылка не проставлена ✗ — {raw[:100]}")
                ok = False
        # 2) исполнимость: имя находится в документах-ожидателях
        if not name:
            continue
        nname = _norm(name)
        for fid in from_ids:
            reg = registry.get(fid)
            if not reg:
                report.append(f"долг от {fid}: ID отсутствует в реестре "
                              f"матрицы ✗ — {raw[:80]}")
                ok = False
                continue
            doc = docs_root / reg[1]
            if not doc.is_file():
                report.append(f"долг от {fid}: файл реестра не найден "
                              f"({reg[1]}) ✗")
                ok = False
                continue
            body = _norm(_fs.read_text(doc, encoding="utf-8", errors="replace"))
            if nname not in body:
                report.append(
                    f"долг НЕИСПОЛНИМ: имя «{name}» не найдено дословно в "
                    f"{reg[1]} ✗ (замена «имя → ссылка» невозможна — "
                    "дословность упоминания нарушена)")
                ok = False
    if n_issue:
        report.append(f"долгов без отсутствующей цели {n_issue} (открытые "
                      "вопросы, противоречия, правила на изображении, "
                      "недоступные источники, вне плана) — сторожится полнота полей"
                      + (f"; из них «вне плана» {n_out_of_plan}" if n_out_of_plan else ""))
    report.extend(out_of_plan_warn)
    report.extend(zone_warn)
    if n_gap:
        report.append(f"пробелов НФТ {n_gap} («Не задано» на страницах типов) "
                      "— просрочка не применяется, цитата сторожится")
    if n_param:
        report.append(f"долгов параметров {n_param} («параметр … не зафиксирован») "
                      "— просрочка по dictionaries.md")
    report.extend(foreign)
    for owner_code, n in sorted(unknown_owners.items()):
        # переименование кода в каталоге без уведомления (ЗК-11 ОНБ-В:
        # shortLinkDirectory → short-link) оставляет долги на несуществующий код
        report.append(f"⚠ владелец «{owner_code}» ×{n}: кода нет в каталоге сервисов "
                      "(переименован или опечатка) — долг не адресуется")
    heading = debts_heading(_fs.read_text(matrix_path, encoding="utf-8", errors="replace"))
    if heading is not None and heading.lower() != _DEBTS_HEADING.lower():
        report.append(f"⚠ раздел долгов назван «{heading}» — норма «{_DEBTS_HEADING}» "
                      "(имя раздела читают гейт переноса и платформа; шаблон матрицы)")
    for ln_ in unrecognized:
        report.append(f"⚠ строка раздела «{_DEBTS_HEADING}» не распознана ни одним "
                      f"форматом долга — не сторожится: {ln_[:120]}")
    if unrecognized:
        report.append(f"нераспознанных строк раздела долгов {len(unrecognized)} — "
                      "форматы: «нет целевого артефакта …», «долг <вид>: …», "
                      "«параметр … не зафиксирован», пробел НФТ «| nfr-<код> | — | «…» |»")
    if cross:
        report.append(
            f"межсервисных долгов {sum(cross.values())} "
            f"(владельцы: {', '.join(sorted(cross))}) — локальная "
            "просрочка не проверяется, дозакрытие при появлении "
            "комплекта владельца ✓")
    if ok:
        report.append(f"OK: долгов {len(debts)}, просроченных нет, "
                      "все имена находятся в документах-ожидателях ✓")
    return report, ok


_OQ_NUM_RE = re.compile(r"^##\s+OQ-(\d+)\b", re.M)

# Настраиваемые параметры: упоминание «[Настраиваемые параметры]
# <сервис>.<ключ>» в документах комплекта требует строки с этим ключом в
# разделе параметров data-model/dictionaries.md (conventions §5.2 —
# параметры фиксируются вместе со значениями; инцидент src-locks
# 2026-08-15: h2h_in_path/h2h_path_polling_time упоминались агентом и
# процессом, в справочнике отсутствовали, долг не заводился).
# пробелы вокруг точки допускаются: «БлокН2Н .h2h_out_path» — дефект
# набора источника прятал третий параметр от сторожа (src-locks)
_PARAM_MENTION_RE = re.compile(
    r"Настраиваемые параметры\W{0,4}\s+[\w-]+(?:\.[\w-]+)*\s*\.\s*(\w+)")


def check_config_params(docs_root: Path) -> Tuple[List[str], bool]:
    dicts = docs_root / "srs" / "data-model" / "dictionaries.md"
    dict_text = (_fs.read_text(dicts, encoding="utf-8", errors="replace")
                 if dicts.is_file() else "")
    missing: Dict[str, List[str]] = {}
    for p in docs_root.rglob("*.md"):
        if "data-model" in p.parts:
            continue
        text = _fs.read_text(p, encoding="utf-8", errors="replace")
        for m in _PARAM_MENTION_RE.finditer(text):
            key = m.group(1)
            if key not in dict_text:
                missing.setdefault(key, []).append(p.name)
    if missing:
        return [f"настраиваемые параметры без строки в dictionaries "
                f"(conventions §5.2): "
                + "; ".join(f"{k} ({', '.join(sorted(set(v))[:2])})"
                            for k, v in sorted(missing.items()))
                + " ✗ — требуется дозаход create-data-model"], False
    return [], True


_FB_NUM_RE = re.compile(r"^##\s+FB-(\d+)\b", re.M)


def _fence_warnings(text: str, name: str) -> List[str]:
    """Предупреждения о блоках кода журнала, не закрытых по правилам GitLab
    (правило kitcheck/fence.py, решение владельца 2026-10-17): журнал читают
    люди, в платформу он не переезжает — сигнал, не брак."""
    out: List[str] = []
    for i in fence_issues(text.split("\n")):
        what = (f"закрыт ограждением с инфо-строкой (строка {i.close_line})"
                if i.kind == "close-with-info" else "не закрыт до конца файла")
        out.append(f"предупреждение: {name}: строка {i.line} — блок кода {what}: "
                   "в GitLab дальше всё код; закрыть голым ``` того же вида и длины")
    return out


def _check_register_order(path: Path, num_re, prefix: str,
                          name: str) -> Tuple[List[str], bool]:
    """Общий сторож append-only реестров записей «## <PREFIX>-NN»:
    номера монотонно возрастают по позиции в файле; вставка в середину
    и перемещение записей при правке — брак."""
    if not path.is_file():
        return [], True
    text = _fs.read_text(path, encoding="utf-8", errors="replace")
    warns = _fence_warnings(text, name)
    # заголовок-образец внутри блока кода записью не является (FB-04
    # «Корпоративных карт», 2026-09-15: пересозданный скелет с примером
    # формата давал «1 записей ✓» при нуле настоящих записей); границы
    # блоков — общее правило прибора (и ~~~, и ограждение с отступом)
    text = blank_code(text, repl="", inline=False)
    nums = [int(m.group(1)) for m in num_re.finditer(text)]
    bad = [(a, b) for a, b in zip(nums, nums[1:]) if b < a]
    if bad:
        return [f"{name}: порядок реестра нарушен (append-only): "
                + ", ".join(f"{prefix}-{b:03d} стоит после {prefix}-{a:03d}"
                            for a, b in bad[:3]) + " ✗"] + warns, False
    return [f"{name}: порядок реестра append-only соблюдён "
            f"({len(nums)} записей) ✓"] + warns, True


def check_oq_order(oq_path: Path) -> Tuple[List[str], bool]:
    """Реестр open-questions — append-only (трёхкратный инцидент,
    третий — src-locks 2026-08-15: закрытая запись переехала в конец)."""
    return _check_register_order(oq_path, _OQ_NUM_RE, "OQ",
                                 "open-questions")


def check_feedback_order(fb_path: Path) -> Tuple[List[str], bool]:
    """Реестр замечаний команды feedback.md (цикл обратной связи,
    модель принята 2026-08-17) — та же дисциплина, что у OQ: записи
    FB-NN append-only, статусы правятся на месте."""
    return _check_register_order(fb_path, _FB_NUM_RE, "FB", "feedback")


# Журнал координации (трек с координатором): запись — строка «- YYYY-MM-DD |
# тема | …» плюс её продолжения с отступом. Лимит длины записи — решение
# владельца 2026-10-09: четвёртая сессия координатора КК, журнал 340
# записей / 700 КБ (средняя 2 060 знаков, максимум 10 535) — «новая сессия
# поднимется с журнала» невыполнимо на любом окне контекста. Доказательства
# (выводы прибора, команд, диффы) живут в sandbox/ и файлах сдачи, запись на
# них ссылается. Сигнал — ⚠ (вердикт не трогает): журнал ведёт агент по
# отмашке, брак здесь не остановил бы ничего, а длинные записи до решения
# были нормой.
COORD_LOG_ENTRY_LIMIT = 600
_COORD_ENTRY_RE = re.compile(r"^- \d{4}-\d{2}-\d{2} \|")


def check_coordination_log(log_path: Path,
                           limit: int = COORD_LOG_ENTRY_LIMIT
                           ) -> Tuple[List[str], bool]:
    """Длина записей coordination-log.md: запись длиннее limit знаков —
    ⚠ с датой и темой; итог — число записей и сколько сверх лимита.
    Файла нет (трек без координатора) — пусто."""
    if not log_path.is_file():
        return [], True
    text = _fs.read_text(log_path, encoding="utf-8", errors="replace")
    warns = _fence_warnings(text, "coordination-log")
    text = blank_code(text, repl="", inline=False)
    entries: List[Tuple[str, int]] = []
    cur: Optional[str] = None
    size = 0
    for ln in text.splitlines():
        if _COORD_ENTRY_RE.match(ln):
            if cur is not None:
                entries.append((cur, size))
            cur, size = ln, len(ln)
        elif cur is not None and (ln.startswith(" ") or ln.startswith("\t")):
            size += len(ln.strip()) + 1
        elif cur is not None and ln.strip():
            # непустая строка без отступа — запись кончилась
            entries.append((cur, size))
            cur, size = None, 0
    if cur is not None:
        entries.append((cur, size))
    if not entries:
        return warns, True
    long = [(head, n) for head, n in entries if n > limit]
    out = [f"coordination-log: записей {len(entries)}, сверх лимита "
           f"{limit} знаков — {len(long)}" + (" ✓" if not long else "")]
    for head, n in long[-5:]:
        parts = [x.strip() for x in split_cells(head)]
        who = " | ".join(parts[:2]).lstrip("- ")[:60]
        out.append(f"предупреждение: запись журнала «{who}» — {n} знаков "
                   f"(лимит {limit}): факты и решение — в запись, "
                   "доказательства — ссылкой на отчёт в sandbox/ или файл "
                   "сдачи")
    if len(long) > 5:
        out.append(f"предупреждение: … и ещё {len(long) - 5} записей сверх "
                   "лимита (показаны последние пять)")
    return out + warns, True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Сторож долгов ссылок: просрочка (цель существует, "
                    "ссылки нет) и исполнимость (имя находится дословно); "
                    "плюс порядок реестра open-questions (append-only).")
    ap.add_argument("--matrix", type=Path, required=True)
    ap.add_argument("--docs", type=Path, required=True,
                    help="корень docs/ комплекта")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    report, ok = check(args.matrix, args.docs)
    oq = args.docs / "open-questions.md"
    if not oq.is_file():
        oq = args.docs.parent / "open-questions.md"
    oq_report, oq_ok = check_oq_order(oq)
    report.extend(oq_report)
    ok = ok and oq_ok
    # feedback.md живёт в корне репозитория (уровень сервиса, вне docs/)
    fb_report, fb_ok = check_feedback_order(
        args.docs.parent / "feedback.md")
    report.extend(fb_report)
    ok = ok and fb_ok
    cp_report, cp_ok = check_config_params(args.docs)
    report.extend(cp_report)
    ok = ok and cp_ok
    for ln in report:
        print(f"# {ln}")
    return 0 if ok or not args.strict else 2


if __name__ == "__main__":
    sys.exit(main())
