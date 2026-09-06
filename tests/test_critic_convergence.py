# tests/test_critic_convergence.py
#
# Инцидент 2026-09-06: reject-all по дереву [КК] не доводил дело до конца за один
# прогон. Причина — блок кода, накрывший требования: экспортёр приклеивает ``` к
# содержимому ячейки, и одиночное ограждение открывает мнимый блок до конца файла
# (в одном файле такой блок занимал 20 689 символов и прятал 65 маркеров). Первый
# проход убирает разметку вокруг, границы блока схлопываются, и остаток становится
# виден только следующему проходу.
#
# Здесь закрыты обе стороны: правило CommonMark отсекает мнимые ограждения (после
# него на боевом дереве вместо трёх файлов второго прохода требуют два), а сама
# правка доводится до неподвижной точки внутри команды.
#
# Гонять команду руками до «файлов изменено 0» — источник ошибок: аналитик не
# обязан помнить про повтор, а тихо недоочищенное дерево уезжает в «чистый ПРОМ».
# Поэтому правка доводится до неподвижной точки внутри самой команды.

import pytest

from app.scripts.CI.critic import (
    CriticError, MAX_EDIT_PASSES, find_markers_in_code,
    process_file_verbose, process_text, process_text_until_stable,
)

# Форма из выгрузки (страница ЭКО_Получение-данных-одной-корпоративной-карты):
# закрыватель маркера склеен с ``` — это не ограждение, а следом идёт одиночное
# ограждение, открывающее мнимый блок до конца файла. Снятие правки выше убирает
# склейку, строка становится настоящим ограждением, блок закрывается — и спрятанное
# требование становится видно только следующему проходу.
FENCE_SWALLOWED = "\n".join([
    "<table><tbody>",
    '<tr class="critic-row-ins" data-task="GBO-1"><td>раз</td></tr>',
    "</tbody></table>",
    "",
    "{++GBO-2: пример++}```",
    "Статус укрупненный",
    "```",
    "{++GBO-3: требование, спрятанное блоком++}",
    "",
])


class TestOnePassIsNotEnough:
    def test_single_pass_leaves_a_tail(self):
        """Базовый факт, ради которого всё: один проход не доводит до конца."""
        once, first = process_text(FENCE_SWALLOWED, "reject", None)
        assert first >= 1
        _twice, second = process_text(once, "reject", None)
        assert second >= 1, "образец должен требовать второго прохода"

    def test_until_stable_finishes_the_job(self):
        out, total, passes = process_text_until_stable(FENCE_SWALLOWED, "reject", None)
        assert passes > 1
        assert total >= 2
        assert process_text(out, "reject", None)[1] == 0     # дальше снимать нечего

    def test_result_equals_manual_repetition(self):
        """Сходимость — это ровно повтор той же операции, без новой семантики."""
        manual, _ = process_text(FENCE_SWALLOWED, "reject", None)
        while True:
            nxt, n = process_text(manual, "reject", None)
            manual = nxt
            if n == 0:
                break
        auto, _total, _passes = process_text_until_stable(FENCE_SWALLOWED, "reject", None)
        assert auto == manual


class TestStableInputUntouched:
    def test_clean_text_needs_one_pass(self):
        text = "{++GBO-1: обычная вставка++}\n"
        out, total, passes = process_text_until_stable(text, "apply", None)
        assert passes == 1 and total == 1
        assert out == "обычная вставка\n"

    def test_nothing_to_do_is_not_a_change(self):
        text = "просто текст\n"
        out, total, passes = process_text_until_stable(text, "reject", None)
        assert (out, total, passes) == (text, 0, 0)   # менять нечего — проходов ноль

    def test_code_without_markers_untouched(self):
        text = "```\nprint('hello')\n```\n"
        out, total, _ = process_text_until_stable(text, "reject", None)
        assert out == text and total == 0


class TestOscillationIsAnError:
    def test_cap_raises_instead_of_looping(self, monkeypatch):
        """Молча крутиться в цикле хуже, чем упасть с указанием файла."""
        calls = {"n": 0}

        def never_stable(text, op, task_id, status_column=None, path=None):
            calls["n"] += 1
            return text + "x", 1

        monkeypatch.setattr("app.scripts.CI.critic.process_text", never_stable)
        with pytest.raises(CriticError, match="не сходятся"):
            process_text_until_stable("текст", "reject", None, max_passes=3)
        assert calls["n"] == 3

    def test_default_cap_is_sane(self):
        assert 2 < MAX_EDIT_PASSES <= 20


class TestThroughFile:
    def test_file_written_once_in_final_state(self, tmp_path):
        path = tmp_path / "страница.md"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("---\nstatus: draft\n---\n\n" + FENCE_SWALLOWED)
        count, passes = process_file_verbose(path, "reject", None)
        assert passes > 1 and count >= 2
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        assert "{++" not in text                      # ничего не осталось на второй заход
        assert process_file_verbose(path, "reject", None) == (0, 0)   # идемпотентность

    def test_untouched_file_reports_no_passes(self, tmp_path):
        path = tmp_path / "чистая.md"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("# Заголовок\n\nбез разметки\n")
        assert process_file_verbose(path, "reject", None) == (0, 0)


class TestFenceRecognition:
    """
    Строка со склеенным inline-кодом — не ограждение (правило CommonMark: инфо-строка
    backtick-ограждения не может содержать обратную кавычку). В выгрузке таких строк
    хватает: экспортёр приклеивает ``` к содержимому ячейки, и раньше они открывали
    мнимую код-зону, накрывавшую требования.
    """

    def _kinds(self, text):
        from app.scripts.CI.critic import _split_fenced_regions
        return [k for k, _r, _l in _split_fenced_regions(text)]

    def test_inline_code_line_is_not_a_fence(self):
        text = '```"filter"``: {`\n{++GBO-1: требование++}\n'
        assert self._kinds(text) == ["text"]
        assert process_text(text, "reject", None)[1] == 1     # маркер обработан

    def test_closing_backtick_line_is_not_a_fence(self):
        assert self._kinds("```}`\n{++GBO-1: текст++}\n") == ["text"]

    def test_real_fence_still_works(self):
        assert self._kinds("```\nкод\n```\n") == ["code"]

    def test_fence_with_language_still_works(self):
        assert self._kinds("```json\n{}\n```\n") == ["code"]

    def test_tilde_fence_untouched(self):
        assert self._kinds("~~~\nкод\n~~~\n") == ["code"]

    def test_marker_inside_real_fence_still_protected(self):
        """Сужение правила не должно вскрывать настоящий код."""
        text = "```\n{++GBO-1: текст++}\n```\n"
        assert process_text(text, "reject", None) == (text, 0)


class TestMarkersInCodeDetector:
    def test_block_with_markers_found(self):
        found = find_markers_in_code(FENCE_SWALLOWED)
        assert len(found) == 1
        assert found[0]["markers"] == 1 and found[0]["tasks"] == ["GBO-3"]
        assert found[0]["chars"] > 0 and found[0]["line"] >= 1

    def test_html_notation_counted_too(self):
        text = '```\n<tr class="critic-row-ins" data-task="GBO-9"><td>x</td></tr>\n```\n'
        found = find_markers_in_code(text)
        assert len(found) == 1 and found[0]["tasks"] == ["GBO-9"]

    def test_honest_code_is_silent(self):
        assert find_markers_in_code("```\nSELECT * FROM t\n```\n") == []

    def test_markers_outside_code_are_silent(self):
        assert find_markers_in_code("{++GBO-1: текст++}\n") == []
