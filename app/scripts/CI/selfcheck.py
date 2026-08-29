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
import subprocess
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
    last = None
    for ln in body.splitlines()[1:200]:
        if ln.strip() == "---":
            return fm
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip()
            last = m.group(1)
        elif last and re.match(r"^\s+-\s+\S", ln):
            # многострочный YAML-список (COM-01 Корпкарт, 2026-08-27):
            # шаблон предписывает inline, но данные ВАЖНЕЕ формата —
            # элементы подклеиваются к значению ключа, чтобы карточка
            # не выпадала из сверки с источником молча; факт помечается
            # служебным ключом для ⚠ в отчёте
            fm[last] = (fm[last] + " "
                        + ln.strip().lstrip("-").strip()).strip()
            fm["__multiline-" + last] = "1"
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
         soft_markers: bool = True,
         pardon_src: Optional[Path] = None) -> Tuple[List[str], bool]:
    return _safe(lambda: nt.run_check(files, src, docs_root=docs_root,
                                      soft_markers=soft_markers,
                                      pardon_source=pardon_src))


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
            if p.name == "traceability-matrix.md":
                rd_rep, rd_ok = _safe(check_registry_duplicates, p)
                if not rd_ok:
                    all_ok = False
                    report.extend(rd_rep)
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
        pid_key_present = ("confluence_page_ids" in fm
                           or "confluence_page_id" in fm)
        if fm.get("__multiline-confluence_page_ids") \
                or fm.get("__multiline-confluence_page_id"):
            # строка-сигнал без счётчика: файл получит свой ✓/✗ ниже,
            # инвариант «один файл — одна отметка» не ломаем
            report.append(f"i {rel}: confluence_page_ids многострочным "
                          "YAML — шаблон предписывает inline-список; "
                          "сверка выполняется, формат привести")
        if not pids:
            if pid_key_present:
                # П-8 (COM-01 Корпкарт, 2026-08-27): ключ есть, а id не
                # распознаны — раньше карточка МОЛЧА становилась
                # «forward» и теряла всю сверку с источником (девять
                # карточек первой сдачи COM-01, фиктивная зелень)
                counts["✗"] += 1
                all_ok = False
                report.append(f"✗ {rel}: confluence_page_ids задан, но "
                              "id не распознаны — reverse-карточка "
                              "выпала бы из сверки с источником; формат "
                              "по шаблону: inline-список")
                continue
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
        # вердикт: сторож привилегий Э-12 и будущие); итог сторожа
        # полноты ячеек виден и при ✓ — иначе приёмщику не отличить
        # «сторож прошёл» от «сторож не запускался» (ложная тревога
        # приёмки COM-01-fix, 2026-08-27)
        return [ln for ln in rep if ln.startswith("предупреждение")
                or ln.startswith("полнота ячеек источника")]

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
        # внутренние сторожа неглавных карточек группы — отдельно;
        # источник группы передаётся ТОЛЬКО каналом помилований
        # (pardon_source): без него честное «ОK» из литерала источника
        # бракует часть формы гомоглифом К-30, хотя главную карточку
        # та же страница милует (z03 ISS-03, scr-cl-01.4)
        for extra in files[1:]:
            rep2, ok2 = _run([extra], None, docs, soft_markers=not strict,
                             pardon_src=src)
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
        # сторож разметки подсервисов (П-4): без таблицы в профиле
        # возвращает пусто и молчит
        sm_rep, sm_ok = _safe(check_subservice_mapping, docs, sources,
                              {pid: fs[0] for pid, fs in groups.items()})
        all_ok = all_ok and sm_ok
        report.extend(sm_rep)
        # сторож среза канона (П-5b): без строки в профиле молчит
        cut_rep, cut_ok = _safe(check_canon_cut, sources, canon_head())
        all_ok = all_ok and cut_ok
        report.extend(cut_rep)
        # сторож полноты промптов этапов (П-5b): информационный,
        # без строки «план миграции» в профиле молчит
        sp_rep, _ = _safe(check_stage_prompts, sources)
        report.extend(sp_rep)
        # сторожа протокольной дисциплины (П-5c): скрипты и retry-лимит
        pd_rep, pd_ok = _safe(check_protocol_discipline, sources)
        all_ok = all_ok and pd_ok
        report.extend(pd_rep)
    # детектор похожих точек применения групп (П-5e): i-сигналы,
    # вердикт не трогают — решение о консолидации только человеческое
    sg_rep, _ = _safe(lambda: (check_similar_group_points(docs), True))
    report.extend(sg_rep)
    # голые атрибутные обращения к сущностям реестра (2026-08-29):
    # ⚠-сигналы, вердикт не трогают
    bm_rep, _ = _safe(lambda: (check_bare_entity_mentions(docs), True))
    report.extend(bm_rep)
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


# --- сторож разметки подсервисов (П-4 песочницы, 2026-08-26) ---
#
# Крупный сервис из подсервисов (conventions §3.1): таблица «Разметка
# подсервисов» в профиле источников (sources/README.md) декларирует
# «тег/ветвь выгрузки → подсервис <слаг> | core <слаг> | общая часть |
# вне Экосистемы»; путь карточки — srs/[<слаг>/]<тип>/. Сторож держит
# соответствие «источник → путь» механически (иначе разметка — устная
# договорённость). Гейт МОЛЧИТ без таблицы (обычные сервисы не
# затронуты); матчер — тег-префикс титула источника или имя
# верхнеуровневой ветви выгрузки, первая подошедшая строка выигрывает.

_KNOWN_TYPES = {
    "function", "screen-form", "control", "process", "data-model",
    "contract-call", "internal-contract", "print-form", "notification",
    "agent", "brd",
}
_ZONE_RE = re.compile(
    r"^(?:(подсервис|core)\s+([\w-]+)|общая часть|вне Экосистемы.*)$",
    re.I)


def _load_subservice_map(profile: Path):
    """[(матчер, слаг|None, зона)]; None — таблицы/файла нет."""
    try:
        text = profile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"^#+\s*Разметка подсервисов.*$", text, re.M)
    if not m:
        return None
    rows = []
    for ln in text[m.end():].splitlines():
        s = ln.strip()
        if s.startswith("#"):
            break
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in ("матчер (тег или ветвь)",
                                                  "матчер"):
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        zm = _ZONE_RE.match(cells[1])
        if not zm:
            continue
        zone = cells[1].lower()
        slug = zm.group(2)
        kind = ("slug" if zm.group(1) else
                "common" if zone.startswith("общая") else "external")
        rows.append((cells[0], slug, kind))
    return rows or None


def check_subservice_mapping(docs: Path, sources: Path,
                             card_files: Dict[str, Path]):
    """(отчёт, ok). card_files: page_id -> карточка docs. Зона источника
    определяется по титулу/ветви его файла выгрузки; путь карточки
    обязан начинаться srs/<слаг>/ (подсервис/core), не иметь слага
    (общая часть) или карточки не должно быть вовсе (вне Экосистемы)."""
    profile = sources.parent / "README.md"
    if not profile.is_file():
        profile = sources / "README.md"
    smap = _load_subservice_map(profile)
    if not smap:
        return [], True
    report: List[str] = []
    ok = True
    slugs = {slug for _, slug, kind in smap if kind == "slug"}
    for src_file in sorted(sources.rglob("*.md")):
        if src_file.name.lower() == "index.md":
            continue
        head = src_file.read_text(encoding="utf-8",
                                  errors="replace")[:2000]
        pid_m = re.search(r"^confluence_page_id:\s*['\"]?(\d+)",
                          head, re.M)
        if not pid_m or pid_m.group(1) not in card_files:
            continue
        title_m = re.search(r"^title:\s*(.+)$", head, re.M)
        title = title_m.group(1).strip().strip("'\"") if title_m else ""
        try:
            branch = src_file.relative_to(sources).parts[0]
        except ValueError:
            branch = ""
        zone = next(((slug, kind) for matcher, slug, kind in smap
                     if title.startswith(matcher)
                     or matcher.strip("[]") == branch
                     or matcher == branch), None)
        if zone is None:
            continue
        slug, kind = zone
        card = card_files[pid_m.group(1)]
        rel = card.relative_to(docs).as_posix()
        parts = rel.split("/")
        seg = (parts[1] if len(parts) > 2 and parts[0] == "srs"
               and parts[1] not in _KNOWN_TYPES else None)
        if kind == "external":
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                "«вне Экосистемы», карточке в docs/ не место "
                "(мини-комплект вне комплекта, conventions §3.1)")
        elif kind == "slug" and seg != slug:
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                f"в подсервис «{slug}», ожидался путь srs/{slug}/… "
                f"(фактический сегмент: {seg or 'нет — корень srs'})")
        elif kind == "common" and seg is not None:
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                f"«общая часть», карточка лежит в подсервисе «{seg}»")
        elif seg is not None and seg not in slugs:
            ok = False
            report.append(
                f"✗ разметка: {rel} — сегмент «{seg}» отсутствует в "
                "таблице разметки профиля (самодеятельный подкаталог)")
    if not report:
        report.append("разметка подсервисов: соответствие "
                      "«источник → путь» выдержано ✓")
    return report, ok


# --- сторож среза канона (П-5b, 2026-08-27) ---
# Профиль src-репозитория несёт строку «срез канона: <hash>» — источник
# истины о том, на каком каноне должен работать стенд. selfcheck знает
# свой фактический HEAD (он лежит в каноне) и сверяет сам: промпты
# заходов хэш не носят (дважды за пилот он устаревал между генерацией
# и запуском); обновление строки — осознанное действие владельца при
# приёмке правки канона, а забытое обновление — громкий ✗, не
# молчаливая работа на старом срезе. Без строки сторож молчит (мягкое
# включение, как у сторожа разметки). Dev-копия selfcheck вне канона
# (analyzer) или недоступный git — ⚠, не ✗.

_CANON_CUT_RE = re.compile(r"срез\s+канона\D{0,40}?([0-9a-f]{7,40})",
                           re.I)


def canon_head() -> Optional[str]:
    """Фактический HEAD репозитория, из которого запущен selfcheck;
    None — dev-копия вне канона или git недоступен."""
    tool_dir = Path(__file__).resolve().parent
    if tool_dir.name != "tools" or tool_dir.parent.name != "_meta":
        return None
    root = tool_dir.parent.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def check_canon_cut(sources: Path,
                    head: Optional[str]) -> Tuple[List[str], bool]:
    """Сверка строки «срез канона: <hash>» профиля с фактическим HEAD."""
    profile = sources.parent / "README.md"
    if not profile.is_file():
        profile = sources / "README.md"
    try:
        text = profile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    m = _CANON_CUT_RE.search(text)
    if not m:
        return [], True
    want = m.group(1).lower()
    if head is None:
        return [f"⚠ срез канона: профиль требует {want}, но фактический "
                "HEAD канона не определён (dev-копия selfcheck вне "
                "канона или git недоступен) — сверка не выполнена"], True
    have = head.lower()
    if have.startswith(want) or want.startswith(have):
        return [f"✓ срез канона: профиль {want} = HEAD канона {have}"], True
    return [f"✗ срез канона: профиль требует {want}, фактический HEAD "
            f"канона {have} — обновите клон канона либо строку «срез "
            "канона» профиля (решение владельца)"], False


# --- сторожа протокольной дисциплины (П-5c, 2026-08-28) ---
# Замер «слабый исполнитель × компактный промпт» (ISS-02): модель
# написала генерирующий скрипт и сделала третий retry — оба прямых
# запрета протокола (§3, §6) потерялись из её внимания за два часа
# работы. Правило и образец есть — не было сторожа; закон обходов:
# ненаблюдаемое правило со временем нарушается любым исполнителем,
# вопрос лишь ёмкости. Мягкое включение: только на протокольном
# стенде (в профиле есть строка «срез канона»). confluence/ исключён
# из скана — это данные источника, не рабочие файлы исполнителя.

_SCRIPT_EXT = {".py", ".ps1", ".psm1", ".sh", ".bat", ".cmd", ".js"}
_RETRY_RE = re.compile(r"-retry-(\d+)", re.I)


def check_protocol_discipline(sources: Path) -> Tuple[List[str], bool]:
    """✗ на следы нарушений протокола: посторонние скрипты в src-репо
    (§3) и отчёты попыток сверх лимита двух (§6)."""
    root = sources.parent
    profile = root / "README.md"
    if not profile.is_file():
        profile = sources / "README.md"
        root = sources
    try:
        ptext = profile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    if not _CANON_CUT_RE.search(ptext):
        return [], True
    report: List[str] = []
    ok = True
    try:
        src_rel = sources.resolve().relative_to(root.resolve()).parts[0]
    except ValueError:
        src_rel = None
    scripts = []
    for p in root.rglob("*"):
        if p.suffix.lower() not in _SCRIPT_EXT:
            continue
        parts = p.relative_to(root).parts
        if ".git" in parts or (src_rel and parts[0] == src_rel):
            continue
        scripts.append(p.relative_to(root))
    for s in scripts[:6]:
        ok = False
        report.append(f"✗ протокол §3: посторонний скрипт в src-репо — "
                      f"{s} (файлы комплекта правятся пофайлово; "
                      "скрипты исполнителю запрещены, разрешены только "
                      "канонические инструменты)")
    if len(scripts) > 6:
        report.append(f"   … и ещё {len(scripts) - 6} скриптов")
    sandbox = root / "sandbox"
    if sandbox.is_dir():
        # retry-N в имени — номер повторного ПРОГОНА захода; лимит §6
        # считается по каждому ✗ отдельно (параллельные ✗ легально
        # дают retry-3 при ≤2 попыток на каждый — кейс z01 ISS-03).
        # 3–4 прогона — ⚠ приёмке проверить по-✗ квалификацию в сдаче;
        # 5+ — ✗ (столько параллельных ✗ в одном заходе не живёт).
        for f in sorted(sandbox.iterdir()):
            m = _RETRY_RE.search(f.name)
            if not m:
                continue
            n = int(m.group(1))
            if n >= 5:
                ok = False
                report.append(f"✗ протокол §6: отчёт {f.name} — "
                              "пятый повторный прогон; лимит попыток "
                              "заведомо исчерпан, требуется исход "
                              "«СТОП по лимиту» и решение человека")
            elif n >= 3:
                report.append(f"⚠ протокол §6: отчёт {f.name} — "
                              "третий+ повторный прогон; приёмке "
                              "проверить по-✗ квалификацию попыток в "
                              "сдаче (легально при параллельных ✗ с "
                              "≤2 попыток на каждый)")
    return report, ok
# План обязан иметь промпт-файл prompts/<ЭТАП>.md на КАЖДЫЙ этап
# (план-промпт v2.2 п.10); неполный пакет промптов обнаруживался
# только внимательностью приёмщика (кейс: «дособери с ISS-02 и далее»
# прочитано планировщиком как «без COM-03+»). Сторож делает неполноту
# видимой на каждом прогоне. Мягкое включение: активен только при
# строке «план миграции: <файл>» в профиле источников; этапы, чьи
# отчёты уже лежат в sandbox/ (selfcheck-<ЭТАП>*.txt), считаются
# выполненными — промпт для них не требуется. Информационный гейт:
# вердикт не трогает (неполнота пакета — не дефект комплекта docs).

_PLAN_LINE_RE = re.compile(r"план\s+миграции\D{0,40}?`?([\w.\- ]+\.md)`?",
                           re.I)
_STAGE_ROW_RE = re.compile(r"^\|\s*`([A-ZА-Я]{2,4}-\d{2})`\s*\|", re.M)


def check_stage_prompts(sources: Path) -> Tuple[List[str], bool]:
    """⚠-строки о этапах плана без файла промпта; ok всегда True."""
    root = sources.parent
    profile = root / "README.md"
    if not profile.is_file():
        profile = sources / "README.md"
        root = sources
    try:
        ptext = profile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    m = _PLAN_LINE_RE.search(ptext)
    if not m:
        return [], True
    plan = root / m.group(1).strip()
    if not plan.is_file():
        return [f"⚠ промпты этапов: план «{m.group(1).strip()}» из "
                "профиля не найден — сверка пакета не выполнена"], True
    stages = set(_STAGE_ROW_RE.findall(
        plan.read_text(encoding="utf-8", errors="replace")))
    if not stages:
        return ["⚠ промпты этапов: в плане не распознаны коды этапов "
                "(таблица с `КОД-NN` первой ячейкой) — сверка пакета "
                "не выполнена"], True
    pdir = root / "prompts"
    have = ({f.stem for f in pdir.glob("*.md")} if pdir.is_dir()
            else set())
    sandbox = root / "sandbox"
    done = {s for s in stages
            if sandbox.is_dir() and any(sandbox.glob(f"selfcheck-{s}*"))}
    missing = sorted(stages - have - done)
    orphans = sorted(have - stages)
    lines: List[str] = []
    if missing:
        lines.append(f"⚠ промпты этапов: без файла prompts/<ЭТАП>.md — "
                     f"{len(missing)} из {len(stages)} этапов плана: "
                     + ", ".join(missing[:12])
                     + (" …" if len(missing) > 12 else ""))
    else:
        lines.append(f"✓ промпты этапов: файлы либо выполненные отчёты "
                     f"есть для всех {len(stages)} этапов плана")
    for s in orphans[:6]:
        lines.append(f"i промпт prompts/{s}.md не соответствует ни "
                     "одному коду этапа плана")
    return lines, True


# --- сторожа П-5d (2026-08-28) ---
# 1) Имя журнала: §4 фиксирует sandbox/journal.txt — самодельные имена
#    расщепляют историю стенда (два живых случая: selfcheck-journal.md
#    у слабого исполнителя d05b, дрейф имён первой редакции COM-01).
#    Замечание владельца лечит один прогон — сторож лечит класс.
# 2) Дубли реестровых ID: два CTL-000 прошли мимо всех гейтов (d01
#    ISS-02). Сторож — по секции «Реестр ID» матрицы: строки покрытия
#    легально повторяют ID и не проверяются.

def check_journal_name(journal: Path,
                       sources: Path) -> Optional[str]:
    """Строка-✗, если журнал прогона не sandbox/journal.txt стенда."""
    expected = sources.resolve().parent / "sandbox" / "journal.txt"
    if journal.resolve() == expected:
        return None
    return (f"✗ протокол §4: журнал прогона «{journal}» — единый журнал "
            "стенда ФИКСИРОВАН: sandbox/journal.txt; самодельные имена "
            "расщепляют историю (запись выполнена, но прогон "
            "аннулирован — повтори с правильным журналом)")


_REGISTRY_HDR_RE = re.compile(r"^#+\s*(?:\d+\.\s*)?Реестр\s+ID",
                              re.I | re.M)


def check_registry_duplicates(matrix_path: Path) -> Tuple[List[str], bool]:
    """Дубли ID в секции «Реестр ID» матрицы — ✗ (реестровый ID
    уникален; кейс: два CTL-000 у общего и подсервисного README)."""
    try:
        text = matrix_path.read_text(encoding="utf-8", errors="replace")
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
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
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


# --- детектор похожих точек применения групп (П-5e, 2026-08-28) ---
# Механический перенос «страница × группа → GRP» размножает одну точку
# применения, описанную разными страницами с разных сторон (живой кейс:
# три группы «Подписать и отправить» GRP-7/9/16 в cc-card-issue нашёл
# вопрос владельца, не прибор). Детектор — НЕ решатель: пары групп
# одного реестра с общим цитируемым литералом (кнопка «…», статус
# `…`) поднимаются i-строкой; решение «слить/различить как фазы» —
# только человеческое (шаг консолидации этапа). Скоуп — ОДИН реестровый
# README: совпадение кнопок между подсервисами — разные ЭФ, не дубль.

_GRP_ROW_RE = re.compile(r"^\|\s*\[?(CTL-GRP-\d+)\]?[^|]*\|\s*([^|]+)")
_QUOTE_TOKEN_RE = re.compile(r"«([^»]{3,60})»|`([A-Za-z_]{3,30})`")


def check_bare_entity_mentions(docs: Path) -> List[str]:
    """Голые атрибутные обращения «Название.<Атрибут>» к сущностям
    реестра ID без ссылки на карточку (решение владельца 2026-08-29,
    README SCR-CL-01: «Клиент Банка.<Краткое наименование>» голым
    текстом при существующей EXT-002 в комплекте).

    Матчинг — по НАИМЕНОВАНИЯМ реестра ID матрицы, не по тегам [XX]:
    теги в титулах Confluence — частая рекомендация, не требование
    (платформенные страницы почти без них), теговый сторож упоминаний
    этот класс не видит. Флагается только обращение к атрибуту
    («Название.<…>») — место, где ссылка на модель данных обязательна;
    прочие голые упоминания имён не флагаются (шум: имена встречаются
    в каждом абзаце). ⚠-сигнал, вердикт не трогает — оформление ссылок
    закрывается дозаходом."""
    matrix = docs / "traceability-matrix.md"
    if not matrix.exists():
        return []
    text = matrix.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^#{1,3}\s.*Реестр ID\s*$", text, re.M)
    names: dict = {}
    for ln in (text[m.end():] if m else "").splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"[A-Z]+-[\w.]+", cells[0]):
            continue
        name = re.sub(r"^\[[^\]]+\]\s*", "", cells[1]).strip()
        # короткие/односложные имена — шум («Фильтр», «Заявка»)
        if len(name) >= 10 and " " in name:
            names[name.lower()] = cells[0]
    if not names:
        return []
    report: List[str] = []
    for p in sorted(docs.rglob("*.md")):
        if p == matrix:
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        # ссылки вырезаются целиком: ярлык со ссылкой — оформлено верно
        bare = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", body)
        hits: dict = {}
        for am in re.finditer(r"([^\n<>|]{3,80}?)\.<", bare):
            cand = am.group(1).strip().lower()
            for name, rid in names.items():
                if cand.endswith(name):
                    hits[name] = hits.get(name, 0) + 1
                    break
        for name, cnt in sorted(hits.items()):
            report.append(
                f"⚠ {p.relative_to(docs)}: голое обращение "
                f"«{name}.<…>» ×{cnt} — карточка {names[name]} есть в "
                "реестре, обращение к атрибуту оформляется ссылкой")
    return report


def check_similar_group_points(docs: Path) -> List[str]:
    """i-строки о парах групп с общим цитируемым литералом точки."""
    report: List[str] = []
    for readme in sorted(docs.rglob("control/README.md")):
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        toks: Dict[str, List[Tuple[str, str]]] = {}
        for ln in text.splitlines():
            m = _GRP_ROW_RE.match(ln.strip())
            if not m:
                continue
            gid, desc = m.group(1), m.group(2).strip()
            for qm in _QUOTE_TOKEN_RE.finditer(desc):
                tok = (qm.group(1) or qm.group(2)).strip().lower()
                toks.setdefault(tok, []).append((gid, desc[:50]))
        rel = readme.relative_to(docs)
        for tok, grps in sorted(toks.items()):
            ids = sorted({g for g, _ in grps})
            if len(ids) > 1:
                report.append(
                    f"i похожие точки применения [{rel}]: "
                    f"{' ↔ '.join(ids)} — общий литерал «{tok}»; "
                    "кандидат на консолидацию (решение владельца, "
                    "шаг консолидации этапа)")
    return report


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
    if args.journal is not None and args.sources is not None:
        jwarn = check_journal_name(args.journal, args.sources)
        if jwarn:
            report.append(jwarn)
            ok = False
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
