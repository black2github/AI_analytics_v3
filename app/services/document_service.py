# app/services/document_service.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
import logging
from typing import List, Dict, Optional
from app.embedding_store import (get_vectorstore, prepare_unified_documents)
#, get_embeddings_model)
from app.confluence_loader import load_pages_by_ids, get_child_page_ids
from app.llm_interface import get_embeddings_model
from app.service_registry import resolve_service_code_from_pages_or_user, get_platform_status
from app.template_registry import store_templates
from app.config import UNIFIED_STORAGE_NAME

logger = logging.getLogger(__name__)


class DocumentService:
    """Простой сервис для работы с документами без сложных абстракций"""

    def load_approved_pages(self, page_ids: List[str], service_code: Optional[str] = None,
                            source: str = "DBOCORPESPLN") -> Dict:
        """Загружает только подтвержденные требования в единое хранилище"""
        logger.info("[DocumentService.load_approved_pages] <- page_ids=%s, service_code=%s",
                    page_ids, service_code)

        # Определяем код сервиса
        if not service_code:
            service_code = resolve_service_code_from_pages_or_user(page_ids)
            if not service_code:
                raise ValueError("Cannot resolve service_code. Please specify explicitly.")

        # Получаем хранилище
        embeddings_model = get_embeddings_model()
        store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        # Загружаем страницы
        pages = load_pages_by_ids(page_ids)
        if not pages:
            raise ValueError("No pages found.")

        # Фильтруем страницы с подтвержденным содержимым
        pages_with_approved = self._filter_pages_with_approved_content(pages)
        if not pages_with_approved:
            raise ValueError("No pages with approved content found.")

        # Удаляем предыдущие фрагменты
        self._delete_existing_fragments(store, pages_with_approved)

        # Создаем и сохраняем документы
        docs = prepare_unified_documents(
            pages=pages_with_approved,
            service_code=service_code,
            doc_type="requirement",
            source=source
        )

        store.add_documents(docs)

        is_platform = get_platform_status(service_code)

        return {
            "total_pages": len(page_ids),
            "pages_with_approved_content": len(pages_with_approved),
            "documents_created": len(docs),
            "is_platform": is_platform,
            "service_code": service_code,
            "storage": UNIFIED_STORAGE_NAME
        }

    def load_templates_to_storage(self, templates: Dict[str, str]) -> int:
        """Загружает шаблоны в хранилище"""
        return store_templates(templates)

    def get_child_pages_with_optional_load(self, page_id: str, service_code: Optional[str] = None,
                                           source: str = "DBOCORPESPLN") -> Dict:
        """Получает дочерние страницы с опциональной загрузкой"""
        child_page_ids = get_child_page_ids(page_id)
        result = {"page_ids": child_page_ids, "load_result": None}

        if service_code and child_page_ids:
            load_result = self.load_approved_pages(child_page_ids, service_code, source)
            result["load_result"] = load_result

        return result

    def remove_page_fragments(self, page_ids: List[str]) -> int:
        """Удаляет фрагменты требований для указанных страниц"""
        if not page_ids:
            return 0

        embeddings_model = get_embeddings_model()
        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        initial_count = len(vectorstore.get()['ids'])

        vectorstore.delete(where={
            "$and": [
                {"page_id": {"$in": page_ids}},
                {"doc_type": {"$eq": "requirement"}}
            ]
        })

        final_count = len(vectorstore.get()['ids'])
        return initial_count - final_count

    def remove_platform_page_fragments(self, page_ids: List[str], service_code: str) -> int:
        """Удаляет фрагменты платформенных страниц"""
        if not service_code:
            raise ValueError("service_code is required for platform pages")

        if not get_platform_status(service_code):
            raise ValueError(f"Service {service_code} is not a platform service")

        embeddings_model = get_embeddings_model()
        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        initial_count = len(vectorstore.get()['ids'])

        vectorstore.delete(where={
            "$and": [
                {"page_id": {"$in": page_ids}},
                {"service_code": {"$eq": service_code}},
                {"doc_type": {"$eq": "requirement"}},
                {"is_platform": {"$eq": True}}
            ]
        })

        final_count = len(vectorstore.get()['ids'])
        return initial_count - final_count

    def get_storage_info(self) -> Dict:
        """Отладочная информация о хранилище"""

        logger.info("[get_storage_info] <-.")
        embeddings_model = get_embeddings_model()
        store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        if store is None:
            raise ValueError("No vectorstore found.")

        logger.debug("[get_storage_info] store = %s", store)
        data = store.get()

        # Статистика
        doc_type_stats = {}
        platform_stats = {"platform": 0, "regular": 0}
        service_stats = {}

        if data.get('metadatas'):
            for metadata in data['metadatas']:
                if metadata:
                    doc_type = metadata.get('doc_type', 'unknown')
                    doc_type_stats[doc_type] = doc_type_stats.get(doc_type, 0) + 1

                    is_platform = metadata.get('is_platform', False)
                    if is_platform:
                        platform_stats["platform"] += 1
                    else:
                        platform_stats["regular"] += 1

                    service_code = metadata.get('service_code', 'unknown')
                    service_stats[service_code] = service_stats.get(service_code, 0) + 1

        # Добавьте статистику размеров
        content_sizes = []
        if data.get('documents'):
            for doc in data['documents']:
                content_sizes.append(len(doc))

        return {
            "storage_name": UNIFIED_STORAGE_NAME,
            "total_documents": len(data.get('ids', [])),
            "doc_type_stats": doc_type_stats,
            "platform_stats": platform_stats,
            "service_stats": service_stats,
            "sample_metadata": data.get('metadatas', [])[:3] if data.get('metadatas') else [],
            # size in chars
            "avg_document_size": sum(content_sizes) / len(content_sizes) if content_sizes else 0,
            "max_document_size": max(content_sizes) if content_sizes else 0,
            "documents_over_2000_chars": len([s for s in content_sizes if s > 2000]),
            "status": "ok"
        }

    def _filter_pages_with_approved_content(self, pages: List[Dict]) -> List[Dict]:
        """Фильтрует страницы с подтвержденным содержимым"""
        pages_with_approved = []
        for page in pages:
            approved_content = page.get("approved_content", "")
            if approved_content and approved_content.strip():
                pages_with_approved.append(page)
                logger.debug("Page %s has approved content (%d chars)",
                             page["id"], len(approved_content))
            else:
                logger.warning("Page %s has no approved content, skipping", page["id"])
        return pages_with_approved

    def _delete_existing_fragments(self, store, pages: List[Dict]):
        """Удаляет существующие фрагменты страниц"""
        page_ids_to_delete = [p["id"] for p in pages]
        try:
            store.delete(where={
                "$and": [
                    {"page_id": {"$in": page_ids_to_delete}},
                    {"doc_type": {"$eq": "requirement"}}
                ]
            })
            logger.debug("[_delete_existing_fragments] Deleted existing requirement fragments for page_ids: %s", page_ids_to_delete)
        except Exception as e:
            logger.warning("[_delete_existing_fragments] Could not delete existing vectors: %s", e)

    def has_approved_fragments(self, page_ids: List[str]) -> bool:
        """
        Проверяет наличие одобренных фрагментов в хранилище для указанных страниц

        Args:
            page_ids: Список идентификаторов страниц

        Returns:
            True если есть фрагменты хотя бы для одной из страниц
        """
        if not page_ids:
            return False

        logger.info("[has_approved_fragments] <- Checking %d page_ids", len(page_ids))

        try:
            embeddings_model = get_embeddings_model()
            store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

            # Ищем документы с указанными page_id
            filter_query = {
                "$and": [
                    {"doc_type": {"$eq": "requirement"}},
                    {"page_id": {"$in": page_ids}}
                ]
            }

            # Получаем данные с фильтром
            results = store.get(where=filter_query)

            found_count = len(results.get('ids', []))
            has_fragments = found_count > 0

            logger.info("[has_approved_fragments] -> Found %d fragments, result: %s",
                        found_count, has_fragments)

            return has_fragments

        except Exception as e:
            logger.error("[has_approved_fragments] Error: %s", str(e))
            return False

    def get_large_documents_info(self, min_chars: int = 10000) -> Dict:
        """Быстрая информация о больших документах"""
        embeddings_model = get_embeddings_model()
        store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        data = store.get()

        large_docs = []
        for doc_content, metadata in zip(data['documents'], data['metadatas']):
            size = len(doc_content)
            if size >= min_chars:
                large_docs.append({
                    'page_id': metadata.get('page_id'),
                    'title': metadata.get('title', 'No title'),
                    'size_chars': size,
                    'size_tokens_estimate': size // 3,  # Оценка для русского
                    'service_code': metadata.get('service_code')
                })

        # Сортируем по размеру
        large_docs.sort(key=lambda x: x['size_chars'], reverse=True)

        return {
            'total_documents': len(data['documents']),
            'large_documents_count': len(large_docs),
            'large_documents': large_docs[:20],  # Топ-20
            'largest_size_chars': large_docs[0]['size_chars'] if large_docs else 0,
            'largest_size_tokens_estimate': large_docs[0]['size_tokens_estimate'] if large_docs else 0
        }