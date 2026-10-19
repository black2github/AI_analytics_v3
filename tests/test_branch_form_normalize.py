# tests/test_branch_form_normalize.py
"""Нормализация формы ветвления в ячейках таблиц (решение владельца 2026-10-19; стандарт
notation.md §1): «**Если** X, **то** Y, **иначе** Z» одной строкой ячейки → через `<br>`;
вне таблиц, литералы в кавычках, код, вложенное условие и маркер списка — не трогаются."""
from pathlib import Path

from app.scripts.CI.normalize_tables import (branch_form_offenders, normalize_branch_form,
                                             run_branch_form)


def norm(text: str):
    return normalize_branch_form(text)


# ---------------------------------------------------------------- срабатывание

def test_one_line_cell_split_by_br():
    out, n, _s = norm("| FLD-1 | **Если** X, **то** Y, **иначе** Z |")
    assert out == "| FLD-1 | **Если** X,<br>**то** Y,<br>**иначе** Z |" and n == 2


def test_then_else_after_br_split_and_result_silent():
    out, n, _s = norm("| x | **Если** X,<br>**то** Y, **иначе** Z |")
    assert out == "| x | **Если** X,<br>**то** Y,<br>**иначе** Z |" and n == 1
    assert branch_form_offenders([out]) == []


def test_nbsp_indent_carried_to_new_lines():
    src = "| x | **Если** A,<br>**то**:<br>&nbsp;&nbsp;**Если** B, **то** C, **иначе** D |"
    out, n, _s = norm(src)
    assert out == ("| x | **Если** A,<br>**то**:<br>&nbsp;&nbsp;**Если** B,<br>&nbsp;&nbsp;**то** C,"
                   "<br>&nbsp;&nbsp;**иначе** D |") and n == 2


def test_idempotent_and_crlf_kept():
    src = "| a | b |\r\n|---|---|\r\n| x | **Если** X, **то** Y |\r\n"
    out, n, _s = norm(src)
    assert n == 1 and "\r\n" in out and "\n" not in out.replace("\r\n", "")
    again, n2, _s2 = norm(out)
    assert again == out and n2 == 0


def test_run_write_keeps_bom_and_dry_run_does_not_write(tmp_path: Path, capsys):
    p = tmp_path / "proc-001.md"
    p.write_bytes(b"\xef\xbb\xbf| x | **\xd0\x95\xd1\x81\xd0\xbb\xd0\xb8** X, **\xd1\x82\xd0\xbe** Y |\n")
    before = p.read_bytes()
    run_branch_form([p], write=False)
    assert p.read_bytes() == before and "переносов 1" in capsys.readouterr().out
    run_branch_form([p], write=True)
    assert p.read_bytes().startswith(b"\xef\xbb\xbf") and b"<br>" in p.read_bytes()


# ---------------------------------------------------------------- несрабатывание

def test_outside_tables_untouched():
    src = "- **Если** X, **то** Y\n\n**Если** A, **то** B."
    assert norm(src) == (src, 0, {})


def test_literal_in_quotes_untouched():
    src = '| MSG-1 | Текст: «**Если** вы не согласны, **то** обратитесь в банк» |'
    out, n, _s = norm(src)
    assert out == src and n == 0
    src2 = '| MSG-2 | Текст: "**Если** нет, **то** нет" |'
    assert norm(src2)[0] == src2


def test_code_untouched():
    src = "```text\n| x | **Если** X, **то** Y |\n```"
    assert norm(src)[1] == 0
    src2 = "| x | `**Если** X, **то** Y` |"
    assert norm(src2)[0] == src2


def test_nested_condition_left_to_human():
    src = "| x | **Если** A, **то** **Если** B, **то** C |"
    out, n, skipped = norm(src)
    assert out == src and n == 0 and skipped == {"вложенное условие": 1}


def test_list_marker_in_cell_left_to_human():
    src = "| x | Формирование:<br>• **Если** A, **то** B |"
    out, n, skipped = norm(src)
    assert out == src and n == 0 and skipped == {"маркер списка в ячейке": 1}


def test_lawful_form_untouched():
    src = "| x | **Если** X,<br>**то** Y,<br>**иначе** Z |"
    assert norm(src) == (src, 0, {})
