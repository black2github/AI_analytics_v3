# tests/test_unapproved_wrap.py
#
# Форс-обёртка неутверждённого состава (эмуляция похода в RAG, 2026-08-07):
# срабатывание на чистом контенте, НЕсрабатывание на чужих маркерах и коде,
# сквозной цикл с critic (reject-all → пусто, apply → чистый состав).

from app.unapproved_wrap import wrap_unapproved
from app.scripts.CI.critic import process_text

T = "GBO-500"


class TestBlocks:
    def test_paragraph_wrapped(self):
        out, rep = wrap_unapproved("Просто требование.", T)
        assert out == "{++GBO-500: Просто требование.++}"
        assert rep["blocks"] == 1

    def test_heading_wrapped_whole_line(self):
        # заголовок оборачивается ЦЕЛИКОМ (вместе с #): reject-all не оставляет «# »
        out, _ = wrap_unapproved("# Раздел\n\nТекст.", T)
        assert "{++GBO-500: # Раздел++}" in out
        assert "{++GBO-500: Текст.++}" in out

    def test_multiline_list_single_marker(self):
        out, rep = wrap_unapproved("- один\n- два\n- три", T)
        assert out == "{++GBO-500: - один\n- два\n- три++}"
        assert rep["blocks"] == 1

    def test_empty_lines_stay_outside_markers(self):
        out, _ = wrap_unapproved("Абзац один.\n\nАбзац два.\n", T)
        assert out == "{++GBO-500: Абзац один.++}\n\n{++GBO-500: Абзац два.++}\n"


class TestForeignMarkers:
    def test_existing_marker_stays_sibling_not_nested(self):
        src = "До. {++GBO-1: чужая вставка++} После."
        out, _ = wrap_unapproved(src, T)
        assert "{++GBO-1: чужая вставка++}" in out          # чужой маркер нетронут
        assert "{++GBO-500: До. ++}" in out
        assert "{++GBO-500:  После.++}" in out
        # вложенности нет: внутри нашей вставки нет чужих опенеров
        assert "GBO-1" not in out.split("{++GBO-500")[1].split("++}")[0]

    def test_deletion_marker_untouched(self):
        src = "{--GBO-2: снятый текст--}"
        out, rep = wrap_unapproved(src, T)
        assert out == src
        assert rep["blocks"] == 0


class TestFencedCode:
    def test_code_not_wrapped_with_warning(self):
        src = "Текст.\n\n```xml\n<Body/>\n```\n"
        out, rep = wrap_unapproved(src, T)
        assert "```xml\n<Body/>\n```" in out                # код байт-в-байт
        assert "{++GBO-500: Текст.++}" in out
        assert rep["code_blocks_skipped"] == 1
        assert rep["warnings"]


class TestMarkdownTables:
    def test_table_without_status_wrapped_whole(self):
        src = "| a | b |\n|---|---|\n| 1 | 2 |"
        out, rep = wrap_unapproved(src, T)
        assert out == "{++GBO-500: | a | b |\n|---|---|\n| 1 | 2 |++}"
        assert rep["tables_wrapped"] == 1

    def test_table_with_foreign_status_marked_per_row(self):
        src = ("| a | status |\n"
               "|---|---|\n"
               "| чужая | +GBO-9 |\n"
               "| наша |  |")
        out, rep = wrap_unapproved(src, T)
        assert "| чужая | +GBO-9 |" in out                  # чужая строка нетронута
        assert "| наша | +GBO-500 |" in out
        assert rep["table_rows"] == 1
        assert "{++" not in out                             # обёртки целиком нет


class TestHtmlIslands:
    def test_clean_island_wrapped_whole(self):
        src = '<table><tr><td>x</td></tr></table>'
        out, rep = wrap_unapproved(src, T)
        assert out == "{++GBO-500: " + src + "++}"
        assert rep["tables_wrapped"] == 1

    def test_island_with_foreign_rows_marked_per_tr(self):
        src = ('<table><tr><th>ID</th></tr>'
               '<tr class="critic-row-ins" data-task="GBO-9"><td>чужая</td></tr>'
               '<tr><td>наша</td></tr></table>')
        out, rep = wrap_unapproved(src, T)
        assert 'data-task="GBO-9"' in out
        assert '<tr class="critic-row-ins" data-task="GBO-500"><td>наша</td></tr>' in out
        assert "<tr><th>ID</th></tr>" in out                # шапка не помечена
        assert rep["island_rows"] == 1


class TestRoundTripWithCritic:
    def test_reject_all_empties_apply_keeps(self):
        src = ("# Функция\n\nОписание требования.\n\n"
               "| a | b |\n|---|---|\n| 1 | 2 |\n")
        wrapped, _ = wrap_unapproved(src, T)
        rejected, _ = process_text(wrapped, "reject-all", None)
        assert "Описание" not in rejected and "| 1 | 2 |" not in rejected
        applied, _ = process_text(wrapped, "apply", T)
        assert applied == src                               # состав принят байт-в-байт

    def test_idempotent_on_rewrap(self):
        src = "Текст требования."
        once, _ = wrap_unapproved(src, T)
        twice, rep = wrap_unapproved(once, T)
        assert twice == once                                # повторная обёртка — no-op
        assert rep["blocks"] == 0
