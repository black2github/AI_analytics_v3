# tests/test_status_column_naming.py
#
# Безымянный служебный столбец (инцидент 2026-09-06). Нотация опознаёт табличную
# правку по ИМЕНИ столбца `status` (ТЗ п. 4.6). Экспортёр писал имя только в ряд
# из <thead>, а выгрузка Confluence держит заголовки в <tbody> — столбец
# оставался безымянным. Такие таблицы apply/reject пропускают целиком и молчат:
# разметка ±ID доехала до ПРОМ-среза, а строки «на удаление» не удалились.
# Нашлось только по хвосту `critic list` — 9 ячеек на 5 страницах дерева [КК].
#
# Здесь закрыты две стороны: сторож (находит) и починка (называет столбец).
# Правка экспортёра — в tests/test_critic_tables.py.

from app.scripts.CI.critic import find_unnamed_status_column, process_text
from app.scripts.repair_export import name_status_column

UNNAMED = ("| Код | Текст |  |\n"
           "| --- | --- | --- |\n"
           "| 01 | обычная |  |\n"
           "| 07 | новая | +GBO-1 |\n")

NAMED = ("| Код | Текст | status |\n"
         "| --- | --- | --- |\n"
         "| 07 | новая | +GBO-1 |\n")

MARKED_HEADER = ("| № | Название | -GBO-2 |\n"
                 "| --- | --- | --- |\n"
                 "| 1 | строка |  |\n")

WRAPPED_HEADER = ("{++GBO-3: | № | Название | -GBO-3 |\n"
                  "| --- | --- | --- |\n"
                  "| 1 | строка |  |++}\n")


class TestDetector:
    def test_unnamed_column_found(self):
        hits = find_unnamed_status_column(UNNAMED)
        assert len(hits) == 1
        assert hits[0]["sign"] == "+" and hits[0]["task"] == "GBO-1"

    def test_named_column_silent(self):
        assert find_unnamed_status_column(NAMED) == []

    def test_marker_in_header_found(self):
        """Разметка на строке, ставшей шапкой, — тоже недостижима для apply/reject."""
        hits = find_unnamed_status_column(MARKED_HEADER)
        assert len(hits) == 1
        assert hits[0]["task"] == "GBO-2" and hits[0]["line"] == 1

    def test_no_double_reporting(self):
        """Однострочная таблица: шапка и строка совпадают — находка должна быть одна."""
        text = "| текст | -GBO-4 |\n| --- | --- |\n"
        assert len(find_unnamed_status_column(text)) == 1

    def test_table_without_markers_silent(self):
        assert find_unnamed_status_column("| a | b |\n| --- | --- |\n| 1 | 2 |\n") == []

    def test_code_block_silent(self):
        assert find_unnamed_status_column("```\n" + UNNAMED + "```\n") == []


class TestRepair:
    def test_empty_header_cell_gets_the_name(self):
        out, n = name_status_column(UNNAMED)
        assert n == 1 and "| Код | Текст | status |" in out

    def test_rows_become_reachable(self):
        """Смысл починки: apply/reject перестают пропускать таблицу."""
        assert process_text(UNNAMED, "reject", None)[1] == 0      # до починки не видит
        out, _ = name_status_column(UNNAMED)
        cleaned, count = process_text(out, "reject", None)
        assert count == 1 and "новая" not in cleaned

    def test_marked_header_keeps_its_marker(self):
        out, n = name_status_column(MARKED_HEADER)
        assert n == 1
        lines = out.splitlines()
        assert lines[0].endswith("| status |")                    # шапка добавлена сверху
        assert "-GBO-2" in out                                    # маркер не потерян
        assert find_unnamed_status_column(out) == []

    def test_header_wrapped_in_inline_marker(self):
        """Самый неудобный случай выгрузки: шапка внутри {++TASK: … — тоже чинится."""
        out, n = name_status_column(WRAPPED_HEADER)
        assert n == 1 and find_unnamed_status_column(out) == []
        assert "{++GBO-3:" in out and "-GBO-3" in out

    def test_named_column_untouched(self):
        assert name_status_column(NAMED) == (NAMED, 0)

    def test_table_without_markers_untouched(self):
        src = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
        assert name_status_column(src) == (src, 0)

    def test_idempotent(self):
        once, _ = name_status_column(UNNAMED)
        assert name_status_column(once) == (once, 0)

    def test_text_outside_tables_untouched(self):
        src = "# Заголовок\n\nПроза со словом status.\n\n" + UNNAMED
        out, _ = name_status_column(src)
        assert out.startswith("# Заголовок\n\nПроза со словом status.\n")

    def test_crlf_preserved(self):
        out, n = name_status_column(UNNAMED.replace("\n", "\r\n"))
        assert n == 1 and "\r\n" in out
        assert out.replace("\r\n", "").count("\n") == 0
