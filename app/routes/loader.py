# app/routes/loader.py - ИСПРАВЛЕННАЯ ВЕРСИЯ с параллельностью

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import logging
import anyio  # pip install anyio

from app.services.document_service import DocumentService
from app.llm_interface import get_embeddings_cache_info, clear_embeddings_cache
from app.page_cache import clear_page_cache, get_cache_info

logger = logging.getLogger(__name__)
router = APIRouter()

# Инициализируем сервис (простое создание без DI)
document_service = DocumentService()


class LoadRequest(BaseModel):
    page_ids: List[str]
    service_code: Optional[str] = None
    source: str = "DBOCORPESPLN"


class TemplateLoadRequest(BaseModel):
    templates: Dict[str, str]


class RemovePagesRequest(BaseModel):
    page_ids: List[str]
    service_code: Optional[str] = None


@router.post("/load_pages", tags=["Загрузка Confluence страниц требований"])
async def load_service_pages(payload: LoadRequest):
    """
     ОПТИМИЗИРОВАНО: Загружает подтвержденные требования в отдельном потоке

    Загружает ТОЛЬКО подтвержденные требования в единое хранилище.
    Тяжелые операции (загрузка страниц, создание эмбеддингов) выполняются в thread pool.
    """
    logger.info("[load_service_pages] <- %d page(s), service_code=%s, source=%s",
                len(payload.page_ids), payload.service_code, payload.source)
    try:
        #  КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Запускаем в thread pool
        result = await anyio.to_thread.run_sync(
            document_service.load_approved_pages,
            payload.page_ids,
            payload.service_code,
            payload.source
        )

        platform_status = "platform" if result["is_platform"] else "regular"

        logger.info("[load_service_pages] -> Created %d documents for %s service '%s'",
                    result['documents_created'], platform_status, result['service_code'])

        return {
            "message": f"{result['documents_created']} documents indexed for {platform_status} service '{result['service_code']}' (approved content only).",
            "total_pages": result["total_pages"],
            "pages_with_approved_content": result["pages_with_approved_content"],
            "documents_created": result["documents_created"],
            "is_platform": result["is_platform"],
            "storage": result["storage"]
        }
    except ValueError as e:
        logger.error("[load_service_pages] Validation error: %s", str(e))
        return {"error": str(e)}
    except Exception as e:
        logger.exception("[load_service_pages] Unexpected error")
        return {"error": str(e)}


@router.post("/load_templates", tags=["Загрузка Confluence шаблонов страниц требований"])
async def load_templates(payload: TemplateLoadRequest):
    """
     ОПТИМИЗИРОВАНО: Загружает шаблоны в отдельном потоке
    """
    logger.info("[load_templates] <- %d template(s)", len(payload.templates))
    try:
        #  КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Запускаем в thread pool
        result = await anyio.to_thread.run_sync(
            document_service.load_templates_to_storage,
            payload.templates
        )
        logger.info("[load_templates] -> Templates loaded: %s", result)
        return {
            "message": f"Templates loaded: {result}",
            "storage": "unified_requirements"
        }
    except Exception as e:
        logger.exception("[load_templates] Error")
        return {"error": str(e)}


@router.get("/child_pages/{page_id}",
            tags=["Получение дочерних страниц Confluence и их опциональная загрузка в хранилище"])
async def get_child_pages(page_id: str, service_code: Optional[str] = None, source: str = "DBOCORPESPLN"):
    """
     ОПТИМИЗИРОВАНО: Получает дочерние страницы в отдельном потоке

    Возвращает список идентификаторов дочерних страниц и загружает их при указании service_code.
    """
    logger.info("[get_child_pages] <- page_id=%s, service_code=%s, source=%s", page_id, service_code, source)
    try:
        #  КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Запускаем в thread pool
        result = await anyio.to_thread.run_sync(
            document_service.get_child_pages_with_optional_load,
            page_id,
            service_code,
            source
        )
        logger.info("[get_child_pages] -> Found %d child pages", len(result["page_ids"]))
        return result
    except Exception as e:
        logger.exception("[get_child_pages] Error")
        return {"error": str(e)}


@router.post("/remove_service_pages", response_description="Удаление фрагментов страниц из единого хранилища")
async def remove_service_pages(request: RemovePagesRequest):
    """
     ОПТИМИЗИРОВАНО: Удаляет фрагменты в отдельном потоке

    Удаляет фрагменты указанных страниц из единого хранилища.
    """
    logger.info("[remove_service_pages] <- %d page(s)", len(request.page_ids))
    try:
        #  КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Запускаем в thread pool
        deleted_count = await anyio.to_thread.run_sync(
            document_service.remove_page_fragments,
            request.page_ids
        )
        logger.info("[remove_service_pages] -> Deleted %d fragments", deleted_count)
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "page_ids": request.page_ids,
            "storage": "unified_requirements"
        }
    except Exception as e:
        logger.error("[remove_service_pages] Error: %s", str(e))
        return {"error": str(e)}


@router.post("/remove_platform_pages", response_description="Удаление фрагментов платформенных страниц")
async def remove_platform_pages(request: RemovePagesRequest):
    """
     ОПТИМИЗИРОВАНО: Удаляет платформенные фрагменты в отдельном потоке

    Удаляет фрагменты платформенных страниц из единого хранилища.
    """
    logger.info("[remove_platform_pages] <- %d page(s), service_code=%s",
                len(request.page_ids), request.service_code)
    try:
        #  КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Запускаем в thread pool
        deleted_count = await anyio.to_thread.run_sync(
            document_service.remove_platform_page_fragments,
            request.page_ids,
            request.service_code
        )
        logger.info("[remove_platform_pages] -> Deleted %d platform fragments", deleted_count)
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "page_ids": request.page_ids,
            "service_code": request.service_code,
            "storage": "unified_requirements"
        }
    except ValueError as e:
        logger.error("[remove_platform_pages] Validation error: %s", str(e))
        return {"error": str(e)}
    except Exception as e:
        logger.error("[remove_platform_pages] Error: %s", str(e))
        return {"error": str(e)}


@router.get("/debug_collections", tags=["Отладка"])
async def debug_collections():
    """
     ОПТИМИЗИРОВАНО: Получает информацию о хранилище в отдельном потоке

    Отладочная информация о едином хранилище
    """
    logger.info("[debug_collections] <-")
    try:
        #  КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Запускаем в thread pool
        result = await anyio.to_thread.run_sync(
            document_service.get_storage_info
        )
        return result
    except Exception as e:
        return {"error": str(e), "storage": "unified_requirements"}


# Сохраняем функцию remove_service_fragments для обратной совместимости с тестами
def remove_service_fragments(page_ids: List[str]) -> int:
    """DEPRECATED: Используйте DocumentService.remove_page_fragments"""
    logger.info("Deprecated [remove_service_fragments] <- page_ids=%s", page_ids)
    return document_service.remove_page_fragments(page_ids)


# ============================================================================
# ЭНДПОИНТЫ КЕШИРОВАНИЯ (быстрые операции, не требуют thread pool)
# ============================================================================

@router.get("/cache_info", tags=["Кеширование"])
async def cache_info():
    """Информация о состоянии кеша страниц (быстрая операция)"""
    logger.info("[cache_info] <-")
    return get_cache_info()


@router.post("/clear_cache", tags=["Кеширование"])
async def clear_cache():
    """Очистка кеша страниц (быстрая операция)"""
    logger.info("[clear_cache] <-")
    clear_page_cache()
    return {"message": "Cache cleared successfully"}


@router.get("/embedding_cache_info", tags=["Кеширование"])
async def embedding_cache_info():
    """Информация о кеше модели эмбеддингов (быстрая операция)"""
    logger.info("[embedding_cache_info] <-")
    cache_info = get_embeddings_cache_info()
    return {
        "hits": cache_info.hits,
        "misses": cache_info.misses,
        "current_size": cache_info.currsize,
        "max_size": cache_info.maxsize
    }


@router.post("/clear_embedding_cache", tags=["Кеширование"])
async def clear_embedding_cache():
    """Очистка кеша модели эмбеддингов (быстрая операция)"""
    logger.info("[clear_embedding_cache] <-")
    clear_embeddings_cache()
    return {"message": "Embedding model cache cleared successfully"}