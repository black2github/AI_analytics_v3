# app/scripts/CI/kitcheck/checks/card_common.py
"""Проверки карточки: помощники, общие для нескольких тем.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import html
import re
from typing import List, Sequence
from ..html import parse_md_tables

# Строка макетов ЭФ в паспорте («Макеты ЭФ | <вложенная таблица Figma>»):
# шаблон screen-form запрещает Figma/Confluence-URL в чистовике, макеты
# живут в src — строка сверке не подлежит (иначе гейт заставлял включать
# сырой HTML с живыми URL в карточку; src-locks, 2026-08-14).
_LAYOUT_ROW_RE = re.compile(r"figma\.com|размерность экрана", re.IGNORECASE)

# FB-03 сервиса «Обновление сведений» (2026-11-18): строка макетов ЭФ узнаётся и по ярлыку —
# ссылки макетов бывают не только Figma (Zeplin: app.zeplin.io, zpl.io), ячейка бывает пустой
# или «-». Ярлык — первая ячейка строки ЦЕЛИКОМ «Макеты» / «Макеты ЭФ» (без разметки и
# двоеточия): «Макет анкеты…», «№ на макете» — не ярлык строки макетов. Признак по хосту
# остаётся для строк с Figma под другим ярлыком. Снятое только ярлыком видно приёмке
# i-строкой (layout_label_rows).
_LAYOUT_LABEL_RE = re.compile(r"макеты(?:\s+эф)?", re.IGNORECASE)
_LAYOUT_HTML_ROW_RE = re.compile(
    r"<tr[^>]*>\s*<t[hd][^>]*>((?:(?!</?t[dr]).)*?)</t[hd]>(.*?)</tr>", re.S | re.I)


def is_layout_label(cell: str) -> bool:
    """Ячейка — ярлык строки макетов ЭФ: целиком «Макеты» / «Макеты ЭФ» (HTML и markdown)."""
    t = html.unescape(re.sub(r"<[^>]+>", " ", cell))
    t = re.sub(r"\s+", " ", re.sub(r"\*\*|__", "", t)).strip().strip(":").strip()
    return _LAYOUT_LABEL_RE.fullmatch(t) is not None


def layout_row(row: Sequence[str]) -> str:
    """Строка макетов ЭФ: «host» — ссылка Figma / «размерность экрана» в любой ячейке,
    «label» — только ярлык первой ячейки, «» — не строка макетов."""
    if any(_LAYOUT_ROW_RE.search(c) for c in row):
        return "host"
    if row and is_layout_label(row[0]):
        return "label"
    return ""


def layout_label_rows(src_text: str) -> int:
    """Число строк макетов ЭФ источника, снятых со сверки только ярлыком (pipe и HTML)."""
    n = 0
    for hdr, rows in parse_md_tables(src_text):
        n += sum(1 for r in [hdr] + rows if layout_row(r) == "label")
    for m in _LAYOUT_HTML_ROW_RE.finditer(src_text):
        if layout_row([m.group(1), m.group(2)]) == "label":
            n += 1
    return n


_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|?\s*$")


def blank_table_breaks(lines: List[str]) -> List[int]:
    """Номера (1-based) пустых строк, разрывающих pipe-таблицу: markdown
    рендерит хвост плоским текстом, содержимое при этом цело и сверка
    значений молчит (К-16: ent-002 «Привязка к реализации»; матрица
    exam-run1 — разрыв внесён LLM-исполнителем захода 4 при дописывании
    блока строк реестра с ведущей пустой строкой). Легальна пустая
    строка МЕЖДУ соседними таблицами — следующий блок начинается своей
    шапкой (строка + разделитель |---|)."""
    out: List[int] = []
    for k in range(1, len(lines) - 1):
        if lines[k].strip():
            continue
        prev = lines[k - 1].strip()
        nxt = next((lines[j].strip() for j in range(k + 1, len(lines))
                    if lines[j].strip()), "")
        if not (prev.startswith("|") and nxt.startswith("|")):
            continue
        j = next(j for j in range(k + 1, len(lines)) if lines[j].strip())
        nxt2 = lines[j + 1].strip() if j + 1 < len(lines) else ""
        if _TABLE_SEP_RE.match(nxt2):
            continue  # новая таблица с собственной шапкой — легально
        out.append(k + 1)
    return out


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()
