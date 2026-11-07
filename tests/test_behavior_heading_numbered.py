# tests/test_behavior_heading_numbered.py
"""Заголовок раздела «Поведение» с номером: сторожа шагов работают на «## 5. Поведение» так же, как
на «## Поведение». Прежде на нумерованном заголовке они молча не работали."""
import pytest

from app.scripts.CI.kitcheck.checks.card_steps import (
    behavior_steps_from_card, check_behavior_nesting, check_behavior_numbering)

GLUED = "{head}\n\nШаг №1: Сделать\nШаг №2: Завершить\n"
STEPS = "{head}\n\n1. Первый шаг\n2. Второй шаг\n\n## Следующий раздел\n\n3. Не шаг\n"
OK_STEPS = "{head}\n\n- 1. Первый шаг\n- 2. Второй шаг\n"
HEADS = ["## Поведение", "## 5. Поведение", "## 12. Поведение", "##  5.  Поведение  "]


@pytest.mark.parametrize("head", HEADS)
def test_glued_steps_fire_on_both_headings(head):
    rep, ok = check_behavior_numbering(GLUED.format(head=head))
    assert not ok and "склеит" in rep[0]


@pytest.mark.parametrize("head", HEADS)
def test_list_steps_pass_on_both_headings(head):
    assert check_behavior_numbering(OK_STEPS.format(head=head))[1]


@pytest.mark.parametrize("head", HEADS)
def test_steps_read_from_section_only(head):
    assert [c for c, _ in behavior_steps_from_card(STEPS.format(head=head))] == ["1", "2"]


@pytest.mark.parametrize("head", ["## Поведение функции", "## 5 Поведение", "## 5.1. Поведение",
                                  "### 5. Поведение", "## Раздел 5. Поведение"])
def test_other_headings_not_taken(head):
    assert behavior_steps_from_card(STEPS.format(head=head)) == []
    assert check_behavior_numbering(GLUED.format(head=head)) == ([], True)


def test_section_ends_at_next_numbered_heading():
    text = "## 5. Поведение\n\n- 1. Шаг\n\n## 6. Вызов\n\n1. Не шаг\n2. Не шаг\n"
    assert check_behavior_numbering(text)[1]
    assert [c for c, _ in behavior_steps_from_card(text)] == ["1"]


def test_nesting_reads_numbered_heading():
    src = ("<table><tr><td><strong>Что делает функция</strong></td><td>"
           "<p>1. Первый</p><p>2. Второй</p></td></tr></table>\n")
    card = "## 5. Поведение\n\n- 1. Первый\n- 2. Второй\n"
    assert check_behavior_nesting(card, src)[1]
