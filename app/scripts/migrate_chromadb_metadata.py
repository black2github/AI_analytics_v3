# app/scripts/migrate_chromadb_metadata.py

"""
Скрипт миграции метаданных в ChromaDB.

Обновляет существующие документы:
1. Добавляет requirement_type для документов без него
2. Добавляет target_system для интеграций
3. Нормализует requirement_type (None → "unknown")

Использование:
    python app/scripts/migrate_chromadb_metadata.py [--dry-run] [--service-code CODE]

Опции:
    --dry-run         Показать что будет изменено без применения
    --service-code    Обработать только конкретный сервис
    --batch-size      Размер батча для обработки (по умолчанию 100)
"""

import sys
import os
import logging
import argparse
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# Добавляем корневую директорию проекта в путь
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, os.path.join(project_root, 'app'))

# Меняем рабочую директорию на корень проекта
# чтобы пути к ChromaDB и другим ресурсам работали правильно
os.chdir(project_root)

# Теперь можем импортировать модули приложения
from app.embedding_store import get_vectorstore
from app.config import UNIFIED_STORAGE_NAME
from app.page_cache import get_page_data_cached
from app.services.template_type_analysis import analyze_content_template_type
from app.services.integration_parser import extract_target_system_from_title

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MetadataMigrator:
    """Класс для миграции метаданных в ChromaDB"""

    def __init__(self, dry_run: bool = False, service_code: Optional[str] = None):
        self.dry_run = dry_run
        self.service_code = service_code

        # Логируем текущую рабочую директорию и путь к ChromaDB
        from app.config import CHROMA_PERSIST_DIR
        logger.info("Current working directory: %s", os.getcwd())
        logger.info("ChromaDB persist directory: %s", CHROMA_PERSIST_DIR)
        logger.info("ChromaDB absolute path: %s", os.path.abspath(CHROMA_PERSIST_DIR))
        logger.info("ChromaDB exists: %s", os.path.exists(CHROMA_PERSIST_DIR))

        logger.info("Initializing vectorstore...")
        self.vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME)
        logger.info("Vectorstore initialized successfully")

        # Статистика
        self.stats = {
            'total_docs': 0,
            'requirement_type_added': 0,
            'requirement_type_unknown': 0,
            'target_system_added': 0,
            'errors': 0,
            'skipped': 0
        }

        # Детали изменений для отчёта
        self.changes = defaultdict(list)

    def migrate(self, batch_size: int = 100) -> Dict:
        """
        Выполняет миграцию всех документов.

        Args:
            batch_size: Размер батча для обработки

        Returns:
            Словарь со статистикой миграции
        """
        logger.info("=" * 80)
        logger.info("Starting ChromaDB metadata migration")
        logger.info("Dry run: %s", self.dry_run)
        logger.info("Service filter: %s", self.service_code or "ALL")
        logger.info("=" * 80)

        # Получаем все документы для миграции
        documents = self._fetch_documents()

        if not documents:
            logger.warning("No documents found for migration")
            return self.stats

        self.stats['total_docs'] = len(documents)
        logger.info("Found %d documents to process", len(documents))

        # Обрабатываем батчами
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(documents) + batch_size - 1) // batch_size

            logger.info("Processing batch %d/%d (%d documents)...",
                        batch_num, total_batches, len(batch))

            self._process_batch(batch)

        # Печатаем финальный отчёт
        self._print_report()

        return self.stats

    def _fetch_documents(self) -> List:
        """
        Получает все документы из ChromaDB для миграции.
        """
        logger.info("Fetching documents from ChromaDB...")

        try:
            # Получаем коллекцию напрямую
            logger.info("Getting collection reference...")
            collection = self.vectorstore._collection
            logger.info("Collection name: %s", collection.name)

            total_count = collection.count()
            logger.info("Total documents in collection: %d", total_count)

            if total_count == 0:
                logger.warning("Collection is empty!")
                return []

            # Фильтр для выборки с правильным синтаксисом ChromaDB
            if self.service_code:
                # Множественные условия требуют оператор $and
                where_filter = {
                    "$and": [
                        {"doc_type": "requirement"},
                        {"service_code": self.service_code}
                    ]
                }
            else:
                # Одно условие - без оператора
                where_filter = {"doc_type": "requirement"}

            logger.info("Using filter: %s", where_filter)

            # Используем get() с фильтром - это правильный способ получить все документы
            logger.info("Calling collection.get()...")
            result = collection.get(
                where=where_filter,
                include=["documents", "metadatas"]
            )
            logger.info("collection.get() returned, processing results...")

            # Преобразуем результат в формат Document
            from langchain_core.documents import Document
            documents = []

            if result and result['documents']:
                logger.info("Converting %d documents to Document objects...", len(result['documents']))
                for i, (doc_text, metadata) in enumerate(zip(result['documents'], result['metadatas'])):
                    if i % 100 == 0:
                        logger.info("  Processed %d/%d documents...", i, len(result['documents']))
                    documents.append(Document(
                        page_content=doc_text,
                        metadata=metadata
                    ))
            else:
                logger.warning("No documents found in result")

            logger.info("Fetched %d documents", len(documents))
            return documents

        except Exception as e:
            logger.error("Error fetching documents: %s", str(e), exc_info=True)
            return []

    def _process_batch(self, batch: List):
        """
        Обрабатывает батч документов.
        """
        for doc in batch:
            try:
                self._process_document(doc)
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(
                    "Error processing document %s: %s",
                    doc.metadata.get('page_id', 'unknown'),
                    str(e)
                )

    def _process_document(self, doc):
        """
        Обрабатывает один документ.
        """
        metadata = doc.metadata
        page_id = metadata.get('page_id', 'unknown')
        title = metadata.get('title', '')

        logger.debug("Processing page_id=%s, title='%s'", page_id, title)

        # Флаг изменений
        needs_update = False
        updated_metadata = metadata.copy()
        changes_for_doc = []

        # 1. Проверка requirement_type
        current_type = metadata.get('requirement_type')

        if not current_type or current_type == '':
            # Нужно определить тип
            new_type = self._determine_requirement_type(page_id, title)

            if new_type and new_type != 'unknown':
                updated_metadata['requirement_type'] = new_type
                needs_update = True
                self.stats['requirement_type_added'] += 1
                changes_for_doc.append(f"requirement_type: None → {new_type}")
                logger.info("  [%s] Added requirement_type: %s", page_id, new_type)
            else:
                updated_metadata['requirement_type'] = 'unknown'
                needs_update = True
                self.stats['requirement_type_unknown'] += 1
                changes_for_doc.append("requirement_type: None → unknown")
                logger.debug("  [%s] Set requirement_type to 'unknown'", page_id)

        # 2. Проверка target_system для интеграций
        req_type = updated_metadata.get('requirement_type')
        current_target = metadata.get('target_system')

        if req_type == 'integration' and not current_target:
            # Извлекаем target_system из заголовка
            target_system = extract_target_system_from_title(title)

            if target_system:
                updated_metadata['target_system'] = target_system
                needs_update = True
                self.stats['target_system_added'] += 1
                changes_for_doc.append(f"target_system: None → {target_system}")
                logger.info("  [%s] Added target_system: %s", page_id, target_system)

        # 3. Применяем изменения
        if needs_update:
            if not self.dry_run:
                self._update_document(doc, updated_metadata)

            # Сохраняем изменения для отчёта
            self.changes[page_id] = {
                'title': title,
                'changes': changes_for_doc
            }
        else:
            self.stats['skipped'] += 1
            logger.debug("  [%s] No changes needed", page_id)

    def _determine_requirement_type(self, page_id: str, title: str) -> str:
        """
        Определяет тип требования для документа.

        1. Пытается получить данные страницы из кеша
        2. Использует analyze_content_template_type для определения типа
        3. Возвращает 'unknown' если не удалось определить
        """
        try:
            # Получаем данные страницы
            page_data = get_page_data_cached(page_id)

            if not page_data:
                logger.warning("  [%s] Could not load page data from cache", page_id)
                return 'unknown'

            raw_html = page_data.get('raw_html')

            if not raw_html:
                logger.warning("  [%s] No HTML content in cached data", page_id)
                return 'unknown'

            # Анализируем тип
            req_type = analyze_content_template_type(title, raw_html)

            return req_type if req_type else 'unknown'

        except Exception as e:
            logger.warning("  [%s] Error determining type: %s", page_id, str(e))
            return 'unknown'

    def _update_document(self, doc, updated_metadata: Dict):
        """
        Обновляет метаданные документа в ChromaDB.

        ChromaDB не имеет прямого API для обновления метаданных,
        поэтому используем update через collection.
        """
        try:
            # Получаем collection напрямую
            collection = self.vectorstore._collection

            # Обновляем метаданные
            # ChromaDB требует ID документа для обновления
            doc_id = doc.metadata.get('page_id')  # Используем page_id как ID

            # Update метаданных
            collection.update(
                ids=[doc_id],
                metadatas=[updated_metadata]
            )

            logger.debug("  Updated metadata in ChromaDB for page_id=%s", doc_id)

        except Exception as e:
            logger.error("  Error updating document in ChromaDB: %s", str(e))
            raise

    def _print_report(self):
        """
        Печатает финальный отчёт о миграции.
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info("MIGRATION REPORT")
        logger.info("=" * 80)
        logger.info("Mode: %s", "DRY RUN (no changes applied)" if self.dry_run else "PRODUCTION")
        logger.info("")
        logger.info("Statistics:")
        logger.info("  Total documents processed: %d", self.stats['total_docs'])
        logger.info("  requirement_type added: %d", self.stats['requirement_type_added'])
        logger.info("  requirement_type set to 'unknown': %d", self.stats['requirement_type_unknown'])
        logger.info("  target_system added: %d", self.stats['target_system_added'])
        logger.info("  Skipped (no changes): %d", self.stats['skipped'])
        logger.info("  Errors: %d", self.stats['errors'])
        logger.info("")

        if self.changes:
            logger.info("Changes by document (first 20):")
            for i, (page_id, details) in enumerate(list(self.changes.items())[:20], 1):
                logger.info("  %d. [%s] %s", i, page_id, details['title'])
                for change in details['changes']:
                    logger.info("     - %s", change)

            if len(self.changes) > 20:
                logger.info("  ... and %d more documents", len(self.changes) - 20)

        logger.info("=" * 80)

        if self.dry_run:
            logger.info("")
            logger.info("This was a DRY RUN. To apply changes, run without --dry-run flag.")
            logger.info("")


def main():
    """Основная функция скрипта"""
    parser = argparse.ArgumentParser(
        description='Migrate ChromaDB metadata for requirements'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without applying changes'
    )
    parser.add_argument(
        '--service-code',
        type=str,
        help='Process only specific service (e.g., CC, SBP)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Batch size for processing (default: 100)'
    )

    args = parser.parse_args()

    try:
        # Создаём мигратор
        migrator = MetadataMigrator(
            dry_run=args.dry_run,
            service_code=args.service_code
        )

        # Запускаем миграцию
        stats = migrator.migrate(batch_size=args.batch_size)

        # Возвращаем код выхода
        if stats['errors'] > 0:
            logger.error("Migration completed with errors")
            sys.exit(1)
        else:
            logger.info("Migration completed successfully")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\nMigration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("Migration failed: %s", str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()