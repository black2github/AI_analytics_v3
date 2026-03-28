# Путь: app/services/page_summary_generator.py
"""
Сервис для генерации summary документов.

Поддерживает:
- Extractive summarization (быстро, без LLM)
- LLM-based summarization (точно, медленно)
- Batch processing для больших объёмов
"""

import json
import logging
import os
import re
import asyncio
from typing import List, Dict, Optional
from langchain_core.messages import HumanMessage

from app.llm_interface import get_llm
from app.utils.text_processing import (
    extract_summary_simple,
    estimate_tokens,
    truncate_text
)

logger = logging.getLogger(__name__)

# ============================================================================
# ЗАГРУЗКА ГЛОССАРИЯ
# ============================================================================

def _load_glossary() -> Dict[str, str]:
    """
    Загружает глоссарий аббревиатур из glossary.json.

    Объединяет все секции файла в единый плоский словарь {аббревиатура: расшифровка}.
    Загружается один раз при импорте модуля.

    Returns:
        Словарь {аббревиатура: расшифровка}
    """
    glossary: Dict[str, str] = {}
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "data", "glossary.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for key, value in data.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict):
                glossary.update(value)

        logger.debug("[_load_glossary] Loaded %d terms", len(glossary))
    except FileNotFoundError:
        logger.warning("[_load_glossary] glossary.json not found, proceeding without glossary")
    except Exception as e:
        logger.warning("[_load_glossary] Failed to load glossary: %s", e)

    return glossary


# Загружаем один раз при импорте
_GLOSSARY: Dict[str, str] = _load_glossary()


def expand_abbreviations(text: str, glossary: Optional[Dict[str, str]] = None) -> str:
    """
    Раскрывает аббревиатуры в тексте при первом вхождении.

    Например: "ЕСК" → "ЕСК (Единый Справочник Клиентов)"

    Обрабатывает только первое вхождение каждой аббревиатуры в тексте
    чтобы не перегружать текст расшифровками.

    Args:
        text: Исходный текст
        glossary: Словарь аббревиатур (None = использовать _GLOSSARY)

    Returns:
        Текст с раскрытыми аббревиатурами при первом вхождении
    """
    if not text:
        return text

    glos = glossary if glossary is not None else _GLOSSARY
    if not glos:
        return text

    # Сортируем по убыванию длины чтобы "АС СБП" заменялось раньше "СБП"
    sorted_abbrs = sorted(glos.keys(), key=len, reverse=True)

    replaced: set = set()
    result = text

    for abbr in sorted_abbrs:
        if abbr in replaced:
            continue
        # Ищем только целое слово/фразу (не часть другого слова)
        pattern = r'(?<![А-ЯA-Z\w])' + re.escape(abbr) + r'(?![А-ЯA-Z\w])'
        expansion = f"{abbr} ({glos[abbr]})"

        new_result = re.sub(pattern, expansion, result, count=1)
        if new_result != result:
            result = new_result
            replaced.add(abbr)

    return result


class SummaryGenerator:
    """
    Генератор summary для документов с поддержкой extractive и LLM методов.
    """

    def __init__(
            self,
            llm_provider: Optional[str] = None,
            llm_model: Optional[str] = None,
            llm_temperature: float = 0.3
    ):
        """
        Args:
            llm_provider: LLM провайдер (None = из config)
            llm_model: LLM модель (None = из config)
            llm_temperature: Температура для LLM (0.0-1.0)
        """
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.llm_temperature = llm_temperature
        self._llm = None

    def _get_llm(self):
        """Ленивая инициализация LLM."""
        if self._llm is None:
            self._llm = get_llm(
                provider=self.llm_provider,
                model=self.llm_model,
                temperature=self.llm_temperature
            )
        return self._llm

    def generate_extractive(
            self,
            text: str,
            max_length: int = 500,
            method: str = "smart"
    ) -> str:
        """
        Быстрая extractive summarization без LLM.

        Args:
            text: Исходный текст
            max_length: Максимальная длина summary
            method: Метод извлечения (first_paragraph/first_sentences/smart)

        Returns:
            Summary текст
        """
        logger.debug(
            "[generate_extractive] Processing %d chars with method='%s'",
            len(text), method
        )

        return extract_summary_simple(text, max_length, method)

    async def generate_llm(
            self,
            text: str,
            max_tokens: int = 200,
            context: Optional[str] = None,
            requirement_type: Optional[str] = None,
    ) -> str:
        """
        LLM-based summarization (async).

        Args:
            text: Исходный текст для саммаризации
            max_tokens: Максимальная длина summary в токенах
            context: Дополнительный контекст (опционально)
            requirement_type: Тип требования для выбора промпта
                (function/dataModel/integration/screenItemForm/states/process/...)

        Returns:
            Summary текст
        """
        logger.debug("[generate_llm] Processing %d chars, req_type=%s", len(text), requirement_type)

        # Вариант Б: предобработка — раскрываем аббревиатуры при первом вхождении
        # Это помогает LLM правильно интерпретировать domain-specific термины
        # прямо в контексте документа
        text = expand_abbreviations(text)

        # Формируем промпт с учётом типа требования и глоссарием (Вариант А)
        prompt = self._build_summary_prompt(text, context, requirement_type)

        # Вызываем LLM асинхронно
        try:
            llm = self._get_llm()

            # LangChain LLMs поддерживают ainvoke для async
            response = await llm.ainvoke(
                [HumanMessage(content=prompt)],
                max_tokens=max_tokens
            )

            summary = response.content.strip()

            logger.debug("[generate_llm] Generated summary (%d chars)", len(summary))

            return summary

        except Exception as e:
            logger.error(
                "[generate_llm] LLM error: %s. Falling back to extractive.",
                str(e)
            )
            # Fallback на extractive при ошибке LLM
            return self.generate_extractive(text, max_length=600)

    async def generate_batch(
            self,
            documents: List[Dict[str, str]],
            max_concurrent: int = 10,
            use_llm_for_large: bool = True,
            large_doc_threshold: int = 5000
    ) -> List[Dict[str, str]]:
        """
        Batch generation summary для множества документов.

        Стратегия:
        - Маленькие документы (<5K chars): extractive (быстро)
        - Большие документы (≥5K chars): LLM (точно) с параллелизмом

        Args:
            documents: Список документов [{page_id, title, content}, ...]
            max_concurrent: Максимальное количество параллельных LLM запросов
            use_llm_for_large: Использовать LLM для больших документов
            large_doc_threshold: Порог размера для LLM (символов)

        Returns:
            Список результатов [{page_id, title, summary, method}, ...]
        """
        logger.info(
            "[generate_batch] Processing %d documents (concurrent=%d, llm_for_large=%s)",
            len(documents), max_concurrent, use_llm_for_large
        )

        results = []

        # Разделяем на маленькие и большие
        small_docs = []
        large_docs = []

        for doc in documents:
            content = doc.get('content', '')
            if len(content) >= large_doc_threshold:
                large_docs.append(doc)
            else:
                small_docs.append(doc)

        logger.info(
            "[generate_batch] Split: %d small docs, %d large docs",
            len(small_docs), len(large_docs)
        )

        # 1. Обрабатываем маленькие документы extractive (синхронно, быстро)
        for doc in small_docs:
            content = doc.get('content', '')
            summary = self.generate_extractive(content, max_length=500)

            results.append({
                'page_id': doc.get('page_id'),
                'title': doc.get('title'),
                'summary': summary,
                'method': 'extractive',
                'original_length': len(content),
                'summary_length': len(summary)
            })

        logger.info("[generate_batch] Processed %d small docs with extractive", len(small_docs))

        # 2. Обрабатываем большие документы LLM (асинхронно, с ограничением параллелизма)
        if large_docs and use_llm_for_large:
            logger.info("[generate_batch] Starting LLM batch for %d large docs...", len(large_docs))

            # Семафор для ограничения параллелизма
            semaphore = asyncio.Semaphore(max_concurrent)

            async def process_with_semaphore(doc):
                """Обработка одного документа с семафором."""
                async with semaphore:
                    content = doc.get('content', '')
                    try:
                        summary = await self.generate_llm(content, max_tokens=200)
                        method = 'llm'
                    except Exception as e:
                        logger.error(
                            "[generate_batch] LLM failed for page_id=%s: %s. Using extractive.",
                            doc.get('page_id'), str(e)
                        )
                        summary = self.generate_extractive(content, max_length=500)
                        method = 'llm_fallback_extractive'

                    return {
                        'page_id': doc.get('page_id'),
                        'title': doc.get('title'),
                        'summary': summary,
                        'method': method,
                        'original_length': len(content),
                        'summary_length': len(summary)
                    }

            # Запускаем все задачи параллельно (с ограничением)
            tasks = [process_with_semaphore(doc) for doc in large_docs]
            large_results = await asyncio.gather(*tasks)

            results.extend(large_results)

            logger.info("[generate_batch] Processed %d large docs with LLM", len(large_docs))

        elif large_docs:
            # LLM отключен - используем extractive для всех
            for doc in large_docs:
                content = doc.get('content', '')
                summary = self.generate_extractive(content, max_length=500)

                results.append({
                    'page_id': doc.get('page_id'),
                    'title': doc.get('title'),
                    'summary': summary,
                    'method': 'extractive_large',
                    'original_length': len(content),
                    'summary_length': len(summary)
                })

            logger.info("[generate_batch] Processed %d large docs with extractive (LLM disabled)",
                        len(large_docs))

        logger.info(
            "[generate_batch] -> Completed %d/%d documents",
            len(results), len(documents)
        )

        return results

    def _build_summary_prompt(
            self,
            text: str,
            context: Optional[str] = None,
            requirement_type: Optional[str] = None,
    ) -> str:
        """
        Создаёт промпт для LLM summarization с учётом типа требования.

        Промпт оптимизирован для семантического поиска по бизнес-требованиям:
        summary должен отвечать на вопрос "какое бизнес-изменение затронет эту страницу",
        а не просто пересказывать структуру документа.

        Args:
            text: Текст документа
            context: Дополнительный контекст
            requirement_type: Тип требования (function/dataModel/integration/...)

        Returns:
            Промпт для LLM
        """
        # Инструкции по формату — общие для всех типов
        format_instruction = (
            "Напиши summary на русском языке длиной не более 500-700 символов. "
            "Используй профессиональную банковскую терминологию из оригинала. "
            "Не используй маркированные списки — только связный текст. "
            "Не начинай с фраз 'Документ описывает', 'Документ определяет', "
            "'Данная страница' — сразу указывай суть. "
        )

        # Типо-зависимые инструкции по содержанию
        type_instructions = {
            "function": (
                "Опиши: какое бизнес-действие выполняет функция, "
                "кто является актором (клиент/банк/система), "
                "с какими объектами (заявка/карта/счёт) она работает, "
                "какие ключевые шаги или проверки включает, "
                "какие смежные системы задействованы."
            ),
            "dataModel": (
                "Опиши: какая сущность модели данных моделируется, "
                "перечисли ключевые атрибуты с их бизнес-смыслом "
                "(не более 8-10 самых важных), "
                "укажи связи с другими сущностями если есть."
            ),
            "integration": (
                "Опиши: с какой внешней системой выполняется интеграция, "
                "какой метод/операция вызывается, "
                "какова бизнес-цель вызова, "
                "какие ключевые параметры передаются и возвращаются, "
                "в каких бизнес-процессах используется."
            ),
            "screenItemForm": (
                "Опиши: какая экранная форма или элемент интерфейса, "
                "в каком бизнес-сценарии используется, "
                "какие ключевые поля содержит и их назначение, "
                "какие действия доступны пользователю."
            ),
            "screenListForm": (
                "Опиши: какой список или журнал отображается, "
                "какие объекты показывает, "
                "в каком бизнес-сценарии используется, "
                "какие действия доступны пользователю."
            ),
            "states": (
                "Опиши: жизненный цикл какого объекта (заявка/запрос/заявление) описан, "
                "перечисли ключевые статусы и их бизнес-смысл, "
                "опиши основные переходы между статусами и условия переходов."
            ),
            "process": (
                "Опиши: какой бизнес-процесс описан, "
                "кто является участниками процесса, "
                "перечисли ключевые шаги и точки принятия решений, "
                "укажи результат процесса."
            ),
            "control": (
                "Опиши: какие бизнес-правила или контроли проверяются, "
                "к какому объекту (заявка/карта/платёж) применяются, "
                "какие условия проверяются и каковы последствия при нарушении."
            ),
        }

        # Берём инструкцию по типу или универсальную если тип неизвестен
        content_instruction = type_instructions.get(
            requirement_type or "",
            # Универсальная инструкция для неизвестных типов
            "Опиши суть документа: какой бизнес-объект или процесс описан, "
            "какие ключевые бизнес-правила или атрибуты определены, "
            "какие смежные системы или сервисы задействованы."
        )

        # Формируем компактный глоссарий для промпта — только термины
        # которые реально встречаются в тексте (Вариант А)
        glossary_section = self._build_glossary_section(text)

        prompt = (
            f"Ты — аналитик банковских систем ДБО для юридических лиц. "
            f"Создай summary страницы технических требований для семантического поиска.\n\n"
            f"ТИП ТРЕБОВАНИЯ: {requirement_type or 'не указан'}\n\n"
            + (f"ГЛОССАРИЙ ТЕРМИНОВ:\n{glossary_section}\n\n" if glossary_section else "")
            + f"ЧТО ВКЛЮЧИТЬ В SUMMARY:\n{content_instruction}\n\n"
            f"ФОРМАТ:\n{format_instruction}\n\n"
            f"ДОКУМЕНТ:\n{text}\n\n"
            f"SUMMARY:"
        )

        if context:
            prompt = (
                f"Ты — аналитик банковских систем ДБО для юридических лиц. "
                f"Создай summary страницы технических требований для семантического поиска.\n\n"
                f"ТИП ТРЕБОВАНИЯ: {requirement_type or 'не указан'}\n\n"
                f"КОНТЕКСТ:\n{context}\n\n"
                + (f"ГЛОССАРИЙ ТЕРМИНОВ:\n{glossary_section}\n\n" if glossary_section else "")
                + f"ЧТО ВКЛЮЧИТЬ В SUMMARY:\n{content_instruction}\n\n"
                f"ФОРМАТ:\n{format_instruction}\n\n"
                f"ДОКУМЕНТ:\n{text}\n\n"
                f"SUMMARY:"
            )

        return prompt

    def _build_glossary_section(self, text: str) -> str:
        """
        Строит компактную секцию глоссария для промпта.

        Включает только термины которые реально встречаются в тексте —
        чтобы не раздувать промпт лишними записями.

        Args:
            text: Текст документа

        Returns:
            Строка с глоссарием или пустая строка если терминов не найдено
        """
        if not _GLOSSARY:
            return ""

        found = []
        for abbr, definition in _GLOSSARY.items():
            # Проверяем наличие аббревиатуры в тексте как целого слова
            pattern = r'(?<![А-ЯA-Z\w])' + re.escape(abbr) + r'(?![А-ЯA-Z\w])'
            if re.search(pattern, text):
                found.append(f"- {abbr}: {definition}")

        if not found:
            return ""

        return "\n".join(sorted(found))


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def create_summary_generator(
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None
) -> SummaryGenerator:
    """
    Фабричная функция для создания SummaryGenerator.

    Args:
        llm_provider: LLM провайдер (None = из config)
        llm_model: LLM модель (None = из config)

    Returns:
        Экземпляр SummaryGenerator
    """
    return SummaryGenerator(
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_temperature=0.2  # Низкая температура для summary
    )


async def generate_summaries_for_pages(
        pages: List[Dict[str, str]],
        use_llm: bool = True,
        max_concurrent: int = 10
) -> Dict[str, str]:
    """
    Генерирует summary для списка страниц.

    Args:
        pages: Список страниц [{page_id, title, content}, ...]
        use_llm: Использовать LLM для больших документов
        max_concurrent: Максимальное количество параллельных запросов

    Returns:
        Словарь {page_id: summary}
    """
    logger.info("[generate_summaries_for_pages] <- Processing %d pages", len(pages))

    generator = create_summary_generator()

    results = await generator.generate_batch(
        documents=pages,
        max_concurrent=max_concurrent,
        use_llm_for_large=use_llm
    )

    # Конвертируем в словарь
    summaries = {
        result['page_id']: result['summary']
        for result in results
    }

    logger.info("[generate_summaries_for_pages] -> Generated %d summaries", len(summaries))

    return summaries