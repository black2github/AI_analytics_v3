# app/services/analysis_service.py

import json
import os
import re
import time
from typing import Optional, List, Any, Union
from app.config import (
    PAGE_ANALYSIS_PROMPT_FILE,
    UNIFIED_STORAGE_NAME,
    LLM_MODEL
)
from app.rag_pipeline import logger, build_chain, build_template_analysis_chain
from app.services.template_type_analysis import perform_legacy_structure_check
from app.service_registry import resolve_service_code_by_user, resolve_service_code_from_pages_or_user
from app.services.context_builder import build_context_optimized
from app.template_registry import get_template_by_type
from app.utils.tokens_budget_utils import get_llm_context_size, calculate_token_budget, truncate_smart, count_tokens


def _get_content_from_response(response: Union[str, Any]) -> str:
    """
    Безопасно извлекает текст из ответа цепочки LCEL.
    Если ответ AIMessage, возвращает .content, иначе приводит к строке.
    """
    if hasattr(response, 'content'):
        return response.content
    return str(response)


def analyze_text(text: str, prompt_template: Optional[str] = None, service_code: Optional[str] = None):
    logger.info("[analyze_text] <- text length=%d, service_code=%s", len(text), service_code)
    if not service_code:
        service_code = resolve_service_code_by_user()
        logger.info("[analyze_text] Resolved service_code: %s", service_code)

    chain = build_chain(prompt_template)
    context = build_context_optimized(service_code, requirements_text=text)

    try:
        # ИСПРАВЛЕНО: замена run() на invoke() + извлечение контента
        response = chain.invoke({"requirement": text, "context": context})
        result = _get_content_from_response(response)

        logger.info("[analyze_text] -> result length=%d", len(result))
        return result
    except Exception as e:
        if "token limit" in str(e).lower():
            logger.error("[analyze_text] Token limit exceeded: %s", str(e))
            return {"error": "Превышен лимит токенов модели. Уменьшите объем текста или контекста."}
        raise


def analyze_pages(page_ids: List[str], prompt_template: Optional[str] = None,
                  service_code: Optional[str] = None, check_templates: bool = False):
    """
    Анализ страниц с оптимизированным распределением токенов.

    Args:
        page_ids: Список ID страниц для анализа
        prompt_template: Кастомный промпт (опционально)
        service_code: Код сервиса
        check_templates: Проверять соответствие шаблонам

    Returns:
        Список результатов анализа
    """
    logger.info("[analyze_pages] <- page_ids=%s, service_code=%s, check_templates=%s",
                page_ids, service_code, check_templates)

    try:
        if not service_code:
            service_code = resolve_service_code_from_pages_or_user(page_ids)
            logger.debug("[analyze_pages] Resolved service_code: %s", service_code)

        # Импорты
        from app.page_cache import get_page_data_cached
        from app.services.template_type_analysis import get_template_name_by_type

        # Определяем размер контекста LLM
        llm_context_size = get_llm_context_size()
        logger.info("[analyze_pages] LLM model: %s, context size: %d", os.getenv("LLM_MODEL"), llm_context_size)

        # Загружаем и измеряем системный промпт
        template = prompt_template or open(PAGE_ANALYSIS_PROMPT_FILE, "r", encoding="utf-8").read().strip()
        template_tokens = count_tokens(template)
        logger.info(f"[analyze_pages] System prompt size: {template_tokens} tokens")

        # Инициализация для цикла
        requirements = []
        valid_page_ids = []
        current_req_tokens = 0

        #
        # ЦИКЛ ДОБАВЛЕНИЯ ТРЕБОВАНИЙ С ДИНАМИЧЕСКИМ ПЕРЕСЧЕТОМ БЮДЖЕТА
        #
        token_budget = calculate_token_budget(
            template_tokens=template_tokens,
            available_tokens=llm_context_size,
            requirements_length=current_req_tokens
        )

        for page_id in page_ids:
            logger.debug(
                f"[analyze_pages] Page {page_id}: current_req_tokens={current_req_tokens}, "
                f"budget={token_budget['requirements']}"
            )

            # Получаем данные страницы через кеш
            page_data = get_page_data_cached(page_id)

            if not page_data:
                logger.warning("[analyze_pages] Could not load page data for %s", page_id)
                continue

            content = page_data['full_content']
            title = page_data['title']
            requirement_type_code = page_data['requirement_type']

            # Получаем человекочитаемое название типа
            requirement_type_name = get_template_name_by_type(
                requirement_type_code) if requirement_type_code else "Неизвестный тип"

            # Формируем текст с заголовком
            header = f"---\npage_id: {page_id}\ntitle: {title}\ntype: {requirement_type_name}\n---\n"
            page_text_with_header = header + content

            if not content:
                logger.warning("[analyze_pages] Empty content for page %s", page_id)
                continue

            # Подсчитываем токены для этой страницы
            req_tokens = count_tokens(page_text_with_header)
            logger.debug(f"[analyze_pages] Page {page_id}: {req_tokens} tokens")

            # ПРОВЕРКА: влезет ли страница в бюджет требований?
            if current_req_tokens + req_tokens <= token_budget['requirements']:
                requirements.append({
                    "page_id": page_id,
                    "content": page_text_with_header,
                    "title": title,
                    "requirement_type": requirement_type_name
                })
                valid_page_ids.append(page_id)
                current_req_tokens += req_tokens

                logger.debug(
                    f"[analyze_pages] Added page {page_id}: "
                    f"{req_tokens} tokens (total: {current_req_tokens}/{token_budget['requirements']})"
                )
            else:
                logger.warning(
                    f"[analyze_pages] Excluded page {page_id}: would exceed budget "
                    f"({current_req_tokens + req_tokens} > {token_budget['requirements']})"
                )
                # Не добавляем страницу и прерываем цикл
                break

        if not requirements:
            logger.warning("[analyze_pages] No valid requirements found, service code: %s", service_code)
            return []

        # ФИНАЛЬНЫЙ ПЕРЕСЧЕТ БЮДЖЕТА с фактическим размером требований
        token_budget = calculate_token_budget(
            template_tokens=template_tokens,
            available_tokens=llm_context_size,
            requirements_length=current_req_tokens
        )

        logger.info(
            f"[analyze_pages] Final token budget after adding {len(requirements)} pages: "
            f"prompt={token_budget['system_prompt']}, "
            f"requirements={current_req_tokens}/{token_budget['requirements']}, "
            f"context_budget={token_budget['rag_context']}, "
            f"response={token_budget['response_reserve']}"
        )

        # ПЕРЕРАСПРЕДЕЛЕНИЕ: если требования меньше бюджета - отдаем токены контексту
        if current_req_tokens < token_budget['requirements']:
            tokens_saved = token_budget['requirements'] - current_req_tokens
            token_budget['rag_context'] += tokens_saved
            logger.info(
                f"[analyze_pages] Redistributed {tokens_saved} unused requirement tokens to context. "
                f"New context budget: {token_budget['rag_context']} tokens"
            )

        # Формируем requirements_text с заголовками
        requirements_text = "\n\n".join([req['content'] for req in requirements])
        logger.debug("[analyze_pages] Total requirements text: %d chars", len(requirements_text))

        #
        # ПОСТРОЕНИЕ КОНТЕКСТА с передачей бюджета
        #
        context = build_context_optimized(
            service_code=service_code,
            requirements_text=requirements_text,
            exclude_page_ids=valid_page_ids,
            max_context_tokens=token_budget['rag_context'],
            response_reserve=token_budget['response_reserve']
        )

        context_tokens = count_tokens(context)
        logger.info(f"[analyze_pages] Context built: {context_tokens} tokens")

        # ФИНАЛЬНАЯ ПРОВЕРКА общего размера
        total_tokens = template_tokens + current_req_tokens + context_tokens
        max_safe_tokens = llm_context_size - token_budget['response_reserve']

        logger.info(
            f"[analyze_pages] Final token usage: "
            f"prompt={template_tokens}, req={current_req_tokens}, ctx={context_tokens}, "
            f"total={total_tokens}/{max_safe_tokens} ({total_tokens / llm_context_size * 100:.1f}% of LLM context)"
        )

        # Если все равно превышен лимит - обрезаем контекст (safety net)
        if total_tokens > max_safe_tokens:
            overflow = total_tokens - max_safe_tokens
            new_context_budget = context_tokens - overflow - 200  # -200 для запаса

            logger.warning(
                f"[analyze_pages] Token overflow detected: {overflow} tokens. "
                f"Reducing context from {context_tokens} to {new_context_budget}"
            )

            context = truncate_smart(context, new_context_budget, preserve_start=True)
            context_tokens = count_tokens(context)
            total_tokens = template_tokens + current_req_tokens + context_tokens

            logger.info(f"[analyze_pages] After emergency reduction: total={total_tokens} tokens")

        # Проверка на критическое превышение
        if total_tokens > llm_context_size:
            logger.error(
                f"[analyze_pages] CRITICAL: Total tokens ({total_tokens}) exceed LLM limit ({llm_context_size})"
            )
            return [{
                "page_id": pid,
                "analysis": "Ошибка: невозможно уместить все данные в контекст LLM даже после оптимизации"
            } for pid in valid_page_ids]

        #
        # АНАЛИЗ LLM
        #
        chain = build_chain(prompt_template)

        try:
            # ИСПРАВЛЕНО: замена run() на invoke() + извлечение контента
            response = chain.invoke({"requirement": requirements_text, "context": context})
            result = _get_content_from_response(response)

            logger.debug("[analyze_pages] Raw LLM response: '%s'", result[:200])

            # Парсинг результата
            cleaned_result = _extract_json_from_llm_response(result)
            if not cleaned_result:
                logger.error("[analyze_pages] No valid JSON found in LLM response")
                return [{
                    "page_id": pid,
                    "analysis": "Ошибка: LLM не вернул корректный JSON"
                } for pid in valid_page_ids]

            try:
                parsed_result = json.loads(cleaned_result)
                logger.info("[analyze_pages] Successfully parsed JSON response")
            except json.JSONDecodeError as json_err:
                logger.error("[analyze_pages] JSON decode error: %s", str(json_err))
                return [{
                    "page_id": valid_page_ids[0] if valid_page_ids else "unknown",
                    "analysis": result
                }]

            if not isinstance(parsed_result, dict):
                logger.error("[analyze_pages] Result is not a dictionary")
                return [{
                    "page_id": pid,
                    "analysis": "Ошибка: неожиданный формат ответа LLM"
                } for pid in valid_page_ids]

            # Формируем финальные результаты
            results = []
            logger.debug("[analyze_pages] Parsed results: '%s'", list(parsed_result.keys()))

            for page_id in valid_page_ids:
                analysis = parsed_result.get(page_id, f"Анализ для страницы {page_id} не найден")
                page_result = {
                    "page_id": page_id,
                    "analysis": analysis,
                    "token_usage": {
                        "prompt": template_tokens,
                        "requirements": current_req_tokens,
                        "context": context_tokens,
                        "total_input": total_tokens,
                        "limit": llm_context_size,
                        "usage_percent": round(total_tokens / llm_context_size * 100, 1)
                    }
                }

                # Опциональная проверка шаблонов
                if check_templates:
                    template_analysis = _analyze_page_template_if_needed(page_id, service_code)
                    if template_analysis:
                        page_result["template_analysis"] = template_analysis

                results.append(page_result)

            logger.info("[analyze_pages] -> Successfully analyzed %d pages", len(results))
            return results

        except Exception as e:
            if "token limit" in str(e).lower():
                logger.error("[analyze_pages] Token limit exceeded: %s", str(e))
                return [{
                    "page_id": pid,
                    "analysis": "Ошибка: превышен лимит токенов модели"
                } for pid in valid_page_ids]
            logger.error("[analyze_pages] Error in LLM chain: %s", str(e))
            raise

    except Exception as e:
        logger.exception("[analyze_pages] Error in analyze_pages")
        raise


def _analyze_page_template_if_needed(page_id: str, service_code: str) -> Optional[dict]:
    """
    Анализирует соответствие шаблону (для случая, если страница еще не была одобрена и сохранена)
    """
    logger.info("[_analyze_page_template_if_needed] <- Checking page_id: %s", page_id)

    try:
        from app.services.document_service import DocumentService
        from app.services.template_type_analysis import analyze_page_template_type

        # Проверяем наличие одобренных фрагментов
        document_service = DocumentService()
        has_fragments = document_service.has_approved_fragments([page_id])

        if has_fragments:
            logger.info(
                "[_analyze_page_template_if_needed] -> Page %s has approved fragments, skipping template analysis",
                page_id
            )
            return None

        logger.info("[_analyze_page_template_if_needed] Page %s has no approved fragments, analyzing template",
                    page_id)

        # Определяем тип шаблона
        template_type = analyze_page_template_type(page_id)

        if not template_type:
            logger.info("[_analyze_page_template_if_needed] -> No template type identified for page %s", page_id)
            return {
                "template_type": None,
                "template_analysis": None,
                "reason": "Template type not identified"
            }

        logger.info("[_analyze_page_template_if_needed] Template type is '%s' for page %s", template_type, page_id)

        template_analysis_items = [{
            "requirement_type": template_type,
            "page_id": page_id
        }]

        # Проводим анализ соответствия шаблону
        template_analysis_results = analyze_with_templates(
            items=template_analysis_items,
            service_code=service_code
        )

        if template_analysis_results:
            analysis_result = template_analysis_results[0]
            logger.info("[_analyze_page_template_if_needed] -> Template analysis completed for page %s", page_id)

            return {
                "template_type": template_type,
                "template_analysis": analysis_result.get("template_analysis"),
                "legacy_formatting_issues": analysis_result.get("legacy_formatting_issues", []),
                "analysis_timestamp": analysis_result.get("analysis_timestamp"),
                "storage_used": analysis_result.get("storage_used")
            }
        else:
            logger.warning("[_analyze_page_template_if_needed] -> Template analysis failed for page %s", page_id)
            return {
                "template_type": template_type,
                "template_analysis": None,
                "reason": "Template analysis failed"
            }

    except Exception as e:
        # logger.error("[_analyze_page_template_if_needed] -> Error analyzing template for page %s: %s", page_id, e)
        logger.error(
            "[_analyze_page_template_if_needed] -> Error analyzing template for page %s: %s",
            page_id,
            e,
            exc_info=True
        )

        return {
            "template_type": None,
            "template_analysis": None,
            "error": str(e)
        }


def analyze_with_templates(items: List[dict], prompt_template: Optional[str] = None,
                           service_code: Optional[str] = None):
    """
    Анализирует новые требования и их соответствие шаблонам с передачей шаблона в LLM.
    """
    logger.info("[analyze_with_templates] <- items count: %d, service_code: %s", len(items), service_code)

    if not service_code:
        page_ids = [item["page_id"] for item in items]
        service_code = resolve_service_code_from_pages_or_user(page_ids)
        logger.info("[analyze_with_templates] Resolved service_code: %s", service_code)

    from app.page_cache import get_page_data_cached
    from app.services.template_type_analysis import get_template_name_by_type

    results = []
    template_chain = build_template_analysis_chain(prompt_template)

    for item in items:
        requirement_type = item["requirement_type"]
        page_id = item["page_id"]

        logger.info("[analyze_with_templates] Processing page_id: %s, type: %s", page_id, requirement_type)

        page_data = get_page_data_cached(page_id)

        if not page_data:
            logger.warning("[analyze_with_templates] Could not load page data for %s", page_id)
            results.append({
                "page_id": page_id,
                "requirement_type": requirement_type,
                "template_analysis": {
                    "error": "Не удалось загрузить данные страницы",
                    "page_data_available": False
                },
                "legacy_formatting_issues": []
            })
            continue

        raw_content = page_data['full_content']
        title = page_data['title']
        requirement_type_name = get_template_name_by_type(
            requirement_type) if requirement_type else "Неизвестный тип"

        header = f"---\npage_id: {page_id}\ntitle: {title}\ntype: {requirement_type_name}\n---\n"
        content = header + raw_content

        template_txt = get_template_by_type(requirement_type)

        if not raw_content or not template_txt:
            logger.warning("[analyze_with_templates] Missing content or template for page %s", page_id)
            results.append({
                "page_id": page_id,
                "requirement_type": requirement_type,
                "template_analysis": {
                    "error": "Отсутствует содержимое страницы или шаблон",
                    "template_available": bool(template_txt),
                    "content_available": bool(raw_content)
                },
                "legacy_formatting_issues": []
            })
            continue

        template_content = template_txt
        context = ""

        legacy_formatting_issues = perform_legacy_structure_check(template_txt, raw_content)

        try:
            logger.debug(
                "[analyze_with_templates] Sending to LLM: template=%d chars, content=%d chars",
                len(template_content), len(content)
            )

            # ИСПРАВЛЕНО: замена run() на invoke() + извлечение контента
            response = template_chain.invoke({
                "requirement": content,
                "template": template_content,
                "context": context
            })
            llm_result = _get_content_from_response(response)

            try:
                template_analysis = _parse_llm_template_response(llm_result)
                logger.info("[analyze_with_templates] LLM analysis completed for page %s", page_id)
            except Exception as json_error:
                logger.error("[analyze_with_templates] Failed to parse LLM JSON for page %s: %s", page_id,
                             str(json_error))
                template_analysis = {
                    "error": "Не удалось разобрать ответ LLM",
                    "raw_response": llm_result[:500],
                    "parse_error": str(json_error)
                }

            results.append({
                "page_id": page_id,
                "requirement_type": requirement_type,
                "template_analysis": template_analysis,
                "legacy_formatting_issues": legacy_formatting_issues,
                "template_used": requirement_type,
                "analysis_timestamp": time.time(),
                "storage_used": UNIFIED_STORAGE_NAME
            })

        except Exception as e:
            logger.error("[analyze_with_templates] Error analyzing page %s: %s", page_id, str(e))

            if "token limit" in str(e).lower():
                error_msg = "Превышен лимит токенов модели"
            else:
                error_msg = f"Ошибка анализа: {str(e)}"

            results.append({
                "page_id": page_id,
                "requirement_type": requirement_type,
                "template_analysis": {
                    "error": error_msg,
                    "error_type": "llm_error"
                },
                "legacy_formatting_issues": legacy_formatting_issues
            })

    logger.info("[analyze_with_templates] -> Completed analysis for %d items", len(results))
    return results


def _extract_json_from_llm_response(response: str) -> Optional[str]:
    """Извлекает JSON из ответа LLM"""
    if not response:
        return None

    response = response.strip()
    response = response.strip("```json").strip("```").strip()

    json_patterns = [
        r'```json\s*(\{.*\})\s*```',
        r'(\{.*\})',
        r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, response, re.DOTALL | re.MULTILINE)
        for match in matches:
            try:
                json.loads(match)
                logger.debug("[_extract_json_from_llm_response] Found valid JSON with pattern: %s", pattern)
                return match.strip()
            except json.JSONDecodeError:
                continue

    try:
        start = response.find('{')
        if start == -1:
            return None

        brace_count = 0
        end = start

        for i, char in enumerate(response[start:], start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i
                    break

        if brace_count == 0:
            candidate = response[start:end + 1]
            json.loads(candidate)
            logger.debug("[_extract_json_from_llm_response] Found valid JSON by manual parsing")
            return candidate.strip()

    except (json.JSONDecodeError, ValueError):
        pass

    logger.warning("[_extract_json_from_llm_response] No valid JSON found in response")
    return None


def _parse_llm_template_response(llm_response: str) -> dict:
    """Парсит JSON ответ от LLM"""
    json_content = _extract_json_from_llm_response(llm_response)

    if not json_content:
        raise ValueError("No valid JSON found in LLM response")

    parsed_result = json.loads(json_content)

    required_sections = ["template_compliance", "recommendations", "summary"]
    missing_sections = [section for section in required_sections if section not in parsed_result]

    if missing_sections:
        logger.warning("[_parse_llm_template_response] Missing sections in LLM response: %s", missing_sections)
        for section in missing_sections:
            parsed_result[section] = {"error": f"Section {section} missing from LLM response"}

    return parsed_result