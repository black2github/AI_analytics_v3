# tests/test_routes/test_analyze_external.py

import pytest
from unittest.mock import patch, MagicMock


class TestAnalyzeExternalRoutes:
    """Тесты для эндпоинта /analyze_external_pages"""

    @patch('app.routes.analyze_external.process_and_cache_external_pages')
    @patch('app.routes.analyze_external.analyze_pages')
    def test_analyze_external_pages_success(self, mock_analyze, mock_cache, app_client):
        """Тест успешного анализа внешних страниц"""
        # Настраиваем моки
        mock_cache.return_value = {
            'total': 2,
            'cached': 2,
            'failed': 0,
            'failed_pages': []
        }

        mock_analyze.return_value = [
            {
                "page_id": "123",
                "analysis": "Analysis result 1",
                "token_usage": {
                    "prompt": 1000,
                    "requirements": 2000,
                    "context": 3000,
                    "total_input": 6000,
                    "limit": 128000,
                    "usage_percent": 4.7
                }
            },
            {
                "page_id": "456",
                "analysis": "Analysis result 2",
                "token_usage": {
                    "prompt": 1000,
                    "requirements": 2000,
                    "context": 3000,
                    "total_input": 6000,
                    "limit": 128000,
                    "usage_percent": 4.7
                }
            }
        ]

        # Выполняем запрос
        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "Test Page 1",
                    "content": "<html><body><p>Test content 1</p></body></html>"
                },
                {
                    "page_id": "456",
                    "title": "Test Page 2",
                    "content": "<html><body><p>Test content 2</p></body></html>"
                }
            ],
            "service_code": "TEST"
        })

        # Проверяем результат
        assert response.status_code == 200
        data = response.json()

        # Проверяем структуру ответа
        assert "results" in data
        assert "cache_info" in data

        # Проверяем результаты анализа
        assert len(data["results"]) == 2
        assert data["results"][0]["page_id"] == "123"
        assert data["results"][1]["page_id"] == "456"

        # Проверяем информацию о кеше
        assert data["cache_info"]["total_pages"] == 2
        assert data["cache_info"]["cached_pages"] == 2
        assert data["cache_info"]["failed_pages_count"] == 0

        # Проверяем вызовы моков
        mock_cache.assert_called_once()
        mock_analyze.assert_called_once()

    @patch('app.routes.analyze_external.process_and_cache_external_pages')
    @patch('app.routes.analyze_external.analyze_pages')
    def test_analyze_external_pages_with_templates(self, mock_analyze, mock_cache, app_client):
        """Тест анализа с проверкой шаблонов"""
        mock_cache.return_value = {
            'total': 1,
            'cached': 1,
            'failed': 0,
            'failed_pages': []
        }

        mock_analyze.return_value = [
            {
                "page_id": "123",
                "analysis": "Template analysis",
                "template_analysis": {
                    "template_compliance": {"score": 0.85},
                    "recommendations": ["Add more details"],
                    "summary": "Good compliance"
                }
            }
        ]

        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "[Process] Test Process",
                    "content": "<html><body><h1>Process</h1></body></html>"
                }
            ],
            "service_code": "TEST",
            "check_templates": True
        })

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["template_analysis"] is not None

    @patch('app.routes.analyze_external.process_and_cache_external_pages')
    def test_analyze_external_pages_partial_failure(self, mock_cache, app_client):
        """Тест частичной неудачи кеширования"""
        # Одна страница закеширована, одна - нет
        mock_cache.return_value = {
            'total': 2,
            'cached': 1,
            'failed': 1,
            'failed_pages': [
                {
                    'page_id': '456',
                    'error': 'Invalid HTML structure'
                }
            ]
        }

        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "Valid Page",
                    "content": "<html><body><p>Valid</p></body></html>"
                },
                {
                    "page_id": "456",
                    "title": "Invalid Page",
                    "content": "<html><invalid>"
                }
            ],
            "service_code": "TEST"
        })

        assert response.status_code == 200
        data = response.json()

        # Проверяем информацию о неудачных страницах
        assert data["cache_info"]["failed_pages_count"] == 1
        assert "failed_pages_details" in data["cache_info"]
        assert len(data["cache_info"]["failed_pages_details"]) == 1
        assert data["cache_info"]["failed_pages_details"][0]["page_id"] == "456"

    @patch('app.routes.analyze_external.process_and_cache_external_pages')
    def test_analyze_external_pages_total_failure(self, mock_cache, app_client):
        """Тест полной неудачи кеширования"""
        # Ни одна страница не закеширована
        mock_cache.return_value = {
            'total': 2,
            'cached': 0,
            'failed': 2,
            'failed_pages': [
                {'page_id': '123', 'error': 'Error 1'},
                {'page_id': '456', 'error': 'Error 2'}
            ]
        }

        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "Page 1",
                    "content": "<html><body>Content 1</body></html>"
                },
                {
                    "page_id": "456",
                    "title": "Page 2",
                    "content": "<html><body>Content 2</body></html>"
                }
            ],
            "service_code": "TEST"
        })

        # Возвращается HTTP 200 с полем error
        assert response.status_code == 200
        data = response.json()

        assert "error" in data
        assert data["error"] == "Failed to cache any pages"
        assert data["total_pages"] == 2
        assert len(data["failed_pages"]) == 2

    def test_analyze_external_pages_validation_empty_page_id(self, app_client):
        """Тест валидации: пустой page_id"""
        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "",  # Пустой page_id
                    "title": "Test",
                    "content": "<html><body>Test</body></html>"
                }
            ]
        })

        # Единый подход - HTTP 200 с полем error
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "Validation error" in data["error"]
        assert "page_id" in data["error"]

    def test_analyze_external_pages_validation_non_numeric_page_id(self, app_client):
        """Тест валидации: не числовой page_id"""
        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "abc123",  # Не числовой
                    "title": "Test",
                    "content": "<html><body>Test</body></html>"
                }
            ]
        })

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "числовой строкой" in data["error"]

    def test_analyze_external_pages_validation_empty_title(self, app_client):
        """Тест валидации: пустой title"""
        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "",  # Пустой title
                    "content": "<html><body>Test</body></html>"
                }
            ]
        })

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "title" in data["error"]

    def test_analyze_external_pages_validation_empty_content(self, app_client):
        """Тест валидации: пустой content"""
        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "Test",
                    "content": ""  # Пустой content
                }
            ]
        })

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "content" in data["error"]

    def test_analyze_external_pages_validation_empty_pages_list(self, app_client):
        """Тест валидации: пустой список pages"""
        response = app_client.post("/analyze_external_pages", json={
            "pages": []  # Пустой список
        })

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "pages" in data["error"]

    def test_analyze_external_pages_validation_invalid_json(self, app_client):
        """Тест валидации: невалидный JSON"""
        response = app_client.post(
            "/analyze_external_pages",
            data="invalid json{",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "Invalid JSON" in data["error"]

    def test_analyze_external_pages_validation_missing_required_field(self, app_client):
        """Тест валидации: отсутствует обязательное поле"""
        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    # Отсутствует title
                    "content": "<html><body>Test</body></html>"
                }
            ]
        })

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "Validation error" in data["error"]

    @patch('app.routes.analyze_external.process_and_cache_external_pages')
    @patch('app.routes.analyze_external.analyze_pages')
    def test_analyze_external_pages_with_custom_prompt(self, mock_analyze, mock_cache, app_client):
        """Тест с кастомным промптом"""
        mock_cache.return_value = {
            'total': 1,
            'cached': 1,
            'failed': 0,
            'failed_pages': []
        }

        mock_analyze.return_value = [
            {"page_id": "123", "analysis": "Custom analysis"}
        ]

        custom_prompt = "Analyze this requirement: {requirement}\nContext: {context}"

        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "Test",
                    "content": "<html><body>Test</body></html>"
                }
            ],
            "service_code": "TEST",
            "prompt_template": custom_prompt
        })

        assert response.status_code == 200
        data = response.json()
        assert "results" in data

        # Проверяем, что custom prompt был передан в analyze_pages
        call_args = mock_analyze.call_args
        assert call_args[0][1] == custom_prompt  # Второй аргумент - prompt_template

    @patch('app.routes.analyze_external.process_and_cache_external_pages')
    @patch('app.routes.analyze_external.analyze_pages')
    def test_analyze_external_pages_unexpected_error(self, mock_analyze, mock_cache, app_client):
        """Тест обработки неожиданной ошибки"""
        mock_cache.return_value = {
            'total': 1,
            'cached': 1,
            'failed': 0,
            'failed_pages': []
        }

        # Симулируем неожиданную ошибку в analyze_pages
        mock_analyze.side_effect = RuntimeError("Unexpected error")

        response = app_client.post("/analyze_external_pages", json={
            "pages": [
                {
                    "page_id": "123",
                    "title": "Test",
                    "content": "<html><body>Test</body></html>"
                }
            ],
            "service_code": "TEST"
        })

        # Единый подход - HTTP 200 с полем error
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "Unexpected error" in data["error"]


class TestPageCacheFunctions:
    """Тесты для функций в page_cache.py"""

    @patch('app.page_cache.filter_all_fragments')
    @patch('app.page_cache.markdownify.markdownify')
    @patch('app.page_cache.analyze_content_template_type')
    def test_process_and_cache_external_page_success(
            self, mock_analyze_type, mock_markdownify, mock_filter, app_client
    ):
        """Тест успешной обработки и кеширования страницы"""
        from app.page_cache import process_and_cache_external_page

        # Настраиваем моки
        mock_filter.return_value = "Filtered content"
        mock_markdownify.return_value = "# Markdown content"
        mock_analyze_type.return_value = "process"

        # Выполняем функцию
        result = process_and_cache_external_page(
            page_id="123",
            title="Test Page",
            raw_html="<html><body><p>Test</p></body></html>"
        )

        # Проверяем результат
        assert result['success'] is True
        assert result['page_id'] == "123"
        assert result['error'] is None

    @patch('app.page_cache.filter_all_fragments')
    def test_process_and_cache_external_page_error(self, mock_filter, app_client):
        """Тест обработки ошибки при кешировании"""
        from app.page_cache import process_and_cache_external_page

        # Симулируем ошибку
        mock_filter.side_effect = ValueError("Processing error")

        result = process_and_cache_external_page(
            page_id="123",
            title="Test",
            raw_html="<html><body>Test</body></html>"
        )

        # Проверяем, что ошибка обработана корректно
        assert result['success'] is False
        assert result['page_id'] == "123"
        assert "Error processing page" in result['error']

    def test_process_and_cache_external_pages_mixed_results(self, app_client):
        """Тест обработки смешанных результатов"""
        from app.page_cache import process_and_cache_external_pages

        pages = [
            {
                'page_id': '123',
                'title': 'Valid Page',
                'content': '<html><body><p>Valid</p></body></html>'
            },
            {
                'page_id': '456',
                'title': 'Missing Content',
                'content': None  # Невалидные данные
            },
            {
                'page_id': '789',
                'title': 'Another Valid',
                'content': '<html><body><p>Valid</p></body></html>'
            }
        ]

        result = process_and_cache_external_pages(pages)

        # Проверяем статистику
        assert result['total'] == 3
        assert result['cached'] >= 1  # Минимум одна успешная
        assert result['failed'] >= 1  # Минимум одна неудачная
        assert len(result['failed_pages']) >= 1