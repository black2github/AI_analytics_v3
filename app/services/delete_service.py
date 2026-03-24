# Путь: app/scripts/delete_service.py
"""
CLI скрипт для удаления всех документов сервиса из ChromaDB по коду сервиса.

Удаляет одним запросом по фильтру service_code — без предварительного
сбора page_ids. Работает как с legacy, так и с multi_vector форматом.

Использование:

  # Удалить все документы сервиса CC:
  python app/scripts/delete_service.py --service CC

  # Удалить из нестандартного хранилища:
  python app/scripts/delete_service.py --service CC --chroma-dir ./store/chroma_db2

  # Показать статистику без удаления:
  python app/scripts/delete_service.py --service CC --dry-run

  # Удалить несколько сервисов:
  python app/scripts/delete_service.py --service CC INT SBP
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.config import (
    CHROMA_PERSIST_DIR,
    UNIFIED_STORAGE_NAME,
    INDEXING_MODE,
    LEGACY_EMBEDDING_MODEL,
    EMBEDDING_DEVICE,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_SEQ_LENGTH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,%(msecs)03d [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _get_embeddings(indexing_mode: str):
    """Возвращает модель эмбеддингов соответствующую режиму хранилища."""
    if indexing_mode == "legacy":
        from langchain_huggingface import HuggingFaceEmbeddings
        logger.info("[_get_embeddings] Using legacy model: %s", LEGACY_EMBEDDING_MODEL)
        return HuggingFaceEmbeddings(
            model_name=LEGACY_EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    else:
        from app.llm_interface import get_embeddings_model
        logger.info("[_get_embeddings] Using multi_vector model")
        return get_embeddings_model()


def _get_vectorstore(chroma_dir: str, embeddings):
    """Открывает ChromaDB хранилище по указанному пути."""
    from langchain_chroma import Chroma
    return Chroma(
        collection_name=UNIFIED_STORAGE_NAME,
        embedding_function=embeddings,
        persist_directory=chroma_dir,
    )


def get_service_stats(vectorstore, service_code: str) -> dict:
    """Возвращает статистику документов сервиса в хранилище."""
    results = vectorstore.get(
        where={
            "$and": [
                {"service_code": {"$eq": service_code}},
                {"doc_type": {"$eq": "requirement"}},
            ]
        },
        include=["metadatas"],
    )

    metadatas = results.get("metadatas") or []
    total = len(metadatas)

    # Считаем уникальные page_id и распределение по vector_type
    page_ids = set()
    vector_type_counts: dict = {}
    for m in metadatas:
        if m.get("page_id"):
            page_ids.add(m["page_id"])
        vt = m.get("vector_type", "legacy")
        vector_type_counts[vt] = vector_type_counts.get(vt, 0) + 1

    return {
        "total_documents": total,
        "unique_pages": len(page_ids),
        "by_vector_type": vector_type_counts,
    }


def delete_service(
    service_code: str,
    chroma_dir: str,
    indexing_mode: str,
    dry_run: bool = False,
) -> dict:
    """
    Удаляет все документы сервиса из хранилища.

    Args:
        service_code: Код сервиса (например, "CC")
        chroma_dir: Путь к ChromaDB
        indexing_mode: "legacy" или "multi_vector" — определяет модель эмбеддингов
        dry_run: Если True — только показывает статистику без удаления

    Returns:
        Словарь со статистикой: было документов, удалено, осталось.
    """
    logger.info(
        "[delete_service] service_code=%s, chroma_dir=%s, indexing_mode=%s, dry_run=%s",
        service_code, chroma_dir, indexing_mode, dry_run,
    )

    embeddings = _get_embeddings(indexing_mode)
    vectorstore = _get_vectorstore(chroma_dir, embeddings)

    # Статистика до удаления
    before_stats = get_service_stats(vectorstore, service_code)

    if before_stats["total_documents"] == 0:
        logger.warning(
            "[delete_service] No documents found for service '%s' in '%s'",
            service_code, chroma_dir,
        )
        return {
            "service_code": service_code,
            "before": before_stats,
            "deleted": 0,
            "dry_run": dry_run,
        }

    logger.info(
        "[delete_service] Found %d documents (%d unique pages) for service '%s': %s",
        before_stats["total_documents"],
        before_stats["unique_pages"],
        service_code,
        before_stats["by_vector_type"],
    )

    if dry_run:
        logger.info("[delete_service] DRY RUN — no changes made.")
        return {
            "service_code": service_code,
            "before": before_stats,
            "deleted": 0,
            "dry_run": True,
        }

    # Удаляем одним запросом по service_code — не нужно собирать page_ids
    vectorstore.delete(where={
        "$and": [
            {"service_code": {"$eq": service_code}},
            {"doc_type": {"$eq": "requirement"}},
        ]
    })

    # Проверяем что осталось
    after_stats = get_service_stats(vectorstore, service_code)
    deleted = before_stats["total_documents"] - after_stats["total_documents"]

    logger.info(
        "[delete_service] Deleted %d documents for service '%s'. Remaining: %d",
        deleted, service_code, after_stats["total_documents"],
    )

    return {
        "service_code": service_code,
        "before": before_stats,
        "after": after_stats,
        "deleted": deleted,
        "dry_run": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Delete all documents for a service from ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete service CC from default store:
  python app/scripts/delete_service.py --service CC

  # Dry run — show stats without deleting:
  python app/scripts/delete_service.py --service CC --dry-run

  # Delete from a specific store:
  python app/scripts/delete_service.py --service CC --chroma-dir ./store/chroma_db2

  # Delete multiple services:
  python app/scripts/delete_service.py --service CC INT SBP

  # Delete from legacy store:
  python app/scripts/delete_service.py --service CC --indexing-mode legacy
        """,
    )

    parser.add_argument(
        "--service",
        nargs="+",
        required=True,
        metavar="SERVICE_CODE",
        help="Service code(s) to delete (e.g. CC, or CC INT SBP)",
    )
    parser.add_argument(
        "--chroma-dir",
        type=str,
        default=None,
        help="Path to ChromaDB directory. Defaults to CHROMA_PERSIST_DIR from config.",
    )
    parser.add_argument(
        "--indexing-mode",
        type=str,
        default=None,
        choices=["legacy", "multi_vector"],
        help=(
            "Embedding model to use when opening the store. "
            "Defaults to INDEXING_MODE from config. "
            "Use 'legacy' for stores built with all-MiniLM-L6-v2, "
            "'multi_vector' for stores built with USER2-base."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show document counts without deleting anything",
    )

    args = parser.parse_args()

    chroma_dir = os.path.abspath(args.chroma_dir) if args.chroma_dir else os.path.abspath(CHROMA_PERSIST_DIR)
    indexing_mode = args.indexing_mode or INDEXING_MODE

    logger.info("=" * 60)
    logger.info("DELETE SERVICE DOCUMENTS")
    logger.info("  chroma_dir    : %s", chroma_dir)
    logger.info("  indexing_mode : %s", indexing_mode)
    logger.info("  services      : %s", args.service)
    logger.info("  dry_run       : %s", args.dry_run)
    logger.info("=" * 60)

    if not os.path.exists(chroma_dir):
        logger.error("ChromaDB directory does not exist: %s", chroma_dir)
        sys.exit(1)

    total_deleted = 0
    errors = 0

    for service_code in args.service:
        try:
            result = delete_service(
                service_code=service_code,
                chroma_dir=chroma_dir,
                indexing_mode=indexing_mode,
                dry_run=args.dry_run,
            )
            total_deleted += result["deleted"]
        except Exception as e:
            logger.error("Error deleting service %s: %s", service_code, e, exc_info=True)
            errors += 1

    logger.info("=" * 60)
    if args.dry_run:
        logger.info("DRY RUN COMPLETED — no documents were deleted")
    else:
        logger.info("DONE. Total deleted: %d documents. Errors: %d", total_deleted, errors)
    logger.info("=" * 60)

    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()