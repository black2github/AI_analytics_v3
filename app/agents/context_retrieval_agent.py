# Путь: app/agents/context_retrieval_agent.py

"""
Context Retrieval Agent — Агент извлечения контекста.

Формирует структурированную карту контекста для создания требований:
1. Страницы с подтверждёнными требованиями из ChromaDB (только чёрный текст)
2. Страницы с незавершёнными изменениями из Confluence (есть цветной текст)
3. Классификация страниц по отношению к задаче
4. Список смежных систем, упоминаемых в интеграциях

ВАЖНО: Гранулярность = страница Confluence, а не отдельное требование.
Страница содержит множество требований (предложений), но является единицей хранения.

QUERY EXPANSION: Использует LLM для декомпозиции бизнес-требований на специализированные
поисковые запросы по типам требований (dataModel, function, integration и т.д.).

MULTI-VECTOR SEARCH: Поиск ведётся по трём векторным слоям (title, summary, content/chunks)
с объединением через Reciprocal Rank Fusion. Каждая страница представлена несколькими
документами в ChromaDB, результаты дедуплицируются по page_id до передачи в ContextMap.

INTEGRATION SUB-QUERY: После основного поиска всегда выполняется дополнительный запрос
по integration-страницам (если тип "integration" не исключён явным фильтром caller-а).
Это гарантирует присутствие смежных систем в карте контекста независимо от топ-N.
"""

import json
import re
import logging
from typing import List, Optional, Dict, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from app.config import (
    UNIFIED_STORAGE_NAME,
    MV_TITLE_WEIGHT,
    MV_SUMMARY_WEIGHT,
    MV_CONTENT_WEIGHT,
    CONTEXT_INTEGRATION_TOP_K,
)
from app.page_cache import get_page_data_cached
from app.service_registry import get_platform_status
from app.llm_interface import get_llm
from app.services.multi_vector_search import MultiVectorSearch, SearchResult
from langchain_core.prompts import PromptTemplate

# Для Hybrid Search (BM25 по контентным векторам поверх Multi-Vector)
try:
    from rank_bm25 import BM25Okapi
    import pymorphy2

    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    logging.warning(
        "BM25 libraries not available. Install: pip install rank-bm25 pymorphy2 pymorphy2-dicts-ru"
    )

logger = logging.getLogger(__name__)


# ============================================================================
# СТРУКТУРЫ ДАННЫХ
# ============================================================================

@dataclass
class PageContext:
    """
    Контекст одной страницы Confluence с требованиями.

    Страница может содержать множество требований (предложений),
    но является единицей хранения и версионирования.

    Терминология:
    - Чёрный текст на странице = подтверждённые требования (есть в ChromaDB)
    - Цветной текст на странице = незавершённые изменения (НЕТ в ChromaDB)

    В Multi-Vector режиме одна страница хранится в ChromaDB несколькими документами
    (title, summary, content). SearchResult уже дедуплицирован по page_id до создания PageContext.
    """
    page_id: str
    title: str
    requirement_type: Optional[str]
    source: str  # "chromadb" или "confluence"
    status: str  # "confirmed", "pending", "modified"
    content_preview: str
    metadata: Dict
    relevance_score: float = 0.0

    # Отладочная информация Multi-Vector (заполняется из SearchResult)
    mv_title_rank: Optional[int] = None
    mv_summary_rank: Optional[int] = None
    mv_content_rank: Optional[int] = None

    # Для страниц с незавершёнными изменениями
    has_pending_changes: bool = False
    pending_content: Optional[str] = None

    # Для интеграций
    target_system: Optional[str] = None


@dataclass
class ContextMap:
    """
    Структурированная карта контекста.

    Содержит информацию о страницах с требованиями сервиса,
    сгруппированную по статусу и типам.
    """
    service_code: str
    is_platform: bool

    # Страницы с полностью подтверждёнными требованиями (только чёрный текст)
    confirmed_pages: List[PageContext] = field(default_factory=list)

    # Страницы с незавершёнными изменениями (есть цветной текст)
    pages_with_pending_changes: List[PageContext] = field(default_factory=list)

    # Страницы, потенциально затрагиваемые задачей (по релевантности)
    potentially_affected_pages: List[PageContext] = field(default_factory=list)

    # Страницы с конфликтами (релевантны И имеют pending changes)
    pages_with_conflicts: List[PageContext] = field(default_factory=list)

    # Смежные системы, упоминаемые в интеграционных требованиях
    related_systems: List[str] = field(default_factory=list)

    # Группировка страниц по типам требований
    pages_by_type: Dict[str, List[PageContext]] = field(default_factory=lambda: defaultdict(list))

    # Статистика
    total_confirmed_pages: int = 0
    total_pages_with_pending: int = 0
    total_pages_with_conflicts: int = 0


# ============================================================================
# RUSSIAN BM25 RETRIEVER
# ============================================================================

class RussianBM25Retriever:
    """
    BM25 retriever с поддержкой русской морфологии через Pymorphy2.

    Особенности:
    - Лемматизация (заявка/заявки/заявке -> заявка)
    - Удаление стоп-слов
    - Фильтрация коротких слов

    Используется поверх Multi-Vector Search как дополнительный сигнал ранжирования
    (по content/chunk документам сервиса).
    """

    RUSSIAN_STOP_WORDS = {
        'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как',
        'а', 'то', 'все', 'она', 'так', 'его', 'но', 'да', 'ты', 'к',
        'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было',
        'вот', 'от', 'меня', 'еще', 'нет', 'о', 'из', 'ему', 'теперь',
        'когда', 'даже', 'ну', 'вдруг', 'ли', 'если', 'уже', 'или',
        'ни', 'быть', 'был', 'него', 'до', 'вас', 'нибудь', 'опять',
        'уж', 'вам', 'ведь', 'там', 'потом', 'себя', 'ничего', 'ей',
        'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней', 'для',
        'мы', 'тебя', 'их', 'чем', 'была', 'сам', 'чтоб', 'без',
        'будто', 'чего', 'раз', 'тоже', 'себе', 'под', 'будет', 'ж',
        'тогда', 'кто', 'этот', 'того', 'потому', 'этого', 'какой',
        'совсем', 'ним', 'здесь', 'этом', 'один', 'почти', 'мой', 'тем',
        'чтобы', 'нее', 'сейчас', 'были', 'куда', 'зачем', 'всех',
        'никогда', 'можно', 'при', 'наконец', 'два', 'об', 'другой',
        'хоть', 'после', 'над', 'больше', 'тот', 'через', 'эти',
        'нас', 'про', 'всего', 'них', 'какая', 'много', 'разве',
        'три', 'эту', 'моя', 'впрочем', 'хорошо', 'свою', 'этой',
        'перед', 'иногда', 'лучше', 'чуть', 'том', 'нельзя', 'такой',
        'им', 'более', 'всегда', 'конечно', 'всю', 'между'
    }

    def __init__(self, documents: List[str], metadatas: List[Dict]):
        """
        Args:
            documents: Список текстов документов
            metadatas: Список метаданных (page_id, title, requirement_type, etc.)
        """
        if not BM25_AVAILABLE:
            raise ImportError(
                "BM25 libraries not installed. "
                "Install: pip install rank-bm25 pymorphy2 pymorphy2-dicts-ru"
            )

        self.morph = pymorphy2.MorphAnalyzer()
        self.documents = documents
        self.metadatas = metadatas

        logger.info("[RussianBM25] Indexing %d documents...", len(documents))
        self.tokenized_docs = [self._process_text(doc) for doc in documents]
        self.bm25 = BM25Okapi(self.tokenized_docs)
        logger.info("[RussianBM25] Indexing complete")

    def _process_text(self, text: str) -> List[str]:
        """Обработка текста: лемматизация + удаление стоп-слов."""
        if not text:
            return []

        tokens = text.lower().split()
        lemmas = []
        for token in tokens:
            clean_token = ''.join(c for c in token if c.isalnum())
            if not clean_token:
                continue
            try:
                lemma = self.morph.parse(clean_token)[0].normal_form
            except Exception:
                lemma = clean_token

            if lemma not in self.RUSSIAN_STOP_WORDS and len(lemma) > 2:
                lemmas.append(lemma)

        return lemmas

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Поиск по запросу.

        Returns:
            Список кортежей (document_index, score)
        """
        tokenized_query = self._process_text(query)

        if not tokenized_query:
            logger.warning("[RussianBM25] Empty query after processing")
            return []

        logger.debug("[RussianBM25] Query tokens: %s", tokenized_query)

        scores = self.bm25.get_scores(tokenized_query)
        top_indices = scores.argsort()[-top_k:][::-1]
        results = [(int(idx), float(scores[idx])) for idx in top_indices]

        logger.debug(
            "[RussianBM25] Top-%d scores: %s",
            top_k,
            [(idx, f"{score:.3f}") for idx, score in results[:5]]
        )

        return results


# ============================================================================
# АГЕНТ
# ============================================================================

class ContextRetrievalAgent:
    """
    Агент извлечения контекста для создания требований.

    Использует Multi-Vector Search (title + summary + content/chunks) с RRF
    для ранжирования страниц по релевантности. Поверх опционально применяется
    BM25 по русскому тексту для гибридного ранжирования.

    Пример использования:
        agent = ContextRetrievalAgent("CC")
        context_map = agent.retrieve_context(
            business_requirements="Добавить поле Комментарий в заявку"
        )
    """

    def __init__(
        self,
        service_code: str,
        use_hybrid_search: bool = True,
        mv_title_weight: float = MV_TITLE_WEIGHT,
        mv_summary_weight: float = MV_SUMMARY_WEIGHT,
        mv_content_weight: float = MV_CONTENT_WEIGHT
    ):
        """
        Args:
            service_code: Код сервиса для извлечения контекста
            use_hybrid_search: Дополнять Multi-Vector BM25 (требует rank-bm25, pymorphy2)
            mv_title_weight: Вес title-вектора в RRF (из config по умолчанию)
            mv_summary_weight: Вес summary-вектора в RRF (из config по умолчанию)
            mv_content_weight: Вес content/chunk-вектора в RRF (из config по умолчанию)
        """
        self.service_code = service_code
        self.is_platform = get_platform_status(service_code)
        self.use_hybrid_search = use_hybrid_search and BM25_AVAILABLE

        # Multi-Vector Search — основной поисковый движок
        self.mv_search = MultiVectorSearch(
            title_weight=mv_title_weight,
            summary_weight=mv_summary_weight,
            content_weight=mv_content_weight
        )

        # BM25 retriever (инициализируется лениво при первом использовании)
        self.bm25_retriever = None
        self._bm25_documents: List[str] = []
        self._bm25_metadatas: List[Dict] = []

        if use_hybrid_search and not BM25_AVAILABLE:
            logger.warning(
                "[ContextRetrievalAgent] Hybrid Search requested but BM25 not available. "
                "Falling back to Multi-Vector only."
            )
            self.use_hybrid_search = False

        logger.info(
            "[ContextRetrievalAgent] Initialized for service='%s', platform=%s, "
            "hybrid=%s, mv_weights=(title=%.2f, summary=%.2f, content=%.2f)",
            service_code, self.is_platform, self.use_hybrid_search,
            mv_title_weight, mv_summary_weight, mv_content_weight
        )

    def retrieve_context(
        self,
        business_requirements: str,
        requirement_types: Optional[List[str]] = None,
        target_system: Optional[str] = None,
        top_k: int = 50,
        use_query_expansion: bool = True,
        bm25_weight: float = 0.3,
        mv_weight: float = 0.7
    ) -> ContextMap:
        """
        Формирует структурированную карту контекста.

        Args:
            business_requirements: Текст бизнес-требований
            requirement_types: Фильтр по типам требований (None = все типы)
            target_system: Фильтр по смежной системе для интеграций
            top_k: Количество страниц в итоговой карте
            use_query_expansion: Декомпозировать запрос через LLM (рекомендуется)
            bm25_weight: Вес BM25 при гибридном ранжировании (актуально если use_hybrid_search=True)
            mv_weight: Вес Multi-Vector при гибридном ранжировании

        Returns:
            ContextMap со структурированным контекстом
        """
        logger.info(
            "[retrieve_context] <- service=%s, types=%s, system=%s, top_k=%d, expansion=%s",
            self.service_code, requirement_types, target_system, top_k, use_query_expansion
        )

        # 1. Поиск страниц с подтверждёнными требованиями
        if use_query_expansion:
            confirmed = self._search_with_query_expansion(
                business_requirements,
                requirement_types,
                target_system,
                top_k
            )
        else:
            confirmed = self._search_confirmed_reqs(
                business_requirements,
                requirement_types,
                target_system,
                top_k
            )

        logger.info("[retrieve_context] Found %d confirmed pages", len(confirmed))

        # 1a. Обязательный sub-запрос по integration-страницам.
        # Integration-страницы часто вытесняются из топ-N основным поиском, потому что
        # dataModel и function страниц численно больше и они семантически ближе к большинству
        # бизнес-требований. Отдельный sub-запрос гарантирует их присутствие в карте контекста
        # независимо от топа.
        # Sub-запрос пропускается только если caller явно задал фильтр по типам и
        # "integration" в этот фильтр не входит.
        types_exclude_integration = (
            requirement_types is not None
            and "integration" not in requirement_types
        )
        if CONTEXT_INTEGRATION_TOP_K > 0 and not types_exclude_integration:
            integration_pages = self._fetch_integration_pages(
                business_requirements=business_requirements,
                target_system=target_system,
                top_k=CONTEXT_INTEGRATION_TOP_K
            )
            if integration_pages:
                existing_ids = {p.page_id for p in confirmed}
                new_integration = [p for p in integration_pages if p.page_id not in existing_ids]
                confirmed = confirmed + new_integration
                logger.info(
                    "[retrieve_context] Integration sub-query added %d new pages "
                    "(total confirmed: %d)",
                    len(new_integration), len(confirmed)
                )

        # 2. Проверка Confluence на незавершённые изменения
        pending = self._check_confluence_for_pending(confirmed)
        logger.info("[retrieve_context] Found %d pages with pending changes", len(pending))

        # 3. Смежные системы из интеграций
        related_systems = self._extract_related_systems(confirmed)
        logger.info("[retrieve_context] Related systems: %s", related_systems)

        # 4. Классификация
        affected, conflicting = self._classify_pages(confirmed, business_requirements)
        logger.info(
            "[retrieve_context] Classification: affected=%d, conflicting=%d",
            len(affected), len(conflicting)
        )

        # 5. Группировка по типам
        by_type = self._group_by_type(confirmed)

        # 6. Формирование карты контекста
        context_map = ContextMap(
            service_code=self.service_code,
            is_platform=self.is_platform,
            confirmed_pages=confirmed,
            pages_with_pending_changes=pending,
            potentially_affected_pages=affected,
            pages_with_conflicts=conflicting,
            related_systems=related_systems,
            pages_by_type=by_type,
            total_confirmed_pages=len(confirmed),
            total_pages_with_pending=len(pending),
            total_pages_with_conflicts=len(conflicting)
        )

        logger.info(
            "[retrieve_context] -> Context map: confirmed=%d, pending=%d, conflicts=%d",
            context_map.total_confirmed_pages,
            context_map.total_pages_with_pending,
            context_map.total_pages_with_conflicts
        )

        return context_map

    # ========================================================================
    # QUERY EXPANSION ЧЕРЕЗ LLM
    # ========================================================================

    def _search_with_query_expansion(
        self,
        business_requirements: str,
        requirement_types: Optional[List[str]] = None,
        target_system: Optional[str] = None,
        top_k: int = 50
    ) -> List[PageContext]:
        """Поиск с декомпозицией запроса через LLM."""
        logger.debug(
            "[_search_with_query_expansion] <- types='%s'", requirement_types
        )

        query_specs = self._generate_search_queries_with_llm(
            business_requirements, requirement_types
        )

        if not query_specs:
            logger.warning("[_search_with_query_expansion] No queries generated, using original text")
            query_specs = [{'query': business_requirements, 'types': None}]

        logger.info(
            "[_search_with_query_expansion] Generated %d specialized queries", len(query_specs)
        )

        all_pages: List[PageContext] = []
        seen_page_ids: Set[str] = set()
        k_per_query = max(5, top_k // len(query_specs))

        for i, spec in enumerate(query_specs, 1):
            query = spec['query']
            types_filter = spec.get('types')
            reason = spec.get('reason', '')

            logger.info(
                "[_search_with_query_expansion] Query %d/%d: types=%s, query='%s'",
                i, len(query_specs), types_filter, query[:150]
            )
            if reason:
                logger.debug("[_search_with_query_expansion] Reason: %s", reason)

            pages = self._search_confirmed_reqs(
                query=query,
                requirement_types=types_filter,
                target_system=target_system,
                top_k=k_per_query
            )

            new_pages = 0
            for page in pages:
                if page.page_id not in seen_page_ids:
                    all_pages.append(page)
                    seen_page_ids.add(page.page_id)
                    new_pages += 1

            logger.info(
                "[_search_with_query_expansion] Query %d: %d pages (%d new, %d duplicates)",
                i, len(pages), new_pages, len(pages) - new_pages
            )

        all_pages = all_pages[:top_k]
        logger.info(
            "[_search_with_query_expansion] -> Total unique pages: %d", len(all_pages)
        )
        return all_pages

    def _generate_search_queries_with_llm(
        self,
        business_requirements: str,
        requirement_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Генерирует специализированные поисковые запросы через LLM.

        Returns:
            [{'query': str, 'types': List[str], 'reason': str}, ...]
        """
        logger.info(
            "[_generate_search_queries_with_llm] <- '%s', types='%s'",
            business_requirements[:200], requirement_types
        )

        types_to_search = requirement_types or [
            "dataModel",
            "function",
            "screenItemForm",
            "screenListForm",
            "integration",
            "process",
            "states",
            "control",
            "printForm",
            "notification"
        ]

        prompt_template = """Ты — эксперт по анализу бизнес-требований к системе ДБО (Дистанционное Банковское Обслуживание).

Твоя задача: из бизнес-требования сгенерировать поисковые запросы для поиска функциональных требований в базе знаний.

Бизнес-требование:
{business_requirement}

Типы функциональных требований в базе:
1. dataModel — модели данных (описания сущностей и их атрибутов)
2. function — функции (операции, действия пользователя)
3. screenItemForm — экранные формы создания/редактирования/просмотра
4. screenListForm — экранные формы просмотра списков
5. integration — интеграции с другими системами (ЕСК, АБС Ф1, ТЕССА, ПЦ и т.д.)
6. process — бизнес-процессы (жизненные циклы) обработки заявок и их подпроцессы
7. states — статусы и состояния
8. control — контроли и проверки
9. printForm - печатные формы
10. notification - нотификации пользователей (под колокольчик, смс, email и т.д.)

Инструкция:
1. Проанализируй бизнес-требование и определи доменные объекты.
2. Перечисли ВСЕ типы требований из списка, которые могут быть релевантны.
3. Для каждого потенциально релевантного типа сгенерируй поисковый запрос.
4. Один тип требования может породить несколько поисковых запросов, если это оправдано.

Формат ответа — JSON массив объектов:
[
  {{
    "type": "dataModel",
    "query": "Модель данных <объект> атрибуты поля <ключевые слова>",
    "reason": "Для добавления поля нужна модель данных"
  }},
  {{
    "type": "function",
    "query": "Функция <действие> <объект>",
    "reason": "Нужна функция для работы с объектом"
  }}
]

ВАЖНО:
- Не генерируй запросы для типов, которые точно не нужны
- Один тип может породить несколько запросов

Верни ТОЛЬКО JSON, без дополнительных пояснений."""

        try:
            llm = get_llm()
            prompt = PromptTemplate(
                input_variables=["business_requirement"],
                template=prompt_template
            )
            chain = prompt | llm
            logger.debug("[_generate_search_queries_with_llm] Calling LLM...")

            result = chain.invoke({"business_requirement": business_requirements})

            result_text = result.content if hasattr(result, 'content') else str(result)

            logger.info(
                "[_generate_search_queries_with_llm] LLM response: %s", result_text
            )

            result_text = re.sub(r'```json\s*', '', result_text)
            result_text = re.sub(r'```\s*$', '', result_text)
            result_text = result_text.strip()

            parsed = json.loads(result_text)

            if not isinstance(parsed, list):
                logger.warning(
                    "[_generate_search_queries_with_llm] LLM returned non-list: %s", type(parsed)
                )
                return [{'query': business_requirements, 'types': None}]

            queries = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                req_type = item.get('type')
                query = item.get('query')
                if not query:
                    continue
                if requirement_types and req_type not in requirement_types:
                    continue
                queries.append({
                    'query': query,
                    'types': [req_type] if req_type else None,
                    'reason': item.get('reason', '')
                })

            logger.info(
                "[_generate_search_queries_with_llm] -> Generated %d queries", len(queries)
            )
            return queries

        except json.JSONDecodeError as e:
            logger.error(
                "[_generate_search_queries_with_llm] JSON parse error: %s", str(e)
            )
            return [{'query': business_requirements, 'types': None}]

        except Exception as e:
            logger.error(
                "[_generate_search_queries_with_llm] Error: %s", str(e), exc_info=True
            )
            return [{'query': business_requirements, 'types': None}]

    # ========================================================================
    # ПОИСК — MULTI-VECTOR
    # ========================================================================

    def _search_confirmed_reqs(
        self,
        query: str,
        requirement_types: Optional[List[str]] = None,
        target_system: Optional[str] = None,
        top_k: int = 50
    ) -> List[PageContext]:
        """
        Поиск страниц с требованиями через Multi-Vector Search.

        MultiVectorSearch ищет по трём слоям (title, summary, content/chunks),
        объединяет через RRF и возвращает список SearchResult, уже дедуплицированных
        по page_id. Здесь конвертируем в PageContext.
        """
        logger.debug(
            "[_search_confirmed_reqs] <- query='%s', types='%s', target_system='%s', top_k=%d",
            query[:100], requirement_types, target_system, top_k
        )

        search_results: List[SearchResult] = self.mv_search.search(
            query=query,
            requirement_types=requirement_types,
            service_code=self.service_code,
            target_system=target_system,
            top_k=top_k
        )

        logger.debug(
            "[_search_confirmed_reqs] MultiVectorSearch returned %d results", len(search_results)
        )

        contexts = self._convert_search_results_to_contexts(search_results)

        logger.info(
            "[_search_confirmed_reqs] -> %d contexts (types filter: %s)",
            len(contexts), requirement_types
        )

        return contexts

    def _fetch_integration_pages(
        self,
        business_requirements: str,
        target_system: Optional[str] = None,
        top_k: int = 10
    ) -> List[PageContext]:
        """
        Обязательный sub-запрос по integration-страницам сервиса.

        Integration-страницы описывают взаимодействие с внешними системами (АБС Ф1, ЕСК,
        ТЕССА и т.д.). При широком поиске они вытесняются из топ-N страницами с моделями
        данных и функциями, которых численно больше. Этот метод гарантирует их присутствие
        в карте контекста.

        Семантический запрос строится из бизнес-требования так же, как и основной поиск.
        Если передан target_system — фильтруем дополнительно по нему.

        Args:
            business_requirements: Текст бизнес-требований для семантического поиска.
            target_system: Опциональный фильтр по смежной системе (например, "ABS_F1").
            top_k: Максимальное число integration-страниц для извлечения.

        Returns:
            Список PageContext для integration-страниц сервиса.
        """
        logger.debug(
            "[_fetch_integration_pages] <- top_k=%d, target_system=%s",
            top_k, target_system
        )

        pages = self._search_confirmed_reqs(
            query=business_requirements,
            requirement_types=["integration"],
            target_system=target_system,
            top_k=top_k
        )

        logger.info(
            "[_fetch_integration_pages] -> Found %d integration pages",
            len(pages)
        )

        return pages

    def _convert_search_results_to_contexts(
        self,
        search_results: List[SearchResult]
    ) -> List[PageContext]:
        """
        Конвертирует SearchResult (из MultiVectorSearch) в PageContext.

        SearchResult уже дедуплицирован по page_id внутри MultiVectorSearch._reciprocal_rank_fusion.
        Поэтому один PageContext = одна страница Confluence.
        """
        contexts = []
        for result in search_results:
            context = PageContext(
                page_id=result.page_id,
                title=result.title,
                requirement_type=result.requirement_type,
                source="chromadb",
                status="confirmed",
                content_preview=result.content_preview,
                metadata=result.metadata,
                relevance_score=result.combined_score,
                mv_title_rank=result.title_rank,
                mv_summary_rank=result.summary_rank,
                mv_content_rank=result.content_rank,
                has_pending_changes=False,
                target_system=result.metadata.get("target_system")
            )
            contexts.append(context)
        return contexts

    # ========================================================================
    # BM25 ПОВЕРХ MULTI-VECTOR (опциональный гибридный режим)
    # ========================================================================

    def _initialize_bm25_if_needed(self, service_code: str):
        """
        Инициализирует BM25 retriever при первом использовании.

        Загружает только content/chunk документы сервиса из ChromaDB
        (title и summary не нужны для лексического поиска).
        """
        if self.bm25_retriever is not None:
            return

        logger.info("[_initialize_bm25] Loading content documents for BM25 indexing...")

        try:
            vectorstore = self.mv_search._get_vectorstore()

            all_docs_results = vectorstore.get(
                where={
                    "$and": [
                        {"service_code": {"$eq": service_code}},
                        {"doc_type": {"$eq": "requirement"}},
                        {"vector_type": {"$in": ["content", "chunk"]}}
                    ]
                },
                include=['documents', 'metadatas']
            )

            if not all_docs_results or not all_docs_results.get('documents'):
                logger.warning("[_initialize_bm25] No content documents found for BM25 indexing")
                self._bm25_documents = []
                self._bm25_metadatas = []
                return

            self._bm25_documents = all_docs_results['documents']
            self._bm25_metadatas = all_docs_results['metadatas']

            logger.info("[_initialize_bm25] Loaded %d documents", len(self._bm25_documents))

            self.bm25_retriever = RussianBM25Retriever(
                self._bm25_documents,
                self._bm25_metadatas
            )

            logger.info("[_initialize_bm25] BM25 retriever initialized")

        except Exception as e:
            logger.error("[_initialize_bm25] Error: %s", str(e))
            self._bm25_documents = []
            self._bm25_metadatas = []

    # ========================================================================
    # ПРОВЕРКА CONFLUENCE НА НЕЗАВЕРШЁННЫЕ ИЗМЕНЕНИЯ
    # ========================================================================

    def _check_confluence_for_pending(
        self,
        confirmed: List[PageContext]
    ) -> List[PageContext]:
        """
        Проверяет страницы Confluence на наличие незавершённых изменений.

        Поскольку confirmed уже дедуплицирован по page_id (MultiVectorSearch),
        итерируем напрямую без дополнительной дедупликации.
        """
        logger.debug("[_check_confluence_for_pending] <- %d pages to check", len(confirmed))

        pending = []

        for page_ctx in confirmed:
            page_id = page_ctx.page_id
            try:
                page_data = get_page_data_cached(page_id)

                if not page_data:
                    logger.warning(
                        "[_check_confluence_for_pending] Could not load page %s", page_id
                    )
                    continue

                full_content = page_data.get('full_content', '')
                approved_content = page_data.get('approved_content', '')

                if full_content == approved_content:
                    continue

                pending_content = self._extract_pending_diff(full_content, approved_content)

                if not pending_content:
                    continue

                page_ctx.has_pending_changes = True
                page_ctx.pending_content = pending_content

                pending_page = PageContext(
                    page_id=page_id,
                    title=page_ctx.title,
                    requirement_type=page_ctx.requirement_type,
                    source="confluence",
                    status="pending",
                    content_preview=pending_content[:300],
                    metadata=page_ctx.metadata,
                    relevance_score=page_ctx.relevance_score,
                    has_pending_changes=True,
                    pending_content=pending_content,
                    target_system=page_ctx.target_system
                )
                pending.append(pending_page)

                logger.debug(
                    "[_check_confluence_for_pending] Found pending on page %s (%d chars)",
                    page_id, len(pending_content)
                )

            except Exception as e:
                logger.warning(
                    "[_check_confluence_for_pending] Error checking page %s: %s",
                    page_id, str(e)
                )

        logger.debug(
            "[_check_confluence_for_pending] -> %d pages with pending", len(pending)
        )

        return pending

    def _extract_pending_diff(self, full: str, approved: str) -> str:
        """Извлекает незавершённые изменения через difflib."""
        if not full or not approved or full == approved:
            return ""

        import difflib

        differ = difflib.Differ()
        diff = list(differ.compare(
            approved.splitlines(keepends=True),
            full.splitlines(keepends=True)
        ))

        added_lines = []
        for line in diff:
            if line.startswith('+ '):
                added_lines.append(line[2:])

        pending_content = ''.join(added_lines).strip()
        return pending_content if pending_content else ""

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def _extract_related_systems(self, pages: List[PageContext]) -> List[str]:
        """Извлекает список смежных систем из интеграционных страниц."""
        systems: Set[str] = set()
        for page in pages:
            if page.target_system:
                systems.add(page.target_system)
        return sorted(list(systems))

    def _classify_pages(
        self,
        pages: List[PageContext],
        business_requirements: str
    ) -> Tuple[List[PageContext], List[PageContext]]:
        """Классифицирует страницы на затрагиваемые и конфликтующие."""
        sorted_pages = sorted(pages, key=lambda p: p.relevance_score, reverse=True)
        threshold = 10
        affected = sorted_pages[:threshold]
        conflicting = [p for p in affected if p.has_pending_changes]
        return affected, conflicting

    def _group_by_type(self, pages: List[PageContext]) -> Dict[str, List[PageContext]]:
        """Группирует страницы по типам требований."""
        by_type: Dict[str, List[PageContext]] = defaultdict(list)
        for page in pages:
            req_type = page.requirement_type or "unknown"
            by_type[req_type].append(page)
        return dict(by_type)

    # ========================================================================
    # ПУБЛИЧНЫЕ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def get_pages_by_type(
        self,
        context_map: ContextMap,
        requirement_type: str
    ) -> List[PageContext]:
        """Извлекает все страницы с требованиями конкретного типа."""
        return context_map.pages_by_type.get(requirement_type, [])

    def get_integration_pages_by_system(
        self,
        context_map: ContextMap,
        target_system: str
    ) -> List[PageContext]:
        """Извлекает все страницы с интеграциями для конкретной смежной системы."""
        integration_pages = context_map.pages_by_type.get("integration", [])
        return [p for p in integration_pages if p.target_system == target_system]

    def format_context_summary(self, context_map: ContextMap) -> str:
        """Форматирует карту контекста в текстовое резюме."""
        lines = [
            f"=== Context Summary for {context_map.service_code} ===",
            f"Platform service: {context_map.is_platform}",
            "",
            "Pages:",
            f"  - With confirmed requirements: {context_map.total_confirmed_pages}",
            f"  - With pending changes: {context_map.total_pages_with_pending}",
            f"  - With conflicts: {context_map.total_pages_with_conflicts}",
            "",
            f"Related systems: {', '.join(context_map.related_systems) or 'None'}",
            "",
            "Pages by requirement type:"
        ]

        for req_type, pages in sorted(context_map.pages_by_type.items()):
            lines.append(f"  - {req_type}: {len(pages)} pages")

        if context_map.potentially_affected_pages:
            lines.append("")
            lines.append("Top affected pages:")
            for i, page in enumerate(context_map.potentially_affected_pages[:5], 1):
                conflict_mark = " [CONFLICT]" if page.has_pending_changes else ""
                mv_info = (
                    f"T={page.mv_title_rank or '-'} "
                    f"S={page.mv_summary_rank or '-'} "
                    f"C={page.mv_content_rank or '-'}"
                )
                lines.append(
                    f"  {i}. [{page.page_id}] {page.title}{conflict_mark} "
                    f"(score={page.relevance_score:.4f}, MV ranks: {mv_info})"
                )

        return "\n".join(lines)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def create_context_agent(
    service_code: str,
    use_hybrid_search: bool = True
) -> ContextRetrievalAgent:
    """
    Фабричная функция для создания агента.

    Args:
        service_code: Код сервиса
        use_hybrid_search: Дополнять Multi-Vector BM25 (требует rank-bm25, pymorphy2)

    Returns:
        Экземпляр ContextRetrievalAgent
    """
    return ContextRetrievalAgent(service_code, use_hybrid_search=use_hybrid_search)