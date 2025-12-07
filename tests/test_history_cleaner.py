# tests/test_history_cleaner.py

import pytest
from app.history_cleaner import (
    remove_history_sections,
    _remove_expand_history_blocks,
    _remove_header_history_sections,
    _remove_paragraph_history_sections,
    _is_history_text,
    _is_history_table
)
from bs4 import BeautifulSoup


class TestHistoryCleaner:

    def test_remove_expand_history_blocks(self):
        """Тест удаления expand блоков с историей изменений"""
        html = '''
        <div class="expand-container conf-macro output-block">
            <div class="expand-control">
                <span>История изменений</span>
            </div>
            <div class="expand-content">
                <table><tr><td>Test history</td></tr></table>
            </div>
        </div>
        <p>Regular content</p>
        '''

        result = remove_history_sections(html)
        assert "История изменений" not in result
        assert "Regular content" in result
        assert "Test history" not in result

    def test_remove_header_history_sections(self):
        """Тест удаления заголовков истории изменений"""
        html = '''
        <h1>Regular Header</h1>
        <p>Regular content</p>
        <h2 id="historia-izmeneniy">История изменений</h2>
        <div class="table-wrap">
            <table><tr><td>History data</td></tr></table>
        </div>
        <p>More regular content</p>
        '''

        result = remove_history_sections(html)
        assert "Regular Header" in result
        assert "Regular content" in result
        assert "More regular content" in result
        assert "История изменений" not in result
        assert "History data" not in result

    def test_remove_paragraph_history_sections(self):
        """Тест удаления параграфов истории изменений"""
        html = '''
        <p>Normal paragraph</p>
        <p><strong>История изменений:</strong></p>
        <div class="table-wrap">
            <table>
                <tr><th>Дата</th><th>Описание</th><th>Автор</th></tr>
                <tr><td>01.01.2023</td><td>Initial</td><td>User</td></tr>
            </table>
        </div>
        <p>Another normal paragraph</p>
        '''

        result = remove_history_sections(html)
        assert "Normal paragraph" in result
        assert "Another normal paragraph" in result
        assert "История изменений:" not in result
        assert "Initial" not in result

    def test_is_history_text(self):
        """Тест определения текста истории изменений"""
        assert _is_history_text("История изменений")
        assert _is_history_text("История изменений:")
        assert _is_history_text("ИСТОРИЯ ИЗМЕНЕНИЙ")
        assert _is_history_text("Change History")
        assert _is_history_text("id-историяизменений")

        assert not _is_history_text("Обычный текст")
        assert not _is_history_text("История документа")
        assert not _is_history_text("")

    def test_is_history_table(self):
        """Тест определения таблицы истории изменений"""
        # Таблица истории изменений
        history_html = '''
        <table>
            <thead>
                <tr><th>Дата</th><th>Описание</th><th>Автор</th><th>Задача в JIRA</th></tr>
            </thead>
            <tbody>
                <tr><td>01.01.2023</td><td>Test</td><td>User</td><td>TASK-123</td></tr>
            </tbody>
        </table>
        '''
        history_table = BeautifulSoup(history_html, 'html.parser').find('table')
        assert _is_history_table(history_table)

        # Обычная таблица
        regular_html = '''
        <table>
            <thead>
                <tr><th>Поле</th><th>Тип</th><th>Описание</th></tr>
            </thead>
            <tbody>
                <tr><td>id</td><td>string</td><td>Идентификатор</td></tr>
            </tbody>
        </table>
        '''
        regular_table = BeautifulSoup(regular_html, 'html.parser').find('table')
        assert not _is_history_table(regular_table)

    def test_complex_history_removal(self):
        """Тест комплексного удаления всех типов истории"""
        html = '''
        <h1>Основные требования</h1>
        <p>Важный контент требований</p>

        <!-- Expand блок с историей -->
        <div class="expand-container">
            <div class="expand-control">
                <span>История изменений</span>
            </div>
            <div class="expand-content">
                <table><tr><td>Expand history</td></tr></table>
            </div>
        </div>

        <p>Еще требования</p>

        <!-- Заголовок с историей -->
        <h2>История изменений</h2>
        <div class="table-wrap">
            <table><tr><td>Header history</td></tr></table>
        </div>

        <!-- Параграф с историей -->
        <p><strong>История изменений:</strong></p>
        <table><tr><td>Paragraph history</td></tr></table>

        <p>Финальный контент</p>
        '''

        result = remove_history_sections(html)

        # Проверяем, что основной контент остался
        assert "Основные требования" in result
        assert "Важный контент требований" in result
        assert "Еще требования" in result
        assert "Финальный контент" in result

        # Проверяем, что вся история удалена
        assert "Expand history" not in result
        assert "Header history" not in result
        assert "Paragraph history" not in result
        assert "История изменений" not in result