# app/logging_utils.py

import logging


def set_log_level(level_name: str):
    """
    Динамически изменяет уровень логирования.
    """
    level = getattr(logging, level_name.upper(), logging.INFO)

    logger = logging.getLogger()

    # Отладка: логируем изменение уровня
    current_level_name = logging.getLevelName(logger.level)
    print(
        f"[DEBUG] Changing log level from {current_level_name} to {level_name.upper()}")  # Используем print для гарантии вывода

    logger.setLevel(level)

    # Обновляем уровень для всех обработчиков
    for handler in logger.handlers:
        handler.setLevel(level)

        #  ИСПРАВЛЕНИЕ: Обновляем фильтр правильно
        for filter_obj in handler.filters:
            if hasattr(filter_obj, 'logger_level'):
                old_level = logging.getLevelName(filter_obj.logger_level)
                filter_obj.logger_level = level
                print(f"[DEBUG] Updated filter level from {old_level} to {level_name.upper()}")

    # Используем print для гарантии, что сообщение будет видно
    print(f"[DEBUG] Log level successfully changed to: {level_name.upper()}")
    logging.info(f"Log level successfully changed to: {level_name.upper()}")


def get_current_log_level() -> str:
    """Возвращает текущий уровень логирования."""
    logger = logging.getLogger()
    return logging.getLevelName(logger.level)


def log_sample_messages():
    """Выводит примеры сообщений разных уровней для тестирования."""
    logger = logging.getLogger(__name__)

    # Генерируем длинное сообщение для тестирования обрезки
    long_message = "Отладочное сообщение для тестирования обрезки 123 " * 24  #  1200 символов

    logger.debug("DEBUG: Это отладочное сообщение (должно быть скрыто)")
    logger.info(f"INFO: Короткое информационное сообщение")
    logger.info(f"INFO: Длинное информационное сообщение: {long_message}")
    logger.warning("WARNING: Предупреждение")
    logger.error("ERROR: Ошибка")