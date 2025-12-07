# tests/test_rag_pipeline.py

import pytest
from unittest.mock import patch, Mock, MagicMock
from app.services.analysis_service import analyze_text, analyze_pages
from app.services.context_builder import build_context, _prepare_search_queries, _fast_deduplicate_documents, \
    build_context_optimized
from langchain_core.documents import Document


class TestRAGPipeline:

    @patch('app.rag_pipeline.get_embeddings_model')
    @patch('app.rag_pipeline.get_vectorstore')
    @patch('app.rag_pipeline.get_platform_services')
    def test_build_context_basic(self, mock_services, mock_vectorstore, mock_embeddings):
        """Тест базового построения контекста"""
        # Настройка моков
        mock_services.return_value = [
            {"code": "UAA", "name": "Auth Service", "platform": True}
        ]

        mock_store = Mock()
        mock_store.similarity_search.return_value = [
            Document(page_content="Test context", metadata={"page_id": "123"})
        ]
        mock_vectorstore.return_value = mock_store

        # result = build_context("CC", "test requirements", exclude_page_ids=["456"])
        result = build_context_optimized("CC", "test requirements", exclude_page_ids=["456"])

        assert isinstance(result, str)
        assert len(result) > 0

    @patch('app.rag_pipeline.extract_key_queries')
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

    @patch('app.rag_pipeline.build_chain')
    @patch('app.rag_pipeline.build_context')
    @patch('app.rag_pipeline.resolve_service_code_by_user')
    def test_analyze_text_success(self, mock_resolve, mock_context, mock_chain):
        """Тест успешного анализа текста"""
        mock_resolve.return_value = "CC"
        mock_context.return_value = "Test context"

        mock_llm_chain = Mock()
        mock_llm_chain.run.return_value = "Analysis result"
        mock_chain.return_value = mock_llm_chain

        result = analyze_text("Test requirements", service_code=None)

        assert result == "Analysis result"
        mock_llm_chain.run.assert_called_once_with({
            "requirement": "Test requirements",
            "context": "Test context"
        })

    @patch('app.rag_pipeline.get_page_content_by_id')
    @patch('app.rag_pipeline.resolve_service_code_from_pages_or_user')
    @patch('app.rag_pipeline.build_context')
    @patch('app.rag_pipeline.build_chain')
    def test_analyze_pages_success(self, mock_chain, mock_context, mock_resolve, mock_content):
        """Тест успешного анализа страниц"""
        mock_resolve.return_value = "CC"
        mock_content.return_value = "Page content"
        mock_context.return_value = "Test context"

        mock_llm_chain = Mock()
        mock_llm_chain.run.return_value = '{"123": "Analysis for page 123"}'
        mock_chain.return_value = mock_llm_chain

        with patch('app.rag_pipeline.count_tokens', return_value=100):
            result = analyze_pages(["123"])

        assert len(result) == 1
        assert result[0]["page_id"] == "123"
        assert result[0]["analysis"] == "Analysis for page 123"

    @patch('app.rag_pipeline.get_page_content_by_id')
    def test_analyze_pages_no_content(self, mock_content):
        """Тест анализа страниц без содержимого"""
        mock_content.return_value = None

        result = analyze_pages(["999"])
        assert result == []