# app/scripts/CI/selfcheck.py
#
# Единый диспетчер механических гейтов самопроверки (срез 1: сверка
# карточек комплекта с источниками). Знание «что проверять» живёт
# здесь, а не в промпте и не у оператора: диспетчер сам находит
# карточки в docs/, сам сопоставляет каждой страницу-источник по
# confluence_page_id (frontmatter выгрузки) и прогоняет связку
# проверок нормализатора (normalize_tables.run_check — единая точка
# монтажа; двойного монтажа проверок нет).
#
# Правила устойчивости (решения 2026-08-16):
#   1) краш проверки одной карточки = брак ЭТОЙ карточки, прогон
#      продолжается (трейсбек одной строкой в отчёт);
#   2) молчаливых пропусков нет: КАЖДЫЙ md-файл комплекта попадает
#      ровно в одну категорию отчёта (✓ / ✗ / ⚠ с причиной), итог со
#      счётчиками; reverse-карточка (page_ids есть) без найденного
#      источника — брак, а не пропуск;
#   3) новой логики сверки здесь НЕТ — только обход, мэппинг, вызовы.
# Read-only: пишет только отчёт в stdout; код 2 при любом браке.
#
# Межтиповые страницы: карточки с одним главным page_id проверяются
# ОДНИМ вызовом (объединение значений; основная — первая по сортировке
# пути), внутренние сторожа прочих карточек группы — отдельными
# вызовами без источника. Дополнительные page_ids карточки (дочерние
# страницы) в срезе 1 не сверяются — честная пометка в отчёте.

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import link_debts as ld  # noqa: E402
import normalize_tables as nt  # noqa: E402
import source_coverage as sc  # noqa: E402

# служебные реестры комплекта — сверке нормализатора не подлежат
# (их сторожа — link_debts, срез 2)
_SERVICE_FILES = {"traceability-matrix.md", "open-questions.md"}
_PID_RE = re.compile(r"\d{4,}")


def read_frontmatter(path: Path) -> Optional[Dict[str, str]]:
    """Плоский frontmatter файла; None — блок не закрыт (битый),
    {} — блока нет вовсе."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return {}
    fm: Dict[str, str] = {}
    for ln in body.splitlines()[1:200]:
        if ln.strip() == "---":
            return fm
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return None


def page_ids(fm: Dict[str, str]) -> List[str]:
    raw = fm.get("confluence_page_ids", "") + " " + \
        fm.get("confluence_page_id", "")
    return _PID_RE.findall(raw)


def index_sources(root: Path):
    """page_id -> файл выгрузки; дубли — списком (используется первый
    по сортировке, в отчёт — предупреждение)."""
    idx: Dict[str, Path] = {}
    dups: Dict[str, List[Path]] = {}
    for p in sorted(root.rglob("*.md")):
        fm = read_frontmatter(p) or {}
        ids = _PID_RE.findall(fm.get("confluence_page_id", ""))
        if not ids:
            continue
        pid = ids[0]
        if pid in idx:
            dups.setdefault(pid, [idx[pid]]).append(p)
        else:
            idx[pid] = p
    return idx, dups


def _safe(fn, *args) -> Tuple[List[str], bool]:
    """Изоляция краша (правило 1): исключение = брак проверяемой
    единицы, прогон продолжается."""
    try:
        return fn(*args)
    except Exception as e:
        return [f"КРАШ проверки: {e!r} — брак, прогон продолжен"], False


def _run(files: List[Path], src: Optional[Path]) -> Tuple[List[str], bool]:
    return _safe(nt.run_check, files, src)


def run(docs: Path, sources: Optional[Path]) -> Tuple[List[str], bool]:
    report: List[str] = []
    counts = {"✓": 0, "✗": 0, "⚠": 0}
    all_ok = True

    idx: Dict[str, Path] = {}
    if sources is not None:
        idx, dups = index_sources(sources)
        for pid, paths in sorted(dups.items()):
            report.append(f"i выгрузка: page_id {pid} у нескольких файлов "
                          f"({', '.join(p.name for p in paths[:3])}) — "
                          "используется первый по сортировке")

    # перепись файлов комплекта (правило 2: каждый — ровно одна категория)
    groups: Dict[str, List[Path]] = {}
    solo: List[Tuple[Path, str]] = []  # (файл, пометка)
    for p in sorted(docs.rglob("*.md")):
        rel = p.relative_to(docs)
        if p.name in _SERVICE_FILES:
            counts["⚠"] += 1
            report.append(f"⚠ {rel}: служебный реестр — сторож среза 2 "
                          "(link_debts), сверке нормализатора не подлежит")
            continue
        fm = read_frontmatter(p)
        if fm is None:
            counts["✗"] += 1
            all_ok = False
            report.append(f"✗ {rel}: frontmatter не распознан (блок не "
                          "закрыт или файл нечитаем) — брак")
            continue
        if not fm:
            counts["⚠"] += 1
            report.append(f"⚠ {rel}: без frontmatter — вне сверки "
                          "(для документов комплекта frontmatter обязателен)")
            continue
        pids = page_ids(fm)
        if not pids:
            solo.append((p, "без источника (page_ids нет — forward/реестр)"))
        elif sources is None:
            solo.append((p, f"источник page_id {pids[0]} не сверялся — "
                            "--sources не задан"))
        elif pids[0] not in idx:
            counts["✗"] += 1
            all_ok = False
            report.append(f"✗ {rel}: источник page_id {pids[0]} НЕ НАЙДЕН "
                          "в выгрузке — reverse-карточка без сверки, брак")
        else:
            groups.setdefault(pids[0], []).append(p)
            if len(pids) > 1:
                report.append(f"i {rel}: доп. страницы-источники "
                              f"({len(pids) - 1}) механически не сверяются "
                              "(сверка — по главной, первой в списке)")

    for p, note in solo:
        rep, ok = _run([p], None)
        mark = "✓" if ok else "✗"
        counts[mark] += 1
        all_ok = all_ok and ok
        report.append(f"{mark} {p.relative_to(docs)}: {note}")
        if not ok:
            report.extend(f"   {ln}" for ln in rep)

    for pid, files in sorted(groups.items()):
        src = idx[pid]
        rep, ok = _run(files, src)
        # внутренние сторожа неглавных карточек группы — отдельно
        for extra in files[1:]:
            rep2, ok2 = _run([extra], None)
            rep = rep + [f"[{extra.name}] {ln}" for ln in rep2]
            ok = ok and ok2
        mark = "✓" if ok else "✗"
        for f in files:
            counts[mark] += 1
        all_ok = all_ok and ok
        names = ", ".join(str(f.relative_to(docs)) for f in files)
        report.append(f"{mark} {names} ← {src.name}")
        if not ok:
            report.extend(f"   {ln}" for ln in rep)

    # --- комплект-уровневые сторожа (срез 2) ---
    matrix = docs / "traceability-matrix.md"
    if matrix.is_file():
        rep, ok = _safe(ld.check, matrix, docs)
        mark = "✓" if ok else "✗"
        all_ok = all_ok and ok
        report.append(f"{mark} долги ссылок (link_debts):")
        report.extend(f"   {ln}" for ln in rep)
    else:
        all_ok = False
        report.append("✗ traceability-matrix.md: матрица не найдена — "
                      "комплект без реестра ID (обязательна, conventions "
                      "§5.3)")
    oq = docs / "open-questions.md"
    if not oq.is_file():
        oq = docs.parent / "open-questions.md"
    rep, ok = _safe(ld.check_oq_order, oq)
    all_ok = all_ok and ok
    if rep:
        report.append(("✓" if ok else "✗") + " реестр открытых вопросов:")
        report.extend(f"   {ln}" for ln in rep)
    rep, ok = _safe(ld.check_config_params, docs)
    all_ok = all_ok and ok
    if not ok:
        report.append("✗ настраиваемые параметры:")
        report.extend(f"   {ln}" for ln in rep)
    if sources is not None:
        # миграционный гейт покрытия — информационный: непокрытое —
        # остаток конвейера (судьба фиксируется долгами), не дефект
        # проверяемых карточек; на вердикт не влияет
        try:
            cov_lines, _n_unc = sc.coverage_report(sources, docs)
        except Exception as e:
            cov_lines = [f"КРАШ проверки: {e!r} — покрытие не оценено"]
        report.append("i покрытие выгрузки (миграционный гейт, "
                      "информационно):")
        report.extend(f"   {ln}" for ln in cov_lines)

    total = sum(counts.values())
    report.append(f"ИТОГО: файлов {total} — ✓ {counts['✓']}, "
                  f"✗ {counts['✗']}, ⚠ {counts['⚠']}; вердикт: "
                  + ("OK" if all_ok else "БРАК"))
    return report, all_ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Единый диспетчер самопроверки комплекта: сам находит "
                    "карточки, сопоставляет источники по confluence_page_id "
                    "и гоняет связку проверок нормализатора; код 2 при "
                    "браке. Read-only.")
    ap.add_argument("--docs", type=Path, required=True,
                    help="корень docs/ комплекта")
    ap.add_argument("--sources", type=Path, default=None,
                    help="каталог выгрузки Confluence (reverse); без него "
                         "выполняются только внутренние сторожа карточек")
    ap.add_argument("--out", type=Path, default=None,
                    help="записать полный отчёт в файл (UTF-8) — вместо "
                         "самодельных лаунчеров и shell-редиректов "
                         "(PowerShell `>` пишет UTF-16)")
    args = ap.parse_args()
    # Windows-консоль cp1251 падает на ✓/✗ — печатаем с заменой, файл
    # отчёта (--out) всегда полный UTF-8 (три самодельных лаунчера
    # агентов решали ровно эту проблему — теперь она решена утилитой)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    report, ok = run(args.docs, args.sources)
    lines = [f"# {ln}" for ln in report]
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for ln in lines:
        print(ln)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
