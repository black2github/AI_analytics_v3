# Путь: app/services/page_summary_generator.py
"""
Сервис для генерации summary документов.

Поддерживает:
- Extractive summarization (быстро, без LLM)
- LLM-based summarization (точно, медленно)
- Batch processing для больших объёмов
"""

import logging
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
            context: Optional[str] = None
    ) -> str:
        """
        LLM-based summarization (async).

        Args:
            text: Исходный текст для саммаризации
            max_tokens: Максимальная длина summary в токенах
            context: Дополнительный контекст (опционально)

        Returns:
            Summary текст
        """
        logger.debug("[generate_llm] Processing %d chars", len(text))

        # Обрезаем текст если слишком длинный (берём начало)
        # Для большинства LLM context limit ~8K токенов
        max_input_chars = 10000  # ~3300 токенов для русского
        if len(text) > max_input_chars:
            logger.warning(
                "[generate_llm] Text too long (%d chars), truncating to %d",
                len(text), max_input_chars
            )
            text = truncate_text(text, max_input_chars, add_ellipsis=True)

        # Формируем промпт
        prompt = self._build_summary_prompt(text, context)

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

    def _build_summary_prompt(self, text: str, context: Optional[str] = None) -> str:
        """
        Создаёт промпт для LLM summarization.

        Args:
            text: Текст документа
            context: Дополнительный контекст

        Returns:
            Промпт для LLM
        """
        prompt = f"""Создай краткое саммари (2-3 предложения, максимум 200 слов) для следующего технического требования.

Саммари должно:
- Отражать суть документа и ключевые сущности
- Быть понятным и информативным
- Использовать профессиональную терминологию из оригинала

ДОКУМЕНТ:
{text}
"""

        if context:
            prompt += f"\n\nКОНТЕКСТ:\n{context}\n"

        prompt += "\nСАММАРИ:"

        return prompt


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
        llm_temperature=0.3  # Низкая температура для summary
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