# tests/test_branch_form_normalize.py
"""Нормализация формы ветвления (решения владельца 2026-10-19; стандарт notation.md §1;
FB-24 КК, решение А): «**Если** X, **то** Y, **иначе** Z» одной строкой → через `<br>` — в
ячейках, элементах списков и абзацах; заголовки, шапка, код, комментарии, литералы в кавычках
и вложенное условие — не трогаются."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.card_branch_form import branch_form_offenders
from app.scripts.CI.kitcheck.branch_form import normalize_branch_form
from app.scripts.CI.normalize_tables import run_branch_form


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

def test_headings_code_frontmatter_comment_untouched():
    src = ("---\ntitle: '**Если** X, **то** Y'\n---\n\n# **Если** X, **то** Y\n\n"
           "```text\n- **Если** X, **то** Y\n```\n\n<!-- **Если** X, **то** Y -->\n"
           "<!--\n**Если** A, **то** B\n-->\n")
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


def test_list_marker_in_cell_split():
    # FB-24: маркер списка больше не причина пропуска — маркер остаётся в начале отрезка
    out, n, skipped = norm("| x | Формирование:<br>• **Если** A, **то** B |")
    assert out == "| x | Формирование:<br>• **Если** A,<br>**то** B |" and n == 1 and skipped == {}


def test_lawful_form_untouched():
    src = "| x | **Если** X,<br>**то** Y,<br>**иначе** Z |"
    assert norm(src) == (src, 0, {})


# ---------------------------------------------------------------- FB-24: списки и абзацы

def test_list_item_with_label():
    src = "- **Логика проверки:** **Если** поле заполнено, **то** проверка пройдена, **иначе** ошибка."
    out, n, _s = norm(src)
    assert out == ("- **Логика проверки:** **Если** поле заполнено,<br>**то** проверка пройдена,"
                   "<br>**иначе** ошибка.") and n == 2


def test_list_item_then_at_end_children_not_moved():
    src = "  - **Если** заявка подписана, **то**:\n    - отправить уведомление;\n    - сменить статус."
    out, n, _s = norm(src)
    assert out == ("  - **Если** заявка подписана,<br>**то**:\n    - отправить уведомление;\n"
                   "    - сменить статус.") and n == 1


def test_paragraph_and_numbered_item():
    kinds = {}
    out, n, _s = normalize_branch_form("Договор: **Если** счёт открыт, **то** печать.\n\n"
                                       "1. **Если** A, **то** B.", kinds)
    assert out == "Договор: **Если** счёт открыт,<br>**то** печать.\n\n1. **Если** A,<br>**то** B."
    assert n == 2 and kinds == {"абзацы": 1, "списки": 1}


def test_nested_outside_table_skipped():
    src = "- **Если** A, **то** **Если** B, **то** C"
    out, n, skipped = norm(src)
    assert out == src and n == 0 and skipped == {"вложенное условие": 1}


def test_lawful_form_outside_table_untouched():
    src = "- **Если** X,<br>**то** Y,<br>**иначе** Z\n\n**Если** A,<br>**то** B."
    assert norm(src) == (src, 0, {})


def test_else_if_chain_split():
    out, n, _s = norm("- **Если** A, **то** B, **иначе если** C, **то** D")
    assert out == "- **Если** A,<br>**то** B,<br>**иначе если** C,<br>**то** D" and n == 3


def test_guard_silent_after_write():
    src = ("| x | **Если** X, **то** Y |\n\n- **Логика проверки:** **Если** A, **то** B, **иначе** C.\n\n"
           "**Если** P, **то** Q.\n\n  - **Если** R, **то**:\n    - S\n")
    assert len(branch_form_offenders(src.split("\n"))) == 4
    out, n, _s = norm(src)
    assert n == 5 and branch_form_offenders(out.split("\n")) == []


def test_else_comma_if_chain_split_not_nested():
    # «**иначе**, **если** …» и «**Иначе** (**если** …)» — цепочка, не вложенность
    out, n, sk = norm("4. **иначе**, **если** `<Категория>` = `4`, **то**:")
    assert out == "4. **иначе**, **если** `<Категория>` = `4`,<br>**то**:" and n == 1 and sk == {}
    out, n, sk = norm("- **Логика проверки:** **Если** A, **то** B, **иначе**, **если** C, **то** D")
    assert out == "- **Логика проверки:** **Если** A,<br>**то** B,<br>**иначе**, **если** C,<br>**то** D", out
    assert n == 3 and sk == {}


def test_mention_of_construction_in_prose_untouched():
    # описание конструкции в шаблонах и правилах — не ветвление: ни переноса, ни ⚠ (FB-24)
    for src in ("8. Логика: ветвления в форме **Если**/**то**/**иначе** (жирным), шаги.",
                "- слова **Если**, **то**, **иначе**, **иначе если** выделяются жирным",
                "    флаг согласия) — ветвлением «**Если** …, **то** …,"):
        assert norm(src) == (src, 0, {}), src
        assert branch_form_offenders([src]) == [], src


def test_mention_limiter_does_not_hide_real_branch():
    # условие из одного инлайн-кода или ссылки — содержание, перенос и ⚠ на месте
    src = "- **Если** `<Категория>`, **то** ошибка"
    assert branch_form_offenders([src]) != []
    assert norm(src)[0] == "- **Если** `<Категория>`,<br>**то** ошибка"
    out, n, _s = norm("**Если** [ENT-1](e.md), **то** печать.")
    assert n == 1 and out == "**Если** [ENT-1](e.md),<br>**то** печать."


def test_guard_skips_outcome_inside_guillemets():
    # симметрия защит: цитата «…» в примечании — ни ⚠ сторожа, ни переноса нормализатора
    src = ("**Примечание:** источник контролей формулирует проверку как «**Если** поле пусто, "
           "**то** ошибка», в карточке — как в источнике.")
    assert branch_form_offenders([src]) == []
    assert norm(src) == (src, 0, {})


def test_guard_still_flags_branch_outside_guillemets():
    # настоящее ветвление вне кавычек — ⚠ по-прежнему, даже рядом с цитатой
    src = "- **Если** статус «Отказ», **то** текст «**Если** вы не согласны, **то** звоните»"
    assert len(branch_form_offenders([src])) == 1
    out, n, _s = norm(src)
    assert n == 1 and out.startswith("- **Если** статус «Отказ»,<br>**то** текст «**Если**")
    assert branch_form_offenders([out]) == []
