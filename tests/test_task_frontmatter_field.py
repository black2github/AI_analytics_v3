# tests/test_task_frontmatter_field.py
"""Пакет П2 ОНБ-В, п. 1 (замечание 44): поле `task` законно у типа task —
техбук conventions §5, блок схемы frontmatter («task: <JIRA-ID> # только task»)."""
from app.scripts.CI import selfcheck as sc


def test_task_template_header_silent():
    # шапка по шаблону канона _meta/templates/task.md
    fm = {"id": "T-ONBV-123", "type": "task", "task": "ONBV-123",
          "service": "onb-v", "created": "2026-11-07"}
    assert sc.frontmatter_schema_issues(fm) == ([], False)


def test_task_field_outside_task_type_warned():
    # срабатывание: поле только у task, у карточки функции — вне схемы
    bad, ver = sc.frontmatter_schema_issues({"id": "FUN-CL-01", "type": "function",
                                             "service": "x", "task": "ONBV-123"})
    assert bad == ["task"] and not ver


def test_created_still_only_task():
    # прежнее поле не расширено попутно
    bad, _ = sc.frontmatter_schema_issues({"id": "SCR-CL-01", "type": "screen-form",
                                           "service": "x", "created": "2026-11-07"})
    assert bad == ["created"]
