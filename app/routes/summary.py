# app/routes/summary.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from app.services.summary_service import ServiceSummaryService

logger = logging.getLogger(__name__)
router = APIRouter()


class GenerateServiceSummaryRequest(BaseModel):
    """Запрос на генерацию саммари сервиса"""
    parent_page_id: str
    use_approved_only: bool = True
    custom_prompt: Optional[str] = None
    max_tokens: int = 50000 # 50000
    max_pages: int = 500


class GenerateServiceSummaryResponse(BaseModel):
    """Ответ с саммари сервиса"""
    success: bool
    summary: Optional[str] = None
    parent_page_id: str
    child_pages_count: int
    processed_pages_count: Optional[int] = None
    use_approved_only: Optional[bool] = None
    requirements_tokens: Optional[int] = None
    processing_stats: Optional[Dict] = None
    page_details: Optional[list] = None
    error: Optional[str] = None


@router.post("/generate_service_summary",
             response_model=GenerateServiceSummaryResponse,
             tags=["Саммари сервиса"],
             summary="Генерация краткого описания назначения сервиса")
async def generate_service_summary(request: GenerateServiceSummaryRequest):
    """
    Генерирует краткое саммари сервиса на основе требований из дочерних страниц.

    Процесс:
    1. Получает все дочерние страницы родительской страницы
    2. Извлекает требования (все или только подтвержденные)
    3. Генерирует структурированное описание через LLM

    Args:
        parent_page_id: ID родительской страницы сервиса
        use_approved_only: Использовать только подтвержденные требования
        custom_prompt: Кастомный промпт для генерации саммари
        max_tokens: Максимальное количество токенов для обработки
        max_pages: Максимальное количество страниц для обработки

    Returns:
        Структурированное описание назначения и функций сервиса
    """
    logger.info("[generate_service_summary] <- parent_page_id=%s", request.parent_page_id)

    try:
        # Инициализируем сервис с параметрами из запроса
        summary_service = ServiceSummaryService(
            max_tokens=request.max_tokens,
            max_pages=request.max_pages
        )

        # Генерируем саммари
        result = summary_service.generate_service_summary(
            parent_page_id=request.parent_page_id,
            use_approved_only=request.use_approved_only,
            custom_prompt=request.custom_prompt
        )

        logger.info("[generate_service_summary] -> success=%s", result.get("success"))

        # Возвращаем результат в формате Pydantic модели
        return GenerateServiceSummaryResponse(**result)

    except Exception as e:
        logger.error("[generate_service_summary] Unexpected error: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate service summary: {str(e)}"
        )


@router.get("/service_summary/{parent_page_id}",
            response_model=GenerateServiceSummaryResponse,
            tags=["Саммари сервиса"],
            summary="Быстрая генерация саммари сервиса (GET)")
async def get_service_summary(
        parent_page_id: str,
        use_approved_only: bool = Query(True, description="Использовать только подтвержденные требования"),
        max_tokens: int = Query(50000, description="Максимальное количество токенов"),
        max_pages: int = Query(50, description="Максимальное количество страниц")
):
    """
    Упрощенная GET версия для быстрой генерации саммари сервиса.

    Args:
        parent_page_id: ID родительской страницы сервиса
        use_approved_only: Использовать только подтвержденные требования
        max_tokens: Максимальное количество токенов для обработки
        max_pages: Максимальное количество страниц для обработки

    Returns:
        Структурированное описание назначения и функций сервиса
    """
    logger.info("[get_service_summary] <- parent_page_id=%s", parent_page_id)

    # Создаем запрос и вызываем POST эндпоинт
    request = GenerateServiceSummaryRequest(
        parent_page_id=parent_page_id,
        use_approved_only=use_approved_only,
        max_tokens=max_tokens,
        max_pages=max_pages
    )

    return await generate_service_summary(request)


@router.get("/service_summary_health", tags=["Саммари сервиса"])
async def service_summary_health_check():
    """Проверка работоспособности модуля генерации саммари"""
    return {
        "status": "ok",
        "module": "service_summary",
        "endpoints": [
            "POST /generate_service_summary",
            "GET /service_summary/{parent_page_id}",
            "GET /service_summary_health"
        ],
        "description": "Service summary generation based on child pages requirements"
    }