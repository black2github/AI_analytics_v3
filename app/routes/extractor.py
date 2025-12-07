# app/routes/extractor.py - С добавленным эндпоинтом /markdown

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
import asyncio
import anyio
from anyio import to_thread
import base64
from atlassian import Confluence

from app.filter_all_fragments import filter_all_fragments
from app.filter_approved_fragments import filter_approved_fragments
from app.page_cache import get_page_data_cached
from app.config import CONFLUENCE_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# МОДЕЛИ ДАННЫХ
# ============================================================================

class ExtractContentRequest(BaseModel):
    """Запрос на извлечение контента страниц"""
    page_ids: List[str]


class PageContent(BaseModel):
    """Контент одной страницы"""
    page_id: str
    title: Optional[str] = None
    content: Optional[str] = None
    error: Optional[str] = None


class ExtractContentResponse(BaseModel):
    """Ответ с контентом страниц"""
    success: bool
    total_pages: int
    processed_pages: int
    pages: List[PageContent]


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С АУТЕНТИФИКАЦИЕЙ
# ============================================================================

def parse_basic_auth(authorization: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Парсит HTTP Basic Authentication заголовок.

    Args:
        authorization: Значение заголовка Authorization (например: "Basic dXNlcjpwYXNz")

    Returns:
        Tuple (username, password) или (None, None) если заголовок невалиден
    """
    if not authorization:
        return None, None

    try:
        # Проверяем, что это Basic Auth
        if not authorization.startswith('Basic '):
            logger.warning("[parse_basic_auth] Authorization header doesn't start with 'Basic '")
            return None, None

        # Извлекаем base64 часть
        encoded_credentials = authorization[6:]  # Убираем "Basic "

        # Декодируем base64
        decoded_bytes = base64.b64decode(encoded_credentials)
        decoded_str = decoded_bytes.decode('utf-8')

        # Разделяем на username и password
        if ':' not in decoded_str:
            logger.warning("[parse_basic_auth] Invalid credentials format (no colon)")
            return None, None

        username, password = decoded_str.split(':', 1)

        logger.debug("[parse_basic_auth] Successfully parsed credentials for user=%s", username)
        return username, password

    except Exception as e:
        logger.error("[parse_basic_auth] Error parsing authorization header: %s", str(e))
        return None, None


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С CONFLUENCE
# ============================================================================

def _get_page_raw_html(confluence_client: Confluence, page_id: str) -> Optional[tuple]:
    """
    Получает raw HTML и title страницы через Confluence API.
    Использует ТОТ ЖЕ подход, что и в page_cache.
    Возвращает tuple (title, html) или None в случае ошибки.
    """
    try:
        logger.debug("[_get_page_raw_html] Fetching page_id=%s", page_id)

        # ИСПОЛЬЗУЕМ ТОТ ЖЕ метод, что работает в основной системе
        page_data = confluence_client.get_page_by_id(
            page_id=page_id,
            expand='body.storage,version'
        )

        if not page_data:
            logger.warning("[_get_page_raw_html] Page not found: %s", page_id)
            return None

        title = page_data.get('title', '')
        body = page_data.get('body', {})
        storage = body.get('storage', {})
        html = storage.get('value', '')

        if not html:
            logger.warning("[_get_page_raw_html] Empty content for page_id=%s", page_id)
            return None

        logger.debug("[_get_page_raw_html] Successfully fetched page_id=%s, title='%s', html_length=%d",
                     page_id, title, len(html))
        return (title, html)

    except Exception as e:
        logger.error("[_get_page_raw_html] Error fetching page_id=%s: %s", page_id, str(e))
        return None


def _process_page_with_custom_credentials(
        username: str,
        password: str,
        page_id: str
) -> PageContent:
    """
    Синхронная функция для извлечения контента страницы с кастомными учетными данными.
    Создает отдельное соединение с Confluence для каждого запроса.
    """
    try:
        logger.debug("[_process_page_with_custom_credentials] Processing page_id=%s with user=%s",
                     page_id, username)

        # Создаем отдельное соединение с Confluence с переданными credentials
        confluence_client = Confluence(
            url=CONFLUENCE_BASE_URL,
            username=username,
            password=password
        )

        # Получаем raw HTML напрямую из Confluence (без кеширования)
        page_data = _get_page_raw_html(confluence_client, page_id)

        if not page_data:
            logger.warning("[_process_page_with_custom_credentials] No data found for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=None,
                content=None,
                error="Page data not found or access denied"
            )

        title, html_content = page_data

        if not html_content:
            logger.warning("[_process_page_with_custom_credentials] No content for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=title,
                content=None,
                error="Page content not found or empty"
            )

        # Извлекаем все фрагменты через filter_all_fragments
        extracted_content = filter_all_fragments(html_content)

        if not extracted_content or not extracted_content.strip():
            logger.warning("[_process_page_with_custom_credentials] No extractable content for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=title,
                content="",
                error="No extractable content found"
            )

        logger.debug("[_process_page_with_custom_credentials] Successfully processed page_id=%s, content_length=%d",
                     page_id, len(extracted_content))

        return PageContent(
            page_id=page_id,
            title=title,
            content=extracted_content.strip()
        )

    except Exception as e:
        logger.error("[_process_page_with_custom_credentials] Error processing page_id=%s: %s",
                     page_id, str(e))
        return PageContent(
            page_id=page_id,
            title=None,
            content=None,
            error=f"Processing error: {str(e)}"
        )


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СТАНДАРТНОЙ ОБРАБОТКИ (с кешированием)
# ============================================================================

def _process_page_all_content(page_id: str) -> PageContent:
    """
    Синхронная функция для извлечения ВСЕГО контента одной страницы.
    Использует стандартные credentials и кеширование.
    """
    try:
        logger.debug("[_process_page_all_content] Processing page_id=%s", page_id)

        page_data = get_page_data_cached(page_id)

        if not page_data:
            logger.warning("[_process_page_all_content] No data found for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=None,
                content=None,
                error="Page data not found"
            )

        title = page_data.get('title')
        html_content = page_data.get('raw_html')

        if not html_content:
            logger.warning("[_process_page_all_content] No content found for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=title,
                content=None,
                error="Page content not found or empty"
            )

        extracted_content = filter_all_fragments(html_content)

        if not extracted_content or not extracted_content.strip():
            logger.warning("[_process_page_all_content] No extractable content for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=title,
                content="",
                error="No extractable content found"
            )

        logger.debug("[_process_page_all_content] Successfully processed page_id=%s, content_length=%d",
                     page_id, len(extracted_content))

        return PageContent(
            page_id=page_id,
            title=title,
            content=extracted_content.strip()
        )

    except Exception as e:
        logger.error("[_process_page_all_content] Error processing page_id=%s: %s", page_id, str(e))
        return PageContent(
            page_id=page_id,
            title=None,
            content=None,
            error=f"Processing error: {str(e)}"
        )


def _process_page_approved_content(page_id: str) -> PageContent:
    """
    Синхронная функция для извлечения ПОДТВЕРЖДЕННОГО контента одной страницы.
    Использует стандартные credentials и кеширование.
    """
    try:
        logger.debug("[_process_page_approved_content] Processing page_id=%s", page_id)

        page_data = get_page_data_cached(page_id)

        if not page_data:
            logger.warning("[_process_page_approved_content] No data found for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=None,
                content=None,
                error="Page data not found"
            )

        title = page_data.get('title')
        html_content = page_data.get('raw_html')

        if not html_content:
            logger.warning("[_process_page_approved_content] No content found for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=title,
                content=None,
                error="Page content not found or empty"
            )

        extracted_content = filter_approved_fragments(html_content)

        if not extracted_content or not extracted_content.strip():
            logger.warning("[_process_page_approved_content] No approved content for page_id=%s", page_id)
            return PageContent(
                page_id=page_id,
                title=title,
                content="",
                error="No approved content found"
            )

        logger.debug("[_process_page_approved_content] Successfully processed page_id=%s, content_length=%d",
                     page_id, len(extracted_content))

        return PageContent(
            page_id=page_id,
            title=title,
            content=extracted_content.strip()
        )

    except Exception as e:
        logger.error("[_process_page_approved_content] Error processing page_id=%s: %s", page_id, str(e))
        return PageContent(
            page_id=page_id,
            title=None,
            content=None,
            error=f"Processing error: {str(e)}"
        )


# ============================================================================
# ЭНДПОИНТЫ
# ============================================================================

@router.post("/extract_all_content",
             response_model=ExtractContentResponse,
             tags=["Извлечение контента"],
             summary="Получение полного текста требований со страниц Confluence")
async def extract_all_content(request: ExtractContentRequest):
    """
    ОПТИМИЗИРОВАНО: Извлекает полный текст требований с ПАРАЛЛЕЛЬНОЙ обработкой страниц.

    Использует стандартные учетные данные из config.py и кеширование страниц.
    Возвращает все фрагменты текста, включая цветные (неподтвержденные) требования.

    Args:
        page_ids: Список идентификаторов страниц Confluence

    Returns:
        Список страниц с полным извлеченным текстом требований
    """
    logger.info("[extract_all_content] <- Processing %d page(s) in parallel", len(request.page_ids))

    if not request.page_ids:
        return ExtractContentResponse(
            success=False,
            total_pages=0,
            processed_pages=0,
            pages=[],
        )

    async def process_page_async(page_id: str) -> PageContent:
        """Обертка для запуска синхронной функции в thread pool"""
        return await anyio.to_thread.run_sync(_process_page_all_content, page_id)

    pages_content = await asyncio.gather(
        *[process_page_async(page_id) for page_id in request.page_ids]
    )

    processed_count = sum(1 for page in pages_content if page.content is not None)

    logger.info("[extract_all_content] -> Processed %d/%d pages successfully",
                processed_count, len(request.page_ids))

    return ExtractContentResponse(
        success=processed_count > 0,
        total_pages=len(request.page_ids),
        processed_pages=processed_count,
        pages=pages_content
    )


@router.post("/extract_approved_content",
             response_model=ExtractContentResponse,
             tags=["Извлечение контента"],
             summary="Получение подтвержденных требований со страниц Confluence")
async def extract_approved_content(request: ExtractContentRequest):
    """
    ОПТИМИЗИРОВАНО: Извлекает подтвержденный контент с ПАРАЛЛЕЛЬНОЙ обработкой страниц.

    Использует стандартные учетные данные из config.py и кеширование страниц.
    Возвращает только фрагменты текста без цветового оформления (подтвержденные требования).

    Args:
        page_ids: Список идентификаторов страниц Confluence

    Returns:
        Список страниц с извлеченным текстом подтвержденных требований
    """
    logger.info("[extract_approved_content] <- Processing %d page(s) in parallel", len(request.page_ids))

    if not request.page_ids:
        return ExtractContentResponse(
            success=False,
            total_pages=0,
            processed_pages=0,
            pages=[],
        )

    async def process_page_async(page_id: str) -> PageContent:
        """Обертка для запуска синхронной функции в thread pool"""
        return await anyio.to_thread.run_sync(_process_page_approved_content, page_id)

    pages_content = await asyncio.gather(
        *[process_page_async(page_id) for page_id in request.page_ids]
    )

    processed_count = sum(1 for page in pages_content if page.content is not None)

    logger.info("[extract_approved_content] -> Processed %d/%d pages successfully",
                processed_count, len(request.page_ids))

    return ExtractContentResponse(
        success=processed_count > 0,
        total_pages=len(request.page_ids),
        processed_pages=processed_count,
        pages=pages_content
    )


@router.post("/markdown",
             response_model=ExtractContentResponse,
             tags=["Извлечение контента"],
             summary="Получение контента с кастомными учетными данными из заголовка")
async def extract_markdown_with_credentials(
        request: ExtractContentRequest,
        authorization: Optional[str] = Header(None)
):
    """
    НОВЫЙ ЭНДПОИНТ: Извлекает контент страниц с использованием учетных данных из HTTP заголовка.

    В отличие от /extract_all_content:
    - Использует HTTP Basic Authentication из заголовка Authorization
    - НЕ использует кеширование (каждый запрос идет напрямую в Confluence)
    - Создает отдельное соединение для каждого запроса
    - Работает параллельно для всех страниц
    - Валидация credentials происходит при первой попытке получить страницу

    Полезно для:
    - Работы с разными учетными записями
    - Доступа к страницам с ограниченными правами
    - Тестирования прав доступа

    Headers:
        Authorization: Basic <base64(username:password)>

    Пример:
        Authorization: Basic YXNlbjpteXBhc3N3b3Jk
        (где "YXNlbjpteXBhc3N3b3Jk" это base64 от "asen:mypassword")

    Args:
        page_ids: Список идентификаторов страниц Confluence
        authorization: HTTP заголовок Authorization с Basic Auth

    Returns:
        Список страниц с полным извлеченным текстом требований

    Raises:
        HTTPException 401: Если заголовок Authorization отсутствует или невалиден
        HTTPException 401: Если учетные данные некорректны или доступ запрещен
    """
    # Парсим credentials из заголовка
    username, password = parse_basic_auth(authorization)

    if not username or not password:
        logger.warning("[extract_markdown_with_credentials] Missing or invalid Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Authorization header with Basic authentication is required. Format: 'Basic <base64(username:password)>'",
            headers={"WWW-Authenticate": "Basic"}
        )

    logger.info("[extract_markdown_with_credentials] <- Processing %d page(s) for user=%s",
                len(request.page_ids), username)

    if not request.page_ids:
        return ExtractContentResponse(
            success=False,
            total_pages=0,
            processed_pages=0,
            pages=[],
        )

    # Параллельная обработка всех страниц с кастомными credentials
    async def process_page_async(page_id: str) -> PageContent:
        """Обертка для запуска синхронной функции в thread pool"""
        return await anyio.to_thread.run_sync(
            _process_page_with_custom_credentials,
            username,
            password,
            page_id
        )

    pages_content = await asyncio.gather(
        *[process_page_async(page_id) for page_id in request.page_ids],
        return_exceptions=True  # Продолжаем обработку даже если одна страница упала
    )

    # Обрабатываем возможные исключения
    processed_pages = []
    for i, result in enumerate(pages_content):
        if isinstance(result, Exception):
            logger.error("[extract_markdown_with_credentials] Exception for page_id=%s: %s",
                         request.page_ids[i], str(result))
            processed_pages.append(PageContent(
                page_id=request.page_ids[i],
                title=None,
                content=None,
                error=f"Exception: {str(result)}"
            ))
        else:
            processed_pages.append(result)

    processed_count = sum(1 for page in processed_pages if page.content is not None)

    # Если ни одна страница не обработана и везде ошибки авторизации - возвращаем 401
    if processed_count == 0 and any(
            page.error and ('access denied' in page.error.lower() or 'unauthorized' in page.error.lower())
            for page in processed_pages
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials or access denied to all pages",
            headers={"WWW-Authenticate": "Basic"}
        )

    logger.info("[extract_markdown_with_credentials] -> Processed %d/%d pages successfully for user=%s",
                processed_count, len(request.page_ids), username)

    return ExtractContentResponse(
        success=processed_count > 0,
        total_pages=len(request.page_ids),
        processed_pages=processed_count,
        pages=processed_pages
    )


@router.get("/extract_health", tags=["Извлечение контента"])
async def extract_health_check():
    """Проверка работоспособности модуля извлечения контента"""
    return {
        "status": "ok",
        "module": "content_extractor",
        "endpoints": [
            "POST /extract_all_content",
            "POST /extract_approved_content",
            "POST /markdown",
            "GET /extract_health"
        ],
        "features": [
            "Parallel page processing with anyio",
            "Non-blocking I/O operations",
            "Thread pool execution for heavy tasks",
            "Custom credentials support (/markdown endpoint)",
            "Caching for standard endpoints",
            "Direct API access for custom credentials"
        ],
        "description": "Content extraction from Confluence pages using filter_all_fragments and filter_approved_fragments"
    }