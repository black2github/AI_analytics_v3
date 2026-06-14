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
# Структура на диске: conf-requirements/ corp-cards/ лимиты/ Родительская-страница.md          ← контент самой
# родительской (если есть) Родительская-страница/            ← папка с дочерними страницами Дочерняя-листовая.md
# Вложенный-раздел.md             ← контент вложенного раздела (если есть) Вложенный-раздел/               ← папка
# для его детей Ещё-одна-страница.md
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

import os
import re
import sys
import html
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from app.confluence_loader import confluence, get_page_title_only
from app.page_cache import (
    get_page_data,
    fetch_page_title_via_http,
    fetch_child_pages_via_http,
)
from app.page_exclusion_filter import load_exclusion_rules, is_page_excluded
from app.config import (
    PAGE_EXCLUSION_RULES_FILE,
    CONFLUENCE_BASE_URL,
    CONFLUENCE_USE_HTTP,
    MIGRATE_INCLUDE_UNAPPROVED,
)
from app.scripts.migrate_confluence_page import (
    safe_filename,
    page_to_frontmatter,
    write_md_file,
    OUTPUT_ROOT,
)

from requests import ReadTimeout

# Текст ссылки может содержать экранированные скобки (\[ \]), которые добавляет
# _escape_link_text в content_extractor. Поэтому в качестве текста ссылки матчим
# либо экранированный символ (\\.), либо любой символ кроме '\' и неэкранированного ']'.
# Простой [^\]]* остановился бы на первом же ']' внутри экранированного '\]'.
_LINK_TEXT = r'((?:\\.|[^\]\\])*)'
_LINK_BY_ID_RE = re.compile(r'\[' + _LINK_TEXT + r'\]\(confluence://(\d+)\)')
_LINK_BY_TITLE_RE = re.compile(r'\[' + _LINK_TEXT + r'\]\(confluence://title/([^)]*)\)')

# Внутри HTML-таблиц ссылки генерируются как HTML-тег <a href="confluence://...">.
# Здесь резолвим только атрибут href, не трогая текст и закрывающий </a>.
_HTML_LINK_BY_ID_RE = re.compile(r'<a href="confluence://(\d+)">')
_HTML_LINK_BY_TITLE_RE = re.compile(r'<a href="confluence://title/([^"]*)">')


def _title_key(title: str) -> str:
    """Нормализует заголовок страницы в ключ реестра title_registry.

    Заголовок может прийти двумя путями, и оба нужно привести к одному виду:
    • напрямую из метаданных Confluence (save_page_file, seed_registries_from_disk);
    • восстановленным из плейсхолдера confluence://title/... на этапе Pass 2.

    Плейсхолдер для ссылок внутри HTML-таблиц проходит через _escape_html_attr,
    который кодирует кавычки как &quot; (а & как &amp;). Без html.unescape такой
    заголовок ('… "Список карт"') никогда не совпал бы с реестром, где лежит
    настоящая строка с кавычками. Дополнительно схлопываем пробелы и приводим
    к нижнему регистру, чтобы мелкие расхождения в вёрстке не ломали матчинг.
    """
    title = html.unescape(title)
    title = re.sub(r"\s+", " ", title).strip()
    return title.lower()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def get_direct_children(page_id: str, use_http: bool = False, retry_count: int = 0) -> List[Dict]:
    """Возвращает прямых потомков страницы Confluence (без рекурсии).

    use_http=True — потомки запрашиваются через прямой HTTP-доступ
    (page-tree endpoint), в обход REST API.
    """
    if use_http:
        # HTTP-ветка имеет собственную обработку ошибок и логирование
        # внутри fetch_child_pages_via_http; retry здесь не применяем.
        return fetch_child_pages_via_http(page_id)
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
            return get_direct_children(page_id, retry_count=retry_count + 1)
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
    page_registry: Dict[str, Path],
    title_registry: Dict[str, Path],
    include_unapproved: bool = False,
) -> bool:
    """Сохраняет страницу Confluence как .md файл с frontmatter.

    Регистрирует сохранённый файл в реестрах page_registry и title_registry
    для последующего разрешения ссылок на этапе post-processing.
    Возвращает True при успешном сохранении.

    include_unapproved=True — в файл пишется ПОЛНОЕ содержимое страницы
    (full_content, все фрагменты), иначе только подтверждённые (approved_content).
    """
    content_field = "full_content" if include_unapproved else "approved_content"
    content_md = page_data.get(content_field, "")
    if not content_md or not content_md.strip():
        logger.warning("  Страница '%s' (id=%s) не содержит %s, пропущена", title, page_id, content_field)
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

    # Миграция картинок: скачиваем вложения в img/ рядом с .md и заменяем плейсхолдеры
    # confluence-attachment:// на относительные ссылки (если конвертация шла с MIGRATE_IMAGES).
    import app.config as _config
    if _config.MIGRATE_IMAGES:
        from app.image_migrator import migrate_images_in_content
        content_md, downloaded, failed = migrate_images_in_content(
            content_md, str(page_id), filepath
        )
        if downloaded or failed:
            logger.info("  🖼 Картинки '%s': скачано %d, ошибок %d", title, downloaded, failed)

    page = {
        "id": page_id,
        "title": title,
        "approved_content": content_md,
        "requirement_type": page_data.get("requirement_type", "unknown"),
    }

    frontmatter = page_to_frontmatter(page, service_code, source, doc_id)
    write_md_file(filepath, frontmatter, content_md)

    page_registry[page_id] = filepath
    title_registry[_title_key(title)] = filepath

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
    page_registry: Dict[str, Path],
    title_registry: Dict[str, Path],
    depth: int = 0,
    use_http: bool = False,
    include_unapproved: bool = False,
) -> None:
    """Рекурсивно мигрирует страницу Confluence и всё её поддерево.

    Принцип "файл рядом с папкой":
    • Страница с детьми → файл <title>.md в текущей директории (если есть контент)
      + папка <title>/ рядом для дочерних страниц.
    • Страница без детей → файл <title>.md в текущей директории.
    • Страница без контента, но с детьми → только папка <title>/ без файла рядом
      (виртуальный контейнер).

    use_http=True — и контент, и потомки, и заголовки запрашиваются через
    прямой HTTP-доступ (как браузер), в обход Confluence REST API.
    include_unapproved=True — в .md пишется всё содержимое (full_content),
    иначе только подтверждённые фрагменты (approved_content).
    """
    if page_id in visited:
        logger.warning("Обнаружена циклическая ссылка для page_id=%s, пропускаем", page_id)
        return
    visited.add(page_id)

    indent = "  " * depth

    # Загружаем данные страницы (контент + метаданные)
    page_data = get_page_data(page_id, use_http=use_http)

    # Определяем заголовок
    if page_data:
        title = page_data.get("title", "")
    elif use_http:
        title = fetch_page_title_via_http(page_id) or ""
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
        c for c in get_direct_children(page_id, use_http=use_http)
        if not is_page_excluded(c.get("title", ""), exclusion_rules)
    ]

    dir_name = safe_filename(title)

    if children:
        # Родительская страница с дочерними:
        # 1) Сохраняем собственный контент как <dir_name>.md в текущей output_dir
        # 2) Создаём папку <dir_name>/ рядом для детей
        # 3) Рекурсивно обходим детей внутри этой папки

        content_field = "full_content" if include_unapproved else "approved_content"
        has_own_content = bool(
            page_data and page_data.get(content_field, "").strip()
        )

        if has_own_content:
            filepath = output_dir / f"{dir_name}.md"
            if save_page_file(page_data, page_id, title, service_code, source, filepath, stats,
                              page_registry, title_registry, include_unapproved=include_unapproved):
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
                page_registry,
                title_registry,
                depth + 1,
                use_http=use_http,
                include_unapproved=include_unapproved,
            )

    else:
        # Листовая страница → сохраняем как <dir_name>.md
        if not page_data:
            logger.warning("%sНет данных для '%s' (id=%s), пропущена", indent, title, page_id)
            stats["skipped"] += 1
            return

        filepath = output_dir / f"{dir_name}.md"
        if save_page_file(page_data, page_id, title, service_code, source, filepath, stats,
                          page_registry, title_registry, include_unapproved=include_unapproved):
            logger.info("%s[ok] %s.md  (id=%s)", indent, dir_name, page_id)


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def seed_registries_from_disk(
    page_registry: Dict[str, Path],
    title_registry: Dict[str, Path],
) -> int:
    """Подмешивает в реестры страницы, уже лежащие на диске в OUTPUT_ROOT.

    Реестры из Pass 1 содержат только страницы текущего запуска. Но ссылки
    часто ведут на страницы из других поддеревьев/сервисов, мигрированных
    ранее. У каждого .md-файла во frontmatter есть confluence_page_id и title —
    этого достаточно, чтобы разрешить и ID-ссылки (confluence://ID), и
    title-ссылки (confluence://title/...) на ранее сохранённые файлы.

    Записи текущего запуска имеют приоритет: уже существующие ключи не
    перезаписываются. Возвращает число подмешанных файлов.
    """
    if not OUTPUT_ROOT.exists():
        return 0

    known = set(page_registry.values()) | set(title_registry.values())
    added = 0
    for filepath in OUTPUT_ROOT.rglob("*.md"):
        if filepath in known:
            continue
        try:
            text = filepath.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue

        page_id = fm.get("confluence_page_id")
        if page_id:
            page_registry.setdefault(str(page_id), filepath)
        title = fm.get("title")
        if title:
            title_registry.setdefault(_title_key(str(title)), filepath)
        if page_id or title:
            added += 1
    return added


def resolve_confluence_links(
    page_registry: Dict[str, Path],
    title_registry: Dict[str, Path],
    files: Optional[set] = None,
) -> Tuple[int, int]:
    """Pass 2: заменяет плейсхолдеры confluence:// на относительные пути в сохранённых .md файлах.

    files — множество файлов, которые нужно обработать (переписать). Если не
    задано, берутся все файлы из реестров. При подмешивании ранее сохранённых
    страниц (seed_registries_from_disk) сюда передаётся только набор текущего
    запуска, чтобы не трогать чужие файлы — подмешанные служат лишь целями ссылок.

    Возвращает (resolved, unresolved) — количество разрешённых и неразрешённых ссылок.
    Неразрешённые ID-ссылки заменяются абсолютным URL Confluence.
    Неразрешённые title-ссылки оставляются как текст в скобках без URL.
    """
    counts = {"resolved": 0, "unresolved": 0}

    if files is None:
        files = set(page_registry.values()) | set(title_registry.values())

    for filepath in files:
        if not filepath.exists():
            continue

        text = filepath.read_text(encoding="utf-8")

        def replace_id(m: re.Match) -> str:
            link_text, page_id = m.group(1), m.group(2)
            target = page_registry.get(page_id)
            if target:
                rel = Path(os.path.relpath(target, filepath.parent))
                counts["resolved"] += 1
                return f"[{link_text}]({str(rel).replace(chr(92), '/')})"
            counts["unresolved"] += 1
            return f"[{link_text}]({CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId={page_id})"

        def replace_title(m: re.Match) -> str:
            link_text, title_encoded = m.group(1), m.group(2)
            # title_encoded может быть "SPACE/Title+Words" или просто "Title+Words"
            raw_title = title_encoded.split("/")[-1].replace("+", " ")
            target = title_registry.get(_title_key(raw_title))
            if target:
                rel = Path(os.path.relpath(target, filepath.parent))
                counts["resolved"] += 1
                return f"[{link_text}]({str(rel).replace(chr(92), '/')})"
            counts["unresolved"] += 1
            return f"[{link_text}]"

        def replace_html_id(m: re.Match) -> str:
            # HTML-форма внутри таблиц: заменяем только href, текст и </a> остаются.
            page_id = m.group(1)
            target = page_registry.get(page_id)
            if target:
                rel = Path(os.path.relpath(target, filepath.parent))
                counts["resolved"] += 1
                return f'<a href="{str(rel).replace(chr(92), "/")}">'
            counts["unresolved"] += 1
            return f'<a href="{CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId={page_id}">'

        def replace_html_title(m: re.Match) -> str:
            title_encoded = m.group(1)
            raw_title = title_encoded.split("/")[-1].replace("+", " ")
            target = title_registry.get(_title_key(raw_title))
            if target:
                rel = Path(os.path.relpath(target, filepath.parent))
                counts["resolved"] += 1
                return f'<a href="{str(rel).replace(chr(92), "/")}">'
            counts["unresolved"] += 1
            # Неразрешённый title в HTML-теге: <a> нельзя «снять» одной заменой href,
            # поэтому ведём на канонический Confluence-URL вида /display/SPACE/Title.
            parts = title_encoded.split("/")
            if len(parts) > 1 and parts[0]:
                return f'<a href="{CONFLUENCE_BASE_URL}/display/{parts[0]}/{parts[-1]}">'
            return f'<a href="{CONFLUENCE_BASE_URL}/dosearchsite.action?queryString={parts[-1]}">'

        new_text = _LINK_BY_ID_RE.sub(replace_id, text)
        new_text = _LINK_BY_TITLE_RE.sub(replace_title, new_text)
        new_text = _HTML_LINK_BY_ID_RE.sub(replace_html_id, new_text)
        new_text = _HTML_LINK_BY_TITLE_RE.sub(replace_html_title, new_text)

        if new_text != text:
            filepath.write_text(new_text, encoding="utf-8")

    return counts["resolved"], counts["unresolved"]


def main():
    # Флаги --http, --all, --keep-history и --with-images можно указать в любом месте
    # аргументов; они переопределяют соответствующие значения из конфигурации.
    flags = {"--http", "--all", "--keep-history", "--with-images"}
    args = [a for a in sys.argv[1:] if a not in flags]
    use_http = ("--http" in sys.argv) or CONFLUENCE_USE_HTTP
    include_unapproved = ("--all" in sys.argv) or MIGRATE_INCLUDE_UNAPPROVED
    keep_history = "--keep-history" in sys.argv
    with_images = "--with-images" in sys.argv

    if len(args) < 3:
        print("Usage: python migrate_confluence_tree.py "
              "<page_id> <service_code> <subdir> [source] [--http] [--all] [--keep-history] [--with-images]")
        print("Example: python migrate_confluence_tree.py "
              "12345 CORP_CARDS лимиты DBOCORPESPLN")
        print("Example (прямой HTTP, в обход API): python migrate_confluence_tree.py "
              "12345 CORP_CARDS лимиты DBOCORPESPLN --http")
        print("Example (всё содержимое, включая неподтверждённое): "
              "python migrate_confluence_tree.py 12345 CORP_CARDS лимиты --all")
        print("Example (сохранить раздел 'История изменений'): "
              "python migrate_confluence_tree.py 12345 CORP_CARDS лимиты --keep-history")
        print("Example (мигрировать картинки в img/ рядом с .md): "
              "python migrate_confluence_tree.py 12345 CORP_CARDS лимиты --with-images")
        sys.exit(1)

    # Переопределяем политику удаления истории на время процесса (вариант A).
    # remove_history_sections() читает app.config.REMOVE_HISTORY_SECTIONS динамически.
    if keep_history:
        import app.config as _config
        _config.REMOVE_HISTORY_SECTIONS = False

    # Включаем миграцию картинок на время процесса. Фабрики экстракторов читают
    # app.config.MIGRATE_IMAGES динамически — флаг должен быть выставлен ДО конвертации.
    if with_images:
        import app.config as _config
        _config.MIGRATE_IMAGES = True

    root_page_id = args[0].strip()
    service_code = args[1]
    subdir = args[2]
    source = args[3] if len(args) > 3 else "DBOCORPESPLN"

    exclusion_rules = load_exclusion_rules(PAGE_EXCLUSION_RULES_FILE)

    service_part = service_code.lower().replace("_", "-")
    base_output_dir = OUTPUT_ROOT / service_part / subdir

    logger.info("Migrating Confluence tree from page_id=%s ...", root_page_id)
    logger.info("Output: %s", base_output_dir)
    logger.info("Access mode: %s", "direct HTTP (в обход API)" if use_http else "REST API")
    logger.info("Content mode: %s",
                "ВСЁ содержимое (включая неподтверждённое)" if include_unapproved
                else "только подтверждённые фрагменты")
    logger.info("History mode: %s",
                "СОХРАНЯТЬ раздел истории" if keep_history else "удалять раздел истории")
    logger.info("Images mode: %s",
                "СКАЧИВАТЬ картинки в img/" if with_images else "картинки игнорируются")
    logger.info("")

    stats: Dict = {"migrated": 0, "skipped": 0}
    visited: set = set()
    page_registry: Dict[str, Path] = {}
    title_registry: Dict[str, Path] = {}

    logger.info("Pass 1: traversing Confluence tree ...")
    migrate_subtree(
        root_page_id,
        service_code,
        source,
        base_output_dir,
        exclusion_rules,
        stats,
        visited,
        page_registry,
        title_registry,
        use_http=use_http,
        include_unapproved=include_unapproved,
    )

    logger.info("")
    logger.info("Pass 2: resolving internal links ...")
    # Файлы текущего запуска фиксируем ДО подмешивания — только их переписываем.
    current_files = set(page_registry.values()) | set(title_registry.values())
    seeded = seed_registries_from_disk(page_registry, title_registry)
    if seeded:
        logger.info("  Подмешано из ранее сохранённых .md (frontmatter): %d", seeded)
    resolved, unresolved = resolve_confluence_links(
        page_registry, title_registry, files=current_files
    )

    logger.info("")
    logger.info("Migration complete:")
    logger.info("  Migrated:           %d", stats["migrated"])
    logger.info("  Skipped:            %d", stats["skipped"])
    logger.info("  Links resolved:     %d", resolved)
    logger.info("  Links unresolved:   %d  (replaced with absolute Confluence URLs)", unresolved)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Заполните пустые поля frontmatter вручную (owner, jira_id)")
    logger.info("  2. Запустите: python scripts/lint_frontmatter.py")
    logger.info("  3. git add, commit, push, open PR")


if __name__ == "__main__":
    main()