# tests/test_source_coverage_label_form.py
"""Метки описи «заморожено» и «контейнер» сверяются с формой страницы текущей выгрузки: ⚠ с
перечнем, класс страницы и число бракующих не меняются."""
from pathlib import Path

import pytest

from app.scripts.CI import source_coverage as cov

_INV_HEAD = ("# Опись\n\n| page_id | title | родитель | req_type | целевой тип (гипотеза) | основание |\n"
             "|---|---|---|---|---|---|\n")
FROZEN_ROW = "| {pid} | Страница {pid} | р | ТТ | вне SRS: заморожено GBO-1 | frozen |\n"
CONTAINER_ROW = "| {pid} | Страница {pid} | р | ТТ | README-реестр | TOC-контейнер |\n"
TOC = ("Раздел описывает API сервиса.\n\n"
       "- [\\[КК\\] Страница (1)](дочерняя/стр.md)\n    * [Вторая](https://x/y?pageId=1)\n")
DATA_TABLE = ("<table><tbody><tr><th>№</th><th>Функция</th></tr>"
              "<tr><td>1</td><td>Просмотр заявки</td></tr>"
              "<tr><td>2</td><td>Подпись заявки</td></tr></tbody></table>\n")
LINK_TABLE = ("<table><tbody><tr><th>Страница</th></tr>"
              '<tr><td><a href="x">Первая</a></td></tr>'
              "<tr><td>[Вторая](y.md)</td></tr></tbody></table>\n")


def _page(src: Path, pid: str, body: str, extra: str = "") -> None:
    p = src / f"p{pid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: 'Страница {pid}'\nconfluence_page_id: '{pid}'\n{extra}---\n\n{body}",
                 encoding="utf-8")


def _kit(tmp_path: Path, rows: str):
    src, docs = tmp_path / "src", tmp_path / "docs"
    src.mkdir()
    docs.mkdir()
    (docs / "inventory.md").write_text(_INV_HEAD + rows, encoding="utf-8")
    return src, docs


def _warn(lines, prefix):
    return next((l for l in lines if l.startswith(prefix)), None)


FROZEN_W = "⚠ метка «заморожено» без признака"
CONT_W = "⚠ контейнер с собственным текстом"


# ---------------------------------------------------------------- форма страницы

def test_form_counts_data_rows_not_header(tmp_path):
    _page(tmp_path, "1", DATA_TABLE)
    form = cov.page_form(tmp_path / "p1.md")
    assert (form["tables"], form["rows"], form["chars"]) == (1, 2, 0)


def test_form_link_table_has_no_data_rows(tmp_path):
    _page(tmp_path, "1", LINK_TABLE)
    form = cov.page_form(tmp_path / "p1.md")
    assert (form["tables"], form["rows"], form["html_tables"]) == (0, 0, 1)


def test_form_markdown_table(tmp_path):
    _page(tmp_path, "1", "| А | Б |\n|---|---|\n| [x](y.md) | |\n| текст | 1 |\n\n| В |\n|---|\n| ещё |\n")
    form = cov.page_form(tmp_path / "p1.md")
    assert (form["tables"], form["rows"]) == (2, 2)


def test_form_text_excludes_links_headings_markers_and_comments(tmp_path):
    _page(tmp_path, "1", "# Заголовок раздела\n\n1) [\\[КК\\] Ссылка (1)](a.md)\n"
                         "<!-- комментарий -->\n![рис](i.png)\n- слово\n")
    assert cov.page_form(tmp_path / "p1.md")["chars"] == len("слово")


def test_form_unapproved_field_from_frontmatter_only(tmp_path):
    _page(tmp_path, "1", "unapproved_jira: GBO-1\n")
    _page(tmp_path, "2", "", extra="unapproved_jira: GBO-1\n")
    assert cov.page_form(tmp_path / "p1.md")["unapproved"] == 0
    assert cov.page_form(tmp_path / "p2.md")["unapproved"] == 1


# ---------------------------------------------------------------- «заморожено»

def test_frozen_without_field_warns_with_page_id(tmp_path):
    src, docs = _kit(tmp_path, FROZEN_ROW.format(pid="101"))
    _page(src, "101", DATA_TABLE + "Текст страницы.\n")
    lines, blocking = cov.coverage_report(src, docs)
    assert _warn(lines, FROZEN_W + " на странице: 1")
    assert any(l.startswith("  - 101 «Страница 101» — строк данных 2") for l in lines)
    assert blocking == 0


def test_frozen_with_field_silent(tmp_path):
    src, docs = _kit(tmp_path, FROZEN_ROW.format(pid="101"))
    _page(src, "101", DATA_TABLE, extra="unapproved_jira: GBO-1\n")
    assert _warn(cov.coverage_report(src, docs)[0], FROZEN_W) is None


@pytest.mark.parametrize("body", ["", "\n\n<!-- только комментарий -->\n", "## Заголовок\n",
                                  "- [Только ссылка](a.md)\n"])
def test_frozen_empty_body_silent(tmp_path, body):
    src, docs = _kit(tmp_path, FROZEN_ROW.format(pid="101"))
    _page(src, "101", body)
    assert _warn(cov.coverage_report(src, docs)[0], FROZEN_W) is None


def test_frozen_table_only_links_is_not_empty(tmp_path):
    src, docs = _kit(tmp_path, FROZEN_ROW.format(pid="101"))
    _page(src, "101", LINK_TABLE)
    assert _warn(cov.coverage_report(src, docs)[0], FROZEN_W + " на странице: 1")


def test_covered_frozen_page_silent(tmp_path):
    # метка снимает с брака только непокрытую страницу
    src, docs = _kit(tmp_path, FROZEN_ROW.format(pid="101"))
    _page(src, "101", DATA_TABLE)
    (docs / "c.md").write_text("---\nconfluence_page_ids: [101]\n---\n", encoding="utf-8")
    assert _warn(cov.coverage_report(src, docs)[0], FROZEN_W) is None


# ---------------------------------------------------------------- «контейнеры»

def test_container_with_data_table_warns(tmp_path):
    src, docs = _kit(tmp_path, CONTAINER_ROW.format(pid="201"))
    _page(src, "201", DATA_TABLE)
    lines, blocking = cov.coverage_report(src, docs)
    assert _warn(lines, CONT_W + ": страниц 1 (таблиц 1, знаков 0)")
    assert blocking == 0


def test_container_toc_with_lead_silent(tmp_path):
    src, docs = _kit(tmp_path, CONTAINER_ROW.format(pid="201"))
    _page(src, "201", TOC + LINK_TABLE)
    assert _warn(cov.coverage_report(src, docs)[0], CONT_W) is None


@pytest.mark.parametrize("n,fires", [(cov.CONTAINER_TEXT_LIMIT, False), (cov.CONTAINER_TEXT_LIMIT + 1, True)])
def test_container_text_limit_boundary(tmp_path, n, fires):
    src, docs = _kit(tmp_path, CONTAINER_ROW.format(pid="201"))
    _page(src, "201", "ж" * n + "\n")
    assert bool(_warn(cov.coverage_report(src, docs)[0], CONT_W)) is fires


def test_container_limit_is_parameter(tmp_path):
    _page(tmp_path, "201", "короткий текст\n")
    inv = {"201": {"title": "Т"}}
    pages = {"201": tmp_path / "p201.md"}
    assert cov.label_form_lines({"201": cov.CONTAINER}, pages, inv, text_limit=5)
    assert not cov.label_form_lines({"201": cov.CONTAINER}, pages, inv, text_limit=100)


def test_other_classes_not_checked(tmp_path):
    src, docs = _kit(tmp_path, "| 301 | Страница 301 | р | ТТ | doc-rules | reference-only |\n")
    _page(src, "301", DATA_TABLE)
    lines = cov.coverage_report(src, docs)[0]
    assert _warn(lines, FROZEN_W) is None and _warn(lines, CONT_W) is None


# ---------------------------------------------------------------- класс и брак не меняются

def test_class_and_blocking_unchanged(tmp_path):
    src, docs = _kit(tmp_path, FROZEN_ROW.format(pid="101") + CONTAINER_ROW.format(pid="201"))
    _page(src, "101", DATA_TABLE)
    _page(src, "201", DATA_TABLE)
    lines, blocking = cov.coverage_report(src, docs)
    assert blocking == 0
    assert "заморожено 1, контейнеры 1" in lines[0]
    assert "заморожено: 1" in lines and "контейнеры: 1" in lines


def test_without_inventory_no_lines(tmp_path):
    src, docs = tmp_path / "src", tmp_path / "docs"
    src.mkdir()
    docs.mkdir()
    _page(src, "101", DATA_TABLE)
    lines = cov.coverage_report(src, docs)[0]
    assert _warn(lines, FROZEN_W) is None and _warn(lines, CONT_W) is None
