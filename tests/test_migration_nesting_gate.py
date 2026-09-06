# tests/test_migration_nesting_gate.py
#
# Гейт на выходе конвейера (инцидент 2026-09-05): экспортёр выпустил разметку,
# которую его же critic не читает — блочный маркер накрыл участок с врезками
# соседних задач. Узнали об этом только когда у команды упал reject-all на
# боевом дереве: apply/reject валятся жёстко и обрывают прогон на первом файле.
#
# Гейт не роняет миграцию (страница уже собрана, терять её из-за разметки
# нельзя), а предупреждает в журнале и кладёт случай в отчёт как позицию
# ручного разбора — с указанием, чем чинить.

from app.scripts.CI.critic import find_literal_nesting
from app.scripts.migrate_colors import finalize, new_accumulator, render_report_md

NESTED = "{++GBO-70412: список - {++DBOCORPESPLN-104756: врезка++} хвост++}"
CLEAN = "{++GBO-70412: список++} {++DBOCORPESPLN-104756: врезка++}"


def _report(nesting_rows):
    acc = new_accumulator()
    acc["pages"] = 1
    acc["literal_nesting"].extend(nesting_rows)
    _manifest, report = finalize(acc, service="KK", migrated_at="2026-09-05")
    return report


def _row_from(text, page="Страница"):
    """Как это делает конвейер: находки гейта → записи отчёта."""
    return [{"page": page, "line": n["line"], "outer": n["outer"], "inner": n["inner"]}
            for n in find_literal_nesting(text)]


class TestDetection:
    def test_gate_sees_nesting_in_page_content(self):
        rows = _row_from(NESTED)
        assert len(rows) == 1
        assert rows[0]["outer"] == "GBO-70412"
        assert rows[0]["inner"] == ["DBOCORPESPLN-104756"]

    def test_gate_silent_on_flat_markup(self):
        assert _row_from(CLEAN) == []

    def test_gate_ignores_fenced_code(self):
        """В коде разметка не разбирается — это не наша вложенность."""
        assert _row_from("```\n" + NESTED + "\n```") == []


class TestReport:
    def test_json_section_carries_case(self):
        report = _report(_row_from(NESTED))
        assert len(report["literal_nesting"]) == 1
        assert report["literal_nesting"][0]["outer"] == "GBO-70412"

    def test_counted_as_manual_review_position(self):
        with_case = _report(_row_from(NESTED))["stats"]["positions_manual_review"]
        without = _report([])["stats"]["positions_manual_review"]
        assert with_case == without + 1

    def test_markdown_names_page_marker_and_remedy(self):
        md = render_report_md(_report(_row_from(NESTED)))
        assert "## Литеральная вложенность маркеров" in md
        assert "GBO-70412" in md and "DBOCORPESPLN-104756" in md
        assert "run-repair --flatten-nested" in md      # аналитику сказано, чем чинить

    def test_section_present_when_clean(self):
        """Секция печатается всегда: «нет» — тоже сведение."""
        md = render_report_md(_report([]))
        start = md.find("## Литеральная вложенность маркеров")
        assert start >= 0 and "_нет_" in md[start:start + 200]


class TestCodeBlockGate:
    """
    Второй случай той же природы (инцидент 2026-09-06): блок кода накрыл маркеры.
    Переносится он байт-в-байт, поэтому apply/reject внутрь не заглядывают —
    неутверждённое молча остаётся в «чистом ПРОМ». Конвейер обязан это назвать.
    """

    IN_CODE = "```\n{++GBO-70412: требование внутри блока++}\n```\n"

    def _rows(self, text, page="Страница"):
        from app.scripts.CI.critic import find_markers_in_code
        return [{"page": page, "line": b["line"], "chars": b["chars"],
                 "markers": b["markers"], "tasks": b["tasks"]}
                for b in find_markers_in_code(text)]

    def _report_with(self, rows):
        acc = new_accumulator()
        acc["pages"] = 1
        acc["markers_in_code"].extend(rows)
        _manifest, report = finalize(acc, service="KK", migrated_at="2026-09-06")
        return report

    def test_gate_sees_markers_in_code(self):
        rows = self._rows(self.IN_CODE)
        assert len(rows) == 1 and rows[0]["tasks"] == ["GBO-70412"]

    def test_json_section_carries_case(self):
        report = self._report_with(self._rows(self.IN_CODE))
        assert report["markers_in_code"][0]["markers"] == 1

    def test_counted_as_manual_review_position(self):
        with_case = self._report_with(self._rows(self.IN_CODE))["stats"]["positions_manual_review"]
        without = self._report_with([])["stats"]["positions_manual_review"]
        assert with_case == without + 1

    def test_markdown_names_page_and_remedy(self):
        md = render_report_md(self._report_with(self._rows(self.IN_CODE)))
        assert "## Маркеры внутри блока кода" in md
        assert "GBO-70412" in md
        assert "unapproved_jira" in md          # чем закрывать, если разбирать нечем

    def test_section_present_when_clean(self):
        md = render_report_md(self._report_with([]))
        start = md.find("## Маркеры внутри блока кода")
        assert start >= 0 and "_нет_" in md[start:start + 200]


class TestRepairClosesTheCase:
    def test_flatten_makes_content_pass_the_gate(self):
        """Починка из отчёта действительно снимает находку гейта."""
        from app.scripts.repair_export import flatten_nested, strip_markers

        fixed, count = flatten_nested(NESTED)
        assert count == 1
        assert find_literal_nesting(fixed) == []
        assert strip_markers(fixed) == strip_markers(NESTED)
