# tests/test_aggregator_title_literals.py
"""Карточки-агрегаторы нескольких страниц (решение владельца канона 2026-10-30, разбор КК
1402d3d): title-страж принимает агрегатор, если наименование каждой страницы-источника стоит
дословно заголовком раздела; корпус литералов — и все артефакты комплекта с той же страницей
в confluence_page_ids (PROC-047 ↔ glossary.md)."""
from pathlib import Path

import pytest

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.checks.card_source import check_quoted_literals, check_title


def src(title: str, pid: str = "1", body: str = "текст\n") -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n{body}"


def card(title: str, pids: str, body: str, type_: str = "data-model") -> str:
    return (f"---\nid: DM-001\ntitle: '{title}'\ntype: {type_}\nconfluence_page_ids: [{pids}]\n"
            f"---\n\n# {title}\n\n{body}")


BOTH = "## [КК_СК] Список статусов\n\nтекст\n\n### 2. [КК_ЛК] Справочник лимитов\n\nтекст\n"


# ---------------------------------------------------------------- title

def test_aggregator_titles_as_headings_pass():
    c = card("Справочники", "'1', '2'", BOTH)
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), extra_titles=["[КК_ЛК] Справочник лимитов"])
    assert ok, rep
    assert rep == ["title: карточка-агрегатор 2 страниц — наименования источников заголовками "
                   "разделов ✓"]


def test_aggregator_without_headings_lists_missing():
    c = card("Справочники", "'1', '2'", "## Статусы\n\nтекст\n")
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), extra_titles=["[КК_ЛК] Справочник лимитов"])
    assert not ok
    assert rep == ["title: карточка-агрегатор 2 страниц — нет заголовков по страницам: "
                   "'[КК_СК] Список статусов'; '[КК_ЛК] Справочник лимитов' ✗ ПОТЕРЯ НАИМЕНОВАНИЯ"]


def test_dictionaries_single_page():
    ok_card = card("Справочники", "'1'", "## [КК_СК] Список статусов\n\nтекст\n")
    rep, ok = check_title(ok_card, src("[КК_СК] Список статусов"), file_name="dictionaries.md")
    assert ok and "карточка-агрегатор 1 страниц" in rep[0], rep
    bad = card("Справочники", "'1'", "## Статусы\n\nтекст\n")
    rep, ok = check_title(bad, src("[КК_СК] Список статусов"), file_name="dictionaries.md")
    assert not ok and "нет заголовков по страницам: '[КК_СК] Список статусов'" in rep[0], rep


def test_heading_searched_in_group_corpus():
    # заголовок второй страницы — в другой карточке группы (корпус combined)
    c = card("Справочники", "'1', '2'", "## [КК_СК] Список статусов\n\nтекст\n")
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), extra_titles=["[КК_ЛК] Справочник лимитов"],
                          corpus=c + "\n\n### [КК_ЛК] Справочник лимитов\n")
    assert ok, rep


def test_equal_title_counts_main_page_only():
    # решение владельца 2026-11-01 (вариант а): равенство title засчитывает только главную
    # страницу; title доп. страниц обязаны быть заголовками разделов
    c = card("[КК] Процесс", "'1', '2', '3'", "## Шаги\n", type_="process")
    rep, ok = check_title(c, src("[КК] Процесс"), extra_titles=["Другая", "Третья"],
                          extra_ids=["2", "3"])
    assert not ok
    assert rep == ["title: дословно перенесён ('[КК] Процесс') ✓",
                   "title доп. страниц: нет заголовков разделов по страницам: 2 'Другая'; "
                   "3 'Третья' ✗ ПОТЕРЯ НАИМЕНОВАНИЯ"], rep


@pytest.mark.parametrize("type_, fname, kind", [
    ("glossary", "glossary.md", "глоссария"), ("vision", "service-vision.md", "видения сервиса"),
    ("domain-vision", "domain-vision.md", "видения домена"), ("data-model", "README.md", "оглавления")])
def test_summary_and_readme_extra_titles_not_checked(type_, fname, kind):
    # решение владельца 2026-11-01 (вариант 2): оглавления и сводки — i-строка, не ✗
    c = card("[КК] Сводка", "'1', '2'", "## Термины\n", type_=type_)
    rep, ok = check_title(c, src("[КК] Сводка"), extra_titles=["Другая"], extra_ids=["2"],
                          file_name=fname)
    assert ok, rep
    assert rep == ["title: дословно перенесён ('[КК] Сводка') ✓",
                   f"i title доп. страниц (1) не сверяется у {kind} — титулы страниц заголовками "
                   "разделов быть не обязаны"], rep


def test_equal_title_extra_pages_as_headings_pass():
    c = card("[КК] Процесс", "'1', '2', '3'", "## Другая\n\n## Третья\n", type_="process")
    rep, ok = check_title(c, src("[КК] Процесс"), extra_titles=["Другая", "Третья"],
                          extra_ids=["2", "3"])
    assert ok and rep == ["title: дословно перенесён ('[КК] Процесс') ✓",
                          "title доп. страниц (2): наименования заголовками разделов ✓"], rep


def test_equal_title_single_page_unchanged():
    # НЕсрабатывание: одна страница — одна строка, как прежде
    c = card("[КК] Глоссарий", "'1'", "## Термины\n", type_="glossary")
    rep, ok = check_title(c, src("[КК] Глоссарий"))
    assert ok and rep == ["title: дословно перенесён ('[КК] Глоссарий') ✓"]


def test_base_contract_stripped_marker_extra_page_checked():
    # knosis-001: title базового без маркера страницы-копии засчитывает главную, вторая
    # страница обязана быть заголовком раздела
    c = ("---\nid: EXTINT-KNOSIS-001\ntitle: 'КНОСИС_API_Запрос выписки ЕГРИП для ИП'\n"
         "type: external-integration\nconfluence_page_ids: [11, 12]\n---\n\n"
         "# EXTINT-KNOSIS-001. Запрос выписки ЕГРИП\n\n## 1. Краткое описание\n")
    main = src("Копия [КК] КНОСИС_API_Запрос выписки ЕГРИП для ИП", pid="11")
    rep, ok = check_title(c, main, extra_titles=["Описание допустимых кодов"], extra_ids=["12"])
    assert not ok and rep[0].startswith("title: перенесён без маркера контура"), rep
    assert "12 'Описание допустимых кодов' ✗ ПОТЕРЯ НАИМЕНОВАНИЯ" in rep[1], rep
    rep, ok = check_title(c + "\n### Описание допустимых кодов\n", main,
                          extra_titles=["Описание допустимых кодов"], extra_ids=["12"])
    assert ok, rep


# ---------------------------------------------------------------- несрабатывание

def test_ordinary_card_mismatch_still_fails():
    # одна страница, файл не dictionaries.md — расхождение title остаётся ✗, заголовок не спасает
    c = card("Справочники", "'1'", "## [КК_СК] Список статусов\n\nтекст\n")
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), file_name="dm-001-x.md")
    assert not ok and rep[0].startswith("title: расходится с источником ✗"), rep


def test_heading_must_be_verbatim():
    # заголовок с изменённым наименованием — не перенос
    c = card("Справочники", "'1', '2'", "## [КК_СК] Список статусов\n\n### [КК_ЛК] Справочник лимитов карты\n")
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), extra_titles=["[КК_ЛК] Справочник лимитов"])
    assert not ok and "'[КК_ЛК] Справочник лимитов'" in rep[0], rep


def test_any_heading_level_counts():
    # уровень заголовка не ограничен (решение владельца 2026-10-30): #### — тоже заголовок раздела
    c = card("Справочники", "'1', '2'",
             "## [КК_СК] Список статусов\n\n### Типы\n\n#### [КК_ЛК] Справочник лимитов\n\nтекст\n")
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), extra_titles=["[КК_ЛК] Справочник лимитов"])
    assert ok, rep


def test_name_without_tag_fails():
    # НЕсрабатывание: наименование без ведущего тега страницы — не дословный перенос
    c = card("Справочники", "'1', '2'",
             "## [КК_СК] Список статусов\n\n#### Справочник лимитов\n\nтекст\n")
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), extra_titles=["[КК_ЛК] Справочник лимитов"])
    assert not ok and "нет заголовков по страницам: '[КК_ЛК] Справочник лимитов'" in rep[0], rep


def test_name_in_paragraph_or_table_not_heading():
    # НЕсрабатывание: наименование в абзаце или ячейке таблицы — не заголовок раздела
    c = card("Справочники", "'1', '2'",
             "## [КК_СК] Список статусов\n\n[КК_ЛК] Справочник лимитов\n\n"
             "| Справочник | Описание |\n|---|---|\n| [КК_ЛК] Справочник лимитов | x |\n")
    rep, ok = check_title(c, src("[КК_СК] Список статусов"), extra_titles=["[КК_ЛК] Справочник лимитов"])
    assert not ok and "'[КК_ЛК] Справочник лимитов'" in rep[0], rep


# ---------------------------------------------------------------- литералы

SRC_LIT = src("[КК] Групповые операции", body="Кнопка «Подписание пакета» и статус «Исчезновение».\n")


def test_literal_in_page_artifact_not_lost():
    rep, ok = check_quoted_literals("карточка без литералов", SRC_LIT,
                                    page_artifacts=[("glossary.md", "Подписание пакета; Исчезновение")])
    assert ok, rep
    assert rep[0].startswith("i кавычечные литералы ×2 найдены в артефактах той же страницы "
                             "(glossary.md), не в группе сверки"), rep


def test_literal_nowhere_still_fails():
    rep, ok = check_quoted_literals("карточка без литералов", SRC_LIT,
                                    page_artifacts=[("glossary.md", "Подписание пакета")])
    assert not ok
    assert any("отсутствуют 1 из 2" in r and "Исчезновение" in r for r in rep), rep


def test_artifact_without_literal_changes_nothing():
    rep, ok = check_quoted_literals("карточка без литералов", SRC_LIT,
                                    page_artifacts=[("glossary.md", "другой текст")])
    assert not ok and not any("артефактах той же страницы" in r for r in rep)


# ---------------------------------------------------------------- selfcheck

def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_selfcheck_literals_from_glossary_same_page(tmp_path):
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(srcs / "a.md", src("[КК] Групповые операции", "111222",
                            "Кнопка «Подписание пакета» и статус «Исчезновение».\n"))
    make(srcs / "g.md", src("[КК] Глоссарий", "333444", "Термины.\n"))
    make(docs / "srs/bc/process/proc-047.md",
         "---\nid: PROC-047\ntitle: '[КК] Групповые операции'\ntype: process\n"
         "confluence_page_ids: ['111222']\n---\n\n# PROC-047. Групповые операции\n\nтекст процесса\n")
    make(docs / "glossary.md",
         "---\nid: GLO-001\ntitle: '[КК] Глоссарий'\ntype: glossary\n"
         "confluence_page_ids: ['333444', '111222']\n---\n\n# Глоссарий\n\n"
         "| Термин | Определение |\n|---|---|\n| **Подписание пакета** | Исчезновение пакета. |\n")
    report, _ok = selfcheck.run(docs, srcs)
    text = "\n".join(report)
    assert any(ln.startswith("✓ srs") and "proc-047.md" in ln for ln in report), text
    assert "найдены в артефактах той же страницы (glossary.md)" in text, text


def test_selfcheck_aggregator_title_by_extra_page(tmp_path):
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(srcs / "a.md", src("[КК_СК] Список статусов", "111222"))
    make(srcs / "b.md", src("[КК_ЛК] Справочник лимитов", "333444"))
    make(docs / "srs/bc/data-model/dictionaries.md",
         card("Справочники сервиса", "'111222', '333444'", "## [КК_СК] Список статусов\n\nтекст\n"))
    report, _ok = selfcheck.run(docs, srcs)
    text = "\n".join(report)
    # вторая страница взята из индекса выгрузки — её заголовка нет
    assert "нет заголовков по страницам: '[КК_ЛК] Справочник лимитов' ✗ ПОТЕРЯ НАИМЕНОВАНИЯ" in text, text


# ------------------------------------------- литералы доп. страниц (решение владельца 2026-11-01)

def _kit(tmp_path, extra_body: str, card_body: str, type_: str = "process", pids=("111222", "222333"),
         sidecar: str = ""):
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(srcs / "main.md", src("[КК] Процесс", "111222", "Кнопка «Сохранить».\n"))
    make(srcs / "extra.md", src("[КК] Процесс, часть 2", "222333", extra_body))
    ids = ", ".join(f"'{p}'" for p in pids)
    make(docs / "srs/bc/process/proc-001.md",
         f"---\nid: PROC-001\ntitle: '[КК] Процесс'\ntype: {type_}\nconfluence_page_ids: [{ids}]\n"
         f"---\n\n# PROC-001. Процесс\n\nКнопка «Сохранить».\n\n## [КК] Процесс, часть 2\n\n{card_body}\n")
    if sidecar:
        make(docs / "srs/bc/process/examples/r.json", sidecar)
    report, _ok = selfcheck.run(docs, srcs)
    return report, "\n".join(report)


def test_extra_page_prose_literal_lost_is_defect(tmp_path):
    report, text = _kit(tmp_path, "Сообщение «Заявка отклонена».\n", "текст без сообщения")
    assert any(ln.startswith("✗ srs") and "proc-001.md" in ln for ln in report), text
    assert ("кавычечные литералы доп. страницы 222333 «[КК] Процесс, часть 2»: в карточке "
            "отсутствуют 1 из 1 ✗") in text, text
    assert "кавычечные литералы доп. страниц" in text and "сверяются по каждой" in text, text


def test_extra_page_literal_found_in_card_or_sidecar(tmp_path):
    report, text = _kit(tmp_path, "Сообщение «Заявка отклонена».\n", "Сообщение «Заявка отклонена».")
    assert any(ln.startswith("✓ srs") and "proc-001.md" in ln for ln in report), text
    report, text = _kit(tmp_path / "s", "Поле «ACCEPTED».\n", "Образец — [r](examples/r.json).",
                        sidecar='{"status": "ACCEPTED"}\n')
    assert any(ln.startswith("✓ srs") and "proc-001.md" in ln for ln in report), text


def test_extra_page_code_block_literal_is_examples_class(tmp_path):
    report, text = _kit(tmp_path, "Ответ:\n\n```json\n{\"status\": \"ACCEPTED\"}\n```\n", "текст")
    assert any(ln.startswith("✓ srs") and "proc-001.md" in ln for ln in report), text
    assert "⚠ примеры: доп. страницы 222333 «[КК] Процесс, часть 2»: значения примера" in text, text


def test_vision_type_not_checked(tmp_path):
    # НЕсрабатывание: сводка видения сервиса — сторож литералов не применяется
    report, text = _kit(tmp_path, "Цель «Цифровая экосистема».\n", "текст", type_="vision")
    assert "сторож литералов не применяется к видению сервиса" in text, text
    assert "кавычечные литералы доп. страницы" not in text, text


def test_extra_page_outside_export_does_not_break(tmp_path):
    report, text = _kit(tmp_path, "Сообщение «Заявка отклонена».\n", "текст",
                        pids=("111222", "999888"))
    assert "вне выгрузки, без сверки: 999888" in text, text
    assert any(ln.startswith("✓ srs") and "proc-001.md" in ln for ln in report), text


def test_single_page_card_unchanged(tmp_path):
    report, text = _kit(tmp_path, "Сообщение «Заявка отклонена».\n", "текст", pids=("111222",))
    assert "доп. страниц" not in text, text
    assert any(ln.startswith("✓ srs") and "proc-001.md" in ln for ln in report), text


# ------------- карточка вызова: доп. страница вне подсервиса — по ссылке (решение 2026-11-02)

def _call_kit(tmp_path, inv_target: str, other_main: bool = False, req_type: str = "function",
              inv_title: str = "Метод"):
    from app.scripts.CI.kitcheck.checks.card_run import run_check
    root = tmp_path / "kit"
    docs = root / "docs"
    call = docs / "srs/bc-issue/contract-call/external/call-ext-011.md"
    call.parent.mkdir(parents=True)
    call.write_text("---\nid: CALL-EXT-011\ntitle: '[КК_ВК] ЭФ Подтверждение'\ntype: contract-call\n"
                    "confluence_page_ids: ['111222', '333444']\n---\n\n# CALL-EXT-011. Вызов\n\n"
                    "Привязка данных.\n", encoding="utf-8")
    if other_main:
        fun = docs / "srs/bc-component/function/system/fun-sys-10.md"
        fun.parent.mkdir(parents=True)
        fun.write_text("---\nid: FUN-SYS-10\ntitle: 'Функция'\ntype: function\n"
                       "confluence_page_ids: ['333444']\n---\n\n# FUN-SYS-10. Ф\n", encoding="utf-8")
    (root / "inventory.md").write_text(
        "| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| 333444 | {inv_title} | [КК]-ЕСК | {req_type} | 10 | {inv_target} | x |\n", encoding="utf-8")
    srcs = tmp_path / "conf"
    srcs.mkdir()
    main = srcs / "main.md"
    main.write_text(src("[КК_ВК] ЭФ Подтверждение", "111222"), encoding="utf-8")
    extra = srcs / "extra.md"
    extra.write_text(src("Копия [КК] ЕСК_ОА_Проверка полномочий", "333444"), encoding="utf-8")
    rep, _ok = run_check([call], main, docs_root=docs, amnesty_sources=[extra])
    return "\n".join(rep)


def test_call_card_extra_page_of_common_part_by_link(tmp_path):
    text = _call_kit(tmp_path, "srs/bc-component/contract-call/external")
    assert "i title доп. страниц по ссылке (метод / общая функция вне подсервиса): 333444" in text, text
    assert "ПОТЕРЯ НАИМЕНОВАНИЯ" not in text, text


def test_call_card_extra_page_main_of_other_card_by_link(tmp_path):
    text = _call_kit(tmp_path, "вне SRS", other_main=True)
    assert "по ссылке (метод / общая функция вне подсервиса): 333444" in text, text


@pytest.mark.parametrize("req_type", ["screenItemForm", "process"])
def test_call_card_extra_page_same_subservice_still_checked(tmp_path, req_type):
    # НЕсрабатывание: доп. страница того же подсервиса (ЭФ, процесс) — титул разделом
    # обязателен, ✗ как (25)
    text = _call_kit(tmp_path, "srs/bc-issue/contract-call/external", req_type=req_type)
    assert "нет заголовков разделов по страницам: 333444" in text, text
    assert "по ссылке" not in text, text


def test_call_card_method_page_same_subservice_by_link(tmp_path):
    # страница метода (integration по описи), копия в папке подсервиса — по ссылке
    # (КК CALL-EXT-030 ← 2464250463, решение владельца 2026-11-02)
    text = _call_kit(tmp_path, "srs/bc-issue/contract-call/external", req_type="integration",
                     inv_title="Копия [КК] ЕСК_ОА_Запрос проверки актуальности данных")
    assert "по ссылке (метод / общая функция вне подсервиса): 333444" in text, text
    assert "ПОТЕРЯ НАИМЕНОВАНИЯ" not in text, text


def test_call_card_own_integration_page_same_subservice_checked(tmp_path):
    # НЕсрабатывание (КК CALL-EXT-017 ← 2166860148): собственная интеграционная страница
    # подсервиса прошлой редакции «(Этап 1)» — integration без «Копия», под (25)
    text = _call_kit(tmp_path, "srs/bc-issue/contract-call/external", req_type="integration",
                     inv_title="[КК_ВК] Параметры вызова процесса загрузки документов (Этап 1)")
    assert "нет заголовков разделов по страницам: 333444" in text, text
    assert "по ссылке" not in text, text


# ------------- пара слияния: доп. страница — близнец главной «(Этап N)» (решение 2026-11-02)

def test_merge_twin_stage_page_not_heading():
    c = card("[КК_ВК] Создать заявку", "'1', '2'", "## Шаги\n", type_="process")
    rep, ok = check_title(c, src("[КК_ВК] Создать заявку"),
                          extra_titles=["[КК_ВК] Создать заявку (Этап 1)"], extra_ids=["2"])
    assert ok, rep
    assert any("пара слияния — 2 '[КК_ВК] Создать заявку (Этап 1)'" in r for r in rep), rep
    assert not any("объявлено" in r for r in rep), rep


def test_merge_twin_declared_mentioned():
    c = card("[КК_ВК] Создать заявку", "'1', '2'",
             "## Шаги\n\nСлияние двух страниц — целевой и её близнеца «Этап 1».\n", type_="process")
    rep, ok = check_title(c, src("[КК_ВК] Создать заявку"),
                          extra_titles=["[КК_ВК] Создать заявку (Этап 1)"], extra_ids=["2"])
    assert ok and any("слияние объявлено в карточке" in r for r in rep), rep


def test_other_suffix_or_title_still_checked():
    # НЕсрабатывание: другой суффикс в скобках и другой title — ✗ (25)
    c = card("[КК_ВК] Создать заявку", "'1', '2', '3'", "## Шаги\n", type_="process")
    rep, ok = check_title(c, src("[КК_ВК] Создать заявку"),
                          extra_titles=["[КК_ВК] Создать заявку (архив)", "Другая страница"],
                          extra_ids=["2", "3"])
    assert not ok and "нет заголовков разделов по страницам: 2 '[КК_ВК] Создать заявку (архив)'" \
        in rep[-1] and "3 'Другая страница'" in rep[-1], rep
