# tests/test_forced_unapproved_origin.py
#
# Форс-режим страницы по списку --unapproved-jira (решение владельца 2026-09-30).
#
# Было: любая ЧЁРНАЯ строка истории с задачей из списка замораживала страницу
# целиком. Задача из списка в середине истории чужой страницы (страница давно в
# ПРОМ, задача внесла в неё чёрную правку) давала тот же результат: reject-all
# оставлял от страницы один frontmatter — молчаливая потеря требований.
#
# Стало: страница замораживается, только если задача из списка стоит в ПЕРВОЙ
# по дате записи истории и эта запись чёрная, то есть страница создана этой
# задачей. Во всех остальных случаях форса нет, а случай уходит в отчёт.
#
# Каждое правило — парой: срабатывание и НЕсрабатывание.

from app.color_map import decide_forced_unapproved, find_forced_unapproved
from app.scripts.migrate_colors import (finalize, new_accumulator,
                                        render_report_md)

ORANGE = "rgb(255,102,0)"
HEADERS = ("Дата", "Описание", "Автор", "Задача в JIRA")


def _hist(rows):
    thead = "".join(f"<th>{h}</th>" for h in HEADERS)
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{rows}</tbody></table>"


def _row(date_iso, color, jira, dated=True):
    """Строка истории; date_iso = 'YYYY-MM-DD'; dated=False — ячейка даты пустая."""
    if dated:
        y, m, d = date_iso.split("-")
        date_cell = f'<time datetime="{date_iso}">{d}.{m}.{y}</time>'
    else:
        date_cell = "уточняется"
    desc = (f'<span style="color: {color}">описание</span>' if color
            else "<span>описание</span>")
    return (f"<tr><td>{date_cell}</td><td>{desc}</td><td>автор</td>"
            f"<td>{jira}</td></tr>")


def _kinds(decision):
    return [n["kind"] for n in decision.notes]


class TestOriginRule:
    """Основное правило: задача из списка — в первой по дате чёрной записи."""

    def test_task_first_forces(self):
        html = _hist(_row("2024-03-05", None, "GBO-50")
                     + _row("2025-06-01", ORANGE, "GBO-77"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced and d.forced.task == "GBO-50"
        assert d.forced.first_seen == (2024, 3, 5)
        assert d.notes == []

    def test_task_in_the_middle_does_not_force(self):
        # тот самый случай потери: страница создана GBO-1 (в ПРОМ), GBO-50
        # внесла чёрную правку позже
        html = _hist(_row("2023-01-10", None, "GBO-1")
                     + _row("2024-03-05", None, "GBO-50")
                     + _row("2025-06-01", ORANGE, "GBO-77"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None
        assert d.notes == [{"kind": "задача из списка не в первой записи истории",
                            "tasks": ["GBO-50"]}]
        assert find_forced_unapproved(html, {"GBO-50"}) is None

    def test_order_of_rows_does_not_matter_when_all_dated(self):
        # история «новые сверху»: первая по дате запись — последняя в таблице
        html = _hist(_row("2025-06-01", ORANGE, "GBO-77")
                     + _row("2024-03-05", None, "GBO-1")
                     + _row("2023-01-10", None, "GBO-50"))
        assert decide_forced_unapproved(html, {"GBO-50"}).forced.task == "GBO-50"
        assert decide_forced_unapproved(html, {"GBO-1"}).forced is None

    def test_no_list_task_in_history_is_silent(self):
        # НЕсрабатывание отчёта: задачи из списка в истории нет — ни форса, ни шума
        html = _hist(_row("2023-01-10", None, "GBO-1")
                     + _row("2024-03-05", None, "GBO-2"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None and d.notes == []

    def test_colored_row_with_list_task_is_silent(self):
        # цветная строка с задачей из списка — дело карты цветов, не форса
        html = _hist(_row("2023-01-10", None, "GBO-1")
                     + _row("2024-03-05", ORANGE, "GBO-50"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None and d.notes == []


class TestSameDate:
    """Край 1 и оговорка про цветные строки той же даты."""

    def test_colored_row_same_date_does_not_block_force(self):
        # требования под цветом добавлены позже, пусть и в тот же день
        html = _hist(_row("2024-03-05", None, "GBO-50")
                     + _row("2024-03-05", ORANGE, "GBO-77"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced and d.forced.task == "GBO-50" and d.notes == []

    def test_black_row_same_date_not_in_list_blocks_force(self):
        html = _hist(_row("2024-03-05", None, "GBO-1")
                     + _row("2024-03-05", None, "GBO-50"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None
        assert "не все задачи из списка" in _kinds(d)[0]

    def test_black_rows_same_date_all_in_list_force(self):
        html = _hist(_row("2024-03-05", None, "GBO-50")
                     + _row("2024-03-05", None, "GBO-51"))
        d = decide_forced_unapproved(html, {"GBO-50", "GBO-51"})
        assert d.forced and d.forced.candidates == ["GBO-50", "GBO-51"]

    def test_black_row_same_date_without_task_blocks_force(self):
        # чёрная запись той же даты без задачи — кто создал страницу, неясно
        html = _hist(_row("2024-03-05", None, "")
                     + _row("2024-03-05", None, "GBO-50"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None and d.notes


class TestUndatedFirstRow:
    """Край 2: первая запись без даты — порядок строк по направлению сортировки."""

    def test_ascending_undated_head_with_list_task_forces(self):
        html = _hist(_row("", None, "GBO-50", dated=False)
                     + _row("2024-03-05", None, "GBO-1")
                     + _row("2025-06-01", ORANGE, "GBO-77"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced and d.forced.task == "GBO-50"

    def test_ascending_undated_head_other_task_does_not_force(self):
        html = _hist(_row("", None, "GBO-1", dated=False)
                     + _row("2024-03-05", None, "GBO-50")
                     + _row("2025-06-01", ORANGE, "GBO-77"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None
        assert _kinds(d) == ["задача из списка не в первой записи истории"]

    def test_descending_undated_tail_is_the_first_record(self):
        html = _hist(_row("2025-06-01", ORANGE, "GBO-77")
                     + _row("2024-03-05", None, "GBO-1")
                     + _row("", None, "GBO-50", dated=False))
        assert decide_forced_unapproved(html, {"GBO-50"}).forced.task == "GBO-50"

    def test_direction_unknown_does_not_force(self):
        # одна датированная строка — направление не определить
        html = _hist(_row("", None, "GBO-50", dated=False)
                     + _row("2024-03-05", None, "GBO-1"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None
        assert "не определяется" in _kinds(d)[0]

    def test_single_undated_row_is_the_first_record(self):
        # единственная запись — она и первая, дата не нужна
        html = _hist(_row("", None, "GBO-50", dated=False))
        assert decide_forced_unapproved(html, {"GBO-50"}).forced.task == "GBO-50"


class TestColoredFirstRow:
    """Край 3: первая запись цветная — страница живёт по карте цветов."""

    def test_colored_first_then_black_list_task_does_not_force(self):
        html = _hist(_row("2023-01-10", ORANGE, "GBO-77")
                     + _row("2024-03-05", None, "GBO-50"))
        d = decide_forced_unapproved(html, {"GBO-50"})
        assert d.forced is None
        assert "первая запись истории цветная" in _kinds(d)[0]

    def test_black_first_then_colored_forces(self):
        html = _hist(_row("2023-01-10", None, "GBO-50")
                     + _row("2024-03-05", ORANGE, "GBO-77"))
        assert decide_forced_unapproved(html, {"GBO-50"}).forced.task == "GBO-50"


class TestSeveralListTasks:
    """Прежнее решение сохранено: при форсе состав метится последней по дате."""

    def test_origin_in_list_later_black_in_list_marks_latest(self):
        html = _hist(_row("2025-01-01", None, "GBO-100")
                     + _row("2025-03-01", None, "GBO-200"))
        d = decide_forced_unapproved(html, {"GBO-100", "GBO-200"})
        assert d.forced.task == "GBO-200"
        assert d.forced.warnings and "GBO-200" in d.forced.warnings[0]

    def test_origin_not_in_list_two_later_list_tasks_no_force(self):
        html = _hist(_row("2024-01-01", None, "GBO-1")
                     + _row("2025-01-01", None, "GBO-100")
                     + _row("2025-03-01", None, "GBO-200"))
        d = decide_forced_unapproved(html, {"GBO-100", "GBO-200"})
        assert d.forced is None
        assert d.notes[0]["tasks"] == ["GBO-100", "GBO-200"]


class TestReport:
    """Случай без форса обязан дойти до отчёта и до счётчика позиций на разбор."""

    def _report(self, skipped):
        acc = new_accumulator()
        acc["pages"] = 1
        acc["forced_skipped"].extend(skipped)
        _manifest, report = finalize(acc, service="KK", migrated_at="2026-09-30")
        return report

    def test_section_lists_the_page(self):
        skipped = [{"page": "[КК] Лимиты", "tasks": ["GBO-50"],
                    "kind": "задача из списка не в первой записи истории"}]
        report = self._report(skipped)
        md = render_report_md(report)
        assert report["forced_skipped"] == skipped
        assert "страница НЕ заморожена" in md and "(1)" in md
        assert ("«[КК] Лимиты»: задача из списка не в первой записи истории "
                "(GBO-50)") in md

    def test_section_empty_when_nothing_skipped(self):
        md = render_report_md(self._report([]))
        head = next(ln for ln in md.splitlines() if "страница НЕ заморожена" in ln)
        assert head.endswith("(0)")
