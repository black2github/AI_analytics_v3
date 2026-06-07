# app/routes/analyze.py - ИСПРАВЛЕННАЯ ВЕРСИЯ с параллельностью

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import logging
import anyio  # pip install anyio
from anyio import to_thread

from app.services.analysis_service import analyze_text, analyze_pages, analyze_pages_multi_pass, analyze_with_templates
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


class AnalyzePageMultiPassRequest(BaseModel):
    page_ids: List[str]
    service_code: Optional[str] = None


class AnalyzeServicePagesRequest(BaseModel):
    page_ids: List[str]
    prompt_template: Optional[str] = None
    check_templates: bool = False


@router.post("/analyze", tags=["Анализ текстовых требований сервиса"])
async def analyze_from_text(payload: AnalyzeTextRequest):
    """
    Анализирует произвольный текст требований с использованием RAG-контекста.

    Принимает текст напрямую (без привязки к Confluence), строит RAG-контекст
    по сервису и передаёт требование в LLM одним вызовом.

    Промпт берётся из `PAGE_ANALYSIS_PROMPT_FILE` (по умолчанию `page_prompt_template.txt`);
    может быть переопределён через `prompt_template` в теле запроса.

    Параметры запроса:
    - `text` — текст требования для анализа
    - `prompt_template` — кастомный промпт (опционально; заменяет файловый)
    - `service_code` — код сервиса для RAG-контекста (опционально; определяется автоматически)

    Возвращает:
    ```json
    { "result": "<текст анализа от LLM>" }
    ```
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
    Анализирует одну или несколько страниц Confluence одним вызовом LLM.

    Все страницы упаковываются в один промпт с динамическим распределением
    токенов: сначала рассчитывается бюджет под требования и RAG-контекст,
    затем страницы добавляются до исчерпания бюджета.
    Неиспользованные токены требований перераспределяются в пользу контекста.

    Промпт берётся из `PAGE_ANALYSIS_PROMPT_FILE` (по умолчанию `page_prompt_template.txt`);
    может быть переопределён через `prompt_template` в теле запроса.

    Параметры запроса:
    - `page_ids` — список ID страниц Confluence
    - `prompt_template` — кастомный промпт (опционально; заменяет файловый)
    - `service_code` — код сервиса (опционально; определяется автоматически по страницам)
    - `check_templates` — если `true`, дополнительно проверяет соответствие страниц шаблонам

    Возвращает список результатов, по одному на страницу:
    ```json
    {
        "page_id": "12345",
        "analysis": "<текст анализа от LLM>",
        "token_usage": {
            "prompt": 800,
            "requirements": 3200,
            "context": 5000,
            "total_input": 9000,
            "limit": 128000,
            "usage_percent": 7.0
        },
        "template_analysis": { ... }  // только если check_templates=true
    }
    ```
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
    Анализирует страницы Confluence для конкретного сервиса (код сервиса — в URL).

    Работает идентично `/analyze_pages`, но код сервиса фиксируется через путь
    запроса `{code}` и не определяется автоматически. Возвращает ошибку если
    сервис с таким кодом не зарегистрирован.

    Параметры пути:
    - `code` — код сервиса (должен существовать в реестре сервисов)

    Параметры запроса:
    - `page_ids` — список ID страниц Confluence
    - `prompt_template` — кастомный промпт (опционально; заменяет файловый)
    - `check_templates` — если `true`, дополнительно проверяет соответствие страниц шаблонам

    Возвращает список результатов, по одному на страницу:
    ```json
    {
        "page_id": "12345",
        "analysis": "<текст анализа от LLM>",
        "token_usage": {
            "prompt": 800,
            "requirements": 3200,
            "context": 5000,
            "total_input": 9000,
            "limit": 128000,
            "usage_percent": 7.0
        },
        "template_analysis": { ... }  // только если check_templates=true
    }
    ```
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


@router.post("/analyze_pages_multi_pass", tags=["Анализ существующих (ранее) требований сервиса"])
async def analyze_pages_multi_pass_route(payload: AnalyzePageMultiPassRequest):
    """
    Многопроходное ревью страниц с требованиями.

    Адаптируется к размеру контекста LLM — подходит для моделей с небольшим
    контекстом (32K токенов и более).

    Стратегия:
    - Уровень 1 (~98% документов): N проходов по полному тексту страницы,
      каждый проход проверяет свою группу критериев.
    - Уровень 2 (~2% документов): предварительное сжатие документа,
      затем те же проходы по конспекту + предупреждение в ответе.

    Число проходов зависит от типа требований (function — 3 прохода,
    states — 1 проход и т.д.) и определяется файлами промптов в
    app/prompts/review/{req_type}/.

    Возвращает список результатов, по одному на страницу:
    {
        "page_id": str,
        "analysis": str,       — финальный текст анализа
        "pass_count": int,     — число выполненных проходов
        "level": int,          — 1 (полный текст) или 2 (сжатый)
        "req_type": str,       — код типа требований
        "token_usage": dict    — статистика токенов
    }
    """
    logger.info("/analyze_pages_multi_pass <- %d page(s)", len(payload.page_ids))
    try:
        result = await anyio.to_thread.run_sync(
            analyze_pages_multi_pass,
            payload.page_ids,
            payload.service_code,
        )
        logger.info(
            "/analyze_pages_multi_pass -> %d results",
            len(result) if isinstance(result, list) else 1
        )
        return {"results": result}
    except Exception as e:
        logger.exception("Ошибка в /analyze_pages_multi_pass")
        return {"error": str(e)}


@router.post("/analyze_with_templates", tags=["Анализ новых требований сервиса и их оформления"])
async def analyze_with_templates_route(payload: AnalyzeWithTemplatesRequest):
    """
    Анализирует новые требования на соответствие зарегистрированным шаблонам.

    Для каждого элемента загружает страницу Confluence и шаблон соответствующего
    типа из реестра шаблонов, передаёт оба в LLM и дополнительно выполняет
    структурную проверку (legacy) без участия LLM.

    В отличие от `/analyze_pages`, каждая страница обрабатывается отдельным
    вызовом LLM и оценивается относительно своего шаблона, а не только в
    контексте сервиса.

    Параметры запроса:
    - `items` — список объектов `{"requirement_type": str, "page_id": str}`
    - `prompt_template` — кастомный промпт (опционально; заменяет файловый)
    - `service_code` — код сервиса (опционально; определяется автоматически)

    Возвращает список результатов, по одному на элемент:
    ```json
    {
        "page_id": "12345",
        "requirement_type": "function",
        "template_analysis": {
            "<поля анализа от LLM>"
        },
        "legacy_formatting_issues": [ "<список структурных замечаний>" ]
    }
    ```
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