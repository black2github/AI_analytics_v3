# Путь: scripts/link_integrations.py
"""
Скрипт связывания интеграционных методов с бизнес-сервисами.

Проблема:
    Страницы с описанием интеграционных методов хранятся в общем каталоге
    Confluence и индексируются под service_code=INT (или другим кодом каталога).
    При поиске по service_code=CC интеграционные методы, используемые сервисом CC,
    не находятся, потому что они не принадлежат CC в ChromaDB.

Решение (Вариант А — дублирование):
    Парсим раздел "Где используется" / "Как вызывается" каждой интеграционной
    страницы. Извлекаем title wiki-ссылок. Ищем эти title в ChromaDB — получаем
    service_code страниц-потребителей. Создаём копии всех векторов интеграционной
    страницы с новым service_code для каждого найденного сервиса.

Последовательность запуска:
    1. Загрузить страницы бизнес-сервисов (через /load_external_pages или migrate)
    2. Загрузить страницы общего каталога интеграций (через /load_external_pages,
       service_code=INT или другой код)
    3. Запустить этот скрипт

Использование:
    # Связать все интеграции:
    python scripts/link_integrations.py

    # Только для конкретного сервиса (пересоздать связи CC):
    python scripts/link_integrations.py --service CC

    # Анализ без изменений:
    python scripts/link_integrations.py --dry-run

    # Принудительно пересоздать существующие связи:
    python scripts/link_integrations.py --force
"""

import argparse
import logging
import os
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import UNIFIED_STORAGE_NAME, CHROMA_PERSIST_DIR
from app.llm_interface import get_embeddings_model
from langchain_chroma import Chroma
from langchain_core.documents import Document

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('link_integrations.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# ПАРСИНГ "ГДЕ ИСПОЛЬЗУЕТСЯ"
# =============================================================================

# Паттерн строки таблицы с разделом "где используется" / "как вызывается"
_USED_BY_ROW_PATTERN = re.compile(
    r'^\|\s*(?:Где используется|Как вызывается)\s*:?\s*\|'
    r'\s*(.+?)\s*\|?\s*$',
    re.IGNORECASE | re.MULTILINE
)

# Паттерн wiki-ссылки Confluence в формате [[Код] Полное название страницы]
# Внешние квадратные скобки обрамляют весь title целиком, включая внутренние.
# Примеры из реальных данных:
#   [[ОНБ_2021] ЭФ Общая "Ввод данных физических лиц"]
#   [[КК_ВК] Клиент: Функция загрузки файла для распознавания паспорта]
#   [[АС СБП_СИП_Запрос истории операций СБП V2 (B2B+B2C)]]
# Паттерн захватывает всё содержимое внешних скобок как единый title.
_WIKI_LINK_PATTERN = re.compile(
    r'\[(\[[^\]]+\][^\]]*)\]'  # [[...] ...] — захватываем весь title целиком
)


def extract_used_by_titles(content: str) -> List[str]:
    """
    Извлекает названия страниц из раздела "Где используется" / "Как вызывается".

    Парсит строку таблицы краткого описания метода, находит все wiki-ссылки
    и возвращает title страниц-потребителей.

    Args:
        content: Markdown-контент интеграционной страницы

    Returns:
        Список title страниц, использующих данный интеграционный метод
    """
    if not content:
        return []

    match = _USED_BY_ROW_PATTERN.search(content)
    if not match:
        logger.debug("[extract_used_by_titles] No 'Где используется' row found")
        return []

    cell_value = match.group(1).strip()
    logger.debug("[extract_used_by_titles] Cell value: %s", cell_value[:200])

    titles = []
    for link_match in _WIKI_LINK_PATTERN.finditer(cell_value):
        title = link_match.group(1).strip()
        if title:
            titles.append(title)

    logger.debug("[extract_used_by_titles] Found %d titles: %s", len(titles), titles)
    return titles


# =============================================================================
# РЕЗОЛВИНГ service_code ПО TITLE
# =============================================================================

def resolve_service_codes_by_titles(
    vectorstore: Chroma,
    titles: List[str]
) -> Dict[str, str]:
    """
    Определяет service_code для каждого title через поиск в ChromaDB.

    Логика: title страницы уникален в Confluence и хранится в метаданных
    каждого документа. Ищем точное совпадение по полю title в метаданных.

    Args:
        vectorstore: ChromaDB хранилище
        titles: Список title страниц для резолвинга

    Returns:
        Словарь {title: service_code} для найденных страниц
    """
    result: Dict[str, str] = {}

    for title in titles:
        if not title:
            continue
        try:
            docs = vectorstore.get(
                where={
                    "$and": [
                        {"title": {"$eq": title}},
                        {"doc_type": {"$eq": "requirement"}},
                        {"vector_type": {"$eq": "title"}}
                    ]
                },
                include=["metadatas"],
                limit=1
            )

            if docs and docs.get("metadatas"):
                service_code = docs["metadatas"][0].get("service_code")
                if service_code:
                    result[title] = service_code
                    logger.debug(
                        "[resolve_service_codes] '%s' -> service_code='%s'",
                        title, service_code
                    )
                else:
                    logger.debug(
                        "[resolve_service_codes] '%s' found but no service_code",
                        title
                    )
            else:
                logger.debug(
                    "[resolve_service_codes] '%s' not found in ChromaDB",
                    title
                )

        except Exception as e:
            logger.warning(
                "[resolve_service_codes] Error looking up '%s': %s", title, e
            )

    return result


# =============================================================================
# ПОЛУЧЕНИЕ ВСЕХ ВЕКТОРОВ ИНТЕГРАЦИОННОЙ СТРАНИЦЫ
# =============================================================================

def get_integration_page_vectors(
    vectorstore: Chroma,
    page_id: str
) -> List[Tuple[str, str, Dict]]:
    """
    Возвращает все векторные документы для интеграционной страницы.

    Args:
        vectorstore: ChromaDB хранилище
        page_id: Идентификатор страницы

    Returns:
        Список (doc_id, page_content, metadata)
    """
    results = vectorstore.get(
        where={
            "$and": [
                {"page_id": {"$eq": page_id}},
                {"doc_type": {"$eq": "requirement"}}
            ]
        },
        include=["documents", "metadatas"]
    )

    if not results or not results.get("ids"):
        return []

    return list(zip(
        results["ids"],
        results["documents"],
        results["metadatas"]
    ))


# =============================================================================
# ОСНОВНАЯ ЛОГИКА
# =============================================================================

class IntegrationLinker:
    """Связывает интеграционные методы с бизнес-сервисами через дублирование."""

    def __init__(
        self,
        persist_dir: str,
        dry_run: bool = False,
        force: bool = False,
        target_service: Optional[str] = None
    ):
        self.persist_dir = persist_dir
        self.dry_run = dry_run
        self.force = force
        self.target_service = target_service

        self.stats = {
            "integration_pages_found": 0,
            "pages_with_used_by": 0,
            "service_links_found": 0,
            "copies_created": 0,
            "copies_skipped_exists": 0,
            "errors": 0,
        }

        logger.info(
            "[IntegrationLinker] persist_dir='%s', dry_run=%s, force=%s, target_service=%s",
            persist_dir, dry_run, force, target_service
        )

    def run(self):
        """Запускает полный цикл связывания."""
        embeddings_model = get_embeddings_model()
        self.vs = Chroma(
            collection_name=UNIFIED_STORAGE_NAME,
            embedding_function=embeddings_model,
            persist_directory=self.persist_dir
        )

        logger.info("=" * 70)
        logger.info("LINKING INTEGRATION METHODS TO BUSINESS SERVICES")
        logger.info("  store : %s", self.persist_dir)
        logger.info("  dry   : %s", self.dry_run)
        logger.info("  force : %s", self.force)
        logger.info("=" * 70)

        # Шаг 1. Получаем все интеграционные страницы (по title-векторам)
        integration_pages = self._get_all_integration_pages()
        self.stats["integration_pages_found"] = len(integration_pages)
        logger.info("[Step 1] Found %d integration pages", len(integration_pages))

        if not integration_pages:
            logger.warning("[Step 1] No integration pages found. Aborting.")
            return self.stats

        # Шаг 2. Обрабатываем каждую страницу
        for idx, (page_id, title, service_code, content) in enumerate(integration_pages, 1):
            logger.info(
                "[Step 2] [%d/%d] Processing page_id=%s title='%s' (service_code=%s)",
                idx, len(integration_pages), page_id, title[:60], service_code
            )
            try:
                self._process_integration_page(page_id, title, service_code, content)
            except Exception as e:
                logger.error(
                    "[Step 2] Error processing page_id=%s: %s", page_id, e, exc_info=True
                )
                self.stats["errors"] += 1

        self._log_summary()
        return self.stats

    def _get_all_integration_pages(self) -> List[Tuple[str, str, str, str]]:
        """
        Возвращает все уникальные интеграционные страницы из ChromaDB.

        Читает только title-векторы (один на страницу) чтобы избежать дублей.
        Также подтягивает content-вектор для парсинга "Где используется".

        Returns:
            Список (page_id, title, service_code, approved_content)
        """
        results = self.vs.get(
            where={
                "$and": [
                    {"requirement_type": {"$eq": "integration"}},
                    {"doc_type": {"$eq": "requirement"}},
                    {"vector_type": {"$eq": "title"}}
                ]
            },
            include=["documents", "metadatas"]
        )

        if not results or not results.get("ids"):
            return []

        pages = []
        for meta in results["metadatas"]:
            page_id = meta.get("page_id")
            title = meta.get("title", "")
            service_code = meta.get("service_code", "")

            if not page_id:
                continue

            # Получаем content-вектор для парсинга "Где используется"
            content = self._get_page_content(page_id)
            pages.append((page_id, title, service_code, content))

        return pages

    def _get_page_content(self, page_id: str) -> str:
        """Возвращает текст content-вектора страницы из ChromaDB."""
        results = self.vs.get(
            where={
                "$and": [
                    {"page_id": {"$eq": page_id}},
                    {"doc_type": {"$eq": "requirement"}},
                    {"vector_type": {"$in": ["content", "summary"]}}
                ]
            },
            include=["documents"],
            limit=1
        )

        if results and results.get("documents"):
            return results["documents"][0]
        return ""

    def _process_integration_page(
        self,
        page_id: str,
        title: str,
        source_service_code: str,
        content: str
    ):
        """Обрабатывает одну интеграционную страницу."""

        # Парсим "Где используется"
        used_by_titles = extract_used_by_titles(content)

        if not used_by_titles:
            logger.debug(
                "[_process] page_id=%s: no 'Где используется' found", page_id
            )
            return

        self.stats["pages_with_used_by"] += 1
        logger.info(
            "[_process] page_id=%s: found %d used_by_titles: %s",
            page_id, len(used_by_titles), used_by_titles
        )

        # Резолвим service_code по title
        title_to_service = resolve_service_codes_by_titles(self.vs, used_by_titles)

        if not title_to_service:
            logger.warning(
                "[_process] page_id=%s: could not resolve any service_code "
                "from %d titles",
                page_id, len(used_by_titles)
            )
            return

        # Уникальные сервисы-потребители (исключаем сам source_service_code)
        consumer_services: Set[str] = set(title_to_service.values())
        consumer_services.discard(source_service_code)

        # Если задан target_service — обрабатываем только его
        if self.target_service:
            if self.target_service not in consumer_services:
                logger.debug(
                    "[_process] page_id=%s: target_service=%s not in consumers %s",
                    page_id, self.target_service, consumer_services
                )
                return
            consumer_services = {self.target_service}

        logger.info(
            "[_process] page_id=%s: consumer services=%s",
            page_id, sorted(consumer_services)
        )

        self.stats["service_links_found"] += len(consumer_services)

        if self.dry_run:
            logger.info("[DRY RUN] Would create copies for services: %s", consumer_services)
            self.stats["copies_created"] += len(consumer_services)
            return

        # Получаем все векторы исходной страницы
        source_vectors = get_integration_page_vectors(self.vs, page_id)
        if not source_vectors:
            logger.warning("[_process] page_id=%s: no vectors found", page_id)
            return

        # Создаём копии для каждого сервиса-потребителя
        for svc in sorted(consumer_services):
            self._create_service_copy(
                page_id=page_id,
                service_code=svc,
                source_vectors=source_vectors
            )

    def _create_service_copy(
        self,
        page_id: str,
        service_code: str,
        source_vectors: List[Tuple[str, str, Dict]]
    ):
        """
        Создаёт копии всех векторов страницы с новым service_code.

        Каждая копия получает суффикс _svc_{service_code} к page_id в метаданных
        чтобы отличаться от оригинала при поиске, но при этом при переходе
        к оригинальной странице используется исходный page_id.
        """
        # Проверяем существование копии (если не force)
        if not self.force:
            existing = self.vs.get(
                where={
                    "$and": [
                        {"page_id": {"$eq": page_id}},
                        {"service_code": {"$eq": service_code}},
                        {"doc_type": {"$eq": "requirement"}}
                    ]
                },
                include=["metadatas"],
                limit=1
            )
            if existing and existing.get("ids"):
                logger.debug(
                    "[_create_copy] page_id=%s service_code=%s: already exists, skipping",
                    page_id, service_code
                )
                self.stats["copies_skipped_exists"] += 1
                return

        # Если force — удаляем существующие копии
        if self.force:
            try:
                self.vs.delete(where={
                    "$and": [
                        {"page_id": {"$eq": page_id}},
                        {"service_code": {"$eq": service_code}},
                        {"doc_type": {"$eq": "requirement"}}
                    ]
                })
                logger.debug(
                    "[_create_copy] Deleted existing copies for page_id=%s service_code=%s",
                    page_id, service_code
                )
            except Exception as e:
                logger.warning("[_create_copy] Could not delete existing: %s", e)

        # Создаём новые документы с обновлённым service_code
        new_docs = []
        for _doc_id, page_content, metadata in source_vectors:
            new_metadata = {**metadata, "service_code": service_code}
            new_docs.append(Document(
                page_content=page_content,
                metadata=new_metadata
            ))

        self.vs.add_documents(new_docs)

        logger.info(
            "[_create_copy] Created %d vectors for page_id=%s service_code=%s",
            len(new_docs), page_id, service_code
        )
        self.stats["copies_created"] += 1

    def _log_summary(self):
        """Логирует итоговую статистику."""
        logger.info("=" * 70)
        logger.info("LINKING COMPLETED")
        logger.info("  integration pages found : %d", self.stats["integration_pages_found"])
        logger.info("  pages with 'used_by'    : %d", self.stats["pages_with_used_by"])
        logger.info("  service links found     : %d", self.stats["service_links_found"])
        logger.info("  copies created          : %d", self.stats["copies_created"])
        logger.info("  copies skipped (exists) : %d", self.stats["copies_skipped_exists"])
        logger.info("  errors                  : %d", self.stats["errors"])
        logger.info("=" * 70)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Link integration methods to business services in ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Link all integrations:
  python scripts/link_integrations.py

  # Dry run (analysis only):
  python scripts/link_integrations.py --dry-run

  # Only for service CC:
  python scripts/link_integrations.py --service CC

  # Force recreate existing links:
  python scripts/link_integrations.py --force

  # Custom ChromaDB path:
  python scripts/link_integrations.py --chroma-dir ./store/chroma_db2
        """
    )
    parser.add_argument(
        '--chroma-dir', type=str, default=None,
        help='ChromaDB directory (default: CHROMA_PERSIST_DIR from config)'
    )
    parser.add_argument(
        '--service', type=str, default=None,
        help='Only create links for this service code (e.g., CC)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Analyze without making any changes'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Recreate existing links (delete and re-create)'
    )

    args = parser.parse_args()

    persist_dir = os.path.abspath(args.chroma_dir) if args.chroma_dir \
        else os.path.abspath(CHROMA_PERSIST_DIR)

    if not os.path.exists(persist_dir):
        logger.error("ChromaDB directory does not exist: %s", persist_dir)
        sys.exit(1)

    logger.info("Starting integration linking...")
    logger.info("  chroma-dir : %s", persist_dir)
    logger.info("  service    : %s", args.service or "all")
    logger.info("  dry-run    : %s", args.dry_run)
    logger.info("  force      : %s", args.force)

    linker = IntegrationLinker(
        persist_dir=persist_dir,
        dry_run=args.dry_run,
        force=args.force,
        target_service=args.service
    )

    stats = linker.run()
    sys.exit(1 if stats["errors"] > 0 else 0)


if __name__ == '__main__':
    main()