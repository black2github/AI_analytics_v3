# -*- coding: utf-8 -*-
"""FB-02 сервиса «Обновление сведений» (2026-11-18): ячейка названия с правилом, записанная по
нотации техбука, — та же запись, что в источнике (сверка «дословно из источника»): подстановка
`<X>` без точки ≡ «X» (§7), `==` ≡ `=` внутри условия «если … то» (§2). Не сводится: вид кавычек
литерала (§7 — «не нормализуются никогда»), опущенное имя сущности перед реквизитом, пересказ."""
import pytest

from app.scripts.CI.kitcheck.columns import validate_columns
from app.scripts.CI.kitcheck.html import _norm_cell
from app.scripts.CI.kitcheck.md import norm_rule_notation

SRC = ('Пол: если [Физическое лицо в заявке].<Пол> = "male", то <Мужской>, '
       'иначе поле не заполняется')
CARD = ('Пол: **если** [Физическое лицо в заявке].«Пол» == "male", **то** «Мужской», '
        '**иначе** поле не заполняется')


def _name_report(card_cell: str, src_cell: str = SRC) -> dict:
    rows = [[card_cell, "Строка"], ["Фамилия", "Строка"]]
    rep = validate_columns(["Наименование", "Тип"], rows, path_index=None,
                           source_literals={"название": {_norm_cell(src_cell)}})
    return next(r for r in rep if r["role"] == "название")


@pytest.mark.parametrize("key,want", [
    ("то <фамилия>", "то «фамилия»"),
    ("если a == \"1\" то b", "если a = \"1\" то b"),
    ("если a то b == c", "если a то b == c"),             # после «то» — не условие
    ("x == y", "x == y"),                                   # без «если» — не условие
    ("a <br> b <p class=\"x\"> c", "a <br> b <p class=\"x\"> c"),  # HTML-тег — как есть
    ("если a == 1 то b, иначе если c == 2 то d", "если a = 1 то b, иначе если c = 2 то d"),
])
def test_norm_rule_notation(key, want):
    assert norm_rule_notation(key) == want


def test_rule_in_techbook_notation_pardoned():
    r = _name_report(CARD)
    assert r["suspicious_count"] == 0 and r["suspicious_pardoned_count"] == 1, r


def test_link_id_and_notation_pardoned():
    # ярлык ссылки чистовика с ID и нотация — вместе
    card = CARD.replace("[Физическое лицо в заявке]", "[ENT-010 Физическое лицо в заявке](../ent-010.md)")
    src = SRC.replace("[Физическое лицо в заявке]", "[Физическое лицо в заявке](../x.md)")
    r = _name_report(card, src)
    assert r["suspicious_count"] == 0 and r["suspicious_pardoned_count"] == 1, r


def test_dropped_entity_prefix_not_pardoned():
    # НЕсрабатывание: источник «то [Сущность].<Фамилия>», карточка «то «Фамилия»» — §7: голая
    # запись «Атрибут» без сущности не используется, расхождение — ✗
    src = SRC.replace("то <Мужской>", "то [Физическое лицо в заявке].<Фамилия>")
    card = CARD.replace("**то** «Мужской»", "**то** «Фамилия»")
    r = _name_report(card, src)
    assert r["suspicious_count"] == 1 and r["suspicious_pardoned_count"] == 0, r


def test_quote_style_not_pardoned():
    # НЕсрабатывание: кавычки литерала не сводятся («male» против "male")
    r = _name_report(CARD.replace('"male"', "«male»"))
    assert r["suspicious_count"] == 1, r


def test_paraphrase_not_pardoned():
    # НЕсрабатывание: пересказ — вставлено слово в ветку «то»
    r = _name_report(CARD.replace("**то** «Мужской»", "**то** выставляется «Мужской»"))
    assert r["suspicious_count"] == 1, r


def test_eq_after_then_not_pardoned():
    # НЕсрабатывание: `==` после «то» (присваивание источника `=`) — не условие, не сводится
    src = SRC.replace("то <Мужской>", "то Пол = 1")
    card = CARD.replace("**то** «Мужской»", "**то** Пол == 1")
    r = _name_report(card, src)
    assert r["suspicious_count"] == 1, r


def test_as_is_still_pardoned():
    r = _name_report(SRC)
    assert r["suspicious_count"] == 0 and r["suspicious_pardoned_count"] == 1, r
