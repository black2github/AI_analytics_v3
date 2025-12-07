# tests/test_approved_fragments_spacing.py

from app.filter_approved_fragments import filter_approved_fragments


def test_approved_link_spacing_fix():
    """Тест исправления лишних пробелов в подтвержденных ссылках"""

    html = '''
    <span style="color: rgb(0,0,0);">
        <span style="color: rgb(0,51,102);">
            <a href="/pages/viewpage.action?pageId=42670178">[КК_БК] Заявка на блокировку карты</a>
        </span>,
    </span>
    '''

    result = filter_approved_fragments(html)
    print(f"Результат (approved): '{result}'")

    # Проверяем, что нет лишних пробелов
    assert result.strip() == "[[КК_БК] Заявка на блокировку карты],"

    print("V Тест подтвержденных фрагментов прошел!")


def test_nested_table_links():
    """Тест ссылок во вложенных таблицах"""

    html = '''
    <table>
        <tr>
            <td>
                Документ: 
                <a href="/page/123">Техзадание</a>
                .
            </td>
        </tr>
    </table>
    '''

    result = filter_approved_fragments(html)
    print(f"Вложенная таблица: '{result}'")

    # Не должно быть лишних пробелов
    expected = "| Документ: [Техзадание]. |"
    assert result.strip() in expected or "Документ: [Техзадание]." in result

    print("V Тест вложенных таблиц прошел!")


def test_approved_table_list_structure():
    """НОВЫЙ ТЕСТ: Проверка структуры списков в таблицах (подтвержденные)"""
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

    result = filter_approved_fragments(html)
    print(f"Approved table list result: '{result}'")

    # Проверяем правильную структуру списка
    assert "Наименование поля: отображается список категорий:" in result
    assert "- Дневной" in result
    assert "- Месячный" in result

    # Главное - проверяем, что НЕТ склеенной строки
    assert "ДневнойМесячныйКвартальныйГодовой" not in result
    assert "категорий:Дневной" not in result

    print("V Тест структуры списков в таблицах (подтвержденные) прошел!")


def test_approved_simple_paragraphs():
    """НОВЫЙ ТЕСТ: Проверка, что простые параграфы не сломались"""
    html = '''
    <p>Простой параграф.</p>
    <p>Еще один <strong>параграф</strong> с выделением.</p>
    <p style="color: red;">Цветной параграф (должен быть исключен).</p>
    <p>Финальный параграф.</p>
    '''

    result = filter_approved_fragments(html)
    print(f"Simple paragraphs result: '{result}'")

    assert "Простой параграф." in result
    assert "Еще один параграф с выделением." in result
    assert "Финальный параграф." in result
    assert "Цветной параграф" not in result

    print("V Тест простых параграфов (подтвержденные) прошел!")


def test_approved_simple_lists():
    """НОВЫЙ ТЕСТ: Проверка, что обычные списки не сломались"""
    html = '''
    <p>Требования:</p>
    <ul>
        <li>Первое требование</li>
        <li><span style="color: red;">Цветное требование</span></li>
        <li>Третье требование</li>
    </ul>
    '''

    result = filter_approved_fragments(html)
    print(f"Simple lists result: '{result}'")

    assert "Требования:" in result
    assert "- Первое требование" in result
    assert "- Третье требование" in result
    assert "Цветное требование" not in result

    print("V Тест простых списков (подтвержденные) прошел!")


if __name__ == "__main__":
    test_approved_link_spacing_fix()
    test_nested_table_links()
    test_approved_table_list_structure()
    test_approved_simple_paragraphs()
    test_approved_simple_lists()
    print("!!! Все тесты подтвержденных фрагментов прошли!")
