# app/utils/tokens_budget_utils.py

from typing import Dict
from app.config import LLM_CONTEXT_SIZE, LLM_MODEL, LLM_PROVIDER
from app.rag_pipeline import logger, _encoding
import os

# Определение размера контекста в токенах для разных моделей
LLM_CONTEXT_SIZES = {
    'llama3.2:3b': 8000,
    'llama3.2:1b': 4000,
    'llama3.1:8b': 128000,
    'gpt-5.1': 400000, # Флагманская модель нового поколения — для сложных задач, кодинга, “agentic” задач и т.п
    'gpt-5.1-mini': 400000, # Более лёгкая и дешевая альтернатива GPT-5.1 — для задач средней сложности, массовых запросов, экономии бюджета.
    'gpt‑5.1‑nano': 400000, # Минимальный по цене вариант — для простых задач, трансформаций текста, классификаций, когда критична стоимость.
    'gpt‑4.1': 1048576,
    'gpt‑4.1‑mini': 1048576,
    'gpt‑4.1‑nano': 1048576,
    'gpt-4': 128000,
    'gpt-4-turbo': 128000,
    'gpt-3.5-turbo': 16000,
    'claude-sonnet-4': 200000,
    'claude-3-sonnet': 200000,
    'deepseek-chat': 128000,
    'kimi-k2-thinking': 256000,
    'kimi-latest': 256000,
    'kimi-k2-thinking-turbo': 256000,
    'gemini-2.5-flash': 1048576,
    'gemini-2.5-pro': 1048576,
    'gemini-2.0-pro': 1048576,
    'grok-4' : 256000,
    'grok-4-1-fast-non-reasoning': 2000000,
    'grok-4-1-fast-reasoning': 2000000,
    'grok-code-fast': 256000,
    'accounts/fireworks/models/qwen2p5-vl-32b-instruct' : 125000,
    'qwen/qwen3-30b-a3b-instruct-2507' : 32000,
    'qwen/qwen3-next-80b-a3b-instruct' : 262000,
    'qwen/qwen3-32b' : 40000,
    'default': LLM_CONTEXT_SIZE
}


def get_llm_context_size() -> int:
    """Определяет размер контекста текущей LLM"""
    llm_model = os.getenv("LLM_MODEL", LLM_MODEL).lower()  # fallback на импортированное
    return LLM_CONTEXT_SIZES.get(llm_model, LLM_CONTEXT_SIZES['default'])


def calculate_token_budget(
        template_tokens: int,
        available_tokens: int,
        requirements_length: int = 0
) -> Dict[str, int]:
    """
    Умное распределение токенов с учетом фактического размера промпта.

    Args:
        template_tokens: Фактический размер системного промпта
        available_tokens: Общий размер контекста LLM
        requirements_length: Примерный размер требований (для адаптации)

    Returns:
        Словарь с распределением токенов
    """
    logger.debug("[calculate_token_budget] <- template_tokens: %d, available_tokens: %d, requirements_length: %d",
                 template_tokens, available_tokens, requirements_length)

    # Резерв для ответа (15-20% от общего контекста)
    response_reserve = int(available_tokens * 0.15)

    # Доступно для требований и контекста
    usable_tokens = available_tokens - template_tokens - response_reserve

    logger.debug(f"[calculate_token_budget] Total: {available_tokens}, "
                 f"Prompt: {template_tokens}, Response: {response_reserve}, "
                 f"Usable: {usable_tokens}")

    # Адаптивное распределение в зависимости от размера требований
    if requirements_length > 0:
        req_ratio = requirements_length / usable_tokens

        # Если требования очень короткие (< 15%) - больше контекста
        if req_ratio < 0.15:
            requirements_budget = min(requirements_length + 500, int(usable_tokens * 0.20))
            context_budget = usable_tokens - requirements_budget
            logger.debug("[calculate_token_budget] Strategy: SHORT requirements, MORE context")

        # Если требования длинные (> 40%) - балансируем
        elif req_ratio > 0.40:
            requirements_budget = int(usable_tokens * 0.40)
            context_budget = usable_tokens - requirements_budget
            logger.debug("[calculate_token_budget] Strategy: LONG requirements, balanced")

        # Оптимальное распределение: 25% требования, 75% контекст
        else:
            requirements_budget = int(usable_tokens * 0.25)
            context_budget = usable_tokens - requirements_budget
            logger.debug("[calculate_token_budget] Strategy: OPTIMAL 25/75 split")

    else:
        # Если размер требований неизвестен - стандартное распределение
        requirements_budget = int(usable_tokens * 0.40)
        context_budget = usable_tokens - requirements_budget
        logger.debug("[calculate_token_budget] Strategy: DEFAULT 40/60 split")

    budget = {
        'total': available_tokens,
        'system_prompt': template_tokens,
        'requirements': requirements_budget,
        'rag_context': context_budget,
        'response_reserve': response_reserve,
        'usable': usable_tokens
    }

    logger.debug(f"[calculate_token_budget] -> Final budget: "
                 f"system_prompt={template_tokens} ({template_tokens / available_tokens * 100:.1f}%), "
                 f"requirements={requirements_budget} ({requirements_budget / available_tokens * 100:.1f}%), "
                 f"rag_context={context_budget} ({context_budget / available_tokens * 100:.1f}%), "
                 f"response_reserve={response_reserve} ({response_reserve / available_tokens * 100:.1f}%)")

    return budget


def truncate_smart(text: str, max_tokens: int, preserve_start: bool = True) -> str:
    """
    Умное обрезание текста до заданного количества токенов.

    Args:
        text: Исходный текст
        max_tokens: Максимальное количество токенов
        preserve_start: Если True - сохраняем начало, иначе конец

    Returns:
        Обрезанный текст
    """
    logger.debug("[truncate_smart] <- text length: %d chars", len(text))

    current_tokens = count_tokens(text)

    if current_tokens <= max_tokens:
        return text

    logger.warning(f"[truncate_smart] Truncating from {current_tokens} to {max_tokens} tokens")

    # Грубая оценка: 1 токен ≈ 3 символа для русского текста
    estimated_chars = max_tokens * 3

    if preserve_start:
        # Обрезаем по предложениям с конца
        sentences = text.split('. ')
        truncated = []
        chars_used = 0

        for sentence in sentences:
            sentence_len = len(sentence)
            if chars_used + sentence_len < estimated_chars:
                truncated.append(sentence)
                chars_used += sentence_len
            else:
                break

        result = '. '.join(truncated)
        if result and not result.endswith('.'):
            result += '.'
        result += "\n\n[... текст обрезан ...]"

    else:
        # Сохраняем конец
        result = "[... текст обрезан ...]\n\n" + text[-estimated_chars:]

    # Проверяем фактический размер
    actual_tokens = count_tokens(result)
    logger.info(f"[truncate_smart] -> Result: {actual_tokens} tokens")

    return result


def count_tokens(text: str) -> int:
    """Подсчитывает количество токенов в тексте"""
    if LLM_PROVIDER == "deepseek":
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    else:
        try:
            return len(_encoding.encode(text))
        except Exception as e:
            logger.error("[count_tokens] Error counting tokens: %s", str(e))
            return len(text.split())
