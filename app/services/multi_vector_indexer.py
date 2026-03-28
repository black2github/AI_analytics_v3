# app/services/multi_vector_indexer.py
"""
Multi-Vector Indexer — адаптивная индексация документов.

Стратегия:
- Tier 1 (Multi-Vector): Документы < LARGE_DOC_THRESHOLD токенов → title + summary + content
- Tier 2 (Multi-Vector Chunked): Документы >= LARGE_DOC_THRESHOLD токенов → title + summary + chunks

LLM Summary (use_llm_summary=True):
- Все LLM-вызовы выполняются единым параллельным батчем ДО основного цикла индексации.
- _create_multi_vector и _create_multi_vector_chunked — синхронные, LLM не вызывают.
- Параллелизм ограничен семафором (batch_size) для контроля нагрузки на LLM API.

Метаданные:
- vector_type: "title" | "summary" | "content" | "chunk"
- index_tier: "multi_vector" | "multi_vector_chunked"
- (+ все существующие метаданные сохраняются)
"""

import asyncio
import logging
from typing import List, Dict, Optional
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_MODE,
    CHUNK_MAX_PAGE_SIZE,
)
from app.service_registry import get_platform_status
from app.services.page_summary_generator import create_summary_generator
from app.utils.text_processing import estimate_tokens

logger = logging.getLogger(__name__)


class MultiVectorIndexer:
    """
    Multi-Vector индексатор с поддержкой адаптивной стратегии.

    Создаёт несколько векторов для каждой страницы:
    - Title vector   — для точного поиска по названию
    - Summary vector — для понимания сути документа
    - Content/Chunk vectors — для детального поиска
    """

    # Порог для определения "большого" документа (в токенах)
    LARGE_DOC_THRESHOLD = CHUNK_MAX_PAGE_SIZE / 3  # ~5000 токенов

    def __init__(
            self,
            chunk_size: int = CHUNK_SIZE,
            chunk_overlap: int = CHUNK_OVERLAP,
            use_llm_summary: bool = False
    ):
        """
        Args:
            chunk_size: Размер чанка (в символах, из config)
            chunk_overlap: Перекрытие между чанками (в символах, из config)
            use_llm_summary: Использовать LLM для генерации summary.
                True  — summary генерируются параллельным батчем через LLM до индексации.
                False — быстрый extractive summary без LLM.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_llm_summary = use_llm_summary

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n## ", "\n\n### ", "\n\n", "\n", ". ", " ", ""],
            length_function=len
        )

        # SummaryGenerator нужен всегда — для extractive fallback тоже
        self.summary_generator = create_summary_generator()

        logger.info(
            "[__init__] Initialized: chunk_size=%d, overlap=%d, llm_summary=%s",
            chunk_size, chunk_overlap, use_llm_summary
        )

    # =========================================================================
    # ПУБЛИЧНЫЙ МЕТОД
    # =========================================================================

    async def prepare_multi_vector_documents(
            self,
            pages: List[Dict],
            service_code: str,
            doc_type: str = "requirement",
            source: str = "DBOCORPESPLN",
            batch_size: int = 10,
            preloaded_summaries: Optional[Dict[str, str]] = None,
    ) -> List[Document]:
        """
        Подготавливает документы с Multi-Vector индексацией.

        Порядок работы:
        1. Если передан preloaded_summaries — использует готовые summary из файла.
           LLM не вызывается даже при use_llm_summary=True для страниц из файла.
        2. Если use_llm_summary=True — генерирует LLM summary для ВСЕХ страниц
           единым параллельным батчем (max_concurrent=batch_size).
        3. Основной цикл: синхронная сборка Document объектов для каждой страницы.

        Args:
            pages: Список страниц [{id, title, approved_content, requirement_type}, ...]
            service_code: Код сервиса
            doc_type: Тип документа
            source: Источник данных
            batch_size: Максимальное число параллельных LLM-запросов при use_llm_summary=True
            preloaded_summaries: Готовые summary из файла {page_id: summary_text}.
                Страницы из этого словаря не требуют LLM-вызова.
                Генерируются скриптом generate_summaries.py.

        Returns:
            Список Document объектов для ChromaDB
        """
        logger.info(
            "[prepare_multi_vector_documents] <- %d pages, service='%s', "
            "llm_summary=%s, batch_size=%d, preloaded=%d",
            len(pages), service_code, self.use_llm_summary, batch_size,
            len(preloaded_summaries) if preloaded_summaries else 0,
        )

        is_platform = get_platform_status(service_code) if doc_type == "requirement" else False

        # Шаг 1. Определяем итоговый словарь summaries.
        # Приоритет: preloaded_summaries > LLM > extractive (в _create_multi_vector).
        summaries: Dict[str, str] = {}

        if preloaded_summaries:
            # Берём preloaded для страниц у которых есть запись в файле
            for page in pages:
                pid = page.get("id", "")
                if pid in preloaded_summaries:
                    summaries[pid] = preloaded_summaries[pid]

            preloaded_count = len(summaries)
            remaining = [p for p in pages if p.get("id") not in summaries]
            logger.info(
                "[prepare_multi_vector_documents] Preloaded summaries: %d/%d pages. "
                "Remaining without summary: %d",
                preloaded_count, len(pages), len(remaining)
            )

            # Для оставшихся страниц — LLM если включён, иначе extractive в _create_mv
            if remaining and self.use_llm_summary:
                llm_summaries = await self._generate_summaries_batch(remaining, batch_size)
                summaries.update(llm_summaries)
        else:
            # Стандартный путь: LLM для всех или extractive
            summaries = await self._generate_summaries_batch(pages, batch_size)

        # Шаг 2. Синхронная сборка Document объектов.
        all_docs: List[Document] = []
        total = len(pages)

        for idx, page in enumerate(pages, 1):
            page_id = page.get("id", "?")
            pregenerated = summaries.get(page_id)

            page_docs = self._process_single_page(
                page=page,
                service_code=service_code,
                doc_type=doc_type,
                source=source,
                is_platform=is_platform,
                pregenerated_summary=pregenerated
            )

            if page_docs:
                summary_doc = next(
                    (d for d in page_docs if d.metadata.get("vector_type") == "summary"),
                    None
                )
                summary_preview = summary_doc.page_content[:150] if summary_doc else "—"
                logger.debug(
                    "[prepare_multi_vector_documents] [%d/%d] page_id=%s "
                    "docs=%d summary='%s'",
                    idx, total, page_id, len(page_docs), summary_preview
                )
            else:
                logger.warning(
                    "[prepare_multi_vector_documents] [%d/%d] page_id=%s "
                    "skipped (no content)",
                    idx, total, page_id
                )

            all_docs.extend(page_docs)

            if idx % 50 == 0 or idx == total:
                logger.info(
                    "[prepare_multi_vector_documents] Progress: %d/%d pages, "
                    "%d docs so far",
                    idx, total, len(all_docs)
                )

        logger.info(
            "[prepare_multi_vector_documents] -> %d documents total for %d pages",
            len(all_docs), total
        )

        return all_docs

    # =========================================================================
    # ГЕНЕРАЦИЯ LLM SUMMARY — ЕДИНЫЙ ПАРАЛЛЕЛЬНЫЙ БАТЧ
    # =========================================================================

    async def _generate_summaries_batch(
            self,
            pages: List[Dict],
            batch_size: int = 10
    ) -> Dict[str, str]:
        """
        Генерирует LLM summary для всех страниц параллельно.

        Обрабатывает ВСЕ страницы (не только большие) — решение о методе
        (LLM vs extractive fallback) принимается здесь централизованно.
        Никаких LLM-вызовов внутри _create_multi_vector/_create_multi_vector_chunked.

        При use_llm_summary=False возвращает {} немедленно.

        Args:
            pages: Список страниц
            batch_size: Максимальное число параллельных LLM-запросов

        Returns:
            Словарь {page_id: summary_text}
        """
        if not self.use_llm_summary:
            return {}

        valid_pages = [
            {
                'page_id': p['id'],
                'title': p['title'],
                'content': p.get('approved_content', '').strip(),
                'requirement_type': p.get('requirement_type', ''),
            }
            for p in pages
            if p.get('approved_content', '').strip()
        ]

        if not valid_pages:
            logger.warning("[_generate_summaries_batch] No pages with content")
            return {}

        logger.info(
            "[_generate_summaries_batch] Generating LLM summaries for %d pages "
            "(max_concurrent=%d)...",
            len(valid_pages), batch_size
        )

        semaphore = asyncio.Semaphore(batch_size)

        async def summarize_one(page_dict: Dict) -> tuple:
            page_id = page_dict['page_id']
            content = page_dict['content']
            req_type = page_dict.get('requirement_type') or None
            async with semaphore:
                try:
                    summary = await self.summary_generator.generate_llm(
                        content,
                        max_tokens=250,
                        requirement_type=req_type,
                    )
                    logger.debug(
                        "[_generate_summaries_batch] LLM OK: page_id=%s (%d chars)",
                        page_id, len(summary)
                    )
                except Exception as e:
                    logger.warning(
                        "[_generate_summaries_batch] LLM failed for page_id=%s: %s. "
                        "Using extractive fallback.",
                        page_id, str(e)
                    )
                    summary = self.summary_generator.generate_extractive(
                        content, max_length=500
                    )
            return page_id, summary

        results = await asyncio.gather(*[summarize_one(p) for p in valid_pages])
        summaries = dict(results)

        logger.info(
            "[_generate_summaries_batch] -> %d summaries generated",
            len(summaries)
        )

        return summaries

    # =========================================================================
    # СБОРКА ДОКУМЕНТОВ — СИНХРОННЫЕ МЕТОДЫ (LLM НЕ ВЫЗЫВАЮТ)
    # =========================================================================

    def _process_single_page(
            self,
            page: Dict,
            service_code: str,
            doc_type: str,
            source: str,
            is_platform: bool,
            pregenerated_summary: Optional[str] = None
    ) -> List[Document]:
        """
        Собирает Document объекты для одной страницы. Синхронный, LLM не вызывает.

        Summary берётся из pregenerated_summary (LLM-батч) или генерируется
        extractive методом как fallback.

        Returns:
            [title_doc, summary_doc, content_doc/chunk_docs] или [] при пустом контенте
        """
        content = page.get("approved_content", "")
        if not content or not content.strip():
            return []

        content = content.strip()
        title = page["title"]
        page_id = page["id"]
        req_type = (page.get("requirement_type") or "unknown").strip()

        base_metadata = {
            "doc_type": doc_type,
            "is_platform": is_platform,
            "service_code": service_code,
            "title": title,
            "source": source,
            "page_id": page_id,
            "original_page_size": len(content),
            "requirement_type": req_type,
        }

        if req_type == "integration":
            from app.services.integration_parser import extract_target_system
            target_system = extract_target_system(title=title, content=content)
            if target_system:
                base_metadata["target_system"] = target_system

        token_count = estimate_tokens(content)
        is_large = token_count >= self.LARGE_DOC_THRESHOLD and CHUNK_MODE != "none"

        if is_large:
            docs = self._create_multi_vector_chunked(
                content=content,
                title=title,
                page_id=page_id,
                base_metadata=base_metadata,
                pregenerated_summary=pregenerated_summary
            )
            logger.debug(
                "[_process_single_page] Large page %s (%d tokens) -> %d docs (chunked)",
                page_id, token_count, len(docs)
            )
        else:
            docs = self._create_multi_vector(
                content=content,
                title=title,
                page_id=page_id,
                base_metadata=base_metadata,
                pregenerated_summary=pregenerated_summary
            )
            logger.debug(
                "[_process_single_page] Regular page %s (%d tokens) -> %d docs",
                page_id, token_count, len(docs)
            )

        return docs

    def _create_multi_vector(
            self,
            content: str,
            title: str,
            page_id: str,
            base_metadata: Dict,
            pregenerated_summary: Optional[str] = None
    ) -> List[Document]:
        """
        Создаёт Multi-Vector документы БЕЗ chunking (Tier 1). Синхронный.

        Returns:
            [title_doc, summary_doc, content_doc]
        """
        summary = pregenerated_summary or self.summary_generator.generate_extractive(
            content, max_length=500, method="smart"
        )

        docs = [
            Document(
                page_content=title,
                metadata={
                    **base_metadata,
                    "vector_type": "title",
                    "index_tier": "multi_vector",
                    "is_full_page": True,
                }
            ),
            Document(
                page_content=summary,
                metadata={
                    **base_metadata,
                    "vector_type": "summary",
                    "index_tier": "multi_vector",
                    "is_full_page": False,
                }
            ),
            Document(
                page_content=content,
                metadata={
                    **base_metadata,
                    "vector_type": "content",
                    "index_tier": "multi_vector",
                    "is_full_page": True,
                }
            ),
        ]

        logger.debug("[_create_multi_vector] page_id=%s -> %d docs", page_id, len(docs))
        return docs

    def _create_multi_vector_chunked(
            self,
            content: str,
            title: str,
            page_id: str,
            base_metadata: Dict,
            pregenerated_summary: Optional[str] = None
    ) -> List[Document]:
        """
        Создаёт Multi-Vector документы С chunking для больших страниц (Tier 2). Синхронный.

        Returns:
            [title_doc, summary_doc, chunk_doc_1, chunk_doc_2, ...]
        """
        summary = pregenerated_summary or self.summary_generator.generate_extractive(
            content, max_length=500, method="smart"
        )

        docs = [
            Document(
                page_content=title,
                metadata={
                    **base_metadata,
                    "vector_type": "title",
                    "index_tier": "multi_vector_chunked",
                    "is_full_page": True,
                }
            ),
            Document(
                page_content=summary,
                metadata={
                    **base_metadata,
                    "vector_type": "summary",
                    "index_tier": "multi_vector_chunked",
                    "is_full_page": False,
                }
            ),
        ]

        chunks = self.text_splitter.split_text(content)
        logger.debug(
            "[_create_multi_vector_chunked] page_id=%s split into %d chunks",
            page_id, len(chunks)
        )

        for i, chunk in enumerate(chunks):
            docs.append(Document(
                page_content=chunk,
                metadata={
                    **base_metadata,
                    "vector_type": "chunk",
                    "index_tier": "multi_vector_chunked",
                    "is_full_page": False,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "chunk_id": f"{page_id}_chunk_{i}",
                }
            ))

        logger.debug(
            "[_create_multi_vector_chunked] page_id=%s -> %d docs",
            page_id, len(docs)
        )
        return docs


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

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