# tests/test_color_map.py
#
# Тесты Модуля 1, срез 1a (ТЗ п. 4.2, 4.3, 4.9, 4.10): нормализация цвета, карта
# «цвет → задача» из истории изменений, обход тела, манифест и отчёт (режим «только отчёт»).
# Нумерация ссылается на список тестов ТЗ п. 9 (8-14).

from app.utils.style_utils import (
    normalize_color, is_black_color, is_near_black, to_rgb_notation,
)
from app.color_map import build_color_task_map, survey_body_colors
from app.scripts.migrate_colors import aggregate, migrate_pages, render_report_md
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

    def test_long_project_key_resolved(self):
        # Инцидент 2026-08-06: ключи длиннее 10 символов (DBOCORPESPLN-123456)
        # не матчились ({1,9}) и цвет уходил в UNKNOWN. Все три формы.
        macro = ('<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">'
                 'DBOCORPESPLN-123456</ac:parameter></ac:structured-macro>')
        href = ('<a href="https://jira.corp.local/browse/DBOCORPESPLN-123457">'
                'DBOCORPESPLN-123457</a>')
        plain = "DBOCORPESPLN-123458"
        rows = (
            _row("2025-01-01", "rgb(153,102,255)", macro, "01.01.2025") +
            _row("2025-02-01", "rgb(0,200,0)", href, "01.02.2025") +
            _row("2025-03-01", "rgb(255,102,0)", plain, "01.03.2025")
        )
        r = build_color_task_map(_hist(rows))
        assert r.color_to_task == {
            "#9966ff": "DBOCORPESPLN-123456",
            "#00c800": "DBOCORPESPLN-123457",
            "#ff6600": "DBOCORPESPLN-123458",
        }


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
            "color": "#9966ff", "confidence": "high", "pages": ["страница"],
            "markers": 1, "first_seen": "2025-01-01"}
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


class TestNearBlack:
    """ТЗ 4.3.1/4.3.2: цвет вне палитры, перцептивно неотличимый от чёрного (ΔE), → чёрный."""

    def _hist1(self):
        return _hist(_row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025"))

    def test_delta_e_separates_grey_from_saturated_darks(self):
        assert is_near_black("#0a0a0a")        # почти-чёрный серый (ΔE мал)
        assert not is_near_black("#000080")    # navy — реальный тёмный ЦВЕТ (ΔE велик)
        assert not is_near_black("#008000")    # dark green
        assert not is_near_black("#ff6600")    # оранжевый

    def test_near_black_classified_black_with_delta_e(self):
        body = '<p><span style="color: rgb(10,10,10)">почти чёрный вне палитры</span></p>'
        r = build_color_task_map(self._hist1() + body)
        survey = survey_body_colors(self._hist1() + body, r)
        assert survey["#0a0a0a"]["classification"] == "near-black"
        assert "delta_e" in survey["#0a0a0a"]           # для калибровки порога (req 5)

    def test_saturated_dark_stays_unknown(self):
        body = '<p><span style="color: rgb(0,0,128)">navy текст</span></p>'  # #000080
        r = build_color_task_map(self._hist1() + body)
        survey = survey_body_colors(self._hist1() + body, r)
        assert survey["#000080"]["classification"] == "unknown"

    def test_delta_e_propagates_to_report_summary(self):
        # ΔE должен доходить до строки сводки отчёта (вход калибровки порога, req 5).
        page = self._hist1() + '<p><span style="color: rgb(0,0,128)">navy</span></p>'
        _m, report = aggregate([("p", page)], "КК", "2026-07-29")
        navy = [c for c in report["color_summary"] if c["color"] == "#000080"][0]
        assert navy["classification"] == "unknown"
        assert isinstance(navy["delta_e"], float) and navy["delta_e"] > 10


class TestIgnoredColors:
    """Ignore-список UI-цветов: не задача и не UNKNOWN, отдельная классификация 'ignored'."""

    def test_ui_color_classified_ignored_not_unknown(self):
        history = _hist(_row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025"))
        body = '<p><span style="color: rgb(0,82,204)">ссылка синим</span></p>'  # #0052cc
        r = build_color_task_map(history + body)
        survey = survey_body_colors(history + body, r)
        assert survey["#0052cc"]["classification"] == "ignored"
        assert survey["#0052cc"]["task"] is None


class TestRgbNotationInReport:
    """Отчёт показывает цвет в форме HTML-исходника: по `#rrggbb` аналитик не найдёт
    фрагмент на странице — Confluence пишет цвет как rgb(r,g,b) (проверено на выгрузках)."""

    def test_to_rgb_notation_forms(self):
        assert to_rgb_notation("#9966ff") == "rgb(153,102,255)"
        assert to_rgb_notation("rgb(153, 102, 255)") == "rgb(153,102,255)"  # пробелы схлопнуты
        assert to_rgb_notation("#333") == "rgb(51,51,51)"                   # короткая форма
        assert to_rgb_notation("black") == "rgb(0,0,0)"                     # именованный
        assert to_rgb_notation("не цвет") is None

    def test_to_rgb_notation_roundtrip(self):
        # Обратная конверсия обязана возвращать ровно тот цвет, из которого получена.
        for src in ("#000000", "#172b4d", "#ff6600", "#0a0a0a"):
            assert normalize_color(to_rgb_notation(src)) == src

    def test_summary_table_has_rgb_column(self):
        page = (_hist(_row("2025-01-01", "rgb(153,102,255)", "GBO-1", "01.01.2025")) +
                '<p><span style="color: rgb(255,102,0)">оранжевое</span></p>')
        _m, report = aggregate([("стр", page)], "КК", "2026-07-31")
        md = render_report_md(report)
        assert "| Цвет в HTML | Цвет |" in md
        # Форма из HTML-исходника — слитная, именно её ищут поиском по странице.
        assert "rgb(255,102,0)" in md and "#ff6600" in md

    def test_unresolved_section_shows_rgb(self):
        # UNKNOWN — главная очередь ручного разбора, там форма для поиска нужнее всего.
        page = '<p><span style="color: rgb(51,153,102)">без истории</span></p>'
        _m, report = aggregate([("стр", page)], "КК", "2026-07-31")
        md = render_report_md(report)
        assert "UNKNOWN-339966" in md
        assert "rgb(51,153,102)" in md


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


class TestForcedUnapproved:
    """Эмуляция похода в RAG (2026-08-07): джира из ЧЁРНОЙ строки истории входит
    в JSON-список неутверждённых → состав страницы метится этой джирой."""

    def _hist_black(self, jira_html, date_iso="2025-01-01", dd="01.01.2025", extra=""):
        return _hist(_row(date_iso, None, jira_html, dd) + extra)

    def test_black_row_jira_in_list_forces(self):
        from app.color_map import find_forced_unapproved
        r = find_forced_unapproved(self._hist_black("GBO-100"), {"GBO-100"})
        assert r is not None and r.task == "GBO-100"
        assert r.candidates == ["GBO-100"] and not r.warnings

    def test_jira_not_in_list_no_force(self):
        # тест на НЕсрабатывание: чёрная строка с джирой вне списка — обычный режим
        from app.color_map import find_forced_unapproved
        assert find_forced_unapproved(self._hist_black("GBO-100"), {"GBO-999"}) is None

    def test_colored_row_jira_ignored(self):
        # цветная строка обрабатывается картой цветов, форс только по ЧЁРНЫМ
        from app.color_map import find_forced_unapproved
        html = _hist(_row("2025-01-01", "rgb(255,102,0)", "GBO-100", "01.01.2025"))
        assert find_forced_unapproved(html, {"GBO-100"}) is None

    def test_multiple_matches_latest_by_date_with_warning(self):
        # решение пользователя: последняя по дате + предупреждение с перечнем
        from app.color_map import find_forced_unapproved
        html = _hist(
            _row("2025-01-01", None, "GBO-100", "01.01.2025") +
            _row("2025-03-01", None, "GBO-200", "01.03.2025")
        )
        r = find_forced_unapproved(html, {"GBO-100", "GBO-200"})
        assert r.task == "GBO-200"
        assert r.candidates == ["GBO-100", "GBO-200"]
        assert r.warnings and "GBO-200" in r.warnings[0]

    def test_no_history_not_covered(self):
        # риск принят: страницы без истории механизм не покрывает
        from app.color_map import find_forced_unapproved
        assert find_forced_unapproved("<p>текст без истории</p>", {"GBO-1"}) is None

    def test_empty_list_no_force(self):
        from app.color_map import find_forced_unapproved
        assert find_forced_unapproved(self._hist_black("GBO-100"), set()) is None

    def test_link_and_macro_resolvers_work_for_black_rows(self):
        # резолверы джиры те же, что у карты цветов (макрос / browse-ссылка)
        from app.color_map import find_forced_unapproved
        macro = ('<ac:structured-macro ac:name="jira">'
                 '<ac:parameter ac:name="key">GBO-7</ac:parameter></ac:structured-macro>')
        assert find_forced_unapproved(self._hist_black(macro), {"GBO-7"}).task == "GBO-7"
        href = '<a href="https://jira.corp.local/browse/GBO-8">GBO-8</a>'
        assert find_forced_unapproved(self._hist_black(href), {"GBO-8"}).task == "GBO-8"


class TestTaskDatesAndApplyOrder:
    """Порядок вливания задач (2026-08-10): дата первой записи истории по
    задаче -> предложение порядка apply на внешнем контуре."""

    def test_min_date_across_duplicate_rows(self):
        # одна задача в двух строках истории — берётся самая ранняя дата
        rows = (
            _row("2025-03-01", "rgb(153,102,255)", "GBO-1", "01.03.2025") +
            _row("2025-01-15", "rgb(153,102,255)", "GBO-1", "15.01.2025")
        )
        r = build_color_task_map(_hist(rows))
        assert r.task_dates["GBO-1"] == (2025, 1, 15)

    def test_series_row_dates_all_ids(self):
        # серия задач в одной ячейке — дата строки относится ко всем id
        rows = _row("2025-02-02", "rgb(0,200,0)", "GBO-2 GBO-3", "02.02.2025")
        r = build_color_task_map(_hist(rows))
        assert r.task_dates["GBO-2"] == (2025, 2, 2)
        assert r.task_dates["GBO-3"] == (2025, 2, 2)

    def test_row_without_date_gives_no_entry(self):
        html = _hist('<tr><td>без даты</td>'
                     '<td><span style="color: rgb(255,102,0)">описание</span></td>'
                     '<td>автор</td><td>GBO-4</td></tr>')
        r = build_color_task_map(html)
        assert "GBO-4" not in r.task_dates
        assert r.color_to_task.get("#ff6600") == "GBO-4"   # сама задача не потеряна

    def test_forced_first_seen(self):
        from app.color_map import find_forced_unapproved
        html = _hist(
            _row("2025-05-01", None, "GBO-7", "01.05.2025") +
            _row("2025-04-01", None, "GBO-7", "01.04.2025")
        )
        r = find_forced_unapproved(html, {"GBO-7"})
        assert r.first_seen == (2025, 4, 1)

    def test_finalize_apply_order_sorted_undated_last(self):
        from app.scripts.migrate_colors import (new_accumulator, accumulate_page,
                                                finalize, render_apply_order_md)
        acc = new_accumulator()
        html_a = (_hist(_row("2025-03-01", "rgb(153,102,255)", "GBO-10", "01.03.2025"))
                  + '<p><span style="color: rgb(153,102,255)">правка A</span></p>')
        html_b = (_hist(_row("2025-01-01", "rgb(0,200,0)", "GBO-20", "01.01.2025"))
                  + '<p><span style="color: rgb(0,200,0)">правка B</span></p>')
        for name, h in (("A", html_a), ("B", html_b)):
            res = build_color_task_map(h)
            accumulate_page(acc, name, res, survey_body_colors(h, res))
        # задача без даты — руками в аккумулятор (как UNKNOWN)
        acc["tasks"]["GBO-30"] = {"color": "#123456", "confidence": "high",
                                  "pages": {"C"}, "markers": 1, "date": None}
        manifest, report = finalize(acc, "CC", "2026-08-10")
        order = [o["task"] for o in report["apply_order"]]
        assert order == ["GBO-20", "GBO-10", "GBO-30"]     # по дате, бездатные в конце
        assert manifest["tasks"]["GBO-20"]["first_seen"] == "2025-01-01"
        md = render_apply_order_md(report)
        assert "run-critic.bat apply GBO-20 --path ." in md
        assert md.index("apply GBO-20") < md.index("apply GBO-10")
        assert "REM порядок уточните: run-critic.bat apply GBO-30" in md

    def test_same_day_group_marked(self):
        from app.scripts.migrate_colors import (new_accumulator, accumulate_page,
                                                finalize, render_apply_order_md)
        acc = new_accumulator()
        rows = (_row("2025-06-01", "rgb(153,102,255)", "GBO-41", "01.06.2025") +
                _row("2025-06-01", "rgb(0,200,0)", "GBO-42", "01.06.2025"))
        h = (_hist(rows)
             + '<p><span style="color: rgb(153,102,255)">a</span>'
             '<span style="color: rgb(0,200,0)">b</span></p>')
        res = build_color_task_map(h)
        accumulate_page(acc, "P", res, survey_body_colors(h, res))
        _m, report = finalize(acc, "CC", "2026-08-10")
        md = render_apply_order_md(report)
        assert md.count("⚠ один день") == 2               # обе строки помечены
