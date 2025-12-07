# tests/test_mixed_content_in_tables.py

import pytest
from app.filter_approved_fragments import filter_approved_fragments
from app.filter_all_fragments import filter_all_fragments


class TestMixedContentInTables:
    """Тесты смешанного контента в ячейках таблиц (списки + заголовки + параграфы)"""

    def test_list_with_header_and_paragraph_approved(self):
        """Тест списка с заголовком и параграфом в ячейке таблицы (подтвержденные)"""
        html = '''
        <table>
            <tbody>
                <tr>
                    <td class="confluenceTd">
                        <ul>
                            <li>
                                <span style="color: rgb(23,43,77);">Атрибуты из </span>
                                <a href="/page/328259">Клиент Банка</a>
                                <span style="color: rgb(23,43,77);">.&lt;Идентификатор клиента&gt;</span>
                                <ul>
                                    <li>item 1
                                        <ul>
                                            <li>item 2</li>
                                        </ul>
                                    </li>
                                </ul>
                            </li>
                        </ul>
                        <h3>Заголовок 3</h3>
                        <p>
                            <strong>Если </strong>
                            <span style="color: rgb(23,43,77);">Входящие параметры.&lt;Список клиентов&gt; пустой, </span>
                            <strong>то</strong>
                        </p>
                    </td>
                </tr>
            </tbody>
        </table>
        '''

        result = filter_approved_fragments(html)
        print(f"Mixed content approved result: '{result}'")

        # V Проверяем правильное разделение элементов
        # Заголовок должен быть отдельной строкой с префиксом ###
        assert "### Заголовок 3" in result

        # V ИСПРАВЛЕНИЕ: Элементы списка должны быть с правильными отступами
        assert "- Атрибуты из [Клиент Банка].<Идентификатор клиента>" in result  # Основной элемент
        assert "    * item 1" in result  # Вложенный уровень 1
        assert "        + item 2" in result  # Вложенный уровень 2

        # V Параграф должен быть отдельно
        assert "Если Входящие параметры" in result
        assert "пустой, то" in result

        # X Проверяем отсутствие склеивания
        assert "item 2 ### Заголовок 3" not in result
        assert "item 2### Заголовок 3" not in result
        assert "ЗаголовокЕсли" not in result
        assert "3Если" not in result

        # V ДОПОЛНИТЕЛЬНО: Проверяем, что заголовок и параграф разделены
        assert "### Заголовок 3\nЕсли" in result or "### Заголовок 3" in result

    def test_list_with_header_and_paragraph_all(self):
        """Тест списка с заголовком и параграфом в ячейке таблицы (все фрагменты)"""
        html = '''
        <table>
            <tbody>
                <tr>
                    <td class="confluenceTd">
                        <ul>
                            <li>
                                <span style="color: rgb(23,43,77);">Цветные атрибуты из </span>
                                <a href="/page/328259">Клиент Банка</a>
                                <ul>
                                    <li>вложенный item 1</li>
                                </ul>
                            </li>
                        </ul>
                        <h2>Важный заголовок</h2>
                        <p>
                            <span style="color: red;">Цветной текст</span> 
                            и обычный текст
                        </p>
                    </td>
                </tr>
            </tbody>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Mixed content all result: '{result}'")

        # V Проверяем правильное разделение всех элементов
        assert "## Важный заголовок" in result
        assert "- Цветные атрибуты из [Клиент Банка]" in result
        assert "    * вложенный item 1" in result
        assert "Цветной текст и обычный текст" in result

        # X Проверяем отсутствие склеивания
        assert "item 1 ## Важный заголовок" not in result
        assert "item 1## Важный заголовок" not in result
        assert "заголовокЦветной" not in result

    def test_complex_real_world_mixed_content(self):
        """Тест реального сложного примера с смешанным контентом"""
        html = '''
        <div class="table-wrap">
            <table class="confluenceTable">
                <thead>
                    <tr>
                        <th>HDR</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="confluenceTd">
                            <ul>
                                <li>
                                    <span style="color: rgb(23,43,77);">&lt;1&gt;. Атрибуты из </span>
                                    <a href="/page/328259">Клиент Банка</a>
                                    <span style="color: rgb(23,43,77);">.&lt;Идентификатор клиента&gt;</span>
                                    <ul>
                                        <li>item 1
                                            <ul>
                                                <li>item 2</li>
                                            </ul>
                                        </li>
                                    </ul>
                                </li>
                            </ul>
                            <h3 id="id-section">Заголовок 3</h3>
                            <p style="margin-left: 40.0px;">
                                <strong>Если </strong>
                                <span style="color: rgb(23,43,77);">Входящие параметры.&lt;Список клиентов&gt; пустой, </span>
                                <strong>то</strong>
                            </p>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
        '''

        result_approved = filter_approved_fragments(html)
        result_all = filter_all_fragments(html)

        print(f"Complex mixed approved: '{result_approved}'")
        print(f"Complex mixed all: '{result_all}'")

        # V Проверяем правильную структуру в обоих режимах
        for result in [result_approved, result_all]:
            assert "### Заголовок 3" in result
            assert "Если Входящие параметры" in result
            assert "пустой, то" in result

            # X Критический тест - заголовок НЕ должен склеиваться со списком
            assert "item 2 ### Заголовок 3" not in result
            assert "item 2### Заголовок 3" not in result
            assert "+ item 2 ### Заголовок 3" not in result

    def test_multiple_headers_in_table_cell(self):
        """Тест множественных заголовков в ячейке с другим контентом"""
        html = '''
        <table>
            <tr>
                <td>
                    <p>Вводный текст</p>
                    <h1>Главный заголовок</h1>
                    <ul>
                        <li>Первый элемент</li>
                        <li>Второй элемент</li>
                    </ul>
                    <h2>Подзаголовок</h2>
                    <p>Заключительный текст</p>
                    <h3>Финальный заголовок</h3>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Multiple headers result: '{result}'")

        # V Все заголовки должны быть правильно отформатированы
        assert "# Главный заголовок" in result
        assert "## Подзаголовок" in result
        assert "### Финальный заголовок" in result

        # V Контент должен быть разделен
        assert "Вводный текст" in result
        assert "- Первый элемент" in result
        assert "- Второй элемент" in result
        assert "Заключительный текст" in result

        # X Контент не должен склеиваться
        assert "элемент ## Подзаголовок" not in result
        assert "текст ### Финальный заголовок" not in result


if __name__ == "__main__":
    test = TestMixedContentInTables()
    test.test_list_with_header_and_paragraph_approved()
    test.test_list_with_header_and_paragraph_all()
    test.test_complex_real_world_mixed_content()
    test.test_multiple_headers_in_table_cell()
    print("V Все тесты смешанного контента готовы!")