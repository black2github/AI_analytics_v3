# app/config_endpoint.py

import logging
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()


class ConfigUpdateRequest(BaseModel):
    """Модель запроса на обновление конфигурации"""
    LLM_PROVIDER: Optional[str] = Field(None, description="Провайдер LLM (openai, anthropic, deepseek)")
    LLM_MODEL: Optional[str] = Field(None, description="Модель LLM")
    LLM_TEMPERATURE: Optional[str] = Field(None, description="Температура для LLM (0.0-1.0)")
    IS_ENTITY_NAMES_CONTEXT: Optional[bool] = Field(None, description="Использовать контекст имен сущностей")
    IS_SERVICE_DOCS_CONTEXT: Optional[bool] = Field(None, description="Использовать контекст документации сервиса")
    IS_PLATFORM_DOCS_CONTEXT: Optional[bool] = Field(None, description="Использовать контекст документации платформы")
    IS_SERVICE_LINKS_CONTEXT: Optional[bool] = Field(None, description="Использовать контекст ссылок сервиса")


class ConfigResponse(BaseModel):
    """Модель ответа с предыдущими значениями конфигурации"""
    previous_values: Dict[str, Any] = Field(..., description="Предыдущие значения параметров")
    current_values: Dict[str, Any] = Field(..., description="Текущие значения параметров")
    message: str = Field(..., description="Сообщение о результате операции")


def get_current_config() -> Dict[str, Any]:
    """Получает текущие значения конфигурационных параметров"""
    return {
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "deepseek"),
        "LLM_MODEL": os.getenv("LLM_MODEL", "deepseek-chat"),
        "LLM_TEMPERATURE": os.getenv("LLM_TEMPERATURE", "0.0"),
        "IS_ENTITY_NAMES_CONTEXT": os.getenv("IS_ENTITY_NAMES_CONTEXT", "true").lower() == "true",
        "IS_SERVICE_DOCS_CONTEXT": os.getenv("IS_SERVICE_DOCS_CONTEXT", "true").lower() == "true",
        "IS_PLATFORM_DOCS_CONTEXT": os.getenv("IS_PLATFORM_DOCS_CONTEXT", "true").lower() == "true",
        "IS_SERVICE_LINKS_CONTEXT": os.getenv("IS_SERVICE_LINKS_CONTEXT", "true").lower() == "true"
    }


def validate_config_values(config: ConfigUpdateRequest) -> None:
    """Валидация значений конфигурации"""

    # Валидация LLM_PROVIDER
    if config.LLM_PROVIDER is not None:
        # openai | anthropic | deepseek | ollama | kimi | gemini | grok
        valid_providers = ["openai", "anthropic", "deepseek", "ollama", "kimi", "gemini", "grok"]
        if config.LLM_PROVIDER not in valid_providers:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid LLM_PROVIDER. Must be one of: {', '.join(valid_providers)}"
            )

    # Валидация LLM_TEMPERATURE
    if config.LLM_TEMPERATURE is not None:
        try:
            temp = float(config.LLM_TEMPERATURE)
            if not (0.0 <= temp <= 1.0):
                raise ValueError()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid LLM_TEMPERATURE. Must be a number between 0.0 and 1.0"
            )

    # Валидация LLM_MODEL (базовая проверка - не пустая строка)
    if config.LLM_MODEL is not None:
        if not config.LLM_MODEL.strip():
            raise HTTPException(
                status_code=400,
                detail="LLM_MODEL cannot be empty"
            )


def update_environment_variables(config: ConfigUpdateRequest) -> None:
    """Обновляет переменные окружения на основе переданных значений"""

    # Обновляем строковые параметры
    if config.LLM_PROVIDER is not None:
        os.environ["LLM_PROVIDER"] = config.LLM_PROVIDER
        logger.info("Updated LLM_PROVIDER to: %s", config.LLM_PROVIDER)

    if config.LLM_MODEL is not None:
        os.environ["LLM_MODEL"] = config.LLM_MODEL
        logger.info("Updated LLM_MODEL to: %s", config.LLM_MODEL)

    if config.LLM_TEMPERATURE is not None:
        os.environ["LLM_TEMPERATURE"] = config.LLM_TEMPERATURE
        logger.info("Updated LLM_TEMPERATURE to: %s", config.LLM_TEMPERATURE)

    # Обновляем булевы параметры
    if config.IS_ENTITY_NAMES_CONTEXT is not None:
        os.environ["IS_ENTITY_NAMES_CONTEXT"] = str(config.IS_ENTITY_NAMES_CONTEXT).lower()
        logger.info("Updated IS_ENTITY_NAMES_CONTEXT to: %s", config.IS_ENTITY_NAMES_CONTEXT)

    if config.IS_SERVICE_DOCS_CONTEXT is not None:
        os.environ["IS_SERVICE_DOCS_CONTEXT"] = str(config.IS_SERVICE_DOCS_CONTEXT).lower()
        logger.info("Updated IS_SERVICE_DOCS_CONTEXT to: %s", config.IS_SERVICE_DOCS_CONTEXT)

    if config.IS_PLATFORM_DOCS_CONTEXT is not None:
        os.environ["IS_PLATFORM_DOCS_CONTEXT"] = str(config.IS_PLATFORM_DOCS_CONTEXT).lower()
        logger.info("Updated IS_PLATFORM_DOCS_CONTEXT to: %s", config.IS_PLATFORM_DOCS_CONTEXT)

    if config.IS_SERVICE_LINKS_CONTEXT is not None:
        os.environ["IS_SERVICE_LINKS_CONTEXT"] = str(config.IS_SERVICE_LINKS_CONTEXT).lower()
        logger.info("Updated IS_SERVICE_LINKS_CONTEXT to: %s", config.IS_SERVICE_LINKS_CONTEXT)


def reload_config_module() -> None:
    """Перезагружает модуль конфигурации для применения новых значений"""
    try:
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        logger.info("Configuration module reloaded successfully")

        # КРИТИЧНО: Очищаем кеш эмбеддингов если изменилась конфигурация
        try:
            from app.llm_interface import clear_embeddings_cache
            clear_embeddings_cache()
            logger.info("Embeddings cache cleared successfully")
        except Exception as cache_err:
            logger.warning("Failed to clear embeddings cache: %s", str(cache_err))

    except Exception as e:
        logger.error("Failed to reload configuration module: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload configuration: {str(e)}"
        )


@router.post("/config", response_model=ConfigResponse)
async def update_config(config: ConfigUpdateRequest) -> ConfigResponse:
    """
    Обновляет конфигурацию сервиса путем изменения переменных окружения.

    Параметры, которые не указаны в запросе, остаются неизменными.

    Возвращает предыдущие и текущие значения всех параметров конфигурации.

    Args:
        config: Объект с новыми значениями конфигурационных параметров

    Returns:
        ConfigResponse с предыдущими и текущими значениями конфигурации

    Raises:
        HTTPException: При ошибке валидации или применения конфигурации

    Example:
        ```bash
        curl -X POST "http://localhost:8000/config" \\
          -H "Content-Type: application/json" \\
          -d '{"LLM_PROVIDER": "deepseek", "LLM_MODEL": "deepseek-chat"}'
        ```
    """
    logger.info("Received config update request: %s", config.model_dump(exclude_none=True))

    try:
        # Получаем текущие значения до изменения
        previous_values = get_current_config()

        # Валидируем новые значения
        validate_config_values(config)

        # Обновляем переменные окружения
        update_environment_variables(config)

        # Перезагружаем модуль конфигурации
        reload_config_module()

        # Получаем новые значения после изменения
        current_values = get_current_config()

        # Формируем список измененных параметров
        changed_params = [
            key for key in current_values.keys()
            if previous_values[key] != current_values[key]
        ]

        if changed_params:
            message = f"Configuration updated successfully. Changed parameters: {', '.join(changed_params)}"
        else:
            message = "No configuration changes were made (all values were already set)"

        logger.info(message)

        return ConfigResponse(
            previous_values=previous_values,
            current_values=current_values,
            message=message
        )

    except HTTPException:
        # Пробрасываем HTTP исключения как есть
        raise
    except Exception as e:
        logger.exception("Unexpected error during config update: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update configuration: {str(e)}"
        )


@router.get("/config", response_model=Dict[str, Any])
async def get_config() -> Dict[str, Any]:
    """
    Получает текущие значения конфигурации сервиса.

    Returns:
        Словарь с текущими значениями всех конфигурационных параметров

    Example:
        ```bash
        curl -X GET "http://localhost:8000/config"
        ```
    """
    logger.info("Received config retrieval request")

    try:
        current_config = get_current_config()
        logger.info("Current configuration retrieved successfully")
        return current_config
    except Exception as e:
        logger.exception("Failed to retrieve configuration: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve configuration: {str(e)}"
        )