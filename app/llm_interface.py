# app/llm_interface.py

import logging
from functools import lru_cache
from typing import List
from langchain_core.embeddings import Embeddings
from app.config import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_TEMPERATURE,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    EMBEDDING_MODELS_WITH_PREFIXES,
    EMBEDDING_DEVICE,
    EMBEDDING_BATCH_SIZE,
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    OLLAMA_API_URL,
    OLLAMA_API_KEY,
    KIMI_API_KEY,
    KIMI_API_URL,
    GEMINI_API_KEY,
    XAI_API_KEY,
    XAI_API_URL,
)

logger = logging.getLogger(__name__)

# ============================================================================
# КАСТОМНЫЙ КЛАСС ДЛЯ МОДЕЛЕЙ С АСИММЕТРИЧНЫМИ ПРЕФИКСАМИ
# ============================================================================

class PrefixedEmbeddings(Embeddings):
    """
    Обёртка над SentenceTransformer для моделей, требующих task-specific префиксы.

    Такие модели (deepvk/USER2-base, intfloat/multilingual-e5-*) обучены
    кодировать запросы и документы в разных режимах:
    - embed_query()     -> добавляет prefix_query    (например "search_query: ")
    - embed_documents() -> добавляет prefix_document (например "search_document: ")

    Без разных префиксов векторы запросов и документов оказываются в разных
    частях пространства, что деградирует качество retrieval.
    """

    def __init__(
        self,
        model_name: str,
        prefix_query: str = "search_query: ",
        prefix_document: str = "search_document: ",
        normalize_embeddings: bool = True,
        batch_size: int = 32, # на GPU можно увеличить с 32 до 128-256
        device: str = "cpu", # "cuda" для GPU
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for PrefixedEmbeddings. "
                "Install it: pip install sentence-transformers"
            )

        self.model_name = model_name
        self.prefix_query = prefix_query
        self.prefix_document = prefix_document
        self.normalize_embeddings = normalize_embeddings
        self.batch_size = batch_size

        logger.info(
            "[PrefixedEmbeddings] Loading model '%s' on device '%s'",
            model_name, device
        )
        self._model = SentenceTransformer(model_name, device=device)
        logger.info("[PrefixedEmbeddings] Model loaded successfully")

    def embed_query(self, text: str) -> List[float]:
        """
        Кодирует поисковый запрос с префиксом search_query.
        Вызывается ChromaDB при similarity_search().
        """
        prefixed = self.prefix_query + text
        vector = self._model.encode(
            prefixed,
            normalize_embeddings=self.normalize_embeddings,
            batch_size=self.batch_size,
        )
        return vector.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Кодирует тексты документов с префиксом search_document.
        Вызывается ChromaDB при add_documents() во время индексации.
        """
        prefixed = [self.prefix_document + t for t in texts]
        vectors = self._model.encode(
            prefixed,
            normalize_embeddings=self.normalize_embeddings,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return vectors.tolist()


def _model_needs_prefixes(model_name: str) -> bool:
    """
    Проверяет, входит ли модель в список моделей с асимметричными префиксами.
    Список задаётся в config.py через EMBEDDING_MODELS_WITH_PREFIXES.
    """
    known_prefix_models = [
        m.strip() for m in EMBEDDING_MODELS_WITH_PREFIXES.split(",") if m.strip()
    ]
    return model_name in known_prefix_models


# ============================================================================
# ПУБЛИЧНЫЕ ФУНКЦИИ
# ============================================================================

def get_llm(provider=None, model=None, temperature=None):
    logger.debug("[get_llm] <- provider=%s, model=%s, temperature=%s.", provider, model, temperature)
    import os

    provider = provider if provider is not None else os.getenv("LLM_PROVIDER", LLM_PROVIDER)
    llm_model = model if model is not None else os.getenv("LLM_MODEL", LLM_MODEL)
    llm_temperature = temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", LLM_TEMPERATURE)

    logger.info("[get_llm] using LLM_MODEL='%s', LLM_TEMPERATURE='%s'", llm_model, llm_temperature)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_API_URL"),
        )

    elif provider == "ollama":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("OLLAMA_API_KEY"),
            base_url=os.getenv("OLLAMA_API_URL"),
        )

    elif provider == "kimi":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("KIMI_API_KEY"),
            base_url=os.getenv("KIMI_API_URL"),
        )

    elif provider == "gonka":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("GONKA_API_KEY"),
            base_url=os.getenv("GONKA_API_URL"),
        )

    elif provider == "fireworks":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("QWEN_API_KEY"),
            base_url=os.getenv("QWEN_BASE_URL"),
        )

    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=os.getenv("OPENROUTER_BASE_URL"),
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set for the 'gemini' provider.")
        return ChatGoogleGenerativeAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("GEMINI_API_KEY"),
        )

    elif provider == "grok":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=llm_model,
            temperature=float(llm_temperature),
            api_key=os.getenv("XAI_API_KEY"),
            base_url=os.getenv("XAI_API_URL"),
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")


@lru_cache(maxsize=1)
def get_embeddings_model() -> Embeddings:
    """
    Возвращает модель эмбеддингов с учётом типа провайдера и модели.

    Для моделей с асимметричными префиксами (deepvk/USER2-*, multilingual-e5-*)
    возвращает PrefixedEmbeddings, который автоматически добавляет
    'search_query:' при поиске и 'search_document:' при индексации.

    Для остальных моделей (OpenAI, стандартные HuggingFace) возвращает
    стандартный клиент без префиксов.

    Результат кешируется — модель загружается один раз за время жизни процесса.
    Для сброса кеша (например, при смене EMBEDDING_MODEL в runtime) вызвать
    clear_embeddings_cache().
    """
    logger.info(
        "[get_embeddings_model] <- Initializing: provider=%s, model=%s",
        EMBEDDING_PROVIDER, EMBEDDING_MODEL,
    )

    if EMBEDDING_PROVIDER == "openai":
        from langchain_community.embeddings import OpenAIEmbeddings
        logger.info("[get_embeddings_model] Using OpenAI embeddings")
        return OpenAIEmbeddings(api_key=OPENAI_API_KEY)

    elif EMBEDDING_PROVIDER == "huggingface":
        if _model_needs_prefixes(EMBEDDING_MODEL):
            logger.info(
                "[get_embeddings_model] Model '%s' requires asymmetric prefixes — "
                "using PrefixedEmbeddings",
                EMBEDDING_MODEL,
            )
            logger.info(
                "[get_embeddings_model] device=%s, batch_size=%d",
                EMBEDDING_DEVICE, EMBEDDING_BATCH_SIZE,
            )
            return PrefixedEmbeddings(
                model_name=EMBEDDING_MODEL,
                prefix_query="search_query: ",
                prefix_document="search_document: ",
                normalize_embeddings=True,
                batch_size=EMBEDDING_BATCH_SIZE,
                device=EMBEDDING_DEVICE,
            )
        else:
            logger.info(
                "[get_embeddings_model] Model '%s' does not require prefixes — "
                "using standard HuggingFaceEmbeddings",
                EMBEDDING_MODEL,
            )
            from langchain_huggingface import HuggingFaceEmbeddings
            return HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={"device": EMBEDDING_DEVICE},
                encode_kwargs={"normalize_embeddings": True, "batch_size": EMBEDDING_BATCH_SIZE},
            )

    raise ValueError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")


def clear_embeddings_cache() -> None:
    """
    Сбрасывает кеш модели эмбеддингов.
    Вызывать при смене EMBEDDING_MODEL или EMBEDDING_PROVIDER в runtime
    (например, через /config endpoint).
    """
    logger.info("[clear_embeddings_cache] Clearing embeddings model cache")
    get_embeddings_model.cache_clear()


def get_embeddings_cache_info():
    """Возвращает статистику lru_cache для модели эмбеддингов."""
    return get_embeddings_model.cache_info()