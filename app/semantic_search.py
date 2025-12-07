# app/semantic_search.py

import logging
import re
from typing import List, Set, Optional
from langchain_core.documents import Document  # ДОБАВЛЯЕМ ИМПОРТ
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable  # Добавлен для типизации LCEL (необязательно, но полезно)
# from langchain.chains.llm import LLMChain
# from langchain_community.chains import LLMChain # УДАЛЕНО: Заменено на LCEL
from app.embedding_store import get_vectorstore
from app.llm_interface import get_llm
from app.config import UNIFIED_STORAGE_NAME

logger = logging.getLogger(__name__)


def extract_key_queries(requirements_text: str) -> List[str]:
    """
    Извлекает ключевые запросы + специальные запросы для сущностей через LLM
    """
    logger.info("[extract_key_queries] <- text length: %d chars", len(requirements_text))

    if not requirements_text.strip():
        return []

    # 1. СНАЧАЛА извлекаем специальные запросы для сущностей
    entity_queries = extract_entity_attribute_queries(requirements_text)

    # 2. ЗАТЕМ извлекаем обычные ключевые запросы с помощью LLM
    regular_queries = _extract_regular_key_queries_with_llm(requirements_text)

    # 3. Объединяем (приоритет у LLM запросов)
    all_queries = regular_queries + entity_queries

    # 4. Ограничиваем общее количество
    logger.info("[extract_key_queries] -> queries: %s", all_queries[:12])
    return all_queries[:12]


def _extract_regular_key_queries_with_llm(requirements_text: str) -> List[str]:
    """
    Извлекает обычные ключевые запросы с помощью LLM
    """
    # Ограничиваем длину входного текста для анализа
    max_input_length = 2000
    if len(requirements_text) > max_input_length:
        requirements_text = requirements_text[:max_input_length] + "..."

    prompt_template = """
Проанализируй текст требований и извлеки ключевые запросы для поиска связанных требований.

Текст требований:
{requirements}

Извлеки:
1. Технические термины и компоненты (API, базы данных, сервисы)
2. Бизнес-сущности (клиенты, продукты, операции)
3. Процессы и функции (авторизация, валидация, обработка)
4. Форматы и стандарты (JSON, XML, протоколы)

Верни 5-6 наиболее важных ключевых запросов, каждый на новой строке:
"""

    try:
        llm = get_llm()
        prompt = PromptTemplate(
            input_variables=["requirements"],
            template=prompt_template
        )

        # --- ИСПРАВЛЕНИЕ: Замена LLMChain на LCEL ---
        chain = prompt | llm

        # Для запуска LCEL-цепочки используем .invoke() и .content
        result = chain.invoke({"requirements": requirements_text}).content
        # ---------------------------------------------

        logger.debug("[_extract_regular_key_queries_with_llm] Raw LLM result: %s", str(result))

        # Парсим результат
        queries = []
        for line in result.split('\n'):
            line = line.strip()
            line = re.sub(r'^\d+\.\s*[-+*]*', '', line)
            line = re.sub(r'^\[\[', '[', line)
            # line = re.sub(r'[\]+*-]+$', '', line)
            line = re.sub(r'[\]+*-]+[\s-\s]*[А-ЯЁа-яёA-Za-z\s\,\.\(\)]*$', '',
                          line)  # после запроса через '-' может идти пояснение
            if line and len(line) > 2:
                queries.append(line)

        queries = queries[:6]  # Ограничиваем для LLM запросов

        logger.debug("[_extract_regular_key_queries_with_llm] extracted LLM queries = %s", queries)
        logger.info("[_extract_regular_key_queries_with_llm] -> extracted %d LLM queries", len(queries))

        return queries

    except Exception as e:
        logging.error("[_extract_regular_key_queries_with_llm] Error extracting queries: %s", str(e))
        return extract_simple_keywords(requirements_text)


def extract_entity_attribute_queries(requirements_text: str) -> List[str]:
    """
    Формирует запросы для поиска в хранилище моделей данных сущностей и их атрибутов
    """
    logger.info("[extract_entity_attribute_queries] <- text length: %d chars", len(requirements_text))

    entity_queries = []

    # Извлекаем все цепочки сущность.атрибут
    entity_chains = _extract_entity_chains(requirements_text)

    for chain in entity_chains:
        entities = chain['entities']
        final_attribute = chain['final_attribute']

        # Создаем запросы для каждой сущности в цепочке
        for entity_name in entities:
            if len(entity_name.split()) <= 5:  # Ограничение: не более 5 слов
                # Создаем специализированные запросы для поиска модели данных
                queries = [
                    f'Атрибутный состав сущности {entity_name}',
                    f'модель данных {entity_name}',
                    f'{entity_name} атрибут',
                    f'Наименование поля',
                    f'{entity_name} реквизит'
                ]

                # Если есть финальный атрибут, добавляем его в запросы
                if final_attribute:
                    queries.extend([
                        f'модель данных {entity_name} {final_attribute}',
                        f'{entity_name} атрибут {final_attribute}',
                        f'Наименование поля {final_attribute}',
                        f'{entity_name} реквизит {final_attribute}'
                    ])

                entity_queries.extend(queries)
                logger.debug("[extract_entity_attribute_queries] Found entity: '%s', final_attribute: '%s'",
                             entity_name, final_attribute)

    # Удаляем дубликаты
    unique_queries = list(dict.fromkeys(entity_queries))

    logger.info("[extract_entity_attribute_queries] -> extracted %d entity queries from %d chains",
                len(unique_queries), len(entity_chains))

    return unique_queries


def _extract_entity_chains(text: str) -> List[dict]:
    """
    Извлекает цепочки сущность.атрибут на основе правил оформления
    """
    chains = []

    chain_patterns = [
        # 1. Цепочки и иерархические ссылки
        r'\[([\[\]\s\w]{1,50})\]\.<\[([\[\]\s\w]{1,50})\]>\.<([^>]{1,50})>',  # [Сущ1].<[Сущ2]>.<атр>
        r'\[([\[\]\s\w]{1,50})\]\.<\[([\[\]\s\w]{1,50})\]>\.\"([^\"]{1,50})\"',  # [Сущ1].<[Сущ2]>."атр"

        r'"([^"]{1,50})"\."([^"]{1,50})"\.<([^>]{1,50})>',
        r'"([^"]{1,50})"\."([^"]{1,50})"\."([^"]{1,50})"',

        r"'([^']{1,50})'\.'([^']{1,50})'\.<([^>]{1,50})>",

        # 2. Одиночные ссылки в квадратных скобках
        r'\[([\[\]\s\w]{1,50})\]\.<([^>]{1,50})>',  # [Название].<атрибут>
        r'\[([\[\]\s\w]{1,50})\]\."([^"]{1,50})"',  # [Название]."атрибут"
        r'\[([\[\]\s\w]{1,50})\]\.\'([^\']{1,50})\'',  # [Название].'атрибут'

        # 3. Кавычки
        r'"([^"]{1,50})"\.<([^>]{1,50})>',
        r'"([^"]{1,50})"\."([^"]{1,50})"',

        r"'([^']{1,50})'\.<([^>]{1,50})>",
        r"'([^']{1,50})'\.'([^']{1,50})'",

        # 4. Простые названия (в последнюю очередь)
        r'\b([А-Яа-яA-Za-z][А-Яа-яA-Za-z0-9_]{2,49})\.<([^>]{1,50})>',
        r'\b([А-Яа-яA-Za-z][А-Яа-яA-Za-z0-9_]{2,49})\."([^"]{1,50})"',
    ]

    for pattern in chain_patterns:
        matches = re.finditer(pattern, text, re.UNICODE)

        for match in matches:
            # Получаем все группы (исключаем None)
            groups = [g.strip() for g in match.groups() if g and g.strip()]

            if len(groups) >= 2:
                # Все группы кроме последней - сущности
                entities = groups[:-1]
                # Последняя группа - атрибут
                final_attribute = groups[-1]

                # Фильтрация простых названий
                filtered_entities = []
                for entity in entities:
                    # Проверяем, что сущность не является стоп-словом
                    if (len(entity.split()) <= 5 and
                            len(entity) >= 3 and
                            entity.lower() not in ['или', 'для', 'при', 'как', 'что', 'это', 'проверить', 'значение']):
                        filtered_entities.append(entity)

                if filtered_entities and final_attribute:
                    # Проверяем, что такая цепочка еще не найдена
                    chain_key = (tuple(filtered_entities), final_attribute)
                    existing_chain = any(
                        (tuple(chain['entities']), chain['final_attribute']) == chain_key
                        for chain in chains
                    )

                    if not existing_chain:
                        chains.append({
                            'entities': filtered_entities,
                            'final_attribute': final_attribute,
                            'full_match': match.group(0)
                        })

                        logger.debug("[_extract_entity_chains] Pattern matched: entities=%s, attribute='%s'",
                                     filtered_entities, final_attribute)

    return chains


def extract_simple_keywords(text: str) -> List[str]:
    """
    Запасной метод: простое извлечение ключевых слов без LLM
    """
    logger.info("[extract_simple_keywords] Fallback keyword extraction")

    # Технические термины, которые часто встречаются в требованиях
    technical_terms = {
        'api', 'json', 'xml', 'rest', 'soap', 'http', 'https',
        'авторизация', 'аутентификация', 'токен', 'jwt',
        'сущность', 'процесс', 'алгоритм', 'таблица',
        'клиент', 'пользователь', 'продукт', 'услуга',
        'справочник', 'каталог', 'реестр',
        'обработка', 'валидация', 'проверка',
        'уведомление', 'нотификация', 'сообщение',
        'форма', 'экран', 'интерфейс',
        'отчет', 'печать', 'документ'
    }

    text_lower = text.lower()
    found_terms = []

    for term in technical_terms:
        if term in text_lower:
            found_terms.append(term)

    # Добавляем слова длиннее 4 символов, встречающиеся часто
    words = re.findall(r'\b[а-яё]{4,}\b', text_lower)
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1

    # Берем часто встречающиеся слова
    frequent_words = [word for word, freq in word_freq.items() if freq >= 2]
    found_terms.extend(frequent_words[:5])

    return found_terms[:8]


def deduplicate_documents(docs: List) -> List:
    """
    Удаляет дублирующиеся документы на основе page_id и содержимого
    """
    seen_pages = set()
    seen_content = set()
    unique_docs = []

    for doc in docs:
        page_id = doc.metadata.get('page_id')
        content_hash = hash(doc.page_content[:200])  # Хеш первых 200 символов

        if page_id not in seen_pages and content_hash not in seen_content:
            seen_pages.add(page_id)
            seen_content.add(content_hash)
            unique_docs.append(doc)

    logger.debug("[deduplicate_documents] Filtered %d -> %d documents", len(docs), len(unique_docs))
    return unique_docs


def search_by_entity_title(entity_names: List[str], service_code: str, exclude_page_ids: Optional[List[str]],
                           embeddings_model) -> List:
    """
    Поиск в едином хранилище страниц с точным совпадением title с именем сущности.
    Обновлено для работы с unified_requirements.
    """
    logger.debug("[search_by_entity_title] <- Searching by exact title match for entities: %s", entity_names)

    if not entity_names:
        return []

    store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)
    found_docs = []

    # Очищаем названия сущностей
    cleaned_entity_names = [name.strip() for name in entity_names if name.strip()]
    if not cleaned_entity_names:
        return []

    # ПОИСК В ПЛАТФОРМЕННОМ dataModel СЕРВИСЕ и сервисе с service code
    platform_docs = unified_search_by_entity_title(cleaned_entity_names, service_code, exclude_page_ids, store)

    found_docs.extend(platform_docs)

    logger.info("[search_by_entity_title] -> Found %d documents by exact title match", len(found_docs))
    return found_docs


def extract_entity_names_from_requirements(requirements_text: str) -> List[str]:
    """
    Извлекает названия сущностей из текста требований для точного поиска по title
    """
    logger.debug("[extract_entity_names_from_requirements] <- Processing text")
    entity_names = []

    # Используем подход с цепочками
    entity_chains = _extract_entity_chains(requirements_text)

    for chain in entity_chains:
        for entity_name in chain['entities']:
            if entity_name not in entity_names and len(entity_name.split()) <= 5:
                entity_names.append(entity_name)

    logger.debug("[extract_entity_names_from_requirements] -> entity names: %s", entity_names)
    return entity_names


def unified_search_by_entity_title(entity_names: List[str], service_code: str, exclude_page_ids: Optional[List[str]],
                                   embeddings_model) -> List[Document]:
    """
    ИЗМЕНЕНО: Теперь возвращает список Document объектов вместо строк.
    Поиск документов по точному совпадению title с именем сущности в едином хранилище.
    """
    logger.info("[unified_search_by_entity_title] <- Searching for entities: %s", entity_names)

    if not entity_names:
        return []

    store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

    # Очищаем названия сущностей
    cleaned_entity_names = [name.strip() for name in entity_names if name.strip()]
    if not cleaned_entity_names:
        return []

    # Один запрос для поиска в dataModel и текущем сервисе
    service_codes = ["dataModel"]
    if service_code != "dataModel":
        service_codes.append(service_code)

    unified_filter = {
        "$and": [
            {"doc_type": {"$eq": "requirement"}},
            {"service_code": {"$in": service_codes}},
            {"title": {"$in": cleaned_entity_names}}
        ]
    }

    # Добавляем исключение page_ids если нужно
    if exclude_page_ids:
        unified_filter["$and"].append({"page_id": {"$nin": exclude_page_ids}})

    logger.debug("[unified_search_by_entity_title] Optimized unified filter: %s", unified_filter)

    try:
        docs = store.similarity_search(
            query="",
            k=len(cleaned_entity_names) * 8,
            filter=unified_filter
        )

        logger.debug("[unified_search_by_entity_title] Found %d docs for entities: %s in services: %s",
                     len(docs), cleaned_entity_names, service_codes)

        # Логируем статистику
        found_entities_by_service = {}
        for doc in docs:
            doc_service = doc.metadata.get('service_code', 'unknown')
            doc_title = doc.metadata.get('title', '')

            if doc_service not in found_entities_by_service:
                found_entities_by_service[doc_service] = set()
            found_entities_by_service[doc_service].add(doc_title)

        for svc, titles in found_entities_by_service.items():
            logger.info("[unified_search_by_entity_title] -> Found entities in %s: %s", svc, sorted(titles))

        return docs

    except Exception as e:
        logger.error("[unified_search_by_entity_title] Error: %s", str(e))
        return []


def search_by_entity_title_old(entity_names: List[str], service_code: str, exclude_page_ids: Optional[List[str]],
                           embeddings_model) -> List[Document]:
    """
    ИЗМЕНЕНО: Теперь возвращает список Document объектов.
    Поиск в едином хранилище страниц с точным совпадением title с именем сущности.
    TODO Что-то не так. Дублирование метода выше.
    """
    logger.debug("[search_by_entity_title] <- Searching by exact title match for entities: %s", entity_names)
    return unified_search_by_entity_title(entity_names, service_code, exclude_page_ids, embeddings_model)