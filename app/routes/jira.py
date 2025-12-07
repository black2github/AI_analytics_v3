# app/routes/jira.py - ИСПРАВЛЕННАЯ ВЕРСИЯ с параллельностью

"""
Маршруты для работы с Jira API.
"""
import logging
from typing import List, Optional, Dict, Any, Union
from fastapi import APIRouter
from pydantic import BaseModel, field_validator
import anyio  # pip install anyio

from app.jira_loader import extract_confluence_page_ids_from_jira_tasks
from app.services.analysis_service import analyze_pages

# Создаем APIRouter для FastAPI
router = APIRouter()

logger = logging.getLogger(__name__)


class PageAnalysisResult(BaseModel):
    """Модель результата анализа одной страницы."""
    page_id: str
    analysis: Union[Dict[str, Any], str]
    template_analysis: Optional[Dict[str, Any]] = None

    @field_validator('analysis')
    @classmethod
    def validate_analysis(cls, v):
        """Валидатор для поля analysis - приводим к нужному формату"""
        if isinstance(v, str):
            return {"error": v}
        elif isinstance(v, dict):
            return v
        else:
            return {"error": str(v)}


class JiraTaskRequest(BaseModel):
    """Модель запроса для анализа задач Jira."""
    jira_task_ids: List[str]
    prompt_template: Optional[str] = None
    service_code: Optional[str] = None
    check_templates: bool = False


class JiraTaskResponse(BaseModel):
    """Модель ответа с результатом анализа."""
    success: bool
    jira_task_ids: List[str]
    confluence_page_ids: List[str]
    total_pages_found: int
    analysis_results: Optional[List[PageAnalysisResult]] = None
    error: Optional[str] = None
    templates_analyzed: int = 0


@router.post("/analyze-jira-task", response_model=JiraTaskResponse, response_model_exclude_none=True)
async def analyze_jira_task(request: JiraTaskRequest):
    """
     ОПТИМИЗИРОВАНО: Анализирует задачи Jira с параллельной обработкой

    Анализирует задачи Jira с опциональной проверкой соответствия шаблонам.
    Тяжелые операции (извлечение page_ids и анализ) выполняются в отдельных потоках.
    """
    logger.info("[analyze_jira_task] <- Processing %d Jira task(s) with check_templates=%s",
                len(request.jira_task_ids), request.check_templates)

    try:
        jira_task_ids = request.jira_task_ids

        if not jira_task_ids:
            return JiraTaskResponse(
                success=False,
                jira_task_ids=[],
                confluence_page_ids=[],
                total_pages_found=0,
                error="jira_task_ids cannot be empty"
            )

        #  ШАГ 1: Извлекаем page_ids из задач Jira (блокирующая операция в thread pool)
        logger.info("[analyze_jira_task] Extracting Confluence page IDs from Jira tasks...")
        page_ids = await anyio.to_thread.run_sync(
            extract_confluence_page_ids_from_jira_tasks,
            jira_task_ids
        )

        logger.info("[analyze_jira_task] Found %d Confluence page IDs", len(page_ids))

        if not page_ids:
            return JiraTaskResponse(
                success=True,
                jira_task_ids=jira_task_ids,
                confluence_page_ids=[],
                total_pages_found=0,
                analysis_results=None,
                error="No Confluence page IDs found in the specified Jira tasks"
            )

        #  ШАГ 2: Проводим анализ найденных страниц (блокирующая операция в thread pool)
        logger.info("[analyze_jira_task] Starting analysis of %d pages with check_templates=%s",
                    len(page_ids), request.check_templates)

        analysis_results = await anyio.to_thread.run_sync(
            analyze_pages,
            page_ids,
            request.prompt_template,
            request.service_code,
            request.check_templates
        )

        logger.info("[analyze_jira_task] -> Analysis completed, got %d results", len(analysis_results))

        # Обработка результатов (быстрая операция, не требует thread pool)
        parsed_results = []
        templates_analyzed = 0

        for result in analysis_results:
            try:
                template_analysis = result.get("template_analysis")

                # Подсчитываем количество проанализированных шаблонов
                if template_analysis and template_analysis.get("template_type"):
                    templates_analyzed += 1

                # Создаем объект с условными параметрами
                result_params = {
                    "page_id": result["page_id"],
                    "analysis": result["analysis"]
                }

                # Добавляем template_analysis только если он существует
                if template_analysis:
                    result_params["template_analysis"] = template_analysis

                parsed_result = PageAnalysisResult(**result_params)
                parsed_results.append(parsed_result)

                logger.debug(
                    "[analyze_jira_task] Processed result for page_id=%s, has_template=%s",
                    result["page_id"], template_analysis is not None)

            except Exception as e:
                logger.error("[analyze_jira_task] Error processing result for page_id=%s: %s",
                             result.get("page_id", "unknown"), str(e))
                # Создаем запасной результат без template_analysis
                parsed_results.append(PageAnalysisResult(
                    page_id=result.get("page_id", "unknown"),
                    analysis={"error": f"Processing error: {str(e)}"}
                ))

        logger.info("[analyze_jira_task] Successfully parsed %d results, %d templates analyzed",
                    len(parsed_results), templates_analyzed)

        return JiraTaskResponse(
            success=True,
            jira_task_ids=jira_task_ids,
            confluence_page_ids=page_ids,
            total_pages_found=len(page_ids),
            analysis_results=parsed_results,
            templates_analyzed=templates_analyzed
        )

    except Exception as e:
        logger.error("[analyze_jira_task] Error: %s", str(e), exc_info=True)
        return JiraTaskResponse(
            success=False,
            jira_task_ids=request.jira_task_ids if request else [],
            confluence_page_ids=[],
            total_pages_found=0,
            error=str(e)
        )


@router.get("/jira/health")
async def health_check():
    """Проверка доступности Jira модуля."""
    return {
        "success": True,
        "message": "Jira module is healthy",
        "endpoints": [
            "POST /analyze-jira-task",
            "GET /jira/health"
        ],
        "features": [
            "Parallel processing with anyio",
            "Confluence page extraction",
            "Requirements analysis",
            "Template structure analysis"
        ]
    }