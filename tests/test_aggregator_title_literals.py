# tests/test_aggregator_title_literals.py
"""Карточки-агрегаторы нескольких страниц (решение владельца канона 2026-10-30, разбор КК
1402d3d): title-страж принимает агрегатор, если наименование каждой страницы-источника стоит
дословно заголовком раздела; корпус литералов — и все артефакты комплекта с той же страницей
в confluence_page_ids (PROC-047 ↔ glossary.md)."""
from pathlib import Path

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


def test_equal_title_passes_first():
    # glossary.md с тремя страницами: title главной — прежняя строка, правило агрегатора не вмешивается
    c = card("[КК] Глоссарий", "'1', '2', '3'", "## Термины\n", type_="glossary")
    rep, ok = check_title(c, src("[КК] Глоссарий"), extra_titles=["Другая", "Третья"])
    assert ok and rep == ["title: дословно перенесён ('[КК] Глоссарий') ✓"]


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
