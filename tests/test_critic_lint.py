# tests/test_critic_lint.py
#
# Тесты линтера (Модуль 3, ТЗ п. 6): по одному на каждое правило-ошибку E1-E7 и на
# предупреждения W1-W2, плюс «чистый файл» и коды возврата CLI. Правило W3 («висящий»
# маркер по дате коммита) отложено по согласованию — здесь не проверяется.

import json

import pytest

from app.scripts.CI.critic import lint_text, main


def _rules(text):
    return {f.rule for f in lint_text(text)}


class TestLintErrors:
    """Правила-ошибки п. 6 — по одному тесту на правило."""

    def test_e1_literal_nesting(self):
        assert "E1" in _rules("{++GBO-1: a {++GBO-2: b++} c++}")

    def test_e2_marker_without_id(self):
        assert "E2" in _rules("{++ текст без идентификатора++}")

    def test_e2_marker_bad_id(self):
        assert "E2" in _rules("{++bad-id: текст++}")

    def test_e3_unknown_placeholder(self):
        assert "E3" in _rules("{++UNKNOWN-9966ff: действующая++}организация")

    def test_e4_unclosed_marker(self):
        assert "E4" in _rules("начало {++GBO-1: без закрытия и дальше текст\n")

    def test_e5_marker_in_fenced_block(self):
        text = "```\n{++GBO-1: x++}\n```\n"
        assert "E5" in _rules(text)

    def test_e5_marker_crosses_table_row(self):
        text = "| ID | Значение |\n| --- | --- |\n| C-1 | {++GBO-1: начало\nконец++} |\n"
        assert "E5" in _rules(text)

    def test_e5_marker_crosses_paragraph(self):
        text = "Абзац один {++GBO-1: начало\n\nконец++} дальше\n"
        assert "E5" in _rules(text)

    def test_e6_marker_inside_smartlink(self):
        assert "E6" in _rules("См. {{CC: {++GBO-1: x++}}} хвост")

    def test_e7_criticmarkup_inside_raw_html(self):
        text = "<table><tr><td>{++GBO-1: x++}</td></tr></table>"
        assert "E7" in _rules(text)


class TestLintWarnings:
    """Предупреждения п. 6."""

    def test_w1_different_tasks_in_one_sentence(self):
        text = "Проверка {++GBO-1: a++} и {++GBO-2: b++} вместе."
        assert "W1" in _rules(text)

    def test_w1_not_raised_across_sentence_boundary(self):
        text = "Первое {++GBO-1: a++}. Второе {++GBO-2: b++}."
        assert "W1" not in _rules(text)

    def test_w2_deleted_text_matches_other_task_insertion(self):
        text = "Тут {++GBO-2: действующая++}. А там {--GBO-1: действующая--}."
        assert "W2" in _rules(text)


class TestLintClean:
    """Корректная разметка не порождает находок."""

    def test_single_valid_marker_is_clean(self):
        assert lint_text("Обычный текст {++GBO-1: слово++} и всё.") == []

    def test_smartlink_and_brackets_are_clean(self):
        text = "См. {{CC: [OTP] Запрос}} и <атрибут> — {++GBO-1: новое++} тут."
        assert lint_text(text) == []

    def test_marker_in_own_line_not_in_table_is_clean(self):
        # Одиночный корректный многострочный маркер вне таблицы/списка — не ошибка.
        assert lint_text("до {++GBO-1: одна строка++} после") == []


class TestLintCli:
    """CLI lint: коды возврата и форматы вывода."""

    def test_errors_return_nonzero(self, tmp_path):
        (tmp_path / "bad.md").write_bytes("{++UNKNOWN-abc: x++}".encode("utf-8"))
        assert main(["lint", "--path", str(tmp_path)]) == 1

    def test_clean_returns_zero(self, tmp_path):
        (tmp_path / "ok.md").write_bytes("текст {++GBO-1: x++} конец".encode("utf-8"))
        assert main(["lint", "--path", str(tmp_path)]) == 0

    def test_warnings_only_return_zero(self, tmp_path):
        (tmp_path / "warn.md").write_bytes(
            "Проверка {++GBO-1: a++} и {++GBO-2: b++} вместе.".encode("utf-8"))
        assert main(["lint", "--path", str(tmp_path)]) == 0

    def test_json_format_is_valid(self, tmp_path, capsys):
        (tmp_path / "bad.md").write_bytes("{++UNKNOWN-abc: x++}".encode("utf-8"))
        rc = main(["lint", "--path", str(tmp_path), "--format", "json"])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert any(item["rule"] == "E3" for item in payload)
        assert all({"path", "line", "level", "rule", "message"} <= set(item) for item in payload)
