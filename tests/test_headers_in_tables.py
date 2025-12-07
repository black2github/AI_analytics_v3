# tests/test_headers_in_tables.py

import pytest
from app.filter_all_fragments import filter_all_fragments
from app.filter_approved_fragments import filter_approved_fragments

class TestHeadersInTables:
    """Тесты обработки заголовков внутри таблиц"""

    def test_simple_header_in_table_cell(self):
        """Тест простого заголовка в ячейке таблицы"""
        html = '''
        <table>
            <tr>
                <td>
                    <h2>Требования к системе</h2>
                    <p>Описание требований</p>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Simple header result: '{result}'")

        # Заголовок должен получить префикс ##
        assert "## Требования к системе" in result
        assert "Описание требований" in result

    def test_multiple_headers_in_table_cell(self):
        """Тест множественных заголовков в ячейке"""
        html = '''
        <table>
            <tr>
                <td>
                    <h1>Главный раздел</h1>
                    <h2>Подраздел</h2>
                    <h3>Детали</h3>
                    <p>Содержимое</p>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Multiple headers result: '{result}'")

        assert "# Главный раздел" in result
        assert "## Подраздел" in result
        assert "### Детали" in result
        assert "Содержимое" in result

    def test_header_in_nested_table(self):
        """Тест заголовка во вложенной таблице"""
        html = '''
        <table>
            <tr>
                <td>
                    Основная таблица:
                    <table>
                        <tr>
                            <td>
                                <h2>Заголовок во вложенной таблице</h2>
                                <p>Текст во вложенной таблице</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Nested table header result: '{result}'")

        assert "Основная таблица:" in result
        assert "## Заголовок во вложенной таблице" in result
        assert "Текст во вложенной таблице" in result

    def test_header_with_colored_content(self):
        """Тест заголовка с цветным содержимым"""
        html = '''
        <table>
            <tr>
                <td>
                    <h2>
                        Заголовок с 
                        <span style="color: red;">новым</span> 
                        содержимым
                    </h2>
                </td>
            </tr>
        </table>
        '''

        # Все фрагменты
        all_result = filter_all_fragments(html)
        assert "## Заголовок с новым содержимым" in all_result

        # Только подтвержденные
        approved_result = filter_approved_fragments(html)
        assert "## Заголовок с содержимым" in approved_result
        assert "новым" not in approved_result

if __name__ == "__main__":
    test = TestHeadersInTables()
    test.test_simple_header_in_table_cell()
    test.test_multiple_headers_in_table_cell()
    test.test_header_in_nested_table()
    test.test_header_with_colored_content()
    print("OK Все тесты заголовков в таблицах готовы!")