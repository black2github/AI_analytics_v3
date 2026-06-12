# tests/test_div_block_separation.py

from app.filter_all_fragments import filter_all_fragments


class TestDivBlockSeparation:
    """Блочные элементы внутри <div> должны разделяться пустой строкой.

    Регрессия: в рендеренном HTML (HTTP-режим) контент завёрнут в layout-div'ы, и
    чистая Markdown-таблица сразу за абзацем (напр. "<strong>История изменений:</strong>")
    не отделялась пустой строкой — таблица не распознавалась как Markdown.
    """

    def test_paragraph_then_table_in_div_gets_blank_line(self):
        html = (
            '<div class="innerCell">'
            '<p><strong>Заголовок раздела:</strong></p>'
            '<table><tbody>'
            '<tr><th>Дата</th><th>Описание</th></tr>'
            '<tr><td>1</td><td>2</td></tr>'
            '</tbody></table>'
            '</div>'
        )
        out = filter_all_fragments(html)
        # Между абзацем и таблицей — ровно одна пустая строка, таблица отформатирована.
        assert "**Заголовок раздела:**\n\n| Дата | Описание |" in out
        assert "| --- | --- |" in out
        assert "\n\n\n" not in out  # без лишних пустых строк

    def test_paragraph_then_table_nested_layout_divs(self):
        # Воспроизводит вложенность рендеренного HTML Confluence (columnLayout/cell/innerCell).
        html = (
            '<div class="contentLayout2"><div class="columnLayout single">'
            '<div class="cell normal"><div class="innerCell">'
            '<p><strong>Раздел:</strong></p>'
            '<div class="table-wrap"><table><tbody>'
            '<tr><th>K</th><th>V</th></tr><tr><td>a</td><td>b</td></tr>'
            '</tbody></table></div>'
            '</div></div></div></div>'
        )
        out = filter_all_fragments(html)
        assert "**Раздел:**\n\n| K | V |" in out
        assert "| --- | --- |" in out
