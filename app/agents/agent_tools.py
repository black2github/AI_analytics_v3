# app/agents/agent_tools.py

"""
Инструменты (tools) для LLM-агента.
Каждый инструмент оборачивает существующую функциональность сервиса.

ИСПРАВЛЕНО для langchain 1.1.2: используем правильные импорты и структуру
"""

import json
import logging
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)


def search_requirements_tool(query: str, service_code: Optional[str] = None, top_k: int = 5) -> str:
    """
    Инструмент для поиска требований в базе знаний.

    Args:
        query: Поисковый запрос
        service_code: Код сервиса (опционально)
        top_k: Количество результатов

    Returns:
        JSON-строка с результатами поиска
    """
    logger.info("[search_requirements_tool] <- query='%s', service_code=%s, top_k=%d",
                query, service_code, top_k)

    try:
        # Импортируем внутри функции чтобы избежать циклических зависимостей
        from app.rag_pipeline import search_documents
        from app.service_registry import resolve_service_code_by_user

        # Определяем service_code если не указан
        if not service_code:
            service_code = resolve_service_code_by_user()
            logger.debug("[search_requirements_tool] Resolved service_code: %s", service_code)

        # Выполняем поиск
        results = search_documents(
            query=query,
            service_code=service_code,
            top_k=top_k
        )

        if not results:
            logger.warning("[search_requirements_tool] No results found for query")
            return json.dumps({
                "success": False,
                "message": "Требования по запросу не найдены",
                "results": []
            }, ensure_ascii=False)

        # Форматируем результаты
        formatted_results = []
        for i, doc in enumerate(results, 1):
            formatted_results.append({
                "rank": i,
                "page_id": doc.metadata.get("page_id", "unknown"),
                "title": doc.metadata.get("title", "Без названия"),
                "requirement_type": doc.metadata.get("requirement_type", "unknown"),
                "content_preview": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                "is_platform": doc.metadata.get("is_platform", False),
                "service_code": doc.metadata.get("service_code", "unknown")
            })

        logger.info("[search_requirements_tool] -> Found %d results", len(formatted_results))

        return json.dumps({
            "success": True,
            "query": query,
            "service_code": service_code,
            "results_count": len(formatted_results),
            "results": formatted_results
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error("[search_requirements_tool] Error: %s", str(e), exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Ошибка при поиске требований"
        }, ensure_ascii=False)


def analyze_page_tool(
        page_ids: Union[str, List[str]],
        service_code: Optional[str] = None,
        check_templates: bool = False
) -> str:
    """
    Инструмент для анализа одной или нескольких страниц Confluence.

    Args:
        page_ids: ID страницы или список ID страниц Confluence (строка с ID разделёнными запятыми или список)
        service_code: Код сервиса
        check_templates: Проверять ли соответствие шаблонам

    Returns:
        JSON-строка с результатами анализа
    """
    # Нормализуем page_ids в список
    if isinstance(page_ids, str):
        # Если строка содержит запятые - разбиваем
        if ',' in page_ids:
            page_ids_list = [pid.strip() for pid in page_ids.split(',') if pid.strip()]
        else:
            page_ids_list = [page_ids.strip()]
    elif isinstance(page_ids, list):
        page_ids_list = [str(pid).strip() for pid in page_ids if pid]
    else:
        page_ids_list = [str(page_ids).strip()]

    logger.info("[analyze_page_tool] <- page_ids=%s (%d pages), service_code=%s, check_templates=%s",
                page_ids_list, len(page_ids_list), service_code, check_templates)

    try:
        from app.services.analysis_service import analyze_pages
        from app.service_registry import resolve_service_code_by_user

        # Определяем service_code
        if not service_code:
            service_code = resolve_service_code_by_user()

        # Выполняем анализ всех страниц за один вызов
        results = analyze_pages(
            page_ids=page_ids_list,
            prompt_template=None,
            service_code=service_code,
            check_templates=check_templates
        )

        if not results:
            logger.warning("[analyze_page_tool] No results returned for pages %s", page_ids_list)
            return json.dumps({
                "success": False,
                "message": f"Не удалось проанализировать страницы {', '.join(page_ids_list)}",
                "page_ids": page_ids_list
            }, ensure_ascii=False)

        logger.info("[analyze_page_tool] -> Analysis completed for %d pages", len(results))

        # Формируем ответ с результатами для всех страниц
        return json.dumps({
            "success": True,
            "pages_count": len(results),
            "service_code": service_code,
            "pages": [
                {
                    "page_id": result.get("page_id"),
                    "analysis": result.get("analysis", "Анализ не выполнен"),
                    "template_analysis": result.get("template_analysis"),
                    "token_usage": result.get("token_usage")
                }
                for result in results
            ]
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error("[analyze_page_tool] Error: %s", str(e), exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": f"Ошибка при анализе страниц {', '.join(page_ids_list) if 'page_ids_list' in locals() else page_ids}"
        }, ensure_ascii=False)


def check_template_compliance_tool(
        page_id: str,
        requirement_type: Optional[str] = None,
        service_code: Optional[str] = None
) -> str:
    """
    Инструмент для проверки соответствия требования шаблону.

    Args:
        page_id: ID страницы
        requirement_type: Тип требования (FR, NFR, etc.) - ОПЦИОНАЛЬНО, будет определён автоматически
        service_code: Код сервиса

    Returns:
        JSON-строка с результатами проверки
    """
    logger.info("[check_template_compliance_tool] <- page_id=%s, type=%s, service_code=%s",
                page_id, requirement_type, service_code)

    try:
        from app.services.analysis_service import analyze_with_templates
        from app.service_registry import resolve_service_code_by_user
        from app.services.template_type_analysis import analyze_page_template_type

        # Определяем service_code
        if not service_code:
            service_code = resolve_service_code_by_user()

        # Если requirement_type не указан - определяем автоматически
        if not requirement_type:
            logger.info("[check_template_compliance_tool] requirement_type not provided, auto-detecting...")
            requirement_type = analyze_page_template_type(page_id)

            if not requirement_type:
                logger.warning("[check_template_compliance_tool] Could not auto-detect requirement_type for page %s",
                               page_id)
                return json.dumps({
                    "success": False,
                    "message": f"Не удалось определить тип требования для страницы {page_id}. "
                               f"Укажите тип явно (FR, NFR, dataModel, process и т.д.)",
                    "page_id": page_id,
                    "auto_detection_failed": True
                }, ensure_ascii=False)

            logger.info("[check_template_compliance_tool] Auto-detected requirement_type: %s", requirement_type)

        # Формируем items для анализа
        items = [{
            "page_id": page_id,
            "requirement_type": requirement_type
        }]

        # Выполняем анализ
        results = analyze_with_templates(
            items=items,
            prompt_template=None,
            service_code=service_code
        )

        if not results:
            logger.warning("[check_template_compliance_tool] No results for page %s", page_id)
            return json.dumps({
                "success": False,
                "message": f"Не удалось проверить соответствие шаблону для страницы {page_id}",
                "page_id": page_id
            }, ensure_ascii=False)

        result = results[0]

        logger.info("[check_template_compliance_tool] -> Check completed for page %s", page_id)

        return json.dumps({
            "success": True,
            "page_id": page_id,
            "requirement_type": requirement_type,
            "service_code": service_code,
            "template_analysis": result.get("template_analysis"),
            "legacy_formatting_issues": result.get("legacy_formatting_issues", []),
            "template_used": result.get("template_used"),
            "auto_detected": not bool(requirement_type)
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error("[check_template_compliance_tool] Error: %s", str(e), exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": f"Ошибка при проверке соответствия шаблону для страницы {page_id}"
        }, ensure_ascii=False)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def format_search_results_for_display(results: list) -> str:
    """
    Форматирует результаты поиска в читаемый текст.

    Args:
        results: Список результатов поиска

    Returns:
        Отформатированная строка
    """
    if not results:
        return "Результаты не найдены"

    formatted = []
    for i, result in enumerate(results, 1):
        formatted.append(
            f"{i}. [{result['title']}] (page_id: {result['page_id']})\n"
            f"   Тип: {result['requirement_type']}\n"
            f"   Превью: {result['content_preview'][:150]}...\n"
        )

    return "\n".join(formatted)


# ============================================================================
# ФУНКЦИЯ ДЛЯ ПАРСИНГА АРГУМЕНТОВ (для совместимости с разными версиями)
# ============================================================================

def parse_tool_input(tool_input: Union[str, dict]) -> dict:
    """
    Парсит входные данные инструмента.
    В разных версиях LangChain tool_input может быть строкой или словарём.

    Args:
        tool_input: Входные данные (строка или словарь)

    Returns:
        Словарь с параметрами
    """
    if isinstance(tool_input, dict):
        return tool_input

    if isinstance(tool_input, str):
        try:
            return json.loads(tool_input)
        except json.JSONDecodeError:
            # Если не JSON, возвращаем как query
            return {"query": tool_input}

    return {}