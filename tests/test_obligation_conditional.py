"""Колонка «Обяз.»: форма «условно — [CTL-NNN …](…)» шаблона screen-form (замечание ОНБ-В 68,
2026-11-07). Остальной словарь — без изменений."""
import pytest

from app.scripts.CI.kitcheck.columns import _looks_like_obligation, validate_columns


@pytest.mark.parametrize("v", [
    "условно — [CTL-012 Проверка заполнения КПП](../../control/cards-org.md#ctl-012)",
    "Условно — [CTL-009 КПП: обязательность заполнения](../../control/cards-org.md#ctl-009)",
    "условно — текст условия",
    "условно",
    "Условно",
    "**условно** — [CTL-012 Проверка](x.md)",
])
def test_conditional_valid(v):
    assert _looks_like_obligation(v)


@pytest.mark.parametrize("v", [
    "условно обязателен",          # не форма шаблона: без тире
    "условно, если заполнен счёт",  # запятая вместо тире
    "условно —",                    # тире без хвоста
    "условность",
    "безусловно",
    "Обязательно, если выбран тип",
])
def test_not_template_form_still_invalid(v):
    assert not _looks_like_obligation(v)


@pytest.mark.parametrize("v", ["Да", "Нет", "О", "Н", "-", "", "Да, если не заполнен адрес"])
def test_old_dictionary_unchanged(v):
    assert _looks_like_obligation(v)


def test_screen_form_registry_column_full_valid():
    headers = ["FLD", "Поле", "Тип", "Обяз."]
    rows = [
        ["FLD-1", "ИНН", "Строка", "Да"],
        ["FLD-2", "КПП", "Строка",
         "условно — [CTL-009 КПП: обязательность заполнения](../../control/cards-org.md#ctl-009)"],
        ["FLD-3", "Комментарий", "Строка", "Нет"],
        ["FLD-4", "ОГРН", "Строка", "условно"],
    ]
    col = next(c for c in validate_columns(headers, rows, path_index=None) if c["role"] == "обязат")
    assert col["bad"] == 0 and col["valid_pct"] == 100.0


def test_free_text_in_obligation_column_still_counted_bad():
    # НЕсрабатывание снятия: свободный текст в колонке остаётся вне словаря
    headers = ["Поле", "Обяз."]
    rows = [["ИНН", "Да"], ["КПП", "условно обязателен при ИП"]]
    col = next(c for c in validate_columns(headers, rows, path_index=None) if c["role"] == "обязат")
    assert col["bad"] == 1
