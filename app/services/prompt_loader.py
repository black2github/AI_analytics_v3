# Путь: app/services/prompt_loader.py
"""
Загрузчик промптов для многопроходного ревью требований.

Промпты хранятся в файловой системе по структуре:
    app/prompts/review/
        system_base.txt             — общая роль и инструкции формата
        errors_criteria.txt         — критерии для сообщений об ошибках
        summarizer.txt              — промпт для сжатия большого документа (уровень 2)
        unknown.txt                 — fallback для неизвестных типов
        {req_type}/
            pass1_*.txt             — первый проход
            pass2_*.txt             — второй проход
            pass3_*.txt             — третий проход (если нужен)
            aggregator.txt          — финальная агрегация всех проходов

Файлы промптов поддерживают директиву {{include: filename.txt}} для включения
общих фрагментов (например, errors_criteria.txt).

Загруженные файлы кешируются в памяти. Для сброса кеша при горячем обновлении
промптов вызвать clear_prompt_cache().
"""

import logging
import os
import re
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Базовая директория промптов — относительно корня проекта
_PROMPTS_BASE = os.path.join(
    os.path.dirname(__file__), "..", "prompts", "review"
)

# Кеш загруженных файлов: path -> content
_prompt_cache: Dict[str, str] = {}


def _resolve_path(*parts: str) -> str:
    """Строит абсолютный путь внутри директории промптов."""
    return os.path.abspath(os.path.join(_PROMPTS_BASE, *parts))


def _read_file(path: str) -> Optional[str]:
    """
    Читает файл промпта с кешированием.

    Returns:
        Содержимое файла или None если файл не найден.
    """
    if path in _prompt_cache:
        return _prompt_cache[path]

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        _prompt_cache[path] = content
        logger.debug("[_read_file] Loaded prompt: %s (%d chars)", path, len(content))
        return content
    except FileNotFoundError:
        logger.debug("[_read_file] Prompt file not found: %s", path)
        return None
    except Exception as e:
        logger.error("[_read_file] Error reading %s: %s", path, e)
        return None


def _resolve_includes(content: str) -> str:
    """
    Обрабатывает директивы {{include: filename.txt}} в тексте промпта.

    Включаемый файл ищется в корне директории review/.
    Вложенные include не поддерживаются (один уровень).

    Args:
        content: Текст промпта с возможными директивами include

    Returns:
        Текст с раскрытыми директивами include
    """
    def replace_include(match: re.Match) -> str:
        filename = match.group(1).strip()
        included_path = _resolve_path(filename)
        included = _read_file(included_path)
        if included:
            logger.debug("[_resolve_includes] Included: %s", filename)
            return included
        logger.warning("[_resolve_includes] Include not found: %s", filename)
        return f"[INCLUDE NOT FOUND: {filename}]"

    return re.sub(r'\{\{include:\s*([^}]+)\}\}', replace_include, content)


def load_pass_prompt(req_type: str, pass_index: int) -> Optional[str]:
    """
    Загружает промпт для конкретного прохода конкретного типа требований.

    Ищет файл по маске pass{N}_*.txt в директории типа.
    Например: app/prompts/review/function/pass1_structure.txt

    Args:
        req_type: Код типа требований (function, dataModel, integration, ...)
        pass_index: Номер прохода (1, 2, 3, ...)

    Returns:
        Текст промпта с раскрытыми include или None если файл не найден
    """
    type_dir = _resolve_path(req_type)

    if not os.path.isdir(type_dir):
        logger.debug("[load_pass_prompt] No directory for type '%s'", req_type)
        return None

    prefix = f"pass{pass_index}_"
    try:
        files = [
            f for f in os.listdir(type_dir)
            if f.startswith(prefix) and f.endswith(".txt")
        ]
    except OSError as e:
        logger.error("[load_pass_prompt] Cannot list directory %s: %s", type_dir, e)
        return None

    if not files:
        logger.debug("[load_pass_prompt] No pass%d file for type '%s'", pass_index, req_type)
        return None

    # Берём первый найденный файл (имя после pass{N}_ описательное, не влияет на логику)
    path = os.path.join(type_dir, sorted(files)[0])
    content = _read_file(path)
    if content:
        return _resolve_includes(content)
    return None


def load_aggregator_prompt(req_type: str) -> Optional[str]:
    """
    Загружает промпт агрегатора для конкретного типа требований.

    Args:
        req_type: Код типа требований

    Returns:
        Текст промпта агрегатора или None
    """
    path = _resolve_path(req_type, "aggregator.txt")
    content = _read_file(path)
    if content:
        return _resolve_includes(content)
    return None


def load_system_base() -> str:
    """
    Загружает базовый системный промпт (роль, формат, ограничения).

    Returns:
        Текст системного промпта. Возвращает заглушку если файл не найден.
    """
    path = _resolve_path("system_base.txt")
    content = _read_file(path)
    if content:
        return content
    logger.warning("[load_system_base] system_base.txt not found, using fallback")
    return (
        "Ты — системный аналитик мирового класса. "
        "Анализируй требования строго и профессионально. "
        "Отвечай только на русском языке."
    )


def load_errors_criteria() -> str:
    """
    Загружает критерии для проверки сообщений об ошибках.

    Returns:
        Текст критериев или пустая строка если файл не найден.
    """
    path = _resolve_path("errors_criteria.txt")
    return _read_file(path) or ""


def load_summarizer_prompt() -> Optional[str]:
    """
    Загружает промпт для сжатия большого документа (Уровень 2).

    Returns:
        Текст промпта или None если файл не найден.
    """
    path = _resolve_path("summarizer.txt")
    content = _read_file(path)
    if content:
        return _resolve_includes(content)
    return None


def load_unknown_prompt() -> Optional[str]:
    """
    Загружает fallback промпт для неизвестных типов требований.

    Returns:
        Текст промпта или None если файл не найден.
    """
    path = _resolve_path("unknown.txt")
    content = _read_file(path)
    if content:
        return _resolve_includes(content)
    return None


def get_pass_count(req_type: str) -> int:
    """
    Определяет количество проходов для данного типа требований.

    Считает количество файлов pass{N}_*.txt в директории типа.

    Args:
        req_type: Код типа требований

    Returns:
        Количество проходов (0 если тип не поддерживается)
    """
    type_dir = _resolve_path(req_type)

    if not os.path.isdir(type_dir):
        return 0

    try:
        count = 0
        for i in range(1, 10):  # Максимум 9 проходов
            prefix = f"pass{i}_"
            files = [f for f in os.listdir(type_dir) if f.startswith(prefix) and f.endswith(".txt")]
            if files:
                count = i
            else:
                break
        return count
    except OSError:
        return 0


def get_supported_types() -> List[str]:
    """
    Возвращает список типов требований с поддержкой многопроходного ревью.

    Returns:
        Список кодов типов (имена поддиректорий в review/)
    """
    try:
        return [
            d for d in os.listdir(_PROMPTS_BASE)
            if os.path.isdir(_resolve_path(d)) and not d.startswith("_")
        ]
    except OSError:
        return []


def clear_prompt_cache() -> None:
    """
    Сбрасывает кеш промптов.

    Вызывать при горячем обновлении файлов промптов без перезапуска сервиса.
    """
    global _prompt_cache
    count = len(_prompt_cache)
    _prompt_cache = {}
    logger.info("[clear_prompt_cache] Cleared %d cached prompts", count)