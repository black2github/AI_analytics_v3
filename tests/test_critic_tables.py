# tests/test_critic_tables.py
#
# Тесты Модуля 1, срез 1b-3 (ТЗ п. 4.6, 4.7): разметка таблиц в режиме CriticMarkup.
# Правильный критерий для табличных правок — не байтовое равенство с approved-экстрактором
# (approved «роняет» цветное содержимое, сохраняя пустую структуру; critic же корректно
# удаляет добавленные строки), а round-trip через critic.py: apply/reject дают ожидаемое.
# Нумерация — по списку ТЗ п. 9 (тесты 6-7).

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text

C = {"#9966ff": "GBO-1"}  # rgb(153,102,255)


def _critic(html):
    return create_critic_extractor(C).extract(html)


class TestMarkdownTable:
    """6. markdown-таблица: правка в ячейке, новая строка, удалённая строка (ТЗ п. 4.6)."""

    def test_cell_internal_edit_is_inline(self):
        html = ('<table><thead><tr><th>ID</th><th>Проверка</th></tr></thead>'
                '<tbody><tr><td>C-1</td>'
                '<td>V <span style="color:rgb(153,102,255)">и группа 2</span></td></tr>'
                '</tbody></table>')
        out = _critic(html)
        assert "{++GBO-1: и группа 2++}" in out
        assert "| status |" not in out  # нет цельных строк — служебный столбец не добавляется

    def test_whole_added_row_uses_status_column(self):
        html = ('<table><thead><tr><th>ID</th><th>Проверка</th></tr></thead>'
                '<tbody>'
                '<tr><td>C-1</td><td>Старая</td></tr>'
                '<tr><td><span style="color:rgb(153,102,255)">C-2</span></td>'
                '<td><span style="color:rgb(153,102,255)">Новая</span></td></tr>'
                '</tbody></table>')
        out = _critic(html)
        assert "| ID | Проверка | status |" in out
        assert "| C-2 | Новая | +GBO-1 |" in out

        # apply GBO-1 → строка остаётся, status очищается, столбец удаляется (все пусты).
        applied, _ = process_text(out, "apply", "GBO-1")
        assert "| C-2 | Новая |" in applied and "status" not in applied
        # reject GBO-1 → строка C-2 удаляется целиком.
        rejected, _ = process_text(out, "reject", "GBO-1")
        assert "C-2" not in rejected and "C-1" in rejected

    def test_whole_deleted_row_uses_minus_status(self):
        html = ('<table><thead><tr><th>ID</th><th>Проверка</th></tr></thead>'
                '<tbody>'
                '<tr><td>C-1</td><td>Живая</td></tr>'
                '<tr><td><span style="color:rgb(153,102,255)"><s>C-2</s></span></td>'
                '<td><span style="color:rgb(153,102,255)"><s>Удаляемая</s></span></td></tr>'
                '</tbody></table>')
        out = _critic(html)
        assert "| -GBO-1 |" in out
        # apply → удаляемая строка исчезает; reject → остаётся (status очищен).
        applied, _ = process_text(out, "apply", "GBO-1")
        assert "C-2" not in applied
        rejected, _ = process_text(out, "reject", "GBO-1")
        assert "C-2" in rejected and "status" not in rejected


class TestHtmlTable:
    """7. Сырая HTML-таблица: те же случаи в HTML-нотации (ТЗ п. 4.7).

    colspan уводит таблицу на HTML-путь (Markdown не поддерживает объединение).
    """

    def test_cell_internal_span_ins(self):
        html = ('<table><tbody>'
                '<tr><td colspan="2">шапка</td></tr>'
                '<tr><td>C-1</td>'
                '<td>V <span style="color:rgb(153,102,255)">и группа 2</span></td></tr>'
                '</tbody></table>')
        out = _critic(html)
        assert '<span class="critic-ins" data-task="GBO-1">и группа 2</span>' in out
        # critic.py умеет снять/удалить нотацию.
        applied, _ = process_text(out, "apply", "GBO-1")
        assert "и группа 2" in applied and "critic-ins" not in applied
        rejected, _ = process_text(out, "reject", "GBO-1")
        assert "и группа 2" not in rejected

    def test_whole_added_row_ins(self):
        html = ('<table><tbody>'
                '<tr><td colspan="2">шапка</td></tr>'
                '<tr><td><span style="color:rgb(153,102,255)">C-2</span></td>'
                '<td><span style="color:rgb(153,102,255)">Новая</span></td></tr>'
                '</tbody></table>')
        out = _critic(html)
        assert '<tr class="critic-row-ins" data-task="GBO-1">' in out
        # apply → строка становится обычной; reject → удаляется.
        applied, _ = process_text(out, "apply", "GBO-1")
        assert "critic-row-ins" not in applied and "Новая" in applied
        rejected, _ = process_text(out, "reject", "GBO-1")
        assert "Новая" not in rejected and "шапка" in rejected

    def test_whole_deleted_row_del(self):
        html = ('<table><tbody>'
                '<tr><td colspan="2">шапка</td></tr>'
                '<tr><td><span style="color:rgb(153,102,255)"><s>C-2</s></span></td>'
                '<td><span style="color:rgb(153,102,255)"><s>Удаляемая</s></span></td></tr>'
                '</tbody></table>')
        out = _critic(html)
        assert '<tr class="critic-row-del" data-task="GBO-1">' in out
        applied, _ = process_text(out, "apply", "GBO-1")
        assert "Удаляемая" not in applied
        rejected, _ = process_text(out, "reject", "GBO-1")
        assert "critic-row-del" not in rejected and "Удаляемая" in rejected


class TestStatusColumnIsNamedInRealShapes:
    """
    Инцидент 2026-09-06. Имя служебного столбца писалось только в ряд из <thead>,
    а выгрузка Confluence держит заголовки внутри <tbody> — первая строка тела
    повышалась до шапки markdown вместе со своей ПУСТОЙ служебной ячейкой.
    Столбец оставался безымянным, critic такую таблицу не опознавал и пропускал
    целиком: ни apply, ни reject до строк не добирались, и разметка ±ID доезжала
    до ПРОМ-среза (на дереве [КК] уцелело 10 ячеек на 6 страницах).

    Прежний тест закрывал только форму с явным <thead> — то есть проверял
    договорённость, а не то, что реально приходит из Confluence.
    """

    COLORED = ('<tr><td><span style="color:rgb(153,102,255)">07</span></td>'
               '<td><span style="color:rgb(153,102,255)">Новая строка</span></td></tr>')
    PLAIN = "<tr><td>01</td><td>Старая строка</td></tr>"

    def _table(self, first_row):
        return "<table><tbody>" + first_row + self.PLAIN + self.COLORED + "</tbody></table>"

    def test_header_as_th_inside_tbody(self):
        out = _critic(self._table("<tr><th>Код</th><th>Текст</th></tr>"))
        assert "| Код | Текст | status |" in out

    def test_header_as_td_inside_tbody(self):
        """В выгрузке шапка часто вообще без <th> — просто первая строка."""
        out = _critic(self._table("<tr><td>Код</td><td>Текст</td></tr>"))
        assert "| Код | Текст | status |" in out

    def test_explicit_thead_still_works(self):
        html = ('<table><thead><tr><th>Код</th><th>Текст</th></tr></thead><tbody>'
                + self.PLAIN + self.COLORED + "</tbody></table>")
        assert "| Код | Текст | status |" in _critic(html)

    def test_marked_first_row_keeps_its_marker(self):
        """Первая строка сама размечена: маркер важнее, шапка добавляется отдельной."""
        out = _critic("<table><tbody>" + self.COLORED + self.PLAIN + "</tbody></table>")
        lines = [l for l in out.splitlines() if l.startswith("|")]
        assert lines[0].endswith("| status |")
        assert "| 07 | Новая строка | +GBO-1 |" in out       # маркер не потерян

    def test_reject_now_reaches_the_rows(self):
        """Смысл правки: разметка перестаёт доезжать до ПРОМ-среза."""
        for first in ("<tr><th>Код</th><th>Текст</th></tr>", "<tr><td>Код</td><td>Текст</td></tr>"):
            out = _critic(self._table(first))
            rejected, count = process_text(out, "reject", None)
            assert count == 1
            assert "+GBO-1" not in rejected and "Новая строка" not in rejected

    def test_table_without_marked_rows_has_no_status_column(self):
        """Ограничитель прежний: нет размеченных строк — столбца нет (ТЗ п. 4.6)."""
        html = "<table><tbody><tr><th>Код</th><th>Текст</th></tr>" + self.PLAIN + "</tbody></table>"
        assert "status" not in _critic(html)
