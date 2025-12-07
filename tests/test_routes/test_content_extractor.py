# tests/test_routes/test_content_extractor.py

import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient


class TestContentExtractorRoutes:

    @patch('app.routes.content_extractor.get_page_title_by_id')
    @patch('app.routes.content_extractor.get_page_content_by_id')
    @patch('app.routes.content_extractor.filter_all_fragments')
    def test_extract_all_content_success(self, mock_filter_all, mock_get_content, mock_get_title, app_client):
        """Тест успешного извлечения полного контента"""
        mock_get_title.return_value = "Test Page"
        mock_get_content.return_value = "<p>Test HTML content</p>"
        mock_filter_all.return_value = "Test extracted content"

        response = app_client.post("/extract_all_content", json={
            "page_ids": ["123"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_pages"] == 1
        assert data["processed_pages"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["page_id"] == "123"
        assert data["pages"][0]["title"] == "Test Page"
        assert data["pages"][0]["content"] == "Test extracted content"

    @patch('app.routes.content_extractor.get_page_title_by_id')
    @patch('app.routes.content_extractor.get_page_content_by_id')
    @patch('app.routes.content_extractor.filter_approved_fragments')
    def test_extract_approved_content_success(self, mock_filter_approved, mock_get_content, mock_get_title, app_client):
        """Тест успешного извлечения подтвержденного контента"""
        mock_get_title.return_value = "Test Page"
        mock_get_content.return_value = '<p>Approved text</p><p style="color: red;">New text</p>'
        mock_filter_approved.return_value = "Approved text"

        response = app_client.post("/extract_approved_content", json={
            "page_ids": ["123"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_pages"] == 1
        assert data["processed_pages"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["content"] == "Approved text"

    @patch('app.routes.content_extractor.get_page_content_by_id')
    def test_extract_content_page_not_found(self, mock_get_content, app_client):
        """Тест обработки отсутствующей страницы"""
        mock_get_content.return_value = None

        response = app_client.post("/extract_all_content", json={
            "page_ids": ["999"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["processed_pages"] == 0
        assert data["pages"][0]["error"] == "Page content not found or empty"

    def test_extract_content_empty_request(self, app_client):
        """Тест пустого запроса"""
        response = app_client.post("/extract_all_content", json={
            "page_ids": []
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["total_pages"] == 0
        assert data["processed_pages"] == 0

    @patch('app.routes.content_extractor.get_page_title_by_id')
    @patch('app.routes.content_extractor.get_page_content_by_id')
    @patch('app.routes.content_extractor.filter_all_fragments')
    def test_extract_multiple_pages(self, mock_filter_all, mock_get_content, mock_get_title, app_client):
        """Тест извлечения контента с нескольких страниц"""
        mock_get_title.side_effect = ["Page 1", "Page 2"]
        mock_get_content.side_effect = ["<p>Content 1</p>", "<p>Content 2</p>"]
        mock_filter_all.side_effect = ["Extracted 1", "Extracted 2"]

        response = app_client.post("/extract_all_content", json={
            "page_ids": ["123", "456"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_pages"] == 2
        assert data["processed_pages"] == 2
        assert len(data["pages"]) == 2

    def test_extract_health_check(self, app_client):
        """Тест health check эндпоинта"""
        response = app_client.get("/extract_health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "content_extractor"
        assert len(data["endpoints"]) == 3