"""Подраздел «Из источника, вне разделов шаблона» (норма канона 2026-10-26, шаблон function §6):
строка i с числом строк (видна и у ✓ карточки); форма подраздела (пустота, положение) не
проверяется — решение владельца канона 2026-10-26; карточка без подраздела — ни одной строки."""
from app.scripts.CI.kitcheck.core import is_soft_signal
from app.scripts.CI.kitcheck.checks.card_source import check_outside_template_section

HEAD = "---\nid: FUN-BNK-01\ntype: function\n---\n\n# Функция\n\n## 1. Назначение\n\nТекст.\n\n"
SECTION = ("## Из источника, вне разделов шаблона\n\n"
           "- Какие методы закрывает функция: `/admin/access-rule/{id}/history`\n")


def test_present_info_line_visible_for_green_card():
    rep, ok = check_outside_template_section(HEAD + SECTION)
    assert ok
    assert rep == ["i подраздел вне шаблона: 1 строк"]
    assert is_soft_signal(rep[0])
    # префикс неглавной карточки группы не прячет строку
    assert is_soft_signal("[scr-cl-09.1-details.md] " + rep[0])


def test_absent_no_lines():
    rep, ok = check_outside_template_section(HEAD + "## 2. Доступность\n\nВсем.\n")
    assert ok and rep == []


def test_empty_section_only_zero_count_no_warning():
    # пустой подраздел виден по «0 строк»; предупреждения о форме нет
    rep, ok = check_outside_template_section(HEAD + "## Из источника, вне разделов шаблона\n\n<!-- нет -->\n")
    assert ok and rep == ["i подраздел вне шаблона: 0 строк"]


def test_not_last_h2_no_warning_count_until_next_h2():
    # положение не проверяется; строки считаются до следующего H2
    rep, ok = check_outside_template_section(HEAD + SECTION + "\n## 5. Связанные артефакты\n\n- x\n- y\n")
    assert ok and rep == ["i подраздел вне шаблона: 1 строк"]


def test_h3_inside_section_is_part_of_it():
    card = HEAD + SECTION + "\n### Ещё\n\n- Лейбл: значение\n"
    rep, _ = check_outside_template_section(card)
    assert rep == ["i подраздел вне шаблона: 3 строк"]


def test_numbered_heading_and_yo_recognized():
    card = HEAD + "## 6. Из источника, вне разделов шаблона\n\n- Лейбл: значение\n"
    assert check_outside_template_section(card)[0] == ["i подраздел вне шаблона: 1 строк"]


def test_heading_in_code_block_ignored():
    card = HEAD + "```markdown\n## Из источника, вне разделов шаблона\n```\n"
    assert check_outside_template_section(card) == ([], True)


def test_other_heading_not_matched():
    # похожее имя — не норма, молчит
    card = HEAD + "## Из источника\n\n- x\n"
    assert check_outside_template_section(card) == ([], True)
