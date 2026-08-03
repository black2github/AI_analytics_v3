# tests/test_angle_token_escaping.py
"""Экранирование токенов-атрибутов в сырых HTML-таблицах экспорта.

Инцидент (2026-08-04, выгрузка КК «страница Анкеты»): в Confluence токен
размерности экрана хранится экранированным (&lt;S&gt;) и отображается текстом,
но при выгрузке текстовые узлы возвращались в сырую HTML-ячейку уже
декодированными (<S>). Для markdown/HTML-рендера <S> — живой тег <s>
(незакрытое зачёркивание всего последующего текста), а неизвестные теги
<XS>/<L>/<M>/<XL> санитайзер GitLab вырезает — токен тихо исчезает.

Фикс: _escape_stray_tag_openers — экранируется ТОЛЬКО '<' перед латинской
буквой / '/' / '!' (то, что HTML-парсер принимает за начало тега). Кириллические
токены (<Номер заявки>) по HTML5 — обычный текст и остаются байт-в-байт
(грепаемость, идемпотентность повторного экспорта) — на это здесь отдельные
тесты-ограничители.
"""

import pytest

from app.content_extractor import _escape_stray_tag_openers
from app.filter_all_fragments import filter_all_fragments


# Ячейка с colspan вынуждает рендер таблицы в сырой HTML
# (_process_top_level_table_to_html), как в исходнике инцидента.
def _html_table_with_cell(cell_html: str) -> str:
    return f'''
    <table>
        <tbody>
            <tr>
                <td colspan="2"><p>{cell_html}</p></td>
                <td><p>обычная ячейка</p></td>
            </tr>
        </tbody>
    </table>
    '''


class TestEscapeStrayTagOpeners:
    """Юнит-тесты хелпера: что экранируется, а что обязано остаться как есть."""

    def test_latin_size_tokens_escaped(self):
        assert _escape_stray_tag_openers("<S> = true") == "&lt;S> = true"
        assert _escape_stray_tag_openers("<XS> или <XL>") == "&lt;XS> или &lt;XL>"

    def test_closing_tag_and_comment_openers_escaped(self):
        assert _escape_stray_tag_openers("</s>") == "&lt;/s>"
        assert _escape_stray_tag_openers("<!-- x -->") == "&lt;!-- x -->"

    # --- ограничители на НЕсрабатывание (асимметрия ошибок) ---

    def test_cyrillic_token_untouched(self):
        assert _escape_stray_tag_openers("<Номер заявки>") == "<Номер заявки>"
        assert _escape_stray_tag_openers(".<Дата заявки> + 1") == ".<Дата заявки> + 1"

    def test_comparison_and_digits_untouched(self):
        assert _escape_stray_tag_openers("a < b") == "a < b"
        assert _escape_stray_tag_openers("сумма <100") == "сумма <100"

    def test_plain_text_idempotent(self):
        text = "обычный текст без скобок"
        assert _escape_stray_tag_openers(text) == text
        # повторное применение ничего не меняет (нет '<' у '&lt;')
        once = _escape_stray_tag_openers("<S>")
        assert _escape_stray_tag_openers(once) == once


class TestAngleTokensInHtmlTables:
    """Интеграционно: путь сырой HTML-таблицы (_process_nested_table_cell_content)."""

    def test_latin_token_stays_escaped_in_html_cell(self):
        html = _html_table_with_cell(
            'Метод определения размерности экрана.&lt;S&gt; = true')
        result = filter_all_fragments(html)
        assert "&lt;S>" in result or "&lt;S&gt;" in result
        assert ".<S>" not in result  # живого тега в выходе нет

    def test_xs_token_stays_escaped_in_html_cell(self):
        html = _html_table_with_cell('при &lt;XS&gt; скрыто')
        result = filter_all_fragments(html)
        assert "&lt;XS" in result
        assert "<XS>" not in result

    def test_cyrillic_token_preserved_verbatim_in_html_cell(self):
        # Ограничитель: поведение для кириллических токенов не меняется.
        html = _html_table_with_cell('значение = [Заявка].&lt;Номер заявки&gt;')
        result = filter_all_fragments(html)
        assert "<Номер заявки>" in result

    def test_list_item_token_escaped(self):
        # Путь _list_to_html: список внутри ячейки тоже форсирует HTML-рендер.
        html = _html_table_with_cell(
            '</p><ul><li>отображается при &lt;M&gt;</li></ul><p>')
        result = filter_all_fragments(html)
        assert "&lt;M" in result
        assert "<M>" not in result
