# app/confluence_loader.py

import logging
import time
from typing import List, Dict, Optional
from atlassian import Confluence
from requests import ReadTimeout

from app.config import CONFLUENCE_BASE_URL, CONFLUENCE_USER, CONFLUENCE_PASSWORD
from app.filter_approved_fragments import filter_approved_fragments

if CONFLUENCE_BASE_URL is None:
    raise ValueError("Переменная окружения CONFLUENCE_BASE_URL не задана")

confluence = Confluence(
    url=CONFLUENCE_BASE_URL,
    username=CONFLUENCE_USER,
    password=CONFLUENCE_PASSWORD,
    # если выдвется ошибка сертификата или не проходит коннект из-за проверки - скидывай в False
    verify_ssl=True
)

logger = logging.getLogger(__name__)

try:
    from markdownify import markdownify as markdownify_fn
except ImportError:
    logging.error("[extract_approved_fragments] markdownify package not installed. Install it using 'pip install markdownify'")
    raise ImportError("markdownify package is required")

def extract_approved_fragments(html: str) -> str:
    """
    Извлекает только одобренные (чёрные) фрагменты текста, включая ссылки и таблицы.
    """
    logger.debug("[extract_approved_fragments] <- html={%s}", html)
    return filter_approved_fragments(html)


from tenacity import retry, stop_after_attempt, wait_exponential
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_page_content_by_id(page_id: str, clean_html: bool = True) -> Optional[str]:
    """
    Использует кеширование.
    Получает содержимое страницы Confluence по её ID.
    """
    logger.info("[get_page_content_by_id] <- page_id=%s, clean_html=%s", page_id, clean_html)

    # ДОБАВЛЯЕМ ИМПОРТ кешированной функции
    from app.page_cache import get_page_data_cached

    page_data = get_page_data_cached(page_id)
    if not page_data:
        logger.warning("[get_page_content_by_id] -> None.")
        return None

    if clean_html:
        content = page_data['full_content']
    else:
        content = page_data['raw_html']

    logger.info("[get_page_content_by_id] -> Content length %d characters", len(content))
    return content


def get_page_title_by_id(page_id: str) -> Optional[str]:
    """
    ОПТИМИЗИРОВАНО: Использует кеширование.
    Получает заголовок страницы по ID.
    """
    logger.debug("[get_page_title_by_id] <- page_id=%s", page_id)

    # ДОБАВЛЯЕМ ИМПОРТ кешированной функции
    from app.page_cache import get_page_data_cached

    page_data = get_page_data_cached(page_id)
    if not page_data:
        return None

    logger.debug("[get_page_title_by_id] -> Result: %s", page_data['title'])
    return page_data['title']


def load_pages_by_ids(page_ids: List[str]) -> List[Dict[str, str]]:
    """
    Загрузка страниц из Confluence по идентификаторам и разбиение на:
    идентификатор, заголовок, содержимое, подтвержденное содержимое и тип требования.
    ОПТИМИЗИРОВАНО: Использует кеширование для быстрой загрузки страниц.
    Args:
        page_ids: список идентификаторов страниц для загрузки.
    Returns:
        страницы (словари) с id, title, content, approved_content, requirement_type.
    """
    logger.info("[load_pages_by_ids] <- page_ids={%s}", page_ids)

    from app.page_cache import get_page_data_cached

    pages = []
    for page_id in page_ids:
        logger.debug("[load_pages_by_ids] Processing page_id=%s", page_id)

        page_data = get_page_data_cached(page_id)

        if not page_data:
            logger.warning("[load_pages_by_ids] Пропущена страница {%s} из-за ошибок загрузки.", page_id)
            continue

        # ИСПРАВЛЕНИЕ: Добавляем детальную проверку каждого поля
        title = page_data.get('title')
        full_markdown = page_data.get('full_markdown')
        approved_content = page_data.get('approved_content')
        requirement_type = page_data.get('requirement_type')

        logger.debug("[load_pages_by_ids] page_id=%s -> title='%s', has_markdown=%s, has_approved=%s, type='%s'",
                     page_id, title, bool(full_markdown), bool(approved_content), requirement_type)

        # Проверяем наличие обязательных данных
        if not title:
            logger.warning("[load_pages_by_ids] Пропущена страница {%s}: отсутствует title.", page_id)
            continue

        if not full_markdown:
            logger.warning("[load_pages_by_ids] Пропущена страница {%s}: отсутствует full_markdown.", page_id)
            continue

        if not approved_content:
            logger.warning("[load_pages_by_ids] Пропущена страница {%s}: отсутствует approved_content.", page_id)
            continue

        pages.append({
            "id": page_id,
            "title": title,
            "content": full_markdown,
            "approved_content": approved_content,
            "requirement_type": requirement_type
        })

        logger.debug("[load_pages_by_ids] Успешно добавлена страница: id=%s, title='%s'", page_id, title)

    logger.info("[load_pages_by_ids] -> Успешно загружено страниц: %s из %s", len(pages), len(page_ids))
    return pages


def load_template_markdown(page_id: str) -> Optional[str]:
    html = get_page_content_by_id(page_id, clean_html=False)
    if not html:
        return None
    return extract_approved_fragments(html)


def get_child_page_ids(page_id: str) -> List[str]:
    """Возвращает список идентификаторов всех дочерних страниц."""
    child_page_ids = []
    visited_pages = set()
    max_retries = 3

    def fetch_children(current_page_id: str, retry_count: int = 0):
        """Рекурсивно собирает идентификаторы дочерних страниц."""
        if current_page_id in visited_pages:
            logger.warning("[fetch_children] Circular reference detected for page_id=%s", current_page_id)
            return

        visited_pages.add(current_page_id)
        logger.debug("[fetch_children] <- current_page_id={%s}", current_page_id)

        try:
            children = confluence.get_child_pages(current_page_id)
            for child in children:
                child_id = child["id"]
                child_page_ids.append(child_id)
                logger.debug("[get_child_page_ids] Found child page: %s for parent: %s", child_id, current_page_id)
                fetch_children(child_id)

        except ReadTimeout as e:
            if retry_count < max_retries:
                logger.warning(f"Timeout for page {current_page_id}, retry {retry_count + 1}/{max_retries}")
                time.sleep(2 ** retry_count)  # Exponential backoff
                fetch_children(current_page_id, retry_count + 1)
            else:
                logger.error(f"Failed to fetch children for page {current_page_id} after {max_retries} retries: {e}")
                # Продолжаем работу, но пропускаем эту страницу

        except Exception as e:
            logger.error(f"Failed to fetch children for page {current_page_id}: {str(e)}")
            # Продолжаем работу вместо полного падения

    try:
        fetch_children(page_id)
        return child_page_ids
    except Exception as e:
        logging.exception("Error fetching child pages for page_id=%s", page_id)
        return child_page_ids  # Возвращаем то, что успели собрать