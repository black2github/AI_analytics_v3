# tests/test_critic_apply_reject.py
#
# Тесты Модуля 2 (app/scripts/CI/critic.py), Этап 1 ТЗ: apply / reject / apply-all /
# reject-all, обе нотации. Нумерация ссылается на ТЗ п. 9 (тесты 15-22) плюс защита
# синтаксиса (тест 13) и hard-fail на вложенности/незакрытости (п. 5.3, 6).

import pytest

from app.scripts.CI.critic import (
    process_text, process_file, main, CriticError, postpass_drop_contained_deletions,
)


class TestInlineIsolation:
    """15. apply одной задачи не трогает маркеры других задач в той же строке."""

    def test_apply_touches_only_target_task(self):
        text = "a {++GBO-1: x++} b {++GBO-2: y++} c"
        out, n = process_text(text, "apply", "GBO-1")
        assert out == "a x b {++GBO-2: y++} c"
        assert n == 1

    def test_reject_touches_only_target_task(self):
        text = "a {++GBO-1: x++} b {--GBO-2: y--} c"
        out, n = process_text(text, "reject", "GBO-2")
        assert out == "a {++GBO-1: x++} b y c"
        assert n == 1


class TestApplyRejectRoundTrip:
    """16. apply и reject на исходном тексте дают, соответственно, целевое состояние и ПРОМ.

    Прим.: строго последовательное apply→reject НЕ тождественно (apply снимает маркер,
    и reject его уже не видит) — это не инверсия, а две разные операции над одним исходником
    (ТЗ п. 5.2). Здесь проверяем ровно определение из таблицы п. 5.2 и байтовую сохранность
    неразмеченного текста.
    """

    ORIGINAL = "a {++GBO-1: X++}b {--GBO-1: Y--}c {~~GBO-1: O~>N~~}d"

    def test_apply_gives_target_state(self):
        out, n = process_text(self.ORIGINAL, "apply", "GBO-1")
        assert out == "a Xb c Nd"
        assert n == 3

    def test_reject_gives_prom_state(self):
        out, n = process_text(self.ORIGINAL, "reject", "GBO-1")
        assert out == "a b Yc Od"
        assert n == 3


class TestIdempotency:
    """17. Повторный apply не меняет уже обработанный файл (ТЗ п. 5.3)."""

    def test_second_apply_is_noop(self, tmp_path):
        fp = tmp_path / "doc.md"
        fp.write_bytes("до {++GBO-1: вставка++} после\n".encode("utf-8"))

        n1 = process_file(fp, "apply", "GBO-1")
        assert n1 == 1
        bytes_after_first = fp.read_bytes()

        n2 = process_file(fp, "apply", "GBO-1")
        assert n2 == 0
        assert fp.read_bytes() == bytes_after_first  # файл не перезаписан


class TestMultilineMarker:
    """18. Многострочный маркер (открыт на одной строке, закрыт через абзацы)."""

    def test_multiline_insertion(self):
        text = "старт {++GBO-1: строка один\n\nстрока два++} финиш"
        out, n = process_text(text, "apply", "GBO-1")
        assert out == "старт строка один\n\nстрока два финиш"
        assert n == 1


class TestFencedCodeBlock:
    """19. Маркер внутри fenced code block не обрабатывается (ТЗ п. 5.3)."""

    def test_marker_in_fence_untouched(self):
        text = (
            "```\n"
            "{++GBO-1: x++}\n"
            "```\n"
            "снаружи {++GBO-1: y++}\n"
        )
        out, n = process_text(text, "apply", "GBO-1")
        assert "{++GBO-1: x++}" in out          # внутри кода — нетронуто
        assert "снаружи y\n" in out             # снаружи — применено
        assert n == 1


class TestMarkdownTableStatus:
    """20. markdown-таблица: обработка столбца status и его удаление при обнулении (ТЗ п. 5.2)."""

    def test_apply_clears_and_drops_status_column(self):
        text = (
            "| a | b | status |\n"
            "| --- | --- | --- |\n"
            "| 1 | x | +GBO-1 |\n"
            "| 2 | y |  |\n"
        )
        out, n = process_text(text, "apply", "GBO-1")
        expected = (
            "| a | b |\n"
            "| --- | --- |\n"
            "| 1 | x |\n"
            "| 2 | y |\n"
        )
        assert out == expected
        assert n == 1

    def test_apply_minus_row_is_dropped(self):
        # status=-ID: apply → удалить строку (ТЗ п. 5.2). Столбец остаётся, т.к. в нём
        # ещё есть непустое значение другой задачи.
        text = (
            "| a | status |\n"
            "| --- | --- |\n"
            "| 1 | -GBO-1 |\n"
            "| 2 | +GBO-2 |\n"
        )
        out, n = process_text(text, "apply", "GBO-1")
        expected = (
            "| a | status |\n"
            "| --- | --- |\n"
            "| 2 | +GBO-2 |\n"
        )
        assert out == expected
        assert n == 1

    def test_reject_plus_row_is_dropped(self):
        text = (
            "| a | status |\n"
            "| --- | --- |\n"
            "| 1 | +GBO-1 |\n"
            "| 2 | +GBO-2 |\n"
        )
        out, n = process_text(text, "reject", "GBO-1")
        expected = (
            "| a | status |\n"
            "| --- | --- |\n"
            "| 2 | +GBO-2 |\n"
        )
        assert out == expected
        assert n == 1

    def test_inline_marker_inside_cell(self):
        # Правка внутри ячейки — обычный CriticMarkup, обрабатывается inline-пасом.
        text = (
            "| ID | V1 | V2 |\n"
            "| --- | --- | --- |\n"
            "| C-1 | V | {++GBO-1: V++} |\n"
        )
        out, n = process_text(text, "apply", "GBO-1")
        assert out == (
            "| ID | V1 | V2 |\n"
            "| --- | --- | --- |\n"
            "| C-1 | V | V |\n"
        )
        assert n == 1


class TestTableRobustness:
    """Крайние случаи pipe-таблиц: экранированный пайп в ячейке и рваные строки."""

    def test_escaped_pipe_in_cell_preserved_on_column_drop(self):
        text = (
            "| a | b | status |\n"
            "| --- | --- | --- |\n"
            "| x \\| y | z | +GBO-1 |\n"
        )
        out, n = process_text(text, "apply", "GBO-1")
        assert out == (
            "| a | b |\n"
            "| --- | --- |\n"
            "| x \\| y | z |\n"
        )
        assert n == 1

    def test_ragged_row_not_corrupted_on_column_drop(self):
        text = (
            "| a | status |\n"
            "| --- | --- |\n"
            "| рваная строка без статуса |\n"
            "| 2 | +GBO-1 |\n"
        )
        out, n = process_text(text, "apply", "GBO-1")
        assert out == (
            "| a |\n"
            "| --- |\n"
            "| рваная строка без статуса |\n"
            "| 2 |\n"
        )
        assert n == 1


class TestHtmlNotation:
    """21. HTML-нотация: атрибуты в произвольном порядке, вложенное содержимое (ТЗ п. 4.7)."""

    def test_span_ins_apply_unwraps_attrs_any_order(self):
        html = ('<table><tr><td>'
                '<span data-task="GBO-1" class="critic-ins">новая <b>жирная</b> </span>'
                'хвост</td></tr></table>')
        out, n = process_text(html, "apply", "GBO-1")
        assert out == '<table><tr><td>новая <b>жирная</b> хвост</td></tr></table>'
        assert n == 1

    def test_span_ins_reject_removes_content(self):
        html = ('<table><tr><td>'
                '<span class="critic-ins" data-task="GBO-1">новая </span>хвост'
                '</td></tr></table>')
        out, n = process_text(html, "reject", "GBO-1")
        assert out == '<table><tr><td>хвост</td></tr></table>'
        assert n == 1

    def test_span_del_apply_removes_content(self):
        html = ('<table><tr><td>'
                '<span class="critic-del" data-task="GBO-1">старое</span>хвост'
                '</td></tr></table>')
        out, n = process_text(html, "apply", "GBO-1")
        assert out == '<table><tr><td>хвост</td></tr></table>'
        assert n == 1

    def test_row_ins_apply_strips_class_and_data_task(self):
        html = ('<table><tr class="critic-row-ins" data-task="GBO-1"><td>x</td></tr></table>')
        out, n = process_text(html, "apply", "GBO-1")
        assert out == '<table><tr><td>x</td></tr></table>'
        assert n == 1

    def test_row_del_apply_removes_row(self):
        html = ('<table>'
                '<tr class="critic-row-del" data-task="GBO-1"><td>x</td></tr>'
                '<tr><td>y</td></tr></table>')
        out, n = process_text(html, "apply", "GBO-1")
        assert out == '<table><tr><td>y</td></tr></table>'
        assert n == 1

    def test_html_other_task_untouched(self):
        html = ('<table><tr><td>'
                '<span class="critic-ins" data-task="GBO-2">z</span>'
                '</td></tr></table>')
        out, n = process_text(html, "apply", "GBO-1")
        assert out == html
        assert n == 0


class TestCrlfPreserved:
    """22. Файл с CRLF: переводы строк сохранены (ТЗ п. 2.3, 11.7)."""

    def test_crlf_preserved_after_apply(self, tmp_path):
        fp = tmp_path / "crlf.md"
        raw = "строка один\r\nдо {++GBO-1: вставка ++}после\r\nстрока три\r\n"
        fp.write_bytes(raw.encode("utf-8"))

        n = process_file(fp, "apply", "GBO-1")
        assert n == 1

        data = fp.read_bytes()
        assert b"\r\n" in data
        # Ни одного «голого» LF (каждый \n должен быть частью \r\n).
        assert data.count(b"\n") == data.count(b"\r\n")
        assert data.decode("utf-8") == "строка один\r\nдо вставка после\r\nстрока три\r\n"


class TestSyntaxProtection:
    """13. Фрагмент со смарт-ссылкой, именами в скобках, угловыми скобками и стрелками."""

    def test_special_syntax_not_eaten_by_markers(self):
        text = ("См. {{CC: [OTP] Запрос}} и <атрибут сущности> и стрелки -> => ~>. "
                "{++GBO-1: действующая ++}организация")
        out, n = process_text(text, "apply", "GBO-1")
        assert out == ("См. {{CC: [OTP] Запрос}} и <атрибут сущности> и стрелки -> => ~>. "
                       "действующая организация")
        assert n == 1


class TestHardFail:
    """Неоднозначность → hard-fail с прерыванием (ТЗ п. 5.3, 6)."""

    def test_nested_markers_raise(self):
        text = "{++GBO-1: a {++GBO-2: b++} c++}"
        with pytest.raises(CriticError):
            process_text(text, "apply", "GBO-1")

    def test_unclosed_marker_raises(self):
        text = "начало {++GBO-1: без закрытия и дальше текст"
        with pytest.raises(CriticError):
            process_text(text, "apply", "GBO-1")

    def test_error_carries_path_and_line(self, tmp_path):
        fp = tmp_path / "bad.md"
        fp.write_bytes("строка 1\nстрока 2 {++GBO-1: x {++GBO-2: y++}++}\n".encode("utf-8"))
        with pytest.raises(CriticError) as ei:
            process_file(fp, "apply", "GBO-1")
        assert ei.value.line == 2
        assert ei.value.path == fp


class TestPostpassContainedDeletions:
    """ТЗ 4.5.4: {--C2: X--}, где X входит в состав чужой вставки, отбрасывается пост-проходом."""

    def test_10_contained_deletion_dropped(self):
        text = ("{++GBO-2: добавлено старое условие теперь++} и {--GBO-1: старое условие--}.")
        new, dropped = postpass_drop_contained_deletions(text)
        assert "{--GBO-1: старое условие--}" not in new   # отброшено (черновик, не ПРОМ)
        assert len(dropped) == 1 and dropped[0]["insert_task"] == "GBO-2"

    def test_11_partial_substring_not_dropped(self):
        # Частичное совпадение (не вхождение целиком) → не трогаем.
        text = ("{++GBO-2: добавлено старое условие++} и "
                "{--GBO-1: старое условие иное целиком--}.")
        new, dropped = postpass_drop_contained_deletions(text)
        assert "{--GBO-1: старое условие иное целиком--}" in new
        assert dropped == []

    def test_same_task_not_dropped(self):
        text = "{++GBO-1: старое условие тут++} и {--GBO-1: старое условие--}."
        new, dropped = postpass_drop_contained_deletions(text)
        assert "{--GBO-1: старое условие--}" in new
        assert dropped == []


class TestRejectRestoresDeletion:
    """ТЗ тест 30: reject дословно восстанавливает текст {--ID: X--} (семантика п. 4.5.1)."""

    def test_30_reject_restores_deleted_text(self):
        out, n = process_text("на месте {--GBO-1: старое условие--} конец", "reject", "GBO-1")
        assert out == "на месте старое условие конец"
        assert n == 1


class TestApplyAllRejectAll:
    """apply-all / reject-all: обработка всех задач (task_id=None)."""

    def test_apply_all_collapses_every_task(self):
        text = "{++GBO-1: a++} {--GBO-2: b--} {~~GBO-3: o~>n~~}"
        out, n = process_text(text, "apply", None)
        assert out == "a  n"
        assert n == 3

    def test_reject_all_collapses_every_task(self):
        text = "{++GBO-1: a++} {--GBO-2: b--} {~~GBO-3: o~>n~~}"
        out, n = process_text(text, "reject", None)
        assert out == " b o"
        assert n == 3


class TestCli:
    """CLI: dry-run ничего не пишет; невалидный ID отвергается."""

    def test_dry_run_does_not_write(self, tmp_path, capsys):
        fp = tmp_path / "d.md"
        raw = "до {++GBO-1: вставка++} после\n".encode("utf-8")
        fp.write_bytes(raw)

        rc = main(["apply", "GBO-1", "--path", str(fp), "--dry-run"])
        assert rc == 0
        assert fp.read_bytes() == raw  # файл не тронут

    def test_invalid_task_id_rejected(self, tmp_path):
        fp = tmp_path / "d.md"
        fp.write_bytes(b"x")
        with pytest.raises(SystemExit):
            main(["apply", "не-задача", "--path", str(fp)])
