"""Сверка выпущенных маркеров с переписью цветов (версия 1.9.18).

Перепись считает цвета HTML, apply/reject работают с маркерами. «UNKNOWN 0» в отчёте
обязано значить, что таких маркеров на страницах прогона нет (архив КК 05.11:
UNKNOWN-ff0000 в маркере при нуле в отчёте).
"""
from types import SimpleNamespace

import pytest

from app.scripts.CI.critic import collect_task_occurrences, count_task_markers
from app.scripts.migrate_colors import (finalize, new_accumulator, reconcile_page_markers,
                                        render_report_md)


def _result(color_to_task=None, unresolved=()):
    return SimpleNamespace(color_to_task=color_to_task or {},
                           unresolved_jira=[{"color": c} for c in unresolved],
                           confidence={})


def _survey(**tasks):
    return {color: {"task": task, "classification": "task", "count": 1}
            for color, task in tasks.items()}


def _report(acc):
    return finalize(acc, "svc", "2026-11-06")


class TestCountTaskMarkers:
    def test_counts_every_notation(self):
        text = ('{++GBO-1: a++} {--GBO-1: b--} {~~GBO-2: c~>d~~}\n\n'
                '<span class="critic-ins" data-task="GBO-3">e</span>'
                '<span class="critic-del" data-task="UNKNOWN-ff0000">f</span>\n\n'
                '| x | status |\n|---|---|\n| y | +GBO-4 |\n')
        assert count_task_markers(text) == {
            "GBO-1": 2, "GBO-2": 1, "GBO-3": 1, "UNKNOWN-ff0000": 1, "GBO-4": 1}

    def test_markers_in_code_block_not_counted(self):
        assert count_task_markers("```\n{++GBO-1: a++}\n```\n\n{++GBO-2: b++}\n") == {"GBO-2": 1}

    def test_collect_occurrences_unchanged(self):
        """Общий обход не изменил отчёт `list`: строки, а не вхождения."""
        text = "{++GBO-1: a++} {++GBO-1: b++}\n```\n{++GBO-2: c++}\n```\n{--GBO-3: d--}\n"
        assert collect_task_occurrences(text) == {"GBO-1": [1], "GBO-3": [5]}


class TestReconcile:
    def test_unknown_missing_from_survey_is_reported(self):
        """Главный случай: цвет размечен экстрактором, перепись его не видит."""
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(), _survey(),
                               '<span class="critic-ins" data-task="UNKNOWN-ff0000">текст</span>')
        manifest, report = _report(acc)
        assert report["unresolved_placeholders"] == [{
            "placeholder": "UNKNOWN-ff0000", "color": "#ff0000", "page": "P", "count": 1,
            "reason": "not-in-history", "source": "markers"}]
        assert manifest["tasks"]["UNKNOWN-ff0000"]["pages"] == ["P"]
        assert manifest["tasks"]["UNKNOWN-ff0000"]["confidence"] == "unresolved"
        row = report["color_summary"][0]
        assert (row["color"], row["classification"], row["source"]) == ("#ff0000", "unknown", "markers")
        assert report["stats"]["marker_mismatches"] == 1
        assert report["stats"]["positions_manual_review"] == 1  # без двойного счёта

    @pytest.mark.parametrize("unresolved, nested, reason", [
        (["#ff0000"], [], "jira-unresolved"),
        (["#ff0000"], ["UNKNOWN-ff0000"], "jira-unresolved"),
        ([], ["UNKNOWN-ff0000"], "nested-only"),
        ([], [], "not-in-history"),
    ])
    def test_unknown_reason(self, unresolved, nested, reason):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(unresolved=unresolved), _survey(),
                               "{++UNKNOWN-ff0000: a++}", nested_tasks=nested)
        assert acc["unresolved_placeholders"][0]["reason"] == reason

    def test_known_task_missing_from_survey_is_mismatch_with_map_color(self):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result({"#00ff00": "GBO-1"}), _survey(),
                               "{++GBO-1: a++} {++GBO-1: b++}")
        manifest, report = _report(acc)
        assert report["unresolved_placeholders"] == []
        assert report["marker_mismatch"] == [{"page": "P", "task": "GBO-1", "color": "#00ff00",
                                              "count": 2, "reason": None}]
        assert manifest["tasks"]["GBO-1"]["markers"] == 2
        assert report["stats"]["positions_manual_review"] == 1
        assert report["color_summary"][0]["classification"] == "task"

    def test_task_outside_map_has_empty_color_and_renders(self):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(), _survey(), "{++GBO-9: a++}")
        _, report = _report(acc)
        assert report["marker_mismatch"][0]["color"] == ""
        assert "`GBO-9` на «P» ×1" in render_report_md(report)

    # --- Несрабатывание: шум в отчёте не должен заслонять настоящие расхождения ---

    def test_task_present_in_survey_is_not_mismatch(self):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(), _survey(**{"#00ff00": "GBO-1"}), "{++GBO-1: a++}")
        _, report = _report(acc)
        assert report["marker_mismatch"] == []
        assert report["color_summary"] == []
        assert report["stats"]["markers_total"] == 1

    def test_unknown_present_in_survey_is_not_duplicated(self):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(), _survey(**{"#ff0000": "UNKNOWN-ff0000"}),
                               "{++UNKNOWN-ff0000: a++}")
        assert acc["unresolved_placeholders"] == []
        assert acc["marker_mismatch"] == []

    def test_forced_wrap_is_separate_number_not_mismatch(self):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(), _survey(), "{++GBO-7: a++}\n\n{++GBO-7: b++}",
                               forced_task="GBO-7")
        _, report = _report(acc)
        assert report["marker_mismatch"] == []
        assert report["stats"]["markers_total"] == 2
        assert report["stats"]["markers_forced"] == 2

    def test_page_without_markers_changes_nothing(self):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(), _survey(), "чистый текст")
        _, report = _report(acc)
        assert report["stats"]["marker_pages"] == 1
        assert report["stats"]["markers_total"] == 0
        assert report["stats"]["positions_manual_review"] == 0


class TestWiring:
    """Сверка подключена к обоим путям выпуска маркеров, считает итоговый markdown."""

    FORCED_HTML = ("<h2>История изменений</h2><table><tbody>"
                   "<tr><th>Дата</th><th>Описание</th><th>Задача в Jira</th></tr>"
                   "<tr><td>01.01.2026</td><td>Создание</td><td>GBO-777</td></tr>"
                   "</tbody></table><p>Чёрный текст страницы</p>")

    def test_tree_export_counts_forced_wrap_separately(self, monkeypatch):
        import app.config as cfg
        from app.scripts.migrate_confluence_tree import _resolve_page_content
        monkeypatch.setattr(cfg, "UNAPPROVED_JIRA_IDS", {"GBO-777"})
        acc = new_accumulator()
        content = _resolve_page_content({"raw_html": self.FORCED_HTML}, False, True, acc, "P")
        assert "{++GBO-777:" in content
        stats = _report(acc)[1]["stats"]
        assert (stats["markers_total"], stats["markers_forced"], stats["marker_mismatches"]) == (1, 1, 0)

    def test_migrate_pages_counts_written_markers(self, tmp_path):
        from app.scripts.migrate_colors import migrate_pages
        html = ('<h2>История изменений</h2><table><tbody>'
                '<tr><th>Дата</th><th>Описание</th><th>Задача в Jira</th></tr>'
                '<tr><td>01.01.2026</td><td><span style="color: rgb(0,128,0);">Правка</span></td>'
                '<td>GBO-5</td></tr></tbody></table>'
                '<p>Чёрный <span style="color: rgb(0,128,0);">зелёный</span></p>')
        _, report = migrate_pages([("P", html)], "svc", "2026-11-06", tmp_path)
        written = count_task_markers((tmp_path / "P.md").read_text(encoding="utf-8"))
        assert written == {"GBO-5": 1}
        assert report["stats"]["markers_total"] == 1
        assert report["stats"]["marker_mismatches"] == 0


class TestReportLine:
    def test_line_with_numbers(self):
        acc = new_accumulator()
        reconcile_page_markers(acc, "P", _result(), _survey(),
                               "{++GBO-7: a++} {++UNKNOWN-ff0000: b++}", forced_task="GBO-7")
        md = render_report_md(_report(acc)[1])
        assert ("- Маркеров в архиве: 2 по 2 задачам (из них форс-обёртка --unapproved-jira: 1), "
                "расхождений с переписью: 1") in md
        assert "## Маркеры задач, которых нет в переписи цветов страницы (1)" in md

    def test_no_line_when_markers_not_checked(self):
        """Команда report маркеры не выпускает: «0 маркеров» было бы ложным нулём."""
        md = render_report_md(_report(new_accumulator())[1])
        assert "Маркеров в архиве" not in md
