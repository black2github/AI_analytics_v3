# tests/test_spacing_fixes.py

"""
Unit тесты для проверки исправлений проблем с пробелами в filter_approved_fragments и filter_all_fragments.
Эти тесты должны предотвратить регрессии при будущих изменениях.
"""

import pytest
from app.filter_approved_fragments import filter_approved_fragments
from app.filter_all_fragments import filter_all_fragments


class TestSpacingFixes:
    """Тесты исправления проблем с пробелами"""

    def test_triangular_brackets_spacing_approved(self):
        """Тест исправления лишних пробелов в треугольных скобках (подтвержденные фрагменты)"""
        html = '''
        <table>
            <tr>
                <td>
                    <ul>
                        <li>
                            <span style="color: rgb(23,43,77);">Атрибуты из </span>
                            <a href="/page/123">Клиент Банка</a>
                            <span style="color: rgb(23,43,77);">.&lt;   Идентификатор клиента   &gt;</span>
                        </li>
                        <li>
                            Другой атрибут &lt; Название поля &gt; без лишних пробелов
                        </li>
                    </ul>
                </td>
            </tr>
        </table>
        '''

        result = filter_approved_fragments(html)
        print(f"Approved triangular brackets result: '{result}'")

        # V Проверяем, что лишние пробелы в треугольных скобках убраны
        assert "<Идентификатор клиента>" in result
        assert "<Название поля>" in result

        # X Проверяем, что старый формат с лишними пробелами отсутствует
        assert "< Идентификатор клиента >" not in result
        assert "<   Идентификатор клиента   >" not in result
        assert "< Название поля >" not in result

    def test_triangular_brackets_spacing_all(self):
        """Тест исправления лишних пробелов в треугольных скобках (все фрагменты)"""
        html = '''
        <p>
            Проверить <span style="color: red;">сущность.&lt;  атрибут с пробелами  &gt;</span> 
            и <span style="color: blue;">другую_сущность.&lt;простой_атрибут&gt;</span>
        </p>
        '''

        result = filter_all_fragments(html)
        print(f"All triangular brackets result: '{result}'")

        # V Проверяем правильные форматы
        assert "<атрибут с пробелами>" in result
        assert "<простой_атрибут>" in result

        # X Проверяем отсутствие неправильных форматов
        assert "<  атрибут с пробелами  >" not in result

    def test_word_spacing_preservation_approved(self):
        """Тест сохранения пробелов между обычными словами (подтвержденные фрагменты)"""
        html = '''
        <table>
            <tr>
                <td>
                    <p>
                        <strong>Если </strong>
                        <span style="color: rgb(23,43,77);">Входящие параметры</span>
                        <span style="color: rgb(23,43,77);">.&lt;Список клиентов&gt; пустой, </span>
                        <strong>то</strong>
                    </p>
                </td>
            </tr>
        </table>
        '''

        result = filter_approved_fragments(html)
        print(f"Word spacing approved result: '{result}'")

        # V Проверяем, что пробелы между словами сохранены
        assert "Если Входящие параметры" in result
        assert "пустой, то" in result

        # X Проверяем, что слова не склеены
        assert "ЕслиВходящие" not in result
        assert "пустой,то" not in result

    def test_word_spacing_preservation_all(self):
        """Тест сохранения пробелов между обычными словами (все фрагменты)"""
        html = '''
        <div>
            <span>Первое </span>
            <span style="color: red;">слово </span>
            <span>второе </span>
            <span style="color: blue;">третье</span>
            <span> четвертое</span>
        </div>
        '''

        result = filter_all_fragments(html)
        print(f"Word spacing all result: '{result}'")

        # V Проверяем правильные пробелы
        assert "Первое слово второе третье четвертое" in result

        # X Проверяем отсутствие склеивания
        assert "Первоеслово" not in result
        assert "третьечетвертое" not in result

    def test_complex_real_world_example_approved(self):
        """Тест реального сложного примера из задачи (подтвержденные фрагменты)"""
        html = '''
        <table class="relative-table wrapped confluenceTable">
            <thead>
                <tr>
                    <th>HDR</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>
                        <ul>
                            <li>
                                <span style="color: rgb(23,43,77);">&lt;1&gt;. Атрибуты из </span>
                                <a href="/page/328259">Клиент Банка</a>
                                <span style="color: rgb(23,43,77);">.&lt; Идентификатор клиента &gt;</span>
                            </li>
                            <li>
                                &lt;2&gt;. 
                                <a href="/page/328218">Представитель Клиента</a>
                                .&lt;
                                <span style="color: rgb(23,43,77);">Ссылка на сущность "</span>
                                <a href="/page/328259">Клиент Банка</a>
                                <span style="color: rgb(23,43,77);">"</span>
                                &gt; == 
                                <a href="/page/328259">Клиент Банка</a>
                                <span style="color: rgb(255,0,0);">.&lt;Идентификатор записи&gt;</span>
                            </li>
                            <li>
                                <span style="color: rgb(23,43,77);">&lt;Список клиентов&gt; . (опциональный). Атрибуты из </span>
                                <a href="/page/328259">Клиент Банка</a>
                                .&lt;
                                <span style="color: rgb(23,43,77);"> Идентификатор клиента </span>
                                &gt;
                            </li>
                        </ul>
                        <p style="margin-left: 40.0px;">
                            <strong>Если  </strong>
                            <span style="color: rgb(23,43,77);">Входящие параметры.&lt;Список клиентов&gt; пустой, </span>
                            <strong>то</strong>
                        </p>
                    </td>
                </tr>
            </tbody>
        </table>
        '''

        result = filter_approved_fragments(html)
        print(f"Complex real example result: '{result}'")

        # V Проверяем правильное исправление треугольных скобок
        assert "<Идентификатор клиента>" in result
        assert "<Список клиентов>" in result

        # V Проверяем сохранение пробелов между словами
        assert "Если Входящие параметры" in result
        assert "пустой, то" in result

        # X Проверяем отсутствие проблем
        assert "< Идентификатор клиента >" not in result
        assert "ЕслиВходящие" not in result

    def test_complex_real_world_example_all(self):
        """Тест реального сложного примера из задачи (все фрагменты)"""
        html = '''
        <table class="relative-table wrapped confluenceTable">
            <thead>
                <tr>
                    <th>HDR</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>
                        <ul>
                            <li>
                                <span style="color: rgb(23,43,77);">&lt;1&gt;. Атрибуты из </span>
                                <a href="/page/328259">Клиент Банка</a>
                                <span style="color: rgb(23,43,77);">.&lt; Идентификатор клиента &gt;</span>
                            </li>
                        </ul>
                        <p style="margin-left: 40.0px;">
                            <strong>Если  </strong>
                            <span style="color: rgb(23,43,77);">Входящие параметры.&lt;Список клиентов&gt; пустой, </span>
                            <strong>то</strong>
                        </p>
                    </td>
                </tr>
            </tbody>
        </table>
        '''

        result = filter_all_fragments(html)
        print(f"Complex real example all result: '{result}'")

        # V Все фрагменты включают цветные элементы
        assert "<1>. Атрибуты из [Клиент Банка].<Идентификатор клиента>" in result
        assert "Если Входящие параметры.<Список клиентов> пустой, то" in result

        # X Но без проблем с пробелами
        assert "< Идентификатор клиента >" not in result
        assert "ЕслиВходящие" not in result

    def test_multiple_spaces_normalization(self):
        """Тест нормализации множественных пробелов"""
        html = '''
        <p>
            Текст    с     множественными        пробелами
            и &lt;   атрибут   с   пробелами   &gt;
        </p>
        '''

        result_approved = filter_approved_fragments(html)
        result_all = filter_all_fragments(html)

        # V Множественные пробелы должны стать одинарными
        assert "Текст с множественными пробелами" in result_approved
        assert "Текст с множественными пробелами" in result_all

        # V В треугольных скобках убираем все лишние пробелы
        assert "<атрибут с пробелами>" in result_approved
        assert "<атрибут с пробелами>" in result_all

        # X Множественные пробелы не должны остаться
        assert "пробелами        и" not in result_approved
        assert "   атрибут   с   пробелами   " not in result_approved

    def test_edge_cases_spacing(self):
        """Тест граничных случаев с пробелами"""
        test_cases = [
            # Только пробелы в треугольных скобках
            ('<span>&lt;   &gt;</span>', '<>'),

            # Треугольные скобки с переносами строк
            ('<span>&lt;\n  атрибут  \n&gt;</span>', '<атрибут>'),

            # Множественные треугольные скобки
            ('<span>&lt; атрибут1 &gt; и &lt;  атрибут2  &gt;</span>', '<атрибут1> и <атрибут2>'),

            # Пробелы до и после слов
            ('<span>  Слово1   Слово2  </span>', 'Слово1 Слово2'),
        ]

        for html_input, expected_content in test_cases:
            result = filter_approved_fragments(f'<p>{html_input}</p>')
            print(f"Edge case: '{html_input}' -> '{result}'")

            assert expected_content in result, f"Expected '{expected_content}' in '{result}'"

    def test_regression_previous_functionality(self):
        """Регрессионный тест - проверяем, что предыдущая функциональность не сломалась"""
        html = '''
        <div>
            <h2>Заголовок</h2>
            <p>Обычный текст без проблем</p>
            <ul>
                <li>Элемент списка 1</li>
                <li style="color: red;">Цветной элемент</li>
                <li>Элемент списка 2</li>
            </ul>
            <table>
                <tr>
                    <th>Поле</th>
                    <th>Значение</th>
                </tr>
                <tr>
                    <td>test</td>
                    <td>value</td>
                </tr>
            </table>
        </div>
        '''

        # Проверяем, что основная функциональность не пострадала
        result_approved = filter_approved_fragments(html)
        result_all = filter_all_fragments(html)

        # V Заголовки работают
        assert "## Заголовок" in result_approved
        assert "## Заголовок" in result_all

        # V Списки работают
        assert "- Элемент списка 1" in result_approved
        assert "- Элемент списка 2" in result_approved
        assert "- Цветной элемент" in result_all  # В all включается
        assert "Цветной элемент" not in result_approved  # В approved исключается

        # V Таблицы работают
        assert "| Поле | Значение |" in result_approved
        assert "| test | value |" in result_approved

        print("V Регрессионный тест прошел - основная функциональность сохранена")

    def test_complex_triangular_brackets_with_quotes_and_links(self):
        """Тест сложных треугольных скобок с кавычками и ссылками"""
        html = '''
        <table>
            <tr>
                <td>
                    <ul>
                        <li>
                            &lt;2&gt;. 
                            <a href="/page/328218">Представитель Клиента</a>
                            .&lt;
                            <span style="color: rgb(23,43,77);">Ссылка на сущность "</span>
                            <a href="/page/328259">Клиент Банка</a>
                            <span style="color: rgb(23,43,77);">"</span>
                            &gt; == 
                            <a href="/page/328259">Клиент Банка</a>
                            <span style="color: rgb(255,0,0);">.&lt;Идентификатор записи&gt;</span>
                        </li>
                    </ul>
                </td>
            </tr>
        </table>
        '''

        result_approved = filter_approved_fragments(html)
        result_all = filter_all_fragments(html)

        print(f"Complex brackets approved: '{result_approved}'")
        print(f"Complex brackets all: '{result_all}'")

        # Ok Правильный формат без лишних пробелов
        assert '<Ссылка на сущность "[Клиент Банка]">' in result_approved
        assert '<Ссылка на сущность "[Клиент Банка]">' in result_all

        # X Неправильный формат с лишними пробелами
        assert '<Ссылка на сущность " [Клиент Банка] ">' not in result_approved
        assert '<Ссылка на сущность " [Клиент Банка] ">' not in result_all


if __name__ == "__main__":
    # Возможность запустить тесты напрямую
    test = TestSpacingFixes()

    print("=== Запуск тестов исправления пробелов ===")

    test.test_triangular_brackets_spacing_approved()
    print("V Треугольные скобки (approved) - OK")

    test.test_triangular_brackets_spacing_all()
    print("V Треугольные скобки (all) - OK")

    test.test_word_spacing_preservation_approved()
    print("V Пробелы между словами (approved) - OK")

    test.test_word_spacing_preservation_all()
    print("V Пробелы между словами (all) - OK")

    test.test_complex_real_world_example_approved()
    print("V Сложный реальный пример (approved) - OK")

    test.test_complex_real_world_example_all()
    print("V Сложный реальный пример (all) - OK")

    test.test_multiple_spaces_normalization()
    print("V Нормализация множественных пробелов - OK")

    test.test_edge_cases_spacing()
    print("V Граничные случаи - OK")

    test.test_regression_previous_functionality()
    print("V Регрессионный тест - OK")

    print("\nOK Все тесты исправления пробелов прошли успешно!")