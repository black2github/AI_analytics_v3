# app/scripts/CI/kitcheck/checks/card_run.py
"""Проверки карточки: контексты, реестры FILE_CHECKS и SOURCE_CHECKS, сверка с источником
(`_rc_*`), точки входа `check_file` и `run_check`, подготовка источника.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from .. import fs as _fs
from ..core import Check, run_checks
from ..html import _fm_head
from ..md import _kit_md, page_ids, read_frontmatter, strip_html_comments
from .card_common import _norm_ws
from .card_form import (
    _fc_blank_line_table_breaks, _fc_blockquote_indented_code, _fc_confluence_ui_artifacts,
    _fc_duplicate_headers, _fc_empty_tables, _fc_figma_mockups, _fc_flattened_attributes,
    _fc_fun_call_token, _fc_homoglyphs, _fc_html_comments, _fc_invisible_chars,
    _fc_invisible_html_tags, _fc_long_lines, _fc_notation_hints, _fc_outside_eco_intc,
    _fc_removed_module_type,
    _fc_param_code_row_numbers,
    _fc_pseudo_screen_form, _fc_readme_main_roles, _fc_screen_form_condition_notation,
    _fc_separator_columns, _fc_shortening_markers, _fc_strikethrough_marker, _fc_stub_card,
    _fc_torn_table_cells, _fc_unclosed_code_blocks, _fc_undecomposed_lines
)
from .card_source import (
    _fc_source_page_refs_and_columns, _frontmatter_title, check_cell_coverage,
    check_image_trace, check_outside_template_section,
    check_quoted_literals, check_source_tables, check_title, check_unchecked_tables,
    source_role_literals, source_tables_summary, thin_call_home, base_contract_ref
)
from .card_steps import (
    check_behavior_nesting, check_behavior_numbering, check_nesting_depth,
    check_step_body_structure, check_step_markers
)
from .card_passport import (check_heavy_cells, check_heavy_pair_structure, check_label_sections,
                            passport_row_keys)
from .card_notification import check_notification_structure
from .card_branch_form import _fc_branch_form
from .card_controls import (
    _ENTITY_ID_RE, _fc_control_cards_by_entity, _fc_fabricated_attributes, _fc_message_attribution,
    _frontmatter_entity
)
from .card_clean import (
    _docs_card_titles, _fc_nested_links, _fc_oq_refs_in_body, check_clean_document,
    check_source_tag_mentions, check_target_mentions, check_tuz_formula
)


def check_file(md_path: Path, min_valid_pct: float = 95.0,
               source_text: Optional[str] = None,
               column_roles: bool = True,
               soft_markers: bool = False,
               amnesty_text: Optional[str] = None,
               kit_summary: bool = False,
               without_sources: bool = False,
               outside_eco: bool = False) -> Tuple[List[str], bool]:
    """Режим --check: колонные валидаторы поверх ГОТОВОЙ карточки.

    Ловит класс «якорная колонка переписана при перекладке» (регресс
    кратности [1] → 1, итерация 6-кватер, 2026-08-07): утилита выдала
    валидную таблицу, а в карточку она попала с искажённым литералом.
    Роли распознаются по заголовкам; таблицы без ролей пропускаются
    (перечень кодов отказов, свойства обмена — им валидаторы не нужны).

    Дополнительно ловит МАРКЕРЫ СОКРАЩЕНИЯ («фрагмент», «см. источник»,
    «и т.д.»): агент трижды ужимал справочник «Коды банковских продуктов»
    до одной колонки с пометкой «(фрагмент из источника)», игнорируя
    правило, сверку и образец (итерации 6-секст/6-септ/6-окт, 2026-08-09) —
    текстовая доставка не доехала, ловим инструментом. В честных переносах
    этих слов нет (проверено по источнику и чистым прогонам).

    kit_summary — прогон в составе самопроверки комплекта: проверки, которые
    комплект сводит в одну строку (форма ветвления), строки на файл не дают.

    without_sources — самопроверка комплекта без выгрузки (selfcheck без --sources):
    формулировки, отсылающие к источнику, заменяются нейтральными (маркер сокращения).

    outside_eco — карточка части вне контура Экосистемы: каталог `srs/<слаг>/` с зоной
    `вне Экосистемы <слаг>` в разметке профиля источников (решение владельца канона
    2026-11-08). Признак выключает сторож привилегий FUN-CL/BNK и требует у карточки
    внутреннего контракта строк «Канал» и «Контур исполнения»; прочее — как у любой карточки."""
    text = _fs.read_text(md_path, encoding="utf-8")
    report: List[str] = [f"проверка карточки: {md_path.name}"]
    ok = True
    src_literals = source_role_literals(source_text) if source_text else None

    lines = text.splitlines()
    # проверки карточки — реестр FILE_CHECKS (ядро kitcheck.core): порядок реестра —
    # порядок строк отчёта, вердикт — в run_checks
    fx = _FileCtx(md_path=md_path, min_valid_pct=min_valid_pct, source_text=source_text, column_roles=column_roles, soft_markers=soft_markers, amnesty_text=amnesty_text, text=text, lines=lines, src_literals=src_literals, kit_summary=kit_summary, without_sources=without_sources, outside_eco=outside_eco)
    f_lines, f_ok = run_checks(FILE_CHECKS, fx)
    report.extend(f_lines)
    ok = ok and f_ok
    return report, ok


# --- проверки карточки (этап 4 рефакторинга) ---
#
# Перенесены из check_file дословно: каждый блок — функция-проверка с
# локальными report/ok; реестр FILE_CHECKS задаёт порядок строк отчёта.
# Новая проверка карточки — функция и строка в реестре.

@dataclass
class _FileCtx:
    """Контекст проверок одной карточки: параметры check_file и её текст."""
    md_path: Path
    min_valid_pct: float
    source_text: Optional[str]
    column_roles: bool
    soft_markers: bool
    amnesty_text: Optional[str]
    text: str
    lines: List[str]
    src_literals: Optional[object]
    kit_summary: bool = False  # в составе selfcheck комплекта: сводные проверки — строкой комплекта
    without_sources: bool = False  # selfcheck без --sources: без отсылок к источнику в формулировках
    outside_eco: bool = False  # карточка части вне контура Экосистемы (по разметке профиля)
# Документы определений, к которым не применяется сторож полноты кавычечных
# литералов источника (решение владельца канона 2026-10-30): глоссарий — не
# дословный перенос страницы, шаблон требует атомарных определений и
# делегирования реестров, то есть сокращения источника; domain-vision домена —
# по тому же основанию. Тип → наименование для i-строки.
_NO_LITERALS_TYPES = {"glossary": "глоссарию", "domain-vision": "видению домена",
                      # сводка видения сервиса по нескольким страницам, в том числе черновикам
                      # (решение владельца канона 2026-11-01, КК service-vision.md)
                      "vision": "видению сервиса"}
# держатели шагов страницы: у группы с главной карточкой вызова поведение сверяется по ним
_STEP_HOLDER_TYPES = frozenset({"function", "process", "screen-form"})
# держатели шагов, у которых строка «**Базовый контракт:**» освобождает состав страницы метода
_BASE_HOLDER_TYPES = frozenset({"function", "process"})
# страница-функция выгрузки: паспорт функции с ячейкой «Что делает функция»
_FUNCTION_PAGE_RE = re.compile(r"Что делает функция", re.I)


FILE_CHECKS: List[Check] = [
    Check("torn_table_cells", _fc_torn_table_cells, scope="file"),
    Check("blank_line_table_breaks", _fc_blank_line_table_breaks, scope="file"),
    Check("shortening_markers", _fc_shortening_markers, scope="file"),
    Check("html_comments", _fc_html_comments, scope="file"),
    Check("param_code_row_numbers", _fc_param_code_row_numbers, scope="file"),
    Check("notation_hints", _fc_notation_hints, scope="file"),
    Check("invisible_chars", _fc_invisible_chars, scope="file"),
    Check("homoglyphs", _fc_homoglyphs, scope="file"),
    Check("empty_tables", _fc_empty_tables, scope="file"),
    Check("separator_columns", _fc_separator_columns, scope="file"),
    Check("flattened_attributes", _fc_flattened_attributes, scope="file"),
    Check("undecomposed_lines", _fc_undecomposed_lines, scope="file"),
    Check("branch_form", _fc_branch_form, scope="file"),
    Check("long_lines", _fc_long_lines, scope="file"),
    Check("readme_main_roles", _fc_readme_main_roles, scope="file"),
    Check("pseudo_screen_form", _fc_pseudo_screen_form, scope="file"),
    Check("figma_mockups", _fc_figma_mockups, scope="file"),
    Check("fabricated_attributes", _fc_fabricated_attributes, scope="file"),
    Check("message_attribution", _fc_message_attribution, scope="file"),
    Check("control_cards_by_entity", _fc_control_cards_by_entity, scope="file"),
    Check("blockquote_indented_code", _fc_blockquote_indented_code, scope="file"),
    Check("unclosed_code_blocks", _fc_unclosed_code_blocks, scope="file"),
    Check("invisible_html_tags", _fc_invisible_html_tags, scope="file"),
    Check("screen_form_condition_notation", _fc_screen_form_condition_notation, scope="file"),
    Check("nested_links", _fc_nested_links, scope="file"),
    Check("confluence_ui_artifacts", _fc_confluence_ui_artifacts, scope="file"),
    Check("stub_card", _fc_stub_card, scope="file"),
    Check("oq_refs_in_body", _fc_oq_refs_in_body, scope="file"),
    Check("strikethrough_marker", _fc_strikethrough_marker, scope="file"),
    Check("duplicate_headers", _fc_duplicate_headers, scope="file"),
    Check("fun_call_token", _fc_fun_call_token, scope="file"),
    Check("outside_eco_intc", _fc_outside_eco_intc, scope="file"),
    Check("removed_module_type", _fc_removed_module_type, scope="file"),
    Check("source_page_refs_and_columns", _fc_source_page_refs_and_columns, scope="file"),
]


def apply_critic(text: str) -> str:
    """ЦЕЛЕВОЙ текст источника: CriticMarkup-правки применяются —
    добавления остаются содержимым (без маркеров и префикса задачи
    «GBO-NNNNN: »), удаления выпадают, замены — новым текстом; обе
    формы разметки (текстовая и HTML-span). К-5 экзамена inkasso:
    гейт, требующий сырую разметку, провоцировал перенос маркеров в
    чистовик (fun-sys-08 — «markup сохранён для прохождения гейта»)."""
    # префикс задачи: «GBO-NNNNN:» и экспортёрский «UNKNOWN-<hex-цвет>:»
    # (правка без номера задачи; К-15 дозахода-3: префикс не снимался и
    # агент вписал его текстом в карточку ent-002 ради гейта значений)
    text = re.sub(r"\{\+\+\s*(?:(?:[A-ZА-Я]+-\d+(?:/\d+)*"
                  r"|UNKNOWN-[0-9a-fA-F]{6}):?\s*)?(.*?)\+\+\}",
                  r"\1", text, flags=re.S)
    text = re.sub(r"\{--.*?--\}", "", text, flags=re.S)
    text = re.sub(r"\{~~.*?~>(.*?)~~\}", r"\1", text, flags=re.S)
    text = re.sub(r"<span[^>]*critic-del[^>]*>.*?</span>", "", text,
                  flags=re.S | re.I)
    text = re.sub(r"<span[^>]*critic-ins[^>]*>(.*?)</span>", r"\1", text,
                  flags=re.S | re.I)
    return text


_HISTORY_TABLE_RE = re.compile(
    r"<table\b(?:(?!</table>).)*?<th[^>]*>\s*(?:Дата|Автор)\b"
    r"(?:(?!</table>).)*?</table>", re.S | re.I)


def strip_history(text: str) -> str:
    """Вырезает HTML-таблицы истории изменений страницы (шапка с
    «Дата»/«Автор») до всех сверок: история по канону не переносится,
    а её кавычечные литералы («исключен реквизит "X"») ложно
    требовались в карточках (К-9 экзамена inkasso, страница контролей).
    Md-таблицы истории режет фильтр check_source_tables."""
    return _HISTORY_TABLE_RE.sub("", text)


# типы шапки, у которых тяжёлая ячейка паспорта остаётся строкой двухколоночной таблицы
# «лейбл | значение» (К-29, шаблон contract-call.md, раздел A)
_PASSPORT_ROW_TYPES = ("external-integration", "internal-contract", "contract-call")


def run_check(files: List[Path], source_path: Optional[Path],
              min_valid_pct: float = 95.0,
              docs_root: Optional[Path] = None,
              soft_markers: bool = False,
              pardon_source: Optional[Path] = None,
              amnesty_sources: Optional[List[Path]] = None,
              kit_summary: bool = False,
              allow_sibling_docs: bool = False,
              without_sources: bool = False,
              inventory: Optional[Path] = None,
              group_extra_sources: Optional[List[Tuple[Path, Path]]] = None,
              call_cards: Optional[List[Path]] = None,
              outside_eco: bool = False
              ) -> Tuple[List[str], bool]:
    """Полная связка режима --check одной функцией — ЕДИНАЯ точка
    подключения проверок для CLI и selfcheck-диспетчера (двойной
    монтаж проверок расходится). Первая карточка — основная (title,
    поведение, колонки); значения источника ищутся в объединении.
    Источник сверяется в ЦЕЛЕВОМ виде (strip_history + apply_critic).

    pardon_source — источник ТОЛЬКО для помилований (z03 ISS-03,
    «ОK» в неглавной карточке группы): неглавные карточки selfcheck
    гоняет без source_path — полная сверка части против главной
    страницы группы ложна по построению (title, литералы и шаги части
    не её) — но дословные помилования check_file (К-30 гомоглифы,
    source_literals колонных ролей) наследуются от той же страницы.
    Действует лишь при source_path is None; сверочные блоки run_check
    (`src_text is not None`) от него не включаются.

    inventory — опись выгрузки (inventory.md) явно: гейт переноса гоняет прибор на
    временной копии docs/, где описи нет; без параметра опись ищется от docs_root
    (kitcheck.fs.find_kit_file).

    group_extra_sources — [(доп. страница, файл-владелец)] НЕглавных файлов группы (замечание
    ОНБ-В 72, 2026-11-07): по ним сверяются только таблицы и кавычечные литералы, как по доп.
    страницам главной; освобождение тонкой карточки вызова — по шапке владельца; сторож title
    и амнистия длинных строк их не видят (title неглавной карточки — не наименование группы).

    outside_eco — главная карточка лежит в части вне контура Экосистемы (каталог `srs/<слаг>/`
    с зоной `вне Экосистемы <слаг>` в разметке профиля; вычисляет вызывающий — selfcheck
    по профилю источников): передаётся в check_file."""
    main_file = files[0]
    src_text = (apply_critic(strip_history(
        _fs.read_text(source_path, encoding="utf-8")))
                if source_path is not None else None)
    pardon_text = (apply_critic(strip_history(
        _fs.read_text(pardon_source, encoding="utf-8")))
                   if src_text is None and pardon_source is not None
                   else None)
    amnesty_text = ("\n".join(
        apply_critic(strip_history(_fs.read_text(p, encoding="utf-8", errors="replace")))
        for p in (amnesty_sources or []) if p.is_file()) or None)
    report, ok = check_file(main_file, min_valid_pct=min_valid_pct,
                            source_text=(src_text if src_text is not None
                                         else pardon_text),
                            column_roles=main_file.name.lower() != "readme.md",
                            soft_markers=soft_markers,
                            amnesty_text=amnesty_text,
                            kit_summary=kit_summary,
                            without_sources=without_sources,
                            outside_eco=outside_eco)
    card_text = _fs.read_text(main_file, encoding="utf-8")
    # межтиповая страница-источник: значения ищутся в ОБЪЕДИНЕНИИ
    # карточек (пример: каталог статусов в dictionaries + переходы в
    # status-model); title/поведение/колонки — по первой (основной).
    # HTML-комменты вырезаются ДО поиска значений (К-13): содержимое
    # коммента невидимо читателю — «найденное» там значение не перенесено.
    # Комменты внутри блоков кода — дословное содержимое примера, остаются
    # (границы — kitcheck/fence.py; proc-033 КК, 2026-11-02).
    combined = strip_html_comments(
        "\n\n".join(_fs.read_text(f, encoding="utf-8") for f in files))
    # Sidecar-образцы §5 — часть карточки: шаблон предписывает держать
    # payload (JSON/XML/XSD/WSDL/curl) в <as>/examples/, а не в теле.
    # Значения источника, перенесённые в sidecar, ищутся ЗДЕСЬ же —
    # иначе «перенос по шаблону» читается прибором как потеря
    # (образцы вызова EXTINT-F1-003: GUID и номер счёта живут в
    # extint-f1-003-request.json, в карточке их быть не должно).
    # Карточка в подкаталоге ссылается на sidecar через «../examples/…» (КК intc-005,
    # internal-contracts/client/, 2026-11-01): такая ссылка — sidecar, только если файл лежит
    # в каталоге examples внутри комплекта (docs_root, если задан); чужие пути не читаются.
    # Ссылка разрешается от каталога ТОЙ карточки группы, где стоит (КК fun-sys-16 + intc-004,
    # 2026-11-01: главная — функция в function/system/, ссылка — в контракте
    # internal-contracts/client/; от каталога главной sidecar не находился, вердикт зависел от
    # порядка файлов). Sidecar, на который ссылаются две карточки, читается один раз.
    root = Path(docs_root).resolve() if docs_root is not None else None
    seen_sides: set = set()
    for f in files:
        f_text = strip_html_comments(_fs.read_text(f, encoding="utf-8"))
        for m in re.finditer(r"\]\(((?:\.\./)*examples/[^)\s]+)\)", f_text):
            side = (f.parent / m.group(1)).resolve()
            if side in seen_sides:
                continue
            try:
                if m.group(1).startswith("../") and (
                        side.parent.name != "examples"
                        or (root is not None and root not in side.parents)):
                    continue
                if (side.is_file() and side.stat().st_size <= 2_000_000
                        and side.suffix.lower() in {
                            ".json", ".xml", ".xsd", ".wsdl", ".sh", ".txt",
                            ".html", ".yaml", ".yml"}):
                    seen_sides.add(side)
                    combined += "\n\n" + _fs.read_text(side, encoding="utf-8", errors="replace")
            except OSError:
                continue
    # проверки — реестр SOURCE_CHECKS (ядро kitcheck.core): порядок реестра —
    # порядок строк отчёта, вердикт — в run_checks
    fx = _SourceCtx(files=files, source_path=source_path, min_valid_pct=min_valid_pct, docs_root=docs_root, soft_markers=soft_markers, pardon_source=pardon_source, amnesty_sources=amnesty_sources, card_text=card_text, combined=combined, main_file=main_file, src_text=src_text, allow_sibling_docs=allow_sibling_docs, inventory=inventory, group_extra_sources=group_extra_sources, call_cards=call_cards)
    f_lines, f_ok = run_checks(SOURCE_CHECKS, fx)
    report.extend(f_lines)
    ok = ok and f_ok
    return report, ok


# --- проверки run_check (рефакторинг: перенос в реестр SOURCE_CHECKS) ---
#
# Перенесены из run_check дословно: каждый блок — функция-проверка с
# локальными report/ok; реестр SOURCE_CHECKS задаёт порядок строк отчёта.
# Новая проверка — функция и строка в реестре.

@dataclass
class _SourceCtx:
    """Контекст проверок run_check: её параметры и значения пролога."""
    files: object
    source_path: object
    min_valid_pct: object
    docs_root: object
    soft_markers: object
    pardon_source: object
    amnesty_sources: object
    card_text: object
    combined: object
    main_file: object
    src_text: object
    allow_sibling_docs: object
    inventory: object = None
    group_extra_sources: object = None
    call_cards: object = None




def _rc_clean_document(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    docs_root, main_file = fx.docs_root, fx.main_file
    allow_sibling_docs = bool(fx.allow_sibling_docs)
    report: List[str] = []
    ok = True
    # сторож чистовика (волна D): по КАЖДОЙ карточке вызова, не только
    # главной (неглавные в selfcheck прогоняются отдельными вызовами,
    # здесь files>1 встречается в CLI)
    cl_report, cl_ok = check_clean_document(
        main_file, docs_root, allow_sibling_docs=allow_sibling_docs)
    report.extend(cl_report)
    ok = ok and cl_ok
    return report, ok


def _rc_form_entity_names(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    docs_root, card_text, main_file = fx.docs_root, fx.card_text, fx.main_file
    report: List[str] = []
    ok = True
    # FB-11: entity-имя формы законно, пока карточки формы в комплекте
    # нет; появилась карточка с таким title — имя заменяется на её ID.
    # Сигнал не зависит от порядка этапов плана (формы раньше или позже
    # контролей): срабатывает, когда есть оба условия сразу.
    if (docs_root is not None
            and main_file.name.lower().startswith("cards-")
            and re.search(r"^type:\s*control\s*$", _fm_head(card_text), re.M)):
        _ename = _frontmatter_entity(card_text)
        if _ename and not _ENTITY_ID_RE.match(_ename):
            _want = _norm_ws(_ename)
            _hit = next((rel for t, rel in _docs_card_titles(docs_root)
                         if _norm_ws(t) == _want), None)
            if _hit:
                report.append(
                    f"предупреждение: entity файла — имя формы, а карточка "
                    f"формы в комплекте уже есть ({_hit}) — заменить имя "
                    "на её ID (шаблон controls.md: имя допустимо только "
                    "до появления карточки)")
    return report, ok


def _rc_tuz_formula(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    card_text, = fx.card_text,
    report: List[str] = []
    ok = True
    # формула ТУЗ обычным шрифтом (решение 2026-08-19, шаблон §2)
    tz_report, tz_ok = check_tuz_formula(card_text)
    report.extend(tz_report)
    ok = ok and tz_ok
    return report, ok


def _rc_source_cell_completeness(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    files, card_text, combined, main_file, src_text = fx.files, fx.card_text, fx.combined, fx.main_file, fx.src_text
    report: List[str] = []
    ok = True
    # полнота ячеек источника — reverse-карточки модели данных
    # (COM-01 Корпкарт 2026-08-27: хвосты ячеек Тип/Описание терялись
    # при выносе перечислений в справочник); корпус поиска — группа
    # карточек + весь каталог модели данных (фрагмент вправе уехать
    # в dictionaries/README по шаблону)
    if src_text is not None and re.search(
            r"^type:\s*data-model\s*$", _fm_head(card_text), re.M):
        sib = "\n\n".join(
            _fs.read_text(f, encoding="utf-8")
            for f in sorted(main_file.parent.glob("*.md"))
            if f not in files)
        corpus_txt = combined + "\n\n" + strip_html_comments(sib)
        cov_rep, cov_ok = check_cell_coverage(src_text, corpus_txt)
        report.extend(cov_rep)
        ok = ok and cov_ok
    return report, ok


def _rc_tagged_mentions(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    docs_root, card_text, main_file = fx.docs_root, fx.card_text, fx.main_file
    report: List[str] = []
    ok = True
    # теговые упоминания целей: ссылка или долг (софт, вердикт не трогает)
    if docs_root is not None:
        tm_report, _ = check_target_mentions(card_text, main_file,
                                             docs_root)
        report.extend(tm_report)
    return report, ok


def _rc_behavior_numbering(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    card_text, = fx.card_text,
    report: List[str] = []
    ok = True
    num_report, num_ok = check_behavior_numbering(card_text)
    report.extend(num_report)
    ok = ok and num_ok
    return report, ok


def _rc_outside_template_section(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    return check_outside_template_section(fx.card_text)


def _rc_notification_structure(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    card_text, = fx.card_text,
    report: List[str] = []
    ok = True
    ntf_report, ntf_ok = check_notification_structure(card_text)
    report.extend(ntf_report)
    ok = ok and ntf_ok
    return report, ok


@_fs.memoize(copy=dict)
def _main_page_index(docs_root: Path) -> Dict[str, List[Path]]:
    """page_id → карточки комплекта, у которых он стоит ПЕРВЫМ в confluence_page_ids
    (главная страница карточки). Кэш сессии, как у _page_artifact_index."""
    out: Dict[str, List[Path]] = {}
    for p in _kit_md(docs_root):
        pids = page_ids(read_frontmatter(p) or {})
        if pids:
            out.setdefault(pids[0], []).append(p)
    return out


_INV_ROW_RE = re.compile(r"^\|\s*(\d{4,})\s*\|(?:[^|\n]*\|){4}\s*(srs/[^|\s]+)", re.M)
# колонки описи: page_id | title | родитель | req_type | строк | целевой тип | основание
_INV_TYPE_RE = re.compile(r"^\|\s*(\d{4,})\s*\|\s*([^|\n]*?)\s*\|[^|\n]*\|\s*([^|\n]*?)\s*\|", re.M)


@_fs.memoize(copy=dict)
def _inventory_targets(inventory: Path) -> Dict[str, str]:
    """page_id → целевой каталог страницы по описи выгрузки (inventory.md в корне комплекта,
    колонка «целевой тип (гипотеза)», только значения вида srs/…)."""
    if not inventory.is_file():
        return {}
    text = _fs.read_text(inventory, encoding="utf-8", errors="replace")
    return {m.group(1): m.group(2) for m in _INV_ROW_RE.finditer(text)}


@_fs.memoize(copy=dict)
def _inventory_req_types(inventory: Path) -> Dict[str, Tuple[str, str]]:
    """page_id → (title, req_type) страницы по описи (req_type: integration, function,
    screenItemForm…; с пометкой «+frozen:…» как есть)."""
    if not inventory.is_file():
        return {}
    text = _fs.read_text(inventory, encoding="utf-8", errors="replace")
    return {m.group(1): (m.group(2), m.group(3)) for m in _INV_TYPE_RE.finditer(text)}


# страница-копия Confluence («Копия [КК] ЕСК_ОА_…»): префикс в начале титула, с заглавной
_COPY_TITLE_RE = re.compile(r"^Копия\s+")


_COPY_TITLE_MARK_RE = re.compile(r"^Копия\s+\[([^\[\]\n]{1,30})\]")


def _inventory_path(docs_root, inventory=None) -> Optional[Path]:
    """Опись выгрузки для сверки: явная (параметр inventory прогона — гейт переноса на
    временной копии docs/), иначе inventory.md в корне комплекта или рядом с ним
    (kitcheck.fs.find_kit_file). Не найдена — None: доводы по описи не срабатывают."""
    if inventory is not None:
        return Path(inventory)
    return _fs.find_kit_file(docs_root, "inventory.md") if docs_root is not None else None


def _copy_method_page_contour(src_text: str, docs_root, inventory=None) -> str:
    """Основа маркера сервиса («КК») у страницы-копии метода — по описи req_type integration и
    титул «Копия [<маркер>] …»; иначе пусто (чужие пункты не снимаются)."""
    inv = _inventory_path(docs_root, inventory)
    if inv is None:
        return ""
    title = _frontmatter_title(src_text) or ""
    m = _COPY_TITLE_MARK_RE.match(title)
    pid = _page_id_of(src_text)
    if not m or not pid:
        return ""
    _t, req_type = _inventory_req_types(inv).get(pid, ("", ""))
    return m.group(1).split("_")[0].strip() if req_type.startswith("integration") else ""


def _subservice(rel_parts: Tuple[str, ...]) -> str:
    """Подсервис по пути «srs/<подсервис>/…»; иначе пусто."""
    return rel_parts[1] if len(rel_parts) > 2 and rel_parts[0] == "srs" else ""


def _page_outside_subservice(pid: str, main_file: Path, files: List[Path], docs_root: Path,
                             inventory: Optional[Path] = None) -> bool:
    """Доп. страница карточки вызова используется по ссылке: главная у другой карточки комплекта
    вне группы; по описи — копия страницы метода владельца (req_type integration и титул
    «Копия …»: копия в папке подсервиса, КК CALL-EXT-030 ← 2464250463, решение владельца канона
    2026-11-02); либо её целевой каталог — в другом подсервисе (в том числе в общей части
    srs/bc-component/…). Страницы того же подсервиса — ЭФ, процесс, собственная интеграционная
    страница прошлой редакции «(Этап 1)» (integration без «Копия») — нет."""
    group = {f.resolve() for f in files}
    if any(p.resolve() not in group for p in _main_page_index(docs_root).get(pid, [])):
        return True
    inv = _inventory_path(docs_root, inventory)
    if inv is None:
        return False
    title, req_type = _inventory_req_types(inv).get(pid, ("", ""))
    if req_type.startswith("integration") and _COPY_TITLE_RE.match(title):
        return True
    try:
        own = _subservice(main_file.resolve().relative_to(docs_root.resolve()).parts)
    except ValueError:
        return False
    target = _inventory_targets(inv).get(pid, "")
    tsub = _subservice(tuple(target.split("/")))
    return bool(own and tsub and tsub != own)


@_fs.memoize(copy=dict)
def _page_artifact_index(docs_root: Path) -> Dict[str, List[Path]]:
    """page_id → карточки комплекта, у которых он стоит в confluence_page_ids в любой
    позиции (группы selfcheck строятся по первой). Строится один раз за прогон: кэш
    сессии selfcheck, а не чтение всего комплекта на каждую карточку."""
    out: Dict[str, List[Path]] = {}
    for p in _kit_md(docs_root):
        for pid in page_ids(read_frontmatter(p) or {}):
            out.setdefault(pid, []).append(p)
    return out


_CALL_CARD_LINK_RE = re.compile(r"\[(CALL-(?:EXT|INT|MOD)-\d{3})[^\]]*\]\(([^)\s#]+\.md)")


def _linked_call_cards(card_text: str, main_file: Path) -> List[Tuple[str, str]]:
    """[(ID, текст)] карточек вызова, на которые ссылается карточка (по относительной ссылке
    «[CALL-…](…md)»); несуществующая цель пропускается (её ловит сторож ссылок)."""
    out: List[Tuple[str, str]] = []
    seen: set = set()
    for m in _CALL_CARD_LINK_RE.finditer(card_text):
        p = (main_file.parent / m.group(2)).resolve()
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        out.append((m.group(1), _fs.read_text(p, encoding="utf-8", errors="replace")))
    return out


def _group_linked_calls(fx: "_SourceCtx", main_type: Optional[str]) -> Optional[List[Tuple[str, str]]]:
    """Карточки вызова по ссылке для сторожа имён параметров — от группы, а не от главного файла
    (КК FUN-SYS-10 + карточка вызова той же страницы, 2026-11-09): ссылки главной карточки, если
    она держатель шагов или карточка вызова, и каждого неглавного держателя шагов группы
    (function / process / screen-form). Одиночная карточка — как прежде: только держатель шагов.
    Найденное в связанных карточках идёт i-строкой с их перечнем; не найденное нигде — ✗."""
    main_file = fx.main_file
    if main_file is None:
        return None
    out: List[Tuple[str, str]] = []
    if main_type in _STEP_HOLDER_TYPES or (main_type == "contract-call" and len(fx.files) > 1):
        out.extend(_linked_call_cards(fx.card_text, main_file))
    for f in fx.files[1:]:
        t = _fs.read_text(f, encoding="utf-8", errors="replace")
        ft = re.search(r"^type:\s*([\w-]+)", _fm_head(t), re.M)
        if ft and ft.group(1) in _STEP_HOLDER_TYPES:
            out.extend(c for c in _linked_call_cards(t, f) if c[0] not in {i for i, _ in out})
    if main_type in _STEP_HOLDER_TYPES or out:
        return out
    return None


def _page_cards(docs_root: Optional[Path], pid: str, files: List[Path],
                skip_dir: Optional[Path] = None) -> List[Tuple[str, str]]:
    """[(путь, текст)] карточек комплекта с этой страницей в confluence_page_ids в любой позиции,
    кроме группы сверки; skip_dir — каталог, уже прочитанный вызывающим как соседи."""
    if docs_root is None or not pid:
        return []
    return [(f.relative_to(docs_root).as_posix(),
             strip_html_comments(_fs.read_text(f, encoding="utf-8", errors="replace")))
            for f in _page_artifact_index(docs_root).get(pid, [])
            if f not in files and f.parent != skip_dir]


def _extra_table_line(line: str, tag: str) -> str:
    """Строка сверки таблиц для доп. страницы: начало сохраняется (видимость при ✓), метка — в
    конце; строки примеров потери — как есть, они идут под строкой с меткой."""
    return line if line.startswith(" ") else f"{line} ({tag})"


def _extra_page_tag(p: Path, p_text: str) -> str:
    return f"доп. страницы {_page_id_of(p_text)} «{_frontmatter_title(p_text) or p.stem}»"


def _extra_page_line(line: str, tag: str) -> str:
    """Строка сторожа литералов для доп. страницы: «… источника» → «… <tag>»; строки класса
    «⚠ примеры:» и i-строки сохраняют начало (класс и видимость при ✓) и получают метку."""
    if "кавычечные литералы источника" in line:
        return line.replace("кавычечные литералы источника", f"кавычечные литералы {tag}", 1)
    if line.startswith("⚠ примеры:"):
        return line.replace("⚠ примеры:", f"⚠ примеры: {tag}:", 1)
    return f"{line} ({tag})"


def _table_literal_extras(fx: "_SourceCtx") -> List[Tuple[Path, Optional[Path]]]:
    """Доп. страницы для сверки таблиц и кавычечных литералов: [(страница, карточка-владелец)].
    У доп. страниц главной владелец — None (главная), у доп. страниц неглавных файлов группы —
    их файл. Без повторов, только найденные файлы выгрузки."""
    out: List[Tuple[Path, Optional[Path]]] = []
    seen: set = set()
    items = ([(p, None) for p in (fx.amnesty_sources or [])]
             + [(p, o) for p, o in (fx.group_extra_sources or [])])
    for p, owner in items:
        if p not in seen and p.is_file():
            seen.add(p)
            out.append((p, owner))
    return out


def _page_id_of(source_text: str) -> str:
    """page_id страницы выгрузки (confluence_page_id шапки) или пусто."""
    m = re.search(r"^confluence_page_id:\s*['\"]?(\d+)", _fm_head(source_text), re.M)
    return m.group(1) if m else ""


def _rc_source_comparison(fx: "_SourceCtx") -> Tuple[List[str], bool]:
    files, docs_root, card_text, combined, main_file, src_text = fx.files, fx.docs_root, fx.card_text, fx.combined, fx.main_file, fx.src_text
    report: List[str] = []
    ok = True
    if src_text is not None:
        # сторож маркеров шагов — только для типов с таблицей шагов /
        # поведением (process, agent, function, notification): на
        # страницах прочих типов составные номера — нумерация секций и
        # строк, не шаги (экзамен inkasso 2026-08-16: сущности МД с
        # секциями 1.1… дали ложные «отсутствуют 72 из 72»). Тип не
        # распознан — консервативно применяем.
        m_type = re.search(r"^type:\s*([\w-]+)", _fm_head(card_text), re.M)
        steps_apply = (m_type is None or m_type.group(1) in
                       {"process", "agent", "function", "notification"})
        debts_text = ""
        if docs_root is not None and (Path(docs_root) / "traceability-matrix.md").is_file():
            debts_text = _fs.read_text(Path(docs_root) / "traceability-matrix.md",
                                       encoding="utf-8", errors="replace")
        # тонкая карточка вызова (шаблон contract-call, решение владельца канона
        # 2026-11-01, КК CALL-EXT-007…034): состав параметров и примеры — в базовом
        # контракте / на странице среза, имена параметров HTML-сеток и литералы из
        # таблиц источника не требуются; литералы прозы — как прежде
        thin_call = (thin_call_home(card_text, debts_text)
                     if m_type is not None and m_type.group(1) == "contract-call"
                     else None)
        thin_label = "тонкая карточка вызова"
        is_base = m_type is not None and m_type.group(1) == "external-integration"
        # карточки вызова потребителей, переданные явно (--call): только у базового контракта
        call_texts = ([(Path(p).name, _fs.read_text(Path(p), encoding="utf-8", errors="replace"))
                       for p in (fx.call_cards or [])] if is_base and fx.call_cards else None)
        if fx.call_cards and not is_base:
            report.append("i --call: карточки вызова учитываются только у базового контракта "
                          "(type: external-integration) — не применено")
        # держатель шагов со строкой «**Базовый контракт:** [EXTINT|INTC|LIBC|MOD-…]» (функция или
        # процесс от страницы метода — дом шагов потребителя, решение владельца 2026-11-08, КК
        # FUN-SYS-41 ← SVFE 2184432769): состав страницы метода — в базовом контракте, освобождение
        # то же, что у тонкой карточки вызова; литералы прозы и шаги — как прежде. Признак — форма
        # строки шапки карточки
        holder_base = (base_contract_ref(card_text)
                       if m_type is not None and m_type.group(1) in _BASE_HOLDER_TYPES else None)
        if holder_base:
            thin_call = f"в базовом контракте {holder_base}"
            thin_label = "состав страницы метода"
            report.append(f"i паспорт и состав страницы метода — в базовом контракте {holder_base}: "
                          "лейбл-секции паспорта (К-34, К-25d), таблицы и имена параметров страницы не "
                          "сверяются, литералы прозы и шаги — как прежде")

        def _owner_thin(owner: Optional[Path]):
            # освобождение тонкой карточки вызова — свойство карточки-владельца доп. страницы:
            # у доп. страниц неглавного файла группы — по его шапке, не по главной (замечание
            # ОНБ-В 66/72: карточка вызова, ставшая неглавной, не теряет освобождения)
            if owner is None:
                return thin_call
            o_text = _fs.read_text(owner, encoding="utf-8", errors="replace")
            if re.search(r"^type:\s*contract-call\s*$", _fm_head(o_text), re.M):
                return thin_call_home(o_text, debts_text)
            return None

        def _owner_label(owner: Optional[Path]) -> str:
            return thin_label if owner is None else "тонкая карточка вызова"

        def _owner_tag(p: Path, p_text: str, owner: Optional[Path]) -> str:
            tag = _extra_page_tag(p, p_text)
            return tag if owner is None else f"{tag} карточки {owner.name}"
        # карточки вызова, на которые ссылается держатель шагов: таблица шага вынесена в них
        # (решение владельца канона 2026-11-02) — имена параметров ищутся и там
        linked_calls = _group_linked_calls(fx, m_type.group(1) if m_type is not None else None)
        # значение страницы перенесено, если оно есть в любой карточке с этой страницей в
        # confluence_page_ids (главной или дополнительной): вердикт — по объединению таких карточек
        src_report, src_ok = check_source_tables(
            combined, src_text, thin_call=thin_call, linked_calls=linked_calls, thin_label=thin_label,
            base_contract=is_base,
            page_artifacts=_page_cards(docs_root, _page_id_of(src_text), files) or None)
        # сводные типы (глоссарий, видения) — как у литералов: доп. страницы они обобщают, а не
        # переносят; число несверенных страниц видно приёмке
        extra_sources = _table_literal_extras(fx)
        if m_type is not None and m_type.group(1) in _NO_LITERALS_TYPES and extra_sources:
            src_report = src_report + [
                f"i таблицы источника: доп. страниц ×{len(extra_sources)} не сверялось: сверка "
                f"доп. страниц не применяется к {_NO_LITERALS_TYPES[m_type.group(1)]}"]
            extra_sources = []
        for p, owner in extra_sources:
            p_text = _fs.read_text(p, encoding="utf-8", errors="replace")
            p_rep, p_ok = check_source_tables(
                combined, p_text, thin_call=_owner_thin(owner), linked_calls=linked_calls,
                thin_label=_owner_label(owner), base_contract=is_base,
                page_artifacts=_page_cards(docs_root, _page_id_of(p_text), files) or None)
            tag = _owner_tag(p, p_text, owner)
            src_report = src_report + [_extra_table_line(ln, tag) for ln in p_rep]
            src_ok = src_ok and p_ok
        # волна 9 ОНБ-В (ЗК-04): таблицы без дословных значений, изображения без
        # следа, перечень таблиц источника — только ⚠ / i
        readme = main_file.parent / "README.md" if main_file is not None else None
        readme_text = (_fs.read_text(readme, encoding="utf-8", errors="replace")
                       if readme is not None and readme.is_file() and readme != main_file else "")
        src_report = src_report + check_unchecked_tables(combined, src_text, readme_text)
        ids = re.findall(r"^(?:id|partOf):\s*['\"]?([\w.-]+)", combined, re.M)
        src_report = src_report + check_image_trace(combined, src_text, debts_text, ids)
        src_report = src_report + source_tables_summary(src_text)
        # title сверяется и у README-реестров: он дословный из главной
        # страницы-оглавления, раз она есть (решение 2026-08-16 v2:
        # title — трассировка к источнику, «собственный» — только у
        # файлов БЕЗ страницы-источника, а такие сюда не попадают;
        # расширенное наименование реестра живёт в H1)
        # карточка-часть группы (partOf без title по шаблону controls:
        # README с id несёт title, части — partOf): наименование ищется
        # в файле группы с `id:` — иначе прибор бракует «ПОТЕРЯ
        # НАИМЕНОВАНИЯ» там, где title дословно перенесён в README
        # (прогон гейта lk-mp 2026-10-13, две группы контролей).
        # Расхождение title держателя с источником — по-прежнему брак.
        ttl_text, ttl_holder = card_text, None
        if (_frontmatter_title(card_text) is None
                and re.search(r"^partOf:", card_text[:600], re.M)):
            for f in files[1:]:
                t = _fs.read_text(f, encoding="utf-8")
                if (re.search(r"^id:", t[:600], re.M)
                        and _frontmatter_title(t) is not None):
                    ttl_text, ttl_holder = t, f
                    break
        # карточка-агрегатор (решение владельца канона 2026-10-30): title доп. страниц —
        # из файлов выгрузки, которые selfcheck передаёт по индексу (amnesty_sources —
        # страницы карточки после главной); заголовки ищутся во всей группе
        extra_pages = []
        for p in (fx.amnesty_sources or []):
            if p.is_file():
                p_text = _fs.read_text(p, encoding="utf-8", errors="replace")
                p_title = _frontmatter_title(p_text)
                if p_title:
                    extra_pages.append((_page_id_of(p_text), p_title))
        # карточка вызова: доп. страница вне её подсервиса — страница метода или общая функция,
        # используется по ссылке, титул разделом не обязателен (решение владельца канона
        # 2026-11-02, уточнение правила 01.11; КК CALL-EXT-011/036/037/038 ← 2464250512/2464250492)
        by_link: List[str] = []
        if (m_type is not None and m_type.group(1) == "contract-call" and docs_root is not None
                and main_file is not None):
            by_link = [i for i, _t in extra_pages
                       if i and _page_outside_subservice(i, main_file, files, Path(docs_root),
                                                       fx.inventory)]
            extra_pages = [(i, t) for i, t in extra_pages if i not in by_link]
        ttl_report, ttl_ok = check_title(
            ttl_text, src_text, extra_titles=[t for _i, t in extra_pages],
            corpus=combined, file_name=(ttl_holder or main_file).name,
            extra_ids=[i for i, _t in extra_pages])
        if by_link:
            ttl_report = ttl_report + [
                f"i title доп. страниц по ссылке (метод / общая функция вне подсервиса): "
                f"{', '.join(by_link)} — разделом карточки вызова не обязательны"]
        if ttl_holder is not None:
            ttl_report = [
                ln.replace("title:", f"title (часть partOf без title, "
                           f"держатель — {ttl_holder.name}):", 1)
                for ln in ttl_report]
        # карточка вызова шаги не несёт (шаблон contract-call: только привязка данных; алгоритм —
        # у функции-держателя, решение владельца канона 2026-11-02, КК CALL-EXT-038 +
        # FUN-CL-21): у группы, где главная — contract-call, поведение сверяется по держателю
        # шагов той же группы (function / process / screen-form); держателя нет — по главной,
        # как прежде (реальная потеря)
        bh_text, bh_holder = card_text, None
        if m_type is not None and m_type.group(1) == "contract-call":
            for f in files[1:]:
                t = _fs.read_text(f, encoding="utf-8", errors="replace")
                ft = re.search(r"^type:\s*([\w-]+)", _fm_head(t), re.M)
                if ft and ft.group(1) in _STEP_HOLDER_TYPES:
                    bh_text, bh_holder = t, f
                    break
        bh_report, bh_ok = check_behavior_nesting(bh_text, src_text)
        if bh_holder is not None:
            bh_report = [f"[{bh_holder.name}] {ln}" for ln in bh_report]
        st_report, st_ok = (check_step_markers(combined, src_text)
                            if steps_apply else ([], True))
        # К-34: лейбл-секции паспорта — только функции (у data-model
        # паспорт-таблица — легитимный слот шаблона). Держатель шагов со строкой
        # «Базовый контракт:» — паспорт метода живёт в базовом контракте, К-34 и
        # К-25d к нему (и к группе, где он главный) не применяются
        if m_type is not None and m_type.group(1) == "function" and not holder_base:
            ls_report, ls_ok = check_label_sections(combined, src_text)
            report.extend(ls_report)
            ok = ok and ls_ok
        # К-32: анти-дефейс теговых упоминаний источника (пилот-2:
        # теги удалялись, чтобы увести упоминания от сторожа)
        sm_report, sm_ok = check_source_tag_mentions(combined, src_text,
                                                     docs_root)
        report.extend(sm_report)
        ok = ok and sm_ok
        # К-29: инвариант тяжёлых ячеек — лейбло- и макето-независимый; у карточек
        # контрактов (базовый контракт внешней АС, внутренний контракт, карточка вызова)
        # тяжёлая ячейка паспорта законно остаётся строкой таблицы §1 (шаблон
        # contract-call.md, раздел A; решение владельца 2026-11-08, на INTC и CALL —
        # 2026-11-09) — там это i-строка
        card_type = m_type.group(1) if m_type is not None else ""
        contract_cards = []
        for f in files:
            t = _fs.read_text(f, encoding="utf-8", errors="replace")
            ft = re.search(r"^type:\s*([\w-]+)", _fm_head(t), re.M)
            if ft and ft.group(1) in _PASSPORT_ROW_TYPES:
                contract_cards.append((ft.group(1), strip_html_comments(t)))
        hc_report, hc_ok = check_heavy_cells(
            combined, src_text,
            passport_rows_ok=card_type in _PASSPORT_ROW_TYPES, card_type=card_type,
            passport_rows=passport_row_keys(contract_cards))
        report.extend(hc_report)
        ok = ok and hc_ok
        # К-25d: профили вынесенных лейбл-секций против эталона
        if not holder_base:
            hp_report, hp_ok = check_heavy_pair_structure(
                combined, src_text, own_contour=_copy_method_page_contour(src_text, docs_root, fx.inventory))
            report.extend(hp_report)
            ok = ok and hp_ok
        # К-26: по-шаговая структура тел (типы с поведением)
        if steps_apply:
            # FB-16 КК (fun-sys-16): вторая карточка группы (intc) несёт
            # свои абзацы под теми же номерами шагов — объединение группы
            # ложно расходится с источником; сначала главная карточка,
            # объединение — только если главная не прошла (шаги могли
            # быть разложены по карточкам группы)
            sb_report, sb_ok = check_step_body_structure(
                strip_html_comments(card_text), src_text)
            if not sb_ok:
                sb_report, sb_ok = check_step_body_structure(combined, src_text)
            report.extend(sb_report)
            ok = ok and sb_ok
        # К-24: уплощение вложенности + потеря паспортного слоя «Что
        # делает функция» (типы с поведением — как у маркеров шагов)
        if steps_apply:
            nd_report, nd_ok = check_nesting_depth(combined, src_text)
            report.extend(nd_report)
            ok = ok and nd_ok
            # К-24-лейбл и лейбл-секции СНЯТЫ (2026-08-18, аудит
            # fun-sys-03 с аналитиком): шаблон function не имеет слота
            # «паспорт» — содержимое ячеек раскладывается по разделам
            # шаблона (Поведение/Вызов/Доступность); требование
            # дословного лейбла толкало исполнителей в двойную
            # структуру. Содержимое и структуру ячеек держат К-29
            # (не в |-строке) и check_heavy_pair_structure (профиль +
            # потеря), лейбло-независимо.
        # sibling-корпус — только внутри комплекта (docs_root задан:
        # selfcheck-режим): в CLI-прогоне рядом с карточкой может лежать
        # что угодно, включая сам источник, — фолбэк глушил бы сверку
        sib_txt = (strip_html_comments(
            "\n\n".join(_fs.read_text(f, encoding="utf-8")
                        for f in sorted(main_file.parent.glob("*.md"))
                        if f not in files))
            if docs_root is not None else None)
        if m_type is not None and m_type.group(1) in _NO_LITERALS_TYPES:
            ql_report, ql_ok = [
                f"i {main_file.name}: сторож литералов не применяется к "
                f"{_NO_LITERALS_TYPES[m_type.group(1)]}"], True
        else:
            # артефакты той же страницы (решение владельца канона 2026-10-30): карточки
            # комплекта с главной страницей группы в confluence_page_ids в любой позиции,
            # кроме группы и соседей каталога (они уже в sib_txt)
            page_art = None
            if docs_root is not None:
                _pids = page_ids(read_frontmatter(main_file) or {})
                page_art = _page_cards(docs_root, _pids[0] if _pids else "", files,
                                       skip_dir=main_file.parent) or None
            ql_report, ql_ok = check_quoted_literals(combined, src_text,
                                                     sibling_text=sib_txt,
                                                     page_artifacts=page_art,
                                                     thin_call=thin_call, thin_label=thin_label,
                                                     call_texts=call_texts)
            # доп. страницы карточки (решение владельца канона 2026-11-01, замер КК: 59 потерь в
            # 3 парах из 60): литералы сверяются как у главной — та же группа, sidecar, соседи,
            # артефакты страницы и освобождения; строки — с page_id и title страницы. Страница
            # вне выгрузки сюда не попадает (selfcheck передаёт только найденные файлы)
            # доп. страница-функция у карточки вызова / экрана группы с карточкой вызова (решение
            # владельца канона 2026-11-02): тексты шагов функции сверяет карточка функции
            call_group = m_type is not None and m_type.group(1) in ("contract-call", "screen-form") \
                and any(re.search(r"^type:\s*contract-call\s*$",
                                  _fm_head(_fs.read_text(f, encoding="utf-8", errors="replace")),
                                  re.M) for f in files)
            # доп. страницы неглавных файлов группы — так же (замечание ОНБ-В 72, 2026-11-07)
            for p, owner in _table_literal_extras(fx):
                p_text = _fs.read_text(p, encoding="utf-8", errors="replace")
                # карточки самой доп. страницы — к карточкам главной, как было
                p_art = list(page_art or [])
                p_art += [a for a in _page_cards(docs_root, _page_id_of(p_text), files,
                                                 skip_dir=main_file.parent) if a not in p_art]
                p_rep, p_ok = check_quoted_literals(
                    combined, p_text, sibling_text=sib_txt, page_artifacts=p_art or None,
                    thin_call=_owner_thin(owner), thin_label=_owner_label(owner),
                    steps_text_free=call_group and _FUNCTION_PAGE_RE.search(p_text) is not None)
                tag = _owner_tag(p, p_text, owner)
                ql_report += [_extra_page_line(ln, tag) for ln in p_rep]
                ql_ok = ql_ok and p_ok
        report.extend(src_report)
        report.extend(ttl_report)
        report.extend(bh_report)
        report.extend(st_report)
        report.extend(ql_report)
        ok = ok and src_ok and ttl_ok and bh_ok and st_ok and ql_ok
    return report, ok


# реестр запускается всегда; сверка с источником (source_cell_completeness,
# source_comparison) — только при --sources (src_text не None), миграционный слой
SOURCE_CHECKS: List[Check] = [
    Check("clean_document", _rc_clean_document, scope="file"),
    Check("form_entity_names", _rc_form_entity_names, scope="file"),
    Check("tuz_formula", _rc_tuz_formula, scope="file"),
    Check("source_cell_completeness", _rc_source_cell_completeness, scope="file"),
    Check("tagged_mentions", _rc_tagged_mentions, scope="file"),
    Check("behavior_numbering", _rc_behavior_numbering, scope="file"),
    Check("notification_structure", _rc_notification_structure, scope="file"),
    Check("source_comparison", _rc_source_comparison, scope="file"),
    Check("outside_template_section", _rc_outside_template_section, scope="file"),
]
