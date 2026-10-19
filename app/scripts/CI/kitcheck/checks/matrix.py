# app/scripts/CI/kitcheck/checks/matrix.py
"""Проверки selfcheck: matrix — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
import re
try:
    from kitcheck import fs as _fs
    from kitcheck.md import table_cells
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import table_cells  # type: ignore


_REGISTRY_HDR_RE = re.compile(r"^#+\s*(?:\d+\.\s*)?Реестр\s+ID",
                              re.I | re.M)


def check_registry_duplicates(matrix_path: Path) -> Tuple[List[str], bool]:
    """Дубли ID в секции «Реестр ID» матрицы — ✗ (реестровый ID
    уникален; кейс: два CTL-000 у общего и подсервисного README)."""
    try:
        text = _fs.read_text(matrix_path, encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    m = _REGISTRY_HDR_RE.search(text)
    if not m:
        return [], True
    sect = text[m.end():]
    nxt = re.search(r"^#+\s", sect, re.M)
    if nxt:
        sect = sect[:nxt.start()]
    seen: Dict[str, str] = {}
    report: List[str] = []
    ok = True
    for ln in sect.splitlines():
        cells = table_cells(ln)
        if len(cells) < 2 or not re.match(r"^[A-ZА-Я]{2,}[-\w]*\d$",
                                          cells[0]):
            continue
        rid = cells[0]
        if rid in seen:
            ok = False
            report.append(f"✗ реестр ID: дубль {rid} в «Реестре ID» "
                          f"матрицы — реестровый ID уникален "
                          f"(строки: «{seen[rid][:60]}» и "
                          f"«{ln.strip()[:60]}»)")
        else:
            seen[rid] = ln.strip()
    return report, ok


def _registry_name_norm(name: str) -> str:
    """Название для сравнения: без кавычек по краям, пробелы схлопнуты, регистр
    и ё/е не различаются (как _norm_title сторожа названий по шапкам)."""
    return re.sub(r"\s+", " ", name.strip().strip("'\"`")).lower().replace("ё", "е")


def check_registry_name_duplicates(matrix_path: Path,
                                   skip: List[set]) -> List[str]:
    """Волна 9 ОНБ-В (ЗК-25): одинаковые названия разных ID одного типа по «Реестру
    ID» матрицы — суб-ID внутри файлов групп (CTL-015 и CTL-034 без title шапки)
    сторож названий по шапкам не видит. Тип — первый сегмент ID (CTL, SCR, FUN…).
    Не дубль: части одной группы с общим базовым ID (SCR-CL-01.1…), README-реестры
    (`*-000`), снятые строки («снят …»). Группа, чьи ID уже названы сторожем по
    шапкам (`skip`), не повторяется. Строки отчёта без значка — заголовок ставит
    selfcheck; только ⚠."""
    try:
        text = _fs.read_text(matrix_path, encoding="utf-8", errors="replace")
    except OSError:
        return []
    m = _REGISTRY_HDR_RE.search(text)
    if not m:
        return []
    sect = text[m.end():]
    nxt = re.search(r"^#+\s", sect, re.M)
    if nxt:
        sect = sect[:nxt.start()]
    name_col = 1
    groups: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for ln in sect.splitlines():
        cells = table_cells(ln)
        if len(cells) < 2:
            continue
        if not re.match(r"^[A-ZА-Я]{2,}[-\w.]*\d$", cells[0]):
            low = [c.lower() for c in cells]
            for want in ("название", "наименование"):
                if want in low:
                    name_col = low.index(want)
            continue
        rid = cells[0]
        name = cells[name_col] if name_col < len(cells) else ""
        if (not name or name == "—" or re.match(r"(?i)снят\b", name)
                or re.search(r"-0{3}$", rid)):
            continue
        groups.setdefault((rid.split("-")[0], _registry_name_norm(name)), []).append((rid, name))
    out: List[str] = []
    for (_typ, _n), items in sorted(groups.items()):
        bases = {re.sub(r"(?:\.\d+)+$", "", rid) for rid, _nm in items}
        if len(bases) < 2:
            continue
        ids = {rid for rid, _nm in items}
        if any(ids <= s for s in skip):
            continue
        out.append(f"{', '.join(sorted(ids))} — «{items[0][1].strip()}»")
    return out
