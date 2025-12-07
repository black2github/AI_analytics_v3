# app/template_registry.py

import json
import logging
import os
from typing import Optional, Dict, List
from app.embedding_store import get_vectorstore, prepare_unified_documents
from app.confluence_loader import load_pages_by_ids
from app.llm_interface import get_embeddings_model
from app.config import UNIFIED_STORAGE_NAME, TEMPLATES_REGISTRY_FILE
from app.service_registry import get_platform_status

logger = logging.getLogger(__name__)


def load_template_types() -> Dict[str, str]:
    """Загружает типы шаблонов из templates.json"""
    try:
        template_file_path = os.path.join(os.path.dirname(__file__), "data", TEMPLATES_REGISTRY_FILE)
        with open(template_file_path, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("templates", {})
    except Exception as e:
        logging.exception("Ошибка при чтении templates.json: %s", e)
        return {}


def get_template_by_type(requirement_type: str) -> Optional[str]:
    """Получает шаблон по типу требования из единого хранилища"""
    logger.debug("[get_template_by_type] <- requirement type='%s'", requirement_type)

    embeddings_model = get_embeddings_model()
    store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

    filters = {
        "$and": [
            {"doc_type": {"$eq": "template"}},
            {"requirement_type": {"$eq": requirement_type}}
        ]
    }

    logger.debug("[get_template_by_type] filters='%s'", filters)
    matches = store.similarity_search("", filter=filters)

    if matches:
        logger.debug("[get_template_by_type] -> Found template for type '%s'", requirement_type)
        return matches[0].page_content

    logger.warning("[get_template_by_type] -> No template found for type '%s'", requirement_type)
    return None


def store_templates(templates: Dict[str, str]) -> int:
    """
    Сохраняет шаблоны требований в единое хранилище.

    Args:
        templates: Словарь {requirement_type: page_id}

    Returns:
        Количество успешно сохранённых шаблонов
    """
    logger.info("[store_templates] <- Storing %d templates", len(templates))

    embeddings_model = get_embeddings_model()
    store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)
    docs_to_store = []

    for requirement_type, page_id in templates.items():
        logger.debug("[store_templates] Processing template type='%s', page_id='%s'", requirement_type, page_id)

        # Удаляем старую версию шаблона если есть
        try:
            store.delete(where={
                "$and": [
                    {"doc_type": {"$eq": "template"}},
                    {"requirement_type": {"$eq": requirement_type}}
                ]
            })
            logger.debug("[store_templates] Deleted old template for type '%s'", requirement_type)
        except Exception as e:
            logger.warning("[store_templates] Could not delete old template for type '%s': %s", requirement_type,
                           str(e))

        # Загружаем новую версию
        pages = load_pages_by_ids([page_id])
        if not pages:
            logger.warning("[store_templates] Could not load page '%s' for template type '%s'", page_id,
                           requirement_type)
            continue

        page = pages[0]

        # Создаем документы с новой схемой метаданных
        docs = prepare_unified_documents(
            pages=[page],
            service_code="templates",  # Специальный код для шаблонов
            doc_type="template",
            requirement_type=requirement_type,
            source="DBOCORPESPLN"  # По умолчанию
        )

        docs_to_store.extend(docs)

    if docs_to_store:
        store.add_documents(docs_to_store)

    logger.info("[store_templates] -> Successfully stored %d template documents", len(docs_to_store))
    return len(docs_to_store)


def get_all_template_types() -> List[str]:
    """Возвращает список всех доступных типов шаблонов"""
    templates = load_template_types()
    return list(templates.keys())