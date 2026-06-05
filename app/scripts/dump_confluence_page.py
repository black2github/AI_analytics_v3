# Путь: scripts/dump_confluence_page.py
"""
Служебный скрипт для сохранения raw HTML страницы Confluence в файл.

Использование:
    python scripts/dump_confluence_page.py <page_id> [output_dir]

Примеры:
    python scripts/dump_confluence_page.py 291472147
    python scripts/dump_confluence_page.py 291472147 debug/html

Сохраняет файл:
    <output_dir>/<page_id>_<safe_title>.html

По умолчанию output_dir = "debug/html"
"""

import sys
import re
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("debug/html")

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE = re.compile(r"\s+")


def safe_filename(title: str, max_length: int = 100) -> str:
    """Превращает заголовок страницы в безопасное имя файла."""
    name = title.strip()
    name = INVALID_FILENAME_CHARS.sub("", name)
    name = WHITESPACE.sub("-", name)
    name = name.strip("-.")
    if not name:
        name = "untitled"
    return name[:max_length]


def dump_page(page_id: str, output_dir: Path) -> Path:
    """
    Загружает страницу из Confluence и сохраняет raw HTML в файл.

    Использует page_cache — тот же путь, что и основной пайплайн,
    поэтому результат гарантированно идентичен тому, что обрабатывает
    content_extractor.

    Returns:
        Путь к сохранённому файлу.
    """
    from app.page_cache import get_page_data_cached

    logger.info("Loading page %s from Confluence...", page_id)
    page_data = get_page_data_cached(page_id)

    if not page_data:
        logger.error("Failed to load page %s — check page_id and Confluence connectivity.", page_id)
        sys.exit(1)

    title = page_data.get("title", "untitled")
    raw_html = page_data.get("raw_html", "")

    if not raw_html:
        logger.error("Page %s loaded but raw_html is empty.", page_id)
        sys.exit(1)

    filename = f"{page_id}_{safe_filename(title)}.html"
    filepath = output_dir / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(raw_html, encoding="utf-8")

    logger.info("Title:  %s", title)
    logger.info("Saved:  %s", filepath)
    logger.info("Size:   %d bytes", len(raw_html.encode("utf-8")))

    return filepath


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/dump_confluence_page.py <page_id> [output_dir]")
        print("Example: python scripts/dump_confluence_page.py 291472147")
        sys.exit(1)

    page_id = sys.argv[1].strip()
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_ROOT

    dump_page(page_id, output_dir)


if __name__ == "__main__":
    main()