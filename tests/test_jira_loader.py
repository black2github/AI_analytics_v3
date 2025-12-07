# tests/test_jira_loader.py

import pytest
from unittest.mock import patch, Mock
import requests
from bs4 import BeautifulSoup
from app.jira_loader import (
    extract_confluence_page_ids_from_jira_tasks,
    _extract_confluence_page_ids_from_html,
    _extract_page_id_from_url,
    get_jira_task_description_via_session,
    authenticate_via_web_session,
    _get_jira_auth
)


class TestJiraLoader:
    """Тесты для модуля jira_loader"""

    def test_extract_page_id_from_url_viewpage_action(self):
        """Тест извлечения pageId из URL с viewpage.action"""
        url = "https://confluence.gboteam.ru/pages/viewpage.action?pageId=245113389"
        result = _extract_page_id_from_url(url)
        assert result == "245113389"

    def test_extract_page_id_from_url_display_format(self):
        """Тест извлечения pageId из URL с display формата"""
        url = "https://confluence.gboteam.ru/display/SPACE/Page+Title?pageId=123456789"
        result = _extract_page_id_from_url(url)
        assert result == "123456789"

    def test_extract_page_id_from_url_query_params(self):
        """Тест извлечения pageId с дополнительными параметрами"""
        url = "https://confluence.gboteam.ru/pages/viewpage.action?spaceKey=TEST&pageId=111111111&version=1"
        result = _extract_page_id_from_url(url)
        assert result == "111111111"

    def test_extract_page_id_from_url_short_link(self):
        """Тест обработки коротких ссылок (пока не реализовано)"""
        url = "https://confluence.gboteam.ru/x/ABC123"
        result = _extract_page_id_from_url(url)
        assert result is None  # Короткие ссылки пока не поддерживаются

    def test_extract_page_id_from_url_invalid(self):
        """Тест обработки невалидных URL"""
        invalid_urls = [
            "https://google.com",
            "https://confluence.gboteam.ru/pages/viewpage.action",
            "",
            None
        ]

        for url in invalid_urls:
            result = _extract_page_id_from_url(url)
            assert result is None, f"Should return None for URL: {url}"

    def test_extract_confluence_page_ids_from_html_basic(self):
        """Тест извлечения page_ids из простого HTML"""
        html_content = """
        <div class="user-content-block">
            <p>Смотри требования тут:</p>
            <a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=245113389">Требования 1</a>
            <p>и еще тут:</p>
            <a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=123456789">Требования 2</a>
        </div>
        """

        result = _extract_confluence_page_ids_from_html(html_content)

        assert len(result) == 2
        assert "245113389" in result
        assert "123456789" in result

    def test_extract_confluence_page_ids_from_html_table(self):
        """Тест извлечения page_ids из таблицы"""
        html_content = """
        <div class="user-content-block">
            <table class="confluenceTable">
                <tr>
                    <td>Функции</td>
                    <td><a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=111111111">Ссылка 1</a></td>
                </tr>
                <tr>
                    <td>ЭФ</td>
                    <td><a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=222222222">Ссылка 2</a></td>
                </tr>
            </table>
        </div>
        """

        result = _extract_confluence_page_ids_from_html(html_content)

        assert len(result) == 2
        assert "111111111" in result
        assert "222222222" in result

    def test_extract_confluence_page_ids_from_html_text_patterns(self):
        """Тест извлечения pageId из текстовых паттернов"""
        html_content = """
        <div class="user-content-block">
            <p>Прямое упоминание pageId=333333333 в тексте</p>
            <span>Еще один pageId: 444444444</span>
        </div>
        """

        result = _extract_confluence_page_ids_from_html(html_content)

        assert len(result) == 2
        assert "333333333" in result
        assert "444444444" in result

    def test_extract_confluence_page_ids_from_html_duplicates(self):
        """Тест дедупликации одинаковых page_ids"""
        html_content = """
        <div class="user-content-block">
            <a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=123456789">Ссылка 1</a>
            <a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=123456789">Ссылка 2</a>
            <p>pageId=123456789</p>
        </div>
        """

        result = _extract_confluence_page_ids_from_html(html_content)

        assert len(result) == 1
        assert "123456789" in result

    def test_extract_confluence_page_ids_from_html_empty(self):
        """Тест обработки пустого HTML"""
        empty_inputs = ["", None, "<div></div>", "<p>Нет ссылок</p>"]

        for html_input in empty_inputs:
            result = _extract_confluence_page_ids_from_html(html_input)
            assert len(result) == 0, f"Should return empty list for input: {html_input}"

    @patch('app.jira_loader.JIRA_USER', 'test_user')
    @patch('app.jira_loader.JIRA_PASSWORD', 'test_password')
    @patch('app.jira_loader.JIRA_API_TOKEN', '')
    def test_get_jira_auth_password(self):
        """Тест получения аутентификации с паролем"""
        result = _get_jira_auth()
        assert result == ('test_user', 'test_password')

    @patch('app.jira_loader.JIRA_USER', 'test_user')
    @patch('app.jira_loader.JIRA_PASSWORD', '')
    @patch('app.jira_loader.JIRA_API_TOKEN', 'test_token')
    def test_get_jira_auth_token(self):
        """Тест получения аутентификации с API токеном"""
        result = _get_jira_auth()
        assert result == ('test_user', 'test_token')

    @patch('app.jira_loader.JIRA_USER', '')
    @patch('app.jira_loader.JIRA_PASSWORD', '')
    @patch('app.jira_loader.JIRA_API_TOKEN', '')
    def test_get_jira_auth_none(self):
        """Тест когда аутентификация не настроена"""
        result = _get_jira_auth()
        assert result is None

    @patch('requests.Session')
    @patch('app.jira_loader.JIRA_BASE_URL', 'https://jira.test.com')
    def test_authenticate_via_web_session_success(self, mock_session_class):
        """Тест успешной веб-аутентификации"""
        # Настройка мока сессии
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Мок для страницы логина
        login_response = Mock()
        login_response.status_code = 200
        login_response.text = '''
        <form id="login-form" action="/login.jsp" method="post">
            <input type="text" name="os_username" />
            <input type="password" name="os_password" />
            <input type="hidden" name="os_destination" value="" />
            <input type="hidden" name="atl_token" value="test_token" />
        </form>
        '''

        # Мок для успешного логина
        dologin_response = Mock()
        dologin_response.status_code = 200
        dologin_response.url = 'https://jira.test.com/secure/Dashboard.jspa'

        mock_session.get.return_value = login_response
        mock_session.post.return_value = dologin_response

        result = authenticate_via_web_session('test_user', 'test_password')

        assert result is not None
        assert result == mock_session
        mock_session.get.assert_called_once_with('https://jira.test.com/login.jsp', timeout=10)
        mock_session.post.assert_called_once()

    @patch('requests.Session')
    @patch('app.jira_loader.JIRA_BASE_URL', 'https://jira.test.com')
    def test_authenticate_via_web_session_failed(self, mock_session_class):
        """Тест неудачной веб-аутентификации"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Мок для страницы логина
        login_response = Mock()
        login_response.status_code = 200
        login_response.text = '<form id="login-form"></form>'

        # Мок для неудачного логина (редирект обратно на login.jsp)
        dologin_response = Mock()
        dologin_response.status_code = 200
        dologin_response.url = 'https://jira.test.com/login.jsp'

        mock_session.get.return_value = login_response
        mock_session.post.return_value = dologin_response

        result = authenticate_via_web_session('test_user', 'wrong_password')

        assert result is None

    @patch('app.jira_loader.authenticate_via_web_session')
    @patch('app.jira_loader.JIRA_USER', 'test_user')
    @patch('app.jira_loader.JIRA_PASSWORD', 'test_password')
    @patch('app.jira_loader.JIRA_BASE_URL', 'https://jira.test.com')
    def test_get_jira_task_description_via_session_success(self, mock_auth):
        """Тест успешного получения описания задачи через сессию"""
        # Настройка мока аутентификации
        mock_session = Mock()
        mock_auth.return_value = mock_session

        # Мок HTML страницы задачи
        task_html = '''
        <html>
            <div class="mod-content">
                <div class="user-content-block">
                    <p>Описание задачи с ссылкой:</p>
                    <a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=123456789">Требования</a>
                </div>
            </div>
        </html>
        '''

        task_response = Mock()
        task_response.status_code = 200
        task_response.text = task_html
        task_response.url = 'https://jira.test.com/browse/GBO-123'

        mock_session.get.return_value = task_response

        result = get_jira_task_description_via_session('GBO-123')

        assert result is not None
        assert 'user-content-block' in result
        assert '123456789' in result
        mock_session.get.assert_called_once_with('https://jira.test.com/browse/GBO-123', timeout=30)

    @patch('app.jira_loader.authenticate_via_web_session')
    @patch('app.jira_loader.JIRA_USER', 'test_user')
    @patch('app.jira_loader.JIRA_PASSWORD', 'test_password')
    def test_get_jira_task_description_via_session_auth_failed(self, mock_auth):
        """Тест когда аутентификация не удалась"""
        mock_auth.return_value = None

        result = get_jira_task_description_via_session('GBO-123')

        assert result is None

    @patch('app.jira_loader.get_jira_task_description_via_session')
    def test_extract_confluence_page_ids_from_jira_tasks_success(self, mock_get_description):
        """Тест успешного извлечения page_ids из задач Jira"""
        # Настройка моков
        mock_get_description.side_effect = [
            '<div class="user-content-block"><a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=111111111">Link 1</a></div>',
            '<div class="user-content-block"><a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=222222222">Link 2</a></div>'
        ]

        result = extract_confluence_page_ids_from_jira_tasks(["GBO-123", "GBO-456"])

        assert len(result) == 2
        assert "111111111" in result
        assert "222222222" in result

        # Проверяем вызовы
        assert mock_get_description.call_count == 2
        mock_get_description.assert_any_call("GBO-123")
        mock_get_description.assert_any_call("GBO-456")

    @patch('app.jira_loader.get_jira_task_description_via_session')
    def test_extract_confluence_page_ids_from_jira_tasks_duplicates(self, mock_get_description):
        """Тест дедупликации одинаковых page_ids из разных задач"""
        # Настройка моков - обе задачи содержат одинаковый page_id
        mock_get_description.side_effect = [
            '<div class="user-content-block"><a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=123456789">Link 1</a></div>',
            '<div class="user-content-block"><a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=123456789">Link 2</a></div>'
        ]

        result = extract_confluence_page_ids_from_jira_tasks(["GBO-123", "GBO-456"])

        assert len(result) == 1
        assert "123456789" in result

    @patch('app.jira_loader.get_jira_task_description_via_session')
    def test_extract_confluence_page_ids_from_jira_tasks_no_description(self, mock_get_description):
        """Тест когда описание задачи не получено"""
        mock_get_description.side_effect = [None, None]

        result = extract_confluence_page_ids_from_jira_tasks(["GBO-123", "GBO-456"])

        assert len(result) == 0

    def test_extract_confluence_page_ids_from_jira_tasks_empty_list(self):
        """Тест обработки пустого списка задач"""
        result = extract_confluence_page_ids_from_jira_tasks([])
        assert result == []

    @patch('app.jira_loader.get_jira_task_description_via_session')
    def test_extract_confluence_page_ids_from_jira_tasks_mixed_results(self, mock_get_description):
        """Тест смешанных результатов: одна задача с описанием, одна без"""
        mock_get_description.side_effect = [
            '<div class="user-content-block"><a href="https://confluence.gboteam.ru/pages/viewpage.action?pageId=111111111">Link</a></div>',
            None  # Вторая задача без описания
        ]

        result = extract_confluence_page_ids_from_jira_tasks(["GBO-123", "GBO-456"])

        assert len(result) == 1
        assert "111111111" in result