# migrate_confluence_tree.py

# Алгоритм
# Входные параметры (аналогично migrate_confluence_page.py):
# python migrate_confluence_tree.py <page_id> <service_code> <subdir> [source]
# Обход дерева (migrate_subtree):
# 1. Загружает данные страницы через get_page_data_cached (с fallback на get_page_title_only для пустых контейнеров).
# 2. Проверяет правила исключения из PAGE_EXCLUSION_RULES_FILE.
# 3. Запрашивает прямых потомков через confluence.get_child_pages(page_id) — с retry на таймаут.
# 4. Если у страницы есть дочерние → сохраняет её собственный контент как <title>.md в текущей директории
#    (если контент есть) и РЯДОМ создаёт каталог <title>/ для дочерних, затем рекурсивно обходит потомков
#    внутри этого каталога. Если у родителя нет собственного контента — создаётся только каталог.
# 5. Если страница листовая → сохраняет как <title>.md в текущей директории.
#
# Структура на диске:
# conf-requirements/
#   corp-cards/
#     лимиты/
#       Родительская-страница.md          ← контент самой родительской (если есть)
#       Родительская-страница/            ← папка с дочерними страницами
#         Дочерняя-листовая.md
#         Вложенный-раздел.md             ← контент вложенного раздела (если есть)
#         Вложенный-раздел/               ← папка для его детей
#           Ещё-одна-страница.md
#
# doc_id в frontmatter вычисляется как путь относительно OUTPUT_ROOT (без расширения).
# Для родительской страницы doc_id и путь к её каталогу детей совпадают по имени,
# что даёт естественную иерархию: parent — это файл, children — файлы в одноимённой папке.
#
# Повторное использование из migrate_confluence_page.py:
# • safe_filename — очистка заголовка для имени файла/каталога
# • page_to_frontmatter — генерация frontmatter
# • write_md_file — запись .md с frontmatter
# • OUTPUT_ROOT — корневой путь вывода

import sys
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.confluence_loader import confluence, get_page_title_only
from app.page_cache import get_page_data_cached
from app.page_exclusion_filter import load_exclusion_rules, is_page_excluded
from app.config import PAGE_EXCLUSION_RULES_FILE
from app.scripts.migrate_confluence_page import (
    safe_filename,
    page_to_frontmatter,
    write_md_file,
    OUTPUT_ROOT,
)

from requests import ReadTimeout

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def get_direct_children(page_id: str, retry_count: int = 0) -> List[Dict]:
    """Возвращает прямых потомков страницы Confluence (без рекурсии)."""
    try:
        return confluence.get_child_pages(page_id) or []
    except ReadTimeout:
        if retry_count < MAX_RETRIES:
            wait = 2 ** retry_count
            logger.warning(
                "Timeout getting children of %s, retry %d/%d in %ds",
                page_id, retry_count + 1, MAX_RETRIES, wait,
            )
            time.sleep(wait)
            return get_direct_children(page_id, retry_count + 1)
        logger.error("Failed to get children of page %s after %d retries", page_id, MAX_RETRIES)
        return []
    except Exception as e:
        logger.error("Failed to get children of page %s: %s", page_id, e)
        return []


def save_page_file(
    page_data: Dict,
    page_id: str,
    title: str,
    service_code: str,
    source: str,
    filepath: Path,
    stats: Dict,
) -> bool:
    """Сохраняет страницу Confluence как .md файл с frontmatter.

    Возвращает True при успешном сохранении.
    """
    content_md = page_data.get("approved_content", "")
    if not content_md or not content_md.strip():
        logger.warning("  Страница '%s' (id=%s) не содержит approved_content, пропущена", title, page_id)
        stats["skipped"] += 1
        return False

    if filepath.exists():
        logger.warning("  Файл уже существует, пропущен: %s", filepath)
        stats["skipped"] += 1
        return False

    # doc_id = путь относительно OUTPUT_ROOT без расширения, с прямыми слешами
    try:
        rel = filepath.relative_to(OUTPUT_ROOT)
        doc_id = str(rel.with_suffix("")).replace("\\", "/")
    except ValueError:
        doc_id = str(filepath.with_suffix("")).replace("\\", "/")

    page = {
        "id": page_id,
        "title": title,
        "approved_content": content_md,
        "requirement_type": page_data.get("requirement_type", "function"),
    }

    frontmatter = page_to_frontmatter(page, service_code, source, doc_id)
    write_md_file(filepath, frontmatter, content_md)
    stats["migrated"] += 1
    return True


def migrate_subtree(
    page_id: str,
    service_code: str,
    source: str,
    output_dir: Path,
    exclusion_rules,
    stats: Dict,
    visited: set,
    depth: int = 0,
) -> None:
    """Рекурсивно мигрирует страницу Confluence и всё её поддерево.

    Принцип "файл рядом с папкой":
    • Страница с детьми → файл <title>.md в текущей директории (если есть контент)
      + папка <title>/ рядом для дочерних страниц.
    • Страница без детей → файл <title>.md в текущей директории.
    • Страница без контента, но с детьми → только папка <title>/ без файла рядом
      (виртуальный контейнер).
    """
    if page_id in visited:
        logger.warning("Обнаружена циклическая ссылка для page_id=%s, пропускаем", page_id)
        return
    visited.add(page_id)

    indent = "  " * depth

    # Загружаем данные страницы (контент + метаданные)
    page_data = get_page_data_cached(page_id)

    # Определяем заголовок
    if page_data:
        title = page_data.get("title", "")
    else:
        title = get_page_title_only(page_id) or ""

    if not title:
        logger.warning("%sНе удалось определить заголовок для page_id=%s, пропускаем", indent, page_id)
        stats["skipped"] += 1
        return

    # Проверяем правила исключения
    if is_page_excluded(title, exclusion_rules):
        logger.info("%s[исключена] '%s' (id=%s)", indent, title, page_id)
        return

    # Получаем прямых потомков и фильтруем исключённые
    children = [
        c for c in get_direct_children(page_id)
        if not is_page_excluded(c.get("title", ""), exclusion_rules)
    ]

    dir_name = safe_filename(title)

    if children:
        # Родительская страница с дочерними:
        # 1) Сохраняем собственный контент как <dir_name>.md в текущей output_dir
        # 2) Создаём папку <dir_name>/ рядом для детей
        # 3) Рекурсивно обходим детей внутри этой папки

        has_own_content = bool(
            page_data and page_data.get("approved_content", "").strip()
        )

        if has_own_content:
            filepath = output_dir / f"{dir_name}.md"
            if save_page_file(page_data, page_id, title, service_code, source, filepath, stats):
                logger.info(
                    "%s[file+dir] %s.md + %s/  (id=%s, дочерних=%d)",
                    indent, dir_name, dir_name, page_id, len(children),
                )
        else:
            logger.info(
                "%s[virtual-dir] %s/  (id=%s, дочерних=%d, без собственного контента)",
                indent, dir_name, page_id, len(children),
            )

        page_dir = output_dir / dir_name
        page_dir.mkdir(parents=True, exist_ok=True)

        for child in children:
            migrate_subtree(
                child["id"],
                service_code,
                source,
                page_dir,
                exclusion_rules,
                stats,
                visited,
                depth + 1,
            )

    else:
        # Листовая страница → сохраняем как <dir_name>.md
        if not page_data:
            logger.warning("%sНет данных для '%s' (id=%s), пропущена", indent, title, page_id)
            stats["skipped"] += 1
            return

        filepath = output_dir / f"{dir_name}.md"
        if save_page_file(page_data, page_id, title, service_code, source, filepath, stats):
            logger.info("%s[ok] %s.md  (id=%s)", indent, dir_name, page_id)


def main():
    if len(sys.argv) < 4:
        print("Usage: python migrate_confluence_tree.py "
              "<page_id> <service_code> <subdir> [source]")
        print("Example: python migrate_confluence_tree.py "
              "12345 CORP_CARDS лимиты DBOCORPESPLN")
        sys.exit(1)

    root_page_id = sys.argv[1].strip()
    service_code = sys.argv[2]
    subdir = sys.argv[3]
    source = sys.argv[4] if len(sys.argv) > 4 else "DBOCORPESPLN"

    exclusion_rules = load_exclusion_rules(PAGE_EXCLUSION_RULES_FILE)

    service_part = service_code.lower().replace("_", "-")
    base_output_dir = OUTPUT_ROOT / service_part / subdir

    logger.info("Migrating Confluence tree from page_id=%s ...", root_page_id)
    logger.info("Output: %s", base_output_dir)
    logger.info("")

    stats: Dict = {"migrated": 0, "skipped": 0}
    visited: set = set()

    migrate_subtree(
        root_page_id,
        service_code,
        source,
        base_output_dir,
        exclusion_rules,
        stats,
        visited,
    )

    logger.info("")
    logger.info("Migration complete:")
    logger.info("  Migrated: %d", stats["migrated"])
    logger.info("  Skipped:  %d", stats["skipped"])
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Заполните пустые поля frontmatter вручную (owner, jira_id)")
    logger.info("  2. Запустите: python scripts/lint_frontmatter.py")
    logger.info("  3. git add, commit, push, open PR")


if __name__ == "__main__":
    main()