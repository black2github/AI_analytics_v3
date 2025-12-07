# tests/test_routes/test_service_summary.py

import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient


class TestServiceSummaryRoutes:

    @patch('app.routes.service_summary.get_page_title_by_id')
    @patch('app.routes.service_summary.get_child_page_ids')
    @patch('app.routes.service_summary.get_page_data_cached')
    @patch('app.routes.service_summary._generate_summary_with_llm')
    def test_generate_service_summary_success(self, mock_generate_summary, mock_get_page_data,
                                            mock_get_children, mock_get_title, app_client):
        """Тест успешной генерации саммари сервиса"""
        # Настройка моков
        mock_get_title.return_value = "Корпоративные карты"
        mock_get_children.return_value = ["child1", "child2"]
        mock_get_page_data.side_effect = [
            {
                'title': 'Требования к выпуску карт',
                'full_content': 'Детальные требования к выпуску корпоративных карт...',
                'approved_content': 'Основные требования...'
            },
            {
                'title': 'Процессы управления картами',
                'full_content': 'Описание процессов управления картами...',
                'approved_content': 'Процессы...'
            }
        ]
        mock_generate_summary.return_value = "Сервис корпоративных карт предназначен для управления выпуском и обслуживанием корпоративных карт..."

        response = app_client.post("/generate_service_summary", json={
            "parent_page_id": "123",
            "service_code": "CC"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["parent_page_id"] == "123"
        assert data["total_child_pages"] == 2
        assert data["processed_pages"] == 2
        assert "корпоративных карт" in data["summary"]

    @patch('app.routes.service_summary.get_child_page_ids')
    def test_generate_service_summary_no_children(self, mock_get_children, app_client):
        """Тест обработки случая без дочерних страниц"""
        mock_get_children.return_value = []

        response = app_client.post("/generate_service_summary", json={
            "parent_page_id": "123"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["total_child_pages"] == 0
        assert "No child pages found" in data["error"]

    @patch('app.routes.service_summary.get_page_title_by_id')
    @patch('app.routes.service_summary.get_child_page_ids')
    def test_generate_service_summary_get_endpoint(self, mock_get_children, mock_get_title, app_client):
        """Тест GET версии эндпоинта"""
        mock_get_title.return_value = "Test Service"
        mock_get_children.return_value = []

        response = app_client.get("/service_summary/123?include_colored=false&max_pages=10")

        assert response.status_code == 200
        data = response.json()
        assert data["parent_page_id"] == "123"

    def test_service_summary_health_check(self, app_client):
        """Тест health check эндпоинта"""
        response = app_client.get("/service_summary_health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "service_summary"
        assert len(data["endpoints"]) == 3