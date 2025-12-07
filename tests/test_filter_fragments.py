# tests/test_filter_fragments.py

import pytest
from app.filter_approved_fragments import filter_approved_fragments
from app.filter_all_fragments import filter_all_fragments


class TestFilterFragments:

    def test_filter_approved_only_black_text(self):
        """Тест фильтрации только подтвержденного (черного) текста"""
        html = '''
        <p>Подтвержденный текст</p>
        <p style="color: red;">Неподтвержденный красный текст</p>
        <p style="color: black;">Подтвержденный черный текст</p>
        <p style="color: rgb(0,0,0);">Подтвержденный RGB черный</p>
        '''

        result = filter_approved_fragments(html)
        assert "Подтвержденный текст" in result
        assert "Подтвержденный черный текст" in result
        assert "Подтвержденный RGB черный" in result
        assert "Неподтвержденный красный текст" not in result

    def test_filter_all_fragments_includes_colored(self):
        """Тест фильтрации всех фрагментов включая цветные"""
        html = '''
        <p>Обычный текст</p>
        <p style="color: red;">Красный текст</p>
        <p style="color: blue;">Синий текст</p>
        '''

        result = filter_all_fragments(html)
        assert "Обычный текст" in result
        assert "Красный текст" in result
        assert "Синий текст" in result

    def test_filter_approved_links_in_approved_context(self):
        """Тест обработки ссылок в подтвержденном контексте"""
        html = '''
        <p>Подтвержденный текст со <a href="/page/123">ссылкой на страницу</a></p>
        <p style="color: red;">Цветной текст со <a href="/page/456">цветной ссылкой</a></p>
        '''

        result = filter_approved_fragments(html)
        assert "ссылкой на страницу" in result
        assert "цветной ссылкой" not in result

    def test_filter_approved_tables(self):
        """ИСПРАВЛЕНО: Тест фильтрации таблиц с подтвержденным содержимым"""
        # Используем HTML вместо Markdown для корректного тестирования
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

        result = filter_approved_fragments(html)
        assert "Идентификатор" in result
        assert "Новое поле" not in result

    def test_filter_strikethrough_text(self):
        """Тест игнорирования зачеркнутого текста"""
        html = '''
        <p>Обычный текст</p>
        <p><s>Зачеркнутый текст</s></p>
        <p>Еще обычный текст</p>
        '''

        result = filter_approved_fragments(html)
        assert "Обычный текст" in result
        assert "Еще обычный текст" in result
        assert "Зачеркнутый текст" not in result

    def test_filter_jira_macros(self):
        """Тест игнорирования JIRA макросов"""
        html = '''
        <p>Обычный текст</p>
        <ac:structured-macro ac:name="jira">
            <ac:parameter ac:name="key">TEST-123</ac:parameter>
        </ac:structured-macro>
        <p>Еще текст</p>
        '''

        result = filter_approved_fragments(html)
        assert "Обычный текст" in result
        assert "Еще текст" in result
        assert "TEST-123" not in result

    def test_filter_simple_text_paragraphs(self):
        """Дополнительный тест для простых параграфов"""
        html = '''
        <p>Простой параграф</p>
        <div>Простой div</div>
        '''

        result = filter_approved_fragments(html)
        assert "Простой параграф" in result
        assert "Простой div" in result