# tests/test_branch_form_notation.py
"""ПР-15 ОНБ-В (волна 5, стандарт notation.md §1 «Форма ветвления — одна»):
**то** / **иначе** открывают строку — в ячейке после `<br>`, вне таблиц строкой
списка; слово-исход посреди строки после **Если** — предупреждение, вердикт не
меняется."""
from pathlib import Path

from app.scripts.CI.normalize_tables import branch_form_offenders, check_file


def off(text: str):
    return branch_form_offenders(text.split("\n"))


# ---------------------------------------------------------------- несрабатывание

def test_br_form_in_cell_silent():
    assert off("| FLD-1 | **Если** X,<br>**то** Y,<br>**иначе** Z |") == []


def test_nbsp_nested_form_from_notation_silent():
    cell = ("| FLD-2 | **Если** поле заполнено,<br>**то**:<br>&nbsp;&nbsp;&nbsp;&nbsp;**Если** "
            "«Код типа счета» == 2,<br>&nbsp;&nbsp;&nbsp;&nbsp;**то** отображается,<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;**иначе** не отображается,<br>**иначе** скрыто. |")
    assert off(cell) == []


def test_nested_list_form_silent():
    text = ("- **Если** поле заполнено,\n"
            "  - **то**:\n"
            "    - **Если** «Код типа счета» == 2,\n"
            "      - **то** отображается,\n"
            "      - **иначе** не отображается,\n"
            "  - **иначе** скрыто.")
    assert off(text) == []


def test_bullet_after_br_and_else_if_silent():
    assert off("| x | **Если** A,<br>• **то** B,<br>• **иначе если** C,<br>• **то** D |") == []


def test_code_block_and_inline_code_silent():
    assert off("```text\n**Если** X, **то** Y\n```") == []
    assert off("Образец: `**Если** X, **то** Y` — не по норме.") == []


def test_bold_to_without_if_silent():
    assert off("Нажмите на **то** поле, которое подсвечено.") == []


# ---------------------------------------------------------------- срабатывание

def test_if_then_one_line_in_cell():
    assert off("| FLD-1 | **Если** X, **то** Y |") == ["**Если** X, **то** Y"]


def test_list_item_if_then_else_one_line_counted_once():
    assert len(off("- **Если** X, **то** Y, **иначе** Z")) == 1


def test_else_inside_then_segment_after_br():
    assert off("| x | **Если** X,<br>**то** Y, **иначе** Z |") == ["**то** Y, **иначе** Z"]


def test_check_file_reports_warning_without_verdict(tmp_path: Path):
    p = tmp_path / "fun-cl-01.md"
    p.write_text("---\nid: FUN-CL-01\ntype: function\nservice: x\n---\n\n# Ф\n\n"
                 "- **Если** X, **то** Y\n", encoding="utf-8")
    rep, ok = check_file(p)
    line = next((ln for ln in rep if ln.startswith("предупреждение: форма ветвления")), "")
    assert "×1" in line and "notation §1" in line, rep
    assert ok
