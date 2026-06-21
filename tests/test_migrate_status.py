# tests/test_migrate_status.py
#
# Проверяет логику frontmatter-статуса при миграции и точный признак
# неподтверждённого контента (has_unapproved).
#
# Правило статуса:
#   status = "draft" if (include_unapproved and has_unapproved) else "active"
# То есть "draft" появляется только когда миграция шла с --all
# (include_unapproved) И на странице реально есть неподтверждённые фрагменты.
# "active" = подтверждённый/живой документ (целевая схема: draft|review|active|deprecated).

import pytest
from unittest.mock import patch

from app.scripts.migrate_confluence_page import page_to_frontmatter
from app.confluence_loader import load_pages_by_ids


class TestMigrateStatus:
    """frontmatter status в зависимости от --all и наличия неподтверждённого."""

    def _status(self, **kwargs) -> str:
        page = {"id": "123", "title": "T", "requirement_type": "function"}
        fm = page_to_frontmatter(page, "CORP_CARDS", "DBOCORPESPLN", "corp-cards/x/t", **kwargs)
        return fm["status"]

    @pytest.mark.parametrize("include_unapproved,has_unapproved,expected", [
        (False, False, "active"),   # без --all
        (False, True,  "active"),   # без --all: пишется только подтверждённое, даже если на странице есть неподтверждённое
        (True,  False, "active"),   # --all, но неподтверждённого на странице нет → контент фактически подтверждён
        (True,  True,  "draft"),    # --all и есть неподтверждённое
    ])
    def test_status_matrix(self, include_unapproved, has_unapproved, expected):
        """Матрица: статус для всех комбинаций флагов."""
        assert self._status(
            include_unapproved=include_unapproved,
            has_unapproved=has_unapproved,
        ) == expected

    def test_status_defaults_backward_compatible(self):
        """Вызов без новых аргументов сохраняет прежнее поведение → active."""
        assert self._status() == "active"


class TestHasUnapprovedDetection:
    """load_pages_by_ids выставляет точный признак has_unapproved."""

    def _page_data(self, full_content, approved_content):
        return {
            "id": "123",
            "title": "T",
            "raw_html": "<p>x</p>",
            "full_content": full_content,
            "full_markdown": "# T",
            "approved_content": approved_content,
            "requirement_type": "function",
        }

    @patch("app.page_cache.get_page_data_cached")
    def test_has_unapproved_false_when_contents_equal(self, mock_get):
        """Нет цветных фрагментов → full == approved → has_unapproved=False."""
        mock_get.return_value = self._page_data("# T\nтекст", "# T\nтекст")
        pages = load_pages_by_ids(["123"])
        assert pages[0]["has_unapproved"] is False

    @patch("app.page_cache.get_page_data_cached")
    def test_has_unapproved_true_when_contents_differ(self, mock_get):
        """Есть неподтверждённое → full != approved → has_unapproved=True."""
        mock_get.return_value = self._page_data("# T\nтекст\nцветное", "# T\nтекст")
        pages = load_pages_by_ids(["123"])
        assert pages[0]["has_unapproved"] is True

    @patch("app.page_cache.get_page_data_cached")
    def test_has_unapproved_independent_of_include_unapproved(self, mock_get):
        """Признак считается из full vs approved и не зависит от выбора content_field."""
        mock_get.return_value = self._page_data("# T\nтекст\nцветное", "# T\nтекст")
        # include_unapproved меняет лишь записываемый content, но не диагноз
        pages_all = load_pages_by_ids(["123"], include_unapproved=True)
        pages_approved = load_pages_by_ids(["123"], include_unapproved=False)
        assert pages_all[0]["has_unapproved"] is True
        assert pages_approved[0]["has_unapproved"] is True
