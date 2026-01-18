# tests/test_agent.py

"""
Юнит-тесты для LLM-агента аналитика требований.
Запуск: pytest tests/test_agent.py -v
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock


# Тесты для инструментов
class TestAgentTools:
    """Тесты для инструментов агента"""

    @patch('app.agents.agent_tools.search_documents')
    @patch('app.agents.agent_tools.resolve_service_code_by_user')
    def test_search_requirements_tool_success(self, mock_resolve, mock_search):
        """Тест успешного поиска требований"""
        from app.agents.agent_tools import search_requirements_tool

        # Mock данные
        mock_resolve.return_value = "SBP"
        mock_doc = Mock()
        mock_doc.page_content = "Test requirement content"
        mock_doc.metadata = {
            "page_id": "123456",
            "title": "Test Page",
            "requirement_type": "FR",
            "is_platform": False,
            "service_code": "SBP"
        }
        mock_search.return_value = [mock_doc]

        # Вызов
        result = search_requirements_tool(query="test query", service_code="SBP")

        # Проверки
        assert result is not None
        result_dict = json.loads(result)
        assert result_dict["success"] is True
        assert result_dict["results_count"] == 1
        assert result_dict["results"][0]["page_id"] == "123456"

    @patch('app.agents.agent_tools.search_documents')
    def test_search_requirements_tool_no_results(self, mock_search):
        """Тест поиска без результатов"""
        from app.agents.agent_tools import search_requirements_tool

        mock_search.return_value = []

        result = search_requirements_tool(query="nonexistent")
        result_dict = json.loads(result)

        assert result_dict["success"] is False
        assert "не найдены" in result_dict["message"]

    @patch('app.agents.agent_tools.analyze_pages')
    def test_analyze_page_tool_success(self, mock_analyze):
        """Тест успешного анализа страницы"""
        from app.agents.agent_tools import analyze_page_tool

        # Mock данные
        mock_analyze.return_value = [{
            "page_id": "123456",
            "analysis": "Test analysis result",
            "token_usage": {"total": 1000}
        }]

        result = analyze_page_tool(page_id="123456", service_code="SBP")
        result_dict = json.loads(result)

        assert result_dict["success"] is True
        assert result_dict["page_id"] == "123456"
        assert "analysis" in result_dict

    @patch('app.agents.agent_tools.analyze_with_templates')
    def test_check_template_compliance_tool_success(self, mock_check):
        """Тест успешной проверки соответствия шаблону"""
        from app.agents.agent_tools import check_template_compliance_tool

        mock_check.return_value = [{
            "page_id": "123456",
            "requirement_type": "FR",
            "template_analysis": {"compliance": "good"},
            "legacy_formatting_issues": []
        }]

        result = check_template_compliance_tool(
            page_id="123456",
            requirement_type="FR",
            service_code="SBP"
        )
        result_dict = json.loads(result)

        assert result_dict["success"] is True
        assert result_dict["requirement_type"] == "FR"


# Тесты для агента
class TestRequirementsAgent:
    """Тесты для класса RequirementsAgent"""

    @pytest.fixture
    def mock_llm(self):
        """Фикстура для мока LLM"""
        llm = Mock()
        llm.invoke = Mock(return_value="Test response")
        return llm

    @pytest.fixture
    def agent(self, mock_llm):
        """Фикстура для создания агента с моками"""
        with patch('app.agents.requirements_agent.create_openai_functions_agent'):
            with patch('app.agents.requirements_agent.AgentExecutor'):
                from app.agents.requirements_agent import RequirementsAgent
                agent = RequirementsAgent(llm=mock_llm, service_code="SBP")
                return agent

    def test_agent_initialization(self, agent):
        """Тест инициализации агента"""
        assert agent is not None
        assert agent.service_code == "SBP"
        assert len(agent.tools) == 3
        assert agent.chat_history == []

    def test_agent_tools_list(self, agent):
        """Тест списка инструментов агента"""
        tool_names = [tool.name for tool in agent.tools]

        assert "search_requirements" in tool_names
        assert "analyze_page" in tool_names
        assert "check_template_compliance" in tool_names

    def test_reset_conversation(self, agent):
        """Тест сброса истории диалога"""
        # Добавляем несколько сообщений
        agent.chat_history = ["message1", "message2", "message3"]

        # Сбрасываем
        agent.reset_conversation()

        assert len(agent.chat_history) == 0

    def test_get_conversation_summary(self, agent):
        """Тест получения сводки диалога"""
        summary = agent.get_conversation_summary()

        assert "messages_count" in summary
        assert "service_code" in summary
        assert "tools_available" in summary
        assert summary["service_code"] == "SBP"
        assert len(summary["tools_available"]) == 3


# Интеграционные тесты для API
class TestAgentAPI:
    """Интеграционные тесты для API endpoints"""

    @pytest.fixture
    def mock_agent(self):
        """Мок агента для тестирования API"""
        agent = Mock()
        agent.chat = Mock(return_value={
            "response": "Test response",
            "service_code": "SBP",
            "tools_used": [],
            "chat_history_length": 2
        })
        agent.reset_conversation = Mock()
        agent.get_conversation_summary = Mock(return_value={
            "messages_count": 0,
            "service_code": "SBP",
            "tools_available": ["search", "analyze", "check"]
        })
        return agent

    @patch('app.routes.agent.get_agent_instance')
    def test_chat_endpoint_success(self, mock_get_agent, mock_agent):
        """Тест успешного запроса к /agent/chat"""
        from fastapi.testclient import TestClient
        from app.main import app  # Предполагается, что есть main.py

        mock_get_agent.return_value = mock_agent
        client = TestClient(app)

        response = client.post("/api/agent/chat", json={
            "message": "Test message",
            "service_code": "SBP",
            "reset_history": False
        })

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["service_code"] == "SBP"

    @patch('app.routes.agent.get_agent_instance')
    def test_reset_endpoint(self, mock_get_agent, mock_agent):
        """Тест endpoint для сброса истории"""
        from fastapi.testclient import TestClient
        from app.main import app

        mock_get_agent.return_value = mock_agent
        client = TestClient(app)

        response = client.post("/api/agent/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_info_endpoint(self):
        """Тест endpoint с информацией об агенте"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/agent/info")

        assert response.status_code == 200
        data = response.json()
        assert "capabilities" in data

    def test_tools_endpoint(self):
        """Тест endpoint со списком инструментов"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/agent/tools")

        assert response.status_code == 200
        data = response.json()
        assert "tools_count" in data
        assert data["tools_count"] == 3


# Тесты конфигурации
class TestAgentConfig:
    """Тесты конфигурации агента"""

    def test_system_prompt_exists(self):
        """Тест наличия системного промпта"""
        from app.agents.agent_config import AGENT_SYSTEM_PROMPT

        assert AGENT_SYSTEM_PROMPT is not None
        assert len(AGENT_SYSTEM_PROMPT) > 100
        assert "аналитик" in AGENT_SYSTEM_PROMPT.lower()

    def test_tools_descriptions_complete(self):
        """Тест полноты описаний инструментов"""
        from app.agents.agent_config import AGENT_TOOLS_DESCRIPTIONS

        required_tools = [
            "search_requirements",
            "analyze_page",
            "check_template_compliance"
        ]

        for tool in required_tools:
            assert tool in AGENT_TOOLS_DESCRIPTIONS
            assert "description" in AGENT_TOOLS_DESCRIPTIONS[tool]
            assert "parameters" in AGENT_TOOLS_DESCRIPTIONS[tool]

    def test_config_defaults(self):
        """Тест дефолтных значений конфигурации"""
        from app.agents.agent_config import (
            AGENT_MAX_ITERATIONS,
            AGENT_TEMPERATURE
        )

        assert AGENT_MAX_ITERATIONS > 0
        assert 0 <= AGENT_TEMPERATURE <= 1


# Запуск тестов
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])