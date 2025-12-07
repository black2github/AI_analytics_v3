# app/services/summary_service.py

import logging
from typing import Dict, List, Optional, Any
from langchain_core.prompts import PromptTemplate
# ИСПРАВЛЕНО: Удалили LLMChain
# from langchain_community.chains import LLMChain
from app.llm_interface import get_llm
from app.utils.tokens_budget_utils import count_tokens
from app.confluence_loader import get_child_page_ids
from app.filter_all_fragments import filter_all_fragments
from app.filter_approved_fragments import filter_approved_fragments
from app.page_cache import get_page_data_cached

logger = logging.getLogger(__name__)


class ServiceSummaryService:
    """Сервис для создания саммари по требованиям сервиса"""

    DEFAULT_PROMPT = """
Ты - системный аналитик банковской системы. 
На основе требований к микросервису создай краткое (не более 300 слов) и структурированное саммари.

ТРЕБОВАНИЯ СЕРВИСА:
{requirements}

Создай саммари в следующем формате:

## НАЗНАЧЕНИЕ СЕРВИСА
[Кратко - зачем, для каких целей или для чего нужен этот сервис в системе, его назначение.]

## ОСНОВНЫЕ ФУНКЦИИ
[Перечисли от 3 до 5 основных функций, которые выполняет сервис и которые 
поясняют «ЧТО» продукт делает для пользователя в целом, его главные преимущества.]

## КЛЮЧЕВЫЕ ВОЗМОЖНОСТИ
[Основные технические возможности и особенности, которые поясняют «КАК» 
продукт это делает, конкретные инструменты и свойства, которые реализуют эти возможности.]

## ИНТЕГРАЦИИ
[С какими сервисами или системами взаимодействует]

## ЦЕЛЕВЫЕ ПОЛЬЗОВАТЕЛИ
[Кто использует этот сервис - клиенты банка, сотрудники банка, другие сервисы]

Будь кратким, но информативным. Избегай технических деталей реализации.
"""

    def __init__(self, max_tokens: int = 100000, max_pages: int = 100):
        """
        Args:
            max_tokens: Максимальное количество токенов для обработки
            max_pages: Максимальное количество страниц для обработки
        """
        self.max_tokens = max_tokens
        self.max_pages = max_pages
        # ИСПРАВЛЕНО: Убрали инициализацию LLM в конструкторе
        # self.llm = get_llm()  # <-- УДАЛЕНО!

    def generate_service_summary(
            self,
            parent_page_id: str,
            use_approved_only: bool = True,
            custom_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Генерирует саммари сервиса на основе дочерних страниц

        Args:
            parent_page_id: ID родительской страницы
            use_approved_only: Использовать только подтвержденные требования
            custom_prompt: Кастомный промпт для генерации саммари

        Returns:
            Словарь с результатами генерации саммари
        """
        logger.info("[ServiceSummaryService.generate_service_summary] <- parent_page_id=%s, approved_only=%s",
                    parent_page_id, use_approved_only)

        try:
            # 1. Получаем дочерние страницы
            child_page_ids = self._get_child_pages(parent_page_id)
            if not child_page_ids:
                return {
                    "success": False,
                    "error": "No child pages found",
                    "parent_page_id": parent_page_id,
                    "child_pages_count": 0
                }

            # 2. Собираем требования со страниц
            requirements_data = self._collect_requirements(child_page_ids, use_approved_only)
            if not requirements_data["valid_pages"]:
                return {
                    "success": False,
                    "error": "No valid requirements found in child pages",
                    "parent_page_id": parent_page_id,
                    "child_pages_count": len(child_page_ids),
                    "processing_stats": requirements_data["stats"]
                }

            # 3. Формируем текст требований
            combined_requirements = self._combine_requirements(requirements_data["valid_pages"])

            # 4. Проверяем лимит токенов
            requirements_tokens = count_tokens(combined_requirements)
            if requirements_tokens > self.max_tokens:
                combined_requirements = self._truncate_requirements(combined_requirements)
                requirements_tokens = count_tokens(combined_requirements)

            # 5. Генерируем саммари через LLM
            summary = self._generate_llm_summary(combined_requirements, custom_prompt)

            return {
                "success": True,
                "summary": summary,
                "parent_page_id": parent_page_id,
                "child_pages_count": len(child_page_ids),
                "processed_pages_count": len(requirements_data["valid_pages"]),
                "use_approved_only": use_approved_only,
                "requirements_tokens": requirements_tokens,
                "processing_stats": requirements_data["stats"],
                "page_details": [
                    {
                        "page_id": page["page_id"],
                        "title": page["title"],
                        "content_length": len(page["content"]),
                        "tokens": count_tokens(page["content"])
                    }
                    for page in requirements_data["valid_pages"]
                ]
            }

        except Exception as e:
            logger.error("[ServiceSummaryService.generate_service_summary] Error: %s", str(e))
            return {
                "success": False,
                "error": f"Service summary generation failed: {str(e)}",
                "parent_page_id": parent_page_id
            }

    def _get_child_pages(self, parent_page_id: str) -> List[str]:
        """Получает список дочерних страниц"""
        try:
            child_page_ids = get_child_page_ids(parent_page_id)
            logger.info("[ServiceSummaryService._get_child_pages] Found %d child pages", len(child_page_ids))
            return child_page_ids
        except Exception as e:
            logger.error("[ServiceSummaryService._get_child_pages] Error: %s", str(e))
            return []

    def _collect_requirements(self, page_ids: List[str], use_approved_only: bool) -> Dict[str, Any]:
        """Собирает требования со страниц с ограничением по количеству"""
        logger.info("[ServiceSummaryService._collect_requirements] Processing %d pages", len(page_ids))

        valid_pages = []
        stats = {
            "total_pages": len(page_ids),
            "processed_pages": 0,
            "skipped_no_content": 0,
            "skipped_token_limit": 0,
            "total_tokens": 0
        }

        # Ограничиваем количество страниц
        pages_to_process = page_ids[:self.max_pages]
        if len(page_ids) > self.max_pages:
            logger.warning("[ServiceSummaryService._collect_requirements] Limited processing to %d pages",
                           self.max_pages)

        current_tokens = 0

        for page_id in pages_to_process:
            try:
                page_data = get_page_data_cached(page_id)
                if not page_data:
                    stats["skipped_no_content"] += 1
                    continue

                # Выбираем тип содержимого
                if use_approved_only:
                    content = page_data['approved_content']
                else:
                    content = page_data['full_content']

                if not content or not content.strip():
                    stats["skipped_no_content"] += 1
                    continue

                # Проверяем токены
                page_tokens = count_tokens(content)
                if current_tokens + page_tokens > self.max_tokens:
                    logger.warning("[ServiceSummaryService._collect_requirements] Token limit reached at page %s",
                                   page_id)
                    stats["skipped_token_limit"] += 1
                    break

                valid_pages.append({
                    "page_id": page_id,
                    "title": page_data['title'],
                    "content": content.strip(),
                    "tokens": page_tokens
                })

                current_tokens += page_tokens
                stats["processed_pages"] += 1
                stats["total_tokens"] += page_tokens

            except Exception as e:
                logger.error("[ServiceSummaryService._collect_requirements] Error processing page %s: %s", page_id,
                             str(e))
                stats["skipped_no_content"] += 1

        logger.info("[ServiceSummaryService._collect_requirements] -> Processed %d/%d pages, %d tokens",
                    len(valid_pages), len(page_ids), stats["total_tokens"])

        return {
            "valid_pages": valid_pages,
            "stats": stats
        }

    def _combine_requirements(self, pages: List[Dict]) -> str:
        """Объединяет требования со страниц в единый текст"""
        logger.info("[ServiceSummaryService._combine_requirements] Combining %d pages", len(pages))

        sections = []
        for page in pages:
            section = f"=== {page['title']} ===\n{page['content']}\n"
            sections.append(section)

        combined = "\n".join(sections)
        logger.info("[ServiceSummaryService._combine_requirements] -> Combined text length: %d", len(combined))
        return combined

    def _truncate_requirements(self, requirements: str) -> str:
        """Обрезает требования до допустимого размера"""
        max_chars = self.max_tokens * 3  # Приблизительная оценка: 1 токен ≈ 3 символа
        if len(requirements) <= max_chars:
            return requirements

        truncated = requirements[:max_chars]
        # Ищем последнее завершенное предложение
        last_period = truncated.rfind('.')
        if last_period > max_chars * 0.8:
            truncated = truncated[:last_period + 1]

        truncated += "\n\n[... текст обрезан из-за ограничений токенов ...]"

        logger.warning("[ServiceSummaryService._truncate_requirements] Truncated from %d to %d chars",
                       len(requirements), len(truncated))
        return truncated

    def _generate_llm_summary(self, requirements: str, custom_prompt: Optional[str] = None) -> str:
        """Генерирует саммари с помощью LLM"""
        logger.info("[ServiceSummaryService._generate_llm_summary] Generating summary with LLM")

        # ИСПРАВЛЕНО: Получаем LLM при каждом вызове
        llm = get_llm()

        prompt_template = custom_prompt or self.DEFAULT_PROMPT

        # ИСПРАВЛЕНО: Создаем промпт и цепь LCEL
        prompt = PromptTemplate(
            input_variables=["requirements"],
            template=prompt_template
        )

        # ИСПОЛЬЗУЕМ LCEL: prompt | llm
        chain = prompt | llm

        try:
            # ИСПОЛЬЗУЕМ .invoke() вместо .run()
            response = chain.invoke({"requirements": requirements})
            summary = response.content

            logger.info("[ServiceSummaryService._generate_llm_summary] -> Summary generated, length: %d", len(summary))
            return summary.strip()
        except Exception as e:
            logger.error("[ServiceSummaryService._generate_llm_summary] Error: %s", str(e))
            raise Exception(f"Failed to generate summary: {str(e)}")