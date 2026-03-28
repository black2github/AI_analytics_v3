# Путь: app/utils/text_processing.py
"""
Утилиты для обработки текста.

Функции:
    estimate_tokens  — оценка числа токенов в тексте
    extract_summary_simple — extractive summary (первые N символов)
    truncate_text    — обрезка текста до заданного числа токенов
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Коэффициент символов на токен для русского текста.
# Русское слово в среднем 6-7 символов, токен BPE ~4-5 символов.
# Эмпирически: ~3 символа на токен для смешанного рус/англ текста.
_CHARS_PER_TOKEN = 3


def estimate_tokens(text: str) -> int:
    """
    Быстрая оценка числа токенов в тексте без загрузки токенизатора.

    Использует эмпирический коэффициент: ~3 символа на токен
    для смешанного русско-английского текста технических требований.
    Точность достаточна для принятия решений о chunking и фильтрации,
    не требует точного подсчёта.

    Args:
        text: Входной текст

    Returns:
        Оценочное число токенов
    """
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def extract_summary_simple(
    text: str,
    max_length: int = 500,
    method: str = "smart",
) -> str:
    """
    Extractive summary без LLM — быстрый fallback для индексации.

    Методы:
        "head"  — первые max_length символов текста
        "smart" — первый смысловой блок: заголовок + первый абзац,
                  не превышая max_length символов

    Args:
        text: Входной текст (markdown)
        max_length: Максимальная длина summary в символах
        method: Метод извлечения ("head" | "smart")

    Returns:
        Строка summary
    """
    if not text:
        return ""

    text = text.strip()

    if method == "smart":
        return _extract_smart(text, max_length)

    # Метод "head" — просто первые N символов
    return _trim_to_sentence(text[:max_length], max_length)


def truncate_text(text: str, max_chars: int, add_ellipsis: bool = False) -> str:
    """
    Обрезает текст до заданного числа символов.

    Обрезает по границе предложения если возможно.

    Args:
        text: Входной текст
        max_chars: Максимальное число символов
        add_ellipsis: Добавить "..." в конец если текст был обрезан

    Returns:
        Обрезанный текст
    """
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    truncated = _trim_to_sentence(text, max_chars)
    if add_ellipsis and len(truncated) < len(text):
        truncated = truncated.rstrip() + "..."
    return truncated


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def _extract_smart(text: str, max_length: int) -> str:
    """
    Умное извлечение summary: заголовок + первый содержательный абзац.

    Логика:
    1. Ищем первый заголовок (# ...) — берём его как контекст
    2. Берём первый непустой абзац после заголовка
    3. Если заголовков нет — берём первые абзацы до max_length

    Args:
        text: Markdown текст
        max_length: Максимальная длина в символах

    Returns:
        Извлечённый summary
    """
    lines = text.splitlines()
    result_parts = []
    current_len = 0
    found_content = False

    for line in lines:
        stripped = line.strip()

        # Пропускаем пустые строки в начале
        if not stripped and not found_content:
            continue

        # Пропускаем служебные строки markdown таблиц
        if stripped.startswith('| ---') or stripped == '|':
            continue

        # Заголовки включаем всегда (они короткие и информативны)
        is_heading = stripped.startswith('#')

        # Строки таблицы — включаем только если есть место
        is_table_row = stripped.startswith('|')

        candidate = stripped if is_table_row else line.rstrip()

        if current_len + len(candidate) + 1 > max_length:
            # Добавляем сколько влезет если ещё ничего не нашли
            if not found_content:
                remaining = max_length - current_len
                if remaining > 20:
                    result_parts.append(candidate[:remaining])
            break

        result_parts.append(candidate)
        current_len += len(candidate) + 1

        if stripped and not is_heading:
            found_content = True

        # Останавливаемся после первого содержательного блока
        # (заголовок + абзац или таблица)
        if found_content and not stripped and current_len > max_length // 3:
            break

    summary = "\n".join(result_parts).strip()

    # Финальная обрезка если всё ещё длинно
    if len(summary) > max_length:
        summary = _trim_to_sentence(summary, max_length)

    return summary or text[:max_length]


def _trim_to_sentence(text: str, max_length: int) -> str:
    """
    Обрезает текст до max_length символов по границе предложения.

    Ищет последнюю точку/перенос строки перед границей.
    Если не находит — обрезает жёстко.

    Args:
        text: Текст для обрезки
        max_length: Максимальная длина в символах

    Returns:
        Обрезанный текст
    """
    if len(text) <= max_length:
        return text

    chunk = text[:max_length]

    # Ищем последний разрыв предложения
    for sep in ('\n', '. ', '! ', '? '):
        pos = chunk.rfind(sep)
        if pos > max_length // 2:
            return chunk[:pos + len(sep)].strip()

    return chunk.strip()