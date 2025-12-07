# tests/test_table_lists.py

import pytest
from app.filter_approved_fragments import filter_approved_fragments
from app.filter_all_fragments import filter_all_fragments


class TestTableLists:
    """Тесты обработки списков в ячейках таблиц"""

    def test_approved_table_list_colored(self):
        """Тест списка в ячейке таблицы с цветными элементами (подтвержденные)"""
        html = '''
        <table>
            <tr>
                <td class="confluenceTd">
                    <div class="content-wrapper">
                        <p style="text-align: left;">
                            <span style="color: rgb(0,51,102);">
                                <strong>Наименование поля:</strong> отображается список категорий:
                            </span>
                        </p>
                        <ul style="text-align: left;">
                            <li><span style="color: rgb(0,51,102);">Дневной</span></li>
                            <li><span style="color: rgb(0,51,102);">Месячный</span></li>
                            <li><span style="color: rgb(0,51,102);">Квартальный</span></li>
                            <li><span style="color: rgb(0,51,102);">Годовой</span></li>
                        </ul>
                    </div>
                </td>
            </tr>
        </table>
        '''

        result = filter_approved_fragments(html)
        print(f"Approved result: '{result}'")

        # Проверяем, что элементы списка разделены переносами
        assert "Наименование поля: отображается список категорий:" in result
        assert "- Дневной" in result
        assert "- Месячный" in result
        assert "- Квартальный" in result
        assert "- Годовой" in result

        # Проверяем, что НЕТ склеенной строки
        assert "ДневнойМесячныйКвартальныйГодовой" not in result

    def test_all_table_list_colored(self):
        """Тест списка в ячейке таблицы с цветными элементами (все фрагменты)"""
        html = '''
        <table>
            <tr>
                <td class="confluenceTd">
                    <div class="content-wrapper">
                        <p style="text-align: left;">
                            <span style="color: rgb(0,51,102);">
                                <strong>Наименование поля:</strong> отображается список категорий:
                            </span>
                        </p>
                        <ul style="text-align: left;">
                            <li><span style="color: rgb(0,51,102);">Дневной</span></li>
                            <li><span style="color: rgb(0,51,102);">Месячный</span></li>
                            <li><span style="color: rgb(0,51,102);">Квартальный</span></li>
                            <li><span style="color: rgb(0,51,102);">Годовой</span></li>
                        </ul>
                    </div>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"All fragments result: '{result}'")

        # Проверяем структуру списка
        assert "Наименование поля: отображается список категорий:" in result
        assert "- Дневной" in result
        assert "- Месячный" in result
        assert "- Квартальный" in result
        assert "- Годовой" in result

        # Проверяем, что НЕТ склеенной строки
        assert "ДневнойМесячныйКвартальныйГодовой" not in result

    def test_approved_table_list_black_and_colored(self):
        """Тест смешанного списка (черный + цветной) в подтвержденных"""
        html = '''
        <table>
            <tr>
                <td>
                    <p><strong>Типы документов:</strong></p>
                    <ul>
                        <li>Паспорт</li>
                        <li><span style="color: red;">Права (новое)</span></li>
                        <li>СНИЛС</li>
                    </ul>
                </td>
            </tr>
        </table>
        '''

        result = filter_approved_fragments(html)
        print(f"Mixed list result: '{result}'")

        # В подтвержденных должны быть только черные элементы
        assert "Типы документов:" in result
        assert "- Паспорт" in result
        assert "- СНИЛС" in result
        assert "Права (новое)" not in result  # Цветной элемент исключен

    def test_all_table_list_black_and_colored(self):
        """Тест смешанного списка (черный + цветной) во всех фрагментах"""
        html = '''
        <table>
            <tr>
                <td>
                    <p><strong>Типы документов:</strong></p>
                    <ul>
                        <li>Паспорт</li>
                        <li><span style="color: red;">Права (новое)</span></li>
                        <li>СНИЛС</li>
                    </ul>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"All mixed list result: '{result}'")

        # Во всех фрагментах должны быть ВСЕ элементы
        assert "Типы документов:" in result
        assert "- Паспорт" in result
        assert "- Права (новое)" in result  # Цветной элемент включен
        assert "- СНИЛС" in result

    def test_numbered_list_in_table(self):
        """Тест нумерованного списка в таблице"""
        html = '''
        <table>
            <tr>
                <td>
                    <p>Этапы процесса:</p>
                    <ol>
                        <li>Подача заявления</li>
                        <li>Проверка документов</li>
                        <li>Принятие решения</li>
                    </ol>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Numbered list result: '{result}'")

        assert "Этапы процесса:" in result
        assert "1. Подача заявления" in result
        assert "2. Проверка документов" in result
        assert "3. Принятие решения" in result

    def test_nested_list_in_table(self):
        """Тест вложенного списка в таблице"""
        html = '''
        <table>
            <tr>
                <td>
                    <p>Документы:</p>
                    <ul>
                        <li>Основные:
                            <ul>
                                <li>Паспорт</li>
                                <li>СНИЛС</li>
                            </ul>
                        </li>
                        <li>Дополнительные:
                            <ul>
                                <li>Справка</li>
                            </ul>
                        </li>
                    </ul>
                </td>
            </tr>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Nested list result: '{result}'")

        assert "Документы:" in result
        assert "- Основные:" in result
        assert "    * Паспорт" in result
        assert "    * СНИЛС" in result
        assert "- Дополнительные:" in result
        assert "    * Справка" in result


if __name__ == "__main__":
    # Запуск отдельных тестов для отладки
    test = TestTableLists()
    test.test_approved_table_list_colored()
    test.test_all_table_list_colored()
    print("✅ Все тесты прошли!")