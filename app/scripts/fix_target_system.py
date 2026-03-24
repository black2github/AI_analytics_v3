# Путь: app/scripts/fix_target_system.py
"""
Точечное исправление атрибута target_system для интеграционных страниц в ChromaDB.

Проблема:
    При индексации страниц с заголовками вида "[КК_ВК] Параметры вызова ... в ТЕССА"
    старый integration_parser не находил систему (отсекал заголовки начинающиеся с '[').
    В результате target_system=None в метаданных хранилища.

Решение:
    Без переиндексации (перевычисления эмбеддингов) обновляем метаданные напрямую
    через ChromaDB _collection.update() — применяем исправленный парсер к заголовкам
    и контенту страниц с target_system=None.

Использование:
    # Анализ без изменений:
    python app/scripts/fix_target_system.py --dry-run

    # Исправить все сервисы:
    python app/scripts/fix_target_system.py

    # Исправить конкретный сервис:
    python app/scripts/fix_target_system.py --service CC

    # Нестандартное хранилище:
    python app/scripts/fix_target_system.py --chroma-dir ./store/chroma_db2
"""

import argparse
import logging
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.config import CHROMA_PERSIST_DIR, UNIFIED_STORAGE_NAME
from app.llm_interface import get_embeddings_model

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s,%(msecs)03d [%(levelname)s] %(filename)s:%(lineno)d %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def fix_target_system(
    chroma_dir: str,
    service_code: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Находит интеграционные страницы с target_system=None и обновляет метаданные.

    Использует исправленный integration_parser: сначала ищет систему в контенте,
    затем в заголовке (включая поиск в любом месте заголовка).

    Args:
        chroma_dir: Путь к ChromaDB
        service_code: Код сервиса (None = все сервисы)
        dry_run: Только анализ без изменений

    Returns:
        Статистика: найдено / обновлено / не удалось определить систему
    """
    from langchain_chroma import Chroma
    from app.services.integration_parser import extract_target_system

    stats = {
        "found": 0,
        "updated": 0,
        "skipped_no_system": 0,
        "errors": 0,
    }

    logger.info("Initializing embeddings model...")
    embeddings_model = get_embeddings_model()

    vs = Chroma(
        collection_name=UNIFIED_STORAGE_NAME,
        embedding_function=embeddings_model,
        persist_directory=chroma_dir,
    )

    # Строим фильтр — ищем интеграционные страницы с отсутствующим target_system.
    # ChromaDB не поддерживает фильтр по отсутствию атрибута напрямую,
    # поэтому берём все title-векторы с req_type=integration и фильтруем в Python.
    where_filter: dict = {
        "$and": [
            {"requirement_type": {"$eq": "integration"}},
            {"doc_type":         {"$eq": "requirement"}},
            {"vector_type":      {"$eq": "title"}},
        ]
    }
    if service_code:
        where_filter["$and"].append({"service_code": {"$eq": service_code}})

    logger.info(
        "Fetching integration title-vectors%s...",
        f" for service '{service_code}'" if service_code else " (all services)"
    )

    results = vs.get(
        where=where_filter,
        include=["documents", "metadatas"],
    )

    if not results or not results.get("ids"):
        logger.info("No integration pages found.")
        return stats

    total = len(results["ids"])
    logger.info("Found %d integration title-vectors total", total)

    # Фильтруем только те где target_system отсутствует или None
    candidates = [
        (doc_id, doc, meta)
        for doc_id, doc, meta in zip(
            results["ids"], results["documents"], results["metadatas"]
        )
        if not meta.get("target_system")
    ]

    logger.info(
        "%d pages have target_system=None (out of %d total integration pages)",
        len(candidates), total
    )

    stats["found"] = len(candidates)

    if not candidates:
        logger.info("Nothing to fix.")
        return stats

    # Обрабатываем каждую страницу
    for doc_id, _title_text, meta in candidates:
        page_id = meta.get("page_id")
        title = meta.get("title", "")
        svc = meta.get("service_code", "")

        # Получаем контент страницы для парсинга
        content_result = vs.get(
            where={
                "$and": [
                    {"page_id":     {"$eq": page_id}},
                    {"vector_type": {"$eq": "content"}},
                    {"doc_type":    {"$eq": "requirement"}},
                ]
            },
            include=["documents"],
            limit=1,
        )
        content = (
            content_result["documents"][0]
            if content_result and content_result.get("documents")
            else ""
        )

        target_system = extract_target_system(title=title, content=content)

        if not target_system:
            logger.debug(
                "Could not determine target_system for page_id=%s title='%s'",
                page_id, title[:60]
            )
            stats["skipped_no_system"] += 1
            continue

        logger.info(
            "page_id=%-12s service=%-15s target_system=%-10s title='%s'",
            page_id, svc, target_system, title[:60]
        )

        if dry_run:
            stats["updated"] += 1
            continue

        # Обновляем метаданные всех векторов этой страницы (title, summary, content)
        try:
            all_vectors = vs.get(
                where={
                    "$and": [
                        {"page_id":    {"$eq": page_id}},
                        {"doc_type":   {"$eq": "requirement"}},
                        {"service_code": {"$eq": svc}},
                    ]
                },
                include=["metadatas"],
            )

            if not all_vectors or not all_vectors.get("ids"):
                logger.warning("No vectors found for page_id=%s svc=%s", page_id, svc)
                stats["errors"] += 1
                continue

            updated_metadatas = [
                {**m, "target_system": target_system}
                for m in all_vectors["metadatas"]
            ]

            # Прямое обновление метаданных — без перевычисления эмбеддингов
            vs._collection.update(
                ids=all_vectors["ids"],
                metadatas=updated_metadatas,
            )

            logger.debug(
                "Updated %d vectors for page_id=%s -> target_system=%s",
                len(all_vectors["ids"]), page_id, target_system
            )
            stats["updated"] += 1

        except Exception as e:
            logger.error(
                "Error updating page_id=%s: %s", page_id, e, exc_info=True
            )
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Fix missing target_system metadata for integration pages in ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run — show what would be fixed:
  python app/scripts/fix_target_system.py --dry-run

  # Fix all services:
  python app/scripts/fix_target_system.py

  # Fix specific service:
  python app/scripts/fix_target_system.py --service CC

  # Custom store path:
  python app/scripts/fix_target_system.py --chroma-dir ./store/chroma_db2
        """
    )
    parser.add_argument(
        '--chroma-dir', type=str, default=None,
        help='ChromaDB directory (default: CHROMA_PERSIST_DIR from config)'
    )
    parser.add_argument(
        '--service', type=str, default=None,
        help='Service code to fix (default: all services)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be fixed without making changes'
    )

    args = parser.parse_args()

    chroma_dir = (
        os.path.abspath(args.chroma_dir)
        if args.chroma_dir
        else os.path.abspath(CHROMA_PERSIST_DIR)
    )

    if not os.path.exists(chroma_dir):
        logger.error("ChromaDB directory does not exist: %s", chroma_dir)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("FIX TARGET_SYSTEM METADATA")
    logger.info("  chroma_dir : %s", chroma_dir)
    logger.info("  service    : %s", args.service or "all")
    logger.info("  dry_run    : %s", args.dry_run)
    logger.info("=" * 60)

    stats = fix_target_system(
        chroma_dir=chroma_dir,
        service_code=args.service,
        dry_run=args.dry_run,
    )

    logger.info("=" * 60)
    if args.dry_run:
        logger.info("DRY RUN — no changes made")
        logger.info("  Would fix : %d pages", stats["updated"])
    else:
        logger.info("DONE")
        logger.info("  updated            : %d", stats["updated"])
        logger.info("  skipped (no system): %d", stats["skipped_no_system"])
        logger.info("  errors             : %d", stats["errors"])
    logger.info("  found (null)       : %d", stats["found"])
    logger.info("=" * 60)

    sys.exit(1 if stats["errors"] > 0 else 0)


if __name__ == '__main__':
    main()