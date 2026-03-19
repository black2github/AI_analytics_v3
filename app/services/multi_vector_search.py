# Путь: app/services/multi_vector_search.py
"""
Multi-Vector Search — поиск с Reciprocal Rank Fusion.

Стратегия:
- Title search (БЕЗ фильтра по requirement_type) — для универсальности
- Summary search (с фильтром если указан)
- Content/Chunk search (с фильтром если указан)
- RRF merge для объединения результатов
"""

import logging
from typing import List, Optional, Dict, Tuple
from collections import defaultdict
from dataclasses import dataclass

from langchain_core.documents import Document

from app.config import UNIFIED_STORAGE_NAME
from app.embedding_store import get_vectorstore
from app.llm_interface import get_embeddings_model

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Результат поиска с метаданными."""
    page_id: str
    title: str
    content_preview: str
    requirement_type: Optional[str]
    metadata: Dict
    combined_score: float
    title_rank: Optional[int] = None
    summary_rank: Optional[int] = None
    content_rank: Optional[int] = None


class MultiVectorSearch:
    """
    Multi-Vector поиск с Reciprocal Rank Fusion.

    Комбинирует результаты поиска по title, summary и content/chunks
    для максимальной точности.
    """

    # Константа для RRF formula
    RRF_K = 60

    def __init__(
            self,
            vectorstore=None,
            title_weight: float = 0.5,
            summary_weight: float = 0.3,
            content_weight: float = 0.2
    ):
        """
        Args:
            vectorstore: ChromaDB vectorstore (None = создаётся автоматически)
            title_weight: Вес title search (0.0-1.0)
            summary_weight: Вес summary search (0.0-1.0)
            content_weight: Вес content search (0.0-1.0)
        """
        self.vectorstore = vectorstore
        self.title_weight = title_weight
        self.summary_weight = summary_weight
        self.content_weight = content_weight

        logger.info(
            "[__init__] <- Initialized with weights: title=%.2f, summary=%.2f, content=%.2f",
            title_weight, summary_weight, content_weight
        )

    def _get_vectorstore(self):
        """Ленивая инициализация vectorstore."""
        if self.vectorstore is None:
            embeddings_model = get_embeddings_model()
            self.vectorstore = get_vectorstore(
                UNIFIED_STORAGE_NAME,
                embedding_model=embeddings_model
            )
        return self.vectorstore

    def search(
            self,
            query: str,
            requirement_types: Optional[List[str]] = None,
            service_code: Optional[str] = None,
            target_system: Optional[str] = None,
            top_k: int = 50,
            title_k: int = 15,
            summary_k: int = 10,
            content_k: int = 30
    ) -> List[SearchResult]:
        """
        Универсальный поиск с Multi-Vector + RRF.

        Args:
            query: Поисковый запрос
            requirement_types: Фильтр по типам требований (None = искать везде)
            service_code: Фильтр по сервису (None = искать везде)
            target_system: Фильтр по target_system для интеграций
            top_k: Итоговое количество результатов
            title_k: Количество результатов из title search
            summary_k: Количество результатов из summary search
            content_k: Количество результатов из content search

        Returns:
            Список SearchResult отсортированных по combined_score
        """
        logger.info(
            "[search] <- query='%s', types=%s, service=%s, top_k=%d",
            query[:100], requirement_types, service_code, top_k
        )

        vectorstore = self._get_vectorstore()

        # ===== 1. TITLE SEARCH (БЕЗ фильтра по requirement_type) =====
        title_filter = self._build_filter(
            requirement_types=None,  # НЕ фильтруем по типу для универсальности
            service_code=service_code,
            target_system=target_system,
            vector_type="title"
        )

        logger.debug("[search] Title filter: %s", title_filter)

        title_results = vectorstore.similarity_search_with_score(
            query,
            k=title_k,
            filter=title_filter
        )

        logger.debug("[search] Title search returned %d results", len(title_results))

        # ===== 2. SUMMARY SEARCH (с фильтром если указан) =====
        summary_filter = self._build_filter(
            requirement_types=requirement_types,
            service_code=service_code,
            target_system=target_system,
            vector_type="summary"
        )

        logger.debug("[search] Summary filter: %s", summary_filter)

        summary_results = vectorstore.similarity_search_with_score(
            query,
            k=summary_k,
            filter=summary_filter
        )

        logger.debug("[search] Summary search returned %d results", len(summary_results))

        # ===== 3. CONTENT/CHUNK SEARCH (с фильтром если указан) =====
        content_filter = self._build_filter(
            requirement_types=requirement_types,
            service_code=service_code,
            target_system=target_system,
            vector_type=["content", "chunk"]  # Оба типа
        )

        logger.debug("[search] Content filter: %s", content_filter)

        content_results = vectorstore.similarity_search_with_score(
            query,
            k=content_k,
            filter=content_filter
        )

        logger.debug("[search] Content search returned %d results", len(content_results))

        # ===== 4. RECIPROCAL RANK FUSION =====
        merged_results = self._reciprocal_rank_fusion(
            title_results=title_results,
            summary_results=summary_results,
            content_results=content_results
        )

        # Ограничиваем топ-k
        final_results = merged_results[:top_k]

        logger.info("[search] -> Returning %d results", len(final_results))

        return final_results

    def _build_filter(
            self,
            requirement_types: Optional[List[str]],
            service_code: Optional[str],
            target_system: Optional[str],
            vector_type: Optional[str | List[str]]
    ) -> Dict:
        """
        Строит фильтр для ChromaDB search.

        Args:
            requirement_types: Типы требований (None = не фильтровать)
            service_code: Код сервиса (None = не фильтровать)
            target_system: Target system (None = не фильтровать)
            vector_type: Тип вектора ("title"/"summary"/["content", "chunk"])

        Returns:
            Словарь фильтра для ChromaDB
        """
        conditions = []

        # Базовый фильтр: только requirements
        conditions.append({"doc_type": {"$eq": "requirement"}})

        # Фильтр по service_code
        if service_code:
            conditions.append({"service_code": {"$eq": service_code}})

        # Фильтр по target_system (для интеграций)
        if target_system:
            conditions.append({"target_system": {"$eq": target_system}})

        # Фильтр по requirement_types
        if requirement_types:
            if len(requirement_types) == 1:
                conditions.append({"requirement_type": {"$eq": requirement_types[0]}})
            else:
                conditions.append({"requirement_type": {"$in": requirement_types}})

        # Фильтр по vector_type
        if vector_type:
            if isinstance(vector_type, str):
                conditions.append({"vector_type": {"$eq": vector_type}})
            elif isinstance(vector_type, list):
                conditions.append({"vector_type": {"$in": vector_type}})

        # Объединяем условия
        if len(conditions) > 1:
            return {"$and": conditions}
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {}

    def _reciprocal_rank_fusion(
            self,
            title_results: List[Tuple[Document, float]],
            summary_results: List[Tuple[Document, float]],
            content_results: List[Tuple[Document, float]]
    ) -> List[SearchResult]:
        """
        Reciprocal Rank Fusion для объединения результатов.

        RRF formula: combined_score = sum(weight / (rank + k))

        Args:
            title_results: Результаты title search [(doc, score), ...]
            summary_results: Результаты summary search
            content_results: Результаты content search

        Returns:
            Отсортированный список SearchResult
        """
        logger.debug(
            "[_reciprocal_rank_fusion] Merging: title=%d, summary=%d, content=%d",
            len(title_results), len(summary_results), len(content_results)
        )

        # Словарь для накопления scores по page_id
        combined_scores = defaultdict(lambda: {
            'score': 0.0,
            'title_rank': None,
            'summary_rank': None,
            'content_rank': None,
            'metadata': None,
            'content_preview': None
        })

        # Обрабатываем title results
        for rank, (doc, _) in enumerate(title_results, 1):
            page_id = doc.metadata.get('page_id')
            if not page_id:
                continue

            # RRF score
            rrf_score = self.title_weight / (rank + self.RRF_K)

            combined_scores[page_id]['score'] += rrf_score
            combined_scores[page_id]['title_rank'] = rank
            combined_scores[page_id]['metadata'] = doc.metadata
            combined_scores[page_id]['content_preview'] = doc.page_content[:300]

        # Обрабатываем summary results
        for rank, (doc, _) in enumerate(summary_results, 1):
            page_id = doc.metadata.get('page_id')
            if not page_id:
                continue

            rrf_score = self.summary_weight / (rank + self.RRF_K)

            combined_scores[page_id]['score'] += rrf_score
            combined_scores[page_id]['summary_rank'] = rank

            # Сохраняем metadata если ещё не сохранены
            if combined_scores[page_id]['metadata'] is None:
                combined_scores[page_id]['metadata'] = doc.metadata
                combined_scores[page_id]['content_preview'] = doc.page_content[:300]

        # Обрабатываем content results
        for rank, (doc, _) in enumerate(content_results, 1):
            page_id = doc.metadata.get('page_id')
            if not page_id:
                continue

            rrf_score = self.content_weight / (rank + self.RRF_K)

            combined_scores[page_id]['score'] += rrf_score
            combined_scores[page_id]['content_rank'] = rank

            # Сохраняем metadata если ещё не сохранены
            if combined_scores[page_id]['metadata'] is None:
                combined_scores[page_id]['metadata'] = doc.metadata
                combined_scores[page_id]['content_preview'] = doc.page_content[:300]

        # Конвертируем в SearchResult и сортируем
        results = []

        for page_id, data in combined_scores.items():
            metadata = data['metadata']

            if metadata is None:
                logger.warning("[_reciprocal_rank_fusion] No metadata for page_id=%s", page_id)
                continue

            result = SearchResult(
                page_id=page_id,
                title=metadata.get('title', 'No title'),
                content_preview=data['content_preview'] or '',
                requirement_type=metadata.get('requirement_type'),
                metadata=metadata,
                combined_score=data['score'],
                title_rank=data['title_rank'],
                summary_rank=data['summary_rank'],
                content_rank=data['content_rank']
            )

            results.append(result)

        # Сортируем по combined_score (выше = лучше)
        results.sort(key=lambda x: x.combined_score, reverse=True)

        logger.debug(
            "[_reciprocal_rank_fusion] -> Merged into %d unique pages",
            len(results)
        )

        # Логируем топ-10
        logger.info("[_reciprocal_rank_fusion] Top 10 after RRF:")
        for i, result in enumerate(results[:10], 1):
            logger.info(
                "  %d. [%s] %s (RRF: %.4f, ranks: T=%s S=%s C=%s)",
                i, result.page_id, result.title[:50],
                result.combined_score,
                result.title_rank or '-',
                result.summary_rank or '-',
                result.content_rank or '-'
            )

        return results


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def create_multi_vector_search(
        title_weight: float = 0.5,
        summary_weight: float = 0.3,
        content_weight: float = 0.2
) -> MultiVectorSearch:
    """
    Фабричная функция для создания MultiVectorSearch.

    Args:
        title_weight: Вес title (по умолчанию 0.5)
        summary_weight: Вес summary (по умолчанию 0.3)
        content_weight: Вес content (по умолчанию 0.2)

    Returns:
        Экземпляр MultiVectorSearch
    """
    return MultiVectorSearch(
        title_weight=title_weight,
        summary_weight=summary_weight,
        content_weight=content_weight
    )


def search_with_multi_vector(
        query: str,
        requirement_types: Optional[List[str]] = None,
        service_code: Optional[str] = None,
        top_k: int = 50
) -> List[SearchResult]:
    """
    Удобная функция для быстрого поиска.

    Args:
        query: Поисковый запрос
        requirement_types: Фильтр по типам
        service_code: Фильтр по сервису
        top_k: Количество результатов

    Returns:
        Список SearchResult
    """
    searcher = create_multi_vector_search()
    return searcher.search(
        query=query,
        requirement_types=requirement_types,
        service_code=service_code,
        top_k=top_k
    )