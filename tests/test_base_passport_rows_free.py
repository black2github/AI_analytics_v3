# -*- coding: utf-8 -*-
"""Базовый контракт внешней АС: строки таблицы-паспорта источника «Где используется» и
«Документация» в сверке с источником не требуются (шаблон contract-call.md, раздел A, решение
владельца 2026-11-08; опись наследия f1: EXTINT-F1-024…028 после выноса — ложные ✗)."""
from app.scripts.CI.kitcheck.checks.card_source import check_source_tables

SRC = ("---\ntitle: 'РКО Ф1. Представление \"Данные по счету\"'\n---\n\n"
       "| **Система:** | АБС РКО Ф1 |\n|---|---|\n"
       "| **Протокол взаимодействия:** | ODS |\n"
       "| **Где используется:** | РКО Ф1_ОА_Получение отчета по счету |\n"
       "| Документация | ТЗ_Ф1_Отчет по счету.docx |\n")
CARD = ("## 1. Краткое описание\n\n| Поле | Значение |\n|---|---|\n| **Система:** | АБС РКО Ф1 |\n"
        "| **Протокол взаимодействия:** | ODS |\n"
        "| Где используется | Потребители — в разделе «Потребители» и в docs сервисов |\n")


def test_base_contract_passport_rows_free():
    rep, ok = check_source_tables(CARD, SRC, base_contract=True)
    assert ok, rep
    assert any(r.startswith("i строки паспорта источника «Где используется» / «Документация» в базовом "
                            "контракте не требуются: 2") for r in rep), rep


def test_other_passport_value_still_required():
    # НЕсрабатывание: значение другой строки паспорта потеряно — ✗ как прежде
    rep, ok = check_source_tables(CARD.replace("| **Протокол взаимодействия:** | ODS |\n", ""), SRC,
                                  base_contract=True)
    assert not ok and any("в карточке отсутствуют 2 значений" in r for r in rep), rep   # лейбл и ODS


def test_not_base_contract_rows_required():
    # НЕсрабатывание: карточка не базовый контракт — строки паспорта сверяются как прежде
    rep, ok = check_source_tables(CARD, SRC)
    assert not ok and any("в карточке отсутствуют" in r for r in rep), rep


def test_multi_column_table_rows_required():
    # НЕсрабатывание: в таблице из трёх колонок ячейка «Где используется» — данные, не паспорт
    src = ("---\ntitle: X\n---\n\n| Параметр | Описание | Где используется |\n|---|---|---|\n"
           "| a | A | Где используется | \n| b | B | функция потребителя |\n")
    rep, ok = check_source_tables("| a | A |\n| b | B |\n", src, base_contract=True)
    assert not ok, rep
