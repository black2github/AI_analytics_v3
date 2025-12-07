# app/routes/analyze.py - ИСПРАВЛЕННАЯ ВЕРСИЯ с параллельностью

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import logging
import anyio  # pip install anyio
from anyio import to_thread

from app.services.analysis_service import analyze_text, analyze_pages, analyze_with_templates
from app.service_registry import is_valid_service

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyzeTextRequest(BaseModel):
    text: str
    prompt_template: Optional[str] = None
    service_code: Optional[str] = None


class AnalyzePagesRequest(BaseModel):
    page_ids: List[str]
    prompt_template: Optional[str] = None
    service_code: Optional[str] = None
    check_templates: bool = False


class AnalyzeWithTemplatesRequest(BaseModel):
    items: List[dict]  # Each item: {"requirement_type": str, "page_id": str}
    prompt_template: Optional[str] = None
    service_code: Optional[str] = None


class AnalyzeServicePagesRequest(BaseModel):
    page_ids: List[str]
    prompt_template: Optional[str] = None
    check_templates: bool = False


@router.post("/analyze", tags=["Анализ текстовых требований сервиса"])
async def analyze_from_text(payload: AnalyzeTextRequest):
    """
    ОПТИМИЗИРОВАНО: Анализирует текст в отдельном потоке
    """
    logger.debug("/analyze <- text length: %d", len(payload.text))
    try:
        #  ИСПРАВЛЕНО: Передаем аргументы позиционно
        result = await anyio.to_thread.run_sync(
            analyze_text,
            payload.text,
            payload.prompt_template,
            payload.service_code
        )
        logger.debug("/analyze -> result received")
        return {"result": result}
    except Exception as e:
        logger.exception("Ошибка в /analyze")
        return {"error": str(e)}


@router.post("/analyze_pages", tags=["Анализ существующих (ранее) требований сервиса"])
async def analyze_service_pages(payload: AnalyzePagesRequest):
    """
     ОПТИМИЗИРОВАНО: Анализирует страницы в отдельном потоке
    """
    logger.info("/analyze_pages <- %d page(s)", len(payload.page_ids))
    try:
        #  ИСПРАВЛЕНО: Передаем аргументы позиционно
        result = await anyio.to_thread.run_sync(
            analyze_pages,
            payload.page_ids,
            payload.prompt_template,
            payload.service_code,
            payload.check_templates
        )
        logger.info("/analyze_pages -> %d results", len(result) if isinstance(result, list) else 1)
        return {"results": result}
    except Exception as e:
        logger.exception("Ошибка в /analyze_pages")
        return {"error": str(e)}


@router.post("/analyze_service_pages/{code}", tags=["Анализ существующих (ранее) требований конкретного сервиса"])
async def analyze_specific_service_pages(code: str, payload: AnalyzeServicePagesRequest):
    """
     ОПТИМИЗИРОВАНО: Анализирует страницы конкретного сервиса в отдельном потоке
     ИСПРАВЛЕНО: Переименована функция (была коллизия имен)
    """
    logger.info("/analyze_service_pages/%s <- %d page(s)", code, len(payload.page_ids))

    if not is_valid_service(code):
        return {"error": f"Сервис с кодом {code} не найден"}

    try:
        #  ИСПРАВЛЕНО: Передаем аргументы позиционно
        result = await anyio.to_thread.run_sync(
            analyze_pages,
            payload.page_ids,
            payload.prompt_template,
            code,  # service_code
            payload.check_templates
        )
        logger.info("/analyze_service_pages/%s -> %d results", code, len(result) if isinstance(result, list) else 1)
        return {"results": result}
    except Exception as e:
        logger.exception("Ошибка в /analyze_service_pages/%s", code)
        return {"error": str(e)}


@router.post("/analyze_with_templates", tags=["Анализ новых требований сервиса и их оформления"])
async def analyze_with_templates_route(payload: AnalyzeWithTemplatesRequest):
    """
     ОПТИМИЗИРОВАНО: Анализирует требования с шаблонами в отдельном потоке

    Анализирует новые требования на соответствие шаблонам с передачей шаблона в LLM.

    Возвращает детальный анализ включая:
    - Соответствие структуре шаблона
    - Качество содержимого
    - Совместимость с системой
    - Конкретные рекомендации по улучшению
    """
    logger.info("[analyze_with_templates] <- %d item(s)", len(payload.items))
    try:
        #  ИСПРАВЛЕНО: Передаем аргументы позиционно
        result = await anyio.to_thread.run_sync(
            analyze_with_templates,
            payload.items,
            payload.prompt_template,
            payload.service_code
        )
        logger.info("[analyze_with_templates] -> %d results", len(result))
        return {"results": result}
    except Exception as e:
        logger.exception("Ошибка в /analyze_with_templates")
        return {"error": str(e)}