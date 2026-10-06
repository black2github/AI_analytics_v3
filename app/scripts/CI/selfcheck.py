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
from urllib.parse import unquote
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


def _empty_source_note(src: Path) -> Tuple[Optional[str], bool]:
    """(пояснение, заморожена) — если тело страницы-источника пусто;
    иначе (None, False).

    Пустой источник (2026-10-05, миграция «Корпоративных карт»): страница
    с флагом заморозки `unapproved_jira` после reject-all несёт один
    frontmatter. Карточка, ссылающаяся на неё, получала ✓: сверять не с
    чем, все сторожа полноты проходят вхолостую. Шесть карточек лимитов
    так прошли гейт, а после перевыгрузки страниц в них не хватило 23
    значений таблицы и 6 фрагментов. Пустота определяется строго — в
    теле нет ни одного непробельного символа; страница с заголовком или
    одной строкой пустой не считается.

    Ужесточение (решение владельца 2026-10-05, FB-08 «Корпоративных
    карт»): страница с флагом заморозки — ✗, а не ⚠. Разбор показал, что
    карточки по замороженным страницам были собраны из архива raw по
    записанному в промпте решению акцептующего, и предупреждение их не
    остановило бы. Теперь принять архив источником можно только осознанно
    приняв БРАК. Пустая страница БЕЗ флага остаётся ⚠: причина
    неизвестна, решение человеческое."""
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, False
    body = text.lstrip("\ufeff")
    fm_text = ""
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) == 3:
            fm_text, body = parts[1], parts[2]
    if body.strip():
        return None, False
    m = re.search(r"^unapproved_jira:\s*(.+)$", fm_text, re.M)
    if m:
        task = m.group(1).strip().strip("'\"[]")
        return ("источник пуст: страница заморожена флагом unapproved_jira "
                f"({task}) — сверка с источником не выполнялась, перенос "
                "не подтверждён; по замороженной странице карточка не "
                "создаётся, содержимое из архива raw основанием не служит "
                "✗"), True
    return ("источник пуст: в теле страницы-источника нет текста — сверка "
            "с источником не выполнялась, перенос не подтверждён; "
            "открытый вопрос акцептующему"), False


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
        strict: bool = False,
        catalog: Optional[Path] = None) -> Tuple[List[str], bool]:
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
        # префикс «[файл] » у строк неглавных карточек группы не должен
        # прятать их ⚠ при зелёной группе (находка 2026-08-31: сторож
        # entity сработал на 37 файлах, в отчёте были видны 7)
        # помилованный маркер (FB-09: «и т.д.» дословно из источника)
        # тоже виден при ✓ — иначе исчезновение ⚠ неотличимо от
        # «сторож не запускался»
        return [ln for ln in rep
                if re.match(r"^(?:\[[^\]]+\]\s+)?(?:предупреждение|"
                            r"полнота ячеек источника|маркер «)", ln)]

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
        # макеты Figma группы (решение 2026-08-31, модель README/main):
        # ссылки макетов живут в НЕсверяемом README-оглавлении — их
        # наличие сторожится здесь (сверка ячейки макетов отключена)
        try:
            _src_t = src.read_text(encoding="utf-8", errors="replace")
            _rd = files[0].parent / "README.md"
            if ("figma.com" in _src_t.lower() and _rd.exists()
                    and files[0].name.endswith("-main.md")
                    and "figma.com" not in _rd.read_text(
                        encoding="utf-8", errors="replace").lower()):
                rep = rep + ["предупреждение: источник несёт ссылки "
                             "Figma, а README-оглавление группы — нет: "
                             "макеты живут в README (решение "
                             "2026-08-31), вернуть ссылки"]
        except OSError:
            pass
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
        # пустой источник (2026-10-05): ✓ без сверки — фиктивная зелень.
        # Замороженная страница (флаг unapproved_jira) — ✗: карточка по
        # ней не создаётся. Пустая без флага — ⚠ (вердикт не меняется:
        # причина неизвестна, решение человеческое). README-оглавление
        # на странице-контейнере без собственного текста — норма, не
        # трогается.
        empty_note, frozen = _empty_source_note(src)
        if empty_note and all(f.name.lower() == "readme.md" for f in files):
            empty_note, frozen = None, False
        if empty_note and frozen:
            ok = False
            mark = "✗"
        elif ok and empty_note:
            mark = "⚠"
        for f in files:
            counts[mark] += 1
        all_ok = all_ok and ok
        names = ", ".join(str(f.relative_to(docs)) for f in files)
        report.append(f"{mark} {names} ← {src.name}")
        if empty_note:
            report.append(f"   {empty_note}")
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
    # прямо в корне; --docs = корень). Признак второй — сам docs является
    # корнем git-репозитория (.git внутри; у worktree это файл). Прежний
    # признак «srs/ или brd/ внутри docs» был ложным: в стендовой
    # топологии docs/srs — норма, и прибор молча мерил сам комплект, а
    # на свежей миграции (srs/ ещё нет) — корень репозитория; отсюда
    # ✗ на prompts/ у первого исполнителя v2.x (2026-09-11).
    # С «--docs .» docs.parent == docs («.».parent == «.») — тот же случай.
    _docs_r = docs.resolve()
    if (_docs_r / ".git").exists() or _docs_r.parent == _docs_r:
        root = _docs_r                      # комплект = корень репозитория
    elif (_docs_r.parent / ".git").exists():
        root = _docs_r.parent               # стендовая: <root>/docs
    elif (docs / "srs").is_dir() or (docs / "brd").is_dir():
        root = _docs_r                      # вне git (тесты): прежний признак
    else:
        root = _docs_r.parent
    # prompts/ — промпты этапов планировщика (протокол §10, инструкции
    # треков): штатный артефакт репозитория источника, не мусор
    # (инцидент 2026-09-11: первый исполнитель по плану v2.x получил
    # ✗ на PRE-01 из-за prompts/ и встал на вопрос владельцу).
    _ok_dirs = {"docs", "sources", "sandbox", "prompts", ".git", "brd", "srs",
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
            "(docs/sources/sandbox/prompts) и markdown; рабочие скрипты и кэши "
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
    # слот части сервиса в ID (2026-09-28): таблица кодов в README комплекта
    rep, ok = _safe(check_id_slots, docs, card_ids)
    all_ok = all_ok and ok
    if rep:
        report.append(("✓" if ok else "✗") + " слот части сервиса в ID:")
        report.extend(f"   {ln}" for ln in rep)
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
    # сторож каталога сервисов (2026-09-29): ⚠-сигналы, вердикт не
    # трогают; без каталога (dev-копия вне канона, без --catalog) молчит
    cat_rep, _ = _safe(check_service_catalog,
                       catalog if catalog is not None
                       else canon_catalog_path(), docs)
    report.extend(cat_rep)
    # контракты OpenAPI/AsyncAPI — в репозитории кода (2026-10-06):
    # каталог api/ и YAML в комплекте — ⚠ до удаления владельцем;
    # ссылки матрицы «API ↔ SRS» — через HEAD, явный ref по правилу
    na_rep, _ = _safe(check_no_api_in_bundle, docs)
    report.extend(na_rep)
    ar_rep, ar_ok = _safe(check_api_matrix_refs, docs, strict)
    all_ok = all_ok and ar_ok
    report.extend(ar_rep)
    # детектор похожих точек применения групп (П-5e): i-сигналы,
    # вердикт не трогают — решение о консолидации только человеческое
    sg_rep, _ = _safe(lambda: (check_similar_group_points(docs), True))
    report.extend(sg_rep)
    # голые атрибутные обращения к сущностям реестра (2026-08-29):
    # ⚠-сигналы, вердикт не трогают
    bm_rep, _ = _safe(lambda: (check_bare_entity_mentions(docs), True))
    report.extend(bm_rep)
    # ссылки-названия на сущности без более ранней полной ссылки с ID
    # (2026-10-02): ⚠-сигналы, вердикт не трогают
    ne_rep, _ = _safe(lambda: (check_named_entity_links(docs), True))
    report.extend(ne_rep)
    # согласованность контура групп контролей (полигон 2026-08-29):
    # ⚠-сигналы, вердикт не трогают — решения о контуре человеческие
    gc_rep, _ = _safe(lambda: (check_group_contours(docs), True))
    report.extend(gc_rep)
    # сторож не-markdown артефактов files/ (сироты и битые ссылки —
    # брак: потеря приложения молчаливая)
    fa_rep, fa_ok = _safe(check_file_artifacts, docs)
    all_ok = all_ok and fa_ok
    report.extend(fa_rep)
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
    "contract-call", "internal-contract", "lib-contract", "print-form", "notification",
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


def _stand_root(sources: Path) -> Path:
    """Корень стенда/репозитория источника по каталогу выгрузки.

    Две топологии: пилотный стенд ``<root>/confluence`` и репозиторий
    источника линии 2.x ``<src>/sources/confluence`` (track-manual,
    гид «Файлы репозитория»). Прежний признак «родитель выгрузки» на
    второй топологии давал ``<src>/sources``: гейт требовал журнал
    ``sources/sandbox/journal.txt``, искал профиль в ``sources/README.md``
    и молча пропускал сверку среза канона — первый исполнитель v2.x
    (PRE-01, 2026-09-11) создал ``sources/sandbox/`` по подсказке
    прибора, координатор велел удалить, круг замкнулся (FB-03; класс
    тот же, что FB-01 — прибор молчаливо предполагает топологию пилота).
    Признак: родитель ``sources`` без собственного ``.git`` — контейнер
    выгрузок, корень выше на уровень; иначе — родитель (пилот, тесты).
    """
    s = sources.resolve()
    parent = s.parent
    if parent.name == "sources" and not (parent / ".git").exists():
        return parent.parent
    return parent


def _profile_path(sources: Path) -> Tuple[Path, Path]:
    """(корень, профиль источников): ``<root>/README.md``; фолбэк —
    README внутри выгрузки (корень = выгрузка), прежнее поведение."""
    root = _stand_root(sources)
    profile = root / "README.md"
    if not profile.is_file():
        profile = sources / "README.md"
        root = sources
    return root, profile


def check_subservice_mapping(docs: Path, sources: Path,
                             card_files: Dict[str, Path]):
    """(отчёт, ok). card_files: page_id -> карточка docs. Зона источника
    определяется по титулу/ветви его файла выгрузки; путь карточки
    обязан начинаться srs/<слаг>/ (подсервис/core), не иметь слага
    (общая часть) или карточки не должно быть вовсе (вне Экосистемы)."""
    _, profile = _profile_path(sources)
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


# --- сторож слота части сервиса в ID (2026-09-28) ---
#
# Сервис из подсервисов (conventions §3.1, схема ID «Слот части сервиса»):
# идентификатор нумерованного артефакта несёт слот части сразу после
# префикса — `FUN-DS-SYS-01`, `ENT-SHR-001`, `NTF-DS-000`. Коды частей
# объявляются один раз таблицей в README корня комплекта (колонки «Код»
# и «Каталог»); общая часть — каталог `srs/shared/`, код `SHR`. Сторож
# держит три инварианта механически: слот только у сервиса с таблицей;
# слот карточки в `srs/<каталог>/…` равен коду этого каталога по
# таблице; документ вне каталогов подсервисов (уровень сервиса, корень
# `srs/`) слота не несёт. Без таблицы и без каталогов подсервисов сторож
# молчит — обычные сервисы не затронуты. Прецедент: docs-sign (слот в
# каждом ID, таблица кодов в README) против §3.1 «подсервис в ID не
# кодируется» — решение владельца 2026-09-28 в пользу объявляемого слота.

_PART_TABLE_HEAD_RE = re.compile(
    r"^#+\s*.*(?:слот|подсервис|част[иь] сервиса|коды частей).*$", re.I | re.M)
_PART_CODE_RE = re.compile(r"^[A-Z]{2,4}$")
# контуры и служебные сегменты ID — не слоты частей
_NOT_SLOT = {"CL", "BNK", "SYS", "GRP", "EXT", "INT"}
# каталоги типов в старой (множественной) раскладке — не подсервисы
_LEGACY_TYPE_DIRS = {"functions", "screen-forms", "controls", "print-forms",
                     "contract-calls", "internal-contracts", "lib-contracts",
                     "external-integrations", "processes"}


def _load_part_codes(readme: Path):
    """{код: каталог} по таблице кодов частей в README корня комплекта.
    None — таблицы нет; {} — таблица есть, но без колонки «Каталог»."""
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _PART_TABLE_HEAD_RE.search(text)
    if not m:
        return None
    header: Optional[List[str]] = None
    codes: Dict[str, str] = {}
    for ln in text[m.end():].splitlines():
        st = ln.strip()
        if st.startswith("#"):
            break
        if not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        try:
            icode = next(i for i, h in enumerate(header) if "код" in h)
        except StopIteration:
            return None
        idir = next((i for i, h in enumerate(header) if "каталог" in h), None)
        if idir is None:
            return {}
        if len(cells) <= max(icode, idir):
            continue
        code = cells[icode].strip("*` ")
        folder = cells[idir].strip("*` /")
        if _PART_CODE_RE.fullmatch(code) and folder:
            codes[code] = folder
    if header is None:
        return None
    return codes


def check_id_slots(docs: Path, card_ids: Dict[Path, str]):
    """(отчёт, ok). card_ids: карточка docs -> id из frontmatter."""
    report: List[str] = []
    ok = True

    def seg_of(p: Path) -> Optional[str]:
        parts = p.relative_to(docs).as_posix().split("/")
        if (len(parts) > 2 and parts[0] == "srs"
                and parts[1] not in _KNOWN_TYPES
                and parts[1] not in _LEGACY_TYPE_DIRS):
            return parts[1]
        return None

    def slot_like(cid: str) -> Optional[str]:
        tokens = cid.split("-")
        if len(tokens) >= 3 and _PART_CODE_RE.fullmatch(tokens[1])                 and tokens[1] not in _NOT_SLOT:
            return tokens[1]
        return None

    codes = _load_part_codes(docs / "README.md")
    if codes is None:
        # без таблицы сторож молчит, кроме явного признака слота: карточка в
        # каталоге подсервиса с id вида <PREFIX>-<КОД>-… (обычные сервисы и
        # старая раскладка с каталогами типов во множественном числе не задеты)
        hits = sorted((p.relative_to(docs).as_posix(), cid)
                      for p, cid in card_ids.items()
                      if seg_of(p) and slot_like(cid))
        if hits:
            ok = False
            report.append(
                "✗ слот части: идентификаторы со слотом части без таблицы "
                "кодов частей в README корня комплекта (колонки «Код», "
                "«Каталог»; conventions §3.1): "
                + ", ".join(f"{rel} ({cid})" for rel, cid in hits[:5])
                + (" …" if len(hits) > 5 else ""))
        return report, ok
    if not codes:
        ok = False
        report.append(
            "✗ слот части: в таблице кодов частей README нет колонки "
            "«Каталог» — соответствие «слот ↔ каталог» непроверяемо "
            "(conventions §3.1)")
        return report, ok
    dir2code = {folder: code for code, folder in codes.items()}
    for p, cid in sorted(card_ids.items()):
        rel = p.relative_to(docs).as_posix()
        seg = seg_of(p)
        tokens = cid.split("-")
        slot = tokens[1] if len(tokens) >= 3 and tokens[1] in codes else None
        if seg is None:
            if slot is not None:
                ok = False
                report.append(
                    f"✗ слот части: {rel} — id {cid} несёт слот «{slot}», "
                    "а документ лежит вне каталогов подсервисов (уровень "
                    "сервиса / корень srs/ слота не несут)")
            continue
        expected = dir2code.get(seg)
        if expected is None:
            ok = False
            report.append(
                f"✗ слот части: {rel} — каталог «{seg}» не объявлен в "
                "таблице кодов частей README")
        elif slot != expected:
            ok = False
            report.append(
                f"✗ слот части: {rel} — id {cid} "
                + (f"несёт слот «{slot}»" if slot else "без слота")
                + f", каталог «{seg}» объявлен с кодом «{expected}»")
    if not report:
        report.append(f"слоты частей: {len(codes)} кодов по таблице README, "
                      "соответствие «слот ↔ каталог» выдержано ✓")
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
    _, profile = _profile_path(sources)
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


# --- сторож каталога сервисов (2026-09-29) ---
# Каталог `_meta/services.json` — единственный дом адресации чужих
# сервисов (документ cross-service-addressing): по `code` ищут запись,
# по `repo` строят абсолютные ссылки на чужие комплекты. За один день
# 29.09 каталог правили три команды: поле repo в формате
# `…/-/tree/master/…?ref_type=heads` вместо `/-/tree/HEAD/…`,
# переименование кода (ломает `service:` во frontmatter комплекта и
# чужие ссылки), давний дубль кода EPR у двух записей. Прибор каталог не
# читал вовсе. Сторож: целостность каталога — ⚠-строки уровня отчёта
# (вердикт команды не трогают: каталог чинит владелец канона, а не
# команда, но сигнал виден в каждом отчёте); код документируемого
# сервиса (`service:` во frontmatter) не найден в каталоге — тоже ⚠
# (решение о переводе в ✗ — после приведения frontmatter пилота КК к
# коду каталога). Без каталога (dev-копия selfcheck вне канона и без
# --catalog) сторож молчит.

_REPO_HOST = "https://gitlab.gboteam.ru/"
_REPO_TREE_RE = re.compile(r"/-/(tree|blob|raw)/([^/?#]+)")


def canon_catalog_path() -> Optional[Path]:
    """`_meta/services.json` канона, из которого запущен selfcheck;
    None — dev-копия вне канона."""
    tool_dir = Path(__file__).resolve().parent
    if tool_dir.name != "tools" or tool_dir.parent.name != "_meta":
        return None
    cat = tool_dir.parent / "services.json"
    return cat if cat.is_file() else None


# адрес каталога контрактов чужого сервиса по коду (документ адресации
# §5.2): код сервиса = имя репозитория кода без префикса ms-
_API_SPEC_RULE = ("https://gitlab.gboteam.ru/ECO_BE/ms-{code}"
                  "/-/tree/HEAD/api-specification")


def check_no_api_in_bundle(docs: Path) -> Tuple[List[str], bool]:
    """Контракты OpenAPI/AsyncAPI живут в api-specification/ репозитория
    кода (решение 2026-10-06): каталог `api/` и YAML-контракты в
    комплекте — унаследованное состояние, ⚠ до удаления владельцем;
    вердикт не трогает (docs-sign, docs-file-storage на момент решения
    такие каталоги несли)."""
    lines: List[str] = []
    dirs = sorted(p for p in docs.rglob("api") if p.is_dir())
    for d in dirs:
        n = sum(1 for f in d.rglob("*") if f.is_file())
        lines.append(f"⚠ контракты в комплекте: каталог "
                     f"{d.relative_to(docs).as_posix()}/ ({n} файлов) — "
                     "контракты OpenAPI/AsyncAPI живут в api-specification/ "
                     "репозитория кода, в комплекте каталог api/ не "
                     "создаётся (унаследованное состояние: убрать при "
                     "ближайшей правке)")
    yamls = []
    for f in sorted(docs.rglob("*.y*ml")):
        if f.suffix.lower() not in (".yaml", ".yml"):
            continue
        if any(p.name == "api" for p in f.relative_to(docs).parents):
            continue  # уже учтён каталогом
        try:
            head = f.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if re.search(r"^(openapi|asyncapi):", head, re.M):
            yamls.append(f.relative_to(docs).as_posix())
    if yamls:
        lines.append(f"⚠ контракты в комплекте: YAML OpenAPI/AsyncAPI ×"
                     f"{len(yamls)} ({', '.join(yamls[:3])}"
                     f"{'…' if len(yamls) > 3 else ''}) — копий контрактов "
                     "в комплекте нет, единственная копия — "
                     "api-specification/ репозитория кода")
    return lines, True


_DEFAULT_BRANCHES = {"master", "main", "trunk", "develop"}
_API_SECTION_RE = re.compile(r"^#{1,3}\s+(?:\d+\.\s*)?Покрытие:\s*API\s*↔\s*SRS",
                             re.M)
_LINK_REF_RE = re.compile(r"https?://[^\s)]+?/-/(?:blob|tree|raw)/([^/\s)]+)/")


def check_api_matrix_refs(docs: Path, strict: bool = False
                          ) -> Tuple[List[str], bool]:
    """Ссылки раздела матрицы «Покрытие: API ↔ SRS» ведут в репозиторий
    кода через HEAD (решение 2026-10-06, вариант В по вопросу 1):
    явный ref допустим, только если комплект описывает не основную
    линию кода — тогда ref назван в шапке раздела (между заголовком и
    таблицей, в обратных кавычках) с причиной, и ссылки с ним ✓. Иной
    явный ref — ⚠; имя ветки по умолчанию (master/main/trunk/develop)
    — ✗ в строгом профиле, ⚠ в командном."""
    matrix = docs / "traceability-matrix.md"
    if not matrix.is_file():
        return [], True
    text = matrix.read_text(encoding="utf-8", errors="replace")
    m = _API_SECTION_RE.search(text)
    if not m:
        return [], True
    level = len(m.group(0)) - len(m.group(0).lstrip("#"))
    rest = text[m.end():]
    # раздел тянется до следующего заголовка того же или верхнего уровня
    # (подразделы «### 3.1. REST …» — внутри; docs-sign)
    nxt = re.search(r"^#{1,%d}\s" % level, rest, re.M)
    section = rest[:nxt.start()] if nxt else rest
    first_row = re.search(r"^\|", section, re.M)
    header = section[:first_row.start()] if first_row else section
    used = _LINK_REF_RE.findall(section)
    # объявленный ref — токен в обратных кавычках шапки, который реально
    # стоит в ссылках раздела (прочие кавычки шапки — пути, ID — не ref)
    declared = set(re.findall(r"`([^`\s]+)`", header)) & set(used)
    lines: List[str] = []
    ok = True
    refs: Dict[str, int] = {}
    for ref in used:
        if ref == "HEAD" or ref in declared:
            continue
        refs[ref] = refs.get(ref, 0) + 1
    for ref, n in sorted(refs.items()):
        if ref in _DEFAULT_BRANCHES:
            mark = "✗" if strict else "⚠"
            ok = ok and not strict
            lines.append(f"{mark} матрица «API ↔ SRS»: ссылки с именем ветки "
                         f"по умолчанию `{ref}` ×{n} — вместо него HEAD "
                         "(адрес переживает переименование ветки)")
        else:
            lines.append(f"⚠ матрица «API ↔ SRS»: ссылки с явным ref "
                         f"`{ref}` ×{n} — допустимо только для комплекта "
                         "не основной линии кода: назвать ref в шапке "
                         "раздела с причиной (conventions §5.3 п. 7)")
    if declared:
        lines.append("i матрица «API ↔ SRS»: в шапке раздела назван ref "
                     f"{', '.join(sorted(declared))} — ссылки с ним приняты")
    return lines, ok


def _repo_format_issue(url: str) -> Optional[str]:
    """Отклонение адреса `repo` от правила адресации; None — норма."""
    if not url.startswith(_REPO_HOST):
        return f"адрес не в GitLab контура ({_REPO_HOST})"
    if "?" in url or "#" in url:
        return "хвост запроса/якоря (например `?ref_type=heads`) — " \
               "адрес должен оканчиваться путём"
    m = _REPO_TREE_RE.search(url)
    if m and m.group(1) != "tree":
        return f"сегмент `/-/{m.group(1)}/` — корень комплекта " \
               "адресуется через `/-/tree/HEAD/<путь>`"
    if m and m.group(2) != "HEAD":
        return f"имя ветки `{m.group(2)}` в адресе — вместо него `HEAD`" \
               " (адрес переживает переименование ветки)"
    return None


def _service_codes(docs: Path) -> Dict[str, int]:
    """Коды `service:` из frontmatter карточек комплекта → число файлов."""
    codes: Dict[str, int] = {}
    for f in sorted(docs.rglob("*.md")):
        fm = read_frontmatter(f) or {}
        code = fm.get("service", "").strip().strip("'\"")
        if code:
            codes[code] = codes.get(code, 0) + 1
    return codes


def check_service_catalog(catalog: Optional[Path],
                          docs: Path) -> Tuple[List[str], bool]:
    """Целостность каталога сервисов и наличие в нём кода комплекта.
    Все сигналы — ⚠ (вердикт не трогают); ok всегда True."""
    if catalog is None:
        return [], True
    import json
    try:
        data = json.loads(catalog.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return [f"⚠ каталог сервисов: {catalog.name} не читается "
                f"({e.__class__.__name__}: {e}) — адресация чужих "
                "сервисов по каталогу невозможна"], True
    items = data if isinstance(data, list) else data.get("services")
    if not isinstance(items, list):
        return [f"⚠ каталог сервисов: {catalog.name} — ожидался список "
                "записей"], True
    lines: List[str] = []
    by_code: Dict[str, List[str]] = {}
    by_key: Dict[str, List[str]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip() or "<без имени>"
        code = str(it.get("code", "")).strip()
        key = str(it.get("key", "")).strip()
        if code:
            by_code.setdefault(code, []).append(name)
        if key:
            by_key.setdefault(key, []).append(name)
        repo = it.get("repo")
        if isinstance(repo, str) and repo.strip():
            issue = _repo_format_issue(repo.strip())
            if issue:
                lines.append(f"⚠ каталог сервисов: repo у `{code or name}` — "
                             f"{issue}: {repo.strip()}")
        # поле api — адрес каталога контрактов ТОЛЬКО для исключений из
        # правила «ECO_BE/ms-<code>/-/tree/HEAD/api-specification»
        # (документ адресации §5.2, решение 2026-10-06); форма та же,
        # что у repo
        api = it.get("api")
        if isinstance(api, str) and api.strip():
            issue = _repo_format_issue(api.strip())
            if issue:
                lines.append(f"⚠ каталог сервисов: api у `{code or name}` — "
                             f"{issue}: {api.strip()}")
            elif api.strip() == _API_SPEC_RULE.format(code=code):
                lines.append(f"⚠ каталог сервисов: api у `{code}` совпадает "
                             "с адресом по правилу — поле для исключений, "
                             "здесь лишнее")
    for code, names in sorted(by_code.items()):
        if len(names) > 1:
            lines.append(f"⚠ каталог сервисов: код `{code}` у {len(names)} "
                         f"записей ({'; '.join(names)}) — по коду нельзя "
                         "однозначно найти сервис")
    for key, names in sorted(by_key.items()):
        if len(names) > 1:
            lines.append(f"⚠ каталог сервисов: ключ `{key}` у {len(names)} "
                         f"записей ({'; '.join(names)})")
    for code, n in sorted(_service_codes(docs).items()):
        if code in by_code:
            entry = next((it for it in items if isinstance(it, dict)
                          and str(it.get("code", "")).strip() == code), {})
            repo = str(entry.get("repo", "")).strip()
            lines.append(f"✓ каталог сервисов: код `{code}` ({n} файлов) — "
                         f"запись найдена" + (f", repo {repo}" if repo
                                              else ", поле repo не заполнено"))
        else:
            lines.append(f"⚠ каталог сервисов: код `{code}` из frontmatter "
                         f"{n} файлов не найден в каталоге — по коду ищут "
                         "запись сервиса при адресации; привести `service:` "
                         "к коду каталога или завести запись")
    return lines, True


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
    root, profile = _profile_path(sources)
    try:
        ptext = profile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    if not _CANON_CUT_RE.search(ptext):
        return [], True
    report: List[str] = []
    ok = True
    # §5: нормализация только на КОПИЯХ в sandbox/normalized —
    # sidecar рядом с источниками = нормализатор гоняли по выгрузке
    # (STS-01 2026-08-31: два *.tables.md легли в confluence/,
    # копий в sandbox не было вовсе)
    stray = sorted(sources.rglob("*.tables.md"))
    if stray:
        ok = False
        for s in stray[:5]:
            report.append(
                f"✗ протокол §5: sidecar в выгрузке — {s.relative_to(root)}"
                " (нормализация только на копиях в sandbox/normalized; "
                "файл удалить, прогон нормализатора повторить по копии)")
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
    root, profile = _profile_path(sources)
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
    expected = _stand_root(sources) / "sandbox" / "journal.txt"
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
# формат с колонкой «Контур» (полигон 2026-08-29): | ID | FE/BE | Привязка |
_GRP_ROW_C_RE = re.compile(
    r"^\|\s*\[?(CTL-GRP-\d+)\]?[^|]*\|\s*(FE|BE)\s*\|\s*([^|]+)")
_QUOTE_TOKEN_RE = re.compile(r"«([^»]{3,60})»|`([A-Za-z_]{3,30})`")

_UI_MARK_RE = re.compile(
    r"кнопк|нажат|\bэф\b|экранн|вкладк|дровер|фокус", re.I)
_ST_MARK_RE = re.compile(r"статус|переход", re.I)
_OP_MARK_RE = re.compile(r"при выполнении|функц", re.I)


_ART_LINK_RE = re.compile(r"\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")


def check_file_artifacts(docs: Path) -> Tuple[List[str], bool]:
    """Сторож не-markdown артефактов комплекта (files/): приложение
    источника (XSD/JSON-схема и т.п.) живёт в подкаталоге files/ рядом
    с карточкой-владельцем, и карточка ОБЯЗАНА на него ссылаться.
    Файл в files/ без входящей ссылки — «сирота» (✗): артефакт, о
    котором комплект молчит. Ссылка карточки в files/ на несуществующий
    файл — тоже ✗ (потеря артефакта). Каталоги img/ — вне сторожа:
    перенос картинок — отдельная существующая конвенция."""
    arts = {p.resolve() for p in docs.rglob("*")
            if p.is_file() and "files" in p.relative_to(docs).parts
            and "img" not in p.relative_to(docs).parts}
    linked: set = set()
    broken: List[Tuple[str, str]] = []
    for md in sorted(docs.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _ART_LINK_RE.finditer(text):
            tgt = unquote(m.group(1)).split("#", 1)[0]
            if not tgt or "://" in tgt or tgt.startswith("mailto:"):
                continue
            norm_t = tgt.replace("\\", "/")
            if "files/" not in norm_t and not norm_t.startswith("files/"):
                continue
            try:
                rp = (md.parent / Path(norm_t)).resolve()
            except OSError:
                continue
            if rp.is_file():
                linked.add(rp)
            else:
                broken.append((md.relative_to(docs).as_posix(), tgt))
    rep: List[str] = []
    ok = True
    for a in sorted(arts - linked):
        ok = False
        rep.append("✗ файл-артефакт без ссылающейся карточки (сирота "
                   "files/): "
                   + Path(a).relative_to(docs.resolve()).as_posix()
                   + " — артефакт, о котором комплект молчит")
    for rel, tgt in broken:
        ok = False
        rep.append(f"✗ битая ссылка на files-артефакт: {rel} → {tgt} "
                   "(файла нет — потеря артефакта)")
    return rep, ok


def check_group_contours(docs: Path) -> List[str]:
    """Согласованность контура групп контролей (решение владельца
    2026-08-29): контур — явная колонка FE/BE реестра групп, сторож
    сверяет её с формулировкой привязки. FE привязывается к UI-событию;
    BE — к переходу статусной модели или серверной операции, БЕЗ
    UI-мест (сервер не знает, откуда пришёл запрос, — API First;
    перечни триггеров заведомо неполны). Неоднозначность не угадывается
    — ⚠-вопрос аналитику (асимметрия). Реестр без колонки «Контур» —
    один ⚠ на файл (разметить при перегонке)."""
    report: List[str] = []
    for readme in sorted(docs.rglob("control/README.md")):
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = readme.relative_to(docs)
        has_rows = any(_GRP_ROW_RE.match(ln.strip())
                       for ln in text.splitlines())
        if not has_rows:
            continue
        header_ok = re.search(r"^\|\s*ID\s*\|\s*Контур\s*\|", text, re.M)
        if not header_ok:
            report.append(
                f"⚠ {rel}: реестр групп без колонки «Контур» (FE/BE) — "
                "разметить при перегонке групп (шаблон controls §2, "
                "решение 2026-08-29)")
            continue
        for ln in text.splitlines():
            m = _GRP_ROW_C_RE.match(ln.strip())
            if not m:
                continue
            gid, contour, bind = m.group(1), m.group(2), m.group(3)
            ui = bool(_UI_MARK_RE.search(bind))
            st = bool(_ST_MARK_RE.search(bind))
            op = bool(_OP_MARK_RE.search(bind))
            if contour == "FE":
                if st:
                    report.append(
                        f"⚠ {rel}: {gid} (FE) — привязка содержит "
                        "статусные маркеры: контур/привязка ошибочны "
                        "либо событие двух контуров — расщепить на "
                        "FE- и BE-группы")
                elif not ui:
                    report.append(
                        f"⚠ {rel}: {gid} (FE) — привязка не называет "
                        "UI-событие; контур неопределим по формулировке "
                        "— вопрос аналитику")
            else:
                if ui:
                    report.append(
                        f"⚠ {rel}: {gid} (BE) — привязка содержит "
                        "UI-маркеры: сервер не знает мест инициирования "
                        "(API First) — убрать UI-места либо пересмотреть "
                        "контур")
                elif not (st or op):
                    report.append(
                        f"⚠ {rel}: {gid} (BE) — привязка не называет ни "
                        "переход статуса, ни серверную операцию — "
                        "неопределима, вопрос аналитику")
    return report


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


# --- сторож ссылок-названий на сущности (решение владельца 2026-10-02) ---
# Конвенции §5: первое упоминание сущности в документе — полная ссылка
# `[ENT-NNN <название>](…)`; повторное в прозе — короткой ссылкой
# `[ENT-NNN](…)` ЛИБО ссылкой с названием без ID
# `[Заявке на выпуск карты](…/ent-016-….md)` (читаемость прозы; текст
# ссылки свободный — слова в падеже предложения, совпадение с названием
# не требуется и не проверяется: морфологии в приборе нет). Обращения к
# атрибутам, формулы и таблицы связей — по-прежнему короткой ссылкой.
# Инвариант, который держит сторож: у ссылки-названия в ТОМ ЖЕ документе
# есть полная ссылка с ID на ту же цель, и она стоит раньше — иначе
# идентификатор сущности в видимом тексте документа не встречается ни
# разу. ID сущности берётся из имени файла цели (`ent-016-…`,
# `ent-shr-012-…`), поэтому правило действует только для ENT: у EXT цель
# общая (`dictionaries.md`), ID в адресе нет — там повторное упоминание
# только с ID. Документ со старой формой (одни короткие ссылки) сторож
# не трогает. Дословное наименование источника С ТЕГОМ сервиса
# (`[[КК_ВК] Заявка на выпуск карты](…)`) считается полноценным
# упоминанием наравне с полной ссылкой: тег с названием однозначно
# определяет сущность, а дословность reverse-переноса запрещает
# вставлять в текст источника ID (живой прогон 2026-10-02: на стенде
# КК ~540 таких ссылок в 65 принятых документах — первая редакция
# сторожа флаговала их все). ⚠-сигнал, вердикт не меняет —
# оформление ссылок, как у сторожа голых обращений.

_MD_LINK_RE = re.compile(
    r"\[((?:[^\[\]\n]|\[[^\[\]\n]*\])+)\]"       # текст, один уровень [..]
    r"\(\s*([^)\s]+)(?:\s+\"[^\"\n]*\")?\s*\)")       # адрес и подсказка
_ENT_FILE_RE = re.compile(r"^(ent(?:-[a-z]{1,4})?-\d+(?:\.\d+)?)[-.]", re.I)
_NAMED_LINK_SKIP = {"readme.md", "dictionaries.md"} | _SERVICE_FILES
# тег сервиса в начале текста ссылки, экранированный или нет:
# `\[КК_ВК\] Название` / `[КК_ВК] Название`
_TAGGED_NAME_RE = re.compile(r"^\\?\[[^\[\]\\\n]{2,14}\\?\]\s*\S")


def check_named_entity_links(docs: Path) -> List[str]:
    """Ссылки на сущности ENT названием без ID: в документе должна быть
    более ранняя полная ссылка `[ENT-NNN <название>]` на ту же цель либо
    ссылка с дословным наименованием источника с тегом сервиса."""
    report: List[str] = []
    for p in sorted(docs.rglob("*.md")):
        if p.name.lower() in _NAMED_LINK_SKIP:
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        body = re.sub(r"```.*?```", " ", body, flags=re.S)   # примеры кода
        first_full: Dict[str, int] = {}
        named: Dict[str, List[int]] = {}
        for m in _MD_LINK_RE.finditer(body):
            text, target = m.group(1).strip(), m.group(2)
            fname = unquote(target.split("#", 1)[0]).replace("\\", "/")
            fname = fname.rsplit("/", 1)[-1]
            fm = _ENT_FILE_RE.match(fname)
            if not fm or fname.lower() == p.name.lower():
                continue
            ent_id = fm.group(1).upper()
            if text.lower().endswith(".md"):       # ссылка именем файла
                continue
            if re.search(rf"(?<![\w-]){re.escape(ent_id)}(?![\w-])", text):
                rest = re.sub(re.escape(ent_id), "", text)
                if len(re.sub(r"[\W_]+", "", rest)) >= 3:
                    first_full.setdefault(ent_id, m.start())
            elif _TAGGED_NAME_RE.match(text):
                # дословное имя источника с тегом — полноценное упоминание
                first_full.setdefault(ent_id, m.start())
            else:
                named.setdefault(ent_id, []).append(m.start())
        rel = p.relative_to(docs)
        for ent_id, poss in sorted(named.items()):
            if ent_id not in first_full:
                report.append(
                    f"⚠ {rel}: ссылка на {ent_id} названием без ID "
                    f"×{len(poss)}, а полной ссылки `[{ent_id} <название>]` "
                    "(или дословного наименования источника с тегом) в "
                    "документе нет — первое упоминание сущности "
                    "оформляется полной ссылкой с ID")
            elif poss[0] < first_full[ent_id]:
                report.append(
                    f"⚠ {rel}: ссылка на {ent_id} названием без ID стоит "
                    f"раньше полной ссылки `[{ent_id} <название>]` — "
                    "полная ссылка с ID ставится при первом упоминании")
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
            # формат с колонкой «Контур»: описание привязки — третья
            # колонка; без неё — вторая (старый формат)
            mc = _GRP_ROW_C_RE.match(ln.strip())
            m = mc or _GRP_ROW_RE.match(ln.strip())
            if not m:
                continue
            gid = m.group(1)
            desc = (m.group(3) if mc else m.group(2)).strip()
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
           f"✗ было {n_base} → стало {n_cur}",
           # замечание координатора КК 2026-10-05: «дельта на единицу
           # больше ИТОГО» читалась дефектом прибора
           "   (в счёт дельты входят и ✗ сторожей уровня комплекта — "
           "долги ссылок, срез канона, реестр матрицы и подобные, — "
           "поэтому число может быть больше ✗ в ИТОГО, где считаются "
           "только файлы)"]
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
    ap.add_argument("--catalog", type=Path, default=None,
                    help="каталог сервисов services.json для сторожа "
                         "каталога; по умолчанию — _meta/services.json "
                         "канона, из которого запущен selfcheck")
    ap.add_argument("--journal", type=Path, default=None,
                    help="дописать строку «таймстемп | ИТОГО…» в файл "
                         "журнала (хронометраж этапов дозахода: время "
                         "штампует прибор, не исполнитель — у LLM нет "
                         "часов, самодельные таймстемпы фабрикуются)")
    args = ap.parse_args()
    report, ok = run(args.docs, args.sources, strict=args.strict,
                     catalog=args.catalog)
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
