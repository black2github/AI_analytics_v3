# tests/test_routes/test_analyze.py

import pytest
from unittest.mock import patch


class TestAnalyzeRoutes:

    @patch('app.routes.analyze.analyze_text')
    def test_analyze_from_text_success(self, mock_analyze, app_client):
        """Тест анализа текстовых требований"""
        mock_analyze.return_value = "Analysis result"

        response = app_client.post("/analyze", json={
            "text": "Test requirements text",
            "service_code": "CC"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == "Analysis result"

    @patch('app.routes.analyze.analyze_pages')
    def test_analyze_service_pages_success(self, mock_analyze, app_client):
        """Тест анализа страниц сервиса"""
        mock_analyze.return_value = [
            {"page_id": "123", "analysis": "Page analysis"}
        ]

        response = app_client.post("/analyze_pages", json={
            "page_ids": ["123"],
            "service_code": "CC"
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["page_id"] == "123"

    @patch('app.routes.analyze.analyze_with_templates')
    def test_analyze_with_templates_success(self, mock_analyze, app_client):
        """Тест анализа с шаблонами"""
        mock_analyze.return_value = [
            {
                "page_id": "123",
                "requirement_type": "process",
                "analysis": "Template analysis",
                "formatting_issues": []
            }
        ]

        response = app_client.post("/analyze_with_templates", json={
            "items": [{"requirement_type": "process", "page_id": "123"}],
            "service_code": "CC"
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["requirement_type"] == "process"