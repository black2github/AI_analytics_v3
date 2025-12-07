# tests/test_config_endpoint.py

import pytest
import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_env():
    """Сброс переменных окружения перед каждым тестом"""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


class TestGetConfig:
    """Тесты для GET /config"""

    def test_get_config_default_values(self):
        """Тест получения конфигурации со значениями по умолчанию"""
        response = client.get("/config")

        assert response.status_code == 200
        config = response.json()

        assert "LLM_PROVIDER" in config
        assert "LLM_MODEL" in config
        assert "LLM_TEMPERATURE" in config
        assert "IS_ENTITY_NAMES_CONTEXT" in config
        assert "IS_SERVICE_DOCS_CONTEXT" in config
        assert "IS_PLATFORM_DOCS_CONTEXT" in config
        assert "IS_SERVICE_LINKS_CONTEXT" in config

    def test_get_config_custom_values(self):
        """Тест получения конфигурации с кастомными значениями"""
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["LLM_MODEL"] = "claude-3-5-sonnet"
        os.environ["LLM_TEMPERATURE"] = "0.7"

        response = client.get("/config")

        assert response.status_code == 200
        config = response.json()

        assert config["LLM_PROVIDER"] == "anthropic"
        assert config["LLM_MODEL"] == "claude-3-5-sonnet"
        assert config["LLM_TEMPERATURE"] == "0.7"


class TestUpdateConfig:
    """Тесты для POST /config"""

    def test_update_llm_provider(self):
        """Тест изменения провайдера LLM"""
        response = client.post(
            "/config",
            json={"LLM_PROVIDER": "deepseek"}
        )

        assert response.status_code == 200
        result = response.json()

        assert "previous_values" in result
        assert "current_values" in result
        assert "message" in result

        assert result["current_values"]["LLM_PROVIDER"] == "deepseek"
        assert "LLM_PROVIDER" in result["message"]

    def test_update_llm_model(self):
        """Тест изменения модели LLM"""
        response = client.post(
            "/config",
            json={"LLM_MODEL": "deepseek-chat"}
        )

        assert response.status_code == 200
        result = response.json()

        assert result["current_values"]["LLM_MODEL"] == "deepseek-chat"

    def test_update_llm_temperature(self):
        """Тест изменения температуры LLM"""
        response = client.post(
            "/config",
            json={"LLM_TEMPERATURE": "0.5"}
        )

        assert response.status_code == 200
        result = response.json()

        assert result["current_values"]["LLM_TEMPERATURE"] == "0.5"

    def test_update_boolean_flags(self):
        """Тест изменения булевых флагов"""
        response = client.post(
            "/config",
            json={
                "IS_ENTITY_NAMES_CONTEXT": False,
                "IS_SERVICE_DOCS_CONTEXT": False
            }
        )

        assert response.status_code == 200
        result = response.json()

        assert result["current_values"]["IS_ENTITY_NAMES_CONTEXT"] is False
        assert result["current_values"]["IS_SERVICE_DOCS_CONTEXT"] is False

    def test_update_multiple_parameters(self):
        """Тест изменения нескольких параметров одновременно"""
        response = client.post(
            "/config",
            json={
                "LLM_PROVIDER": "anthropic",
                "LLM_MODEL": "claude-3-5-sonnet",
                "LLM_TEMPERATURE": "0.3",
                "IS_PLATFORM_DOCS_CONTEXT": False
            }
        )

        assert response.status_code == 200
        result = response.json()

        assert result["current_values"]["LLM_PROVIDER"] == "anthropic"
        assert result["current_values"]["LLM_MODEL"] == "claude-3-5-sonnet"
        assert result["current_values"]["LLM_TEMPERATURE"] == "0.3"
        assert result["current_values"]["IS_PLATFORM_DOCS_CONTEXT"] is False

    def test_update_preserves_unchanged_values(self):
        """Тест что неизмененные параметры сохраняются"""
        # Устанавливаем начальные значения
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["LLM_MODEL"] = "gpt-4o"

        # Изменяем только температуру
        response = client.post(
            "/config",
            json={"LLM_TEMPERATURE": "0.8"}
        )

        assert response.status_code == 200
        result = response.json()

        # Провайдер и модель не должны измениться
        assert result["current_values"]["LLM_PROVIDER"] == "openai"
        assert result["current_values"]["LLM_MODEL"] == "gpt-4o"
        assert result["current_values"]["LLM_TEMPERATURE"] == "0.8"

    def test_update_returns_previous_values(self):
        """Тест что возвращаются предыдущие значения"""
        # Устанавливаем начальное значение
        os.environ["LLM_PROVIDER"] = "openai"

        response = client.post(
            "/config",
            json={"LLM_PROVIDER": "deepseek"}
        )

        assert response.status_code == 200
        result = response.json()

        assert result["previous_values"]["LLM_PROVIDER"] == "openai"
        assert result["current_values"]["LLM_PROVIDER"] == "deepseek"

    def test_update_no_changes(self):
        """Тест когда значения не изменились"""
        os.environ["LLM_PROVIDER"] = "deepseek"

        response = client.post(
            "/config",
            json={"LLM_PROVIDER": "deepseek"}
        )

        assert response.status_code == 200
        result = response.json()

        assert "No configuration changes" in result["message"]


class TestConfigValidation:
    """Тесты валидации конфигурации"""

    def test_invalid_llm_provider(self):
        """Тест невалидного провайдера LLM"""
        response = client.post(
            "/config",
            json={"LLM_PROVIDER": "invalid_provider"}
        )

        assert response.status_code == 400
        assert "Invalid LLM_PROVIDER" in response.json()["detail"]

    def test_invalid_temperature_too_high(self):
        """Тест слишком высокой температуры"""
        response = client.post(
            "/config",
            json={"LLM_TEMPERATURE": "2.0"}
        )

        assert response.status_code == 400
        assert "Invalid LLM_TEMPERATURE" in response.json()["detail"]

    def test_invalid_temperature_negative(self):
        """Тест отрицательной температуры"""
        response = client.post(
            "/config",
            json={"LLM_TEMPERATURE": "-0.5"}
        )

        assert response.status_code == 400
        assert "Invalid LLM_TEMPERATURE" in response.json()["detail"]

    def test_invalid_temperature_not_number(self):
        """Тест нечисловой температуры"""
        response = client.post(
            "/config",
            json={"LLM_TEMPERATURE": "not_a_number"}
        )

        assert response.status_code == 400
        assert "Invalid LLM_TEMPERATURE" in response.json()["detail"]

    def test_empty_model_name(self):
        """Тест пустого имени модели"""
        response = client.post(
            "/config",
            json={"LLM_MODEL": ""}
        )

        assert response.status_code == 400
        assert "LLM_MODEL cannot be empty" in response.json()["detail"]

    def test_whitespace_only_model_name(self):
        """Тест имени модели из пробелов"""
        response = client.post(
            "/config",
            json={"LLM_MODEL": "   "}
        )

        assert response.status_code == 400
        assert "LLM_MODEL cannot be empty" in response.json()["detail"]


class TestConfigPersistence:
    """Тесты персистентности конфигурации"""

    def test_config_persists_across_requests(self):
        """Тест что конфигурация сохраняется между запросами"""
        # Изменяем конфигурацию
        client.post(
            "/config",
            json={"LLM_PROVIDER": "anthropic"}
        )

        # Проверяем что изменение сохранилось
        response = client.get("/config")
        config = response.json()

        assert config["LLM_PROVIDER"] == "anthropic"

    def test_multiple_sequential_updates(self):
        """Тест последовательных обновлений"""
        # Первое обновление
        response1 = client.post(
            "/config",
            json={"LLM_PROVIDER": "deepseek"}
        )
        assert response1.status_code == 200

        # Второе обновление
        response2 = client.post(
            "/config",
            json={"LLM_MODEL": "deepseek-chat"}
        )
        assert response2.status_code == 200

        # Проверяем что оба изменения применились
        response = client.get("/config")
        config = response.json()

        assert config["LLM_PROVIDER"] == "deepseek"
        assert config["LLM_MODEL"] == "deepseek-chat"


class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_empty_request_body(self):
        """Тест пустого тела запроса"""
        response = client.post(
            "/config",
            json={}
        )

        assert response.status_code == 200
        result = response.json()
        assert "No configuration changes" in result["message"]

    def test_valid_temperature_boundaries(self):
        """Тест граничных значений температуры"""
        # Минимальное значение
        response1 = client.post(
            "/config",
            json={"LLM_TEMPERATURE": "0.0"}
        )
        assert response1.status_code == 200

        # Максимальное значение
        response2 = client.post(
            "/config",
            json={"LLM_TEMPERATURE": "1.0"}
        )
        assert response2.status_code == 200

    def test_boolean_string_conversion(self):
        """Тест конвертации булевых значений в строки"""
        response = client.post(
            "/config",
            json={"IS_ENTITY_NAMES_CONTEXT": True}
        )

        assert response.status_code == 200

        # Проверяем что в environment переменной установлена строка
        assert os.getenv("IS_ENTITY_NAMES_CONTEXT") == "true"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])