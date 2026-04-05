# Путь: app/services/multi_pass_reviewer.py
"""
Многопроходное ревью страниц с требованиями.

Стратегия двух уровней:
─────────────────────────────────────────────────────────────────────────────
Уровень 1 — документ умещается в контекст целиком (~98% случаев):
    Проход 1..N  — каждый проход проверяет свою группу критериев.
                   Полный текст страницы + тематический контекст.
    Финальный    — агрегатор объединяет все частичные результаты,
                   может добавлять собственные наблюдения.

Уровень 2 — документ не умещается (>available_tokens):
    Шаг 0        — LLM сжимает документ до ~8K токенов (структурированный конспект).
    Проход 1..N  — те же проходы, но по конспекту.
    Финальный    — агрегатор + стандартное предупреждение в начале ответа.
─────────────────────────────────────────────────────────────────────────────

Количество проходов зависит от типа требований и определяется числом
файлов pass{N}_*.txt в соответствующей директории промптов.

Для неизвестных типов используется один проход с universal промптом.
"""

import json
import logging
import re
from typing import Optional, List, Dict, Any

from app.services.prompt_loader import (
    load_pass_prompt,
    load_aggregator_prompt,
    load_system_base,
    load_errors_criteria,
    load_summarizer_prompt,
    load_unknown_prompt,
    get_pass_count,
)
from app.utils.tokens_budget_utils import count_tokens, get_llm_context_size, calculate_token_budget
from app.llm_interface import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# Типы требований которые проверяют сообщения об ошибках — errors_criteria включается
# только в их проходы (pass где это указано через {{include: errors_criteria.txt}})
_TYPES_WITH_ERROR_MESSAGES = {
    "function", "integration", "screenItemForm", "screenListForm", "control"
}

# Предупреждение для уровня 2 (большие документы)
_LARGE_DOC_WARNING = (
    "⚠️ ВНИМАНИЕ: Данный документ превышает допустимый размер контекста модели. "
    "Анализ выполнен по сокращённому структурированному представлению страницы, "
    "а не по полному тексту. Все выводы требуют дополнительной проверки аналитиком "
    "на основе оригинального документа в Confluence.\n\n"
)


class MultiPassReviewer:
    """
    Выполняет многопроходное ревью одной страницы требований.

    Один экземпляр создаётся на каждый вызов analyze_pages и используется
    для всех страниц в запросе последовательно.
    """

    def __init__(self):
        self.llm = get_llm()
        self.llm_context_size = get_llm_context_size()
        self.system_base = load_system_base()
        self.errors_criteria = load_errors_criteria()

    def review_page(
        self,
        page_id: str,
        page_content: str,
        page_title: str,
        req_type: str,
        req_type_name: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        Выполняет полное многопроходное ревью одной страницы.

        Args:
            page_id: Идентификатор страницы Confluence
            page_content: Полный текст страницы (approved_content)
            page_title: Заголовок страницы
            req_type: Код типа требований (function, dataModel, ...)
            req_type_name: Человекочитаемое название типа
            context: Предварительно построенный RAG-контекст

        Returns:
            Словарь с ключами:
                analysis      — финальный текст анализа (str)
                pass_count    — количество выполненных проходов (int)
                level         — уровень обработки (1 или 2)
                token_usage   — статистика использования токенов (dict)
        """
        logger.info(
            "[review_page] <- page_id=%s, type=%s, content=%d chars, context=%d chars",
            page_id, req_type, len(page_content), len(context)
        )

        # Определяем доступный бюджет для документа
        system_tokens = count_tokens(self.system_base)
        context_tokens = count_tokens(context)
        response_reserve = int(self.llm_context_size * 0.15)

        # Сколько токенов доступно для тела документа в одном проходе
        # (промпт прохода ~800-1200 токенов, оставляем запас)
        pass_prompt_reserve = 1500
        available_for_doc = (
            self.llm_context_size
            - system_tokens
            - context_tokens
            - response_reserve
            - pass_prompt_reserve
        )

        doc_tokens = count_tokens(page_content)

        logger.info(
            "[review_page] page_id=%s: doc=%d tokens, available=%d tokens, context=%d tokens",
            page_id, doc_tokens, available_for_doc, context_tokens
        )

        # Выбираем уровень обработки
        if doc_tokens <= available_for_doc:
            return self._review_level1(
                page_id=page_id,
                page_content=page_content,
                page_title=page_title,
                req_type=req_type,
                req_type_name=req_type_name,
                context=context,
                doc_tokens=doc_tokens,
                system_tokens=system_tokens,
                context_tokens=context_tokens,
            )
        else:
            logger.info(
                "[review_page] page_id=%s: document too large (%d > %d tokens), using Level 2",
                page_id, doc_tokens, available_for_doc
            )
            return self._review_level2(
                page_id=page_id,
                page_content=page_content,
                page_title=page_title,
                req_type=req_type,
                req_type_name=req_type_name,
                context=context,
                doc_tokens=doc_tokens,
                available_for_doc=available_for_doc,
                system_tokens=system_tokens,
                context_tokens=context_tokens,
            )

    # =========================================================================
    # УРОВЕНЬ 1 — полный документ
    # =========================================================================

    def _review_level1(
        self,
        page_id: str,
        page_content: str,
        page_title: str,
        req_type: str,
        req_type_name: str,
        context: str,
        doc_tokens: int,
        system_tokens: int,
        context_tokens: int,
    ) -> Dict[str, Any]:
        """Многопроходное ревью с полным текстом документа."""

        logger.info("[_review_level1] <- page_id=%s, content length=%d", page_id, len(page_content))

        pass_count = get_pass_count(req_type)
        header = self._build_page_header(page_id, page_title, req_type_name)

        if pass_count == 0:
            # Неизвестный тип — один universal проход
            logger.info("[_review_level1] Unknown type '%s', using universal pass", req_type)
            partial = self._run_universal_pass(
                page_id=page_id,
                header=header,
                page_content=page_content,
                context=context,
                req_type_name=req_type_name,
            )
            pass_results = [partial]
            pass_count = 1
        else:
            pass_results = []
            for i in range(1, pass_count + 1):
                partial = self._run_pass(
                    pass_index=i,
                    req_type=req_type,
                    page_id=page_id,
                    header=header,
                    page_content=page_content,
                    context=context,
                    req_type_name=req_type_name,
                )
                pass_results.append(partial)
                logger.info(
                    "[_review_level1] page_id=%s pass %d/%d done (%d chars result)",
                    page_id, i, pass_count, len(partial)
                )

        # Финальная агрегация
        analysis = self._run_aggregator(
            req_type=req_type,
            page_id=page_id,
            header=header,
            pass_results=pass_results,
            req_type_name=req_type_name,
            level=1,
        )

        logger.info("[_review_level1] -> %d runs completed.",pass_count)
        return {
            "analysis": analysis,
            "pass_count": pass_count,
            "level": 1,
            "token_usage": {
                "doc_tokens": doc_tokens,
                "context_tokens": context_tokens,
                "system_tokens": system_tokens,
                "llm_context_size": self.llm_context_size,
            }
        }

    # =========================================================================
    # УРОВЕНЬ 2 — большой документ: сначала сжатие, потом проходы
    # =========================================================================

    def _review_level2(
        self,
        page_id: str,
        page_content: str,
        page_title: str,
        req_type: str,
        req_type_name: str,
        context: str,
        doc_tokens: int,
        available_for_doc: int,
        system_tokens: int,
        context_tokens: int,
    ) -> Dict[str, Any]:
        """Многопроходное ревью с предварительным сжатием документа."""

        logger.info("[_review_level2] <- Compressing document for page_id=%s, content length=%d",
                    page_id, len(page_content))

        # Шаг 0 — сжатие документа
        compressed = self._compress_document(
            page_content=page_content,
            page_title=page_title,
            req_type_name=req_type_name,
            target_tokens=min(available_for_doc, 8000),
        )

        compressed_tokens = count_tokens(compressed)
        logger.info(
            "[_review_level2] page_id=%s: compressed %d -> %d tokens",
            page_id, doc_tokens, compressed_tokens
        )

        # Далее — те же проходы, но с конспектом вместо полного текста
        pass_count = get_pass_count(req_type)
        header = self._build_page_header(page_id, page_title, req_type_name)

        if pass_count == 0:
            partial = self._run_universal_pass(
                page_id=page_id,
                header=header,
                page_content=compressed,
                context=context,
                req_type_name=req_type_name,
            )
            pass_results = [partial]
            pass_count = 1
        else:
            pass_results = []
            for i in range(1, pass_count + 1):
                partial = self._run_pass(
                    pass_index=i,
                    req_type=req_type,
                    page_id=page_id,
                    header=header,
                    page_content=compressed,
                    context=context,
                    req_type_name=req_type_name,
                )
                pass_results.append(partial)
                logger.info(
                    "[_review_level2] page_id=%s pass %d/%d done",
                    page_id, i, pass_count
                )

        # Агрегация с пометкой уровня 2
        analysis = self._run_aggregator(
            req_type=req_type,
            page_id=page_id,
            header=header,
            pass_results=pass_results,
            req_type_name=req_type_name,
            level=2,
        )

        logger.info("[_review_level2] -> %d runs passed", pass_count)
        return {
            "analysis": analysis,
            "pass_count": pass_count,
            "level": 2,
            "token_usage": {
                "doc_tokens": doc_tokens,
                "compressed_tokens": compressed_tokens,
                "context_tokens": context_tokens,
                "system_tokens": system_tokens,
                "llm_context_size": self.llm_context_size,
            }
        }

    # =========================================================================
    # ВЫЗОВЫ LLM
    # =========================================================================

    def _run_pass(
        self,
        pass_index: int,
        req_type: str,
        page_id: str,
        header: str,
        page_content: str,
        context: str,
        req_type_name: str,
    ) -> str:
        """
        Выполняет один проход ревью.

        Args:
            pass_index: Номер прохода (1-based)
            req_type: Код типа требований
            page_id: Идентификатор страницы
            header: Заголовок страницы (page_id + title + type)
            page_content: Текст страницы (полный или сжатый)
            context: RAG-контекст
            req_type_name: Человекочитаемое название типа

        Returns:
            Текст частичного анализа от LLM
        """
        logger.debug("[_run_pass] <- page_id=%s, pass_index=%d, type=%s",
                     page_id, pass_index, req_type_name)

        pass_prompt = load_pass_prompt(req_type, pass_index)
        if not pass_prompt:
            logger.warning(
                "[_run_pass] No prompt for type='%s' pass=%d, skipping",
                req_type, pass_index
            )
            return f"[Проход {pass_index}: промпт не найден]"

        human_message = self._build_pass_message(
            pass_prompt=pass_prompt,
            header=header,
            page_content=page_content,
            context=context,
            req_type_name=req_type_name,
            pass_index=pass_index,
        )

        logger.debug(
            "[_run_pass] -> page_id=%s pass=%d, message=%d chars",
            page_id, pass_index, len(human_message)
        )

        return self._invoke_llm(human_message, label=f"pass{pass_index}[{page_id}]")

    def _run_universal_pass(
        self,
        page_id: str,
        header: str,
        page_content: str,
        context: str,
        req_type_name: str,
    ) -> str:
        """Универсальный единственный проход для неизвестных типов."""

        prompt = load_unknown_prompt()
        if not prompt:
            prompt = (
                "Проверь данную страницу требований на полноту, непротиворечивость, "
                "проверяемость и осуществимость. Укажи конкретные замечания."
            )

        human_message = self._build_pass_message(
            pass_prompt=prompt,
            header=header,
            page_content=page_content,
            context=context,
            req_type_name=req_type_name,
            pass_index=1,
        )

        return self._invoke_llm(human_message, label=f"universal[{page_id}]")

    def _run_aggregator(
        self,
        req_type: str,
        page_id: str,
        header: str,
        pass_results: List[str],
        req_type_name: str,
        level: int,
    ) -> str:
        """
        Финальная агрегация результатов всех проходов.

        Args:
            req_type: Код типа требований
            page_id: Идентификатор страницы
            header: Заголовок страницы
            pass_results: Список результатов каждого прохода
            req_type_name: Человекочитаемое название типа
            level: Уровень обработки (1 или 2)

        Returns:
            Финальный анализ. Для уровня 2 — с предупреждением в начале.
        """
        logger.info("[_run_aggregator] <- page_id=%s level=%s (%d chars)",
                    page_id, level, sum(len(r) for r in pass_results) )

        aggregator_prompt = load_aggregator_prompt(req_type)
        if not aggregator_prompt:
            # Fallback агрегатор если файл не найден
            aggregator_prompt = (
                "На основе результатов всех проходов ревью составь финальный структурированный анализ. "
                "Объедини все замечания, исключи дублирование. "
                "Можешь добавить общие выводы которые следуют из совокупности замечаний. "
                "Верни результат в формате JSON: {{\"<page_id>\": \"<текст анализа>\"}}."
            )

        # Формируем блок с результатами проходов
        passes_text = ""
        for i, result in enumerate(pass_results, 1):
            passes_text += f"\n\n--- РЕЗУЛЬТАТ ПРОХОДА {i} ---\n{result}"

        human_message = (
            f"{header}\n\n"
            f"ТИП ТРЕБОВАНИЙ: {req_type_name}\n\n"
            f"ЗАДАЧА АГРЕГАТОРА:\n{aggregator_prompt}\n\n"
            f"РЕЗУЛЬТАТЫ ПРОХОДОВ РЕВЬЮ:{passes_text}\n\n"
            f"Верни финальный анализ строго в JSON формате:\n"
            f"{{\"{page_id}\": \"Детальный анализ...\"}}"
        )

        raw_result = self._invoke_llm(human_message, label=f"aggregator[{page_id}]")

        # Парсим JSON из ответа агрегатора
        analysis_text = self._extract_analysis_text(raw_result, page_id)

        # Для уровня 2 добавляем предупреждение
        if level == 2:
            analysis_text = _LARGE_DOC_WARNING + analysis_text

        logger.info("[_run_aggregator] -> .")
        return analysis_text

    def _compress_document(
        self,
        page_content: str,
        page_title: str,
        req_type_name: str,
        target_tokens: int,
    ) -> str:
        """
        Сжимает большой документ до структурированного конспекта.

        Конспект сохраняет все атрибуты, типы данных, алгоритмы шагов,
        ссылки и бизнес-правила — всё что нужно для ревью.

        Args:
            page_content: Полный текст страницы
            page_title: Заголовок страницы
            req_type_name: Тип требований для контекстного сжатия
            target_tokens: Целевой размер конспекта в токенах

        Returns:
            Сжатый конспект документа
        """
        summarizer_prompt = load_summarizer_prompt()
        if not summarizer_prompt:
            summarizer_prompt = (
                "Создай структурированный конспект данной страницы требований для последующего ревью. "
                "Сохрани: все атрибуты с их типами данных и ограничениями, все алгоритмические шаги, "
                "все бизнес-правила и условия, все ссылки на другие страницы, "
                "все сообщения об ошибках. "
                f"Целевой объём конспекта: не более {target_tokens} токенов (~{target_tokens * 3} символов)."
            )

        target_chars = target_tokens * 3

        human_message = (
            f"ЗАГОЛОВОК: {page_title}\n"
            f"ТИП ТРЕБОВАНИЙ: {req_type_name}\n\n"
            f"ЗАДАЧА:\n{summarizer_prompt}\n\n"
            f"ДОКУМЕНТ ДЛЯ СЖАТИЯ:\n{page_content}"
        )

        compressed = self._invoke_llm(human_message, label=f"compress[{page_title[:40]}]")

        # Проверяем что сжатие реально произошло
        if len(compressed) > len(page_content) * 0.9:
            logger.warning(
                "[_compress_document] Compression ineffective: %d -> %d chars, using truncation",
                len(page_content), len(compressed)
            )
            # Жёсткий fallback — просто обрезаем
            compressed = page_content[:target_chars] + "\n\n[... документ обрезан ...]"

        return compressed

    def _invoke_llm(self, human_message: str, label: str = "") -> str:
        """
        Вызывает LLM с системным промптом и пользовательским сообщением.

        Args:
            human_message: Текст пользовательского сообщения
            label: Метка для логирования

        Returns:
            Текст ответа LLM
        """
        try:
            messages = [
                SystemMessage(content=self.system_base),
                HumanMessage(content=human_message),
            ]

            response = self.llm.invoke(messages)

            content = response.content if hasattr(response, "content") else str(response)
            logger.debug("[_invoke_llm] %s -> %d chars", label, len(content))
            return content.strip()

        except Exception as e:
            logger.error("[_invoke_llm] %s error: %s", label, e, exc_info=True)
            return f"[Ошибка LLM при выполнении {label}: {e}]"

    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================================================================

    @staticmethod
    def _build_page_header(page_id: str, page_title: str, req_type_name: str) -> str:
        """Формирует стандартный заголовок страницы для промптов."""
        return (
            f"---\n"
            f"page_id: {page_id}\n"
            f"title: {page_title}\n"
            f"type: {req_type_name}\n"
            f"---"
        )

    @staticmethod
    def _build_pass_message(
        pass_prompt: str,
        header: str,
        page_content: str,
        context: str,
        req_type_name: str,
        pass_index: int,
    ) -> str:
        """
        Собирает полное сообщение для одного прохода.

        Структура:
            [Заголовок страницы]
            [Тип требований]
            [Критерии проверки для этого прохода]
            [Страница требований]
            [Контекст — если не пустой]
        """
        parts = [
            header,
            f"\nТИП ТРЕБОВАНИЙ: {req_type_name}",
            f"\nКРИТЕРИИ ПРОХОДА {pass_index}:\n{pass_prompt}",
            f"\nСТРАНИЦА ТРЕБОВАНИЙ:\n{page_content}",
        ]

        if context and context.strip():
            parts.append(f"\nКОНТЕКСТ (существующие требования):\n{context}")

        parts.append(
            "\nВерни ТОЛЬКО список замечаний по указанным критериям. "
            "Если замечаний нет — верни пустую строку. "
            "Указывай конкретные ссылки на пункты требований."
        )

        return "\n".join(parts)

    @staticmethod
    def _extract_analysis_text(raw_result: str, page_id: str) -> str:
        """
        Извлекает текст анализа из JSON-ответа агрегатора.

        Если JSON не найден — возвращает сырой ответ как есть.

        Args:
            raw_result: Сырой ответ LLM
            page_id: Идентификатор страницы (ключ в JSON)

        Returns:
            Текст анализа
        """
        if not raw_result:
            return "Анализ не получен"

        # Пробуем распарсить JSON
        cleaned = raw_result.strip().strip("```json").strip("```").strip()

        # Ищем JSON объект
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Ключ может быть page_id или первый ключ словаря
                if page_id in parsed:
                    return str(parsed[page_id])
                elif parsed:
                    return str(next(iter(parsed.values())))
            except json.JSONDecodeError:
                pass

        # Fallback — возвращаем сырой текст
        logger.debug(
            "[_extract_analysis_text] -> Could not parse JSON for page_id=%s, returning raw",
            page_id
        )
        return raw_result


def create_reviewer() -> MultiPassReviewer:
    """Фабричная функция для создания экземпляра ревьюера."""
    return MultiPassReviewer()