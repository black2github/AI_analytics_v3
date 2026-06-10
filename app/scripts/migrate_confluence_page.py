# scripts/migrate_confluence_page.py

import sys
import re
import logging
import yaml
from pathlib import Path
from typing import Dict, Optional

from app.confluence_loader import load_pages_by_ids
from app.page_cache import fetch_page_data_via_http
from app.service_registry import get_platform_status

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


OUTPUT_ROOT = Path("conf-requirements")

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE = re.compile(r"\s+")


def safe_filename(title: str, max_length: int = 100) -> str:
    """Превращает заголовок Confluence-страницы в имя файла, сохраняя кириллицу.

    Удаляет только символы, запрещённые в именах файлов на Windows/Linux/macOS.
    Пробелы заменяет на дефисы для читаемости в URL и Git.
    """
    name = title.strip()
    name = INVALID_FILENAME_CHARS.sub("", name)
    name = WHITESPACE.sub("-", name)
    name = name.strip("-.")
    if not name:
        name = "untitled"
    return name[:max_length]


def build_doc_id(service_code: str, subdir: str, filename: str) -> str:
    """Строит doc_id из пути файла.

    Service_code приводим к нижнему регистру с дефисом, чтобы URL и пути
    были консистентны: CORP_CARDS → corp-cards.
    """
    service_part = service_code.lower().replace("_", "-")
    return f"{service_part}/{subdir}/{filename}"


def page_to_frontmatter(
    page: Dict,
    service_code: str,
    source: str,
    doc_id: str,
) -> Dict:
    """Строит frontmatter из метаданных Confluence-страницы.

    Поля, которых нет в Confluence как структурированные данные (owner,
    jira_id, related, author, tags, reviewed_by, parent), оставляются
    пустыми. Линтер при первой попытке коммита укажет на пропуски —
    аналитик заполнит их вручную при ревью миграции.
    """
    req_type = (page.get("requirement_type") or "function").strip()
    is_platform = get_platform_status(service_code)

    fm: Dict = {
        # Идентификация
        "doc_id": doc_id,
        "title": page.get("title", ""),
        "document_name": "",

        # Классификация
        "doc_type": "requirement",
        "requirement_type": req_type,
        "service_code": service_code,
        "microservice": "",
        "feature": "",
        "is_platform": is_platform,

        # Источник и трассировка
        "source": source,
        "jira_id": "",
        "jira_ids": "",
        "confluence_page_id": str(page["id"]),

        # Статус и владение
        "status": "approved",
        "owner": "",
        "author": "",
        "reviewed_by": "",
        "version": "1.0",
        "created_date": "",
        "updated_date": "",

        # Связи
        "related": "",
        "parent": "",

        # Теги
        "tags": "",
    }

    # target_system — для интеграционных требований
    # В load_pages_by_ids это поле сейчас не возвращается. Оставляем пустым;
    # при ревью миграции аналитик заполнит вручную. Если в будущем добавишь
    # извлечение target_system в page_cache — подхвати page.get("target_system")
    # здесь автоматически.
    if req_type == "integration":
        fm["target_system"] = page.get("target_system", "")

    return fm


def write_md_file(
    filepath: Path,
    frontmatter: Dict,
    content_md: str,
) -> None:
    """Сохраняет .md файл с frontmatter и Markdown-содержимым."""
    filepath.parent.mkdir(parents=True, exist_ok=True)

    frontmatter_str = yaml.dump(
        frontmatter,
        allow_unicode=True,        # критично для кириллицы в значениях
        default_flow_style=False,
        sort_keys=False,
    )

    full_text = f"---\n{frontmatter_str}---\n\n{content_md}\n"
    filepath.write_text(full_text, encoding="utf-8")


def migrate_page(
    page: Dict,
    service_code: str,
    source: str,
    subdir: str,
) -> Optional[Path]:
    """Конвертирует одну страницу Confluence в .md файл.

    Использует approved_content из load_pages_by_ids — это уже готовый
    Markdown (гибридный Markdown + HTML), сформированный твоим форматером
    через filter_approved_fragments.
    """
    content_md = page.get("approved_content", "")
    if not content_md or not content_md.strip():
        logger.warning("  ⚠ Page %s has no approved content, skipped", page["id"])
        return None

    filename = safe_filename(page["title"])
    doc_id = build_doc_id(service_code, subdir, filename)
    filepath = OUTPUT_ROOT / f"{doc_id}.md"

    if filepath.exists():
        logger.warning("  ⚠ File already exists, skipped: %s", filepath)
        return None

    frontmatter = page_to_frontmatter(page, service_code, source, doc_id)
    write_md_file(filepath, frontmatter, content_md)

    return filepath


def main():
    from app.config import CONFLUENCE_USE_HTTP

    # Флаг --http можно указать в любом месте аргументов; он переопределяет
    # значение CONFLUENCE_USE_HTTP из конфигурации.
    raw_args = [a for a in sys.argv[1:] if a != "--http"]
    use_http = ("--http" in sys.argv) or CONFLUENCE_USE_HTTP

    if len(raw_args) < 3:
        print("Usage: python migrate_confluence_page.py "
              "<page_id,...> <service_code> <subdir> [source] [--http]")
        print("Example: python migrate_confluence_page.py "
              "12345,67890 CORP_CARDS лимиты DBOCORPESPLN")
        print("Example (прямой HTTP, в обход API): python migrate_confluence_page.py "
              "12345,67890 CORP_CARDS лимиты DBOCORPESPLN --http")
        sys.exit(1)

    page_ids = raw_args[0].split(",")
    service_code = raw_args[1]
    subdir = raw_args[2]
    source = raw_args[3] if len(raw_args) > 3 else "DBOCORPESPLN"

    if use_http:
        # Прямой HTTP-доступ: предзаполняем общий page_cache через браузерный
        # запрос. Дальше load_pages_by_ids (-> get_page_data_cached) берёт данные
        # из кеша (cache HIT) и не обращается к закрытому REST API.
        logger.info("Loading %d page(s) from Confluence via direct HTTP...", len(page_ids))
        for page_id in page_ids:
            result = fetch_page_data_via_http(page_id.strip())
            if result:
                logger.info("  ✓ Fetched page_id=%s title='%s'", page_id, result["title"])
            else:
                logger.warning("  ⚠ Failed to fetch page_id=%s", page_id)
    else:
        logger.info("Loading %d page(s) from Confluence via REST API...", len(page_ids))

    pages = load_pages_by_ids(page_ids)

    if not pages:
        logger.error(
            "No pages loaded. Possible reasons: missing title, full_markdown, "
            "or approved_content in source pages (see load_pages_by_ids logs)."
        )
        sys.exit(1)

    logger.info("Migrating to %s/%s/ ...", service_code, subdir)

    migrated = []
    skipped = []

    for page in pages:
        result = migrate_page(page, service_code, source, subdir)
        if result:
            migrated.append(result)
            logger.info("  ✓ %s → %s", page["title"], result)
        else:
            skipped.append(page["id"])

    logger.info("")
    logger.info("Migration complete:")
    logger.info("  Loaded from Confluence: %d", len(pages))
    logger.info("  Migrated:               %d", len(migrated))
    logger.info("  Skipped:                %d", len(skipped))
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Fill in empty frontmatter fields (owner, jira_id) manually")
    logger.info("  2. Run: python scripts/lint_frontmatter.py")
    logger.info("  3. git add, commit, push, open PR")


if __name__ == "__main__":
    main()