# app/scripts/CI/kitcheck/checks/_common.py
"""Проверки selfcheck: _common — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import re
try:
    from kitcheck import fs as _fs
    from kitcheck.md import table_cells
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import table_cells  # type: ignore


_KNOWN_TYPES = {
    "function", "screen-form", "control", "process", "data-model",
    "contract-call", "internal-contract", "lib-contract", "print-form", "notification",
    "agent", "brd",
}


def _cell_plain(cell: str) -> str:
    """Текст ячейки без markdown: ссылка → её текст, без бэктиков/жирного."""
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    return cell.strip().strip("*`").strip()


def _load_service_table(readme: Path):
    """{каталог: (слот, слот_в_id)} по таблице сервисов корневого README
    домена; None — таблицы нет. Таблица узнаётся по шапке: колонка
    каталога («Каталог» либо «service-id») и колонка слота («Слот» либо
    «Код» — «Код в ID» у «Цифрового рубля»). Значение «нет» в колонке
    слота — сервис включён в домен без перенумерации (решение владельца
    2026-10-12: термины `service-id` и «слот сервиса» разведены, таблица
    `service-id | Слот | Название | Вход`)."""
    try:
        text = _fs.read_text(readme, encoding="utf-8", errors="replace")
    except OSError:
        return None
    header: Optional[List[str]] = None
    out: Dict[str, Tuple[str, bool]] = {}
    for ln in text.splitlines():
        st = ln.strip()
        if not st.startswith("|"):
            if header is not None and out:
                break               # таблица закончилась
            header = None
            continue
        cells = table_cells(st)
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        low = [c.lower() for c in cells]
        if header is None:
            if any("слот" in h or "код" in h for h in low) and any(
                    "каталог" in h or "service-id" in h for h in low):
                header = low
            continue
        idir = next((i for i, h in enumerate(header) if "каталог" in h), None)
        if idir is None:
            idir = next(i for i, h in enumerate(header) if "service-id" in h)
        islot = next((i for i, h in enumerate(header) if "слот" in h), None)
        if islot is None:
            islot = next(i for i, h in enumerate(header) if "код" in h)
        if len(cells) <= max(islot, idir):
            continue
        slot = _cell_plain(cells[islot])
        folder = _cell_plain(cells[idir]).strip("/")
        if folder.endswith("/README.md"):
            folder = folder[:-len("/README.md")]
        folder = folder.strip("/").split("/")[0]
        if not folder:
            continue
        if slot.lower() in ("нет", "no", "-", "—", ""):
            out[folder] = ("", False)
        elif _PART_CODE_RE.fullmatch(slot):
            out[folder] = (slot, True)
    return out or None


def domain_context(docs: Path):
    """(корень домена, таблица сервисов, запись этого комплекта) либо None:
    родитель комплекта несёт README с таблицей сервисов, в которой есть
    каталог комплекта."""
    d = docs.resolve()
    parent = d.parent
    if parent == d:
        return None
    table = _load_service_table(parent / "README.md")
    if not table or d.name not in table:
        return None
    return parent, table, table[d.name]


_PART_CODE_RE = re.compile(r"^[A-Z]{2,4}$")
