# tests/test_table_header_order_fix.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import pytest
from app.filter_all_fragments import filter_all_fragments


class TestTableHeaderOrderFix:
    """Тесты исправления порядка заголовков таблиц"""

    def test_table_with_thead_tbody_order(self):
        """Тест правильного порядка заголовков при наличии thead и tbody"""
        html = '''
        <table class="relative-table wrapped" style="width: 65.2473%;">
            <colgroup>
                <col style="width: 7.68943%;" />
                <col style="width: 36.8671%;" />
                <col style="width: 108.705%;" />
            </colgroup>
            <thead>
                <tr>
                    <th><p>Шаг №</p></th>
                    <th><p>Название шага</p></th>
                    <th><p>Описание шага</p></th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="highlight-grey" data-highlight-colour="grey">1.1</td>
                    <td><p><strong>название 1</strong></p></td>
                    <td><p><span style="color: rgb(0,51,102);">Описание 1</span></p></td>
                </tr>
                <tr>
                    <td class="highlight-grey" data-highlight-colour="grey">1.2</td>
                    <td><p><strong>название 2</strong></p></td>
                    <td><p>Описание 2</p></td>
                </tr>
            </tbody>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Fixed table result:\n{result}")

        # ИСПРАВЛЕНИЕ: Работаем с реальной структурой вывода
        lines = result.split('\n')

        # Находим индексы ключевых элементов
        table_start_idx = None
        header_start_idx = None
        separator_idx = None
        first_data_idx = None

        for i, line in enumerate(lines):
            if '**Таблица:**' in line:
                table_start_idx = i
            elif 'Шаг №' in line:
                header_start_idx = i
            elif '| --- | --- | --- |' in line:
                separator_idx = i
            elif '1.1' in line and '|' in line:
                first_data_idx = i
                break

        # Основные проверки
        assert table_start_idx is not None, "Table marker not found!"
        assert header_start_idx is not None, "Header not found!"
        assert separator_idx is not None, "Separator not found!"
        assert first_data_idx is not None, "Data rows not found!"

        # ГЛАВНАЯ ПРОВЕРКА: правильный порядок элементов
        assert table_start_idx < header_start_idx, "Table marker should come before header"
        assert header_start_idx < separator_idx, "Header should come before separator"
        assert separator_idx < first_data_idx, "Separator should come before data"

        print(
            f" Order verified: table({table_start_idx}) -> header({header_start_idx}) -> separator({separator_idx}) -> data({first_data_idx})")

        # Проверяем наличие всех заголовков
        header_section = '\n'.join(lines[header_start_idx:separator_idx])
        assert 'Шаг №' in header_section, "Missing 'Шаг №' in header"
        assert 'Название шага' in header_section, "Missing 'Название шага' in header"
        assert 'Описание шага' in header_section, "Missing 'Описание шага' in header"

        # Проверяем наличие данных после разделителя
        data_section = '\n'.join(lines[separator_idx + 1:])
        assert '1.1' in data_section, "Missing '1.1' in data"
        assert '1.2' in data_section, "Missing '1.2' in data"
        assert 'название 1' in data_section, "Missing 'название 1' in data"

        print(" Table header order fix verified!")

    def test_table_without_explicit_thead_tbody(self):
        """Тест таблицы без явных thead/tbody тегов"""
        html = '''
        <table>
            <tr>
                <th>Колонка 1</th>
                <th>Колонка 2</th>
            </tr>
            <tr>
                <td>Значение 1</td>
                <td>Значение 2</td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Simple table result:\n{result}")

        # ИСПРАВЛЕНИЕ: Ищем компоненты, а не полные строки
        lines = result.split('\n')

        header_found = False
        separator_found = False
        data_found = False
        header_idx = None
        separator_idx = None
        data_idx = None

        for i, line in enumerate(lines):
            if 'Колонка 1' in line and not header_found:
                header_found = True
                header_idx = i
            elif '---' in line and not separator_found:
                separator_found = True
                separator_idx = i
            elif 'Значение 1' in line and not data_found:
                data_found = True
                data_idx = i

        assert header_found, "Header not found"
        assert separator_found, "Separator not found"
        assert data_found, "Data not found"
        assert header_idx < separator_idx < data_idx, f"Wrong order: header({header_idx}), separator({separator_idx}), data({data_idx})"

        print(" Simple table order verified!")

    def test_complex_table_with_colored_content(self):
        """Тест сложной таблицы с цветным содержимым"""
        html = '''
        <table>
            <thead>
                <tr>
                    <th>Поле</th>
                    <th>Тип</th>
                    <th>Описание</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>id</td>
                    <td>string</td>
                    <td>Идентификатор</td>
                </tr>
                <tr>
                    <td>name</td>
                    <td>string</td>
                    <td><span style="color: red;">Новое поле</span></td>
                </tr>
            </tbody>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Complex table result:\n{result}")

        # ИСПРАВЛЕНИЕ: Ищем компоненты в правильном порядке
        lines = result.split('\n')

        header_idx = None
        separator_idx = None
        data_idx = None

        for i, line in enumerate(lines):
            if 'Поле' in line and header_idx is None:
                header_idx = i
            elif '---' in line and separator_idx is None:
                separator_idx = i
            elif 'id' in line and 'string' in line and data_idx is None:
                data_idx = i

        assert header_idx is not None, "Header not found"
        assert separator_idx is not None, "Separator not found"
        assert data_idx is not None, "Data not found"
        assert header_idx < separator_idx < data_idx, "Header should come before data"

        # Проверяем наличие цветного содержимого (в all_fragments оно должно быть)
        full_result = '\n'.join(lines)
        assert 'Новое поле' in full_result, "Colored content should be included in all_fragments"

        print(" Complex table order verified!")


if __name__ == "__main__":
    test = TestTableHeaderOrderFix()
    test.test_table_with_thead_tbody_order()
    test.test_table_without_explicit_thead_tbody()
    test.test_complex_table_with_colored_content()
    print(" All table header order fix tests passed!")