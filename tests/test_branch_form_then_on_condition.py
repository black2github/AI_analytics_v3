# tests/test_branch_form_then_on_condition.py
"""Норма от 2026-11-06: **то** на строке условия, исходы вложенным списком, **иначе** с новой
строки. Сторож проверяет только **иначе** / **иначе если** (и вложенное условие в одном отрезке),
нормализатор переносит только их, уже стоящий `<br>**то**` не убирает. Признак «то/иначе без
исхода» — по форме записи: пункт кончается на **то** или **иначе**, следом текст не глубже него;
⚠, вердикт не меняет."""
from pathlib import Path

import pytest

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.branch_form import normalize_branch_form
from app.scripts.CI.kitcheck.checks.card_branch_form import (
    branch_form_counts, branch_form_offenders, branch_no_outcome
)
from app.scripts.CI.kitcheck.checks.card_run import check_file


def off(text: str):
    return branch_form_offenders(text.split("\n"))


def lost(text: str):
    return branch_no_outcome(text.split("\n"))


def norm(text: str):
    return normalize_branch_form(text)


# ---------------------------------------------------------------- форма: нет предупреждения

@pytest.mark.parametrize("src", [
    "| x | **Если** X, **то** Y,<br>**иначе** Z |",          # новая норма, ячейка
    "- **Если** X, **то** Y,<br>**иначе** Z",                 # новая норма, пункт списка
    "| x | **Если** X,<br>**то** Y,<br>**иначе** Z |",        # прежняя форма, ячейка
    "- **Если** X,<br>**то** Y,<br>**иначе** Z",              # прежняя форма, пункт списка
    "- **Если** X, **то** Y",
    "| x | **Если** X, **то** Y |",
    "**Если** P, **то** Q.",
    "- **Логика проверки:** **Если** A, **то** B,<br>**иначе если** C, **то** D,<br>**иначе** E",
    "- **Если** X, **то** Y,\n- **иначе** Z",
])
def test_lawful_forms_silent_and_normalizer_keeps_bytes(src):
    assert off(src) == []
    assert norm(src) == (src, 0, {})


def test_notation_nested_cell_sample_silent():
    src = ("| x | **Если** поле заполнено, **то**:<br>&nbsp;&nbsp;&nbsp;&nbsp;**Если** «Код типа счета» == 2, "
           "**то** отображается,<br>&nbsp;&nbsp;&nbsp;&nbsp;**иначе** не отображается,<br>**иначе** скрыто |")
    assert off(src) == []
    assert norm(src) == (src, 0, {})


def test_notation_nested_list_sample_silent():
    src = ("- **Если** поле заполнено, **то**:\n"
           "  - **Если** «Код типа счета» == 2, **то** отображается,\n"
           "  - **иначе** не отображается,\n"
           "- **иначе** скрыто.")
    assert off(src) == [] and lost(src) == []
    assert norm(src) == (src, 0, {})


# ---------------------------------------------------------------- форма: предупреждение и перенос

def test_one_line_warns_and_normalizes_without_br_before_then():
    src = "**Если** X, **то** Y, **иначе** Z"
    assert len(off(src)) == 1
    out, n, skipped = norm(src)
    assert out == "**Если** X, **то** Y,<br>**иначе** Z" and n == 1 and skipped == {}
    assert "<br>**то**" not in out and off(out) == []
    assert norm(out) == (out, 0, {})  # идемпотентность


def test_existing_br_before_then_not_removed():
    src = "- **Если** X,<br>**то** Y, **иначе** Z"
    out, n, _s = norm(src)
    assert out == "- **Если** X,<br>**то** Y,<br>**иначе** Z" and n == 1


def test_else_if_warns_too():
    assert len(off("- **Если** A, **то** B, **иначе если** C")) == 1


def test_counts_for_kit_line():
    assert branch_form_counts("| x | **Если** X, **то** Y |\n") == (0, 0)
    assert branch_form_counts("| x | **Если** X, **то** Y, **иначе** Z |\n") == (1, 0)


# ---------------------------------------------------------------- вложенность одной строкой

@pytest.mark.parametrize("src", [
    "**Если** A, **то** X, **Если** B, **то** Y",
    "**Если** A, **то** **Если** B, **то** C",
    "| x | **Если** A, **то** X, **Если** B, **то** Y |",
])
def test_nested_in_one_segment_stays_flagged_and_left_to_human(src):
    assert len(off(src)) == 1
    out, n, skipped = norm(src)
    assert out == src and n == 0 and skipped == {"вложенное условие": 1}
    assert branch_form_counts(src) == (1, 1)


def test_nested_rule_does_not_flag_conditions_in_separate_segments():
    # НЕсрабатывание: условия в разных отрезках и «Если» внутри цитаты — не вложенность
    assert off("- **Если** A, **то** B,<br>**Если** C, **то** D") == []
    assert off("- **Если** статус «Отказ», **то** текст «**Если** нет, **то** звоните»") == []


def test_else_if_chain_is_not_nested():
    assert off("**иначе если** C, **то** D") == []
    assert off("4. **иначе**, **если** C, **то** D") == []


# ---------------------------------------------------------------- «то» без исхода

@pytest.mark.parametrize("then", ["**то**", "**то:**", "**то**:"])
def test_no_outcome_all_spellings(then):
    assert len(lost(f"- **Если** X, {then}\n- исход")) == 1


@pytest.mark.parametrize("word", ["**иначе**", "**иначе:**", "**иначе**:", "**иначе,**", "**Иначе:**",
                                  "**иначе если** Y, **то**"])
def test_no_outcome_else_spellings(word):
    assert len(lost(f"- {word}\n- исход")) == 1


def test_no_outcome_else_live_form():
    # живой случай ЛК МП: «- **иначе:**» + условие того же уровня
    assert len(lost("- **Если** A, **то** B\n- **иначе:**\n- **Если** C, **то** D")) == 1
    # в конце отрезка после <br>
    assert len(lost("- **Если** A,<br>**то** B,<br>**иначе,**\n- исход")) == 1


@pytest.mark.parametrize("src", [
    "- **Если** A, **то** B,\n- **иначе**:\n  - исход 1\n  - исход 2",  # вложено правильно
    "- **иначе:**\n  - **Если** C, **то** D",
    "- **Если** A, **то** B,<br>**иначе:**\n  - исход",
    "- **иначе** исход\n- b",                                           # исход на строке
    "- **иначе** [MSG-1](#msg-1)\n- b",
    "- **иначе:**\n\n| A |\n|---|\n| 1 |",                              # таблица
    "- **иначе:**\n\n```text\nкод\n```",                                # блок кода
    "- **иначе:**\n\n## Раздел",                                        # конец раздела
    "- **иначе:**",                                                     # конец файла
    "- слова **то**, **иначе**\n- b",                                   # упоминание конструкции
    "| x | - **иначе:** |\n| y | - исход |",                             # ячейка таблицы
])
def test_no_outcome_else_silent(src):
    assert lost(src) == [], src


def test_no_outcome_old_form_with_br():
    assert len(lost("- **Если** X,<br>**то**\n- исход")) == 1


def test_no_outcome_line_number_and_fragment():
    hit = lost("# З\n\n- **Если** X, **то**\n\n- исход")
    assert hit == [(3, "**Если** X, **то**")]


def test_no_outcome_numbered_outcomes_at_same_indent():
    # живой случай: «- … **то**:» + «1. …» на том же отступе
    assert len(lost("- **Логика проверки:** **Если** A,<br>**то**:\n1. проверить\n2. вернуть")) == 1


def test_no_outcome_next_item_shallower():
    assert len(lost("- a\n  - **Если** X, **то**\n- b")) == 1


def test_no_outcome_paragraph_not_deeper():
    assert len(lost("2. **Если** X, **то**\n\n**Если** Y, **то** Z")) == 1


@pytest.mark.parametrize("src", [
    "- **Если** X, **то**\n  - исход 1\n  - исход 2",            # вложено правильно
    "1. **Если** X, **то**\n   1. исход",
    "- **Если** X, **то**\n\n  = продолжение абзаца с отступом",  # абзац глубже — исход
    "- **Если** X, **то**\n\n| A |\n|---|\n| 1 |",               # таблица
    "- **Если** X, **то**\n\n<table><tr><td>1</td></tr></table>",
    "- **Если** X, **то**\n\n```text\nкод\n```",                  # блок кода
    "- **Если** X, **то**\n\n## Раздел",                          # конец раздела
    "- **Если** X, **то**\n\n---",
    "- **Если** X, **то**",                                       # конец файла
    "- **Если** X, **то**\n\n",
    "| x | - **Если** X, **то** |\n| y | - исход |",              # ячейка таблицы
    "```text\n- **Если** X, **то**\n- исход\n```",                # блок кода
    "**Если** X, **то**\nисход",                                  # не пункт списка
    "- **Если** X, **то** [MSG-1](#msg-1)\n- b",                  # исход ссылкой
    "- **Если** X, **то** [[КК] Имя](a.md)\n- b",
    "- **Если** X, **то** `<Код>`\n- b",                          # исход кодом
    "- **Если** X, `**то**`\n- b",                                # слово в коде
    "- **Если** X, **то** Y\n- b",                                # исход на строке
    "- слова **Если**, **то**\n- b",                              # упоминание конструкции
    "- ветвлением «**Если** …, **то**\n- b",                      # незакрытая цитата
    "- **Если** X, **то**\n<!-- комментарий -->",
])
def test_no_outcome_silent(src):
    assert lost(src) == [], src


def test_no_outcome_does_not_touch_normalizer_or_offenders():
    src = "- **Если** X, **то**\n- исход"
    assert off(src) == []
    assert norm(src) == (src, 0, {})


def test_crlf_lines_handled():
    assert len(branch_no_outcome("- **Если** X, **то**\r\n- исход\r\n".splitlines())) == 1


# ---------------------------------------------------------------- отчёты

def _card(body: str) -> str:
    return f"---\nid: FUN-CL-01\ntitle: '[X] Ф'\ntype: function\nservice: x\n---\n\n# Ф\n\n{body}"


def test_check_file_warning_keeps_verdict(tmp_path: Path):
    p = tmp_path / "fun-cl-01.md"
    p.write_text(_card("- **Если** X, **то**\n- исход\n"), encoding="utf-8")
    rep, ok = check_file(p)
    line = next((ln for ln in rep if "без исхода" in ln), "")
    assert line.startswith("предупреждение: форма ветвления: «то»/«иначе» без исхода") and "×1" in line, rep
    assert any("пример:" in ln and "**то**" in ln for ln in rep), rep
    assert ok


def test_check_file_nested_has_own_line_not_about_then(tmp_path: Path):
    p = tmp_path / "fun-cl-01.md"
    p.write_text(_card("**Если** A, **то** X, **Если** B, **то** Y\n\n- **Если** C, **то** D, **иначе** E\n"),
                 encoding="utf-8")
    rep, ok = check_file(p)
    nested = next((ln for ln in rep if "второе «**Если**»" in ln), "")
    assert nested.startswith("предупреждение: форма ветвления — второе «**Если**» в строке после исхода "
                             "(вложенное условие одной строкой)") and "×1" in nested, rep
    other = next((ln for ln in rep if "«**иначе**» не в начале" in ln), "")
    assert other and "×1" in other, rep
    assert not any("«**то**»" in ln for ln in rep), rep
    assert ok


def test_check_file_silent_for_new_form(tmp_path: Path):
    p = tmp_path / "fun-cl-01.md"
    p.write_text(_card("- **Если** X, **то** Y,<br>**иначе** Z\n- **Если** A, **то**\n  - исход\n"), encoding="utf-8")
    rep, ok = check_file(p)
    assert not any("форма ветвления" in ln for ln in rep), rep
    assert ok


def _kit(tmp_path: Path, n: int) -> Path:
    docs = tmp_path / "docs"
    rows = "".join(f"| X-0{i} | function | Ф | f{i}.md |\n" for i in range(n))
    (docs / "srs/functions").mkdir(parents=True)
    (docs / "traceability-matrix.md").write_text(
        f"# Матрица\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n{rows}", encoding="utf-8")
    for i in range(n):
        (docs / f"srs/functions/f{i}.md").write_text(
            f"---\nid: X-0{i}\ntitle: '[X] X-0{i}'\ntype: function\n---\n\n# X-0{i}\n\n"
            "- **Если** X, **то**\n- исход\n", encoding="utf-8")
    return docs


def test_kit_report_line_examples_and_listing(tmp_path: Path, monkeypatch):
    docs = _kit(tmp_path, 3)
    report, _ok = selfcheck.run(docs, None)
    assert "⚠ форма ветвления: «то»/«иначе» без исхода — следующий пункт на уровне условия ×3" in report, report
    assert sum(ln.strip().startswith("пример:") for ln in report) == 2, report
    listing = [ln for ln in report if ln.startswith(selfcheck.OUT_ONLY) and ":9:" in ln]
    assert len(listing) == 3, report
    assert not any(ln.startswith("⚠ форма ветвления (notation §1)") for ln in report), report


def test_kit_verdict_same_with_and_without_no_outcome(tmp_path: Path):
    _r1, ok1 = selfcheck.run(_kit(tmp_path / "a", 1), None)
    clean = _kit(tmp_path / "b", 1)
    f = clean / "srs/functions/f0.md"
    f.write_text(f.read_text(encoding="utf-8").replace("- исход", "  - исход"), encoding="utf-8")
    r2, ok2 = selfcheck.run(clean, None)
    assert ok1 == ok2
    assert not any("форма ветвления" in ln for ln in r2), r2
