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
