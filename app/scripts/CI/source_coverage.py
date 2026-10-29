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
#
# Классы непокрытия (FB-28 КК, 2026-10-20): непокрытая страница получает
# класс по своей строке описи inventory.md комплекта (дом классификации —
# шаг 2 плана миграции): заморожено, контейнер, справочный вход, снято с
# миграции, бинарное, вне плана, не в описи — структурное непокрытие по
# решению плана; иначе —
# пробел миграции. С описью --strict бракует только пробелы и страницы вне
# описи (опись отстала от выгрузки); без описи — прежнее поведение.
#
# Страницы НФТ лежат в output/<service>/nfr/, рядом с docs/, не внутри
# него. Обход корня комплекта (output/<service>) их уже видит. Если
# передан корень docs/, дополнительно читается соседний каталог nfr/.
# То же для мини-комплектов зоны «вне Экосистемы» modules/<имя>/ (Д-46).

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
try:
    from kitcheck import fs as _fs  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck import fs as _fs  # type: ignore  # noqa: E402

_FM_BOUND = re.compile(r"^---\s*$")
_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$")
_PAGE_ID_RE = re.compile(r"^confluence_page_id:\s*['\"]?(\d+)['\"]?\s*$")
_PAGE_IDS_RE = re.compile(r"^confluence_page_ids:\s*\[(.*)\]\s*$")
_ID_TOKEN_RE = re.compile(r"\d+")


def read_frontmatter_lines(path: Path, limit: int = 60) -> List[str]:
    """Строки frontmatter (между первыми двумя ---); [] если его нет."""
    try:
        text = _fs.read_text(path, encoding="utf-8", errors="replace")
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


def source_title(path: Path) -> Optional[str]:
    """title страницы из frontmatter — человеческое наименование для отчёта
    (имена файлов выгрузки обрезаются/латинизируются, title — нет).
    YAML-перенос длинного значения склеивается пробелом (экспортёр пишет
    продолжение со сдвигом — однострочное чтение обрезало хвост)."""
    lines = read_frontmatter_lines(path)
    for i, ln in enumerate(lines):
        m = _TITLE_RE.match(ln.strip())
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
    roots = [output]
    if output.name == "docs":
        for sib in ("nfr", "modules"):
            sibling = output.parent / sib
            if sibling.is_dir():
                roots.append(sibling)
    for root in roots:
        for p in sorted(root.rglob("*.md")):
            for pid in artifact_page_ids(p):
                covered.setdefault(pid, []).append(p)
    return pages, parents, covered, no_id, orphan_dirs


def empty_dirs(sources: Path) -> List[Path]:
    """Каталоги без парной fileN.md и без дочерних страниц .md — дефект выгрузки.
    Каталоги вложений экспортёра img/ (и всё под ними) — не страницы, не в счёт."""
    out: List[Path] = []
    for d in sorted(sources.rglob("*")):
        if (not d.is_dir() or d == sources or d.with_suffix(".md").is_file()
                or "img" in d.relative_to(sources).parts):
            continue
        if not any(f.suffix == ".md" and f.name.lower() != "index.md"
                   for f in d.rglob("*")):
            out.append(d)
    return out


# --- классы непокрытия по описи (FB-28 КК) ---
#
# Закрытый перечень классов и словарь признаков — здесь и только здесь.
# Признаки читаются из колонок описи «целевой тип (гипотеза)», «основание»,
# «req_type», «родитель»; бинарное — по файлу выгрузки; вне плана — по
# migration-plan.md. Первое совпадение сверху; не совпало ничего — пробел.
# Асимметрия ошибок: структурный класс снимает страницу из брака --strict,
# поэтому признаки узкие, а сомнительное остаётся пробелом.
GAP, NOT_IN_INV = "пробелы миграции", "не в описи"
FROZEN, CONTAINER, REFERENCE = "заморожено", "контейнеры", "справочные"
WITHDRAWN = "снято с миграции"
OUT_OF_PLAN, BINARY = "вне плана", "бинарные"
# порядок перечней отчёта: пробелы первыми, затем отставание описи, затем
# структурные классы
CLASS_ORDER = (GAP, NOT_IN_INV, FROZEN, CONTAINER, REFERENCE, WITHDRAWN, OUT_OF_PLAN, BINARY)
# отрицание признака («НЕ frozen, GBO-… снят», «не TOC») признаком не считается —
# иначе карточка, которую опись прямо называет живой, ушла бы из брака
_NOT = r"(?<!не )(?<!не-)"
_FROZEN_RE = re.compile(rf"(?i){_NOT}(?:frozen|заморож)")
_FROZEN_PARENT_RE = re.compile(r"(?i)^заморожено")
_CONTAINER_TARGET_RE = re.compile(r"(?i)^README-реестр$")
_CONTAINER_RE = re.compile(rf"(?i){_NOT}(?:\bTOC\b|контейнер|навигац|\bnavigation\b)")
_REFERENCE_TARGET_RE = re.compile(r"(?i)^doc-rules$")
_REFERENCE_RE = re.compile(rf"(?i){_NOT}\b(?:reference-only|baseline|instruction)\b")
# Снято с миграции (OQ-294 КК, 2026-10-30): страница помечена в выгрузке DELETE /
# [DRAFT] / «черновик», её преемник или актуальная страница покрыта карточкой. Раньше
# такие строки описи несли только reference-only и маскировались под справочный вход.
# Признак: «снято с миграции» в целевом типе или основании; метки выгрузки DELETE
# (заглавными) и [DRAFT] — в title или основании; «черновик» — только в основании:
# в title это бывает частью названия живой страницы (КК: «Черновик - ПР для выпуска
# ЦК» — справочный вход концепции сервиса). Проверяется до справочного входа, после
# заморозки и контейнеров («(черновик)» в title замороженной — заморожено).
_WITHDRAWN_RE = re.compile(rf"(?i){_NOT}(?:снят[оаы]?\s+с\s+миграции|(?<![\w-])черновик)")
_WITHDRAWN_MARK_RE = re.compile(rf"(?i){_NOT}(?:(?-i:\bDELETE\b)|\[DRAFT\])")
_PLAN_SLUG_RE = re.compile(r"(?i)\b(?:подсервис|core)\s+`?([a-z0-9][a-z0-9-]*)")
_TARGET_SLUG_RE = re.compile(r"^srs/([a-z0-9][a-z0-9-]*)(?:/|$)")
# страница-вложение: тело — только изображения / ссылки на файлы, без текста
_ATTACH_RE = re.compile(r"(?i)!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>|"
                        r"\[[^\]]*\]\([^)]*\.(?:png|jpe?g|gif|svg|bmp|pdf|docx?|xlsx?|"
                        r"pptx?|zip|vsdx?|bpmn|drawio)\)")
_INV_COLS = {"page_id": "page_id", "title": "title", "родитель": "parent",
             "req_type": "req_type", "целевой тип": "target", "основание": "basis"}
# Зона «вне Экосистемы» (Д-46): модуль сервиса в чужом контуре исполнения, дом —
# мини-комплект modules/<имя>/ рядом с docs/. Страница зоны покрыта, только если её
# page_id несёт файл под modules/; иначе — ПРОБЕЛ миграции, не структурный класс:
# «вне Экосистемы» значит «мигрировать в мини-комплект», а не «не мигрировать».
# Признак — «вне Экосистемы» или «modules/» в целевом типе или основании описи
# (форма колонки — «вне Экосистемы (modules/<имя>/)»).
_ZONE_RE = re.compile(r"(?i)вне\s+Экосистемы|modules/")


def is_zone_row(row: Dict[str, str]) -> bool:
    """Строка описи относится к зоне «вне Экосистемы» (Д-46)."""
    return bool(_ZONE_RE.search(row.get("target", "")) or _ZONE_RE.search(row.get("basis", "")))


def _under_modules(path: Path, output: Path) -> bool:
    """Файл лежит в мини-комплекте: docs/modules/<имя>/ (Д-49, норма) или modules/ рядом с
    docs/ (старое место, переходный период)."""
    rp = path.resolve()
    for base in (output.parent / "modules", output / "modules"):
        try:
            rp.relative_to(base.resolve())
            return True
        except ValueError:
            continue
    return False


def find_kit_file(output: Path, name: str) -> Optional[Path]:
    """Файл комплекта (inventory.md, migration-plan.md): в корне --output или
    в его родителе (для docs/ — рядом с docs/)."""
    for d in (output, output.parent):
        p = d / name
        if p.is_file():
            return p
    return None


def read_inventory(path: Path) -> Dict[str, Dict[str, str]]:
    """page_id → {parent, req_type, target, basis} по таблице описи; колонки —
    по заголовку таблицы (порядок колонок не закреплён)."""
    text = _fs.read_text(path, encoding="utf-8", errors="replace").lstrip("\ufeff")
    cols: Dict[str, int] = {}
    rows: Dict[str, Dict[str, str]] = {}
    for ln in text.splitlines():
        st = ln.strip()
        if not st.startswith("|"):
            cols = {} if not rows else cols
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", st.strip("|"))]
        if not cols:
            head = {}
            for i, c in enumerate(cells):
                for name, key in _INV_COLS.items():
                    if c.lower().startswith(name):
                        head[key] = i
            if "page_id" in head:
                cols = head
            continue
        pid = cells[cols["page_id"]] if cols["page_id"] < len(cells) else ""
        if not re.fullmatch(r"\d+", pid):
            continue  # разделитель заголовка
        rows[pid] = {k: (cells[i] if i < len(cells) else "") for k, i in cols.items()}
    return rows


def plan_slugs(plan: Path) -> Tuple[Set[str], str]:
    """(слаги подсервисов и core из migration-plan.md, текст плана); ({}, "")
    — план не читается."""
    try:
        text = _fs.read_text(plan, encoding="utf-8", errors="replace")
    except OSError:
        return set(), ""
    return {m.group(1).lower() for m in _PLAN_SLUG_RE.finditer(text)}, text


def _attachment_only(path: Path) -> bool:
    try:
        text = _fs.read_text(path, encoding="utf-8", errors="replace").lstrip("\ufeff")
    except OSError:
        return False
    lines = text.splitlines()
    if lines and _FM_BOUND.match(lines[0]):
        end = next((i for i in range(1, len(lines)) if _FM_BOUND.match(lines[i])), 0)
        lines = lines[end + 1:]
    body = "\n".join(lines)
    if not _ATTACH_RE.search(body):
        return False
    rest = re.sub(r"<[^>]+>", " ", _ATTACH_RE.sub(" ", body))
    return not re.search(r"\w", rest)


def classify(pid: str, path: Path, inv: Dict[str, Dict[str, str]],
             slugs: Set[str], plan_text: str) -> str:
    """Класс непокрытой страницы (закрытый перечень CLASS_ORDER)."""
    row = inv.get(pid)
    if row is not None:
        target, basis = row.get("target", ""), row.get("basis", "")
        if (_FROZEN_RE.search(target) or _FROZEN_RE.search(basis)
                or _FROZEN_RE.search(row.get("req_type", ""))
                or _FROZEN_PARENT_RE.search(row.get("parent", ""))):
            return FROZEN
        if (_CONTAINER_TARGET_RE.search(target) or _CONTAINER_RE.search(basis)
                or _CONTAINER_RE.search(target)):
            return CONTAINER
        if (_WITHDRAWN_RE.search(f"{target} {basis}")
                or _WITHDRAWN_MARK_RE.search(f"{row.get('title', '')} {basis}")):
            return WITHDRAWN
        if _REFERENCE_TARGET_RE.search(target) or _REFERENCE_RE.search(f"{target} {basis}"):
            return REFERENCE
    if _attachment_only(path):
        return BINARY
    if row is None:
        return NOT_IN_INV
    m = _TARGET_SLUG_RE.match(row.get("target", ""))
    if (m and slugs and m.group(1).lower() not in slugs
            and f"srs/{m.group(1)}/" not in plan_text):
        return OUT_OF_PLAN
    return GAP


def coverage_report(sources: Path, output: Path,
                    inventory: Optional[Path] = None):
    """(строки отчёта, число бракующих) — единая точка формата для CLI
    и selfcheck-диспетчера. Бракующие: с описью — пробелы миграции и
    страницы вне описи; без описи — все непокрытые (прежнее поведение)."""
    pages, parents, covered, no_id, orphan_dirs = collect(sources, output)
    inv_path = inventory if inventory is not None else find_kit_file(output, "inventory.md")
    inv = (read_inventory(inv_path)
           if inv_path is not None and inv_path.is_file() else None)
    # Д-46: страница зоны покрыта только мини-комплектом modules/<имя>/
    zone = ({pid for pid, row in inv.items() if pid in pages and is_zone_row(row)}
            if inv is not None else set())
    zone_in_modules = {pid for pid in zone
                       if any(_under_modules(a, output) for a in covered.get(pid, []))}
    uncovered = {pid: p for pid, p in pages.items()
                 if pid not in covered or (pid in zone and pid not in zone_in_modules)}
    head = (f"страниц выгрузки: {len(pages)}; "
            f"покрыто артефактами: {len(pages) - len(uncovered)}; "
            f"НЕ покрыто: {len(uncovered)}")
    lines: List[str] = []
    classes: Dict[str, str] = {}
    if inv is not None:
        plan = find_kit_file(output, "migration-plan.md") or inv_path.parent / "migration-plan.md"
        slugs, plan_text = plan_slugs(plan)
        classes = {pid: (GAP if pid in zone else classify(pid, p, inv, slugs, plan_text))
                   for pid, p in uncovered.items()}
        n = {c: sum(1 for v in classes.values() if v == c) for c in CLASS_ORDER}
        lines.append(f"{head} = пробелы миграции {n[GAP]}; структурно: заморожено "
                     f"{n[FROZEN]}, контейнеры {n[CONTAINER]}, справочные {n[REFERENCE]}, "
                     + (f"снято с миграции {n[WITHDRAWN]}, " if n[WITHDRAWN] else "")
                     + f"вне плана {n[OUT_OF_PLAN]}, бинарные {n[BINARY]}; не в описи "
                     f"{n[NOT_IN_INV]}"
                     + (f"; вне Экосистемы {len(zone)} (покрыто мини-комплектом "
                        f"{len(zone_in_modules)})" if zone else ""))
        if not slugs:
            lines.append("i вне плана: подсервисы в migration-plan.md не найдены — "
                         "класс не выдаётся")
        blocking = n[GAP] + n[NOT_IN_INV]
    else:
        lines.append(head)
        if uncovered:
            lines.append("опись не найдена — классы непокрытия не определены")
        blocking = len(uncovered)

    # К-17 (2026-08-17): блок непокрытых печатается БЕЗ page_id — в
    # формате, пригодном для прямого копирования в open-questions
    # («title — файл выгрузки»). Язык прибора диктует язык документа:
    # прежний формат «page_id — title» исполнители копировали в OQ как
    # есть, а page_id в текстах документов запрещён (носители — только
    # frontmatter и матрица). page_id страницы остаётся в её frontmatter.
    def item(pid: str, p: Path) -> str:
        par = parents.get(pid)
        mark = (" ⚠ дочерняя единица ПОКРЫТОГО родителя"
                if par and par in covered and pid not in zone else "")
        if pid in zone:
            mark += (" ⚠ зона «вне Экосистемы»: дом — мини-комплект docs/modules/<имя>/"
                     + (" (покрыта карточкой комплекта — не дом зоны)" if pid in covered else ""))
        ttl = source_title(p)
        name = ttl if ttl else p.stem
        return f"  - {name} — {p.relative_to(sources)}{mark}"

    ordered = sorted(uncovered.items(), key=lambda kv: str(kv[1]))
    if classes:
        for c in CLASS_ORDER:
            group = [(pid, p) for pid, p in ordered if classes[pid] == c]
            if group:
                lines.append(f"{c}: {len(group)}")
                lines.extend(item(pid, p) for pid, p in group)
    else:
        lines.extend(item(pid, p) for pid, p in ordered)
    if no_id:
        lines.append(f"страниц БЕЗ confluence_page_id (дефект выгрузки): "
                     f"{len(no_id)}")
        for p in no_id[:10]:
            lines.append(f"  - {p.relative_to(sources)}")
    # Каталог без парной fileN.md с дочерними страницами — узел дерева выгрузки
    # (OQ-294 КК, 2026-10-30: принято владельцем канона, выгрузку не переснимать);
    # дефект выгрузки — только каталог без страницы и без дочерних .md.
    if orphan_dirs:
        lines.append(f"каталоги-узлы без собственной страницы: {len(orphan_dirs)} "
                     f"(у каталога есть дочерние страницы, собственной страницы в "
                     f"выгрузке нет; текста среза не несёт; возможная причина — "
                     f"страница не выгружена экспортёром (пустая или без доступа))")
        for d in orphan_dirs:
            lines.append(f"  - {d.relative_to(sources)}/")
    empty = empty_dirs(sources)
    if empty:
        lines.append(f"каталогов без парной страницы fileN.md и без дочерних страниц "
                     f"(нарушение инварианта имён выгрузки): {len(empty)}")
        for d in empty:
            lines.append(f"  - {d.relative_to(sources)}/")
    if not uncovered and not no_id and not orphan_dirs and not empty:
        lines.append("OK: выгрузка покрыта полностью, целостность "
                     "иерархии не нарушена.")
    return lines, blocking


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Покрытие страниц выгрузки артефактами комплекта "
                    "(по confluence_page_id/confluence_page_ids).")
    ap.add_argument("--sources", type=Path, required=True,
                    help="корень выгрузки (sources/confluence/<срез>)")
    ap.add_argument("--output", type=Path, required=True,
                    help="корень комплекта (output/<service>)")
    ap.add_argument("--strict", action="store_true",
                    help="код 2, если есть непокрытые страницы (с описью — "
                         "только пробелы миграции и страницы вне описи)")
    ap.add_argument("--inventory", type=Path, default=None,
                    help="опись выгрузки inventory.md; по умолчанию — в корне "
                         "--output или в его родителе")
    args = ap.parse_args()

    lines, n_uncovered = coverage_report(args.sources, args.output,
                                         inventory=args.inventory)
    for i, ln in enumerate(lines):
        print(ln if ln.startswith("  ") else f"# {ln}")
    return 2 if (args.strict and n_uncovered) else 0


if __name__ == "__main__":
    sys.exit(main())
