# app/page_cache.py

import logging
import time
import threading
from typing import Dict, Optional, List
from requests.exceptions import ConnectionError, RequestException
from http.client import RemoteDisconnected

import markdownify
from cachetools import TTLCache
from cachetools.keys import hashkey

from app.config import PAGE_CACHE_SIZE, PAGE_CACHE_TTL
from app.confluence_loader import confluence, extract_approved_fragments
from app.filter_all_fragments import filter_all_fragments
from app.services.template_type_analysis import analyze_content_template_type

logger = logging.getLogger(__name__)

# Создаем TTL кэш: максимум PAGE_CACHE_SIZE элементов, время жизни PAGE_CACHE_TTL секунд
page_cache = TTLCache(maxsize=PAGE_CACHE_SIZE, ttl=PAGE_CACHE_TTL)
cache_lock = threading.RLock()

# Константы для retry-логики
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # секунды
MAX_BACKOFF = 8  # секунды


def _reconnect_confluence():
    """
    Переинициализация соединения с Confluence.
    Закрывает текущую сессию и создает новую.
    """
    try:
        if hasattr(confluence, 'session') and confluence.session:
            logger.debug("[_reconnect_confluence] Closing existing session")
            confluence.session.close()

        # Если у confluence есть метод переинициализации, используем его
        if hasattr(confluence, 'reinit_session'):
            confluence.reinit_session()
        elif hasattr(confluence, '_create_session'):
            confluence._create_session()
        else:
            # В противном случае просто создаем новую сессию
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            confluence.session = requests.Session()

            # Настройка retry strategy
            retry_strategy = Retry(
                total=2,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
            )

            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=10,
                pool_maxsize=20,
                pool_block=False
            )

            confluence.session.mount("https://", adapter)
            confluence.session.mount("http://", adapter)

            # Keep-alive headers
            if not hasattr(confluence.session, 'headers'):
                confluence.session.headers = {}
            confluence.session.headers.update({
                'Connection': 'keep-alive'
            })

            logger.info("[_reconnect_confluence] Session reconnected successfully")

    except Exception as e:
        logger.warning("[_reconnect_confluence] Failed to reconnect: %s", str(e))


def get_page_data_cached(page_id: str) -> Optional[Dict]:
    """
    Кешированная функция для получения всех данных страницы за один запрос.

    Включает retry-механизм для обработки обрывов соединения.
    Не кешируем None (неудачные результаты), чтобы избежать
    повторяющихся ошибок "нет данных" из-за закешированных неудач.

    Args:
        page_id: Идентификатор страницы

    Returns:
        Словарь с полными данными страницы или None при ошибке
    """
    logger.debug("[get_page_data_cached] <- page_id=%s", page_id)

    # Создаем ключ для кеша
    cache_key = hashkey(page_id)

    # Проверяем наличие в кеше
    with cache_lock:
        if cache_key in page_cache:
            cached_data = page_cache[cache_key]
            logger.debug("[get_page_data_cached] Cache HIT for page_id=%s", page_id)
            return cached_data

    logger.debug("[get_page_data_cached] Cache MISS for page_id=%s", page_id)

    # Загружаем данные с retry-механизмом
    last_error = None
    backoff = INITIAL_BACKOFF

    for attempt in range(MAX_RETRIES):
        try:
            # Единственный запрос к Confluence API
            page = confluence.get_page_by_id(page_id, expand='body.storage,title')

            if not page:
                logger.warning("[get_page_data_cached] Page not found: %s", page_id)
                return None  # НЕ кешируем None

            title = page.get('title', '')
            raw_html = page.get('body', {}).get('storage', {}).get('value', '')

            if not raw_html:
                logger.warning("[get_page_data_cached] No content found for page_id=%s", page_id)
                return None  # НЕ кешируем None

            # Все виды обработки HTML выполняем один раз
            full_content = filter_all_fragments(raw_html)
            full_markdown = markdownify.markdownify(raw_html, heading_style="ATX")
            approved_content = extract_approved_fragments(raw_html)
            requirement_type = analyze_content_template_type(title, raw_html)

            result = {
                'id': page_id,
                'title': title,
                'raw_html': raw_html,
                'full_content': full_content,
                'full_markdown': full_markdown,
                'approved_content': approved_content,
                'requirement_type': requirement_type
            }

            # ТОЛЬКО успешные результаты кешируем
            with cache_lock:
                page_cache[cache_key] = result

            logger.debug("[get_page_data_cached] -> Processed and CACHED page: title='%s', type='%s'",
                         title, requirement_type)

            # Если были повторные попытки, логируем успех
            if attempt > 0:
                logger.info(
                    "[get_page_data_cached] Successfully retrieved page_id=%s after %d attempt(s)",
                    page_id, attempt + 1
                )

            return result

        except (ConnectionError, RemoteDisconnected, RequestException) as e:
            last_error = e

            if attempt < MAX_RETRIES - 1:
                # Не последняя попытка - retry
                logger.warning(
                    "[get_page_data_cached] Connection error for page_id=%s "
                    "(attempt %d/%d): %s. Retrying in %ds...",
                    page_id, attempt + 1, MAX_RETRIES, str(e), backoff
                )

                # Переинициализируем соединение
                _reconnect_confluence()

                # Ждем с экспоненциальной задержкой
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                # Последняя попытка - логируем ошибку
                logger.error(
                    "[get_page_data_cached] Failed to retrieve page_id=%s after %d attempts: %s",
                    page_id, MAX_RETRIES, str(e)
                )

        except Exception as e:
            # Другие ошибки (не связанные с соединением) не retry
            logger.error(
                "[get_page_data_cached] Error processing page_id=%s: %s",
                page_id, str(e)
            )
            return None  # НЕ кешируем ошибки

    # Если все попытки исчерпаны
    logger.error(
        "[get_page_data_cached] All retry attempts exhausted for page_id=%s. Last error: %s",
        page_id, str(last_error)
    )
    return None  # НЕ кешируем ошибки


def clear_page_cache():
    """Очистка кеша страниц"""
    with cache_lock:
        page_cache.clear()
    logger.info("[clear_page_cache] Page cache cleared")


def get_cache_info():
    """Информация о состоянии кеша"""
    with cache_lock:
        current_size = len(page_cache)

    logger.info("[get_cache_info] Cache stats: size=%d, max_size=%d",
                current_size, PAGE_CACHE_SIZE)
    return {
        'current_size': current_size,
        'max_size': PAGE_CACHE_SIZE,
        'ttl': PAGE_CACHE_TTL
    }

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ для /analyze_external
# ============================================================================

def process_and_cache_external_page(page_id: str, title: str, raw_html: str) -> dict:
    """
    Обрабатывает одну внешнюю страницу и помещает её в кеш.

    Выполняет те же операции, что и get_page_data_cached(), но использует
    уже полученные данные вместо запроса к Confluence API.

    Args:
        page_id: Идентификатор страницы
        title: Заголовок страницы
        raw_html: HTML содержимое страницы

    Returns:
        dict с результатом: {'success': bool, 'page_id': str, 'error': str}
    """
    try:
        logger.debug("[process_and_cache_external_page] Processing page_id=%s, title='%s'",
                     page_id, title)

        # Выполняем все виды обработки HTML (как в get_page_data_cached)
        full_content = filter_all_fragments(raw_html)
        full_markdown = markdownify.markdownify(raw_html, heading_style="ATX")

        # Импортируем здесь, чтобы избежать циклических зависимостей
        from app.filter_approved_fragments import filter_approved_fragments
        approved_content = filter_approved_fragments(raw_html)

        # Определяем тип требования
        requirement_type = analyze_content_template_type(title, raw_html)

        # Формируем результат в том же формате, что и get_page_data_cached
        result = {
            'id': page_id,
            'title': title,
            'raw_html': raw_html,
            'full_content': full_content,
            'full_markdown': full_markdown,
            'approved_content': approved_content,
            'requirement_type': requirement_type
        }

        # Помещаем в кеш (перезаписываем если существует)
        cache_key = hashkey(page_id)
        with cache_lock:
            page_cache[cache_key] = result

        logger.debug("[process_and_cache_external_page] Successfully cached page_id=%s, type='%s'",
                     page_id, requirement_type)

        return {
            'success': True,
            'page_id': page_id,
            'error': None
        }

    except Exception as e:
        error_msg = f"Error processing page: {str(e)}"
        logger.error("[process_and_cache_external_page] Failed to process page_id=%s: %s",
                     page_id, error_msg, exc_info=True)

        return {
            'success': False,
            'page_id': page_id,
            'error': error_msg
        }


def process_and_cache_external_pages(pages: List[Dict[str, str]]) -> dict:
    """
    Обрабатывает список внешних страниц и помещает их в кеш.

    Args:
        pages: Список словарей с ключами 'page_id', 'title', 'content'

    Returns:
        dict со статистикой: {
            'total': int,
            'cached': int,
            'failed': int,
            'failed_pages': list
        }
    """
    logger.info("[process_and_cache_external_pages] <- Processing %d pages", len(pages))

    total = len(pages)
    cached = 0
    failed = 0
    failed_pages = []

    for page_data in pages:
        page_id = page_data.get('page_id')
        title = page_data.get('title')
        content = page_data.get('content')

        if not all([page_id, title, content]):
            error_msg = "Missing required fields (page_id, title, or content)"
            logger.warning("[process_and_cache_external_pages] %s for page_id=%s",
                           error_msg, page_id)
            failed += 1
            failed_pages.append({
                'page_id': page_id or 'unknown',
                'error': error_msg
            })
            continue

        result = process_and_cache_external_page(page_id, title, content)

        if result['success']:
            cached += 1
        else:
            failed += 1
            failed_pages.append({
                'page_id': result['page_id'],
                'error': result['error']
            })

    logger.info("[process_and_cache_external_pages] -> Cached: %d/%d, Failed: %d",
                cached, total, failed)

    return {
        'total': total,
        'cached': cached,
        'failed': failed,
        'failed_pages': failed_pages
    }