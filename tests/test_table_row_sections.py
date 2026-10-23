# tests/test_table_row_sections.py
#
# Строки таблицы за пределами первого <tbody> (2026-10-23, сторож --check-prom на
# выгрузке КК 1.9.10): все три пути (pipe, HTML верхнего уровня, вложенная HTML)
# брали строки только из ПЕРВОГО <tbody> либо прямых <tr> — строки во втором
# <tbody>, в <tfoot> или за обёрткой внутри таблицы молча выпадали. На трёх
# страницах B2B таблица «Логика работы метода» уезжала одной строкой заголовка
# (~1230 слов каждая). Дефект старше режима CriticMarkup, задевает все режимы.
#
# Стало: _table_row_sections — строки ЭТОЙ таблицы по секциям (шапка / тело / подвал)
# в документном порядке. Тесты парами: срабатывание на трёх путях и в критик-режиме,
# НЕсрабатывание (одна секция — байты как раньше, строки вложенной таблицы не
# поднимаются во внешнюю).

from app.content_extractor import create_critic_extractor
from app.filter_all_fragments import filter_all_fragments
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
CMAP = {"#008000": TASK}


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _island(inner_table):
    return f"<table><tbody><tr><td>внешняя</td><td>{inner_table}</td></tr></tbody></table>"


TWO_TBODY_PIPE = ('<table><tbody><tr><th>Шаг</th><th>Описание</th></tr></tbody>'
                  '<tbody><tr><td>1</td><td>результат положительный</td></tr></tbody></table>')
TWO_TBODY_HTML = ('<table><tbody><tr><td colspan="2"><strong>Шаг</strong></td><td>Описание</td></tr></tbody>'
                  '<tbody><tr><td>1</td><td>а</td><td>результат положительный</td></tr></tbody></table>')


class TestPipeTable:
    def test_second_tbody_rows_kept(self):
        md = filter_all_fragments(TWO_TBODY_PIPE)
        assert "| 1 | результат положительный |" in md

    def test_tfoot_rows_kept_at_end(self):
        html = ('<table><tfoot><tr><td>итог</td></tr></tfoot><tbody><tr><th>А</th></tr>'
                '<tr><td>строка</td></tr></tbody></table>')
        md = filter_all_fragments(html)
        assert md.index("строка") < md.index("итог")

    def test_thead_plus_two_tbody(self):
        html = ('<table><thead><tr><th>Шаг</th></tr></thead><tbody><tr><td>один</td></tr></tbody>'
                '<tbody><tr><td>два</td></tr></tbody></table>')
        md = filter_all_fragments(html)
        assert "| один |" in md and "| два |" in md

    def test_colored_row_in_second_tbody_marked(self):
        html = ('<table><tbody><tr><th>А</th></tr></tbody><tbody><tr><td>'
                f'<span style="color: {GREEN};">новая строка</span></td></tr></tbody></table>')
        md = _critic(html)
        assert f"| новая строка | +{TASK} |" in md
        assert "новая строка" not in process_text_until_stable(md, "reject", None)[0]

    # --- НЕсрабатывание ---

    def test_single_tbody_unchanged(self):
        html = '<table><tbody><tr><th>А</th><th>Б</th></tr><tr><td>1</td><td>2</td></tr></tbody></table>'
        assert filter_all_fragments(html).strip() == "| А | Б |\n| --- | --- |\n| 1 | 2 |"

    def test_direct_rows_first_th_header_unchanged(self):
        html = '<table><tr><th>А</th></tr><tr><td>1</td></tr></table>'
        assert filter_all_fragments(html).strip() == "| А |\n| --- |\n| 1 |"


class TestTopLevelHtmlTable:
    def test_second_tbody_rows_kept(self):
        md = filter_all_fragments(TWO_TBODY_HTML)
        assert "<td>результат положительный</td>" in md
        assert md.count("<tbody>") == 1          # тела склеены в одно

    def test_rows_behind_wrapper_kept(self):
        html = ('<table><tbody><tr><td colspan="2">Шаг</td></tr></tbody>'
                '<div><tr><td>а</td><td>за обёрткой</td></tr></div></table>')
        assert "за обёрткой" in filter_all_fragments(html)

    def test_critic_row_in_second_tbody(self):
        html = ('<table><tbody><tr><td colspan="2">Шаг</td></tr></tbody><tbody><tr>'
                f'<td><span style="color: {GREEN};">а</span></td>'
                f'<td><span style="color: {GREEN};">б</span></td></tr></tbody></table>')
        md = _critic(html)
        assert f'<tr class="critic-row-ins" data-task="{TASK}">' in md

    # --- НЕсрабатывание ---

    def test_single_tbody_bytes_unchanged(self):
        html = '<table><tbody><tr><td colspan="2">А</td></tr><tr><td>1</td><td>2</td></tr></tbody></table>'
        assert filter_all_fragments(html).strip() == (
            "<table>\n<tbody>\n<tr>\n<td colspan=\"2\">А</td>\n</tr>\n<tr>\n<td>1</td>\n"
            "<td>2</td>\n</tr>\n</tbody>\n</table>")

    def test_nested_table_rows_not_lifted(self):
        inner = '<table><thead><tr><th>вложенная шапка</th></tr></thead><tbody><tr><td>в</td></tr></tbody></table>'
        html = f'<table><tbody><tr><td colspan="2">А</td></tr><tr><td>1</td><td>{inner}</td></tr></tbody></table>'
        md = filter_all_fragments(html)
        assert md.count("вложенная шапка") == 1
        assert not md.startswith("<table>\n<thead>")     # чужая шапка не стала шапкой внешней


class TestNestedHtmlTable:
    def test_second_tbody_rows_kept(self):
        md = filter_all_fragments(_island(
            '<table><tbody><tr><td>шапка</td></tr></tbody><tbody><tr><td>результат</td></tr></tbody></table>'))
        assert "<td>результат</td>" in md

    def test_thead_rendered_first(self):
        # раньше шапка вложенной таблицы дописывалась ПОСЛЕ тела
        md = filter_all_fragments(_island(
            '<table><thead><tr><td>шапка</td></tr></thead><tbody><tr><td>тело</td></tr></tbody></table>'))
        assert md.index("шапка") < md.index("тело")

    def test_colored_text_in_second_tbody_marked(self):
        md = _critic(_island(
            '<table><tbody><tr><td>шапка</td></tr></tbody><tbody><tr><td>'
            f'<p><span style="color: {GREEN};">новое</span></p></td></tr></tbody></table>'))
        assert f'data-task="{TASK}">новое' in md

    # --- НЕсрабатывание ---

    def test_direct_rows_unchanged(self):
        md = filter_all_fragments(_island('<table><tr><td>а</td></tr><tr><td>б</td></tr></table>'))
        assert "<table><tr><td>а</td></tr><tr><td>б</td></tr></table>" in md
