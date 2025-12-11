# app/routes/agent.py

"""
API endpoints для взаимодействия с LLM-агентом аналитика требований.
"""

import logging
import anyio
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from anyio import to_thread

from app.agents.requirements_agent import RequirementsAgent
from app.agents.agent_config import AGENT_MODEL, AGENT_TEMPERATURE

logger = logging.getLogger(__name__)
router = APIRouter()

# Глобальный экземпляр агента (в продакшене можно использовать session-based подход)
_agent_instance: Optional[RequirementsAgent] = None


# ============================================================================
# МОДЕЛИ ДАННЫХ
# ============================================================================

class ChatRequest(BaseModel):
    """Запрос для чата с агентом"""
    message: str = Field(..., description="Сообщение пользователя", min_length=1)
    service_code: Optional[str] = Field(None, description="Код сервиса (опционально)")
    reset_history: bool = Field(False, description="Очистить историю перед ответом")
    session_id: Optional[str] = Field(None, description="ID сессии (для будущей реализации)")


class ChatResponse(BaseModel):
    """Ответ от агента"""
    response: str = Field(..., description="Ответ агента")
    service_code: Optional[str] = Field(None, description="Используемый код сервиса")
    tools_used: list = Field(default_factory=list, description="Использованные инструменты")
    chat_history_length: int = Field(..., description="Количество сообщений в истории")
    error: Optional[str] = Field(None, description="Ошибка если была")


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def get_agent_instance(service_code: Optional[str] = None) -> RequirementsAgent:
    """
    Получает или создаёт глобальный экземпляр агента.

    Args:
        service_code: Код сервиса по умолчанию

    Returns:
        Экземпляр RequirementsAgent
    """
    global _agent_instance

    if _agent_instance is None:
        logger.info("[get_agent_instance] Creating new agent instance")

        # Импортируем LLM
        from app.llm_interface import get_llm

        # Создаём LLM для агента
        # llm = get_llm(
        #     model_name=AGENT_MODEL,
        #     temperature=AGENT_TEMPERATURE
        # )
        llm = get_llm()

        # Создаём агента
        _agent_instance = RequirementsAgent(
            llm=llm,
            service_code=service_code
        )

        logger.info("[get_agent_instance] Agent instance created successfully")

    return _agent_instance


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/agent/chat", response_model=ChatResponse, tags=["Агент-аналитик"])
async def agent_chat(request: ChatRequest):
    """
    Чат с агентом-аналитиком требований.

    Агент может:
    - Искать требования в базе знаний (поиск по ключевым словам)
    - Анализировать конкретные страницы Confluence
    - Проверять соответствие требований шаблонам
    - Отвечать на вопросы о требованиях

    **Примеры запросов:**
    - "Найди требования по СБП"
    - "Проанализируй страницу 274628758"
    - "Какие есть функциональные требования к авторизации?"
    - "Проверь соответствие страницы 123456 шаблону FR"

    **Особенности:**
    - Агент помнит историю диалога в рамках сессии
    - Можно сбросить историю установив reset_history=true
    - Агент автоматически выбирает нужные инструменты

    Args:
        message: Сообщение пользователя
        service_code: Код сервиса (опционально, например "SBP")
        reset_history: Очистить историю диалога перед ответом
        session_id: ID сессии (зарезервировано для будущего)

    Returns:
        Ответ агента с использованными инструментами

    Example:
        ```json
        {
            "message": "Найди требования по авторизации",
            "service_code": "SBP",
            "reset_history": false
        }
        ```
    """
    logger.info("[agent_chat] <- message='%s', service_code=%s, reset_history=%s",
                request.message[:100], request.service_code, request.reset_history)

    try:
        # Получаем агента
        agent = get_agent_instance(request.service_code)

        # Запускаем в thread pool (агент может выполнять долгие операции)
        result = await anyio.to_thread.run_sync(
            agent.chat,
            request.message,
            request.service_code,
            request.reset_history
        )

        logger.info("[agent_chat] -> Response generated, tools_used: %d",
                    len(result.get("tools_used", [])))

        return ChatResponse(
            response=result.get("response", "Ошибка формирования ответа"),
            service_code=result.get("service_code"),
            tools_used=result.get("tools_used", []),
            chat_history_length=result.get("chat_history_length", 0),
            error=result.get("error")
        )

    except Exception as e:
        logger.error("[agent_chat] Error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка агента: {str(e)}")


@router.post("/agent/reset", tags=["Агент-аналитик"])
async def agent_reset():
    """
    Сброс истории диалога агента.

    Очищает всю историю текущей сессии.
    Используйте это если хотите начать новый диалог с чистого листа.

    Returns:
        Статус сброса
    """
    logger.info("[agent_reset] <- Resetting agent conversation")

    try:
        agent = get_agent_instance()

        await anyio.to_thread.run_sync(agent.reset_conversation)

        logger.info("[agent_reset] -> Conversation reset successful")

        return {
            "status": "success",
            "message": "История диалога очищена"
        }

    except Exception as e:
        logger.error("[agent_reset] Error: %s", str(e), exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/agent/info", tags=["Агент-аналитик"])
async def agent_info():
    """
    Информация об агенте и текущей сессии.

    Возвращает:
    - Количество сообщений в текущей сессии
    - Доступные инструменты
    - Настройки агента

    Returns:
        Информация о состоянии агента
    """
    logger.info("[agent_info] <- Getting agent info")

    try:
        agent = get_agent_instance()

        summary = await anyio.to_thread.run_sync(agent.get_conversation_summary)

        return {
            "status": "active",
            "model": AGENT_MODEL,
            "temperature": AGENT_TEMPERATURE,
            "session": summary,
            "capabilities": [
                "Поиск требований в базе знаний",
                "Анализ страниц Confluence",
                "Проверка соответствия шаблонам",
                "Диалоговое взаимодействие с поддержанием контекста"
            ]
        }

    except Exception as e:
        logger.error("[agent_info] Error: %s", str(e))
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/agent/tools", tags=["Агент-аналитик"])
async def agent_tools():
    """
    Список доступных инструментов агента.

    Возвращает подробную информацию о каждом инструменте:
    - Название
    - Описание
    - Параметры

    Returns:
        Список инструментов с описаниями
    """
    from app.agents.agent_config import AGENT_TOOLS_DESCRIPTIONS
    logger.info("[agent_tools] <- Getting agent tools")

    return {
        "tools_count": len(AGENT_TOOLS_DESCRIPTIONS),
        "tools": AGENT_TOOLS_DESCRIPTIONS
    }