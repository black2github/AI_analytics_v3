# tests/test_normalize_tables.py
"""Нормализатор сырых HTML-таблиц (Д-21, проход 1): сетка, протяжка,
иерархия по профилю, счётный инвариант нулевых потерь."""

import pytest
from bs4 import BeautifulSoup

from app.scripts.CI.normalize_tables import (
    Profile, assert_invariant, build_flat, expand_grid, find_top_tables,
    render_sample,
)


def grid_of(html: str):
    table = BeautifulSoup(html, "html.parser").find("table")
    return expand_grid(table)


ROWSPAN_HTML = """
<table>
<tr><th>Узел</th><th>Параметр</th><th>Тип</th></tr>
<tr><td rowspan="2">RelPerson</td><td>Name</td><td>Строка</td></tr>
<tr><td>INN</td><td>Число</td></tr>
</table>
"""


class TestGrid:
    def test_rowspan_stretched(self):
        g = grid_of(ROWSPAN_HTML)
        assert g[1][0] == "RelPerson" and g[2][0] == "RelPerson"
        assert g[2][1] == "INN"  # колонка не съехала

    def test_colspan_expanded(self):
        g = grid_of('<table><tr><td colspan="3">Шапка</td><td>X</td></tr>'
                    '<tr><td>a</td><td>b</td><td>c</td><td>d</td></tr></table>')
        assert g[0] == ["Шапка", "Шапка", "Шапка", "X"]
        assert g[1] == ["a", "b", "c", "d"]

    def test_links_become_markdown(self):
        g = grid_of('<table><tr><td><a href="/x">Заявка</a> текст</td></tr></table>')
        assert g[0][0] == "[Заявка](/x) текст"

    def test_pipe_escaped_and_br(self):
        g = grid_of('<table><tr><td><p>a|b</p><p>вторая</p></td></tr></table>')
        assert g[0][0] == "a\\|b<br>вторая"

    def test_ragged_rows_padded(self):
        g = grid_of('<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>')
        assert g[1] == ["c", ""]


class TestProfileBuild:
    def test_hierarchy_path_joined_without_adjacent_dups(self):
        g = grid_of(ROWSPAN_HTML)
        p = Profile(name="t", header_rows=1, hierarchy_cols=[0, 1],
                    path_title="XML-элемент", keep_cols=[(2, "Тип")])
        headers, rows = build_flat(g, p)
        assert headers == ["XML-элемент", "Тип"]
        assert rows[0] == ["RelPerson/Name", "Строка"]
        assert rows[1] == ["RelPerson/INN", "Число"]

    def test_invariant_counts(self):
        g = grid_of(ROWSPAN_HTML)
        p = Profile(header_rows=1, hierarchy_cols=[0, 1], keep_cols=[(2, "Тип")])
        _, rows = build_flat(g, p)
        assert "✓" in assert_invariant(g, p, rows)

    def test_passthrough_without_profile(self):
        g = grid_of(ROWSPAN_HTML)
        headers, rows = build_flat(g, Profile())
        assert headers == ["Узел", "Параметр", "Тип"]
        assert len(rows) == 2 and rows[1][0] == "RelPerson"


class TestDiscovery:
    def test_top_level_only(self):
        md = ("текст\n<table><tr><td>внешняя"
              "<table><tr><td>вложенная</td></tr></table></td></tr></table>\n")
        tables = find_top_tables(md)
        assert len(tables) == 1

    def test_sample_lists_columns(self):
        g = grid_of(ROWSPAN_HTML)
        s = render_sample(g)
        assert "[0] Узел" in s and "строка 1" in s
