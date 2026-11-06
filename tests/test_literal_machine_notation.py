# tests/test_literal_machine_notation.py
"""Кавычечный литерал внутри машинной записи — класс «примеры» (⚠), а не требование (✗):
общее правило по форме значения (решение владельца канона 2026-11-06)."""
from app.scripts.CI.kitcheck.checks.card_source import (
    _balanced_brackets, check_quoted_literals, machine_notation_literals, quoted_literals,
)

CARD = "---\nid: C\n---\n\n# Карточка\n\nтекст\n"


def src(body: str) -> str:
    return "---\ntitle: Т\n---\n\n" + body


def machine(body: str) -> set:
    return machine_notation_literals(src(body))


def check(body: str, card: str = CARD):
    return check_quoted_literals(card, src(body))


def lost_line(rep) -> str:
    return next((r for r in rep if "в карточке отсутствуют" in r and "✗" in r), "")


def examples_line(rep) -> str:
    return next((r for r in rep if r.startswith("⚠ примеры: машинная запись")), "")


CELL = '<table><tr><td>a</td><td>currencyCodes: {in: ["RUB", "USD", "EUR", "CNY"]}</td></tr></table>\n'


def test_html_cell_list_and_prose_occurrence():
    rep, ok = check('<p>Валюта "RUB" по умолчанию.</p>\n' + CELL)
    assert not ok
    assert "'CNY'" in examples_line(rep)
    assert "'RUB'" not in examples_line(rep) and "'RUB'" in lost_line(rep)
    assert any(r == "i кавычечные литералы: по правилу машинной записи снято 3" for r in rep), rep


def test_signals_visible_on_green_card():
    from app.scripts.CI.kitcheck.core import is_examples_signal, is_soft_signal
    rep, _ok = check(CELL)
    assert is_examples_signal(examples_line(rep)) and is_soft_signal(examples_line(rep))
    count = next(r for r in rep if r.startswith("i кавычечные литералы: по правилу"))
    assert is_soft_signal(count) and not is_examples_signal(count)


def test_all_machine_literals_listed_without_verdict():
    rep, ok = check(CELL)
    assert ok, rep
    line = examples_line(rep)
    for v in ("RUB", "USD", "EUR", "CNY"):
        assert repr(v) in line
    assert "кавычечные литералы источника: тексты и значения вне примеров на месте ✓" in rep


def test_unquoted_prose_occurrence_keeps_requirement():
    # вхождение в обычном тексте без кавычек — тоже проза
    rep, ok = check("<p>По умолчанию RUB.</p>\n" + CELL)
    assert not ok and "'RUB'" in lost_line(rep)


def test_pipe_table_cell():
    body = '| Поле | Значение |\n|---|---|\n| a | currencyCodes: {in: ["RUB", "CNY"]} |\n| b | c |\n'
    assert {"rub", "cny"} <= machine(body)
    assert check(body)[1]


def test_escaped_brackets_in_pipe_cell():
    body = '| Поле | Значение |\n|---|---|\n| a | codes: {in: \\["RUB", "CNY"\\]} |\n| b | c |\n'
    assert {"rub", "cny"} <= machine(body)


def test_key_value_object():
    assert "корпоративная расчетная карта" in machine('<p>productName: {eq: "Корпоративная расчетная карта"}</p>\n')


def test_json_with_quoted_keys():
    got = machine('<p>"multiSort": [{"direction": "ASC", "field": "inn"}]</p>\n')
    assert {"direction", "asc", "field", "inn"} <= got


def test_escaped_tag_attribute_is_not_notation():
    # НЕсрабатывание: запись вида тега — не машинная запись, значение требуется
    body = '<p>&lt;egrul датаВыг="2022-06-14" xmlns=""&gt;</p>\n'
    assert machine(body) == set()
    rep, ok = check(body)
    assert not ok and "'2022-06-14'" in lost_line(rep)


def test_real_markup_attribute_not_a_literal():
    # атрибут настоящего HTML-тега разметки — как прежде: не литерал
    body = '<p class="critic-del">текст</p>\n<p><span data-task="GBO-1">x</span></p>\n'
    assert quoted_literals(src(body)) == []
    assert check(body)[1]


def test_assignment_is_condition_not_notation():
    # НЕсрабатывание: присваивание — условие логики, значение требуется при любом ключе
    for body in ('<p>State = "Suspended"</p>\n', '<p>ErrorCode = "BSN003"</p>\n',
                 '<table><tr><td>meta.channel = "BOL"</td><td>x</td></tr></table>\n'):
        assert machine(body) == set(), body
        rep, ok = check(body)
        assert not ok and lost_line(rep), body


def test_assignment_next_to_notation_keeps_requirement():
    # одно и то же значение в присваивании и в объекте: присваивание — обычный текст, значение требуется
    body = '<p>{a: "ACTIVE"}</p>\n<p>state = "ACTIVE"</p>\n'
    assert "active" not in machine(body)
    rep, ok = check(body)
    assert not ok and "'ACTIVE'" in lost_line(rep)


def test_array_or_object_after_equals_is_assignment():
    # присваивание остаётся присваиванием при любом типе значения: потеря — ✗
    for body in ('<p>status = ["ACTIVE", "LIQUIDATING"]</p>\n',
                 '- query = текст\n- status = ["ACTIVE", "LIQUIDATING"]\n- count = "5"\n',
                 '<p>status={"state": "ACTIVE", "kind": "LIQUIDATING"}</p>\n',
                 '<p>status == ["ACTIVE", "LIQUIDATING"]</p>\n',
                 '<p>status != ["ACTIVE", "LIQUIDATING"]</p>\n',
                 '<p>status = <b>["ACTIVE", "LIQUIDATING"]</b></p>\n',
                 '| Поле | Значение |\n|---|---|\n| a | status = \\["ACTIVE", "LIQUIDATING"\\] |\n| b | c |\n'):
        assert not {"active", "liquidating"} & machine(body), body
        rep, ok = check(body)
        assert not ok and "'ACTIVE'" in lost_line(rep), body
        assert not examples_line(rep), body


def test_nested_value_of_assignment_is_not_notation():
    # вложенный массив с ключом — часть значения присваивания
    body = '<p>filter = {status: ["ACTIVE", "LIQUIDATING"]}</p>\n'
    assert machine(body) == set()
    rep, ok = check(body)
    assert not ok and "'LIQUIDATING'" in lost_line(rep)


def test_colon_notation_stays_example():
    # НЕсрабатывание правила присваивания: запись через двоеточие — по-прежнему класс «примеры»
    for body in (CELL, '<p>status: ["ACTIVE", "LIQUIDATING"]</p>\n',
                 '<p>currencyCodes: {in: ["RUB", "USD"]}</p>\n'):
        assert machine(body), body
        rep, ok = check(body)
        assert ok and examples_line(rep), body


def test_equals_elsewhere_in_fragment_does_not_cancel_notation():
    # «=» в этом же абзаце, но не перед скобкой: запись остаётся записью
    body = '<p>count = 5, filter: {status: ["ACTIVE", "LIQUIDATING"]}</p>\n'
    assert {"active", "liquidating"} <= machine(body)
    assert check(body)[1]


def test_prose_occurrence_of_phrase_keeps_requirement():
    # НЕсрабатывание: то же словосочетание в кавычках в прозе
    body = ('<p>Продукт "Корпоративная расчетная карта" выбран.</p>\n'
            '<p>productName: {eq: "Корпоративная расчетная карта"}</p>\n')
    rep, ok = check(body)
    assert not ok and "Корпоративная расчетная карта" in lost_line(rep)
    assert not examples_line(rep)


def test_unbalanced_open_bracket_keeps_requirement():
    # НЕсрабатывание: незакрытая скобка перед литералом
    rep, ok = check('<p>currencyCodes: {in: "CNY"</p>\n')
    assert not ok and "'CNY'" in lost_line(rep)


def test_unbalanced_extra_close_cancels_segment():
    assert machine('<p>x] {a: "CNY"}</p>\n') == set()


def test_cyrillic_assignment_is_prose():
    # НЕсрабатывание вида 3: кириллица перед «=»
    rep, ok = check('<p>Статус = "Новый"</p>\n')
    assert not ok and "'Новый'" in lost_line(rep)
    assert machine('<p>Статус = "Новый"</p>\n') == set()


def test_fragment_crossing_cell_boundary():
    # НЕсрабатывание: запись пересекает </td>
    body = '<table><tr><td>{a: "CNY"</td><td>}</td></tr></table>\n'
    rep, ok = check(body)
    assert not ok and "'CNY'" in lost_line(rep)


def test_crossing_pipe_cell_boundary():
    body = '| A | B |\n|---|---|\n| {a: "CNY" | } |\n| x | y |\n'
    rep, ok = check(body)
    assert not ok and "'CNY'" in lost_line(rep)


def test_crossing_empty_line():
    rep, ok = check('{a: "CNY"\n\n}\n')
    assert not ok and "'CNY'" in lost_line(rep)


def test_window_longer_than_limit():
    rep, ok = check('<p>{a: "CNY", b: "' + "x" * 75 + '", c: "' + "y" * 2000 + '"}</p>\n')
    assert not ok and "'CNY'" in lost_line(rep)


def test_brackets_without_key_or_list_are_prose():
    for body in ('<p>[значение "CNY"]</p>\n', '<p>{ "CNY" }</p>\n', '<p>[Примечание: "CNY"]</p>\n',
                 '<p>{Если статус: "CNY"}</p>\n', '<p>["CNY"]</p>\n'):
        assert machine(body) == set(), body
        rep, ok = check(body)
        assert not ok and "'CNY'" in lost_line(rep), body


def test_round_brackets_never():
    assert machine('<p>(a: "CNY", b: "USD")</p>\n') == set()


def test_markdown_link_is_not_notation():
    assert machine('<p>[status: "CNY"](http://x/y)</p>\n') == set()


def test_code_block_plus_machine_is_example():
    # вхождения только в блоке кода и в машинной записи — без обычного текста
    body = '<p>{a: "CNY"}</p>\n<pre>{ "b": "CNY" }</pre>\n'
    rep, ok = check(body)
    assert ok, rep


def test_literal_present_in_card_no_signal():
    card = CARD + "\nзначения RUB USD EUR CNY\n"
    rep, ok = check(CELL, card)
    assert ok and not examples_line(rep)
    assert not any(r.startswith("i кавычечные литералы") for r in rep)


def test_quoted_literals_unchanged_for_other_consumers():
    # перечень литералов прежний: правило работает только в сверке карточки
    assert set(quoted_literals(src(CELL))) == {"RUB", "USD", "EUR", "CNY"}


def test_balanced_brackets_ignore_quoted_brackets():
    assert _balanced_brackets('{a: "}"}') == [(0, 8)]
    assert _balanced_brackets('{a: "b}') == []
