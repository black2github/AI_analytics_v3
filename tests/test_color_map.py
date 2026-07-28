# tests/test_color_map.py
#
# Тесты Модуля 1, срез 1a (ТЗ п. 4.2, 4.3, 4.9, 4.10): нормализация цвета, карта
# «цвет → задача» из истории изменений, обход тела, манифест и отчёт (режим «только отчёт»).
# Нумерация ссылается на список тестов ТЗ п. 9 (8-14).

from app.utils.style_utils import normalize_color, is_black_color
from app.color_map import build_color_task_map, survey_body_colors
from app.scripts.migrate_colors import aggregate, migrate_pages
from app.scripts.CI.critic import process_text


def _hist(rows, headers=("Дата", "Описание", "Автор", "Задача в JIRA")):
    thead = "".join(f"<th>{h}</th>" for h in headers)
    return (f'<table><thead><tr>{thead}</tr></thead><tbody>{rows}</tbody></table>')


def _row(date_iso, color, jira_html, dd_mm_yyyy):
    color_cell = (f'<span style="color: {color}">описание</span>' if color
                  else "<span>описание</span>")
    return (f'<tr>'
            f'<td><time datetime="{date_iso}">{dd_mm_yyyy}</time></td>'
            f'<td>{color_cell}</td>'
            f'<td>автор</td>'
            f'<td>{jira_html}</td>'
            f'</tr>')


class TestColorNormalization:
    """11-12. Нормализация цвета и классификация чёрного (ТЗ п. 4.3)."""

    def test_black_forms_all_recognized(self):
        # rgb(51,51,51) есть в наборе; его эквиваленты должны опознаваться после нормализации.
        for v in ("#333333", "rgb(51,51,51)", "RGB(51, 51, 51)", "#333"):
            assert is_black_color(v), v

    def test_named_and_zero_forms_black(self):
        for v in ("black", "#000", "#000000", "rgb(0,0,0)", "rgba(0, 0, 0, 1)"):
            assert is_black_color(v), v

    def test_non_black_color_not_black(self):
        for v in ("#ff6600", "rgb(255,102,0)", "#9966ff"):
            assert not is_black_color(v), v

    def test_normalize_forms(self):
        assert normalize_color("rgb(153,102,255)") == "#9966ff"
        assert normalize_color("#9966FF") == "#9966ff"
        assert normalize_color("#96f") == "#9966ff"
        assert normalize_color("RGB(255, 102, 0)") == "#ff6600"
        assert normalize_color("нечто") is None


class TestJiraResolvers:
    """10. Все три формы идентификатора Jira: макрос, ссылка, простой текст (ТЗ п. 4.2.г)."""

    def test_three_id_forms(self):
        macro = ('<ac:structured-macro ac:name="jira">'
                 '<ac:parameter ac:name="key">GBO-1</ac:parameter></ac:structured-macro>')
        href = '<a href="https://jira.corp.local/browse/GBO-2">GBO-2</a>'
        plain = "GBO-3"
        rows = (
            _row("2025-01-01", "rgb(153,102,255)", macro, "01.01.2025") +
            _row("2025-02-01", "rgb(0,200,0)", href, "01.02.2025") +
            _row("2025-03-01", "rgb(255,102,0)", plain, "01.03.2025")
        )
        r = build_color_task_map(_hist(rows))
        assert r.color_to_task == {"#9966ff": "GBO-1", "#00c800": "GBO-2", "#ff6600": "GBO-3"}
        assert all(c == "high" for c in r.confidence.values())


class TestHistoryEdgeCases:
    """8, коллизии, чёрные строки, многоцветные строки (ТЗ п. 4.2)."""

    def test_page_without_history(self):
        r = build_color_task_map("<p>Просто текст без истории</p>")
        assert r.no_history is True
        assert r.color_to_task == {}

    def test_black_row_ignored(self):
        rows = _row("2025-01-01", "rgb(0,51,102)", "GBO-9", "01.01.2025")  # чёрный
        r = build_color_task_map(_hist(rows))
        assert r.color_to_task == {}  # чёрная строка = задача на ПРОМ, в карту не идёт

    def test_collision_latest_date_low_confidence(self):
        rows = (
            _row("2024-01-01", "rgb(0,200,0)", "GBO-10", "01.01.2024") +
            _row("2025-06-01", "rgb(0,200,0)", "GBO-20", "01.06.2025")  # позже
        )
        r = build_color_task_map(_hist(rows))
        assert r.color_to_task["#00c800"] == "GBO-20"       # выбрана поздняя дата
        assert r.confidence["#00c800"] == "low"
        assert r.collisions and set(r.collisions[0]["candidates"]) == {"GBO-10", "GBO-20"}

    def test_multi_color_row_maps_all_to_task(self):
        cell = ('<span style="color: rgb(255,0,255)">a</span>'
                '<span style="color: rgb(255,102,0)">b</span>')
        rows = (f'<tr><td><time datetime="2025-01-01">01.01.2025</time></td>'
                f'<td>{cell}</td><td>автор</td><td>GBO-7</td></tr>')
        r = build_color_task_map(_hist(rows))
        assert r.color_to_task == {"#ff00ff": "GBO-7", "#ff6600": "GBO-7"}

    def test_column_order_by_header_not_position(self):
        # Столбец «Задача в JIRA» первый, «Описание» последний — ищем по тексту заголовка.
        rows = ('<tr><td>GBO-5</td><td>автор</td>'
                '<td><time datetime="2025-01-01">01.01.2025</time></td>'
                '<td><span style="color: rgb(153,102,255)">d</span></td></tr>')
        html = _hist(rows, headers=("Задача в JIRA", "Автор", "Дата", "Описание"))
        r = build_color_task_map(html)
        assert r.color_to_task == {"#9966ff": "GBO-5"}


class TestSurveyUnknown:
    """9. Цвет в теле, отсутствующий в истории → плейсхолдер UNKNOWN-* (ТЗ п. 4.2.ж)."""

    def test_unknown_placeholder_for_color_not_in_history(self):
        history = _hist(_row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025"))
        body = '<p><span style="color: rgb(255,102,0)">оранжевое не в истории</span></p>'
        r = build_color_task_map(history + body)
        survey = survey_body_colors(history + body, r)
        assert survey["#ff6600"]["classification"] == "unknown"
        assert survey["#ff6600"]["task"] == "UNKNOWN-ff6600"
        assert survey["#ff6600"]["reason"] == "not-in-history"

    def test_mapped_and_black_classification(self):
        history = _hist(_row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025"))
        body = ('<p><span style="color: rgb(153,102,255)">по задаче</span>'
                '<span style="color: rgb(0,0,0)">чёрное</span></p>')
        r = build_color_task_map(history + body)
        survey = survey_body_colors(history + body, r)
        assert survey["#9966ff"]["classification"] == "task"
        assert survey["#9966ff"]["task"] == "GBO-1"
        assert survey["#000000"]["classification"] == "black"


class TestManifest:
    """14. Корректность migration-manifest на странице с тремя задачами (ТЗ п. 4.9)."""

    def test_manifest_three_tasks(self):
        rows = (
            _row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025") +
            _row("2025-02-01", "rgb(0,200,0)", "GBO-2", "01.02.2025") +
            _row("2025-03-01", "rgb(255,102,0)", "GBO-3", "01.03.2025")
        )
        body = ('<p><span style="color: rgb(153,102,255)">a</span></p>'
                '<p><span style="color: rgb(0,200,0)">b</span>'
                '<span style="color: rgb(0,200,0)">c</span></p>'
                '<p><span style="color: rgb(255,102,0)">d</span></p>')
        page = _hist(rows) + body
        manifest, report = aggregate([("страница", page)], "КК", "2026-08-15")

        assert set(manifest["tasks"]) == {"GBO-1", "GBO-2", "GBO-3"}
        assert manifest["tasks"]["GBO-1"] == {
            "color": "#9966ff", "confidence": "high", "pages": ["страница"], "markers": 1}
        assert manifest["tasks"]["GBO-2"]["markers"] == 2
        assert manifest["tasks"]["GBO-3"]["markers"] == 1
        assert manifest["service"] == "КК" and manifest["migrated_at"] == "2026-08-15"
        assert report["stats"]["pages_processed"] == 1
        # Все три цвета — по задаче, ничего не требует ручного разбора.
        assert report["stats"]["positions_manual_review"] == 0


class TestMigrate:
    """Срез 1b-4: команда migrate пишет .md с маркерами и собирает отчёт (ТЗ 4.5/4.9/4.10)."""

    def test_migrate_writes_markers_and_roundtrips(self, tmp_path):
        page = (_hist(_row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025")) +
                '<p>Текст <span style="color: rgb(153,102,255)">правка</span>.</p>')
        docs = tmp_path / "docs"
        manifest, report = migrate_pages([("стр", page)], "КК", "2026-08-15", docs)

        md = (docs / "стр.md").read_text(encoding="utf-8")
        assert "{++GBO-1: правка++}" in md
        assert "GBO-1" in manifest["tasks"]
        assert "nested_flattened" in report
        # round-trip: reject-all снимает все маркеры (Модуль 2 понимает продукт Модуля 1).
        rejected, _ = process_text(md, "reject", None)
        assert "{++" not in rejected and 'class="critic-' not in rejected

    def test_migrate_records_nesting(self, tmp_path):
        history = _hist(
            _row("2025-01-01", "rgb(255,153,204)", "GBO-1", "01.01.2025") +
            _row("2025-02-01", "rgb(153,204,0)", "GBO-2", "01.02.2025"))
        body = ('<p><span style="color: rgb(255,153,204)">A '
                '<span style="color: rgb(153,204,0)">B</span></span></p>')
        _manifest, report = migrate_pages([("p", history + body)], "КК", "2026-08-15",
                                          tmp_path / "docs")
        assert report["stats"]["nested_flattened"] == 1
        assert set(report["nested_flattened"][0]["tasks"]) == {"GBO-1", "GBO-2"}


class TestPerPageColorSummary:
    """Фикс C: сводка цветов — постраничная (один цвет может быть task/unknown на разных страницах)."""

    def test_same_color_two_pages_two_classifications(self):
        p1 = (_hist(_row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025")) +
              '<p><span style="color: rgb(153,102,255)">a</span></p>')       # есть история → task
        p2 = '<p><span style="color: rgb(153,102,255)">b</span></p>'          # нет истории → unknown
        _m, r = aggregate([("p1", p1), ("p2", p2)], "КК", "2026-08-15")
        rows = [c for c in r["color_summary"] if c["color"] == "#9966ff"]
        assert {row["page"] for row in rows} == {"p1", "p2"}
        assert {row["classification"] for row in rows} == {"task", "unknown"}


class TestRealDebugFiles:
    """Интеграция на приложенных rendered-view HTML (закрепляем поведение на реальных данных)."""

    def _load(self, name_part):
        from pathlib import Path
        for p in Path("debug/html").glob("*.html"):
            if name_part in p.name:
                return p.read_text(encoding="utf-8")
        raise AssertionError(f"debug html not found: {name_part}")

    def test_big_file_resolves_via_link_and_drops_phantom_colors(self):
        # После фикса A цвет берётся по ближайшему предку: фантомные внешние обёртки
        # (magenta поверх оранжевого, зелёная строка поверх чёрного) отброшены —
        # остаётся честная карта: оранжевый (через ссылку browse/) и зелёный (одна задача).
        r = build_color_task_map(self._load("Заявка-на-выпуск-карты"))
        assert r.color_to_task.get("#ff6600") == "TEAMTB-3633"   # через ссылку browse/
        assert r.color_to_task.get("#99cc00") == "GBO-48965"     # зелёный, одна задача
        assert "#ff00ff" not in r.color_to_task                  # фантомная magenta-обёртка отброшена

    def test_small_file_all_unresolved(self):
        r = build_color_task_map(self._load("Настройка-скроллера"))
        assert r.color_to_task == {}                             # сломанные jira-макросы
        assert {u["color"] for u in r.unresolved_jira}           # цвета есть, id нет
