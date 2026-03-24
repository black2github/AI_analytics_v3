# Путь: app/services/integration_parser.py

"""
Парсер интеграционных страниц.

Отвечает за извлечение и нормализацию названия смежной системы (target_system)
из страниц с описанием интеграционных методов.

Порядок приоритетов при извлечении target_system:
1. Из контента страницы — раздел "Система" / "Система-поставщик" в таблице
   краткого описания метода. Точность ~95%.
2. Из заголовка страницы — поиск известных синонимов систем из master_systems.json.
   Fallback при отсутствии или недоступности контента.
3. None — если ни один способ не дал результата.
"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

MASTER_SYSTEMS_FILE = "master_systems.json"

# ============================================================================
# ЗАГРУЗКА СПРАВОЧНИКА СИСТЕМ
# ============================================================================

def _load_synonyms_map() -> dict:
    """
    Строит словарь синоним -> system_id из master_systems.json.

    Returns:
        Словарь вида {"рко ф1": "ABS_F1", "abs f1": "ABS_F1", ...}
        Ключи приведены к нижнему регистру для поиска без учёта регистра.
    """
    synonyms: dict = {}
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "data", MASTER_SYSTEMS_FILE)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for domain in data.get("data_domains", []):
            system_id = domain.get("system_id")
            if not system_id:
                continue
            for syn in domain.get("synonyms", []):
                synonyms[syn.lower()] = system_id

        logger.debug(
            "[_load_synonyms_map] Loaded %d synonyms from master_systems.json",
            len(synonyms)
        )
    except Exception as e:
        logger.error("[_load_synonyms_map] Failed to load master_systems.json: %s", e)

    return synonyms


# Загружаем один раз при импорте модуля
_SYNONYMS_MAP: dict = _load_synonyms_map()

# ============================================================================
# НОРМАЛИЗАЦИЯ
# ============================================================================

# Жёстко заданные маппинги — дополняют master_systems.json.
# Используются как первый приоритет в normalize_system_name,
# поскольку содержат выверенные написания из реальных страниц.
_HARDCODED_MAPPINGS = {
    # АБС Ф1 / РКО Ф1
    "АБС Ф1":              "ABS_F1",
    "АБС_Ф1":              "ABS_F1",
    "РКО Ф1":              "ABS_F1",
    "РКО_Ф1":              "ABS_F1",
    "ABS F1":              "ABS_F1",
    # ТЕССА
    "ТЕССА":               "TESSA",
    "АС ТЕССА":            "TESSA",
    # КНОСИС
    "КНОСИС":              "KNOSIS",
    "АС КНОСИС":           "KNOSIS",
    # ЕСК
    "ЕСК":                 "ESK",
    "ЕСК (ЦФТ ГО)":        "ESK",
    "Единый Справочник Клиентов": "ESK",
    # ПЦ / SVFE
    "ПЦ":                  "PC",
    "SVFE":                "PC",
    "ПЦ SVFE":             "PC",
    "Процессинговый Центр": "PC",
    # МДМ
    "МДМ":                 "MDM",
    # СБП
    "АС СБП":              "SBPG",
    "СБП":                 "SBPG",
    # KMS
    "KMS":                 "KMS",
    "KMS API":             "KMS",
    "KMS_API":             "KMS",
    "АС KMS":              "KMS",
    "АС_KMS":              "KMS",
    # АС ЕПР
    "АС ЕПР":              "EPR",
    "ЕПР":                 "EPR",
}


def normalize_system_name(raw: str) -> Optional[str]:
    """
    Нормализует произвольное название системы к каноническому system_id.

    Порядок поиска:
    1. Жёстко заданный маппинг (_HARDCODED_MAPPINGS) — точное совпадение
    2. Динамический словарь синонимов из master_systems.json (_SYNONYMS_MAP)
       — поиск без учёта регистра
    3. Возвращает исходное значение с заменой пробелов на '_' (последний резерв)

    Args:
        raw: Сырое название системы из заголовка или контента страницы

    Returns:
        Канонический system_id или исходная строка с '_' вместо пробелов
    """
    if not raw:
        return None

    raw_stripped = raw.strip()

    # 1. Жёсткий маппинг (точное совпадение)
    if raw_stripped in _HARDCODED_MAPPINGS:
        result = _HARDCODED_MAPPINGS[raw_stripped]
        logger.debug("[normalize_system_name] Hardcoded match: '%s' -> '%s'", raw_stripped, result)
        return result

    # 2. Синонимы из master_systems.json (регистронезависимо)
    raw_lower = raw_stripped.lower()
    if raw_lower in _SYNONYMS_MAP:
        result = _SYNONYMS_MAP[raw_lower]
        logger.debug("[normalize_system_name] Synonym match: '%s' -> '%s'", raw_stripped, result)
        return result

    # 3. Последний резерв
    fallback = raw_stripped.replace(" ", "_")
    logger.debug(
        "[normalize_system_name] No match for '%s', using fallback: '%s'",
        raw_stripped, fallback
    )
    return fallback


# ============================================================================
# ИЗВЛЕЧЕНИЕ ИЗ КОНТЕНТА (ПЕРВИЧНЫЙ ИСТОЧНИК)
# ============================================================================

# Паттерн ищет строку таблицы вида:
#   | Система | РКО Ф1 |
#   | Система: | ЕСК (ЦФТ ГО) |
#   | Система-поставщик сервиса | ПЦ SVFE |
#   | Система-поставщик | ТЕССА |
_SYSTEM_ROW_PATTERN = re.compile(
    r'^\|\s*Система(?:-поставщик(?:\s+сервиса)?)?\s*:?\s*\|'  # заголовок ячейки
    r'\s*(.+?)\s*\|',                                           # значение
    re.IGNORECASE | re.MULTILINE
)


def extract_target_system_from_content(content: str) -> Optional[str]:
    """
    Извлекает название смежной системы из markdown-контента страницы.

    Ищет строку таблицы с ключом "Система", "Система:", "Система-поставщик"
    или "Система-поставщик сервиса" в разделе краткого описания метода.

    Args:
        content: Markdown-текст страницы (approved_content)

    Returns:
        Нормализованный system_id или None
    """
    if not content:
        return None

    match = _SYSTEM_ROW_PATTERN.search(content)
    if not match:
        logger.debug("[extract_target_system_from_content] No 'Система' row found in content")
        return None

    raw_value = match.group(1).strip()

    # Убираем уточнения в скобках: "ЕСК (ЦФТ ГО)" -> "ЕСК"
    raw_value = re.sub(r'\s*\(.*?\)', '', raw_value).strip()

    if not raw_value:
        logger.debug("[extract_target_system_from_content] Empty value after cleanup")
        return None

    result = normalize_system_name(raw_value)
    logger.debug(
        "[extract_target_system_from_content] Found '%s' -> normalized to '%s'",
        raw_value, result
    )
    return result


# ============================================================================
# ИЗВЛЕЧЕНИЕ ИЗ ЗАГОЛОВКА (FALLBACK)
# ============================================================================

# Упорядоченный список известных синонимов для поиска в заголовке.
# Более длинные варианты стоят раньше, чтобы "АС ТЕССА" нашлось раньше "ТЕССА".
_TITLE_SYNONYMS = sorted(
    list(_HARDCODED_MAPPINGS.keys()),
    key=len,
    reverse=True
)


def extract_target_system_from_title(title: str) -> Optional[str]:
    """
    Извлекает название смежной системы из заголовка страницы (fallback).

    Используется когда контент страницы недоступен.

    Порядок поиска:
    1. Известные синонимы из _HARDCODED_MAPPINGS в начале заголовка
    2. Известные синонимы из _HARDCODED_MAPPINGS в любом месте заголовка —
       для страниц вида "[КК_ВК] Параметры вызова ... в ТЕССА"
    3. Первый сегмент заголовка до '_' с нормализацией (только если не мусорный)

    Args:
        title: Заголовок страницы интеграции

    Returns:
        Нормализованный system_id или None
    """
    if not title:
        return None

    # 1. Ищем известные синонимы в начале заголовка
    for synonym in _TITLE_SYNONYMS:
        if title.startswith(synonym):
            result = normalize_system_name(synonym)
            logger.debug(
                "[extract_target_system_from_title] Known synonym match at start: '%s' -> '%s'",
                synonym, result
            )
            return result

    # 2. Ищем известные синонимы в любом месте заголовка.
    # Покрывает страницы вида "[КК_ВК] Параметры вызова процесса загрузки в ТЕССА",
    # где система указана не в начале, а в конце или середине заголовка.
    for synonym in _TITLE_SYNONYMS:
        if synonym in title:
            result = normalize_system_name(synonym)
            logger.debug(
                "[extract_target_system_from_title] Known synonym match in body: '%s' -> '%s'",
                synonym, result
            )
            return result

    # 3. Парсим первый сегмент до '_' — только если не мусорный префикс
    parts = title.split('_')
    if len(parts) >= 2:
        candidate = parts[0].strip()
        # Отсекаем мусорные префиксы: wiki-ссылки, черновики, копии, URL-пути
        is_junk = (
            candidate.startswith('[')
            or candidate.startswith('/')
            or candidate.upper().startswith('DRAFT')
            or candidate.upper().startswith('КОПИЯ')
            or candidate.upper().startswith('COPY')
        )
        if is_junk:
            logger.debug(
                "[extract_target_system_from_title] Skipping non-system prefix: '%s'",
                candidate
            )
            return None
        result = normalize_system_name(candidate)
        logger.debug(
            "[extract_target_system_from_title] Segment match: '%s' -> '%s'",
            candidate, result
        )
        return result

    logger.debug(
        "[extract_target_system_from_title] Could not extract system from title: '%s'",
        title
    )
    return None


# ============================================================================
# ЕДИНАЯ ТОЧКА ВХОДА ДЛЯ ИНДЕКСАТОРА
# ============================================================================

def extract_target_system(title: str, content: Optional[str] = None) -> Optional[str]:
    """
    Извлекает target_system с приоритетом контента над заголовком.

    Основная функция для вызова из MultiVectorIndexer.

    Порядок:
    1. Из контента страницы (раздел "Система" / "Система-поставщик")
    2. Из заголовка страницы (поиск известных синонимов)
    3. None

    Args:
        title: Заголовок страницы
        content: Markdown-контент страницы (approved_content), опционально

    Returns:
        Нормализованный system_id или None
    """
    # 1. Контент — первичный источник
    if content:
        result = extract_target_system_from_content(content)
        if result:
            logger.info(
                "[extract_target_system] From content: '%s' (page title: '%s')",
                result, title
            )
            return result
        logger.debug(
            "[extract_target_system] Content parse failed, falling back to title"
        )

    # 2. Заголовок — fallback
    result = extract_target_system_from_title(title)
    if result:
        logger.info(
            "[extract_target_system] From title: '%s' (title: '%s')",
            result, title
        )
    else:
        logger.warning(
            "[extract_target_system] Could not determine target_system for: '%s'",
            title
        )

    return result


# ============================================================================
# ИЗВЛЕЧЕНИЕ ПОТРЕБИТЕЛЕЙ ИНТЕГРАЦИИ ("ГДЕ ИСПОЛЬЗУЕТСЯ")
# ============================================================================

_USED_BY_ROW_PATTERN = re.compile(
    r'^\|\s*(?:Где используется|Как вызывается)\s*:?\s*\|',
    re.IGNORECASE | re.MULTILINE
)

# Паттерн wiki-ссылок Confluence в markdown:
# [[anchor] display_title] -> захватывает '[anchor] display_title' как title
# [Title] -> захватывает 'Title'
_WIKI_LINK_PATTERN = re.compile(
    r'\[(\[[^\]]+\][^\]]*)\]'  # [[anchor] display_title]
    r'|'
    r'\[([^\[\]]+)\]'            # [простой Title]
)


def extract_used_by_titles(content: str) -> list:
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

    # Ищем строку таблицы с разделом "где используется"
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if _USED_BY_ROW_PATTERN.match(line.strip()):
            # Значение может быть в той же строке после второго |
            # или в следующей строке (многострочная ячейка таблицы)
            parts = line.split('|')
            if len(parts) >= 3:
                cell_value = parts[2].strip()
            else:
                cell_value = ''

            # Собираем продолжение многострочной ячейки
            for j in range(i + 1, min(i + 20, len(lines))):
                next_line = lines[j]
                # Конец ячейки — новая строка таблицы с | в начале, содержащая новый ключ
                if next_line.strip().startswith('|') and '|' in next_line[1:]:
                    # Проверяем что это не продолжение значения, а новая строка
                    stripped = next_line.strip('| \t')
                    # Если строка начинается с нового ключа — останавливаемся
                    if not stripped.startswith('[') and ':' in stripped[:30]:
                        break
                cell_value += '\n' + next_line

            titles = []
            for link_match in _WIKI_LINK_PATTERN.finditer(cell_value):
                title = (link_match.group(1) or link_match.group(2) or '').strip()
                if title:
                    titles.append(title)

            logger.debug(
                "[extract_used_by_titles] Found %d titles: %s", len(titles), titles
            )
            return titles

    logger.debug("[extract_used_by_titles] No 'Где используется' row found")
    return []