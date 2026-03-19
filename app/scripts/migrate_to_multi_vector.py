# Путь: app/scripts/migrate_to_multi_vector.py
"""
CLI скрипт для миграции существующих документов на Multi-Vector индексацию.

Поддерживает раздельные хранилища: чтение из источника (старая модель эмбеддингов),
запись в целевое хранилище (новая модель). Это позволяет мигрировать постепенно,
по одному сервису, без потери исходных данных.

Использование:

  # Посмотреть список сервисов в исходном хранилище
  python app/scripts/migrate_to_multi_vector.py --list-services --source-dir ./chroma

  # Мигрировать один сервис из старого хранилища в новое
  python app/scripts/migrate_to_multi_vector.py --service CC \\
      --source-dir ./chroma --target-dir ./chroma_user2

  # С LLM-summary и без интерактивного подтверждения
  python app/scripts/migrate_to_multi_vector.py --service CC \\
      --source-dir ./chroma --target-dir ./chroma_user2 \\
      --use-llm-summary --force

  # Dry-run: только показать статистику, ничего не писать
  python app/scripts/migrate_to_multi_vector.py --service CC \\
      --source-dir ./chroma --target-dir ./chroma_user2 --dry-run

  # Если source и target совпадают (in-place миграция, старая модель уже заменена)
  python app/scripts/migrate_to_multi_vector.py --service CC --force
"""

import logging
import argparse
import asyncio
import sys
from typing import List, Dict
from datetime import datetime
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.confluence_loader import load_pages_by_ids
from app.llm_interface import get_embeddings_model
from app.config import UNIFIED_STORAGE_NAME, CHROMA_PERSIST_DIR
from app.services.multi_vector_indexer import create_multi_vector_indexer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('multi_vector_indexer.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Размер одного upsert-батча для ChromaDB.
# ChromaDB ограничивает размер запроса (~5461 документов). Берём с запасом.
CHROMA_BATCH_SIZE = 2000


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С ХРАНИЛИЩЕМ
# ============================================================================

def _open_chroma_collection(store_dir: str):
    """
    Открывает коллекцию ChromaDB напрямую через chromadb.PersistentClient
    без модели эмбеддингов. Используется для чтения метаданных —
    это не требует пересчёта векторов и не зависит от размерности.
    """
    import chromadb
    client = chromadb.PersistentClient(path=store_dir)
    try:
        return client.get_collection(UNIFIED_STORAGE_NAME)
    except Exception as e:
        logger.error(
            "[_open_chroma_collection] Collection '%s' not found in '%s': %s",
            UNIFIED_STORAGE_NAME, store_dir, str(e)
        )
        return None


def get_service_page_ids_from_source(service_code: str, source_dir: str) -> List[str]:
    """
    Читает page_ids для сервиса из исходного хранилища через прямой доступ
    к метаданным (без пересчёта эмбеддингов, без конфликта размерностей).
    """
    logger.info(
        "[get_service_page_ids_from_source] service='%s', source='%s'",
        service_code, source_dir
    )

    collection = _open_chroma_collection(source_dir)
    if collection is None:
        return []

    results = collection.get(
        where={
            "$and": [
                {"service_code": {"$eq": service_code}},
                {"doc_type": {"$eq": "requirement"}}
            ]
        },
        include=["metadatas"]
    )

    # Дедупликация: один сервис имеет несколько векторов на страницу (title/summary/content)
    page_ids = list({m["page_id"] for m in results["metadatas"] if m.get("page_id")})

    logger.info(
        "[get_service_page_ids_from_source] Found %d unique pages", len(page_ids)
    )
    return page_ids


def list_services_in_source(source_dir: str) -> List[Dict]:
    """
    Возвращает список сервисов в исходном хранилище со статистикой.
    """
    logger.info("[list_services_in_source] Scanning '%s'", source_dir)

    collection = _open_chroma_collection(source_dir)
    if collection is None:
        return []

    results = collection.get(
        where={"doc_type": {"$eq": "requirement"}},
        include=["metadatas"]
    )

    service_pages: Dict[str, set] = {}
    service_mv_docs: Dict[str, int] = {}

    for m in results["metadatas"]:
        code = m.get("service_code", "unknown")
        page_id = m.get("page_id", "")
        vector_type = m.get("vector_type")

        if code not in service_pages:
            service_pages[code] = set()
            service_mv_docs[code] = 0

        service_pages[code].add(page_id)
        if vector_type:
            service_mv_docs[code] += 1

    services = []
    for code, pages in sorted(service_pages.items()):
        services.append({
            "service_code": code,
            "pages": len(pages),
            "mv_docs": service_mv_docs.get(code, 0),
            "status": "multi-vector" if service_mv_docs.get(code, 0) > 0 else "legacy"
        })

    return services


def check_indexing_status_in_source(page_ids: List[str], source_dir: str) -> Dict:
    """
    Проверяет статус индексации страниц в исходном хранилище.
    """
    collection = _open_chroma_collection(source_dir)
    if collection is None:
        return {"legacy_count": 0, "multi_vector_count": 0, "not_indexed_count": len(page_ids)}

    results = collection.get(
        where={
            "$and": [
                {"page_id": {"$in": page_ids}},
                {"doc_type": {"$eq": "requirement"}}
            ]
        },
        include=["metadatas"]
    )

    page_status = {}
    for m in results.get("metadatas", []):
        page_id = m.get("page_id")
        vector_type = m.get("vector_type")
        if vector_type:
            page_status[page_id] = "multi_vector"
        elif page_id not in page_status:
            page_status[page_id] = "legacy"

    multi_vector_count = sum(1 for s in page_status.values() if s == "multi_vector")
    legacy_count = sum(1 for s in page_status.values() if s == "legacy")
    not_indexed_count = len(page_ids) - len(page_status)

    return {
        "legacy_count": legacy_count,
        "multi_vector_count": multi_vector_count,
        "not_indexed_count": not_indexed_count
    }


# ============================================================================
# ОСНОВНОЙ КЛАСС МИГРАЦИИ
# ============================================================================

class MultiVectorMigrator:
    """
    Мигрирует документы сервиса из исходного хранилища в целевое
    с Multi-Vector индексацией и новой моделью эмбеддингов.

    source_dir — папка с исходным ChromaDB (старая модель, 384 dim).
    target_dir — папка для нового ChromaDB (новая модель, 768 dim).

    Если source_dir == target_dir — in-place миграция: старые документы
    сервиса удаляются перед записью новых. Используется когда модель уже
    заменена и переиндексация происходит в ту же папку.

    Если source_dir != target_dir — cross-store миграция: исходное
    хранилище не изменяется. Новые документы записываются в target_dir.
    Это позволяет мигрировать постепенно и откатиться при необходимости.
    """

    def __init__(
            self,
            source_dir: str,
            target_dir: str,
            dry_run: bool = False,
            use_llm_summary: bool = False,
            batch_size: int = 50
    ):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.use_llm_summary = use_llm_summary
        self.batch_size = batch_size
        self.in_place = (os.path.abspath(source_dir) == os.path.abspath(target_dir))

        self.stats = {
            "total_pages": 0,
            "processed_pages": 0,
            "created_documents": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None
        }

        logger.info(
            "[MultiVectorMigrator] source='%s', target='%s', in_place=%s, "
            "dry_run=%s, llm_summary=%s",
            source_dir, target_dir, self.in_place, dry_run, use_llm_summary
        )

    async def migrate_service(self, service_code: str, force: bool = False) -> Dict:
        """
        Мигрирует все документы сервиса.

        Args:
            service_code: Код сервиса (например, "CC")
            force: Пропустить проверку "уже мигрировано" и переиндексировать

        Returns:
            Словарь со статистикой
        """
        logger.info("=" * 80)
        logger.info("MIGRATING SERVICE: %s", service_code)
        logger.info("  source : %s", self.source_dir)
        logger.info("  target : %s", self.target_dir)
        logger.info("  in_place: %s", self.in_place)
        logger.info("=" * 80)

        self.stats["start_time"] = datetime.now()

        # ------------------------------------------------------------------ #
        # Шаг 1. Читаем page_ids из источника (без пересчёта эмбеддингов)
        # ------------------------------------------------------------------ #
        logger.info("[Step 1/5] Fetching page_ids from source...")
        page_ids = get_service_page_ids_from_source(service_code, self.source_dir)

        if not page_ids:
            logger.warning("No pages found for service '%s' in source.", service_code)
            self._print_summary()
            return self.stats

        logger.info("Found %d pages", len(page_ids))
        self.stats["total_pages"] = len(page_ids)

        # ------------------------------------------------------------------ #
        # Шаг 2. Проверяем статус индексации в источнике
        # ------------------------------------------------------------------ #
        logger.info("[Step 2/5] Checking indexing status in source...")
        status = check_indexing_status_in_source(page_ids, self.source_dir)
        logger.info("  Legacy indexed   : %d pages", status["legacy_count"])
        logger.info("  Multi-Vector     : %d pages", status["multi_vector_count"])
        logger.info("  Not indexed      : %d pages", status["not_indexed_count"])

        if status["multi_vector_count"] > 0 and not force:
            logger.warning(
                "Source already has %d Multi-Vector indexed pages. "
                "Use --force to reindex anyway.",
                status["multi_vector_count"]
            )
            if not self._confirm_reindex():
                logger.info("Migration cancelled by user.")
                return self.stats

        # ------------------------------------------------------------------ #
        # Шаг 3. Загружаем страницы из Confluence
        # ------------------------------------------------------------------ #
        logger.info("[Step 3/5] Loading pages from Confluence...")
        pages = load_pages_by_ids(page_ids)
        logger.info("Loaded %d pages from Confluence", len(pages))

        pages_with_approved = [
            p for p in pages
            if p.get("approved_content") and p["approved_content"].strip()
        ]
        logger.info(
            "Pages with approved content: %d/%d",
            len(pages_with_approved), len(pages)
        )

        if not pages_with_approved:
            logger.error("No pages with approved content found!")
            self._print_summary()
            return self.stats

        # ------------------------------------------------------------------ #
        # Шаг 4. Создаём Multi-Vector документы
        # ------------------------------------------------------------------ #
        logger.info("[Step 4/5] Creating Multi-Vector documents...")
        logger.info("  LLM Summary: %s", self.use_llm_summary)
        logger.info("  Batch size : %d", self.batch_size)

        if self.dry_run:
            logger.info("DRY RUN MODE: skipping document creation and write.")
            self.stats["processed_pages"] = len(pages_with_approved)
            estimated = len(pages_with_approved) * 3
            logger.info("Would create approximately %d documents.", estimated)
            self._print_summary()
            return self.stats

        indexer = create_multi_vector_indexer(use_llm_summary=self.use_llm_summary)
        docs = await indexer.prepare_multi_vector_documents(
            pages=pages_with_approved,
            service_code=service_code,
            doc_type="requirement",
            source="DBOCORPESPLN",
            batch_size=self.batch_size
        )

        logger.info("Created %d Multi-Vector documents", len(docs))
        self.stats["created_documents"] = len(docs)
        self.stats["processed_pages"] = len(pages_with_approved)

        # ------------------------------------------------------------------ #
        # Шаг 5. Записываем в целевое хранилище
        # ------------------------------------------------------------------ #
        logger.info("[Step 5/5] Writing to target '%s'...", self.target_dir)

        from langchain_chroma import Chroma
        embedding_model = get_embeddings_model()

        target_vs = Chroma(
            collection_name=UNIFIED_STORAGE_NAME,
            embedding_function=embedding_model,
            persist_directory=self.target_dir
        )

        if self.in_place:
            # In-place: удаляем старые документы сервиса перед записью новых
            page_ids_to_delete = [p["id"] for p in pages_with_approved]
            logger.info(
                "In-place mode: deleting old documents for %d pages...",
                len(page_ids_to_delete)
            )
            target_vs.delete(where={
                "$and": [
                    {"page_id": {"$in": page_ids_to_delete}},
                    {"doc_type": {"$eq": "requirement"}}
                ]
            })
        else:
            logger.info(
                "Cross-store mode: source '%s' remains untouched.",
                self.source_dir
            )

        # Записываем батчами
        total_docs = len(docs)
        total_batches = (total_docs + CHROMA_BATCH_SIZE - 1) // CHROMA_BATCH_SIZE
        logger.info(
            "Adding %d documents in %d batch(es) of up to %d...",
            total_docs, total_batches, CHROMA_BATCH_SIZE
        )

        for batch_start in range(0, total_docs, CHROMA_BATCH_SIZE):
            batch = docs[batch_start: batch_start + CHROMA_BATCH_SIZE]
            batch_num = batch_start // CHROMA_BATCH_SIZE + 1
            logger.info(
                "  Batch %d/%d: %d documents",
                batch_num, total_batches, len(batch)
            )
            target_vs.add_documents(batch)

        logger.info("Write complete. Total documents added: %d", total_docs)
        self._print_summary()
        return self.stats

    def _print_summary(self):
        self.stats["end_time"] = datetime.now()
        start = self.stats.get("start_time")
        end = self.stats.get("end_time")
        duration = (end - start).total_seconds() if start and end else 0
        logger.info("=" * 80)
        logger.info("MIGRATION COMPLETED")
        logger.info("  Total pages      : %d", self.stats["total_pages"])
        logger.info("  Processed pages  : %d", self.stats["processed_pages"])
        logger.info("  Created documents: %d", self.stats["created_documents"])
        logger.info("  Errors           : %d", self.stats["errors"])
        logger.info("  Duration         : %.1f seconds", duration)
        logger.info("=" * 80)

    def _confirm_reindex(self) -> bool:
        response = input("Continue with reindexing? [y/N]: ")
        return response.lower() in ("y", "yes")


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

async def migrate_service_async(
        service_code: str,
        source_dir: str,
        target_dir: str,
        dry_run: bool = False,
        use_llm_summary: bool = False,
        force: bool = False,
        batch_size: int = 50
):
    migrator = MultiVectorMigrator(
        source_dir=source_dir,
        target_dir=target_dir,
        dry_run=dry_run,
        use_llm_summary=use_llm_summary,
        batch_size=batch_size
    )
    return await migrator.migrate_service(service_code, force=force)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate documents to Multi-Vector indexing with source/target store separation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List services in source store
  python migrate_to_multi_vector.py --list-services --source-dir ./chroma

  # Migrate one service to new store (source untouched)
  python migrate_to_multi_vector.py --service CC \\
      --source-dir ./chroma --target-dir ./chroma_user2

  # Force reindex with LLM summary
  python migrate_to_multi_vector.py --service CC \\
      --source-dir ./chroma --target-dir ./chroma_user2 \\
      --use-llm-summary --force

  # In-place (source == target, model already replaced)
  python migrate_to_multi_vector.py --service CC --force
        """
    )

    parser.add_argument(
        "--service",
        type=str,
        help="Service code to migrate (e.g., CC, SBP)"
    )
    parser.add_argument(
        "--list-services",
        action="store_true",
        help="List all services in the source store and exit"
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default=CHROMA_PERSIST_DIR,
        help=f"Source ChromaDB directory (default from config: {CHROMA_PERSIST_DIR})"
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=None,
        help="Target ChromaDB directory. Defaults to --source-dir (in-place migration)"
    )
    parser.add_argument(
        "--use-llm-summary",
        action="store_true",
        help="Use LLM for summary generation (slower, more accurate)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze without making any changes"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip 'already migrated' check and reindex anyway"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for LLM summary generation (default: 50)"
    )

    args = parser.parse_args()

    # target_dir по умолчанию совпадает с source_dir (in-place)
    target_dir = args.target_dir if args.target_dir else args.source_dir

    # ---------------------------------------------------------------------- #
    # Команда: список сервисов
    # ---------------------------------------------------------------------- #
    if args.list_services:
        services = list_services_in_source(args.source_dir)
        if not services:
            print(f"No services found in '{args.source_dir}'")
            sys.exit(0)

        print(f"\nServices in '{args.source_dir}':\n")
        print(f"  {'Service':<25} {'Pages':>8} {'MV docs':>10} {'Status':<15}")
        print("  " + "-" * 60)
        for s in services:
            print(
                f"  {s['service_code']:<25} {s['pages']:>8} "
                f"{s['mv_docs']:>10} {s['status']:<15}"
            )
        print()
        sys.exit(0)

    # ---------------------------------------------------------------------- #
    # Команда: миграция сервиса
    # ---------------------------------------------------------------------- #
    if not args.service:
        parser.error("Either --service or --list-services must be specified")

    logger.info("Starting Multi-Vector migration...")
    logger.info("  source-dir : %s", args.source_dir)
    logger.info("  target-dir : %s", target_dir)

    if args.dry_run:
        logger.info("DRY RUN MODE: no changes will be made")

    if os.path.abspath(args.source_dir) == os.path.abspath(target_dir):
        logger.info("Mode: in-place (source and target are the same directory)")
    else:
        logger.info("Mode: cross-store (source data will remain untouched)")

    stats = asyncio.run(
        migrate_service_async(
            service_code=args.service,
            source_dir=args.source_dir,
            target_dir=target_dir,
            dry_run=args.dry_run,
            use_llm_summary=args.use_llm_summary,
            force=args.force,
            batch_size=args.batch_size
        )
    )

    logger.info("Migration script completed")
    sys.exit(1 if stats["errors"] > 0 else 0)


if __name__ == "__main__":
    main()