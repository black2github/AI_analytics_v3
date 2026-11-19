# app/scripts/CI/kitcheck/checks/matrix.py
"""Проверки selfcheck: matrix — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
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
    from kitcheck.md import table_cells, _kit_md, read_frontmatter
    from kitcheck.checks._common import in_outside_eco_part, passport_slugs
    from kitcheck.checks.catalog_api import api_section
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import table_cells, _kit_md, read_frontmatter  # type: ignore
    from ._common import in_outside_eco_part, passport_slugs  # type: ignore
    from .catalog_api import api_section  # type: ignore


_REGISTRY_HDR_RE = re.compile(r"^#+\s*(?:\d+\.\s*)?Реестр\s+ID",
                              re.I | re.M)


def _kit_doc_ids(root: Path) -> set:
    """id из шапок документов комплекта (для ID иной формы в первой ячейке реестра)."""
    out = set()
    for p in _kit_md(root):
        i = str((read_frontmatter(p) or {}).get("id", "") or "").strip().strip("'\"")
        if i:
            out.add(i)
    return out


def check_registry_duplicates(matrix_path: Path,
                              doc_ids: Optional[set] = None) -> Tuple[List[str], bool]:
    """Дубли ID в секции «Реестр ID» матрицы — ✗ (реестровый ID
    уникален; кейс: два CTL-000 у общего и подсервисного README). ID иной
    формы (страницы НФТ: `nfr`, `nfr-avl`) — когда ячейка целиком и точно
    равна id из шапки документа комплекта (решение владельца канона
    19.11.2026; правило matrix_sync._first_id)."""
    try:
        text = _fs.read_text(matrix_path, encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    m = _REGISTRY_HDR_RE.search(text)
    if not m:
        return [], True
    lazy_ids = doc_ids
    sect = text[m.end():]
    nxt = re.search(r"^#+\s", sect, re.M)
    if nxt:
        sect = sect[:nxt.start()]
    seen: Dict[str, str] = {}
    report: List[str] = []
    ok = True
    for ln in sect.splitlines():
        cells = table_cells(ln)
        if len(cells) < 2:
            continue
        rid = cells[0]
        if not re.match(r"^[A-ZА-Я]{2,}[-\w]*\d$", rid):
            bare = re.sub(r"\]\([^)]*\)", "]", rid).strip().strip("[]`* ")
            # заглавная форма — прежнее правило (шапка «ID», нестандартные ID); иная форма —
            # только точное совпадение с id документа
            if not bare or bare[:1].isupper() or set(bare) <= set("-:"):
                continue
            if lazy_ids is None:
                lazy_ids = _kit_doc_ids(matrix_path.parent)
            if bare not in lazy_ids:
                continue
            rid = bare
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


# --- раздел «Покрытие: API ↔ SRS»: пустота и полнота (гейт переноса, П4–П5) ---
#
# Постановка 2026-11-19 (сессия «AI Factory»), решения владельца 19.11: раздел пуст при
# карточках собственных методов — отказ гейта, если причина не записана в шапке раздела (текст
# между заголовком и таблицей); каждая карточка `type: internal-contract` в контуре Экосистемы
# названа своим ID в разделе — строкой-операцией либо в колонке «Артефакты SRS»
# (conventions §5.3 п. 7: до перехода на API First строка раздела — карточка INTC). Карточки части
# вне контура Экосистемы (паспорт границы `srs/<слаг>/boundary-passport.md`, канал js-api) и
# README-реестры методов (файл README.md) не считаются — правило шаблона матрицы. Признаки — тип
# шапки, файл паспорта границы, имя файла, ID в ячейке; слов источника нет. Слой — ядро
# (работает без выгрузки). В selfcheck — ⚠ (вердикт не меняется), гейт полного режима — ✗.

_SEP_ROW_RE = re.compile(r"^\|[\s:|-]+\|?$")


def _api_rows(section: str) -> List[str]:
    """Строки данных таблиц раздела: без шапки каждой таблицы и разделителя."""
    rows: List[str] = []
    in_table = False
    for ln in section.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        if not in_table:
            in_table = True  # первая строка таблицы — шапка
            continue
        if _SEP_ROW_RE.match(s):
            continue
        rows.append(s)
    return rows


def api_coverage(docs: Path) -> Optional[dict]:
    """Раздел «Покрытие: API ↔ SRS» против карточек методов. None — матрицы нет.
    {section: раздел есть, ops: строк-операций, reason: шапка раздела (причина пустоты),
    intc: ID карточек методов в контуре Экосистемы, outside: число карточек части вне контура,
    unnamed: ID карточек, не названных в разделе}."""
    matrix = docs / "traceability-matrix.md"
    if not matrix.is_file():
        return None
    text = _fs.read_text(matrix, encoding="utf-8", errors="replace")
    sect = api_section(text)
    slugs = passport_slugs(docs)
    intc: List[str] = []
    outside = 0
    for p in _kit_md(docs):
        if p.name.lower() == "readme.md":
            continue
        fm = read_frontmatter(p) or {}
        if str(fm.get("type", "")).strip().strip("'\"") != "internal-contract":
            continue
        cid = str(fm.get("id", "")).strip().strip("'\"")
        if not cid:
            continue
        if in_outside_eco_part(p, docs, slugs):
            outside += 1
        else:
            intc.append(cid)
    out = {"section": sect is not None, "ops": 0, "reason": "", "intc": sorted(intc),
           "outside": outside, "unnamed": []}
    if sect is None:
        return out
    header, section = sect
    # шапка: первая строка — хвост строки заголовка, не текст раздела
    out["reason"] = " ".join(header.split("\n", 1)[1].split()) if "\n" in header else ""
    rows = _api_rows(section)
    out["ops"] = len(rows)
    if rows:
        try:
            import matrix_sync as _ms  # noqa: E402 — диапазоны ID «INTC-001…INTC-005»
        except ImportError:  # импорт пакетом app.scripts.CI (тесты)
            from ... import matrix_sync as _ms  # type: ignore
        named = _ms.cell_ids("\n".join(rows))
        out["unnamed"] = [i for i in out["intc"] if i not in named]
    return out


def api_coverage_lines(cov: Optional[dict]) -> List[Tuple[str, str]]:
    """(знак гейта полного режима, текст) по разделу API; раздела нет — пусто (строку об
    отсутствии раздела печатает гейт)."""
    if not cov or not cov["section"]:
        return []
    n, outside = len(cov["intc"]), cov["outside"]
    tail = (f"; карточек части вне контура Экосистемы {outside} — в раздел не вносятся"
            if outside else "")
    if cov["ops"] == 0:
        if not n:
            return [("✓", "раздел пуст — собственных методов нет" + tail)]
        if cov["reason"]:
            q = cov["reason"]
            return [("✓", f"раздел пуст, причина записана в шапке раздела: «{q[:160]}"
                          f"{'…' if len(q) > 160 else ''}»" + tail)]
        return [("✗", f"раздел пуст, а в комплекте карточек собственных методов "
                      f"(internal-contract) {n}: {', '.join(cov['intc'][:8])}"
                      f"{'…' if n > 8 else ''} — внесите операции (до перехода на API First "
                      "строка раздела — карточка INTC) либо запишите причину пустоты в шапке "
                      "раздела, между заголовком и таблицей" + tail)]
    if cov["unnamed"]:
        u = cov["unnamed"]
        return [("✗", f"операций {cov['ops']}; карточки собственных методов не названы в "
                      f"разделе: {len(u)} из {n} ({', '.join(u[:8])}{'…' if len(u) > 8 else ''})"
                      " — каждая карточка internal-contract в контуре Экосистемы названа своим "
                      "ID строкой-операцией либо в колонке «Артефакты SRS» (conventions §5.3 "
                      "п. 7)" + tail)]
    return [("✓", f"раздел есть, операций {cov['ops']}"
                  + (f"; все карточки собственных методов названы ({n})" if n else "") + tail)]
