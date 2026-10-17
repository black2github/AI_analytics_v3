# tests/test_kitcheck_fence.py
"""Правило границ блоков кода `kitcheck/fence.py` — тест поведения: таблица
строк → разметка «код / текст» и находки (решение владельца 2026-10-17,
независимая оценка сессии «КК и хвосты»: тест поведения вместо равенства
регулярок)."""

import re

from app.scripts.CI import critic
from app.scripts.CI.kitcheck import fence

# прежнее правило строки (critic._FENCE_RE до 2026-10-17) — для сравнения
_OLD_LINE_RE = re.compile(r"^[ \t]*(?:`{3,}[^`\n]*|~{3,}[^\n]*)\r?\n?$")


def code_lines(text):
    """Номера строк (с 1), размеченных как код."""
    lines = text.split("\n")
    return [k + 1 for k, c in enumerate(fence.code_flags(lines)) if c]


def kinds(text):
    return [(i.kind, i.line, i.close_line) for i in fence.issues(text.split("\n"))]


# --- строка-ограждение ------------------------------------------------------

def test_fence_line_rule():
    assert fence.fence_of("```") == ("`", 3, "")
    assert fence.fence_of("````markdown") == ("`", 4, "markdown")
    assert fence.fence_of("  ~~~~ python ") == ("~", 4, "python")
    assert fence.fence_of("\t```json") == ("`", 3, "json")       # табуляция в отступе
    assert fence.fence_of("```\r\n") == ("`", 3, "")              # CRLF
    assert fence.fence_of("﻿```") == ("`", 3, "")            # BOM первой строки
    for ln in ('```"filter"``: {', "```x```", "```}`", "``", "~~", "текст ```",
               "> ```", "}```"):
        assert fence.fence_of(ln) is None, ln


def test_line_rule_same_as_before():
    # правило одной строки не меняется против прежнего (меняется только вложенность)
    for ln in ("```", "```json", "~~~", "~~~ x ~~~", "````", "   ```py ", '```"a"``',
               "```x```", "text", "> ```", "\t~~~", "``` ` ", "~~~~"):
        assert (fence.fence_of(ln) is not None) == bool(_OLD_LINE_RE.match(ln)), ln


def test_critic_zones_use_module():
    # critic делит текст на зоны по тому же модулю: вложенный образец — одна зона кода
    text = "a\n````markdown\n```mermaid\n{++X-1: x++}\n```\n````\nb {++X-1: y++}\n"
    kinds_ = [k for k, _t, _s in critic._split_fenced_regions(text)]
    assert kinds_ == ["text", "code", "text"]
    assert "".join(t for _k, t, _s in critic._split_fenced_regions(text)) == text


# --- вложенность ------------------------------------------------------------

def test_inner_shorter_fence_is_content():
    text = "a\n````markdown\n## Раздел\n```mermaid\nx\n```\n## Ещё\n````\nb"
    assert code_lines(text) == [2, 3, 4, 5, 6, 7, 8]
    assert kinds(text) == []


def test_tilde_inside_backtick_and_back():
    assert code_lines("```\n~~~\nx\n~~~\n```\nt") == [1, 2, 3, 4, 5]
    assert code_lines("~~~\n```\nx\n```\n~~~\nt") == [1, 2, 3, 4, 5]


def test_three_levels():
    text = "`````\n````markdown\n```mermaid\nx\n```\n````\n`````\nt"
    assert code_lines(text) == [1, 2, 3, 4, 5, 6, 7]


def test_longer_closes_shorter_does_not():
    assert code_lines("````\nx\n```\ny\n`````\nt") == [1, 2, 3, 4, 5]


# --- находки ----------------------------------------------------------------

def test_close_with_info_closes_and_is_reported():
    # опечатка автора (eco-kb): ```text ... ```text — блок закрыт, текст ниже проверяется
    text = "п\n```text\nA - 1\n```text\n### Примеры xml\nтекст"
    assert code_lines(text) == [2, 3, 4]
    assert kinds(text) == [("close-with-info", 2, 4)]


def test_unclosed_with_content_reported():
    text = "п\n```\nкод\n\nещё"
    assert code_lines(text) == [2, 3, 4, 5]
    assert kinds(text) == [("unclosed", 2, 0)]


def test_lone_fence_last_line_not_reported():
    assert kinds("п\n```") == []
    assert kinds("п\n```\n\n   ") == []


def test_glued_close_is_not_a_fence():
    # приклеенное закрытие «}```» — не ограждение: блок открыт до конца
    text = "```scala\nval x = {\n}```\nтекст"
    assert code_lines(text) == [1, 2, 3, 4]
    assert kinds(text) == [("unclosed", 1, 0)]


# --- НЕсрабатывание ---------------------------------------------------------

def test_list_indent_and_tab():
    text = "1. Шаг:\n\n   ```powershell\n   git pull\n   ```\n\n\t~~~\n\tx\n\t~~~\nтекст"
    assert code_lines(text) == [3, 4, 5, 7, 8, 9]
    assert kinds(text) == []


def test_crlf_same_as_lf():
    lf = "a\n````\n```\nb\n````\nc"
    crlf_lines = lf.replace("\n", "\r\n").splitlines(keepends=True)
    assert fence.code_flags(crlf_lines) == fence.code_flags(lf.split("\n"))
    assert fence.issues(crlf_lines) == []


def test_glued_inline_and_triple_inline_not_fences():
    text = '```"params"``: {`\n## Раздел\n```x```\nтекст'
    assert code_lines(text) == [] and kinds(text) == []


def test_fence_in_quote_not_a_fence():
    assert code_lines("> ```\n> код\n> ```\nтекст") == []


def test_plain_text_and_empty():
    assert code_lines("") == [] and fence.issues([]) == []
    assert code_lines("# Заголовок\n\n| a | b |\n|---|---|\n") == []


def test_list_and_tuple_input_same():
    lines = ["```", "x", "```"]
    assert fence.blocks(lines) == fence.blocks(tuple(lines))
