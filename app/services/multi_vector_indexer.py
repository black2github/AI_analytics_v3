# Путь: app/services/multi_vector_indexer.py
"""
Multi-Vector Indexer — адаптивная индексация документов.

Стратегия:
- Tier 1 (Multi-Vector): Документы < 5000 токенов → title + summary + content
- Tier 2 (Multi-Vector Chunked): Документы ≥ 5000 токенов → title + summary + chunks

Метаданные:
- vector_type: "title" | "summary" | "content" | "chunk"
- index_tier: "multi_vector" | "multi_vector_chunked"
- (+ все существующие метаданные сохраняются)
"""

import logging
from typing import List, Dict, Optional
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_MODE, CHUNK_MAX_PAGE_SIZE
)
from app.service_registry import get_platform_status
from app.services.page_summary_generator import create_summary_generator
from app.utils.text_processing import estimate_tokens

logger = logging.getLogger(__name__)


class MultiVectorIndexer:
    """
    Multi-Vector индексатор с поддержкой адаптивной стратегии.

    Создаёт несколько векторов для каждой страницы:
    - Title vector (для точного поиска по названию)
    - Summary vector (для понимания сути документа)
    - Content/Chunk vectors (для детального поиска)
    """

    # Порог для определения "большого" документа (в токенах)
    LARGE_DOC_THRESHOLD = CHUNK_MAX_PAGE_SIZE / 3 # 5000 токенов

    def __init__(
            self,
            chunk_size: int = CHUNK_SIZE,
            chunk_overlap: int = CHUNK_OVERLAP,
            use_llm_summary: bool = False
    ):
        """
        Args:
            chunk_size: Размер чанка (в символах)
            chunk_overlap: Перекрытие между чанками (в символах)
            use_llm_summary: Использовать LLM для генерации summary (медленнее, точнее)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_llm_summary = use_llm_summary

        # Text splitter для chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n## ", "\n\n### ", "\n\n", "\n", ". ", " ", ""],
            length_function=len
        )

        # Summary generator
        self.summary_generator = create_summary_generator() if use_llm_summary else None

        logger.info(
            "[__init__] -> Initialized with chunk_size=%d, overlap=%d, llm_summary=%s",
            chunk_size, chunk_overlap, use_llm_summary
        )

    async def prepare_multi_vector_documents(
            self,
            pages: List[Dict],
            service_code: str,
            doc_type: str = "requirement",
            source: str = "DBOCORPESPLN",
            batch_size: int = 50
    ) -> List[Document]:
        """
        Подготавливает документы с Multi-Vector индексацией.

        Args:
            pages: Список страниц [{id, title, approved_content, requirement_type}, ...]
            service_code: Код сервиса
            doc_type: Тип документа
            source: Источник данных
            batch_size: Размер батча для LLM summary generation

        Returns:
            Список Document объектов для ChromaDB
        """
        logger.info(
            "[prepare_multi_vector_documents] <- %d pages for service='%s'",
            len(pages), service_code
        )

        all_docs = []
        is_platform = get_platform_status(service_code) if doc_type == "requirement" else False

        # Если используем LLM summary - генерируем батчем для всех больших документов
        if self.use_llm_summary:
            summaries = await self._generate_summaries_batch(pages, batch_size)
        else:
            summaries = None

        # Обрабатываем каждую страницу
        for page in pages:
            page_docs = await self._process_single_page(
                page=page,
                service_code=service_code,
                doc_type=doc_type,
                source=source,
                is_platform=is_platform,
                pregenerated_summary=summaries.get(page['id']) if summaries else None
            )
            # Находим summary документ
            summary_doc = next((doc for doc in page_docs if doc.metadata.get("vector_type") == "summary"), None)
            summary_content = summary_doc.page_content if summary_doc else "No summary"

            logger.debug("[prepare_multi_vector_documents] summary for page_id=%s is [%s]",
                         page['id'], summary_content[:200])
            all_docs.extend(page_docs)

        logger.info(
            "[prepare_multi_vector_documents] -> Created %d documents total",
            len(all_docs)
        )

        return all_docs

    async def _process_single_page(
            self,
            page: Dict,
            service_code: str,
            doc_type: str,
            source: str,
            is_platform: bool,
            pregenerated_summary: Optional[str] = None
    ) -> List[Document]:
        """
        Обрабатывает одну страницу с Multi-Vector индексацией.

        Returns:
            Список документов для этой страницы (title + summary + content/chunks)
        """
        logger.debug("[_process_single_page] <- %s", page)
        content = page.get("approved_content", "")
        if not content or not content.strip():
            logger.warning(
                "[_process_single_page]-> No approved content for page %s",
                page.get("id")
            )
            return []

        content = content.strip()
        title = page["title"]
        page_id = page["id"]

        # Определяем requirement_type
        req_type = page.get("requirement_type", "unknown")
        if req_type:
            req_type = req_type.strip()

        # Базовые метаданные (общие для всех векторов страницы)
        base_metadata = {
            "doc_type": doc_type,
            "is_platform": is_platform,
            "service_code": service_code,
            "title": title,
            "source": source,
            "page_id": page_id,
            "original_page_size": len(content),
            "requirement_type": req_type
        }

        # Для интеграций добавляем target_system
        if req_type == "integration":
            from app.services.integration_parser import extract_target_system_from_title
            target_system = extract_target_system_from_title(title)
            if target_system:
                base_metadata["target_system"] = target_system

        # Определяем tier на основе размера
        token_count = estimate_tokens(content)

        if token_count >= self.LARGE_DOC_THRESHOLD and CHUNK_MODE != "none" :
            # Tier 2: Multi-Vector Chunked
            docs = await self._create_multi_vector_chunked(
                content=content,
                title=title,
                page_id=page_id,
                base_metadata=base_metadata,
                pregenerated_summary=pregenerated_summary
            )

            logger.debug(
                "[_process_single_page] Large page %s (%d tokens) -> %d documents (chunked)",
                page_id, token_count, len(docs)
            )
        else:
            # Tier 1: Multi-Vector (без chunking)
            docs = await self._create_multi_vector(
                content=content,
                title=title,
                page_id=page_id,
                base_metadata=base_metadata,
                pregenerated_summary=pregenerated_summary
            )

            logger.debug(
                "[_process_single_page] Regular page %s (%d tokens) -> %d documents",
                page_id, token_count, len(docs)
            )

        return docs

    async def _create_multi_vector(
            self,
            content: str,
            title: str,
            page_id: str,
            base_metadata: Dict,
            pregenerated_summary: Optional[str] = None
    ) -> List[Document]:
        """
        Создаёт Multi-Vector документы БЕЗ chunking.

        Returns:
            [title_doc, summary_doc, content_doc]
        """
        logger.debug("[_create_multi_vector] <- %s", page_id)
        docs = []

        # 1. Title Document
        title_doc = Document(
            page_content=title,
            metadata={
                **base_metadata,
                "vector_type": "title",
                "index_tier": "multi_vector",
                "is_full_page": True  # Title всегда "полная страница"
            }
        )
        docs.append(title_doc)

        # 2. Summary Document
        if pregenerated_summary:
            summary = pregenerated_summary
        else:
            # Extractive summary
            summary = self.summary_generator.generate_extractive(
                content, max_length=500, method="smart"
            ) if self.summary_generator else content[:500]

        summary_doc = Document(
            page_content=summary,
            metadata={
                **base_metadata,
                "vector_type": "summary",
                "index_tier": "multi_vector",
                "is_full_page": False
            }
        )
        docs.append(summary_doc)

        # 3. Content Document (полное содержимое)
        content_doc = Document(
            page_content=content,
            metadata={
                **base_metadata,
                "vector_type": "content",
                "index_tier": "multi_vector",
                "is_full_page": True
            }
        )
        docs.append(content_doc)
        logger.debug("[_create_multi_vector] -> %d docs.", len(docs))
        return docs

    async def _create_multi_vector_chunked(
            self,
            content: str,
            title: str,
            page_id: str,
            base_metadata: Dict,
            pregenerated_summary: Optional[str] = None
    ) -> List[Document]:
        """
        Создаёт Multi-Vector документы С chunking для больших страниц.

        Returns:
            [title_doc, summary_doc, chunk_doc_1, chunk_doc_2, ...]
        """
        logger.debug("[_create_multi_vector_chunked] <- %s", page_id)
        docs = []

        # 1. Title Document
        title_doc = Document(
            page_content=title,
            metadata={
                **base_metadata,
                "vector_type": "title",
                "index_tier": "multi_vector_chunked",
                "is_full_page": True
            }
        )
        docs.append(title_doc)

        # 2. Summary Document
        if pregenerated_summary:
            summary = pregenerated_summary
        elif self.use_llm_summary and self.summary_generator:
            # LLM summary для больших документов
            try:
                summary = await self.summary_generator.generate_llm(
                    content, max_tokens=200
                )
            except Exception as e:
                logger.warning(
                    "[_create_multi_vector_chunked] LLM summary failed for page %s: %s. Using extractive.",
                    page_id, str(e)
                )
                summary = self.summary_generator.generate_extractive(content, max_length=500)
        else:
            # Extractive summary
            summary = self.summary_generator.generate_extractive(
                content, max_length=500, method="smart"
            ) if self.summary_generator else content[:500]

        summary_doc = Document(
            page_content=summary,
            metadata={
                **base_metadata,
                "vector_type": "summary",
                "index_tier": "multi_vector_chunked",
                "is_full_page": False
            }
        )
        docs.append(summary_doc)

        # 3. Chunk Documents
        chunks = self.text_splitter.split_text(content)

        logger.debug(
            "[_create_multi_vector_chunked] Split page %s into %d chunks",
            page_id, len(chunks)
        )

        for i, chunk in enumerate(chunks):
            chunk_doc = Document(
                page_content=chunk,
                metadata={
                    **base_metadata,
                    "vector_type": "chunk",
                    "index_tier": "multi_vector_chunked",
                    "is_full_page": False,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "chunk_id": f"{page_id}_chunk_{i}"
                }
            )
            docs.append(chunk_doc)

        logger.debug("[_create_multi_vector_chunked] -> %d docs.", len(docs))
        return docs

    async def _generate_summaries_batch(
            self,
            pages: List[Dict],
            batch_size: int = 50
    ) -> Dict[str, str]:
        """
        Генерирует summary батчем для всех больших документов.

        Args:
            pages: Список страниц
            batch_size: Размер батча

        Returns:
            Словарь {page_id: summary}
        """
        logger.debug("[_generate_summaries_batch] <- %s", pages)

        if not self.use_llm_summary or not self.summary_generator:
            return {}

        # Фильтруем только большие документы
        large_pages = []
        for page in pages:
            content = page.get("approved_content", "")
            token_count = estimate_tokens(content)

            if token_count >= self.LARGE_DOC_THRESHOLD:
                large_pages.append({
                    'page_id': page['id'],
                    'title': page['title'],
                    'content': content
                })

        if not large_pages:
            logger.info("[_generate_summaries_batch] No large documents to process")
            return {}

        logger.info(
            "[_generate_summaries_batch] Generating LLM summaries for %d large documents...",
            len(large_pages)
        )

        # Батч генерация
        results = await self.summary_generator.generate_batch(
            documents=large_pages,
            max_concurrent=batch_size,
            use_llm_for_large=True,
            large_doc_threshold=0  # Все уже отфильтрованы
        )

        # Конвертируем в словарь
        summaries = {
            result['page_id']: result['summary']
            for result in results
        }

        logger.info(
            "[_generate_summaries_batch] -> Generated %d summaries",
            len(summaries)
        )

        return summaries


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def create_multi_vector_indexer(
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        use_llm_summary: bool = False
) -> MultiVectorIndexer:
    """
    Фабричная функция для создания MultiVectorIndexer.

    Args:
        chunk_size: Размер чанка (из config по умолчанию)
        chunk_overlap: Перекрытие (из config по умолчанию)
        use_llm_summary: Использовать LLM для summary

    Returns:
        Экземпляр MultiVectorIndexer
    """
    return MultiVectorIndexer(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        use_llm_summary=use_llm_summary
    )