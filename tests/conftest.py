# tests/conftest.py

import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from langchain_core.documents import Document

# Мокаем внешние зависимости до импорта приложения
@pytest.fixture(autouse=True)
def mock_external_dependencies():
    """Автоматически мокает все внешние зависимости для каждого теста"""
    with patch('app.config.OPENAI_API_KEY', 'test-key'), \
         patch('app.config.CONFLUENCE_BASE_URL', 'http://test-confluence.com'), \
         patch('app.config.CONFLUENCE_USER', 'test-user'), \
         patch('app.config.CONFLUENCE_PASSWORD', 'test-password'), \
         patch('app.config.CHROMA_PERSIST_DIR', '/tmp/test-chroma'):
        yield

@pytest.fixture
def mock_llm():
    """Мок LLM модели"""
    llm = Mock()
    llm.invoke.return_value = Mock(content='{"test_page_id": "Test analysis result"}')
    return llm

@pytest.fixture
def mock_embeddings():
    """Мок embedding модели"""
    embeddings = Mock()
    embeddings.embed_query.return_value = [0.1] * 384  # Размерность 384
    embeddings.embed_documents.return_value = [[0.1] * 384] * 3
    return embeddings

@pytest.fixture
def mock_vectorstore():
    """Мок векторного хранилища"""
    store = Mock()
    store.similarity_search.return_value = [
        Document(
            page_content="Test context document",
            metadata={"page_id": "123", "service_code": "test", "title": "Test Page"}
        )
    ]
    store.add_documents.return_value = None
    store.delete.return_value = None
    store.get.return_value = {'ids': ['id1', 'id2', 'id3']}
    return store

@pytest.fixture
def mock_confluence():
    """Мок Confluence API"""
    confluence = Mock()
    confluence.get_page_by_id.return_value = {
        'body': {
            'storage': {
                'value': '<p>Test page content</p>'
            }
        },
        'title': 'Test Page'
    }
    confluence.get_child_pages.return_value = [
        {'id': 'child1', 'title': 'Child Page 1'},
        {'id': 'child2', 'title': 'Child Page 2'}
    ]
    return confluence

@pytest.fixture
def app_client():
    """FastAPI тест клиент"""
    from app.main import app
    return TestClient(app)

@pytest.fixture
def temp_dir():
    """Временная директория для тестов"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def sample_services():
    """Тестовые данные сервисов"""
    return [
        {"code": "UAA", "name": "Authentication Service", "platform": True},
        {"code": "CC", "name": "Corporate Cards", "platform": False},
        {"code": "SBP", "name": "Fast Payment System", "platform": False}
    ]

@pytest.fixture
def sample_pages():
    """Тестовые данные страниц"""
    return [
        {
            "id": "12345",
            "title": "Test Requirements Page",
            "content": "<p>All content</p><p style='color: red;'>New requirement</p>",
            "approved_content": "<p>Approved content only</p>"
        },
        {
            "id": "67890",
            "title": "Another Page",
            "content": "<p>More content</p>",
            "approved_content": "<p>More approved content</p>"
        }
    ]