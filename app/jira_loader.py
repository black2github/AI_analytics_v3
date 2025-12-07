# app/jira_loader.py
"""
Модуль для работы с Jira API и извлечения идентификаторов страниц Confluence из задач Jira.
"""
import logging
import re
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from app.config import (
    JIRA_BASE_URL,
    JIRA_USER,
    JIRA_API_TOKEN,
    JIRA_PASSWORD
)

logger = logging.getLogger(__name__)


def _get_jira_auth():
    """
    Возвращает объект аутентификации для Jira Server.
    Приоритет: Password > API Token > None
    """
    if JIRA_PASSWORD and JIRA_USER:
        logger.debug("[_get_jira_auth] Using Basic Auth (username/password) for Jira Server")
        return (JIRA_USER, JIRA_PASSWORD)
    elif JIRA_API_TOKEN and JIRA_USER:
        logger.debug("[_get_jira_auth] Trying API token (may not work on Jira Server)")
        return (JIRA_USER, JIRA_API_TOKEN)
    else:
        logger.warning("[_get_jira_auth] No authentication configured! Set JIRA_USER and JIRA_PASSWORD")
        return None


def authenticate_via_web_session(username: str, password: str) -> Optional[requests.Session]:
    """
    Аутентификация через веб-форму логина Jira Server.
    Использует endpoint dologin.jsp для корректного логина.
    """
    logger.info("[authenticate_via_web_session] Attempting web authentication for user: %s", username)

    session = requests.Session()

    try:
        # 1. Получаем страницу логина для получения скрытых полей
        login_page_url = f"{JIRA_BASE_URL}/login.jsp"
        logger.debug("[authenticate_via_web_session] Getting login page: %s", login_page_url)

        login_page = session.get(login_page_url, timeout=10)
        if login_page.status_code != 200:
            logger.error("[authenticate_via_web_session] Failed to get login page: %d", login_page.status_code)
            return None

        # 2. Парсируем скрытые поля из формы
        soup = BeautifulSoup(login_page.text, 'html.parser')
        login_form = soup.find('form', {'id': 'login-form'})

        # 3. Подготавливаем данные для отправки
        form_data = {
            'os_username': username,
            'os_password': password,
        }

        # Добавляем скрытые поля если они есть
        if login_form:
            for hidden_input in login_form.find_all('input', type='hidden'):
                name = hidden_input.get('name')
                value = hidden_input.get('value', '')
                if name:
                    form_data[name] = value

        # 4. Отправляем на dologin.jsp (рабочий endpoint для Jira Server)
        dologin_url = f"{JIRA_BASE_URL}/dologin.jsp"
        logger.debug("[authenticate_via_web_session] Submitting to: %s", dologin_url)

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': login_page_url
        }

        login_response = session.post(dologin_url, data=form_data, headers=headers, timeout=10, allow_redirects=True)

        # 5. Проверяем успешность логина
        if login_response.status_code == 200:
            # Проверяем, что мы НЕ на странице логина
            if 'login.jsp' not in login_response.url and 'dologin.jsp' not in login_response.url:
                logger.info("[authenticate_via_web_session]  Web authentication successful!")
                return session
            else:
                logger.error("[authenticate_via_web_session] Login failed - redirected to login page")
                return None
        else:
            logger.error("[authenticate_via_web_session] Login failed with status: %d", login_response.status_code)
            return None

    except Exception as e:
        logger.error("[authenticate_via_web_session] Exception during web authentication: %s", str(e))
        return None


def get_jira_task_description_via_session(task_id: str) -> Optional[str]:
    """
    Получает описание задачи Jira через веб-сессию.
    Возвращает HTML содержимое блока с описанием.
    """
    logger.info("[get_jira_task_description_via_session] Getting task description for: %s", task_id)

    if not JIRA_USER or not JIRA_PASSWORD:
        logger.error("[get_jira_task_description_via_session] Username or password not configured")
        return None

    # Аутентификация через веб-форму
    session = authenticate_via_web_session(JIRA_USER, JIRA_PASSWORD)
    if not session:
        logger.error("[get_jira_task_description_via_session] Web authentication failed")
        return None

    try:
        # Получаем страницу задачи
        task_url = f"{JIRA_BASE_URL}/browse/{task_id}"
        logger.debug("[get_jira_task_description_via_session] Getting task page: %s", task_url)

        response = session.get(task_url, timeout=30)

        if response.status_code == 200:
            logger.info("[get_jira_task_description_via_session] Successfully got task page (%d chars)", len(response.text))

            # Парсим HTML для извлечения описания
            soup = BeautifulSoup(response.text, 'html.parser')

            # Ищем блок с описанием: mod-content > user-content-block
            mod_content = soup.find('div', class_='mod-content')
            if mod_content:
                user_content_block = mod_content.find('div', class_='user-content-block')
                if user_content_block:
                    description_html = str(user_content_block)
                    logger.info("[get_jira_task_description_via_session] Found description (%d chars)", len(description_html))
                    return description_html

            # Fallback: ищем все user-content-block на странице
            all_user_blocks = soup.find_all('div', class_='user-content-block')
            if all_user_blocks:
                logger.info("[get_jira_task_description_via_session] Found %d user-content-blocks, using first", len(all_user_blocks))
                return str(all_user_blocks[0])

            logger.warning("[get_jira_task_description_via_session] No description blocks found")
            return None
        else:
            logger.error("[get_jira_task_description_via_session] Failed to get task page: %d %s", response.status_code, response.reason)
            return None

    except Exception as e:
        logger.error("[get_jira_task_description_via_session] Error: %s", str(e))
        return None


def _extract_confluence_page_ids_from_html(html_content: str) -> List[str]:
    """
    Извлекает идентификаторы страниц Confluence из HTML контента.

    Поддерживаемые форматы URL:
    - https://confluence.example.com/pages/viewpage.action?pageId=123456
    - https://confluence.example.com/display/SPACE/Page+Title?pageId=123456
    - https://confluence.example.com/x/ABC123 (встроенные ссылки)
    """
    if not html_content:
        return []

    page_ids = []

    # Парсим HTML с помощью BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Ищем все ссылки
    links = soup.find_all('a', href=True)

    for link in links:
        href = link['href']
        # Извлекаем pageId из различных форматов URL
        page_id = _extract_page_id_from_url(href)
        if page_id:
            page_ids.append(page_id)

    # Также ищем pageId в обычном тексте (на случай если ссылки не в тегах <a>)
    page_id_pattern = r'pageId[=:]\s*(\d+)'
    text_matches = re.findall(page_id_pattern, html_content, re.IGNORECASE)
    page_ids.extend(text_matches)

    # Удаляем дубликаты и возвращаем
    return list(set(page_ids))


def _extract_page_id_from_url(url: str) -> Optional[str]:
    """
    Извлекает pageId из URL Confluence различных форматов.
    """
    if not url:
        return None

    # Паттерн для поиска pageId в параметрах URL
    page_id_match = re.search(r'[?&]pageId=(\d+)', url)
    if page_id_match:
        return page_id_match.group(1)

    # Паттерн для коротких ссылок вида /x/ABC123
    # Пока не реализовано разрешение коротких ссылок
    short_link_match = re.search(r'/x/([A-Za-z0-9]+)', url)
    if short_link_match:
        logger.debug("[_extract_page_id_from_url] Found short link that needs resolution: %s", url)
        # TODO: Implement short link resolution if needed
        return None

    return None


def extract_confluence_page_ids_from_jira_tasks(jira_task_ids: List[str]) -> List[str]:
    """
    Извлекает идентификаторы страниц Confluence из списка задач Jira.

    Args:
        jira_task_ids: Список идентификаторов задач Jira (например, ["GBO-123", "GBO-456"])

    Returns:
        Список уникальных идентификаторов страниц Confluence (например, ["123456", "789012"])
    """
    logger.info("[extract_confluence_page_ids_from_jira_tasks] <- Processing %d Jira tasks via web session", len(jira_task_ids))

    all_page_ids = []

    for task_id in jira_task_ids:
        logger.debug("[extract_confluence_page_ids_from_jira_tasks] Processing task: %s", task_id)

        # Получаем описание задачи через веб-сессию
        description_html = get_jira_task_description_via_session(task_id)

        if description_html:
            # Извлекаем page_ids из HTML
            page_ids = _extract_confluence_page_ids_from_html(description_html)
            if page_ids:
                logger.info("[extract_confluence_page_ids_from_jira_tasks] Task %s: found %d page IDs: %s", task_id, len(page_ids), page_ids)
                all_page_ids.extend(page_ids)
            else:
                logger.info("[extract_confluence_page_ids_from_jira_tasks] Task %s: no page IDs found", task_id)
        else:
            logger.warning("[extract_confluence_page_ids_from_jira_tasks] No task or description found for task: %s", task_id)

    # Удаляем дубликаты
    unique_page_ids = list(set(all_page_ids))

    logger.info("[extract_confluence_page_ids_from_jira_tasks] -> Found %d unique Confluence page IDs", len(unique_page_ids))
    return unique_page_ids