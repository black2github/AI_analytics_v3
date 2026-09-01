# tests/test_migrate_colors_multi_task.py
#
# Инцидент 2026-09-02: в строке истории две задачи в одной ячейке
# (TEAMECO-5354 рядом с DBOCORPESPLN-59857, один цвет rgb(255,0,255)).
# Карта устроена «цвет → ОДНА задача», поэтому в маркеры уходит первый id,
# а второй выпадает. Предупреждение об этом строилось (result.multi_id_rows),
# но до отчёта не доходило — аналитик видел аккуратную карту и не знал,
# что рядом отброшена вторая задача.
#
# Здесь закрепляется вывод такого случая в отчёт: JSON-секция, строка в
# markdown и учёт в счётчике позиций ручного разбора.

from app.scripts.migrate_colors import aggregate, render_report_md

TWO_LINKS = (
    '<a href="https://jira.example/jira/browse/DBOCORPESPLN-59857">DBOCORPESPLN-59857</a> '
    '<a href="https://jira.example/jira/browse/TEAMECO-5354">TEAMECO-5354</a>'
)
ONE_LINK = '<a href="https://jira.example/jira/browse/GBO-100">GBO-100</a>'


def _page(jira_html: str, color: str = "rgb(255,0,255)") -> str:
    """Страница с историей из одной строки и цветным фрагментом в теле."""
    return (
        '<table><thead><tr><th>Дата</th><th>Описание</th>'
        '<th>Автор</th><th>Задача в JIRA</th></tr></thead><tbody>'
        '<tr>'
        '<td><time datetime="2026-03-26">26.03.2026</time></td>'
        f'<td><span style="color: {color}">описание правки</span></td>'
        '<td>автор</td>'
        f'<td>{jira_html}</td>'
        '</tr></tbody></table>'
        f'<p><span style="color: {color}">требование из этой правки</span></p>'
    )


def _report(html: str) -> dict:
    _manifest, report = aggregate([("Страница", html)], service="IL",
                                  migrated_at="2026-09-02")
    return report


class TestJsonSection:
    def test_dropped_task_is_reported(self):
        rows = _report(_page(TWO_LINKS))["multi_task_rows"]
        assert len(rows) == 1
        row = rows[0]
        assert row["page"] == "Страница"
        assert row["color"] == "#ff00ff"
        assert row["chosen"] == "DBOCORPESPLN-59857"
        assert row["dropped"] == ["TEAMECO-5354"]
        assert row["task_ids"] == ["DBOCORPESPLN-59857", "TEAMECO-5354"]

    def test_single_task_row_is_silent(self):
        """Одна задача в ячейке — сообщать не о чем."""
        assert _report(_page(ONE_LINK))["multi_task_rows"] == []

    def test_counted_as_manual_review_position(self):
        """Случай требует глаз аналитика — попадает в счётчик позиций."""
        with_multi = _report(_page(TWO_LINKS))["stats"]["positions_manual_review"]
        without = _report(_page(ONE_LINK))["stats"]["positions_manual_review"]
        assert with_multi == without + 1


class TestMarkdownSection:
    def test_section_names_chosen_and_dropped(self):
        md = render_report_md(_report(_page(TWO_LINKS)))
        assert "## Несколько задач в одной строке истории" in md
        assert "взят DBOCORPESPLN-59857" in md
        assert "TEAMECO-5354" in md
        assert "rgb(255,0,255)" in md and "#ff00ff" in md

    def test_section_present_and_empty_without_incident(self):
        """Секция есть всегда: «нет» — тоже сведение, а не умолчание."""
        md = render_report_md(_report(_page(ONE_LINK)))
        assert "## Несколько задач в одной строке истории" in md
        start = md.find("## Несколько задач в одной строке истории")
        assert "_нет_" in md[start:start + 200]


class TestMarkersUnchanged:
    def test_first_task_still_wins_in_markers(self):
        """Правка только про отчёт: поведение карты не меняется."""
        report = _report(_page(TWO_LINKS))
        colors = {c["color"]: c for c in report["color_summary"]}
        assert colors["#ff00ff"]["task"] == "DBOCORPESPLN-59857"
