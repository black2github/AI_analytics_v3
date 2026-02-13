# app/services/integration_parser.py

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Известные смежные системы (из справочника мастер-систем)
KNOWN_SYSTEMS = [
    "АБС Ф1", "АБС_Ф1",
    "ЕСК", "ПЦ",
    "ТЕССА", "АС ТЕССА",
    "КНОСИС", "АС КНОСИС",
    "МДМ",
    "Процессинговый Центр",
    "Единый Справочник Клиентов"
]


def extract_target_system_from_title(title: str) -> Optional[str]:
    """
    Извлекает название смежной системы из заголовка интеграции.

    Формат заголовка: "Система_Протокол_Название метода"
    Например: "АБС Ф1_REST_Получение списка карт клиента"

    Args:
        title: Заголовок страницы интеграции

    Returns:
        Название смежной системы или None
    """
    if not title:
        return None

    # Проверяем известные системы в начале заголовка
    for system in KNOWN_SYSTEMS:
        if title.startswith(system):
            logger.debug("[extract_target_system] Found known system: %s", system)
            return normalize_system_name(system)

    # Если не нашли известную систему, пробуем парсить по шаблону
    # Формат: "Система_Протокол_..."
    parts = title.split('_')
    if len(parts) >= 2:
        potential_system = parts[0].strip()
        logger.debug("[extract_target_system] Extracted from pattern: %s", potential_system)
        return normalize_system_name(potential_system)

    logger.debug("[extract_target_system] Could not extract target system from: %s", title)
    return None


def normalize_system_name(system: str) -> str:
    """
    Нормализует название системы к единому формату.

    Например:
    - "АБС Ф1" → "АБС_Ф1"
    - "АС ТЕССА" → "ТЕССА"
    - "Процессинговый Центр" → "ПЦ"
    """
    # Маппинг вариантов написания к каноническому
    mappings = {
        "АБС Ф1": "АБС_Ф1",
        "АБС_Ф1": "АБС_Ф1",
        "АС ТЕССА": "TESSA",
        "ТЕССА": "TESSA",
        "АС КНОСИС": "KNOSIS",
        "КНОСИС": "KNOSIS",
        "Единый Справочник Клиентов": "ESK",
        "ЕСК": "ESK",
        "Процессинговый Центр": "PC",
        "ПЦ": "PC",
        "МДМ": "MDM"
    }

    return mappings.get(system, system.replace(" ", "_"))