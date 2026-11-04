# tests/test_columns_silent_formula.py
"""Сторож колонок и формула пробела источника «в постановке не задано» (2026-11-04): карточка
по шаблону module-interface не бракуется; прочие заполнители и порог — как прежде."""
from pathlib import Path

from app.scripts.CI.kitcheck import md
from app.scripts.CI.kitcheck.checks import content
from app.scripts.CI.kitcheck.columns import _is_section_row, _is_silent_formula, validate_columns

F = "в постановке не задано"
HEADERS = ["Код параметра", "Наименование параметра", "Тип", "Обяз.", "Кратность", "Правила заполнения"]


def rows(n=4, code=F, card=F, oblig="Да"):
    return [[code, f"Параметр {i}", F, oblig, card, f"правило {i}"] for i in range(n)]


def by_col(report):
    return {c["column"]: c for c in report}


def test_formula_one_home():
    assert md.SILENT_FORMULA == F
    assert content._SILENT_FORMULA == md.SILENT_FORMULA
    # дом один: в content.py формула импортируется, а не задаётся заново
    assert "_SILENT_FORMULA = " not in Path(content.__file__).read_text(encoding="utf-8")


def test_formula_valid_in_path_and_cardinality():
    cols = by_col(validate_columns(HEADERS, rows(), path_index=0))
    for name in ("Код параметра", "Кратность"):
        assert (cols[name]["bad"], cols[name]["total"], cols[name]["valid_pct"]) == (0, 4, 100.0)


def test_other_placeholder_still_bad():
    # НЕсрабатывание послабления: «не задано» без «в постановке» — брак, как прежде
    r = rows()
    r[0][4] = "не задано"
    cols = by_col(validate_columns(HEADERS, r, path_index=0))
    assert (cols["Кратность"]["bad"], cols["Кратность"]["valid_pct"]) == (1, 75.0)
    assert cols["Кратность"]["samples"] == ["не задано"]
    assert cols["Код параметра"]["bad"] == 0


def test_other_values_of_roles_unchanged():
    # прежнее поведение ролей: пустой путь валиден, предложение в пути — брак, голая кратность — брак
    r = rows(1, code="") + rows(1, code="это целое предложение тут") + rows(1, card="1") + rows(1, card="[1]")
    cols = by_col(validate_columns(HEADERS, r, path_index=0))
    assert cols["Код параметра"]["samples"] == ["это целое предложение тут"]
    assert cols["Кратность"]["samples"] == ["1"]


def test_markup_and_exact_match():
    assert _is_silent_formula(f"**{F}**")
    assert _is_silent_formula(f"*{F}*")
    assert _is_silent_formula(f"  {F} ")
    assert _is_silent_formula("В постановке не задано")
    assert not _is_silent_formula(f"{F}, см. п. 3")
    assert not _is_silent_formula("не задано")
    assert not _is_silent_formula("")
    assert not _is_silent_formula("В ПОСТАНОВКЕ НЕ ЗАДАНО")
    cols = by_col(validate_columns(HEADERS, rows(1, card=f"**{F}**"), path_index=0))
    assert cols["Кратность"]["bad"] == 0
    cols = by_col(validate_columns(HEADERS, rows(1, card=f"{F}, см. п. 3"), path_index=0))
    assert cols["Кратность"]["bad"] == 1


def test_obligation_role():
    cols = by_col(validate_columns(HEADERS, rows(1, oblig=F) + rows(1, oblig="Да") + rows(1, oblig="Нет"),
                                   path_index=0))
    assert cols["Обяз."]["bad"] == 0
    cols = by_col(validate_columns(HEADERS, rows(1, oblig="возможно"), path_index=0))
    assert cols["Обяз."]["bad"] == 1


def test_obligation_pair_role():
    headers = ["Код", "Обязательность / Уникальность"]
    cols = by_col(validate_columns(headers, [["a", F], ["b", "Да / Да"]], path_index=0))
    assert cols[headers[1]]["bad"] == 0
    cols = by_col(validate_columns(headers, [["a", "возможно / да"]], path_index=0))
    assert cols[headers[1]]["bad"] == 1


def test_source_mode_unchanged():
    # при нормализации источника послабления нет
    cols = by_col(validate_columns(HEADERS, rows(1), path_index=0, source_mode=True))
    assert cols["Код параметра"]["bad"] == 1


def test_row_of_formulas_is_data_not_section():
    # строка параметра, где заполнены только имя и формулы, — данные: раньше считалась заголовком
    # группы, а таблица из таких строк давала 0% [0/0]
    row = [F, "Имя", F, "", F, ""]
    assert not _is_section_row(row)
    cols = by_col(validate_columns(HEADERS, [row, row], path_index=0))
    assert (cols["Код параметра"]["total"], cols["Код параметра"]["valid_pct"]) == (2, 100.0)
    # настоящая строка-раздел — по-прежнему раздел
    assert _is_section_row(["Реквизиты операции"] * 5)
