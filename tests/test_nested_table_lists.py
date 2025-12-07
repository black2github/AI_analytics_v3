# tests/test_nested_table_lists.py

import pytest
from app.filter_approved_fragments import filter_approved_fragments
from app.filter_all_fragments import filter_all_fragments


class TestNestedTableLists:
    """Тесты обработки списков во вложенных таблицах"""

    def test_nested_table_simple_list_all_fragments(self):
        """Тест простого списка во вложенной таблице (все фрагменты)"""
        html = '''
        <table>
            <tr>
                <td>Основная таблица</td>
                <td>
                    <div class="table-wrap">
                        <table>
                            <tr>
                                <td>1</td>
                                <td>
                                    <ul>
                                        <li>вл_строка2.2.1</li>
                                        <li>вл_строка2.2.2</li>
                                        <li>вл_строка2.2.3</li>
                                    </ul>
                                </td>
                            </tr>
                        </table>
                    </div>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"All fragments nested table result: '{result}'")

        # Проверяем, что элементы списка НЕ склеены
        assert "вл_строка2.2.1вл_строка2.2.2вл_строка2.2.3" not in result

        # Проверяем, что элементы списка разделены правильно
        assert "- вл_строка2.2.1" in result
        assert "- вл_строка2.2.2" in result
        assert "- вл_строка2.2.3" in result

    def test_nested_table_simple_list_approved_fragments(self):
        """Тест простого списка во вложенной таблице (подтвержденные фрагменты)"""
        html = '''
        <table>
            <tr>
                <td>Основная таблица</td>
                <td>
                    <div class="table-wrap">
                        <table>
                            <tr>
                                <td>1</td>
                                <td>
                                    <ul>
                                        <li>подтвержденная_строка1</li>
                                        <li><span style="color: red;">цветная_строка</span></li>
                                        <li>подтвержденная_строка2</li>
                                    </ul>
                                </td>
                            </tr>
                        </table>
                    </div>
                </td>
            </tr>
        </table>
        '''

        result = filter_approved_fragments(html)
        print(f"Approved nested table result: '{result}'")

        # Проверяем, что подтвержденные элементы есть
        assert "- подтвержденная_строка1" in result
        assert "- подтвержденная_строка2" in result

        # Проверяем, что цветной элемент исключен
        assert "цветная_строка" not in result

        # Проверяем, что элементы НЕ склеены
        assert "подтвержденная_строка1подтвержденная_строка2" not in result

    def test_complex_nested_table_from_real_html(self):
        """Тест реального примера из вашего HTML"""
        html = '''
        <table class="relative-table wrapped confluenceTable tablesorter tablesorter-default" style="width: 10.5802%;" role="grid" resolved="">
            <colgroup><col style="width: 25.3013%;"><col style="width: 129.17%;"></colgroup>
            <thead>
                <tr role="row" class="tablesorter-headerRow">
                    <th scope="col" class="confluenceTh tablesorter-header sortableHeader tablesorter-headerUnSorted">№</th>
                    <th scope="col" class="confluenceTh tablesorter-header sortableHeader tablesorter-headerUnSorted">Заг2</th>
                </tr>
            </thead>
            <tbody aria-live="polite" aria-relevant="all">
                <tr role="row">
                    <td class="confluenceTd">2</td>
                    <td class="confluenceTd">
                        <div class="table-wrap">
                            <table class="wrapped confluenceTable tablesorter tablesorter-default" data-mce-resize="false" role="grid" resolved="">
                                <colgroup><col><col></colgroup>
                                <thead>
                                    <tr role="row" class="tablesorter-headerRow">
                                        <th scope="col" class="confluenceTh tablesorter-header sortableHeader tablesorter-headerUnSorted">№</th>
                                        <th scope="col" class="confluenceTh tablesorter-header sortableHeader tablesorter-headerUnSorted">Вл_Заг2</th>
                                    </tr>
                                </thead>
                                <tbody aria-live="polite" aria-relevant="all">
                                    <tr role="row">
                                        <td class="confluenceTd">1</td>
                                        <td class="confluenceTd">
                                            <ul>
                                                <li>вл_строка2.2.1</li>
                                                <li>вл_строка2.2.2</li>
                                                <li>вл_строка2.2.3</li>
                                            </ul>
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </td>
                </tr>
            </tbody>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Real HTML result: '{result}'")

        # Основная проверка - элементы НЕ должны быть склеены
        assert "вл_строка2.2.1вл_строка2.2.2вл_строка2.2.3" not in result

        # Проверяем правильную структуру списка
        assert "- вл_строка2.2.1" in result
        assert "- вл_строка2.2.2" in result
        assert "- вл_строка2.2.3" in result

    def test_numbered_list_in_nested_table(self):
        """Тест нумерованного списка во вложенной таблице"""
        html = '''
        <table>
            <tr>
                <td>
                    <table>
                        <tr>
                            <td>
                                <ol>
                                    <li>Первый пункт</li>
                                    <li>Второй пункт</li>
                                    <li>Третий пункт</li>
                                </ol>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Numbered nested list result: '{result}'")

        assert "1. Первый пункт" in result
        assert "2. Второй пункт" in result
        assert "3. Третий пункт" in result

        # Проверяем, что НЕ склеены
        assert "Первый пунктВторой пунктТретий пункт" not in result


if __name__ == "__main__":
    test = TestNestedTableLists()
    test.test_nested_table_simple_list_all_fragments()
    test.test_nested_table_simple_list_approved_fragments()
    test.test_complex_nested_table_from_real_html()
    test.test_numbered_list_in_nested_table()
    print("✅ Все тесты вложенных таблиц со списками прошли!")