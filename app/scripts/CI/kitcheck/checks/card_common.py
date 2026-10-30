# app/scripts/CI/kitcheck/checks/card_common.py
"""Проверки карточки: помощники, общие для нескольких тем.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import re
from typing import List

# Строка макетов ЭФ в паспорте («Макеты ЭФ | <вложенная таблица Figma>»):
# шаблон screen-form запрещает Figma/Confluence-URL в чистовике, макеты
# живут в src — строка сверке не подлежит (иначе гейт заставлял включать
# сырой HTML с живыми URL в карточку; src-locks, 2026-08-14).
_LAYOUT_ROW_RE = re.compile(r"figma\.com|размерность экрана", re.IGNORECASE)


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
