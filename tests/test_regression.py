# tests/test_regression.py
"""
Регрессионные тесты для проверки, что исправления не сломали существующую функциональность
"""

from app.filter_all_fragments import filter_all_fragments
from app.filter_approved_fragments import filter_approved_fragments


def test_headers_not_broken():
    """Проверка, что заголовки обрабатываются корректно"""
    html = '''
    <h1>Основной заголовок</h1>
    <h2 style="color: red;">Цветной заголовок</h2>
    <h3>Подзаголовок</h3>
    '''

    # Все фрагменты
    all_result = filter_all_fragments(html)
    assert "# Основной заголовок" in all_result
    assert "## Цветной заголовок" in all_result
    assert "### Подзаголовок" in all_result

    # Только подтвержденные
    approved_result = filter_approved_fragments(html)
    assert "# Основной заголовок" in approved_result
    assert "### Подзаголовок" in approved_result
    assert "Цветной заголовок" not in approved_result

    print("V Заголовки обрабатываются корректно")


def test_tables_not_broken():
    """Проверка, что обычные таблицы без списков работают"""
    html = '''
    <table>
        <thead>
            <tr><th>Поле</th><th>Тип</th></tr>
        </thead>
        <tbody>
            <tr><td>id</td><td>string</td></tr>
            <tr><td>name</td><td><span style="color: red;">новое поле</span></td></tr>
        </tbody>
    </table>
    '''

    # Все фрагменты
    all_result = filter_all_fragments(html)
    assert "| Поле | Тип |" in all_result
    assert "| id | string |" in all_result
    assert "| name | новое поле |" in all_result

    # Только подтвержденные
    approved_result = filter_approved_fragments(html)
    assert "| Поле | Тип |" in approved_result
    assert "| id | string |" in approved_result
    assert "новое поле" not in approved_result

    print("V Обычные таблицы работают корректно")


def test_links_not_broken():
    """Проверка, что ссылки обрабатываются корректно"""
    html = '''
    <p>Смотри <a href="/page/123">документ требований</a> и 
    <span style="color: red;"><a href="/page/456">новый документ</a></span>.</p>
    '''

    # Все фрагменты
    all_result = filter_all_fragments(html)
    assert "[документ требований]" in all_result
    assert "[новый документ]" in all_result

    # Только подтвержденные (упрощенная проверка)
    approved_result = filter_approved_fragments(html)
    assert "[документ требований]" in approved_result

    print("V Ссылки обрабатываются корректно")


def test_mixed_content():
    """Комплексный тест смешанного контента"""
    html = '''
    <h2>Спецификация API</h2>
    <p>Основные <strong>требования</strong> к системе:</p>
    <ul>
        <li>Производительность</li>
        <li><span style="color: blue;">Новое требование безопасности</span></li>
        <li>Масштабируемость</li>
    </ul>

    <table>
        <tr>
            <th>Метод</th>
            <th>Описание</th>
        </tr>
        <tr>
            <td>GET /users</td>
            <td>Получение списка пользователей</td>
        </tr>
    </table>
    '''

    # Все фрагменты
    all_result = filter_all_fragments(html)
    assert "## Спецификация API" in all_result
    assert "Основные требования к системе:" in all_result
    assert "- Производительность" in all_result
    assert "- Новое требование безопасности" in all_result
    assert "- Масштабируемость" in all_result
    assert "| Метод | Описание |" in all_result

    # Только подтвержденные
    approved_result = filter_approved_fragments(html)
    assert "## Спецификация API" in approved_result
    assert "Основные требования к системе:" in approved_result
    assert "- Производительность" in approved_result
    assert "- Масштабируемость" in approved_result
    assert "Новое требование безопасности" not in approved_result

    print("V Смешанный контент обрабатывается корректно")


if __name__ == "__main__":
    test_headers_not_broken()
    test_tables_not_broken()
    test_links_not_broken()
    test_mixed_content()
    print("!!! Все регрессионные тесты прошли!")