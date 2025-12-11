# app/llm_interface.py
import logging
from functools import lru_cache
from app.config import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_TEMPERATURE,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL, OLLAMA_API_URL, OLLAMA_API_KEY, KIMI_API_KEY, KIMI_API_URL, GEMINI_API_KEY, XAI_API_KEY,
    XAI_API_URL
)

logger = logging.getLogger(__name__)

def get_llm():
    logger.debug("[get_llm] <-.")
    import os
    current_provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER)  # fallback на импортированное
    llm_model = os.getenv("LLM_MODEL", LLM_MODEL)  # fallback на импортированное
    llm_temperature = os.getenv("LLM_TEMPERATURE", LLM_TEMPERATURE)  # fallback на импортированное

    if current_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("OPENAI_API_KEY")
        )

    elif current_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

    elif current_provider == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_API_URL")
        )

    elif current_provider == "ollama":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("OLLAMA_API_KEY"),
            base_url=os.getenv("OLLAMA_API_URL")
        )

    elif current_provider == "kimi":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("KIMI_API_KEY"),
            base_url=os.getenv("KIMI_API_URL")
        )

    elif current_provider == "gemini":
        # Убедитесь, что установлена библиотека: pip install langchain-google-genai
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not GEMINI_API_KEY:
            # LangChain также проверяет переменную окружения GOOGLE_API_KEY или GEMINI_API_KEY
            # Но явная проверка лучше для отладки.
            raise ValueError("GEMINI_API_KEY is not set for the 'gemini' provider.")

        return ChatGoogleGenerativeAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("GEMINI_API_KEY")
            # API-ключ также может быть установлен через переменную окружения GOOGLE_API_KEY
            # или GEMINI_API_KEY, и тогда 'api_key' не обязателен.
        )

    elif current_provider == "grok":
    #     # Убедитесь, что установлена библиотека: pip install langchain-xai
    #     from langchain_xai import ChatXAI
    #
    #     if not XAI_API_KEY:
    #         raise ValueError("XAI_API_KEY is not set for the 'grok' provider.")
    #
    #     return ChatXAI(
    #         model=llm_model,
    #         temperature=float(llm_temperature),
    #         xai_api_key=XAI_API_KEY
    #     )
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("XAI_API_KEY"),
            base_url=os.getenv("XAI_API_URL")
        )

    raise ValueError(f"Unsupported LLM provider: {current_provider}")


@lru_cache(maxsize=10)
def get_embeddings_model():
    """
    Кеширует модель эмбеддингов для избежания повторной инициализации.

    Returns:
        Кешированный объект модели эмбеддингов
    """
    logger.debug("[get_embeddings_model] <-.")
    if EMBEDDING_PROVIDER == "openai":
        from langchain_community.embeddings import OpenAIEmbeddings
        return OpenAIEmbeddings(api_key=OPENAI_API_KEY)

    elif EMBEDDING_PROVIDER == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    raise ValueError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")


def clear_embeddings_cache():
    """Очистка кеша модели эмбеддингов (например, при изменении конфигурации)"""
    logger.debug("[clear_embeddings_cache] <-.")
    get_embeddings_model.cache_clear()


def get_embeddings_cache_info():
    """Информация о кеше модели эмбеддингов"""
    logger.debug("[get_embeddings_cache_info] <-.")
    return get_embeddings_model.cache_info()