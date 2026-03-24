# Путь: app/services/document_service.py

import asyncio
import logging
from typing import List, Dict, Optional

from app.confluence_loader import load_pages_by_ids, get_child_page_ids
from app.llm_interface import get_embeddings_model
from app.service_registry import resolve_service_code_from_pages_or_user, get_platform_status
from app.template_registry import store_templates
from app.config import UNIFIED_STORAGE_NAME, CHUNK_SIZE, CHUNK_OVERLAP, INDEXING_MODE
from app.embedding_store import get_vectorstore, prepare_unified_documents
from app.services.multi_vector_indexer import MultiVectorIndexer

logger = logging.getLogger(__name__)


class DocumentService:
    """Сервис для работы с документами. Публичные методы — синхронные,
    предназначены для вызова через anyio.to_thread.run_sync."""

    def load_approved_pages(
        self,
        page_ids: List[str],
        service_code: Optional[str] = None,
        source: str = "DBOCORPESPLN",
        use_llm_summary: bool = False
    ) -> Dict:
        """Загружает подтверждённые требования в хранилище с Multi-Vector индексацией.

        Вызывается из синхронного потока (anyio worker thread).
        Async-часть (генерация summary через LLM) выполняется через asyncio.run().
        """
        logger.info(
            "[load_approved_pages] <- page_ids=%s, service_code=%s, source=%s",
            page_ids, service_code, source
        )

        if not service_code:
            service_code = resolve_service_code_from_pages_or_user(page_ids)
            if not service_code:
                raise ValueError("Cannot resolve service_code. Please specify explicitly.")

        # Выбираем модель и хранилище в зависимости от режима индексации.
        # В legacy-режиме передаём embedding_model=None — get_vectorstore сам
        # выберет all-MiniLM-L6-v2 согласно INDEXING_MODE из config.
        if INDEXING_MODE == "legacy":
            store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=None)
        else:
            embeddings_model = get_embeddings_model()
            store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        pages = load_pages_by_ids(page_ids)
        if not pages:
            raise ValueError("No pages found.")

        pages_with_approved = self._filter_pages_with_approved_content(pages)
        if not pages_with_approved:
            raise ValueError("No pages with approved content found.")

        self._delete_existing_fragments(store, pages_with_approved)

        # Создаём документы в зависимости от режима индексации.
        # legacy       — один документ на страницу, без vector_type, all-MiniLM-L6-v2.
        # multi_vector — title + summary + content/chunk векторы, USER2-base.
        if INDEXING_MODE == "legacy":
            docs = prepare_unified_documents(
                pages=pages_with_approved,
                service_code=service_code,
                doc_type="requirement",
                source=source
            )
        else:
            docs = self._create_multi_vector_documents(
                pages=pages_with_approved,
                service_code=service_code,
                source=source,
                use_llm_summary=use_llm_summary
            )

        store.add_documents(docs)

        is_platform = get_platform_status(service_code)

        logger.info(
            "[load_approved_pages] -> %d documents indexed for service='%s'",
            len(docs), service_code
        )

        return {
            "total_pages": len(page_ids),
            "pages_with_approved_content": len(pages_with_approved),
            "documents_created": len(docs),
            "is_platform": is_platform,
            "service_code": service_code,
            "storage": UNIFIED_STORAGE_NAME
        }

    def load_templates_to_storage(self, templates: Dict[str, str]) -> int:
        """Загружает шаблоны в хранилище."""
        return store_templates(templates)

    def get_child_pages_with_optional_load(
        self,
        page_id: str,
        service_code: Optional[str] = None,
        source: str = "DBOCORPESPLN"
    ) -> Dict:
        """Получает дочерние страницы с опциональной загрузкой."""
        child_page_ids = get_child_page_ids(page_id)
        result = {"page_ids": child_page_ids, "load_result": None}

        if service_code and child_page_ids:
            load_result = self.load_approved_pages(child_page_ids, service_code, source)
            result["load_result"] = load_result

        return result

    def remove_page_fragments(self, page_ids: List[str]) -> int:
        """Удаляет фрагменты требований для указанных страниц."""
        if not page_ids:
            return 0

        embeddings_model = get_embeddings_model()
        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        initial_count = len(vectorstore.get()["ids"])

        vectorstore.delete(where={
            "$and": [
                {"page_id": {"$in": page_ids}},
                {"doc_type": {"$eq": "requirement"}}
            ]
        })

        final_count = len(vectorstore.get()["ids"])
        return initial_count - final_count

    def remove_platform_page_fragments(self, page_ids: List[str], service_code: str) -> int:
        """Удаляет фрагменты платформенных страниц."""
        if not service_code:
            raise ValueError("service_code is required for platform pages")

        if not get_platform_status(service_code):
            raise ValueError(f"Service {service_code} is not a platform service")

        embeddings_model = get_embeddings_model()
        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        initial_count = len(vectorstore.get()["ids"])

        vectorstore.delete(where={
            "$and": [
                {"page_id": {"$in": page_ids}},
                {"service_code": {"$eq": service_code}},
                {"doc_type": {"$eq": "requirement"}},
                {"is_platform": {"$eq": True}}
            ]
        })

        final_count = len(vectorstore.get()["ids"])
        return initial_count - final_count

    def has_approved_fragments(self, page_ids: List[str]) -> bool:
        """Проверяет наличие одобренных фрагментов в хранилище для указанных страниц."""
        if not page_ids:
            return False

        logger.info("[has_approved_fragments] <- Checking %d page_ids", len(page_ids))

        try:
            embeddings_model = get_embeddings_model()
            store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

            results = store.get(where={
                "$and": [
                    {"doc_type": {"$eq": "requirement"}},
                    {"page_id": {"$in": page_ids}}
                ]
            })

            found_count = len(results.get("ids", []))
            has_fragments = found_count > 0

            logger.info(
                "[has_approved_fragments] -> Found %d fragments, result: %s",
                found_count, has_fragments
            )
            return has_fragments

        except Exception as e:
            logger.error("[has_approved_fragments] Error: %s", str(e))
            return False

    def get_storage_info(self) -> Dict:
        """Отладочная информация о хранилище."""
        logger.info("[get_storage_info] <-")
        embeddings_model = get_embeddings_model()
        store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        if store is None:
            raise ValueError("No vectorstore found.")

        data = store.get()

        doc_type_stats = {}
        platform_stats = {"platform": 0, "regular": 0}
        service_stats = {}
        content_sizes = []

        for metadata, doc_content in zip(
            data.get("metadatas", []),
            data.get("documents", [])
        ):
            if metadata:
                doc_type = metadata.get("doc_type", "unknown")
                doc_type_stats[doc_type] = doc_type_stats.get(doc_type, 0) + 1

                if metadata.get("is_platform", False):
                    platform_stats["platform"] += 1
                else:
                    platform_stats["regular"] += 1

                svc = metadata.get("service_code", "unknown")
                service_stats[svc] = service_stats.get(svc, 0) + 1

            if doc_content:
                content_sizes.append(len(doc_content))

        return {
            "storage_name": UNIFIED_STORAGE_NAME,
            "total_documents": len(data.get("ids", [])),
            "doc_type_stats": doc_type_stats,
            "platform_stats": platform_stats,
            "service_stats": service_stats,
            "sample_metadata": data.get("metadatas", [])[:3],
            "avg_document_size": sum(content_sizes) / len(content_sizes) if content_sizes else 0,
            "max_document_size": max(content_sizes) if content_sizes else 0,
            "documents_over_2000_chars": len([s for s in content_sizes if s > 2000]),
            "status": "ok"
        }

    def get_large_documents_info(self, min_chars: int = 10000) -> Dict:
        """Информация о больших документах в хранилище."""
        embeddings_model = get_embeddings_model()
        store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        data = store.get()

        large_docs = []
        for doc_content, metadata in zip(data["documents"], data["metadatas"]):
            size = len(doc_content)
            if size >= min_chars:
                large_docs.append({
                    "page_id": metadata.get("page_id"),
                    "title": metadata.get("title", "No title"),
                    "size_chars": size,
                    "size_tokens_estimate": size // 3,
                    "service_code": metadata.get("service_code")
                })

        large_docs.sort(key=lambda x: x["size_chars"], reverse=True)

        return {
            "total_documents": len(data["documents"]),
            "large_documents_count": len(large_docs),
            "large_documents": large_docs[:20],
            "largest_size_chars": large_docs[0]["size_chars"] if large_docs else 0,
            "largest_size_tokens_estimate": large_docs[0]["size_tokens_estimate"] if large_docs else 0
        }

    # -------------------------------------------------------------------------
    # Внутренние методы
    # -------------------------------------------------------------------------

    def _create_multi_vector_documents(
        self,
        pages: List[Dict],
        service_code: str,
        source: str,
        doc_type: str = "requirement",
        use_llm_summary: bool = False
    ):
        """Создаёт Multi-Vector документы для списка страниц.

        Вызывается из синхронного потока. Async-метод индексатора запускается
        через asyncio.run(), который создаёт изолированный event loop в потоке.
        """
        logger.info(
            "[_create_multi_vector_documents] Creating Multi-Vector docs for %d pages (llm_summary=%s)",
            len(pages), use_llm_summary
        )

        indexer = MultiVectorIndexer(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            use_llm_summary=use_llm_summary
        )

        # asyncio.run() безопасно создаёт новый event loop в worker thread.
        # Не использовать get_event_loop() — в потоке anyio его нет.
        docs = asyncio.run(
            indexer.prepare_multi_vector_documents(
                pages=pages,
                service_code=service_code,
                doc_type=doc_type,
                source=source
            )
        )

        logger.info(
            "[_create_multi_vector_documents] -> %d documents prepared",
            len(docs)
        )
        return docs

    def _filter_pages_with_approved_content(self, pages: List[Dict]) -> List[Dict]:
        """Фильтрует страницы с подтверждённым содержимым."""
        result = []
        for page in pages:
            approved_content = page.get("approved_content", "")
            if approved_content and approved_content.strip():
                result.append(page)
                logger.debug(
                    "Page %s has approved content (%d chars)",
                    page["id"], len(approved_content)
                )
            else:
                logger.warning("Page %s has no approved content, skipping", page["id"])
        return result

    def _delete_existing_fragments(self, store, pages: List[Dict]) -> None:
        """Удаляет существующие фрагменты страниц перед переиндексацией."""
        page_ids_to_delete = [p["id"] for p in pages]
        try:
            store.delete(where={
                "$and": [
                    {"page_id": {"$in": page_ids_to_delete}},
                    {"doc_type": {"$eq": "requirement"}}
                ]
            })
            logger.debug(
                "[_delete_existing_fragments] Deleted existing fragments for page_ids: %s",
                page_ids_to_delete
            )
        except Exception as e:
            logger.warning("[_delete_existing_fragments] Could not delete existing vectors: %s", e)