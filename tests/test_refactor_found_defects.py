# tests/test_refactor_found_defects.py
"""Подозрения на дефект текущей реализации прибора, найденные при рефакторинге
без изменения функционала (ветка refactor/tool-structure, правило владельца
2026-10-17).

Каждый тест описывает поведение, которое ожидалось бы по норме, и помечен
`xfail(strict=True)`: сейчас он падает — дефект виден, набор остаётся зелёным.
Рефакторинг поведение не меняет; решение по каждому случаю — отдельно (см.
REFACTOR_STATUS.md, раздел «Подозрения на дефект текущей реализации»). Когда
дефект исправят, тест начнёт проходить и `strict=True` потребует снять пометку.
"""
import pytest

from app.scripts.CI import link_debts as ld
from app.scripts.CI import normalize_tables as nt

# Д-1. Экранированная вертикальная черта «\|» внутри ячейки таблицы.
# GFM: «\|» в ячейке — часть её текста, не граница. Все 14 мест разбора строки
# таблицы режут ячейку по «|», колонки строки сдвигаются. В снимке комплектов
# 17.10 такие строки есть: КК 8, lk-mp 11, УЛ 186, эталон 2.
ROW_WITH_ESCAPED_PIPE = "| 1.8 | досье\\|продукты |"


@pytest.mark.xfail(strict=True, reason="Д-1: «\\|» в ячейке режется как граница")
def test_d1_parse_md_tables_keeps_escaped_pipe_in_cell():
    text = "| Код | Значение |\n|---|---|\n" + ROW_WITH_ESCAPED_PIPE + "\n"
    (header, rows), = nt.parse_md_tables(text)
    assert len(rows[0]) == len(header) == 2, rows
    assert rows[0][1] in ("досье\\|продукты", "досье|продукты"), rows


@pytest.mark.xfail(strict=True, reason="Д-1: «\\|» в имени долга превращается в «\\ »")
def test_d1_link_debts_debt_name_keeps_escaped_pipe():
    """Имя долга сторож ищет в документах дословно; «A\\|B» разбирается как
    «A\\ B» — такое имя в документах не найдётся."""
    md = ("# Матрица\n\n## Долги по ссылкам\n\n| Артефакт | Цель | Долг |\n| --- | --- | --- |\n"
          "| FUN-CL-01 | — | долг противоречие: «A\\|B» — вопрос OQ-1 |\n")
    _matrix, debts, _unrecognized = ld.parse_matrix_full(md)
    (_ids, _kind, name, _target, _row), = debts
    assert name in ("A|B", "A\\|B"), name
