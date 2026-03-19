# Путь: app/scripts/migrate_to_multi_vector.py
"""
CLI скрипт для миграции существующих документов на Multi-Vector индексацию.

Использование:
    python app/scripts/migrate_to_multi_vector.py --service CC [--force]
    python app/scripts/migrate_to_multi_vector.py --service CC --use-llm-summary
    python app/scripts/migrate_to_multi_vector.py --all-services
    python app/scripts/migrate_to_multi_vector.py --dry-run --service CC
"""

import logging
import argparse
import asyncio
import sys
from typing import List, Dict, Optional
from datetime import datetime
import logging

# Добавляем корень проекта в PYTHONPATH
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.embedding_store import get_vectorstore, get_service_page_ids
from app.confluence_loader import load_pages_by_ids
from app.llm_interface import get_embeddings_model
from app.config import UNIFIED_STORAGE_NAME
from app.services.multi_vector_indexer import create_multi_vector_indexer

# Настройка логирования в начале файла
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('multi_vector_indexer.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MultiVectorMigrator:
    """Класс для миграции документов на Multi-Vector индексацию."""

    def __init__(
            self,
            dry_run: bool = False,
            use_llm_summary: bool = False,
            batch_size: int = 50
    ):
        """
        Args:
            dry_run: Режим без изменений (только анализ)
            use_llm_summary: Использовать LLM для summary
            batch_size: Размер батча для обработки
        """
        self.dry_run = dry_run
        self.use_llm_summary = use_llm_summary
        self.batch_size = batch_size

        # Статистика
        self.stats = {
            'total_pages': 0,
            'processed_pages': 0,
            'created_documents': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }

        logger.info(
            "[MultiVectorMigrator] Initialized (dry_run=%s, llm_summary=%s)",
            dry_run, use_llm_summary
        )

    async def migrate_service(
            self,
            service_code: str,
            force: bool = False
    ) -> Dict:
        """
        Мигрирует все документы сервиса на Multi-Vector.

        Args:
            service_code: Код сервиса
            force: Переиндексировать даже если уже есть Multi-Vector документы

        Returns:
            Статистика миграции
        """
        logger.info("=" * 80)
        logger.info("MIGRATING SERVICE: %s", service_code)
        logger.info("=" * 80)

        self.stats['start_time'] = datetime.now()

        # 1. Получаем все page_ids сервиса
        logger.info("[Step 1/5] Fetching page_ids for service '%s'...", service_code)
        page_ids = get_service_page_ids(service_code, doc_type="requirement")

        if not page_ids:
            logger.warning("No pages found for service '%s'", service_code)
            return self.stats

        logger.info("Found %d pages", len(page_ids))
        self.stats['total_pages'] = len(page_ids)

        # 2. Проверяем текущий статус индексации
        logger.info("[Step 2/5] Checking current indexing status...")

        current_status = self._check_indexing_status(page_ids)

        logger.info("Current status:")
        logger.info("  - Legacy indexed: %d pages", current_status['legacy_count'])
        logger.info("  - Multi-Vector indexed: %d pages", current_status['multi_vector_count'])
        logger.info("  - Not indexed: %d pages", current_status['not_indexed_count'])

        if current_status['multi_vector_count'] > 0 and not force:
            logger.warning(
                "Service already has %d Multi-Vector indexed pages. "
                "Use --force to reindex anyway.",
                current_status['multi_vector_count']
            )

            if not self._confirm_reindex():
                logger.info("Migration cancelled by user")
                return self.stats

        # 3. Загружаем страницы из Confluence
        logger.info("[Step 3/5] Loading pages from Confluence...")

        pages = load_pages_by_ids(page_ids)

        logger.info("Loaded %d pages", len(pages))

        # Фильтруем страницы с approved content
        pages_with_approved = [
            p for p in pages
            if p.get('approved_content') and p['approved_content'].strip()
        ]

        logger.info(
            "Pages with approved content: %d/%d",
            len(pages_with_approved), len(pages)
        )

        if not pages_with_approved:
            logger.error("No pages with approved content found!")
            return self.stats

        # 4. Создаём Multi-Vector документы
        logger.info("[Step 4/5] Creating Multi-Vector documents...")
        logger.info("  - LLM Summary: %s", self.use_llm_summary)
        logger.info("  - Batch size: %d", self.batch_size)

        if self.dry_run:
            logger.info("DRY RUN MODE: Skipping document creation")
            self.stats['processed_pages'] = len(pages_with_approved)
            estimated_docs = len(pages_with_approved) * 3  # Примерно title + summary + content
            logger.info("Would create approximately %d documents", estimated_docs)
        else:
            indexer = create_multi_vector_indexer(use_llm_summary=self.use_llm_summary)

            docs = await indexer.prepare_multi_vector_documents(
                pages=pages_with_approved,
                service_code=service_code,
                doc_type="requirement",
                source="DBOCORPESPLN",
                batch_size=self.batch_size
            )

            logger.info("Created %d documents", len(docs))
            self.stats['created_documents'] = len(docs)
            self.stats['processed_pages'] = len(pages_with_approved)

            # 5. Удаляем старые документы и сохраняем новые
            logger.info("[Step 5/5] Updating vectorstore...")

            embeddings_model = get_embeddings_model()
            vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

            # Удаляем старые
            page_ids_to_delete = [p['id'] for p in pages_with_approved]

            logger.info("Deleting old documents for %d pages...", len(page_ids_to_delete))

            vectorstore.delete(where={
                "$and": [
                    {"page_id": {"$in": page_ids_to_delete}},
                    {"doc_type": {"$eq": "requirement"}}
                ]
            })

            # Сохраняем новые батчами.
            # ChromaDB ограничивает размер одного upsert-запроса (~5000 документов).
            # Разбиваем на батчи с запасом ниже лимита.
            CHROMA_BATCH_SIZE = 2000
            total_docs = len(docs)
            logger.info(
                "Adding %d new Multi-Vector documents in batches of %d...",
                total_docs, CHROMA_BATCH_SIZE
            )

            for batch_start in range(0, total_docs, CHROMA_BATCH_SIZE):
                batch = docs[batch_start: batch_start + CHROMA_BATCH_SIZE]
                batch_num = batch_start // CHROMA_BATCH_SIZE + 1
                total_batches = (total_docs + CHROMA_BATCH_SIZE - 1) // CHROMA_BATCH_SIZE
                logger.info(
                    "  Batch %d/%d: %d documents",
                    batch_num, total_batches, len(batch)
                )
                vectorstore.add_documents(batch)

            logger.info("Vectorstore updated successfully! Total documents added: %d", total_docs)

        self.stats['end_time'] = datetime.now()
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        logger.info("=" * 80)
        logger.info("MIGRATION COMPLETED")
        logger.info("=" * 80)
        logger.info("Statistics:")
        logger.info("  - Total pages: %d", self.stats['total_pages'])
        logger.info("  - Processed pages: %d", self.stats['processed_pages'])
        logger.info("  - Created documents: %d", self.stats['created_documents'])
        logger.info("  - Errors: %d", self.stats['errors'])
        logger.info("  - Duration: %.1f seconds", duration)
        logger.info("=" * 80)

        return self.stats

    def _check_indexing_status(self, page_ids: List[str]) -> Dict:
        """
        Проверяет текущий статус индексации для списка страниц.

        Returns:
            {
                'legacy_count': int,
                'multi_vector_count': int,
                'not_indexed_count': int
            }
        """
        embeddings_model = get_embeddings_model()
        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

        # Получаем все документы для этих страниц
        results = vectorstore.get(
            where={
                "$and": [
                    {"page_id": {"$in": page_ids}},
                    {"doc_type": {"$eq": "requirement"}}
                ]
            },
            include=['metadatas']
        )

        # Анализируем
        page_status = {}

        if results.get('metadatas'):
            for metadata in results['metadatas']:
                page_id = metadata.get('page_id')
                vector_type = metadata.get('vector_type')

                if vector_type:
                    # Multi-Vector документ
                    page_status[page_id] = 'multi_vector'
                else:
                    # Legacy документ
                    if page_id not in page_status:
                        page_status[page_id] = 'legacy'

        # Подсчёт
        multi_vector_count = len([s for s in page_status.values() if s == 'multi_vector'])
        legacy_count = len([s for s in page_status.values() if s == 'legacy'])
        not_indexed_count = len(page_ids) - len(page_status)

        return {
            'legacy_count': legacy_count,
            'multi_vector_count': multi_vector_count,
            'not_indexed_count': not_indexed_count
        }

    def _confirm_reindex(self) -> bool:
        """Запрашивает подтверждение у пользователя."""
        response = input("Continue with reindexing? [y/N]: ")
        return response.lower() in ('y', 'yes')


async def migrate_service_async(
        service_code: str,
        dry_run: bool = False,
        use_llm_summary: bool = False,
        force: bool = False,
        batch_size: int = 50
):
    """Async функция для миграции сервиса."""
    migrator = MultiVectorMigrator(
        dry_run=dry_run,
        use_llm_summary=use_llm_summary,
        batch_size=batch_size
    )

    stats = await migrator.migrate_service(service_code, force=force)

    return stats


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate existing documents to Multi-Vector indexing"
    )

    parser.add_argument(
        '--service',
        type=str,
        help='Service code to migrate (e.g., CC, RKO_PP)'
    )

    parser.add_argument(
        '--all-services',
        action='store_true',
        help='Migrate all services (not implemented yet)'
    )

    parser.add_argument(
        '--use-llm-summary',
        action='store_true',
        help='Use LLM for summary generation (slower, more accurate)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Analyze without making changes'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reindexing even if Multi-Vector documents exist'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Batch size for LLM summary generation (default: 50)'
    )

    args = parser.parse_args()

    if not args.service and not args.all_services:
        parser.error("Either --service or --all-services must be specified")

    if args.all_services:
        print("ERROR: --all-services not implemented yet. Use --service <code>")
        sys.exit(1)

    # Запускаем миграцию
    logger.info("Starting Multi-Vector migration...")

    if args.dry_run:
        logger.info("DRY RUN MODE: No changes will be made")

    stats = asyncio.run(
        migrate_service_async(
            service_code=args.service,
            dry_run=args.dry_run,
            use_llm_summary=args.use_llm_summary,
            force=args.force,
            batch_size=args.batch_size
        )
    )

    logger.info("Migration script completed")

    # Exit code
    if stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()