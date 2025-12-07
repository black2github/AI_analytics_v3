# tests/test_link_spacing.py

from app.filter_all_fragments import filter_all_fragments


def test_link_spacing_fix():
    """Тест исправления лишних пробелов в ссылках"""

    html = '''
    <span style="color: rgb(0,0,0);">
        <span style="color: rgb(0,51,102);">
            <a href="/pages/viewpage.action?pageId=42670178">[КК_БК] Заявка на блокировку карты</a>
        </span>,
    </span>
    '''

    result = filter_all_fragments(html)
    print(f"Результат: '{result}'")

    # Проверяем, что нет лишних пробелов
    assert result.strip() == "[[КК_БК] Заявка на блокировку карты],"
    # Не должно быть: "- [[КК_БК] Заявка на блокировку карты] ,"

    print("V Тест прошел! Лишние пробелы убраны.")


def test_complex_link_structure():
    """Тест сложной структуры с вложенными span и ссылками"""

    html = '''
    <p>
        Смотри документ: 
        <span style="color: rgb(0,0,0);">
            <span style="color: rgb(0,51,102);">
                <a href="/pages/viewpage.action?pageId=12345">Требования к системе</a>
            </span>
            и еще 
            <span style="color: rgb(255,0,0);">
                <a href="/pages/viewpage.action?pageId=67890">Техническое задание</a>
            </span>.
        </span>
    </p>
    '''

    result = filter_all_fragments(html)
    print(f"Сложная структура: '{result}'")

    # Ожидаем правильный результат без лишних пробелов
    expected = "Смотри документ: [Требования к системе] и еще [Техническое задание]."
    assert result.strip() == expected

    print("V Сложная структура обработана корректно!")


def test_all_table_list_structure():
    """НОВЫЙ ТЕСТ: Проверка структуры списков в таблицах (все фрагменты)"""
    html = '''
    <table>
        <tr>
            <td class="confluenceTd">
                <div class="content-wrapper">
                    <p><strong>Наименование поля:</strong> отображается список категорий:</p>
                    <ul>
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
    print(f"All fragments table list result: '{result}'")

    # Проверяем правильную структуру списка
    assert "Наименование поля: отображается список категорий:" in result
    assert "- Дневной" in result
    assert "- Месячный" in result

    # Главное - проверяем, что НЕТ склеенной строки
    assert "ДневнойМесячныйКвартальныйГодовой" not in result
    assert "категорий:Дневной" not in result

    print("V Тест структуры списков в таблицах (все фрагменты) прошел!")


def test_all_simple_paragraphs():
    """НОВЫЙ ТЕСТ: Проверка, что простые параграфы не сломались"""
    html = '''
    <p>Простой параграф.</p>
    <p>Еще один <strong>параграф</strong> с выделением.</p>
    <p style="color: red;">Цветной параграф (должен быть включен).</p>
    <p>Финальный параграф.</p>
    '''

    result = filter_all_fragments(html)
    print(f"All simple paragraphs result: '{result}'")

    assert "Простой параграф." in result
    assert "Еще один параграф с выделением." in result
    assert "Цветной параграф (должен быть включен)." in result
    assert "Финальный параграф." in result

    print("V Тест простых параграфов (все фрагменты) прошел!")


def test_all_simple_lists():
    """НОВЫЙ ТЕСТ: Проверка, что обычные списки не сломались"""
    html = '''
    <p>Требования:</p>
    <ul>
        <li>Первое требование</li>
        <li><span style="color: red;">Цветное требование</span></li>
        <li>Третье требование</li>
    </ul>
    '''

    result = filter_all_fragments(html)
    print(f"All simple lists result: '{result}'")

    assert "Требования:" in result
    assert "- Первое требование" in result
    assert "- Третье требование" in result
    assert "Цветное требование" in result  # В ALL фрагментах цветные включены

    print("V Тест простых списков (все фрагменты) прошел!")


if __name__ == "__main__":
    test_link_spacing_fix()
    test_complex_link_structure()
    test_all_table_list_structure()
    test_all_simple_paragraphs()
    test_all_simple_lists()
    print("!!! Все тесты всех фрагментов прошли!")
