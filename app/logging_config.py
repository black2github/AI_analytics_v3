# app/logging_config.py

import logging
import sys

MAX_CHARS_SIZE = 64000

class TrimFilter(logging.Filter):
    """
    Фильтр для обрезки длинных сообщений с динамическим уровнем логирования.
    """

    def __init__(self, logger_level=logging.INFO):
        super().__init__()
        self.logger_level = logger_level

    def filter(self, record):
        # ИСПРАВЛЕНИЕ: Проверяем против текущего уровня фильтра
        if record.levelno < self.logger_level:
            return False  # Блокируем записи ниже установленного уровня

        # Обрезаем INFO записи до 2000 символов
        if record.levelno == logging.INFO:
            if isinstance(record.msg, str) and len(record.msg) > MAX_CHARS_SIZE:
                record.msg = record.msg[:MAX_CHARS_SIZE] + "... [обрезано]"
            # Также обрабатываем случай с аргументами
            if hasattr(record, 'args') and record.args:
                try:
                    # Форматируем сообщение с аргументами
                    formatted_msg = record.msg % record.args
                    if len(formatted_msg) > MAX_CHARS_SIZE:
                        record.msg = formatted_msg[:MAX_CHARS_SIZE] + "... [обрезано]"
                        record.args = ()  # Очищаем args, так как уже отформатировали
                except (TypeError, ValueError):
                    # Если форматирование не удалось, обрезаем только msg
                    if len(str(record.msg)) > MAX_CHARS_SIZE:
                        record.msg = str(record.msg)[:MAX_CHARS_SIZE] + "... [обрезано]"

        # WARNING, ERROR, CRITICAL пропускаем без изменений
        return True


def setup_logging():
    """
    Настройка логирования с уровнем INFO и обрезкой длинных сообщений.
    """
    logger = logging.getLogger()

    # Устанавливаем уровень INFO (DEBUG исключается)
    logger.setLevel(logging.INFO)

    # Очищаем существующие обработчики
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Настраиваем формат логирования
    formatter = logging.Formatter(
        '%(asctime)s,%(msecs)03d [%(levelname)s] %(filename)s:%(lineno)d %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Файловый обработчик
    file_handler = logging.FileHandler('rag-services.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Добавляем фильтр обрезки к обоим обработчикам
    trim_filter = TrimFilter(logging.INFO)
    console_handler.addFilter(trim_filter)
    file_handler.addFilter(trim_filter)

    # Добавляем обработчики к логгеру
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Установка кодировки UTF-8 для консоли на Windows
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            # Для старых версий Python
            pass

    # Настройка логирования для внешних библиотек
    # Снижаем уровень логирования для шумных библиотек
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('chromadb').setLevel(logging.WARNING)
    logging.getLogger('langchain').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)

    logger.info(f"Logging configured: level=INFO, max_message_length={MAX_CHARS_SIZE} chars")