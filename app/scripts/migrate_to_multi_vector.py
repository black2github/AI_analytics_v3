# Путь: scripts/migrate_to_multi_vector.py
"""
CLI скрипт для миграции существующих документов на Multi-Vector индексацию.

Использование:

  # Обновление на месте (source и target совпадают):
  python scripts/migrate_to_multi_vector.py --service CC --force

  # Миграция в новое хранилище (безопасный режим):
  python scripts/migrate_to_multi_vector.py --service CC \\
      --source-dir ./store/chroma_db \\
      --target-dir ./store/chroma_db2

  # Анализ без изменений:
  python scripts/migrate_to_multi_vector.py --service CC --dry-run

  # С LLM summary (медленнее, точнее):
  python scripts/migrate_to_multi_vector.py --service CC --use-llm-summary --batch-size 10

Параметры --source-dir и --target-dir переопределяют CHROMA_PERSIST_DIR из config
локально внутри скрипта, не затрагивая переменную окружения.
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.confluence_loader import load_pages_by_ids
from app.llm_interface import get_embeddings_model
from app.config import UNIFIED_STORAGE_NAME, CHROMA_PERSIST_DIR
from app.services.multi_vector_indexer import create_multi_vector_indexer

logging.basicConfig(
    level=logging.INFO,
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='%(asctime)s,%(msecs)03d [%(levelname)s] %(filename)s:%(lineno)d %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('migrate_to_multi_vector.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ — получение vectorstore с явным persist_dir
# =============================================================================

def _get_vectorstore_at(persist_dir: str, embeddings_model=None):
    """
    Создаёт Chroma vectorstore по явно указанному пути.

    Не использует CHROMA_PERSIST_DIR из config — принимает путь аргументом.
    Это позволяет независимо работать с source и target хранилищами
    независимо от текущего значения переменной окружения.
    """
    from langchain_chroma import Chroma

    if embeddings_model is None:
        embeddings_model = get_embeddings_model()

    return Chroma(
        collection_name=UNIFIED_STORAGE_NAME,
        embedding_function=embeddings_model,
        persist_directory=persist_dir
    )


# =============================================================================
# МИГРАТОР
# =============================================================================

class MultiVectorMigrator:
    """Миграция документов сервиса на Multi-Vector индексацию."""

    def __init__(
            self,
            source_dir: str,
            target_dir: str,
            dry_run: bool = False,
            use_llm_summary: bool = False,
            batch_size: int = 10
    ):
        """
        Args:
            source_dir: Путь к исходному ChromaDB (откуда читаем page_ids)
            target_dir: Путь к целевому ChromaDB (куда пишем новые документы)
            dry_run: Режим без изменений (только анализ)
            use_llm_summary: Использовать LLM для summary
            batch_size: Максимальное число параллельных LLM-запросов
        """
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.use_llm_summary = use_llm_summary
        self.batch_size = batch_size

        self.stats = {
            'total_pages': 0,
            'processed_pages': 0,
            'created_documents': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None,
        }

        logger.info(
            "[MultiVectorMigrator] <- source='%s', target='%s', "
            "dry_run=%s, llm_summary=%s, batch_size=%d",
            source_dir, target_dir, dry_run, use_llm_summary, batch_size
        )

        if source_dir == target_dir:
            logger.info("[MultiVectorMigrator] -> In-place mode: source == target")
        else:
            logger.info("[MultiVectorMigrator] -> Safe migration mode: source != target")

    async def migrate_service(self, service_code: str, force: bool = False) -> Dict:
        """
        Мигрирует все документы сервиса на Multi-Vector.

        Шаги:
        1. Читает page_ids из SOURCE хранилища
        2. Проверяет статус индексации в SOURCE
        3. Загружает страницы из Confluence
        4. Создаёт Multi-Vector документы (с LLM или extractive summary)
        5. Удаляет старые документы из TARGET и записывает новые в TARGET

        Args:
            service_code: Код сервиса (например, "CC")
            force: Переиндексировать даже если уже есть Multi-Vector документы
        """
        logger.info("=" * 70)
        logger.info("MIGRATING SERVICE: %s", service_code)
        logger.info("  source : %s", self.source_dir)
        logger.info("  target : %s", self.target_dir)
        logger.info("=" * 70)

        self.stats['start_time'] = datetime.now()
        embeddings_model = get_embeddings_model()

        # ------------------------------------------------------------------
        # Шаг 1. Читаем page_ids из SOURCE
        # ------------------------------------------------------------------
        logger.info("[Step 1/5] Fetching page_ids from source '%s'...", self.source_dir)

        source_vs = _get_vectorstore_at(self.source_dir, embeddings_model)
        page_ids = self._get_service_page_ids(source_vs, service_code)

        if not page_ids:
            logger.warning("[Step 1/5] No pages found for service '%s' in source.", service_code)
            return self.stats

        logger.info("[Step 1/5] Found %d unique pages", len(page_ids))
        self.stats['total_pages'] = len(page_ids)

        # ------------------------------------------------------------------
        # Шаг 2. Проверяем статус индексации в SOURCE
        # ------------------------------------------------------------------
        logger.info("[Step 2/5] Checking indexing status in source...")

        status = self._check_indexing_status(source_vs, page_ids)
        logger.info(
            "[Step 2/5] legacy=%d, multi_vector=%d, not_indexed=%d",
            status['legacy_count'], status['multi_vector_count'], status['not_indexed_count']
        )

        if status['multi_vector_count'] > 0 and not force:
            logger.warning(
                "[Step 2/5] %d pages already have Multi-Vector docs. Use --force to reindex.",
                status['multi_vector_count']
            )
            if not self._confirm_reindex():
                logger.info("Migration cancelled by user.")
                return self.stats

        # ------------------------------------------------------------------
        # Шаг 3. Загружаем страницы из Confluence
        # ------------------------------------------------------------------
        logger.info("[Step 3/5] Loading %d pages from Confluence...", len(page_ids))

        # TODO похоже лишняя операция, все есть в хранилище, можно брать из него.
        #  Но возможно проблема: эмебеддинг размер в исходном хранилище 384, а в целевом 768ю
        pages = load_pages_by_ids(page_ids)
        pages_with_content = [
            p for p in pages
            if p.get('approved_content') and p['approved_content'].strip()
        ]

        logger.info(
            "[Step 3/5] Loaded %d pages, %d have approved content",
            len(pages), len(pages_with_content)
        )

        if not pages_with_content:
            logger.error("[Step 3/5] No pages with approved content. Aborting.")
            return self.stats

        # ------------------------------------------------------------------
        # Шаг 4. Создаём Multi-Vector документы
        # ------------------------------------------------------------------
        logger.info(
            "[Step 4/5] Creating Multi-Vector documents "
            "(llm_summary=%s, batch_size=%d)...",
            # batch_size - число параллельных запросов к LLM для саммари
            self.use_llm_summary, self.batch_size
        )

        if self.dry_run:
            estimated = len(pages_with_content) * 3
            logger.info(
                "[Step 4/5] DRY RUN: would process %d pages, ~%d documents",
                len(pages_with_content), estimated
            )
            self.stats['processed_pages'] = len(pages_with_content)
            self._finalize_stats()
            return self.stats

        indexer = create_multi_vector_indexer(use_llm_summary=self.use_llm_summary)

        docs = await indexer.prepare_multi_vector_documents(
            pages=pages_with_content,
            service_code=service_code,
            doc_type="requirement",
            source="DBOCORPESPLN",
            batch_size=self.batch_size
        )

        logger.info("[Step 4/5] Created %d documents", len(docs))
        self.stats['created_documents'] = len(docs)
        self.stats['processed_pages'] = len(pages_with_content)

        # ------------------------------------------------------------------
        # Шаг 5. Обновляем TARGET хранилище
        # ------------------------------------------------------------------
        logger.info("[Step 5/5] Updating target '%s'...", self.target_dir)

        target_vs = _get_vectorstore_at(self.target_dir, embeddings_model)

        # Удаляем старые документы в target (если in-place или повторная миграция)
        page_ids_to_delete = [p['id'] for p in pages_with_content]
        logger.info(
            "[Step 5/5] Deleting old documents for %d pages from target...",
            len(page_ids_to_delete)
        )

        target_vs.delete(where={
            "$and": [
                {"page_id": {"$in": page_ids_to_delete}},
                {"doc_type": {"$eq": "requirement"}}
            ]
        })

        # Записываем новые документы.
        # ВАЖНО: add_documents работает быстро только в пустое хранилище.
        # При вставке в непустую коллекцию скорость деградирует — использовать
        # отдельное хранилище для каждой полной миграции (--target-dir новый путь).
        logger.info("[Step 5/5] Adding %d new documents to target...", len(docs))
        target_vs.add_documents(docs)
        logger.info("[Step 5/5] Target updated successfully.")

        self._finalize_stats()
        return self.stats

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # -------------------------------------------------------------------------


    async def migrate_all_services(self, force: bool = False) -> Dict:
        """
        Мигрирует ВСЕ сервисы из source в target за один проход.

        Стратегия: собирает документы всех сервисов последовательно,
        вставляет каждый сервис в target пока хранилище ещё небольшое.
        Целевое хранилище должно быть пустым — это гарантирует линейную
        скорость вставки без деградации HNSW индекса.

        Args:
            force: Переиндексировать даже если уже есть Multi-Vector документы
        """
        logger.info("=" * 70)
        logger.info("MIGRATING ALL SERVICES")
        logger.info("  source : %s", self.source_dir)
        logger.info("  target : %s", self.target_dir)
        logger.info("=" * 70)

        self.stats['start_time'] = datetime.now()
        embeddings_model = get_embeddings_model()

        # Получаем список всех сервисов из source
        source_vs = _get_vectorstore_at(self.source_dir, embeddings_model)
        service_codes = self._get_all_service_codes(source_vs)

        if not service_codes:
            logger.warning("No services found in source.")
            self._finalize_stats()
            return self.stats

        logger.info("Found %d services: %s", len(service_codes), sorted(service_codes))

        # Проверяем что target пустой (иначе деградация неизбежна)
        target_vs = _get_vectorstore_at(self.target_dir, embeddings_model)
        target_count = len(target_vs.get(include=[])['ids'])
        if target_count > 0 and not force:
            logger.warning(
                "Target already contains %d documents. "
                "Migration into non-empty store will be slow. "
                "Use --force to proceed anyway, or use an empty --target-dir.",
                target_count
            )
            if not self._confirm_reindex():
                logger.info("Migration cancelled.")
                self._finalize_stats()
                return self.stats

        # Мигрируем каждый сервис
        for i, service_code in enumerate(sorted(service_codes), 1):
            logger.info(
                "--- Service %d/%d: %s ---",
                i, len(service_codes), service_code
            )
            try:
                await self.migrate_service(service_code, force=force)
            except Exception as e:
                logger.error("Error migrating service %s: %s", service_code, e, exc_info=True)
                self.stats['errors'] += 1

        self._finalize_stats()
        return self.stats

    def _get_all_service_codes(self, vectorstore) -> List[str]:
        """Возвращает список уникальных service_code из хранилища."""
        results = vectorstore.get(
            where={"doc_type": {"$eq": "requirement"}},
            include=["metadatas"]
        )
        if not results or not results.get("metadatas"):
            return []
        return list({
            m["service_code"]
            for m in results["metadatas"]
            if m.get("service_code")
        })

    def _get_service_page_ids(self, vectorstore, service_code: str) -> List[str]:
        """
        Возвращает уникальные page_ids сервиса из хранилища.

        Использует vectorstore.get() вместо similarity_search() —
        это не вычисляет embeddings и работает на порядок быстрее.
        """
        results = vectorstore.get(
            where={
                "$and": [
                    {"service_code": {"$eq": service_code}},
                    {"doc_type": {"$eq": "requirement"}}
                ]
            },
            include=["metadatas"]
        )

        if not results or not results.get("metadatas"):
            return []

        # Дедупликация — в Multi-Vector хранилище одна страница = несколько документов
        page_ids = list({
            m["page_id"]
            for m in results["metadatas"]
            if m.get("page_id")
        })

        return page_ids

    def _check_indexing_status(self, vectorstore, page_ids: List[str]) -> Dict:
        """Проверяет статус индексации страниц в хранилище."""
        results = vectorstore.get(
            where={
                "$and": [
                    {"page_id": {"$in": page_ids}},
                    {"doc_type": {"$eq": "requirement"}}
                ]
            },
            include=["metadatas"]
        )

        page_status: Dict[str, str] = {}
        for meta in (results.get("metadatas") or []):
            pid = meta.get("page_id")
            if not pid:
                continue
            if meta.get("vector_type"):
                page_status[pid] = "multi_vector"
            elif pid not in page_status:
                page_status[pid] = "legacy"

        return {
            "legacy_count": sum(1 for s in page_status.values() if s == "legacy"),
            "multi_vector_count": sum(1 for s in page_status.values() if s == "multi_vector"),
            "not_indexed_count": len(page_ids) - len(page_status),
        }


    def _confirm_reindex(self) -> bool:
        """Запрашивает подтверждение у пользователя."""
        response = input("Continue with reindexing? [y/N]: ")
        return response.strip().lower() in ("y", "yes")

    def _finalize_stats(self):
        """Логирует итоговую статистику."""
        self.stats['end_time'] = datetime.now()
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        logger.info("=" * 70)
        logger.info("MIGRATION COMPLETED")
        logger.info("  total pages    : %d", self.stats['total_pages'])
        logger.info("  processed pages: %d", self.stats['processed_pages'])
        logger.info("  created docs   : %d", self.stats['created_documents'])
        logger.info("  errors         : %d", self.stats['errors'])
        logger.info("  duration       : %.1f sec (%.1f min)",
                    duration, duration / 60)
        logger.info("=" * 70)


# =============================================================================
# ASYNC ОБЁРТКА
# =============================================================================

async def migrate_service_async(
        service_code: str,
        source_dir: str,
        target_dir: str,
        dry_run: bool = False,
        use_llm_summary: bool = False,
        force: bool = False,
        batch_size: int = 10,
        all_services: bool = False
) -> Dict:
    migrator = MultiVectorMigrator(
        source_dir=source_dir,
        target_dir=target_dir,
        dry_run=dry_run,
        use_llm_summary=use_llm_summary,
        batch_size=batch_size
    )
    if all_services:
        return await migrator.migrate_all_services(force=force)
    return await migrator.migrate_service(service_code, force=force)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Migrate service documents to Multi-Vector indexing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # In-place reindex (update existing store):
  python scripts/migrate_to_multi_vector.py --service CC --force

  # Safe migration to new store:
  python scripts/migrate_to_multi_vector.py --service CC \\
      --source-dir ./store/chroma_db \\
      --target-dir ./store/chroma_db2

  # Dry run (analysis only):
  python scripts/migrate_to_multi_vector.py --service CC --dry-run

  # With LLM summary (slower, more accurate):
  python scripts/migrate_to_multi_vector.py --service CC \\
      --use-llm-summary --batch-size 10 --force
        """
    )

    parser.add_argument(
        '--service', type=str, default=None,
        help='Service code to migrate (e.g., CC). Required unless --all-services is used.'
    )
    parser.add_argument(
        '--all-services', action='store_true',
        help=(
            'Migrate all services found in source store. '
            'Target store should be empty for best performance.'
        )
    )
    parser.add_argument(
        '--source-dir', type=str, default=None,
        help=(
            'Source ChromaDB directory to read page_ids from. '
            'Defaults to CHROMA_PERSIST_DIR from config.'
        )
    )
    parser.add_argument(
        '--target-dir', type=str, default=None,
        help=(
            'Target ChromaDB directory to write new documents to. '
            'Defaults to --source-dir (in-place update).'
        )
    )
    parser.add_argument(
        '--use-llm-summary', action='store_true',
        help='Use LLM for summary generation (slower, more accurate). '
             'All LLM calls run in a single parallel batch before indexing.'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Analyze without making any changes'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Reindex even if Multi-Vector documents already exist'
    )
    parser.add_argument(
        '--batch-size', type=int, default=10,
        help='Max parallel LLM requests for summary generation (default: 10)'
    )

    args = parser.parse_args()

    # Разрешаем пути: source и target
    source_dir = os.path.abspath(args.source_dir) if args.source_dir else os.path.abspath(CHROMA_PERSIST_DIR)
    target_dir = os.path.abspath(args.target_dir) if args.target_dir else source_dir

    logger.info("Starting Multi-Vector migration...")
    logger.info("  service   : %s", args.service)
    logger.info("  source    : %s", source_dir)
    logger.info("  target    : %s", target_dir)
    logger.info("  llm       : %s", args.use_llm_summary)
    logger.info("  batch_size: %d", args.batch_size)
    logger.info("  force     : %s", args.force)
    logger.info("  dry_run   : %s", args.dry_run)

    if args.dry_run:
        logger.info("DRY RUN MODE: no changes will be made")

    if source_dir != target_dir and not os.path.exists(source_dir):
        logger.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    if not args.all_services and not args.service:
        parser.error('Either --service or --all-services must be specified.')

    stats = asyncio.run(
        migrate_service_async(
            service_code=args.service or '',
            source_dir=source_dir,
            target_dir=target_dir,
            dry_run=args.dry_run,
            use_llm_summary=args.use_llm_summary,
            force=args.force,
            batch_size=args.batch_size,
            all_services=args.all_services
        )
    )

    logger.info("Migration script finished.")
    sys.exit(1 if stats['errors'] > 0 else 0)


if __name__ == '__main__':
    main()