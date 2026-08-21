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


def _run(files: List[Path], src: Optional[Path],
         docs_root: Optional[Path] = None,
         soft_markers: bool = True) -> Tuple[List[str], bool]:
    return _safe(lambda: nt.run_check(files, src, docs_root=docs_root,
                                      soft_markers=soft_markers))


def run(docs: Path, sources: Optional[Path],
        strict: bool = False) -> Tuple[List[str], bool]:
    # Два профиля (Р-8, 2026-08-22): командный (по умолчанию) — маркеры
    # сокращения предупреждением (3/3 ложняков на эталоне); полный
    # (--strict, прогоны держателей канона) — маркеры браком, как раньше.
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
    extra_pids: Dict[Path, int] = {}   # карточка -> число доп. page_ids
    card_ids: Dict[Path, str] = {}     # карточка -> id из frontmatter
    for p in sorted(docs.rglob("*.md")):
        rel = p.relative_to(docs)
        if p.name in _SERVICE_FILES:
            # содержательно реестр сторожит link_debts (срез 2), но
            # структурную целостность таблиц проверяем и здесь: разрыв
            # матрицы жил с захода 4 незамеченным (К-16, 2026-08-17)
            rep, ok = _safe(nt.check_service_table_integrity, p)
            if ok:
                counts["⚠"] += 1
                report.append(f"⚠ {rel}: служебный реестр — сторож среза 2 "
                              "(link_debts), сверке нормализатора не "
                              "подлежит")
            else:
                counts["✗"] += 1
                all_ok = False
                report.append(f"✗ {rel}: служебный реестр — таблицы битые")
                report.extend(f"   {ln}" for ln in rep)
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
            # Р-9 (2026-08-22): навигационные README освобождены от
            # требования frontmatter — в эталоне их 5, техдолг осознан
            # и будет закрыт по всем сервисам одной волной. Файл остаётся
            # в переписи (правило 2: молчаливых пропусков нет).
            if p.name.lower() == "readme.md":
                report.append(f"⚠ {rel}: навигационный README без "
                              "frontmatter — вне сверки (освобождён, Р-9)")
            else:
                report.append(f"⚠ {rel}: без frontmatter — вне сверки "
                              "(для документов комплекта frontmatter "
                              "обязателен)")
            continue
        if fm.get("id"):
            card_ids[p] = fm["id"]
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
            extra_pids[p] = len(pids) - 1
            if len(pids) > 1:
                report.append(f"i {rel}: доп. страницы-источники "
                              f"({len(pids) - 1}) механически не сверяются "
                              "(сверка — по главной, первой в списке)")

    def _warns(rep: List[str]) -> List[str]:
        # предупреждения видимы и при ✓ (софт-сигналы, не влияют на
        # вердикт: сторож привилегий Э-12 и будущие)
        return [ln for ln in rep if ln.startswith("предупреждение")]

    for p, note in solo:
        rep, ok = _run([p], None, docs, soft_markers=not strict)
        mark = "✓" if ok else "✗"
        counts[mark] += 1
        all_ok = all_ok and ok
        if ok:
            report.append(f"✓ {p.relative_to(docs)}: {note}")
            report.extend(f"   {ln}" for ln in _warns(rep))
        else:
            # Формулировка причины ✗ (2026-08-22): пометка режима сверки
            # («без источника…») читалась причиной брака — брак всегда
            # у внутренних сторожей, их строки ниже.
            report.append(f"✗ {p.relative_to(docs)}: брак внутренних "
                          f"сторожей (причины ниже); {note}")
            report.extend(f"   {ln}" for ln in rep)

    for pid, files in sorted(groups.items()):
        src = idx[pid]
        # К-20 (2026-08-18): паразитирование на «доп. страницы не
        # сверяются» — если группу по ОДНОМУ главному page_id делят
        # README-реестр и карточки, у которых есть СВОИ доп. страницы,
        # то карточкам главной поставлено оглавление каталога: их
        # собственные страницы выпадают из сверки целиком (прогон
        # inkasso-run1: 12 карточек «сверялись» против оглавления МД —
        # фиктивная зелень). Главная страница карточки — та, чьим
        # переносом она является; оглавление — главная только у README.
        has_readme = any(f.name.lower() == "readme.md" for f in files)
        misordered = [f for f in files
                      if f.name.lower() != "readme.md"
                      and extra_pids.get(f, 0) > 0] if has_readme else []
        if misordered:
            all_ok = False
            for f in misordered:
                counts["✗"] += 1
                report.append(
                    f"✗ {f.relative_to(docs)}: главной указана "
                    f"страница-оглавление ({src.name}) — карточка не "
                    "сверяется со СВОЕЙ страницей; порядок "
                    "confluence_page_ids: главная страница карточки "
                    "ПЕРВОЙ, оглавление — главная только у README")
            files = [f for f in files if f not in misordered]
            if not files:
                continue
        rep, ok = _run(files, src, docs, soft_markers=not strict)
        # внутренние сторожа неглавных карточек группы — отдельно
        for extra in files[1:]:
            rep2, ok2 = _run([extra], None, docs, soft_markers=not strict)
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
        else:
            report.extend(f"   {ln}" for ln in _warns(rep))

    # --- комплект-уровневые сторожа (срез 2) ---
    # чистота корня репозитория отдачи (2026-08-19): дозаход 5.5 оставил
    # в корне 7 скриптов массовых правок и __pycache__ — прибор корень
    # не видел, устное «удали» не персистентно. Инвариант: корень несёт
    # штатные каталоги (docs/sources/sandbox/.git) и markdown/точечные
    # файлы; исполняемое и кэши = брак.
    # Две топологии комплекта: стендовая (--docs = <root>/docs, root =
    # родитель) и «комплект в корне репозитория» (эталон
    # docs-account-opening-request: brd/, srs/ и корневые документы лежат
    # прямо в корне; --docs = корень). Признак второй — srs/ или brd/
    # внутри docs; тогда root = сам docs, а brd/srs — штатные каталоги.
    # С «--docs .» docs.parent == docs («.».parent == «.») — прежний код
    # молча мерил сам комплект и флаговал brd/srs как мусор.
    _docs_r = docs.resolve()
    if (docs / "srs").is_dir() or (docs / "brd").is_dir():
        root = docs
    else:
        root = _docs_r.parent
    _ok_dirs = {"docs", "sources", "sandbox", ".git", "brd", "srs",
                _docs_r.name}
    # штатные не-markdown файлы GitLab-репозитория комплекта
    _ok_files = {"CODEOWNERS", "gpb-manifest.json"}
    if sources is not None:
        # каталог выгрузки задаётся аргументом и не обязан зваться
        # «sources» — если он внутри корня, его вершина легитимна
        try:
            _ok_dirs.add(
                sources.resolve().relative_to(root.resolve()).parts[0])
        except (ValueError, IndexError, OSError):
            pass
    junk = sorted(
        p.name for p in root.iterdir()
        if (p.is_dir() and p.name not in _ok_dirs)
        or (p.is_file() and not p.name.startswith(".")
            and p.name not in _ok_files
            and p.suffix.lower() not in (".md", ".markdown")))
    if junk:
        all_ok = False
        report.append(
            f"✗ корень репозитория: посторонние файлы ×{len(junk)} "
            f"({', '.join(junk[:8])}) — в корне только штатные каталоги "
            "(docs/sources/sandbox) и markdown; рабочие скрипты и кэши "
            "недопустимы (скрипты, изменяющие файлы комплекта, запрещены "
            "вовсе; read-only анализ — в sandbox)")
    matrix = docs / "traceability-matrix.md"
    if matrix.is_file():
        # К-22 (2026-08-18): id из frontmatter каждой карточки обязан
        # состоять в реестре ID матрицы — фантомный/авансовый ID вне
        # реестра невидим сверкам и ломает правило выдачи ID (дозаход
        # 3.1: rbac-заглушка с RBAC-001, которого нет в матрице)
        mtext = matrix.read_text(encoding="utf-8", errors="replace")
        ghosts = sorted((p, cid) for p, cid in card_ids.items()
                        if cid not in mtext)
        if ghosts:
            all_ok = False
            report.append("✗ реестр ID матрицы: фантомные id карточек "
                          "(в реестре матрицы отсутствуют — ID выдаются "
                          "по реестру, авансовые запрещены):")
            report.extend(
                f"   {p.relative_to(docs)}: id {cid} ✗"
                for p, cid in ghosts[:10])
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
    # К-17: page_id в текстах OQ — софт-сигнал (носители page_id — только
    # frontmatter и матрица; ужесточение после вычистки легаси-фона)
    wrep, _ = _safe(nt.check_oq_page_refs, oq)
    if rep or wrep:
        report.append(("✓" if ok else "✗") + " реестр открытых вопросов:")
        report.extend(f"   {ln}" for ln in rep)
        report.extend(f"   {ln}" for ln in wrep)
    # реестр замечаний команды (цикл обратной связи, модель 2026-08-17):
    # feedback.md живёт в КОРНЕ репозитория отдачи; файла нет — ок
    rep, ok = _safe(ld.check_feedback_order, docs.parent / "feedback.md")
    all_ok = all_ok and ok
    if rep:
        report.append(("✓" if ok else "✗") + " реестр замечаний команды:")
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


# --- дельта против базлайна (протокол сдачи, 2026-08-19) ---
#
# «Монотонно падать» — неверный инвариант: честный рост находок бывает
# (снятие маскировки/починка frontmatter раскрывает скрытое — пилот-3:
# возврат тегов добавил ⚠). Верный инвариант сдачи: каждый ✗ на момент
# сдачи погашен или объяснён блокером, НОВЫЕ ✗ квалифицированы
# (раскрытие в зоне правок либо ПОРЧА вне зоны = брак дозахода —
# авария достройки 5.5: правки функций ломали prc-файлы молча).
# Протокол: старт дозахода — «--out sandbox/baseline.txt», сдача —
# «--baseline sandbox/baseline.txt», дельта-блок в сдаче дословно.

_MARKS = ("✓", "✗", "⚠")


def _verdict_map(lines) -> Dict[str, str]:
    """вердикт по единице отчёта: файл (в группах «a.md, b.md ← src» —
    каждый) или комплект-уровневый гейт (текст до двоеточия)."""
    out: Dict[str, str] = {}
    for ln in lines:
        s = ln.strip()
        if not s or s[0] not in _MARKS:
            continue
        mark, rest = s[0], s[1:].strip()
        rest = rest.split(" ← ")[0].split(":")[0].strip()
        for name in rest.split(", "):
            if name:
                out[name] = mark
    return out


def delta_report(baseline_path: Path, cur_lines: List[str]) -> List[str]:
    try:
        raw = baseline_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [f"i дельта: базлайн не прочитан ({e!r}) — сравнение "
                "пропущено"]
    base = _verdict_map(ln.lstrip("# ").rstrip()
                        for ln in raw.splitlines())
    cur = _verdict_map(cur_lines)
    n_base = sum(1 for v in base.values() if v == "✗")
    n_cur = sum(1 for v in cur.values() if v == "✗")
    closed = sorted(k for k, v in cur.items()
                    if v != "✗" and base.get(k) == "✗")
    opened = sorted(k for k, v in cur.items()
                    if v == "✗" and base.get(k) != "✗")
    out = [f"дельта против базлайна {baseline_path.name}: "
           f"✗ было {n_base} → стало {n_cur}"]
    if closed:
        out.append(f"   закрыто ✗→✓ ×{len(closed)}: "
                   + ", ".join(closed[:10]))
    if opened:
        out.append(f"   НОВЫЕ ✗ ×{len(opened)}: " + ", ".join(opened[:10])
                   + " — каждый квалифицировать в сдаче: раскрытие в "
                   "зоне правок (в работу или блокер) либо ПОРЧА вне "
                   "зоны правок (брак дозахода)")
    if not closed and not opened:
        out.append("   изменений вердиктов нет")
    return out


def main() -> int:
    # Windows-консоль cp1251 падает на ✓/✗ — печатаем с заменой, файл
    # отчёта (--out) всегда полный UTF-8 (три самодельных лаунчера
    # агентов решали ровно эту проблему — теперь она решена утилитой).
    # До argparse: текст --help тоже содержит «✗» и падал до перестройки.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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
    ap.add_argument("--baseline", type=Path, default=None,
                    help="сравнить вердикты с ранее сохранённым отчётом "
                         "(--out в начале дозахода): дельта закрытых и "
                         "НОВЫХ ✗ — блок обязателен в сдаче")
    ap.add_argument("--strict", action="store_true",
                    help="полный профиль (держатели канона): маркеры "
                         "сокращения — брак; без флага — командный "
                         "профиль, маркеры — предупреждение (Р-8)")
    ap.add_argument("--journal", type=Path, default=None,
                    help="дописать строку «таймстемп | ИТОГО…» в файл "
                         "журнала (хронометраж этапов дозахода: время "
                         "штампует прибор, не исполнитель — у LLM нет "
                         "часов, самодельные таймстемпы фабрикуются)")
    args = ap.parse_args()
    report, ok = run(args.docs, args.sources, strict=args.strict)
    if args.baseline is not None:
        report.extend(delta_report(args.baseline, report))
    if args.journal is not None:
        import json
        from datetime import datetime
        itogo = next((ln for ln in report if ln.startswith("ИТОГО")),
                     "ИТОГО: ?")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # изменённые с ПРОШЛОГО прогона файлы (mtime-скан docs):
            # интервал журнала и его содержимое — в одной строке,
            # повторные правки одного файла видны по-прогонно (вопрос
            # аналитика о соотнесении тихих интервалов с шагами)
            state_p = args.journal.with_suffix(
                args.journal.suffix + ".state")
            cur_mt = {str(p.relative_to(args.docs)):
                      round(p.stat().st_mtime, 2)
                      for p in sorted(args.docs.rglob("*.md"))}
            try:
                prev_mt = json.loads(state_p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                prev_mt = None
            if prev_mt is None:
                changed_note = "первый прогон (точка отсчёта)"
            else:
                changed = sorted(f for f, mt in cur_mt.items()
                                 if prev_mt.get(f) != mt)
                changed_note = ("изменены: " + ", ".join(changed[:12])
                                + (f" (+{len(changed) - 12})"
                                   if len(changed) > 12 else "")
                                if changed else "изменений файлов нет")
            args.journal.parent.mkdir(parents=True, exist_ok=True)
            with open(args.journal, "a", encoding="utf-8") as jf:
                jf.write(f"{stamp} | {itogo} | {changed_note}\n")
            state_p.write_text(json.dumps(cur_mt, ensure_ascii=False),
                               encoding="utf-8")
        except OSError as e:
            report.append(f"i журнал не записан: {e!r}")
    lines = [f"# {ln}" for ln in report]
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for ln in lines:
        print(ln)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
