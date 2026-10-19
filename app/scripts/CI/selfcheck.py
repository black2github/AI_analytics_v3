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
from dataclasses import dataclass
import json
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
try:
    from kitcheck import fs as _fs  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck import fs as _fs  # type: ignore  # noqa: E402
try:
    from kitcheck.md import (  # noqa: E402,F401 — примитивы markdown (этап 1б); имена
        _MD_LINK_RE, _PID_RE, _anchors_of, _kit_md,  # сохраняются в selfcheck для
        gitlab_slug, in_dot_dir, is_task_file,  # утилит и тестов, которые зовут их
        page_ids, read_frontmatter, table_cells, is_fence, FENCE_BOTH,  # как selfcheck.*
        FENCE_BACKTICK, frontmatter_end, frontmatter_split)
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.md import (  # type: ignore  # noqa: E402,F401
        _MD_LINK_RE, _PID_RE, _anchors_of, _kit_md,
        gitlab_slug, in_dot_dir, is_task_file,
        page_ids, read_frontmatter, table_cells, is_fence, FENCE_BOTH,
        FENCE_BACKTICK, frontmatter_end, frontmatter_split)
try:
    from kitcheck.core import Check, is_soft_signal, run_checks  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.core import Check, is_soft_signal, run_checks  # type: ignore  # noqa: E402
try:
    from kitcheck.checks._common import (  # noqa: E402,F401 — этап 3
        _KNOWN_TYPES, _PART_CODE_RE, _cell_plain, _load_service_table, domain_context)
    from kitcheck.checks.artifacts import (  # noqa: E402,F401 — этап 3
        _ART_LINK_RE, _BOM, _PRE_RE, _STRUCT_EXT, _TOKEN_RE, _parse_structured, _source_candidates, _struct_tokens, check_file_artifacts, check_structured_examples)
    from kitcheck.checks.catalog_api import (  # noqa: E402,F401 — этап 3
        _API_SECTION_RE, _API_SPEC_RULE, _DEFAULT_BRANCHES, _LINK_REF_RE, _REPO_HOST, _REPO_TREE_RE, _repo_format_issue, _service_codes, check_api_matrix_refs, check_no_api_in_bundle, check_service_catalog)
    from kitcheck.checks.content import (  # noqa: E402,F401 — этап 3
        _FM_BY_TYPE, _FM_COMMON, _GAP_MARK_RE, _GAP_QUOTED_RE, _H1_QUOTED_RE, _KNOWN_SECTIONS, _REQ_SECTIONS, _SECTION_ID_RE, _SILENT_FORMULA, _STUB_MARK, _h2_keys, _has_section, _norm_title, _section_key, _service_names, check_h1_service, check_required_sections, check_source_silent, check_title_uniqueness, format_frontmatter_schema, frontmatter_schema_issues)
    from kitcheck.checks.controls import (  # noqa: E402,F401 — этап 3
        _GRP_ROW_C_RE, _GRP_ROW_RE, _OP_MARK_RE, _QUOTE_TOKEN_RE, _ST_MARK_RE, _UI_MARK_RE, check_group_contours, check_similar_group_points)
    from kitcheck.checks.ids_domain import (  # noqa: E402,F401 — этап 3
        _FM_DESCRIBED, _LEGACY_TYPE_DIRS, _LEGEND_HEAD_RE, _LEGEND_TOKEN_RE, _NOT_SLOT, _PART_TABLE_HEAD_RE, _PREFIX_RE, _declared_prefixes, _legend_section, _load_part_codes, check_id_slots, check_readme_legend)
    from kitcheck.checks.links import (  # noqa: E402,F401 — этап 3
        _CALL_USAGE_RE, _CARD_ID_HEAD_RE, _ENT_FILE_RE, _NAMED_LINK_SKIP, _SERVICE_FILES, _STEP_CELL_RE, _STEP_HEAD_RE, _STEP_NUM_RE, _STEP_RANGE_RE, _TAGGED_NAME_RE, _link_targets, _step_literals, check_bare_entity_mentions, check_link_anchors_and_ids, check_named_entity_links, check_process_call_consistency, check_relative_links)
    from kitcheck.checks.matrix import (  # noqa: E402,F401 — этап 3
        _REGISTRY_HDR_RE, check_registry_duplicates)
    from kitcheck.checks.nfr import (  # noqa: E402,F401 — этап 3
        _NFR_CODES, _NFR_INGRESS, _NFR_ROW_RE, _NFR_TYPE_BY_CODE, _nfr_repo_root, check_nfr_catalog)
    from kitcheck.checks.source_profile import (  # noqa: E402,F401 — этап 3
        _CANON_CUT_RE, _PLAN_LINE_RE, _RETRY_RE, _SCRIPT_EXT, _SERVICE_ZONE_RE, _STAGE_ROW_RE, _ZONE_RE, _load_subservice_map, _profile_path, _stand_root, check_canon_cut, check_protocol_discipline, check_stage_prompts, check_subservice_mapping)
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.checks._common import (  # type: ignore  # noqa: E402,F401
        _KNOWN_TYPES, _PART_CODE_RE, _cell_plain, _load_service_table, domain_context)
    from .kitcheck.checks.artifacts import (  # type: ignore  # noqa: E402,F401
        _ART_LINK_RE, _BOM, _PRE_RE, _STRUCT_EXT, _TOKEN_RE, _parse_structured, _source_candidates, _struct_tokens, check_file_artifacts, check_structured_examples)
    from .kitcheck.checks.catalog_api import (  # type: ignore  # noqa: E402,F401
        _API_SECTION_RE, _API_SPEC_RULE, _DEFAULT_BRANCHES, _LINK_REF_RE, _REPO_HOST, _REPO_TREE_RE, _repo_format_issue, _service_codes, check_api_matrix_refs, check_no_api_in_bundle, check_service_catalog)
    from .kitcheck.checks.content import (  # type: ignore  # noqa: E402,F401
        _FM_BY_TYPE, _FM_COMMON, _GAP_MARK_RE, _GAP_QUOTED_RE, _H1_QUOTED_RE, _KNOWN_SECTIONS, _REQ_SECTIONS, _SECTION_ID_RE, _SILENT_FORMULA, _STUB_MARK, _h2_keys, _has_section, _norm_title, _section_key, _service_names, check_h1_service, check_required_sections, check_source_silent, check_title_uniqueness, format_frontmatter_schema, frontmatter_schema_issues)
    from .kitcheck.checks.controls import (  # type: ignore  # noqa: E402,F401
        _GRP_ROW_C_RE, _GRP_ROW_RE, _OP_MARK_RE, _QUOTE_TOKEN_RE, _ST_MARK_RE, _UI_MARK_RE, check_group_contours, check_similar_group_points)
    from .kitcheck.checks.ids_domain import (  # type: ignore  # noqa: E402,F401
        _FM_DESCRIBED, _LEGACY_TYPE_DIRS, _LEGEND_HEAD_RE, _LEGEND_TOKEN_RE, _NOT_SLOT, _PART_TABLE_HEAD_RE, _PREFIX_RE, _declared_prefixes, _legend_section, _load_part_codes, check_id_slots, check_readme_legend)
    from .kitcheck.checks.links import (  # type: ignore  # noqa: E402,F401
        _CALL_USAGE_RE, _CARD_ID_HEAD_RE, _ENT_FILE_RE, _NAMED_LINK_SKIP, _SERVICE_FILES, _STEP_CELL_RE, _STEP_HEAD_RE, _STEP_NUM_RE, _STEP_RANGE_RE, _TAGGED_NAME_RE, _link_targets, _step_literals, check_bare_entity_mentions, check_link_anchors_and_ids, check_named_entity_links, check_process_call_consistency, check_relative_links)
    from .kitcheck.checks.matrix import (  # type: ignore  # noqa: E402,F401
        _REGISTRY_HDR_RE, check_registry_duplicates)
    from .kitcheck.checks.nfr import (  # type: ignore  # noqa: E402,F401
        _NFR_CODES, _NFR_INGRESS, _NFR_ROW_RE, _NFR_TYPE_BY_CODE, _nfr_repo_root, check_nfr_catalog)
    from .kitcheck.checks.source_profile import (  # type: ignore  # noqa: E402,F401
        _CANON_CUT_RE, _PLAN_LINE_RE, _RETRY_RE, _SCRIPT_EXT, _SERVICE_ZONE_RE, _STAGE_ROW_RE, _ZONE_RE, _load_subservice_map, _profile_path, _stand_root, check_canon_cut, check_protocol_discipline, check_stage_prompts, check_subservice_mapping)


def index_sources(root: Path):
    """page_id -> файл выгрузки; дубли — списком (используется первый
    по сортировке, в отчёт — предупреждение)."""
    idx: Dict[str, Path] = {}
    dups: Dict[str, List[Path]] = {}
    for p in sorted(root.rglob("*.md")):
        # FB-21 КК (2026-10-14): --sources на родительский каталог
        # индексировал и sources/raw/ (нетронутый архив выгрузки) —
        # 615 дублей page_id; архив — не область сверки
        if "raw" in p.relative_to(root).parts[:-1]:
            continue
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
        text = _fs.read_text(src, encoding="utf-8", errors="replace")
    except OSError:
        return None, False
    fm_head, body = frontmatter_split(text)
    fm_text = fm_head or ""
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
         pardon_src: Optional[Path] = None,
         amnesty: Optional[List[Path]] = None) -> Tuple[List[str], bool]:
    return _safe(lambda: nt.run_check(files, src, docs_root=docs_root,
                                      soft_markers=soft_markers,
                                      pardon_source=pardon_src,
                                      amnesty_sources=amnesty))


def run(docs: Path, sources: Optional[Path],
        strict: bool = False,
        catalog: Optional[Path] = None) -> Tuple[List[str], bool]:
    """Прогон самопроверки комплекта: (строки отчёта, вердикт OK).

    Файлы комплекта и выгрузки читаются с диска один раз за прогон — через
    кэш `kitcheck.fs` (сессия на время прогона)."""
    with _fs.session():
        return _run_impl(docs, sources, strict, catalog)


def _run_impl(docs: Path, sources: Optional[Path],
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
        if any(d.is_dir() for d in sources.rglob("raw")):
            report.append("i выгрузка: каталоги raw/ (архив) при индексации "
                          "источников пропущены — область сверки sources/confluence")
        for pid, paths in sorted(dups.items()):
            report.append(f"i выгрузка: page_id {pid} у нескольких файлов "
                          f"({', '.join(p.name for p in paths[:3])}) — "
                          "используется первый по сортировке")

    # перепись файлов комплекта (правило 2: каждый — ровно одна категория)
    groups: Dict[str, List[Path]] = {}
    solo: List[Tuple[Path, str]] = []  # (файл, пометка)
    extra_pids: Dict[Path, int] = {}   # карточка -> число доп. page_ids
    extra_page_ids: Dict[Path, List[str]] = {}  # карточка -> доп. page_ids
    card_ids: Dict[Path, str] = {}     # карточка -> id из frontmatter
    card_titles: Dict[Path, Tuple[str, str, str]] = {}  # карточка -> (type, title, id)
    fm_schema_issues: List[Tuple[str, List[str], bool]] = []  # (файл, поля вне схемы, version)
    for p in sorted(docs.rglob("*.md")):
        rel = p.relative_to(docs)
        if in_dot_dir(p, docs):
            continue
        if is_task_file(p, docs):
            # строка-сигнал без счётчика: постановка — источник правок,
            # а не документ комплекта (молчаливых пропусков нет)
            report.append(f"i {rel}: постановка задачи (type: task) — "
                          "источник правок forward, вне сверки")
            continue
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
        bad_fields, has_version = frontmatter_schema_issues(fm)
        if bad_fields or has_version:
            fm_schema_issues.append((rel.as_posix() if hasattr(rel, "as_posix") else str(rel),
                                     bad_fields, has_version))
        if fm.get("id"):
            card_ids[p] = fm["id"]
            if fm.get("title") and fm.get("type"):
                card_titles[p] = (fm["type"], fm["title"], fm["id"])
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
            # ЗК-12 ОНБ-В: у карточек вызова первым ставили page_id страницы
            # владельца метода (вне выгрузки) — 9 постоянных ✗ обесценили гейт
            hint = (" (карточка вызова: первым — page_id страницы ЭТОГО сервиса, "
                    "где описан вызов; страница метода владельца — не источник, "
                    "её page_id — в open-questions/долге; шаблон contract-call.md)"
                    if "contract-call" in p.parts else "")
            report.append(f"✗ {rel}: источник page_id {pids[0]} НЕ НАЙДЕН "
                          "в выгрузке — reverse-карточка без сверки, брак" + hint)
        else:
            groups.setdefault(pids[0], []).append(p)
            extra_pids[p] = len(pids) - 1
            extra_page_ids[p] = list(pids[1:])
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
        # контракт начала строки — kitcheck.core.SOFT_SIGNAL_RE
        return [ln for ln in rep if is_soft_signal(ln)]

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
        # FB-19 КК: дословные абзацы дочерних страниц карточки — амнистия
        # длинных строк по всем её page_ids (файлы выгрузки доп. страниц)
        amnesty = [idx[x] for x in extra_page_ids.get(files[0], [])
                   if x in idx and idx[x] != src]
        rep, ok = _run(files, src, docs, soft_markers=not strict,
                       amnesty=amnesty or None)
        # макеты Figma группы (решение 2026-08-31, модель README/main):
        # ссылки макетов живут в НЕсверяемом README-оглавлении — их
        # наличие сторожится здесь (сверка ячейки макетов отключена)
        try:
            _src_t = _fs.read_text(src, encoding="utf-8", errors="replace")
            _rd = files[0].parent / "README.md"
            if ("figma.com" in _src_t.lower() and _rd.exists()
                    and files[0].name.endswith("-main.md")
                    and "figma.com" not in _fs.read_text(_rd, encoding="utf-8", errors="replace").lower()):
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

    # проверки уровня комплекта и репозитория — реестр KIT_CHECKS (ядро kitcheck.core):
    # порядок реестра — порядок строк отчёта; вердикт — в run_checks
    _kctx = _KitCtx(docs=docs, sources=sources, strict=strict, catalog=catalog,
                    card_ids=card_ids, card_titles=card_titles,
                    fm_schema_issues=fm_schema_issues, groups=groups, idx=idx)
    _k_lines, _k_ok = run_checks(KIT_CHECKS, _kctx)
    report.extend(_k_lines)
    all_ok = all_ok and _k_ok

    total = sum(counts.values())
    report.append(f"ИТОГО: файлов {total} — ✓ {counts['✓']}, "
                  f"✗ {counts['✗']}, ⚠ {counts['⚠']}; вердикт: "
                  + ("OK" if all_ok else "БРАК"))
    return report, all_ok


# --- проверки уровня комплекта и репозитория (этап 2 рефакторинга) ---
#
# Перенесены из _run_impl дословно: каждый фрагмент — функция-проверка с
# локальными report/all_ok; реестр KIT_CHECKS задаёт порядок строк отчёта.
# Новая проверка уровня комплекта — функция и строка в реестре.

@dataclass
class _KitCtx:
    """Контекст проверок уровня комплекта — итоги переписи файлов прогона."""
    docs: Path
    sources: Optional[Path]
    strict: bool
    catalog: Optional[Path]
    card_ids: Dict[Path, str]
    card_titles: Dict[Path, Tuple[str, str, str]]
    fm_schema_issues: List[Tuple[str, List[str], bool]]
    groups: Dict[str, List[Path]]
    idx: Dict[str, Path]


def _kc_repo_root(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, sources = ctx.docs, ctx.sources
    report: List[str] = []
    all_ok = True
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
    # nfr/ — каталог НФТ рядом с docs/ (шаблон nfr.md). На комплекте без
    # srs/ и brd корень проверки — папка сервиса, и без этого имени
    # каталог НФТ читается как посторонний.
    # tasks/ — постановки задач forward-режима «изменение по постановке»
    # (решение 2026-10-15): штатный каталог целевого docs-репозитория
    _ok_dirs = {"docs", "sources", "sandbox", "prompts", ".git", "brd", "srs",
                "nfr", "tasks", _docs_r.name}
    # корень домена: каталоги сервисов из таблицы корневого README законны
    # (решение владельца 2026-10-11); domain-vision.md и glossary.md —
    # markdown, он разрешён и так
    _dom = domain_context(docs)
    if _dom is not None and _dom[0] == root.resolve():
        _ok_dirs |= set(_dom[1].keys())
        _gm = domain_glossary_mode(root / "README.md")
        report.append(f"i домен: корень {root.name}, сервис "
                      + (f"«{_dom[2][0]}»" if _dom[2][1] else "без слота")
                      + " по таблице сервисов корневого README"
                      + ("; глоссарий доменный" if _gm == "domain" else
                         "; глоссарий доменный + указатели" if _gm == "pointers"
                         else ""))
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
    # точечные каталоги (.cursor, .claude, .vscode, .idea) — обёртки IDE,
    # в комплект не входят и в git не пушатся (гид: «только локально»);
    # как и точечные файлы, мусором не считаются (FB-01 lk-mp 2026-10-09:
    # пустой .cursor от IDE давал ✗ корня на первом же прогоне PRE-01)
    junk = sorted(
        p.name for p in root.iterdir()
        if (p.is_dir() and p.name not in _ok_dirs
            and not p.name.startswith("."))
        or (p.is_file() and not p.name.startswith(".")
            and p.name not in _ok_files
            and p.suffix.lower() not in (".md", ".markdown")))
    if junk:
        all_ok = False
        report.append(
            f"✗ корень репозитория: посторонние файлы ×{len(junk)} "
            f"({', '.join(junk[:8])}) — в корне только штатные каталоги "
            "(docs/sources/sandbox/prompts/nfr/tasks) и markdown; рабочие скрипты и кэши "
            "недопустимы (скрипты, изменяющие файлы комплекта, запрещены "
            "вовсе; read-only анализ — в sandbox)")
    return report, all_ok


def _kc_matrix_registry_and_debts(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_ids = ctx.docs, ctx.card_ids
    report: List[str] = []
    all_ok = True
    matrix = docs / "traceability-matrix.md"
    if matrix.is_file():
        # К-22 (2026-08-18): id из frontmatter каждой карточки обязан
        # состоять в реестре ID матрицы — фантомный/авансовый ID вне
        # реестра невидим сверкам и ломает правило выдачи ID (дозаход
        # 3.1: rbac-заглушка с RBAC-001, которого нет в матрице)
        mtext = _fs.read_text(matrix, encoding="utf-8", errors="replace")
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
        rep, ok = _safe(ld.check, matrix, docs, catalog_codes())
        mark = "✓" if ok else "✗"
        all_ok = all_ok and ok
        report.append(f"{mark} долги ссылок (link_debts):")
        report.extend(f"   {ln}" for ln in rep)
    else:
        all_ok = False
        report.append("✗ traceability-matrix.md: матрица не найдена — "
                      "комплект без реестра ID (обязательна, conventions "
                      "§5.3)")
    return report, all_ok


def _matrix_sync_report(docs: Path) -> Tuple[List[str], bool]:
    """Сверка выводимых разделов матрицы (`matrix_sync --check`) для отчёта
    selfcheck: (строки, есть ⚠). Матрица не по шаблону канона — одна строка
    «i … сверка пропущена»: расхождения структуры показывает сама утилита,
    в отчёт selfcheck они не попадают (решение владельца канона 2026-10-17)."""
    try:
        import matrix_sync as ms  # noqa: E402 — утилита сама импортирует selfcheck
    except ImportError:  # импорт пакетом app.scripts.CI (тесты)
        from . import matrix_sync as ms  # type: ignore
    matrix = docs / ms.MATRIX
    text = _fs.read_text(matrix, encoding="utf-8", errors="replace").replace("\r\n", "\n")
    if ms.structure_issues(ms.parse_matrix(text)):
        return ["i матрица трассировки не по шаблону канона — сверка выводимых "
                "разделов (matrix_sync) пропущена"], False
    rep, warn = ms.check(docs, matrix)
    if warn:
        head = ("⚠ выводимые разделы матрицы (matrix_sync) расходятся с документами "
                "— пересборка: matrix_sync.py --write:")
    else:
        rep = [ln for ln in rep if not ln.startswith("✓")]
        head = ("✓ выводимые разделы матрицы совпадают с документами (matrix_sync)"
                + (":" if rep else ""))
    return [head] + [f"   {ln}" for ln in rep], warn


def _kc_matrix_sync(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    # справочная сверка: ⚠ и i, вердикт не меняет; без матрицы молчит —
    # отсутствие матрицы — брак проверки реестра ID выше
    if not (ctx.docs / "traceability-matrix.md").is_file():
        return [], True
    rep, _ = _safe(_matrix_sync_report, ctx.docs)
    return rep, True


def _kc_open_questions(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
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
    return report, all_ok


def _kc_id_slots(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_ids = ctx.docs, ctx.card_ids
    report: List[str] = []
    all_ok = True
    # слот части сервиса в ID (2026-09-28): таблица кодов в README комплекта
    rep, ok = _safe(check_id_slots, docs, card_ids)
    all_ok = all_ok and ok
    if rep:
        report.append(("✓" if ok else "✗") + " слот части сервиса в ID:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_frontmatter_schema(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    fm_schema_issues, = ctx.fm_schema_issues,
    report: List[str] = []
    all_ok = True
    # одинаковые названия разных артефактов одного типа (ПР-08 разбора
    # замечаний ОНБ-В, 2026-10-16) — читатель не различит их по названию;
    # ⚠, вердикт не трогает
    fs_rep = format_frontmatter_schema(fm_schema_issues)
    report.extend(fs_rep)
    return report, all_ok


def _kc_title_uniqueness(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_titles = ctx.docs, ctx.card_titles
    report: List[str] = []
    all_ok = True
    tu_rep = check_title_uniqueness(docs, card_titles)
    if tu_rep:
        report.append("⚠ одинаковые названия разных артефактов одного типа:")
        report.extend(f"   {ln}" for ln in tu_rep)
    return report, all_ok


def _kc_source_silent(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # пробелы постановки (conventions §6 п.5, ПР-12 разбора ОНБ-В): ⚠
    ss_rep, _ = _safe(lambda: (check_source_silent(docs), True))
    report.extend(ss_rep)
    return report, all_ok


def _kc_required_sections(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # обязательные разделы шаблона (пакет 2 задача 7, ПР-05, ЗК-23): нет раздела — ⚠,
    # раздел вне шаблона — i; вердикт не трогают
    rs_rep, _ = _safe(lambda: (check_required_sections(docs), True))
    report.extend(rs_rep)
    return report, all_ok


def _kc_process_call(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # шаг процесса ↔ карточка вызова (пакет 2 задача 8, ЗК-13) — ⚠
    pc_rep, _ = _safe(lambda: (check_process_call_consistency(docs), True))
    report.extend(pc_rep)
    return report, all_ok


def _kc_readme_legend(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_ids = ctx.docs, ctx.card_ids
    report: List[str] = []
    all_ok = True
    # условные обозначения README (2026-10-10): самоописание комплекта
    # для внешних читателей — ⚠-сигналы, вердикт не трогают
    lg_rep, _ = _safe(lambda: (check_readme_legend(docs, card_ids), True))
    if lg_rep:
        report.append("⚠ условные обозначения README (самоописание "
                      "комплекта):")
        report.extend(f"   {ln}" for ln in lg_rep)
    return report, all_ok


def _kc_feedback_order(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # реестр замечаний команды (цикл обратной связи, модель 2026-08-17):
    # feedback.md живёт в КОРНЕ репозитория отдачи; файла нет — ок
    rep, ok = _safe(ld.check_feedback_order, docs.parent / "feedback.md")
    all_ok = all_ok and ok
    if rep:
        report.append(("✓" if ok else "✗") + " реестр замечаний команды:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_coordination_log(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # журнал координации (трек с координатором): длина записи — ⚠
    # (решение 2026-10-09: журнал должен читаться следующей сессией)
    rep, _ = _safe(ld.check_coordination_log,
                   docs.parent / "coordination-log.md")
    if rep:
        report.append("i журнал координации:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_config_params(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    rep, ok = _safe(ld.check_config_params, docs)
    all_ok = all_ok and ok
    if not ok:
        report.append("✗ настраиваемые параметры:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_sources_protocol(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, sources, groups = ctx.docs, ctx.sources, ctx.groups
    report: List[str] = []
    all_ok = True
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
    return report, all_ok


def _kc_service_catalog_and_h1(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, catalog = ctx.docs, ctx.catalog
    report: List[str] = []
    all_ok = True
    # сторож каталога сервисов (2026-09-29): ⚠-сигналы, вердикт не
    # трогают; без каталога (dev-копия вне канона, без --catalog) молчит
    cat_rep, _ = _safe(check_service_catalog,
                       catalog if catalog is not None
                       else canon_catalog_path(), docs)
    # H1 без названия сервиса (conventions §5; пакет 2 задача 9, ЗК-26) — ⚠
    h1_rep, _ = _safe(lambda: (check_h1_service(
        docs, catalog if catalog is not None else canon_catalog_path()), True))
    report.extend(h1_rep)
    report.extend(cat_rep)
    return report, all_ok


def _kc_no_api_in_bundle(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # контракты OpenAPI/AsyncAPI — в репозитории кода (2026-10-06):
    # каталог api/ и YAML в комплекте — ⚠ до удаления владельцем;
    # ссылки матрицы «API ↔ SRS» — через HEAD, явный ref по правилу
    na_rep, _ = _safe(check_no_api_in_bundle, docs)
    report.extend(na_rep)
    return report, all_ok


def _kc_api_matrix_refs(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, strict = ctx.docs, ctx.strict
    report: List[str] = []
    all_ok = True
    ar_rep, ar_ok = _safe(check_api_matrix_refs, docs, strict)
    all_ok = all_ok and ar_ok
    report.extend(ar_rep)
    return report, all_ok


def _kc_similar_group_points(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # детектор похожих точек применения групп (П-5e): i-сигналы,
    # вердикт не трогают — решение о консолидации только человеческое
    sg_rep, _ = _safe(lambda: (check_similar_group_points(docs), True))
    report.extend(sg_rep)
    return report, all_ok


def _kc_bare_entity_mentions(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # голые атрибутные обращения к сущностям реестра (2026-08-29):
    # ⚠-сигналы, вердикт не трогают
    bm_rep, _ = _safe(lambda: (check_bare_entity_mentions(docs), True))
    report.extend(bm_rep)
    return report, all_ok


def _kc_named_entity_links(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # ссылки-названия на сущности без более ранней полной ссылки с ID
    # (2026-10-02): ⚠-сигналы, вердикт не трогают
    ne_rep, _ = _safe(lambda: (check_named_entity_links(docs), True))
    report.extend(ne_rep)
    return report, all_ok


def _kc_group_contours(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # согласованность контура групп контролей (полигон 2026-08-29):
    # ⚠-сигналы, вердикт не трогают — решения о контуре человеческие
    gc_rep, _ = _safe(lambda: (check_group_contours(docs), True))
    report.extend(gc_rep)
    return report, all_ok


def _kc_file_artifacts(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # сторож не-markdown артефактов files/ (сироты и битые ссылки —
    # брак: потеря приложения молчаливая)
    fa_rep, fa_ok = _safe(check_file_artifacts, docs)
    all_ok = all_ok and fa_ok
    report.extend(fa_rep)
    return report, all_ok


def _kc_structured_examples(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, idx = ctx.docs, ctx.idx
    report: List[str] = []
    all_ok = True
    # структурные сторожа (2026-10-10): sidecar-примеры разбираются
    # (брак переноса ✗ / дефект источника ⚠), относительные ссылки
    # ведут на существующие файлы (✗)
    se_rep, se_ok = _safe(check_structured_examples, docs, idx)
    all_ok = all_ok and se_ok
    report.extend(se_rep)
    return report, all_ok


def _kc_relative_links(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    rl_rep, rl_ok = _safe(check_relative_links, docs)
    all_ok = all_ok and rl_ok
    report.extend(rl_rep)
    return report, all_ok


def _kc_link_anchors_and_ids(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # якоря ссылок и упоминание карточки без ID (ПР-06 разбора замечаний
    # ОНБ-В, 2026-10-16) — ⚠, вердикт не трогают
    la_rep, _ = _safe(lambda: (check_link_anchors_and_ids(docs), True))
    report.extend(la_rep)
    return report, all_ok


def _kc_nfr_catalog(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    nfr_rep, nfr_ok = _safe(check_nfr_catalog, docs)
    all_ok = all_ok and nfr_ok
    report.extend(nfr_rep)
    return report, all_ok


def _kc_source_coverage(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, sources = ctx.docs, ctx.sources
    report: List[str] = []
    all_ok = True
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
    return report, all_ok


KIT_CHECKS: List[Check] = [
    Check("repo_root", _kc_repo_root, affects_verdict=True),
    Check("matrix_registry_and_debts", _kc_matrix_registry_and_debts, affects_verdict=True),
    Check("matrix_sync", _kc_matrix_sync, affects_verdict=False),
    Check("open_questions", _kc_open_questions, affects_verdict=True),
    Check("id_slots", _kc_id_slots, affects_verdict=True),
    Check("frontmatter_schema", _kc_frontmatter_schema, affects_verdict=False),
    Check("title_uniqueness", _kc_title_uniqueness, affects_verdict=False),
    Check("source_silent", _kc_source_silent, affects_verdict=False),
    Check("required_sections", _kc_required_sections, affects_verdict=False),
    Check("process_call", _kc_process_call, affects_verdict=False),
    Check("readme_legend", _kc_readme_legend, affects_verdict=False),
    Check("feedback_order", _kc_feedback_order, affects_verdict=True),
    Check("coordination_log", _kc_coordination_log, affects_verdict=False),
    Check("config_params", _kc_config_params, affects_verdict=True),
    Check("sources_protocol", _kc_sources_protocol, affects_verdict=True),
    Check("service_catalog_and_h1", _kc_service_catalog_and_h1, affects_verdict=False),
    Check("no_api_in_bundle", _kc_no_api_in_bundle, affects_verdict=False),
    Check("api_matrix_refs", _kc_api_matrix_refs, affects_verdict=True),
    Check("similar_group_points", _kc_similar_group_points, affects_verdict=False),
    Check("bare_entity_mentions", _kc_bare_entity_mentions, affects_verdict=False),
    Check("named_entity_links", _kc_named_entity_links, affects_verdict=False),
    Check("group_contours", _kc_group_contours, affects_verdict=False),
    Check("file_artifacts", _kc_file_artifacts, affects_verdict=True),
    Check("structured_examples", _kc_structured_examples, affects_verdict=True),
    Check("relative_links", _kc_relative_links, affects_verdict=True),
    Check("link_anchors_and_ids", _kc_link_anchors_and_ids, affects_verdict=False),
    Check("nfr_catalog", _kc_nfr_catalog, affects_verdict=True),
    Check("source_coverage", _kc_source_coverage, affects_verdict=False),
]


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


# --- домен сервисов (решение владельца 2026-10-11) ---
#
# Доменный docs-репозиторий: в корне README с ТАБЛИЦЕЙ СЕРВИСОВ (колонки
# «Код», «Каталог» (или «service-id»), необязательно «Слот» — код либо
# «нет»), domain-vision.md и glossary.md домена; комплекты сервисов — в
# `<service-id>/`, общий сервис — `shared/`. Идентификатор артефакта
# комплекта домена несёт слот сервиса сразу после префикса
# (`FUN-REG-IDN-CL-01`, `ENT-SHR-001`), слот части — следом, как прежде.
# Без таблицы сервисов в README родителя комплекта прибор ведёт себя как
# раньше: одиночные сервисы и сервисы с частями не затронуты.


_GLOSSARY_MODE_RE = re.compile(r"Глоссарий\s*[:—-]\s*(доменный(?:\s*\+\s*указатели)?)",
                               re.I)


def domain_glossary_mode(readme: Path) -> Optional[str]:
    """Режим глоссария, объявленный в README домена (решение владельца
    2026-10-12): «доменный» — один файл домена, в комплектах глоссария нет;
    «доменный + указатели» — в каждом комплекте указатель. None — не
    объявлен (одиночный сервис либо режим не выбран)."""
    try:
        text = _fs.read_text(readme, encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _GLOSSARY_MODE_RE.search(text)
    if not m:
        return None
    return "pointers" if "указател" in m.group(1).lower() else "domain"


# --- сторож условных обозначений README комплекта (2026-10-10) ---
# README комплекта — самоописание: внешние читатели (агенты платформы
# AI Factory по её паспорту ЭКО «Как читать» п. 2) берут из раздела
# «Условные обозначения» контуры, коды частей (таблица «Подсервисы»),
# префиксы ID и идентификатор статусной модели; где README молчит,
# действует их паспорт, а не канон миграции. Сторож держит самоописание
# полным: каждый префикс ID, встречающийся в комплекте, описан; статусная
# модель названа; поля frontmatter объяснены; таблица частей носит имя,
# по которому её ищут. Только ⚠ — действующие комплекты не ломаются;
# без README сторож называет это одним предупреждением.


# --- структурные сторожа (2026-10-10, решение владельца P-20) ---
# Два свойства комплекта, которых прибор не проверял, а валидатор
# платформы AI Factory блокирует на входе (E_STRUCTURED_FILE_INVALID,
# E_LOCAL_LINK_MISSING): sidecar-примеры JSON/YAML/XML разбираются;
# относительные ссылки в документах ведут на существующие файлы. Замер
# 2026-10-07 на КК: три невалидных JSON-примера (BOM; синтаксис), две
# битые ссылки — гейт миграции их не видел. Сторож обнаруживает, не
# лечит, и разводит причину по источнику: пример испорчен переносом
# (BOM, обрезка, склейка — в источнике тот же текст разбирается или
# пример в источнике не найден) — брак миграции ✗, чинится; пример
# невалиден уже в источнике — дефект аналитики ⚠: файл сохраняется как
# `.txt` с пометкой в карточке и записью в вопросы, не правится.


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


def catalog_codes() -> Optional[set]:
    """Коды сервисов каталога канона для сторожа владельцев долгов
    (link_debts); None — каталог недоступен (dev-копия вне канона)."""
    cat = canon_catalog_path()
    if cat is None:
        return None
    try:
        data = json.loads(_fs.read_text(cat, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {s.get("code") for s in data if isinstance(s, dict) and s.get("code")}


def canon_catalog_path() -> Optional[Path]:
    """`_meta/services.json` канона, из которого запущен selfcheck;
    None — dev-копия вне канона."""
    tool_dir = Path(__file__).resolve().parent
    if tool_dir.name != "tools" or tool_dir.parent.name != "_meta":
        return None
    cat = tool_dir.parent / "services.json"
    return cat if cat.is_file() else None


# --- сторожа протокольной дисциплины (П-5c, 2026-08-28) ---
# Замер «слабый исполнитель × компактный промпт» (ISS-02): модель
# написала генерирующий скрипт и сделала третий retry — оба прямых
# запрета протокола (§3, §6) потерялись из её внимания за два часа
# работы. Правило и образец есть — не было сторожа; закон обходов:
# ненаблюдаемое правило со временем нарушается любым исполнителем,
# вопрос лишь ёмкости. Мягкое включение: только на протокольном
# стенде (в профиле есть строка «срез канона»). confluence/ исключён
# из скана — это данные источника, не рабочие файлы исполнителя.


# План обязан иметь промпт-файл prompts/<ЭТАП>.md на КАЖДЫЙ этап
# (план-промпт v2.2 п.10); неполный пакет промптов обнаруживался
# только внимательностью приёмщика (кейс: «дособери с ISS-02 и далее»
# прочитано планировщиком как «без COM-03+»). Сторож делает неполноту
# видимой на каждом прогоне. Мягкое включение: активен только при
# строке «план миграции: <файл>» в профиле источников; этапы, чьи
# отчёты уже лежат в sandbox/ (selfcheck-<ЭТАП>*.txt), считаются
# выполненными — промпт для них не требуется. Информационный гейт:
# вердикт не трогает (неполнота пакета — не дефект комплекта docs).


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


# --- детектор похожих точек применения групп (П-5e, 2026-08-28) ---
# Механический перенос «страница × группа → GRP» размножает одну точку
# применения, описанную разными страницами с разных сторон (живой кейс:
# три группы «Подписать и отправить» GRP-7/9/16 в cc-card-issue нашёл
# вопрос владельца, не прибор). Детектор — НЕ решатель: пары групп
# одного реестра с общим цитируемым литералом (кнопка «…», статус
# `…`) поднимаются i-строкой; решение «слить/различить как фазы» —
# только человеческое (шаг консолидации этапа). Скоуп — ОДИН реестровый
# README: совпадение кнопок между подсервисами — разные ЭФ, не дубль.


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
        raw = _fs.read_text(baseline_path, encoding="utf-8", errors="replace")
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
    # FB-02 lk-mp (2026-10-09): «✗ было 0 → стало 0» читалось как «ничего
    # не сделано» — дельта сравнивает ВЕРДИКТЫ, не содержание; строка
    # состава показывает, что единицы отчёта прибавились/убыли; изменение
    # внутри уже существовавших файлов — по строке «изменены:» журнала
    # гейта (sandbox/journal.txt) и git-скоупу сдачи
    added = sorted(k for k in cur if k not in base)
    gone = sorted(k for k in base if k not in cur)
    comp = (f"   состав: единиц в отчёте было {len(base)} → стало {len(cur)}"
            + (f"; новых ×{len(added)}: " + ", ".join(added[:6])
               + (" …" if len(added) > 6 else "") if added else "")
            + (f"; исчезло ×{len(gone)}: " + ", ".join(gone[:6])
               + (" …" if len(gone) > 6 else "") if gone else ""))
    out.append(comp + " (дельта сравнивает вердикты; изменения внутри "
               "прежних файлов — строка «изменены:» журнала гейта)")
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
                prev_mt = json.loads(_fs.read_text(state_p, encoding="utf-8"))
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
