# tests/test_table_escaped_pipe.py
"""Д-1 (исправлено 2026-10-17): экранированная вертикальная черта «\\|» внутри
ячейки pipe-таблицы — часть текста ячейки, не граница (GFM). Найдено при
рефакторинге прибора (REFACTOR_STATUS.md, «Подозрения на дефект»); в снимке
комплектов 17.10 такие строки были в КК, lk-mp, УЛ и эталоне.

Ограничитель: строки без «\\|» режутся ровно как раньше — тесты на
несрабатывание ниже."""
import pytest

from app.scripts.CI import link_debts as ld
from app.scripts.CI import normalize_tables as nt
from app.scripts.CI.kitcheck import md
from app.scripts.CI.kitcheck.checks import controls

ROW_WITH_ESCAPED_PIPE = "| 1.8 | досье\\|продукты |"


# ---------------------------------------------------------------- примитивы

def test_table_cells_keeps_escaped_pipe_in_cell():
    assert md.table_cells(ROW_WITH_ESCAPED_PIPE) == ["1.8", "досье\\|продукты"]


def test_escaped_backslash_before_pipe_is_a_boundary():
    # «\\\\|» — экранированный обратный слэш, за ним граница ячейки
    assert md.table_cells("| a\\\\| b |") == ["a\\\\", "b"]
    assert md.table_cells("| a\\\\\\|b | c |") == ["a\\\\\\|b", "c"]


def test_escaped_pipe_at_end_of_last_cell_is_kept():
    assert md.strip_row("| a | b\\|") == " a | b\\|"
    assert md.table_cells("| a | b\\|") == ["a", "b\\|"]


def test_count_cells_ignores_escaped_pipe():
    assert md.count_cells("| Код | A\\|B | C |") == 3
    assert md.count_cells("|---|---|---|") == 3


@pytest.mark.parametrize("line", [
    "| a | b |", "|a|b|", "  | a |  ", "| a |", "|| a || b ||", "| a | `x|y` |",
    "| пусто |  |", "| конец без черты", "без черт вовсе", "|", "",
])
def test_rows_without_escaped_pipe_split_as_before(line):
    """Несрабатывание: без «\\|» результат до символа прежний."""
    old = [c.strip() for c in line.strip().strip("|").split("|")]
    assert md.table_cells(line) == old
    assert md.strip_row(line) == line.strip().strip("|")
    assert md.split_cells(line) == line.split("|")


# ---------------------------------------------------------------- места разбора

def test_parse_md_tables_keeps_escaped_pipe_in_cell():
    text = "| Код | Значение |\n|---|---|\n" + ROW_WITH_ESCAPED_PIPE + "\n"
    (header, rows), = nt.parse_md_tables(text)
    assert len(rows[0]) == len(header) == 2, rows
    assert rows[0][1] == "досье\\|продукты", rows


def test_parse_md_tables_without_escaped_pipe_unchanged():
    text = "| Код | Значение |\n|---|---|\n| 1 | `x` |\n"
    assert nt.parse_md_tables(text) == [(["Код", "Значение"], [["1", "x"]])]


def test_link_debts_debt_name_keeps_escaped_pipe():
    """Имя долга сторож ищет в документах дословно; раньше «A\\|B»
    разбиралось как «A\\ B»."""
    text = ("# Матрица\n\n## Долги по ссылкам\n\n| Артефакт | Цель | Долг |\n| --- | --- | --- |\n"
            "| FUN-CL-01 | — | долг противоречие: «A\\|B» — вопрос OQ-1 |\n")
    _matrix, debts, _unrecognized = ld.parse_matrix_full(text)
    (_ids, _kind, name, _target, _row), = debts
    assert name == "A\\|B", name


def test_control_group_row_name_keeps_escaped_pipe():
    m = controls._GRP_ROW_RE.match("| CTL-GRP-01 | имя\\|два | x |")
    assert m and m.group(2).strip() == "имя\\|два"
    m = controls._GRP_ROW_C_RE.match("| CTL-GRP-02 | FE | привязка\\|вторая | x |")
    assert m and m.group(3).strip() == "привязка\\|вторая"


def test_control_group_row_without_escaped_pipe_unchanged():
    m = controls._GRP_ROW_RE.match("| CTL-GRP-01 | имя | x |")
    assert m.group(1) == "CTL-GRP-01" and m.group(2) == "имя "
    m = controls._GRP_ROW_C_RE.match("| [CTL-GRP-02] | BE | привязка | x |")
    assert m.group(2) == "BE" and m.group(3) == "привязка "
