# app/routes/load_external.py

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator, ValidationError
from typing import List, Optional
import logging
import anyio

from app.services.document_service import DocumentService
from app.page_cache import process_and_cache_external_pages

logger = logging.getLogger(__name__)
router = APIRouter()

# Инициализируем сервис
document_service = DocumentService()


# ============================================================================
# МОДЕЛИ ДАННЫХ
# ============================================================================

class ExternalPageData(BaseModel):
    """Модель данных для одной внешней страницы"""
    page_id: str = Field(..., description="Идентификатор страницы Confluence")
    title: str = Field(..., description="Заголовок страницы")
    content: str = Field(..., description="HTML содержимое страницы")

    @field_validator('page_id')
    @classmethod
    def validate_page_id(cls, v: str) -> str:
        """Проверяет, что page_id - это строка с числом"""
        if not v or not v.strip():
            raise ValueError("page_id не может быть пустым")

        # Проверяем, что это строка с числом
        if not v.strip().isdigit():
            raise ValueError(f"page_id должен быть числовой строкой, получено: {v}")

        return v.strip()

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Проверяет, что title не пустой"""
        if not v or not v.strip():
            raise ValueError("title не может быть пустым")
        return v.strip()

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Проверяет, что content не пустой"""
        if not v or not v.strip():
            raise ValueError("content не может быть пустым")
        return v


class LoadExternalPagesRequest(BaseModel):
    """Запрос на загрузку внешних страниц в векторное хранилище"""
    pages: List[ExternalPageData] = Field(..., description="Список страниц для загрузки")
    service_code: str = Field(..., description="Код сервиса")
    source: Optional[str] = Field("DBOCORPESPLN", description="Источник данных")

    @field_validator('pages')
    @classmethod
    def validate_pages_not_empty(cls, v: List[ExternalPageData]) -> List[ExternalPageData]:
        """Проверяет, что список страниц не пустой"""
        if not v:
            raise ValueError("Список pages не может быть пустым")
        return v

    @field_validator('service_code')
    @classmethod
    def validate_service_code(cls, v: str) -> str:
        """Проверяет, что service_code не пустой"""
        if not v or not v.strip():
            raise ValueError("service_code не может быть пустым")
        return v.strip()


# ============================================================================
# ЭНДПОИНТ
# ============================================================================

@router.post("/load_external_pages", tags=["Загрузка внешних страниц требований в векторное хранилище"])
async def load_external_pages(request: Request):
    """
    ✨ ОПТИМИЗИРОВАНО: Загружает внешние страницы требований в векторное хранилище без обращения к Confluence.

    Эндпоинт принимает страницы, полученные внешним процессом из Confluence,
    обрабатывает их, помещает в кеш и загружает в векторное хранилище.

    Этапы обработки:
    1. Валидация входных данных (page_id, title, content, service_code)
    2. Обработка HTML каждой страницы через page_cache:
       - Извлечение всех фрагментов (full_content)
       - Конвертация в Markdown (full_markdown)
       - Извлечение одобренных фрагментов (approved_content)
       - Определение типа требования (requirement_type)
    3. Помещение обработанных страниц в кеш
    4. Загрузка закешированных страниц в векторное хранилище через
       document_service.load_approved_pages()

    Args:
        pages: Список страниц с полями page_id, title, content (HTML)
        service_code: Код сервиса (обязательный)
        source: Источник данных (опционально, по умолчанию "DBOCORPESPLN")

    Returns:
        Результат загрузки в том же формате, что и /load_pages,
        плюс информация о кешировании страниц

    Example:
        ```json
        {
            "pages": [
                {
                    "page_id": "274628758",
                    "title": "[КК] Nested table test",
                    "content": "<html>...</html>"
                }
            ],
            "service_code": "SBP",
            "source": "DBOCORPESPLN"
        }
        ```
    """
    try:
        # Парсим и валидируем входные данные
        body = await request.json()
        payload = LoadExternalPagesRequest(**body)

    except ValidationError as e:
        # Pydantic валидация не прошла - возвращаем ошибку с HTTP 200
        error_msg = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
        logger.error("[load_external_pages] Validation error: %s", error_msg)
        return {"error": f"Validation error: {error_msg}"}

    except Exception as e:
        # Ошибка парсинга JSON
        logger.error("[load_external_pages] JSON parsing error: %s", str(e))
        return {"error": f"Invalid JSON: {str(e)}"}

    logger.info("[load_external_pages] <- Received %d pages, service_code=%s, source=%s",
                len(payload.pages), payload.service_code, payload.source)

    try:
        # ====================================================================
        # ЭТАП 1: Обработка и кеширование страниц (в thread pool)
        # ====================================================================
        logger.info("[load_external_pages] Step 1: Processing and caching %d pages",
                    len(payload.pages))

        # Преобразуем Pydantic модели в словари для page_cache
        pages_data = [
            {
                'page_id': page.page_id,
                'title': page.title,
                'content': page.content
            }
            for page in payload.pages
        ]

        # Обработка через page_cache (вынесенная логика)
        cache_result = await anyio.to_thread.run_sync(
            process_and_cache_external_pages,
            pages_data
        )

        # Логируем статистику кеширования
        logger.info("[load_external_pages] Caching completed: cached=%d/%d, failed=%d",
                    cache_result['cached'], cache_result['total'], cache_result['failed'])

        if cache_result['failed'] > 0:
            logger.warning("[load_external_pages] Failed pages: %s",
                           cache_result['failed_pages'])

        # Если не удалось закешировать ни одной страницы - возвращаем ошибку
        if cache_result['cached'] == 0:
            error_details = {
                'error': 'Failed to cache any pages',
                'total_pages': cache_result['total'],
                'failed_pages': cache_result['failed_pages']
            }
            logger.error("[load_external_pages] No pages cached: %s", error_details)
            return error_details

        # ====================================================================
        # ЭТАП 2: Загрузка закешированных страниц в векторное хранилище (в thread pool)
        # ====================================================================
        logger.info("[load_external_pages] Step 2: Loading %d cached pages to vector store",
                    cache_result['cached'])

        # Собираем page_id только успешно закешированных страниц
        page_ids = [page.page_id for page in payload.pages
                    if page.page_id not in [fp['page_id'] for fp in cache_result['failed_pages']]]

        # Загружаем через document_service (аналогично /load_pages)
        load_result = await anyio.to_thread.run_sync(
            document_service.load_approved_pages,
            page_ids,
            payload.service_code,
            payload.source
        )

        # ====================================================================
        # ЭТАП 3: Формирование ответа
        # ====================================================================
        platform_status = "platform" if load_result["is_platform"] else "regular"

        logger.info("[load_external_pages] -> Created %d documents for %s service '%s'",
                    load_result['documents_created'], platform_status, load_result['service_code'])

        # Формируем ответ в формате /load_pages с дополнительной информацией о кешировании
        response = {
            "message": f"{load_result['documents_created']} documents indexed for {platform_status} service '{load_result['service_code']}' (approved content only).",
            "total_pages": load_result["total_pages"],
            "pages_with_approved_content": load_result["pages_with_approved_content"],
            "documents_created": load_result["documents_created"],
            "is_platform": load_result["is_platform"],
            "storage": load_result["storage"],
            "cache_info": {
                "total_pages": cache_result['total'],
                "cached_pages": cache_result['cached'],
                "failed_pages_count": cache_result['failed']
            }
        }

        # Добавляем детали по неудачным страницам если они есть
        if cache_result['failed'] > 0:
            response['cache_info']['failed_pages_details'] = cache_result['failed_pages']

        return response

    except ValueError as e:
        logger.error("[load_external_pages] Validation error: %s", str(e))
        return {"error": str(e)}

    except Exception as e:
        # Неожиданные ошибки
        logger.exception("[load_external_pages] Unexpected error")
        return {"error": str(e)}