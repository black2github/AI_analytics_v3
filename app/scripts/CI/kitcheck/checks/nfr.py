# app/scripts/CI/kitcheck/checks/nfr.py
"""Проверки selfcheck: nfr — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
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
    from kitcheck.md import frontmatter_split
    from kitcheck.md import read_frontmatter
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import frontmatter_split  # type: ignore
    from ..md import read_frontmatter  # type: ignore


# написание как в таблице шаблона nfr.md (без «ё»)
_NFR_TYPE_BY_CODE = {
    "prf": "Производительность",
    "avl": "Доступность",
    "rel": "Надежность",
    "sca": "Масштабируемость",
    "log": "Протоколирование",
    "sec": "Безопасность",
    "cmp": "Совместимость",
    "ins": "Удобство установки",
    "itg": "Целостность",
    "rsl": "Устойчивость",
    "prt": "Защита",
    "use": "Удобство использования",
    "eff": "Эффективность",
    "mod": "Возможность модификации",
    "tst": "Проверяемость и тестируемость",
    "mig": "Миграция",
    "mnt": "Требования к сопровождению",
    "mon": "Мониторинг",
}


_NFR_CODES = frozenset(_NFR_TYPE_BY_CODE)


_NFR_ROW_RE = re.compile(r"(?m)^\|\s*(nfr-([a-z]{3})-(\d{3}))\s*\|")


_NFR_INGRESS = frozenset({"reverse", "forward", "mixed"})


def _nfr_repo_root(docs: Path) -> Path:
    """output/<service>/docs → корень репозитория. Иначе родитель docs."""
    if (docs.name == "docs" and docs.parent.parent.name == "output"):
        return docs.parent.parent.parent
    return docs.parent


def check_nfr_catalog(docs: Path) -> Tuple[List[str], bool]:
    """Сторож output/<service>/nfr рядом с docs/.

    Каталога нет — молчит: утилита не знает, был ли вход. Значение nfr
    в _KNOWN_TYPES пути srs/<тип>/ не добавляется.
    """
    report: List[str] = []
    ok = True
    features = docs / "brd" / "features"
    if features.is_dir():
        for p in sorted(features.rglob("*.md")):
            try:
                text = _fs.read_text(p, encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"(?m)^## Нефункциональные требования\s*$", text):
                ok = False
                report.append(
                    f"✗ {p.relative_to(docs)}: раздел «Нефункциональные "
                    "требования» внутри фичи; страницы НФТ — в ../nfr/")
    nfr_dir = docs.parent / "nfr"
    if not nfr_dir.is_dir():
        return report, ok
    for d in sorted(p for p in nfr_dir.rglob("*") if p.is_dir()):
        ok = False
        report.append(
            f"✗ {d.relative_to(docs.parent)}: вложенный каталог в nfr/")
    seen_codes: Dict[str, Path] = {}
    page_rows: set = set()
    repo = _nfr_repo_root(docs)
    for p in sorted(nfr_dir.glob("*.md")):
        rel = p.relative_to(docs.parent)
        fm = read_frontmatter(p)
        if not fm:
            ok = False
            report.append(f"✗ {rel}: frontmatter не распознан")
            continue
        if fm.get("type", "").strip("'\"") != "nfr":
            ok = False
            report.append(f"✗ {rel}: ожидался type: nfr")
        if "status" in fm:
            ok = False
            report.append(f"✗ {rel}: поле status запрещено")
        if "nfr_profile" in fm:
            ok = False
            report.append(f"✗ {rel}: поле nfr_profile запрещено")
        if p.name == "README.md":
            if fm.get("id", "").strip("'\"") != "nfr":
                ok = False
                report.append(f"✗ {rel}: у реестра id: nfr")
            if "ingress" in fm or "nfr_type" in fm:
                ok = False
                report.append(
                    f"✗ {rel}: у реестра нет ingress и nfr_type")
            continue
        m = re.fullmatch(r"nfr-([a-z]{3})\.md", p.name)
        if not m or m.group(1) not in _NFR_CODES:
            ok = False
            report.append(
                f"✗ {rel}: имя файла не из каталога nfr-<код>.md")
            continue
        code = m.group(1)
        if code in seen_codes:
            ok = False
            report.append(f"✗ {rel}: вторая страница кода {code}")
        seen_codes[code] = p
        expected_id = f"nfr-{code}"
        page_id = fm.get("id", "").strip("'\"")
        if page_id != expected_id:
            ok = False
            report.append(f"✗ {rel}: id должен быть {expected_id}")
        expected_type = _NFR_TYPE_BY_CODE[code]
        nfr_type = fm.get("nfr_type", "").strip("'\"")
        if nfr_type != expected_type:
            ok = False
            report.append(
                f"✗ {rel}: nfr_type должен быть «{expected_type}»")
        ingress = fm.get("ingress", "").strip("'\"")
        if ingress not in _NFR_INGRESS:
            ok = False
            report.append(
                f"✗ {rel}: ingress обязателен: reverse, forward или mixed")
        has_conf = bool(fm.get("confluence_page_ids", "").strip())
        has_src = bool(fm.get("source_artifacts", "").strip())
        if ingress == "reverse" and (not has_conf or has_src):
            ok = False
            report.append(
                f"✗ {rel}: reverse требует confluence_page_ids "
                "и запрещает source_artifacts")
        if ingress == "forward" and (has_conf or has_src):
            ok = False
            report.append(
                f"✗ {rel}: forward запрещает confluence_page_ids "
                "и source_artifacts")
        if ingress == "mixed" and (not has_conf or has_src):
            ok = False
            report.append(
                f"✗ {rel}: mixed требует confluence_page_ids "
                "и запрещает source_artifacts")
        if has_src:
            # путь в кавычках не режется по пробелам (имя файла БТ)
            for a, b, c in re.findall(
                    r"'([^']*)'|\"([^\"]*)\"|(\S+)",
                    fm.get("source_artifacts", "")):
                tok = (a or b or c).strip().strip("'\"")
                if not tok or tok.startswith("<"):
                    continue
                path = Path(tok)
                resolved = path if path.is_absolute() else (repo / tok)
                if not resolved.is_file():
                    ok = False
                    report.append(
                        f"✗ {rel}: source_artifacts не файл: {tok}")
        try:
            text = _fs.read_text(p, encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        seen_rows = set()
        for token, row_code, _num in _NFR_ROW_RE.findall(text):
            if row_code != code:
                ok = False
                report.append(f"✗ {rel}: строка {token} не типа {code}")
            if token in seen_rows:
                ok = False
                report.append(f"✗ {rel}: повтор номера {token}")
            seen_rows.add(token)
        page_rows.update(seen_rows)
        # тело — по общей границе шапки: с BOM шапка прежде оставалась в
        # теле, и её `status:` давал ложный ✗
        body = frontmatter_split(text)[1]
        if re.search(
                r"OQ-|TODO|sources/|pageId|confluence|_meta/|REJ-|nfr_profile"
                r"|\]\([^)]*srs/|^status:",
                body, re.M):
            ok = False
            report.append(
                f"✗ {rel}: запрещённые слова вне frontmatter")
    matrix = docs / "traceability-matrix.md"
    if seen_codes:
        if not matrix.is_file():
            ok = False
            report.append(
                "✗ traceability-matrix.md: нет матрицы при каталоге НФТ")
            brd_rows: set = set()
        else:
            mtext = _fs.read_text(matrix, encoding="utf-8", errors="replace")
            sec = re.search(
                r"^## BRD-6\.2\..*?(?=^## |\Z)", mtext, re.S | re.M)
            brd_rows = set(re.findall(
                r"\|\s*(nfr-[a-z]{3}-\d{3})\s*\|",
                sec.group(0) if sec else ""))
        for missing in sorted(page_rows - brd_rows):
            ok = False
            report.append(f"✗ BRD-6.2: нет строки {missing}")
        for extra in sorted(brd_rows - page_rows):
            ok = False
            report.append(f"✗ BRD-6.2: строка {extra} без страницы типа")
    if ok:
        report.append(f"✓ {nfr_dir.relative_to(docs.parent)}: каталог НФТ")
    return report, ok
