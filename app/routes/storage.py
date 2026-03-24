# app/routes/storage.py
import logging
from typing import Optional

from fastapi import APIRouter, Query

from app.utils.find_huge_documents import find_huge_documents, analyze_document_distribution
from app.embedding_store import get_vectorstore
from app.config import UNIFIED_STORAGE_NAME

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/storage/analyze-sizes")
def analyze_document_sizes():
    """Анализ размеров документов в хранилище"""
    logger.info("[analyze_document_sizes] <-.")
    try:
        # Вызываем функцию и захватываем вывод
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output

        large_docs = find_huge_documents(min_chars=10000, top_n=20)
        analyze_document_distribution()

        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()
        logger.info("[analyze_document_sizes] -> ...")
        return {
            "status": "success",
            "large_documents": large_docs,
            "console_output": output
        }
    except Exception as e:
        logger.error("[analyze_document_sizes] %s", str(e))
        return {"status": "error", "message": str(e)}


@router.get("/storage/chunks/{page_id}", tags=["Диагностика хранилища"])
def get_page_chunks(
        page_id: str,
        service_code: Optional[str] = Query(None, description="Фильтр по коду сервиса (опционально)")
):
    """
    Получает все фрагменты/чанки страницы из ChromaDB с полными метаданными.

    Используется для диагностики:
    - Проверки какие метаданные ассоциированы с фрагментами страницы
    - Проверки правильности разбиения на чанки
    - Проверки наличия requirement_type, target_system и других полей
    - Анализа размеров фрагментов

    Args:
        page_id: Идентификатор страницы Confluence
        service_code: Опциональный фильтр по коду сервиса

    Returns:
        Информация о всех чанках страницы с метаданными

    Example:
        GET /storage/chunks/274628758
        GET /storage/chunks/274628758?service_code=CC
    """
    logger.info("[get_page_chunks] <- page_id=%s, service_code=%s", page_id, service_code)

    try:
        # Получаем vectorstore
        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME)

        # Формируем фильтр
        filter_conditions = [{"page_id": page_id}]

        if service_code:
            filter_conditions.append({"service_code": service_code})

        query_filter = (
            {"$and": filter_conditions}
            if len(filter_conditions) > 1
            else filter_conditions[0]
        )

        logger.debug("[get_page_chunks] Filter: %s", query_filter)

        # Поиск всех фрагментов страницы
        # Используем пустой запрос для получения всех документов с фильтром
        docs = vectorstore.similarity_search(
            query="",
            k=100,  # Достаточно большое число для получения всех чанков
            filter=query_filter
        )

        if not docs:
            logger.warning("[get_page_chunks] No chunks found for page_id=%s", page_id)
            return {
                "status": "success",
                "page_id": page_id,
                "service_code": service_code,
                "total_chunks": 0,
                "chunks": [],
                "message": "Фрагменты не найдены в хранилище"
            }

        # Формируем детальную информацию о каждом чанке
        chunks_info = []
        total_content_size = 0

        for i, doc in enumerate(docs, 1):
            metadata = doc.metadata
            content = doc.page_content
            content_size = len(content)
            total_content_size += content_size

            chunk_info = {
                "chunk_number": i,
                "content_size": content_size,
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
                "full_content": content,  # Полное содержимое для детальной проверки
                "metadata": {
                    "page_id": metadata.get("page_id"),
                    "index_tier": metadata.get("index_tier"),
                    "vector_type": metadata.get("vector_type"),
                    "title": metadata.get("title"),
                    "requirement_type": metadata.get("requirement_type"),
                    "service_code": metadata.get("service_code"),
                    "doc_type": metadata.get("doc_type"),
                    "is_platform": metadata.get("is_platform"),
                    "target_system": metadata.get("target_system"),
                    "source": metadata.get("source"),
                    "is_full_page": metadata.get("is_full_page"),
                    "chunk_index": metadata.get("chunk_index"),
                    "chunk_id": metadata.get("chunk_id"),
                    "total_chunks": metadata.get("total_chunks"),
                    "original_page_size": metadata.get("original_page_size")
                }
            }

            chunks_info.append(chunk_info)

        # Статистика
        chunk_sizes = [chunk["content_size"] for chunk in chunks_info]
        avg_chunk_size = total_content_size / len(chunks_info) if chunks_info else 0

        # Проверка метаданных
        missing_metadata = []
        important_fields = ["requirement_type", "service_code", "title"]

        for field in important_fields:
            if not all(chunk["metadata"].get(field) for chunk in chunks_info):
                missing_metadata.append(field)

        result = {
            "status": "success",
            "page_id": page_id,
            "service_code": service_code,
            "total_chunks": len(chunks_info),
            "statistics": {
                "total_content_size": total_content_size,
                "average_chunk_size": round(avg_chunk_size, 2),
                "min_chunk_size": min(chunk_sizes) if chunk_sizes else 0,
                "max_chunk_size": max(chunk_sizes) if chunk_sizes else 0,
                "is_chunked": any(
                    not chunk["metadata"].get("is_full_page", True)
                    for chunk in chunks_info
                ),
            },
            "metadata_check": {
                "all_fields_present": len(missing_metadata) == 0,
                "missing_fields": missing_metadata,
                "requirement_types": list(set(
                    chunk["metadata"].get("requirement_type")
                    for chunk in chunks_info
                    if chunk["metadata"].get("requirement_type")
                )),
                "target_systems": list(set(
                    chunk["metadata"].get("target_system")
                    for chunk in chunks_info
                    if chunk["metadata"].get("target_system")
                )),
            },
            "chunks": chunks_info
        }

        logger.info(
            "[get_page_chunks] -> Found %d chunks, total_size=%d, avg_size=%.2f",
            len(chunks_info), total_content_size, avg_chunk_size
        )

        return result

    except Exception as e:
        logger.error("[get_page_chunks] Error: %s", str(e), exc_info=True)
        return {
            "status": "error",
            "page_id": page_id,
            "message": str(e)
        }


@router.get("/storage/search-chunks", tags=["Диагностика хранилища"])
def search_chunks_by_metadata(
        requirement_type: Optional[str] = Query(None, description="Тип требования"),
        service_code: Optional[str] = Query(None, description="Код сервиса"),
        target_system: Optional[str] = Query(None, description="Смежная система"),
        title_contains: Optional[str] = Query(None, description="Поиск в заголовке (частичное совпадение)"),
        limit: int = Query(10, description="Максимальное количество результатов", ge=1, le=100)
):
    """
    Поиск фрагментов по метаданным (без семантического поиска).

    Используется для диагностики фильтрации в ChromaDB.

    Args:
        requirement_type: Фильтр по типу требования (dataModel, function и т.д.)
        service_code: Фильтр по коду сервиса
        target_system: Фильтр по смежной системе
        title_contains: Поиск в заголовке
        limit: Количество результатов

    Returns:
        Список найденных фрагментов с метаданными

    Example:
        GET /storage/search-chunks?requirement_type=dataModel&service_code=CC
        GET /storage/search-chunks?title_contains=заявка&service_code=CC
    """
    logger.info(
        "[search_chunks_by_metadata] <- type=%s, service=%s, system=%s, title=%s",
        requirement_type, service_code, target_system, title_contains
    )

    try:
        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME)

        # Формируем фильтр
        filter_conditions = []

        if requirement_type:
            filter_conditions.append({"requirement_type": requirement_type})

        if service_code:
            filter_conditions.append({"service_code": service_code})

        if target_system:
            filter_conditions.append({"target_system": target_system})

        # Для поиска в title используем contains (если ChromaDB поддерживает)
        # Если нет - будем фильтровать после получения результатов

        query_filter = (
            {"$and": filter_conditions}
            if len(filter_conditions) > 1
            else (filter_conditions[0] if filter_conditions else {})
        )

        logger.debug("[search_chunks_by_metadata] Filter: %s", query_filter)

        # Поиск
        docs = vectorstore.similarity_search(
            query="",
            k=limit * 2 if title_contains else limit,  # Берём больше если нужна фильтрация по title
            filter=query_filter if filter_conditions else None
        )

        # Фильтрация по title если нужно
        if title_contains:
            title_lower = title_contains.lower()
            docs = [
                doc for doc in docs
                if title_lower in doc.metadata.get("title", "").lower()
            ][:limit]

        # Формируем результат
        results = []
        for doc in docs:
            metadata = doc.metadata
            results.append({
                "page_id": metadata.get("page_id"),
                "title": metadata.get("title"),
                "requirement_type": metadata.get("requirement_type"),
                "service_code": metadata.get("service_code"),
                "target_system": metadata.get("target_system"),
                "is_full_page": metadata.get("is_full_page"),
                "chunk_index": metadata.get("chunk_index"),
                "content_preview": doc.page_content[:150] + "..." if len(doc.page_content) > 150 else doc.page_content
            })

        logger.info("[search_chunks_by_metadata] -> Found %d results", len(results))

        return {
            "status": "success",
            "filters": {
                "requirement_type": requirement_type,
                "service_code": service_code,
                "target_system": target_system,
                "title_contains": title_contains
            },
            "total_results": len(results),
            "results": results
        }

    except Exception as e:
        logger.error("[search_chunks_by_metadata] Error: %s", str(e), exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }