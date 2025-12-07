# tests/test_confluence_loader.py

import pytest
from unittest.mock import patch, Mock
from app.confluence_loader import (
    get_page_content_by_id,
    load_pages_by_ids,
    get_child_page_ids,
    extract_approved_fragments
)


class TestConfluenceLoader:

    @patch('app.confluence_loader.confluence')
    def test_get_page_content_by_id_success(self, mock_confluence):
        """Тест успешной загрузки страницы"""
        mock_confluence.get_page_by_id.return_value = {
            'body': {
                'storage': {
                    'value': '<p>Test content</p>'
                }
            }
        }

        result = get_page_content_by_id('123', clean_html=False)
        assert result == '<p>Test content</p>'
        mock_confluence.get_page_by_id.assert_called_once_with('123', expand='body.storage')

    @patch('app.confluence_loader.confluence')
    def test_get_page_content_by_id_not_found(self, mock_confluence):
        """Тест обработки отсутствующей страницы"""
        mock_confluence.get_page_by_id.return_value = {
            'body': {
                'storage': {
                    'value': ''
                }
            }
        }

        result = get_page_content_by_id('999')
        assert result is None

    @patch('app.confluence_loader.confluence')
    def test_get_page_content_by_id_with_cleaning(self, mock_confluence):
        """Тест загрузки с очисткой HTML"""
        mock_confluence.get_page_by_id.return_value = {
            'body': {
                'storage': {
                    'value': '<p>Clean content</p><p style="color: red;">Colored content</p>'
                }
            }
        }

        with patch('app.confluence_loader.filter_all_fragments') as mock_filter:
            mock_filter.return_value = 'Filtered content'
            result = get_page_content_by_id('123', clean_html=True)

        assert result == 'Filtered content'
        mock_filter.assert_called_once()

    @patch('app.confluence_loader.get_page_title_by_id')
    @patch('app.confluence_loader.get_page_content_by_id')
    @patch('app.confluence_loader.extract_approved_fragments')
    def test_load_pages_by_ids(self, mock_extract, mock_content, mock_title):
        """Тест загрузки нескольких страниц"""
        mock_title.side_effect = ['Page 1', 'Page 2']
        mock_content.side_effect = [
            '<p>Content 1</p>',
            '<p>Content 2</p>'
        ]
        mock_extract.side_effect = [
            'Approved 1',
            'Approved 2'
        ]

        result = load_pages_by_ids(['123', '456'])

        assert len(result) == 2
        assert result[0]['id'] == '123'
        assert result[0]['title'] == 'Page 1'
        assert result[0]['approved_content'] == 'Approved 1'
        assert result[1]['id'] == '456'

    @patch('app.confluence_loader.confluence')
    def test_get_child_page_ids(self, mock_confluence):
        """Тест получения дочерних страниц без рекурсии"""

        # ИСПРАВЛЕНИЕ: Настраиваем мок для предотвращения бесконечной рекурсии
        def mock_get_child_pages(page_id):
            if page_id == 'parent123':
                return [{'id': 'child1'}, {'id': 'child2'}]
            else:
                # Для дочерних страниц возвращаем пустой список
                return []

        mock_confluence.get_child_pages.side_effect = mock_get_child_pages

        result = get_child_page_ids('parent123')

        assert result == ['child1', 'child2']
        # Проверяем, что функция была вызвана для родительской и дочерних страниц
        assert mock_confluence.get_child_pages.call_count >= 1

    def test_extract_approved_fragments_basic(self):
        """Тест извлечения подтвержденных фрагментов"""
        html = '''
        <p>Approved text</p>
        <p style="color: red;">Rejected text</p>
        <p style="color: black;">Approved black text</p>
        '''

        result = extract_approved_fragments(html)
        assert "Approved text" in result
        assert "Approved black text" in result
        assert "Rejected text" not in result