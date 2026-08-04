# tests/test_list_item_spacing.py
"""Пробелы и <strong> в пунктах списков внутри сырых HTML-таблиц.

Инцидент (2026-08-04, функция «Запрос на создание заявки 115», Onix-transport):
в ячейке HTML-таблицы пункт списка `<li><strong>Если</strong> <a …>Заявка…</a>`
экспортировался как «Если<a …» — пробел потерян. Причина: пробел между
`</strong>` и `<a>` — отдельный ЧИСТО ПРОБЕЛЬНЫЙ текстовый узел (границы
<strong> и цветных <span> дробят текст), а _list_to_html отбрасывал узлы,
не проходящие text.strip(). Смежный дефект: прямой <strong> внутри <li>
терял обёртку (уходил в общий else-обход).

Паттерны тестов повторяют структуру живого исходника (colspan вынуждает
рендер таблицы сырым HTML).
"""

import pytest

from app.filter_all_fragments import filter_all_fragments


def _table_with_li(li_inner: str) -> str:
    return f'''
    <table>
        <tbody>
            <tr>
                <td colspan="2"><ul><li>{li_inner}</li></ul></td>
                <td><p>обычная ячейка</p></td>
            </tr>
        </tbody>
    </table>
    '''


class TestListItemSpacing:
    def test_space_node_between_strong_and_link_preserved(self):
        # Точный паттерн инцидента: <strong>Если</strong>␣<a …>
        html = _table_with_li(
            '<strong>Если</strong> <a href="/pages/viewpage.action?pageId=1">Заявка</a>. текст')
        result = filter_all_fragments(html)
        assert "Если<a" not in result and "Если</strong><a" not in result
        assert "Если</strong> <a" in result

    def test_space_node_between_span_pieces_preserved(self):
        # Цветовые span дробят текст: узел-пробел между двумя span
        html = _table_with_li(
            '<span style="color: rgb(23,43,77);">Если</span> '
            '<span style="color: rgb(23,43,77);">условие</span>')
        result = filter_all_fragments(html)
        assert "Если условие" in result
        assert "Еслиусловие" not in result

    def test_direct_strong_in_li_keeps_wrapper(self):
        html = _table_with_li('<strong>Если</strong> далее текст')
        result = filter_all_fragments(html)
        assert "<strong>Если</strong>" in result

    # --- ограничители на НЕсрабатывание ---

    def test_space_inside_text_node_unchanged(self):
        # Здоровый вариант инцидента (ACC_COMMISS): пробел внутри узла «Если »
        html = _table_with_li(
            'Если <a href="/pages/viewpage.action?pageId=1">Заявка</a>')
        result = filter_all_fragments(html)
        assert "Если <a" in result

    def test_no_leading_space_from_indentation(self):
        # Пробельный узел ПЕРЕД первым содержимым — не разделитель, а вёрстка
        html = _table_with_li(
            ' <a href="/pages/viewpage.action?pageId=1">Заявка</a>')
        result = filter_all_fragments(html)
        assert "<li> <a" not in result

    def test_strong_with_inner_trailing_space_unchanged(self):
        # Вариант «<strong>Если </strong>»: пробел внутри жирного выносится за тег
        html = _table_with_li(
            '<strong>Если </strong><a href="/pages/viewpage.action?pageId=1">Заявка</a>')
        result = filter_all_fragments(html)
        assert "Если</strong> <a" in result
        assert "Если </strong><a" not in result
