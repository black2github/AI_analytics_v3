# app/routes/template_analysis.py - ИСПРАВЛЕННАЯ ВЕРСИЯ с параллельностью

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import logging
import anyio  # pip install anyio

from app.services.template_type_analysis import analyze_pages_template_types

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyzeTypesRequest(BaseModel):
    page_ids: List[str]


class PageTemplateResult(BaseModel):
    """Результат анализа одной страницы"""
    page_id: str
    template_name: Optional[str]


class AnalyzeTypesResponse(BaseModel):
    """Ответ с результатами анализа типов шаблонов"""
    results: List[PageTemplateResult]
    total_pages: int
    identified_types: int


@router.post("/analyze_types", response_model=AnalyzeTypesResponse, tags=["Анализ типов шаблонов"])
async def analyze_template_types(request: AnalyzeTypesRequest):
    """
    ✅ ОПТИМИЗИРОВАНО: Определяет типы шаблонов с параллельной обработкой.

    Определяет типы шаблонов требований для списка страниц Confluence.
    Каждая страница анализируется в отдельном потоке для максимальной производительности.

    Args:
        page_ids: Список идентификаторов страниц

    Returns:
        Список пар page_id - template_name для каждой страницы
    """
    logger.info("[analyze_template_types] <- Analyzing %d pages in parallel", len(request.page_ids))

    try:
        # ✅ КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Запускаем блокирующую операцию в thread pool
        template_types = await anyio.to_thread.run_sync(
            analyze_pages_template_types,
            request.page_ids
        )

        # Формируем результат в виде пар page_id - template_name
        results = []
        for page_id, template_type in zip(request.page_ids, template_types):
            results.append(PageTemplateResult(
                page_id=page_id,
                template_name=template_type
            ))

        # Подсчитываем статистику
        identified_count = sum(1 for result in results if result.template_name is not None)

        logger.info("[analyze_template_types] -> Identified %d/%d template types",
                    identified_count, len(request.page_ids))

        return AnalyzeTypesResponse(
            results=results,
            total_pages=len(request.page_ids),
            identified_types=identified_count
        )

    except Exception as e:
        logger.error("[analyze_template_types] Error: %s", str(e))

        # В случае ошибки возвращаем пустые результаты
        error_results = []
        for page_id in request.page_ids:
            error_results.append(PageTemplateResult(
                page_id=page_id,
                template_name=None
            ))

        return AnalyzeTypesResponse(
            results=error_results,
            total_pages=len(request.page_ids),
            identified_types=0
        )