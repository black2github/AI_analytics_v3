# app/agents/context_retrieval_agent.py

from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

from app.embedding_store import get_vectorstore
from app.config import UNIFIED_STORAGE_NAME
from app.page_cache import get_page_data_cached
from app.service_registry import get_platform_status

logger = logging.getLogger(__name__)


@dataclass
class RequirementContext:
    """Контекст одного требования"""
    page_id: str
    title: str
    requirement_type: Optional[str]
    source: str  # "chromadb" или "confluence"
    status: str  # "confirmed", "pending", "modified"
    content_preview: str
    metadata: Dict

    # Для незавершённых требований
    has_pending_changes: bool = False
    pending_content: Optional[str] = None


@dataclass
class ContextMap:
    """Структурированная карта контекста"""
    service_code: str

    # Подтверждённые требования из ChromaDB
    confirmed_requirements: List[RequirementContext]

    # Незавершённые изменения из Confluence
    pending_requirements: List[RequirementContext]

    # Классификация по отношению к задаче
    potentially_affected: List[RequirementContext]
    potentially_conflicting: List[RequirementContext]

    # Смежные системы, упоминаемые в требованиях
    related_systems: List[str]

    # Статистика
    total_confirmed: int
    total_pending: int


class ContextRetrievalAgent:
    """
    Агент извлечения контекста для создания требований.

    Формирует структурированную карту контекста на основе:
    1. Подтверждённых требований из ChromaDB
    2. Незавершённых изменений из Confluence
    3. Классификации требований по отношению к задаче
    """

    def __init__(self, service_code: str):
        self.service_code = service_code
        self.vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME)
        self.is_platform = get_platform_status(service_code)

    def retrieve_context(
            self,
            business_requirements: str,
            requirement_types: Optional[List[str]] = None
    ) -> ContextMap:
        """
        Формирует структурированную карту контекста.

        Args:
            business_requirements: Текст бизнес-требований для семантического поиска
            requirement_types: Фильтр по типам требований (опционально)

        Returns:
            ContextMap со структурированным контекстом
        """
        logger.info(
            "[ContextRetrievalAgent] Retrieving context for service=%s, platform=%s",
            self.service_code, self.is_platform
        )

        # 1. Поиск подтверждённых требований в ChromaDB
        confirmed = self._search_confirmed_requirements(
            business_requirements,
            requirement_types
        )

        # 2. Проверка Confluence на незавершённые работы
        pending = self._check_confluence_for_pending(confirmed)

        # 3. Извлечение смежных систем
        related_systems = self._extract_related_systems(confirmed)

        # 4. Классификация требований
        affected, conflicting = self._classify_requirements(
            confirmed,
            business_requirements
        )

        context_map = ContextMap(
            service_code=self.service_code,
            confirmed_requirements=confirmed,
            pending_requirements=pending,
            potentially_affected=affected,
            potentially_conflicting=conflicting,
            related_systems=related_systems,
            total_confirmed=len(confirmed),
            total_pending=len(pending)
        )

        logger.info(
            "[ContextRetrievalAgent] Context retrieved: confirmed=%d, pending=%d, systems=%s",
            len(confirmed), len(pending), related_systems
        )

        return context_map

    def _search_confirmed_requirements(
            self,
            query: str,
            requirement_types: Optional[List[str]] = None
    ) -> List[RequirementContext]:
        """
        Поиск подтверждённых требований в ChromaDB.
        """
        logger.debug("[ContextRetrievalAgent] Searching confirmed requirements...")

        # Базовый фильтр
        query_filter = {
            "service_code": self.service_code,
            "doc_type": "requirement"
        }

        # Добавляем фильтр по типам требований если указан
        # ПРОБЛЕМА: requirement_type может отсутствовать в метаданных!
        # Пока ищем по всем типам, затем фильтруем вручную

        # Semantic search
        docs = self.vectorstore.similarity_search(
            query,
            k=50,  # начальная выборка
            filter=query_filter
        )

        # Конвертируем в RequirementContext
        contexts = []
        for doc in docs:
            metadata = doc.metadata

            # Фильтрация по requirement_types если указан и доступен
            if requirement_types:
                req_type = metadata.get("requirement_type")
                if req_type and req_type not in requirement_types:
                    continue

            context = RequirementContext(
                page_id=metadata["page_id"],
                title=metadata["title"],
                requirement_type=metadata.get("requirement_type"),
                source="chromadb",
                status="confirmed",
                content_preview=doc.page_content[:300],
                metadata=metadata,
                has_pending_changes=False
            )
            contexts.append(context)

        logger.debug("[ContextRetrievalAgent] Found %d confirmed requirements", len(contexts))
        return contexts

    def _check_confluence_for_pending(
            self,
            confirmed: List[RequirementContext]
    ) -> List[RequirementContext]:
        """
        Проверяет страницы Confluence на наличие незавершённых изменений.

        Сравнивает full_content и approved_content для каждой страницы.
        """
        logger.debug("[ContextRetrievalAgent] Checking Confluence for pending changes...")

        pending = []

        for req in confirmed:
            page_id = req.page_id
            page_data = get_page_data_cached(page_id)

            if not page_data:
                logger.warning("[ContextRetrievalAgent] Could not load page %s", page_id)
                continue

            full_content = page_data['full_content']
            approved_content = page_data['approved_content']

            # Есть ли разница между полным контентом и одобренным?
            if full_content != approved_content:
                # Есть незавершённые изменения (цветные фрагменты)
                pending_content = self._extract_pending_diff(
                    full_content,
                    approved_content
                )

                req.has_pending_changes = True
                req.pending_content = pending_content

                # Создаём отдельный контекст для pending
                pending_req = RequirementContext(
                    page_id=page_id,
                    title=req.title,
                    requirement_type=req.requirement_type,
                    source="confluence",
                    status="pending",
                    content_preview=pending_content[:300],
                    metadata=req.metadata,
                    has_pending_changes=True,
                    pending_content=pending_content
                )
                pending.append(pending_req)

        logger.debug("[ContextRetrievalAgent] Found %d pages with pending changes", len(pending))
        return pending

    def _extract_pending_diff(self, full: str, approved: str) -> str:
        """
        Извлекает только те фрагменты, которые есть в full, но нет в approved.

        Простая реализация — вычитание.
        Для более точной — можно использовать difflib.
        """
        # Простой вариант — всё что не в approved
        # TODO: улучшить через difflib для точного определения изменений

        if len(full) > len(approved):
            # Есть добавления
            return full[len(approved):]
        else:
            return ""

    def _extract_related_systems(
            self,
            requirements: List[RequirementContext]
    ) -> List[str]:
        """
        Извлекает список смежных систем из требований.

        ТЕКУЩАЯ РЕАЛИЗАЦИЯ: парсинг из заголовков интеграций.
        БУДУЩАЯ: использование target_system из метаданных.
        """
        systems = set()

        for req in requirements:
            # Если это интеграция
            if req.requirement_type == "integration":
                # Парсим из заголовка
                # Формат: "АБС Ф1_REST_Получение списка карт"
                title = req.title
                if "_" in title:
                    system = title.split("_")[0].strip()
                    systems.add(system)

                # БУДУЩЕЕ: когда будет target_system в метаданных
                # system = req.metadata.get("target_system")
                # if system:
                #     systems.add(system)

        return sorted(list(systems))

    def _classify_requirements(
            self,
            requirements: List[RequirementContext],
            business_requirements: str
    ) -> tuple[List[RequirementContext], List[RequirementContext]]:
        """
        Классифицирует требования на затрагиваемые и конфликтующие.

        Использует простую эвристику на основе семантической близости.
        В будущем можно добавить LLM для более точной классификации.
        """
        # Для MVP — простая классификация по релевантности из векторного поиска
        # Предполагаем, что первые N результатов — затрагиваемые

        affected = requirements[:10]  # топ-10 наиболее релевантных

        # Конфликтующие определяем эвристически
        # Например, если есть pending changes на затрагиваемых страницах
        conflicting = [
            req for req in affected
            if req.has_pending_changes
        ]

        return affected, conflicting