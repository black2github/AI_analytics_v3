# app/agents/requirements_agent.py

"""
LLM-агент для анализа требований к системе ДБО.
Использует современный langchain.agents.create_agent (langchain 1.1.2+)

ФИНАЛЬНАЯ ВЕРСИЯ для langchain 1.1.2 / LangGraph 1.0.4+
"""

import logging
from typing import List, Dict, Any, Optional

# ============================================================================
# ПРАВИЛЬНЫЕ ИМПОРТЫ для langchain 1.1.2 (современная версия)
# ============================================================================
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import Tool

from app.agents.agent_config import (
    AGENT_SYSTEM_PROMPT,
    AGENT_TOOLS_DESCRIPTIONS,
    AGENT_MAX_ITERATIONS
)
from app.agents.agent_tools import (
    search_requirements_tool,
    analyze_page_tool,
    check_template_compliance_tool
)

logger = logging.getLogger(__name__)


class RequirementsAgent:
    """
    Агент-аналитик требований с доступом к RAG и инструментам анализа.

    Использует langchain.agents.create_agent (современный подход)

    Основные возможности:
    - Поиск требований в базе знаний
    - Анализ страниц Confluence
    - Проверка соответствия шаблонам
    - Диалоговое взаимодействие с памятью
    """

    def __init__(
            self,
            llm,
            service_code: Optional[str] = None,
            max_iterations: int = AGENT_MAX_ITERATIONS
    ):
        """
        Инициализация агента.

        Args:
            llm: Языковая модель для агента
            service_code: Код сервиса по умолчанию
            max_iterations: Максимальное количество итераций агента
        """
        logger.info("[RequirementsAgent] Initializing agent with service_code=%s", service_code)

        self.llm = llm
        self.service_code = service_code
        self.max_iterations = max_iterations

        # История диалога (для одной сессии)
        self.chat_history: List[Any] = []

        # Инициализируем инструменты
        self.tools = self._initialize_tools()

        # Создаём агента
        self.agent = self._create_agent()

        logger.info("[RequirementsAgent] Agent initialized with %d tools", len(self.tools))

    def _initialize_tools(self) -> List[Tool]:
        """
        Инициализирует инструменты агента.

        Returns:
            Список инструментов LangChain
        """
        logger.debug("[RequirementsAgent] Initializing tools...")

        tools = [
            Tool(
                name="search_requirements",
                func=search_requirements_tool,
                description=AGENT_TOOLS_DESCRIPTIONS["search_requirements"]["description"]
            ),
            Tool(
                name="analyze_page",
                func=analyze_page_tool,
                description=AGENT_TOOLS_DESCRIPTIONS["analyze_page"]["description"]
            ),
            Tool(
                name="check_template_compliance",
                func=check_template_compliance_tool,
                description=AGENT_TOOLS_DESCRIPTIONS["check_template_compliance"]["description"]
            )
        ]

        logger.debug("[RequirementsAgent] Initialized %d tools", len(tools))
        return tools

    def _create_agent(self):
        """
        Создаёт агента через langchain.agents.create_agent.

        Returns:
            Настроенный агент
        """
        logger.debug("[RequirementsAgent] Creating agent...")

        # Используем современный create_agent из langchain.agents
        # Правильное имя параметра: system_prompt (не state_modifier)
        agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=AGENT_SYSTEM_PROMPT
        )

        logger.debug("[RequirementsAgent] Agent created successfully")
        return agent

    def chat(
            self,
            message: str,
            service_code: Optional[str] = None,
            reset_history: bool = False
    ) -> Dict[str, Any]:
        """
        Отправляет сообщение агенту и получает ответ.

        Args:
            message: Сообщение пользователя
            service_code: Код сервиса (переопределяет дефолтный)
            reset_history: Очистить историю перед ответом

        Returns:
            Словарь с ответом агента и метаданными
        """
        logger.info("[RequirementsAgent] Processing message: '%s'", message[:100])

        if reset_history:
            self.chat_history = []
            logger.debug("[RequirementsAgent] Chat history reset")

        # Используем service_code из параметра или дефолтный
        current_service_code = service_code or self.service_code

        try:
            # Добавляем контекст сервиса в сообщение если нужно
            enhanced_message = message
            if current_service_code:
                enhanced_message = f"[Контекст: сервис {current_service_code}]\n{message}"

            # Создаём список сообщений для агента (системный промпт уже в агенте)
            messages = self.chat_history + [HumanMessage(content=enhanced_message)]

            # Вызываем агента
            result = self.agent.invoke({
                "messages": messages
            })

            # Извлекаем ответ из результата
            # create_agent возвращает {'messages': [...]}
            result_messages = result.get("messages", [])

            # Последнее сообщение - это ответ агента
            if result_messages:
                last_message = result_messages[-1]
                agent_response = last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                agent_response = "Извините, не смог сформировать ответ"

            # Обновляем историю
            self.chat_history.append(HumanMessage(content=message))
            self.chat_history.append(AIMessage(content=agent_response))

            # Извлекаем информацию об использованных инструментах
            tools_used = self._extract_tools_from_messages(result_messages)

            # Формируем структурированный ответ
            response = {
                "response": agent_response,
                "service_code": current_service_code,
                "tools_used": tools_used,
                "chat_history_length": len(self.chat_history)
            }

            logger.info("[RequirementsAgent] Response generated successfully, tools used: %d",
                        len(response["tools_used"]))

            return response

        except Exception as e:
            logger.error("[RequirementsAgent] Error processing message: %s", str(e), exc_info=True)
            return {
                "response": f"Произошла ошибка при обработке запроса: {str(e)}",
                "error": str(e),
                "service_code": current_service_code,
                "tools_used": [],
                "chat_history_length": len(self.chat_history)
            }

    def _extract_tools_from_messages(self, messages: List) -> List[Dict[str, Any]]:
        """
        Извлекает информацию об использованных инструментах из сообщений.

        Args:
            messages: Список сообщений от агента

        Returns:
            Список использованных инструментов с деталями
        """
        tools_used = []

        for msg in messages:
            # Проверяем tool messages
            if hasattr(msg, 'type') and msg.type == 'tool':
                tool_info = {
                    "tool": getattr(msg, 'name', 'unknown'),
                    "input": {},
                    "output_preview": str(msg.content)[:200] + "..." if len(str(msg.content)) > 200 else str(
                        msg.content)
                }
                tools_used.append(tool_info)

            # Также проверяем tool_calls в AI сообщениях
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_info = {
                        "tool": tool_call.get('name', 'unknown'),
                        "input": tool_call.get('args', {}),
                        "output_preview": "Tool called"
                    }
                    tools_used.append(tool_info)

        return tools_used

    def reset_conversation(self):
        """Очищает историю диалога."""
        self.chat_history = []
        logger.info("[RequirementsAgent] Conversation history cleared")

    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        Возвращает краткую сводку текущей сессии.

        Returns:
            Сводка по текущему диалогу
        """
        return {
            "messages_count": len(self.chat_history),
            "service_code": self.service_code,
            "tools_available": [tool.name for tool in self.tools],
            "agent_type": "LangChain Agent (create_agent)"
        }