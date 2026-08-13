# app/scripts/CI/source_coverage.py
#
# Гейт покрытия выгрузки: каждая страница Confluence-выгрузки (sources)
# обязана быть источником хотя бы одного артефакта комплекта (output) —
# сверка по confluence_page_id (источник, скаляр) ↔ confluence_page_ids
# (артефакты, список во frontmatter).
#
# Дополнительно — целостность иерархии выгрузки: дочерние страницы лежат
# в каталоге fileN/ рядом с родительской fileN.md (инвариант экспортёра
# confluence-tree-exporter; расхождение имён = дефект выгрузки, обычно
# ручная правка человеком — репортится отдельно). Иерархия используется
# для диагностики непокрытых страниц: «дочерняя единица покрытого
# родителя» — кандидат на потерю смысла (родитель перенесён, его
# неразрывная часть — нет).
#
# МИГРАЦИОННЫЙ гейт reverse-режима: актуален на время переезда из
# Confluence, пока комплект строится из выгрузки. В дальнейшей жизни
# комплекта (delta/forward) не применяется: после реструктуризации
# информация расходится по разделам и входит составными частями в другие
# артефакты — покрытие «страница ↔ артефакт» перестаёт быть инвариантом.
#
# Мягкий гейт: код 0 и отчёт; --strict — код 2 при непокрытых страницах.

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

_FM_BOUND = re.compile(r"^---\s*$")
_PAGE_ID_RE = re.compile(r"^confluence_page_id:\s*['\"]?(\d+)['\"]?\s*$")
_PAGE_IDS_RE = re.compile(r"^confluence_page_ids:\s*\[(.*)\]\s*$")
_ID_TOKEN_RE = re.compile(r"\d+")


def read_frontmatter_lines(path: Path, limit: int = 60) -> List[str]:
    """Строки frontmatter (между первыми двумя ---); [] если его нет."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # BOM: PowerShell-редиректы пишут UTF-8-sig — иначе '---' не распознать
    lines = text.lstrip("﻿").splitlines()
    if not lines or not _FM_BOUND.match(lines[0]):
        return []
    out: List[str] = []
    for ln in lines[1:limit]:
        if _FM_BOUND.match(ln):
            return out
        out.append(ln)
    return []


def source_page_id(path: Path) -> Optional[str]:
    for ln in read_frontmatter_lines(path):
        m = _PAGE_ID_RE.match(ln.strip())
        if m:
            return m.group(1)
    return None


def artifact_page_ids(path: Path) -> List[str]:
    for ln in read_frontmatter_lines(path):
        m = _PAGE_IDS_RE.match(ln.strip())
        if m:
            return _ID_TOKEN_RE.findall(m.group(1))
    return []


def collect(sources: Path, output: Path):
    pages: Dict[str, Path] = {}          # page_id -> файл источника
    no_id: List[Path] = []               # страницы без page_id (дефект)
    parents: Dict[str, Optional[str]] = {}  # page_id -> page_id родителя
    orphan_dirs: List[Path] = []         # каталоги без парного fileN.md

    for p in sorted(sources.rglob("*.md")):
        if p.name.lower() == "index.md":
            continue
        pid = source_page_id(p)
        if pid is None:
            no_id.append(p)
            continue
        pages[pid] = p
        parent_md = p.parent.with_suffix(".md")  # инвариант fileN/ <- fileN.md
        parents[pid] = (source_page_id(parent_md)
                        if p.parent != sources and parent_md.is_file() else None)

    for d in sorted(sources.rglob("*")):
        if d.is_dir() and d != sources and not d.with_suffix(".md").is_file():
            if any(f.suffix == ".md" and f.name.lower() != "index.md"
                   for f in d.rglob("*")):
                orphan_dirs.append(d)

    covered: Dict[str, List[Path]] = {}
    for p in sorted(output.rglob("*.md")):
        for pid in artifact_page_ids(p):
            covered.setdefault(pid, []).append(p)
    return pages, parents, covered, no_id, orphan_dirs


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Покрытие страниц выгрузки артефактами комплекта "
                    "(по confluence_page_id/confluence_page_ids).")
    ap.add_argument("--sources", type=Path, required=True,
                    help="корень выгрузки (sources/confluence/<срез>)")
    ap.add_argument("--output", type=Path, required=True,
                    help="корень комплекта (output/<service>)")
    ap.add_argument("--strict", action="store_true",
                    help="код 2, если есть непокрытые страницы")
    args = ap.parse_args()

    pages, parents, covered, no_id, orphan_dirs = collect(
        args.sources, args.output)
    uncovered = {pid: p for pid, p in pages.items() if pid not in covered}

    print(f"# страниц с page_id: {len(pages)}; "
          f"покрыто артефактами: {len(pages) - len(uncovered)}; "
          f"НЕ покрыто: {len(uncovered)}")
    for pid, p in sorted(uncovered.items(), key=lambda kv: str(kv[1])):
        par = parents.get(pid)
        mark = (" ⚠ дочерняя единица ПОКРЫТОГО родителя"
                if par and par in covered else "")
        print(f"  - [{pid}] {p.relative_to(args.sources)}{mark}")
    if no_id:
        print(f"# страниц БЕЗ confluence_page_id (дефект выгрузки): {len(no_id)}")
        for p in no_id[:10]:
            print(f"  - {p.relative_to(args.sources)}")
    if orphan_dirs:
        print(f"# каталогов без парной страницы fileN.md "
              f"(нарушение инварианта имён выгрузки): {len(orphan_dirs)}")
        for d in orphan_dirs:
            print(f"  - {d.relative_to(args.sources)}/")
    if not uncovered and not no_id and not orphan_dirs:
        print("# OK: выгрузка покрыта полностью, целостность иерархии не нарушена.")
    return 2 if (args.strict and uncovered) else 0


if __name__ == "__main__":
    sys.exit(main())
