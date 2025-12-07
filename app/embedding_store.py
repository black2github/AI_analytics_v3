# app/embedding_store.py

import logging
import os
import time
from pprint import pformat

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter  # FIXED IMPORT
from app.config import (
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    OPENAI_API_KEY,
    UNIFIED_STORAGE_NAME,
    CHUNK_MAX_PAGE_SIZE,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_MODE
)
from app.service_registry import get_platform_status

logger = logging.getLogger(__name__)

# ====================================================================
# ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ ДЛЯ КЭШИРОВАНИЯ МОДЕЛИ В ПАМЯТИ
# ====================================================================
_embedding_model_cache = None


def get_embedding_model(name: str = EMBEDDING_MODEL, use_offline: bool = False) -> Embeddings:
    """
    Получает embedding модель с кэширование и детальным логированием.

    Args:
        name: Имя модели (по умолчанию из config)
        use_offline: Если True, использует только локальный кэш без обращения к сети.
            Устанавливает переменные окружения, которые затем читают библиотеки загрузки.

    Returns:
        Embeddings: Модель для создания эмбеддингов
    """
    global _embedding_model_cache

    # ===== ШАГ 1: ПРОВЕРКА КЭША В ПАМЯТИ =====
    if _embedding_model_cache is not None:
        logger.debug("[get_embedding_model] Returning cached model from memory")
        return _embedding_model_cache

    logger.info("[get_embedding_model] Starting model initialization: provider=%s, model=%s",
                EMBEDDING_PROVIDER, name)

    # ===== ШАГ 2: ПРОВЕРКА ЛОКАЛЬНОГО КЭША HUGGINGFACE =====
    cache_dir = os.path.expanduser("~/.cache/huggingface/")
    logger.info("[get_embedding_model] HuggingFace cache directory: %s", cache_dir)
    logger.info("[get_embedding_model] Cache exists: %s", os.path.exists(cache_dir))

    # ===== ШАГ 3: НАСТРОЙКА ОФЛАЙН-РЕЖИМА =====
    # Если use_offline=True или переменная окружения установлена - работаем только с кэшем
    original_transformers_offline = os.environ.get('TRANSFORMERS_OFFLINE')
    original_hf_hub_offline = os.environ.get('HF_HUB_OFFLINE')

    # НАСТРОЙКА ПЕРЕМЕННЫХ ДЛЯ БИБЛИОТЕК
    if use_offline:
        logger.info("[get_embedding_model] Using OFFLINE mode - will only use local cache")
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_OFFLINE'] = '1'

    # ===== ШАГ 4: ЗАГРУЗКА МОДЕЛИ =====
    try:
        if EMBEDDING_PROVIDER == "openai":
            logger.info("[get_embedding_model] Loading OpenAI embeddings...")
            from langchain_community.embeddings import OpenAIEmbeddings
            model = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
            dim = 1536  # Фиксированная размерность для OpenAI
            logger.info("[get_embedding_model] OpenAI model loaded successfully")

        elif EMBEDDING_PROVIDER == "huggingface":
            logger.info("[get_embedding_model] Loading HuggingFace model: %s", EMBEDDING_MODEL)

            if use_offline:
                logger.info("[get_embedding_model] Offline mode: loading from cache only")
            else:
                logger.info("[get_embedding_model] Online mode: will download if not cached (1-5 min)")

            from langchain_huggingface import HuggingFaceEmbeddings

            start_time = time.time()

            # Создаем модель с оптимальными параметрами
            # (библиотека читает переменные окружения и для кэширования)
            model = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={
                    'device': 'cpu',  # Используем CPU (для GPU поставьте 'cuda')
                },
                encode_kwargs={
                    'normalize_embeddings': True,  # Нормализация для косинусного сходства
                    'batch_size': 32  # Размер батча для обработки
                }
            )

            elapsed = time.time() - start_time
            logger.info("[get_embedding_model] Model loaded in %.2f seconds", elapsed)

            # Тестовое вычисление для определения размерности
            logger.info("[get_embedding_model] Testing embedding dimensions...")
            test_start = time.time()
            test_embedding = model.embed_query("test")
            test_elapsed = time.time() - test_start
            dim = len(test_embedding)
            logger.info("[get_embedding_model] Test embedding completed in %.2f seconds, dimension: %d",
                        test_elapsed, dim)

        else:
            raise ValueError(f"Unknown embedding provider: {EMBEDDING_PROVIDER}")

        # ===== ШАГ 5: СОХРАНЕНИЕ В КЭШ ПАМЯТИ =====
        logger.info("[get_embedding_model] Model ready: %s, dimension: %d", name, dim)
        _embedding_model_cache = model

        return model

    except Exception as e:
        logger.error("[get_embedding_model] Failed to load model: %s", str(e), exc_info=True)
        raise

    finally:
        # ===== ШАГ 6: ВОССТАНОВЛЕНИЕ ИСХОДНЫХ НАСТРОЕК =====
        # Восстанавливаем оригинальные значения переменных окружения
        if use_offline:
            if original_transformers_offline is None:
                os.environ.pop('TRANSFORMERS_OFFLINE', None)
            else:
                os.environ['TRANSFORMERS_OFFLINE'] = original_transformers_offline

            if original_hf_hub_offline is None:
                os.environ.pop('HF_HUB_OFFLINE', None)
            else:
                os.environ['HF_HUB_OFFLINE'] = original_hf_hub_offline


def get_vectorstore(collection_name: str, embedding_model: Embeddings = None) -> Chroma:
    """
    Получает векторное хранилище ChromaDB.

    Args:
        collection_name: Имя коллекции
        embedding_model: Модель эмбеддингов (если None - создается автоматически)

    Returns:
        Chroma: Векторное хранилище
    """
    logger.debug("[get_vectorstore] <- collection_name='%s', embedding_model='%s'",
                 collection_name, embedding_model)

    if embedding_model is None:
        logger.info("[get_vectorstore] No embedding model provided, initializing default...")
        # Используем offline режим по умолчанию для быстрой загрузки из кэша
        embedding_model = get_embedding_model(use_offline=True)

    # Проверка версии ChromaDB для совместимости
    try:
        import chromadb
        chroma_version = chromadb.__version__

        if chroma_version.startswith(("0.4.", "0.5.")):
            logger.warning("ChromaDB %s may have filter limitations. Consider upgrading to 0.6+",
                           chroma_version)
    except Exception as e:
        logger.debug("Could not check ChromaDB version: %s", e)

    return Chroma(
        collection_name=collection_name,
        embedding_function=embedding_model,
        persist_directory=CHROMA_PERSIST_DIR
    )


def prepare_unified_documents(
        pages: list,
        service_code: str,
        doc_type: str = "requirement",
        requirement_type: str = None,
        source: str = "DBOCORPESPLN",
        chunk_strategy: str = CHUNK_MODE,
        max_full_page_size: int = CHUNK_MAX_PAGE_SIZE,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Document]:
    """
    Создает документы для единого хранилища с новой схемой метаданных.

    Адаптивная стратегия chunking:
    - "none": Всегда целая страница без разбиения
    - "adaptive": Маленькие страницы целиком, большие разбиваются
    - "fixed": Все страницы разбиваются на чанки

    Args:
        pages: Список страниц для обработки
        service_code: Код сервиса
        doc_type: Тип документа (requirement/template и т.д.)
        requirement_type: Тип требования
        source: Источник данных
        chunk_strategy: Стратегия разбиения (none/adaptive/fixed)
        max_full_page_size: Максимальный размер страницы для хранения целиком
        chunk_size: Размер чанка при разбиении
        chunk_overlap: Перекрытие между чанками

    Returns:
        list[Document]: Список подготовленных документов
    """
    logger.debug(
        "[prepare_unified_documents] <- Processing %d pages, service_code='%s', doc_type='%s', strategy=%s",
        len(pages), service_code, doc_type, chunk_strategy
    )

    # Инициализируем text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n## ", "\n\n### ", "\n\n", "\n", ". ", " ", ""],
        length_function=len
    )

    docs = []
    is_platform = get_platform_status(service_code) if doc_type == "requirement" else False

    for page in pages:
        content = page.get("approved_content", "")
        if not content or not content.strip():
            logger.warning("[prepare_unified_documents] No approved content for page %s", page.get("id"))
            continue

        content = content.strip()
        content_length = len(content)

        # Базовые метаданные
        base_metadata = {
            "doc_type": doc_type,
            "is_platform": is_platform,
            "service_code": service_code,
            "title": page["title"],
            "source": source,
            "page_id": page["id"],
            "original_page_size": content_length
        }

        if requirement_type:
            base_metadata["requirement_type"] = requirement_type
        elif page.get("requirement_type"):
            base_metadata["requirement_type"] = page["requirement_type"]

        # ===== СТРАТЕГИЯ 1: БЕЗ РАЗБИЕНИЯ =====
        if chunk_strategy == "none":
            doc = Document(page_content=content, metadata={**base_metadata, "is_full_page": True})
            docs.append(doc)
            logger.debug("[prepare_unified_documents] Added full page: %s (%d chars)",
                         page["id"], content_length)

        # ===== СТРАТЕГИЯ 2: АДАПТИВНАЯ =====
        elif chunk_strategy == "adaptive":
            if content_length <= max_full_page_size:
                # Маленькая страница - сохраняем целиком
                doc = Document(page_content=content, metadata={**base_metadata, "is_full_page": True})
                docs.append(doc)
                logger.debug("[prepare_unified_documents] Small page kept whole: %s (%d chars)",
                             page["id"], content_length)
            else:
                # Большая страница - разбиваем на чанки
                chunks = text_splitter.split_text(content)
                logger.info("[prepare_unified_documents] Splitting large page %s (%d chars) into %d chunks",
                            page["id"], content_length, len(chunks))

                for i, chunk in enumerate(chunks):
                    chunk_metadata = {
                        **base_metadata,
                        "is_full_page": False,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "title": f"{page['title']} [часть {i + 1}/{len(chunks)}]"
                    }
                    doc = Document(page_content=chunk, metadata=chunk_metadata)
                    docs.append(doc)

                logger.debug("[prepare_unified_documents] Created %d chunks for page %s",
                             len(chunks), page["id"])

        # ===== СТРАТЕГИЯ 3: ПРИНУДИТЕЛЬНОЕ РАЗБИЕНИЕ =====
        elif chunk_strategy == "fixed":
            chunks = text_splitter.split_text(content)
            logger.info("[prepare_unified_documents] Fixed chunking: page %s -> %d chunks",
                        page["id"], len(chunks))

            for i, chunk in enumerate(chunks):
                chunk_metadata = {
                    **base_metadata,
                    "is_full_page": False,
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
                doc = Document(page_content=chunk, metadata=chunk_metadata)
                docs.append(doc)

    logger.info("[prepare_unified_documents] -> Created %d documents total", len(docs))
    return docs


# ====================================================================
# LEGACY ФУНКЦИИ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ
# ====================================================================

def prepare_documents_for_approved_content(
        pages: list,
        service_code: str | None = None,
        source: str = "DBOCORPESPLN",
        doc_type: str = "requirement",
        enrich_with_type: bool = False
) -> list:
    """Legacy wrapper для обратной совместимости"""
    return prepare_unified_documents(
        pages=pages,
        service_code=service_code or "unknown",
        doc_type=doc_type,
        source=source
    )


def prepare_documents_for_index(
        pages: list,
        service_code: str | None = None,
        source: str = "DBOCORPESPLN",
        doc_type: str = "requirement",
        enrich_with_type: bool = False
) -> list[Document]:
    """Legacy wrapper для обратной совместимости"""
    return prepare_unified_documents(
        pages=pages,
        service_code=service_code or "unknown",
        doc_type=doc_type,
        source=source
    )