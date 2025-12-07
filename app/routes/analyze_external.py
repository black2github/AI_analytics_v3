# app/routes/analyze_external.py

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator, ValidationError
from typing import List, Optional
import logging
import anyio

from app.services.analysis_service import analyze_pages
from app.page_cache import process_and_cache_external_pages

logger = logging.getLogger(__name__)
router = APIRouter()


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


class AnalyzeExternalPagesRequest(BaseModel):
    """Запрос на анализ внешних страниц"""
    pages: List[ExternalPageData] = Field(..., description="Список страниц для анализа")
    service_code: Optional[str] = Field(None, description="Код сервиса (опционально)")
    prompt_template: Optional[str] = Field(None, description="Кастомный промпт (опционально)")
    check_templates: bool = Field(False, description="Проверять соответствие шаблонам")

    @field_validator('pages')
    @classmethod
    def validate_pages_not_empty(cls, v: List[ExternalPageData]) -> List[ExternalPageData]:
        """Проверяет, что список страниц не пустой"""
        if not v:
            raise ValueError("Список pages не может быть пустым")
        return v


# ============================================================================
# ЭНДПОИНТ
# ============================================================================

@router.post("/analyze_external_pages", tags=["Анализ внешних страниц требований"])
async def analyze_external_pages(request: Request):
    """
    ✨ ОПТИМИЗИРОВАНО: Анализирует требования из внешних источников без обращения к Confluence.

    Эндпоинт принимает страницы, полученные внешним процессом из Confluence,
    обрабатывает их, помещает в кеш и запускает анализ через analyze_pages().

    Этапы обработки:
    1. Валидация входных данных (page_id, title, content)
    2. Обработка HTML каждой страницы через page_cache:
       - Извлечение всех фрагментов (full_content)
       - Конвертация в Markdown (full_markdown)
       - Извлечение одобренных фрагментов (approved_content)
       - Определение типа требования (requirement_type)
    3. Помещение обработанных страниц в кеш
    4. Запуск анализа через analyze_pages() с использованием закешированных данных

    Args:
        pages: Список страниц с полями page_id, title, content (HTML)
        service_code: Код сервиса (опционально)
        prompt_template: Кастомный промпт для анализа (опционально)
        check_templates: Проверять соответствие шаблонам (по умолчанию False)

    Returns:
        Результат анализа в том же формате, что и /analyze_pages,
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
            "service_code": "SBP"
        }
        ```
    """
    try:
        # Парсим и валидируем входные данные
        body = await request.json()
        payload = AnalyzeExternalPagesRequest(**body)

    except ValidationError as e:
        # Pydantic валидация не прошла - возвращаем ошибку с HTTP 200
        error_msg = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
        logger.error("[analyze_external_pages] Validation error: %s", error_msg)
        return {"error": f"Validation error: {error_msg}"}

    except Exception as e:
        # Ошибка парсинга JSON
        logger.error("[analyze_external_pages] JSON parsing error: %s", str(e))
        return {"error": f"Invalid JSON: {str(e)}"}

    logger.info("[analyze_external_pages] <- Received %d pages, service_code=%s",
                len(payload.pages), payload.service_code)

    try:
        # ====================================================================
        # ЭТАП 1: Обработка и кеширование страниц (в thread pool)
        # ====================================================================
        logger.info("[analyze_external_pages] Step 1: Processing and caching %d pages",
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
        logger.info("[analyze_external_pages] Caching completed: cached=%d/%d, failed=%d",
                    cache_result['cached'], cache_result['total'], cache_result['failed'])

        if cache_result['failed'] > 0:
            logger.warning("[analyze_external_pages] Failed pages: %s",
                           cache_result['failed_pages'])

        # Если не удалось закешировать ни одной страницы - возвращаем ошибку
        if cache_result['cached'] == 0:
            error_details = {
                'error': 'Failed to cache any pages',
                'total_pages': cache_result['total'],
                'failed_pages': cache_result['failed_pages']
            }
            logger.error("[analyze_external_pages] No pages cached: %s", error_details)
            return error_details

        # ====================================================================
        # ЭТАП 2: Запуск анализа через analyze_pages() (в thread pool)
        # ====================================================================
        logger.info("[analyze_external_pages] Step 2: Running analysis for %d cached pages",
                    cache_result['cached'])

        # Собираем page_id только успешно закешированных страниц
        page_ids = [page.page_id for page in payload.pages]

        # Запускаем анализ через существующую функцию
        analysis_result = await anyio.to_thread.run_sync(
            analyze_pages,
            page_ids,
            payload.prompt_template,
            payload.service_code,
            payload.check_templates
        )

        # ====================================================================
        # ЭТАП 3: Формирование ответа
        # ====================================================================
        logger.info("[analyze_external_pages] -> Analysis completed for %d pages",
                    len(analysis_result) if isinstance(analysis_result, list) else 1)

        response = {
            'results': analysis_result,
            'cache_info': {
                'total_pages': cache_result['total'],
                'cached_pages': cache_result['cached'],
                'failed_pages_count': cache_result['failed'],
            }
        }

        # Добавляем детали по неудачным страницам если они есть
        if cache_result['failed'] > 0:
            response['cache_info']['failed_pages_details'] = cache_result['failed_pages']

        return response

    except Exception as e:
        # Неожиданные ошибки
        logger.exception("[analyze_external_pages] Unexpected error")
        return {"error": str(e)}