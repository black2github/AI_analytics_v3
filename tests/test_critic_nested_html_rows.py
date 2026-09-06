# tests/test_critic_nested_html_rows.py
#
# Инцидент 2026-09-06: reject-all по дереву [КК] обрывался на середине с
# AttributeError: 'NoneType' object has no attribute 'get'. Причина — вложенные
# друг в друга <tr class="critic-row-*">: в выгрузке Confluence таблица стоит
# внутри ячейки другой таблицы, а html.parser вложенность не расправляет.
# Список строк собирается ДО мутаций, поэтому удаление внешней строки
# уничтожает внутреннюю, которая всё ещё лежит в списке обхода — обращение к её
# атрибутам падало и роняло весь прогон (первый же файл обрывает миграцию).
#
# Класс тот же, что у литеральной вложенности маркеров: конвейер выпускает
# разметку, которую его же critic не дочитывает. Здесь закрепляется, что
# уничтоженный элемент пропускается, а не роняет прогон.

from app.scripts.CI.critic import process_file, process_text

# Форма из реальной выгрузки: строка-вставка, внутри ячейки которой лежит
# таблица-легенда, тоже размеченная как вставка той же задачи.
NESTED_ROWS = (
    "<table><tbody>\n"
    '<tr class="critic-row-ins" data-task="TEAMTB-3633">\n'
    "<td>3.1</td><td>Меню навигации по страницам</td>\n"
    "<td><table><tbody>\n"
    '<tr class="critic-row-ins" data-task="TEAMTB-3633">\n'
    "<td>Серый круг</td><td>Страница ещё не посещалась</td>\n"
    "</tr>\n"
    "</tbody></table></td>\n"
    "</tr>\n"
    '<tr class="critic-row-ins" data-task="GBO-1">\n'
    "<td>соседняя строка</td>\n"
    "</tr>\n"
    "</tbody></table>\n"
)

NESTED_SPANS = (
    "<table><tbody>\n"
    '<tr><td><span class="critic-ins" data-task="GBO-1">внешний '
    '<span class="critic-ins" data-task="GBO-2">внутренний</span></span></td></tr>\n'
    "</tbody></table>\n"
)


class TestNestedRowsDoNotCrash:
    def test_reject_all_survives_nested_rows(self):
        out, count = process_text(NESTED_ROWS, "reject", None)
        assert count == 2                       # внешняя строка и соседняя
        assert "Меню навигации" not in out      # вставка отклонена
        assert "Серый круг" not in out          # внутренняя ушла вместе с внешней
        assert "соседняя строка" not in out

    def test_apply_all_keeps_both_rows(self):
        out, count = process_text(NESTED_ROWS, "apply", None)
        assert count == 3                       # здесь ничего не уничтожается
        assert "Меню навигации" in out and "Серый круг" in out
        assert "critic-row-ins" not in out and "data-task" not in out

    def test_targeted_reject_of_outer_takes_inner_with_it(self):
        """Внутренняя строка той же задачи уезжает вместе с внешней — это и есть откат."""
        out, count = process_text(NESTED_ROWS, "reject", "TEAMTB-3633")
        assert count == 1
        assert "Серый круг" not in out
        assert "соседняя строка" in out         # чужая задача не тронута

    def test_nested_spans_survive_reject(self):
        out, count = process_text(NESTED_SPANS, "reject", None)
        assert count == 1                       # внутренний ушёл с внешним
        assert "внешний" not in out and "внутренний" not in out


class TestFlatIslandsUnchanged:
    """Сторож не должен менять поведение на обычных, невложенных островах."""

    FLAT = (
        "<table><tbody>\n"
        '<tr class="critic-row-ins" data-task="GBO-1"><td>раз</td></tr>\n'
        '<tr class="critic-row-del" data-task="GBO-2"><td>два</td></tr>\n'
        '<tr><td><span class="critic-ins" data-task="GBO-3">три</span></td></tr>\n'
        "</tbody></table>\n"
    )

    def test_reject(self):
        out, count = process_text(self.FLAT, "reject", None)
        assert count == 3
        assert "раз" not in out and "два" in out and "три" not in out

    def test_apply(self):
        out, count = process_text(self.FLAT, "apply", None)
        assert count == 3
        assert "раз" in out and "два" not in out and "три" in out


class TestThroughFile:
    def test_whole_file_processed_not_aborted(self, tmp_path):
        """Прогон по файлу доходит до конца: миграция не обрывается на первом же."""
        path = tmp_path / "страница.md"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("# Заголовок\n\n" + NESTED_ROWS + "\nхвост страницы\n")
        count = process_file(path, "reject", None)
        assert count == 2
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        assert "хвост страницы" in text
        assert "critic-row-ins" not in text
