# app/routes/test_context.py

import logging
from fastapi import APIRouter, HTTPException
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable # Добавлен для типизации LCEL (необязательно)
#from langchain.chains.llm import LLMChain
# from langchain_community.chains import LLMChain # УДАЛЕНО: Заменено на LCEL
from app.llm_interface import get_llm

router = APIRouter(tags=["Тестирование LLM"])

logger = logging.getLogger(__name__)  # Лучше использовать __name__ для именованных логгеров

@router.get("/test_context_size", response_description="Результат тестирования максимального размера контекста для LLM")
async def test_context_size(context_size: int):
    """Тестирует максимальный размер контекста для LLM, генерируя тестовый контекст указанного размера.

    Args:
        context_size: Желаемый размер контекста в символах (query-параметр).

    Returns:
        JSON с результатом вызова LLM или сообщением об ошибке.
    """
    logger.info("[test_context_size] ← context_size=%d", context_size)

    if context_size < 1:
        logging.error("[test_context_size] Invalid context_size: %d", context_size)
        raise HTTPException(status_code=400, detail="context_size должен быть положительным числом")

    try:
        # Генерируем тестовый контекст
        base_text = "Тестовый текст "
        repeat_count = (context_size // len(base_text)) + 1
        context = (base_text * repeat_count)[:context_size]  # Обрезаем до точного размера

        logging.debug("[test_context_size] Generated context length: %d characters", len(context))

        # Получаем LLM
        llm = get_llm()

        # Создаем шаблон промпта
        prompt_template = PromptTemplate(
            input_variables=["requirement", "context"],
            template="Требование: {requirement}\n\nКонтекст: {context}\n\nОтвет:"
        )

        # Создаем цепочку (LCEL)
        chain = prompt_template | llm # ИСПРАВЛЕНО: Замена LLMChain на LCEL

        # Вызываем цепочку
        result = chain.invoke({"requirement": "Тест", "context": context}).content # ИСПРАВЛЕНО: Замена .run() на .invoke().content

        logger.info("[test_context_size] → Success, result length: %d", len(str(result)))
        return {
            "status": "success",
            "context_size": len(context),
            "result": result
        }
    except Exception as e:
        logging.error("[test_context_size] Error with context_size=%d: %s", context_size, str(e))
        raise HTTPException(status_code=500, detail=f"Ошибка при тестировании контекста: {str(e)}")