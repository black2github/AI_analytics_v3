# tests/test_rag_pipeline.py
#
# Подмены нацелены на модуль, где имя ищется при вызове: код переехал из app/rag_pipeline.py в
# app/services/context_builder.py и app/services/analysis_service.py, которые берут имена своими
# импортами — подмена в app.rag_pipeline на них не действует (2026-10-28). Тест не ходит ни в
# Confluence, ни к LLM, ни в векторное хранилище.

import pytest
from unittest.mock import patch, Mock, MagicMock
from app.services.analysis_service import analyze_text, analyze_pages
from app.services.context_builder import _prepare_search_queries, _fast_deduplicate_documents, \
    build_context_optimized
from langchain_core.documents import Document

_CB = "app.services.context_builder"
_AS = "app.services.analysis_service"


class TestRAGPipeline:

    @patch(f'{_CB}.get_template_name_by_type', return_value="Функция")
    @patch(f'{_CB}.count_tokens', return_value=10)
    @patch(f'{_CB}.unified_service_search')
    @patch(f'{_CB}.extract_entity_attribute_queries', return_value=[])
    @patch(f'{_CB}.extract_key_queries', return_value=["query1"])
    @patch(f'{_CB}.get_bool_env', side_effect=lambda name: name == "IS_SERVICE_DOCS_CONTEXT")
    @patch(f'{_CB}.get_embeddings_model')
    def test_build_context_basic(self, mock_embeddings, mock_env, mock_keys, mock_entity,
                                 mock_search, mock_tokens, mock_type):
        """Тест базового построения контекста: документ сервиса попадает в контекст с заголовком"""
        mock_search.return_value = [
            Document(page_content="Test context", metadata={"page_id": "123", "title": "Т"})
        ]

        result = build_context_optimized("CC", "test requirements", exclude_page_ids=["456"])

        assert "Test context" in result
        assert "title: Т" in result
        kw = mock_search.call_args.kwargs
        assert kw["service_code"] == "CC" and kw["exclude_page_ids"] == ["456"]
        assert kw["queries"] == ["query1"]

    @patch(f'{_CB}.extract_key_queries')
    def test_prepare_search_queries_with_text(self, mock_extract):
        """Тест подготовки поисковых запросов с текстом"""
        mock_extract.return_value = ["query1", "query2", "query3"]

        result = _prepare_search_queries("Sample requirements text")

        assert result == ["query1", "query2", "query3"]
        mock_extract.assert_called_once_with("Sample requirements text")

    def test_prepare_search_queries_empty_text(self):
        """Тест подготовки поисковых запросов с пустым текстом"""
        result = _prepare_search_queries("")
        assert result == [""]

    def test_fast_deduplicate_documents(self):
        """Тест быстрой дедупликации документов"""
        docs = [
            Document(page_content="Same content", metadata={"page_id": "123"}),
            Document(page_content="Same content", metadata={"page_id": "123"}),  # Дубликат
            Document(page_content="Different content", metadata={"page_id": "456"}),
        ]

        result = _fast_deduplicate_documents(docs)

        assert len(result) == 2
        assert result[0].metadata["page_id"] == "123"
        assert result[1].metadata["page_id"] == "456"

    @patch(f'{_AS}.build_chain')
    @patch(f'{_AS}.build_context_optimized')
    @patch(f'{_AS}.resolve_service_code_by_user')
    def test_analyze_text_success(self, mock_resolve, mock_context, mock_chain):
        """Тест успешного анализа текста (цепочка LCEL: invoke вместо run)"""
        mock_resolve.return_value = "CC"
        mock_context.return_value = "Test context"

        mock_llm_chain = Mock()
        mock_llm_chain.invoke.return_value = "Analysis result"
        mock_chain.return_value = mock_llm_chain

        result = analyze_text("Test requirements", service_code=None)

        assert result == "Analysis result"
        mock_context.assert_called_once_with("CC", requirements_text="Test requirements")
        mock_llm_chain.invoke.assert_called_once_with({
            "requirement": "Test requirements",
            "context": "Test context"
        })

    # страница — через кеш app.page_cache (импорт внутри analyze_pages), тип — через
    # template_type_analysis (тоже внутри); промпт передаётся явно, файл промпта не читается
    @patch('app.services.template_type_analysis.get_template_name_by_type', return_value="Функция")
    @patch('app.page_cache.get_page_data_cached')
    @patch(f'{_AS}.count_tokens', return_value=100)
    @patch(f'{_AS}.resolve_service_code_from_pages_or_user')
    @patch(f'{_AS}.build_context_optimized')
    @patch(f'{_AS}.build_chain')
    def test_analyze_pages_success(self, mock_chain, mock_context, mock_resolve, mock_tokens,
                                   mock_page, mock_type):
        """Тест успешного анализа страниц"""
        mock_resolve.return_value = "CC"
        mock_page.return_value = {"full_content": "Page content", "title": "Страница",
                                  "requirement_type": "function"}
        mock_context.return_value = "Test context"

        mock_llm_chain = Mock()
        mock_llm_chain.invoke.return_value = '{"123": "Analysis for page 123"}'
        mock_chain.return_value = mock_llm_chain

        result = analyze_pages(["123"], prompt_template="Промпт")

        assert len(result) == 1
        assert result[0]["page_id"] == "123"
        assert result[0]["analysis"] == "Analysis for page 123"
        assert mock_context.call_args.kwargs["exclude_page_ids"] == ["123"]

    @patch('app.page_cache.get_page_data_cached', return_value=None)
    @patch(f'{_AS}.resolve_service_code_from_pages_or_user', return_value="CC")
    @patch(f'{_AS}.build_chain')
    def test_analyze_pages_no_content(self, mock_chain, mock_resolve, mock_page):
        """Тест анализа страниц без содержимого: пустой результат, LLM не вызывается"""
        result = analyze_pages(["999"], prompt_template="Промпт")
        assert result == []
        mock_chain.assert_not_called()
