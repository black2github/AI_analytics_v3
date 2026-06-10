# app/scripts/index_changed_files.py

# скрипт нужен для CI-пайплайна: после мержа в main определить какие .md файлы изменились
# и проиндексировать их в ChromaDB через существующий DocumentService

# Как CI его вызывает:
# # CI делает git diff и сохраняет список в файл
# git diff --name-only HEAD~1 HEAD -- "requirements/**/*.md" > changed.txt
#
# # Запускает скрипт
# python app/scripts/index_changed_files.py changed.txt

import sys
import logging
from pathlib import Path
from typing import List, Dict

from app.services.document_service import DocumentService, load_md_page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def read_changed_files(filepath: str) -> List[str]:
    """Читает список изменённых файлов, который записал CI через git diff."""
    lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip().endswith(".md")]


def group_pages_by_service(filepaths: List[str]) -> Dict[str, List[Dict]]:
    """Загружает .md файлы и группирует их по service_code."""
    by_service: Dict[str, List[Dict]] = {}

    for filepath in filepaths:
        try:
            page = load_md_page(filepath)
        except Exception as e:
            logger.error("Failed to parse %s: %s", filepath, e)
            continue

        service_code = page.get("service_code")
        if not service_code:
            logger.warning("Skipped %s: no service_code in frontmatter", filepath)
            continue

        by_service.setdefault(service_code, []).append(page)

    return by_service


def main():
    if len(sys.argv) < 2:
        print("Usage: python index_changed_files.py <changed_files_list.txt>")
        sys.exit(1)

    changed_files_list = sys.argv[1]
    filepaths = read_changed_files(changed_files_list)

    if not filepaths:
        logger.info("No .md files changed. Nothing to index.")
        return

    logger.info("Indexing %d changed files", len(filepaths))

    by_service = group_pages_by_service(filepaths)
    service = DocumentService()

    for service_code, pages in by_service.items():
        page_ids = [p["id"] for p in pages]
        try:
            result = service.load_approved_pages(
                page_ids=page_ids,
                service_code=service_code,
            )
            logger.info(
                "  ✓ %s: %d documents indexed",
                service_code,
                result["documents_created"],
            )
        except Exception as e:
            logger.error("Failed to index %s: %s", service_code, e)


if __name__ == "__main__":
    main()