# tests/test_fence_recognition.py
"""Границы блоков кода в приборе — одно правило для всех мест (решение
владельца 2026-10-17, исследование «Прибор — распознавание блоков кода и
ограждений»): правило ограждения общего кода бандла (`critic._FENCE_RE`),
``` и ~~~ во всех местах, склеенный инлайн-код выгрузки ```"x"`` — не
ограждение, непарная ``` в строке не прячет текст до следующего блока,
<pre> источника — кандидат примера (Р-2), голый <pre> в карточке — ✗ (Р-3)."""

from pathlib import Path

from app.scripts.CI import link_debts as ld, selfcheck, transfer_gate as tg
from app.scripts.CI.kitcheck import md
from app.scripts.CI.kitcheck.checks import artifacts, content
from app.scripts.CI.normalize_tables import check_file

GLUED = '```"params"``: {`'   # склейка инлайн-кода выгрузки (инцидент 2026-09-06)


def _make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --- правило ----------------------------------------------------------------

def test_md_uses_fence_module():
    # одно правило в одном модуле (kitcheck/fence.py, решение 2026-10-17):
    # строка-ограждение и разметка строк в md — из него; поведение правила
    # держит tests/test_kitcheck_fence.py (тест поведения вместо равенства
    # регулярок)
    from app.scripts.CI.kitcheck import fence
    for ln in ("```", "~~~ x", '```"a"``', "```x```", "> ```", "текст"):
        assert md.is_fence(ln) == (fence.fence_of(ln) is not None), ln
    lines = ["````markdown", "```mermaid", "x", "```", "## Раздел", "````", "т"]
    assert md.code_line_flags(lines) == fence.code_flags(lines)
    assert md.code_line_flags(lines) == [True] * 6 + [False]


def test_is_fence_rule():
    for ln in ("```", "```json", "~~~", "~~~markdown", "````markdown", "```plantuml "):
        assert md.is_fence(ln), ln
    for ln in (GLUED, "```}`", "``` x ``` y", "``", "~~", "текст ```"):
        assert not md.is_fence(ln), ln


def test_blank_code_blocks_inline_and_unpaired():
    text = "A\n```json\n{[x](a.md)}\n```\nB ```[y](b.md)``` C\nD ``` E\n[z](c.md)\n~~~\nF\n~~~\nG"
    out = md.blank_code(text)
    assert "a.md" not in out and "b.md" not in out and "F" not in out
    # непарная ``` в строке не спаривается со следующим блоком
    assert "[z](c.md)" in out and "D ``` E" in out
    assert out.split("\n")[0] == "A" and out.split("\n")[-1] == "G"


def test_blank_code_unclosed_and_glued():
    assert md.blank_code("A\n```\nB\nC") == "A\n "
    assert md.blank_code(GLUED + "\n## Раздел") == GLUED + "\n## Раздел"
    assert md.blank_code("A\n```\nB\n```\nC", repl="", inline=False) == "A\n\nC"


def test_code_blocks():
    assert md.code_blocks("x\n```json\n{\"a\": 1}\n```\n~~~\nq\n~~~\n```\nopen") == \
        ['{"a": 1}', "q", "open"]
    assert md.code_blocks("| a ```{x}``` |\n| b |\n```\n{y}\n```") == ["{y}"]


# --- построчные переключатели (Т1–Т11) ---------------------------------------

def test_glued_inline_does_not_hide_sections():
    # Т3: раздел после склейки виден (прежде склейка открывала мнимый блок)
    assert content._h2_keys(GLUED + "\n## Назначение\n") == ["назначение"]
    # НЕсрабатывание: раздел из образца в ~~~ не засчитан
    assert content._h2_keys("~~~\n## Назначение\n~~~\n") == []


def test_glued_inline_does_not_hide_anchors(tmp_path):
    p = _make(tmp_path / "a.md", GLUED + "\n## Раздел\n")
    assert "раздел" in md._anchors_of(p, {})
    p2 = _make(tmp_path / "b.md", "~~~\n## Раздел\n~~~\n")
    assert "раздел" not in md._anchors_of(p2, {})


def test_torn_cell_guard_skips_tilde_block(tmp_path):
    # Т9: свимлейны PlantUML в ~~~ — не разорванная ячейка (прежде — только ```)
    p = _make(tmp_path / "card.md",
              "# Процесс\n\n~~~plantuml\n@startuml\n|Система|\n  :5 Шаг;\n"
              "|Пользователь|\n@enduml\n~~~\n")
    rep, ok = check_file(p)
    assert not any("разорванная ячейка" in ln for ln in rep), rep


def test_torn_cell_still_caught_after_glued_line(tmp_path):
    # НЕсрабатывание исключения: склейка не открывает блок — разрыв ниже виден
    p = _make(tmp_path / "card.md",
              "# Карточка\n\n" + GLUED + "\n\n| Параметр | Описание |\n|---|---|\n"
              "| A | начало |\nхвост разорванной ячейки\n| B | дальше |\n")
    rep, ok = check_file(p)
    assert any("разорванная ячейка" in ln for ln in rep), rep


# --- регулярки (Р1–Р8) ------------------------------------------------------

def test_unpaired_triple_in_table_row_does_not_hide_links(tmp_path):
    # Р2: прежде непарная ``` строки таблицы спаривалась со следующим
    # ограждением и прятала битую ссылку между ними
    docs = tmp_path / "docs"
    _make(docs / "f1.md",
          "# Ф\n\n| Поле | Пример |\n|---|---|\n| a | **ID**<br>```<br>\"sort\" |\n\n"
          "[нет](none.md)\n\n```\nкод\n```\n")
    rep, ok = selfcheck.check_relative_links(docs)
    assert not ok and any("none.md" in ln for ln in rep), rep


def test_links_in_tilde_block_skipped(tmp_path):
    # НЕсрабатывание: ссылка-пример в ~~~ не проверяется
    docs = tmp_path / "docs"
    _make(docs / "f1.md", "# Ф\n\n~~~\n[пример](нет-такого.md)\n~~~\n")
    rep, ok = selfcheck.check_relative_links(docs)
    assert ok and rep == [], rep


def test_bare_pre_in_card_is_defect(tmp_path):
    # Р-3 (а): голый <pre> в карточке — ✗ (пример переносится ограждением
    # или в sidecar); в блоке кода и в инлайн-коде — нет
    p = _make(tmp_path / "c.md", "# К\n\n| Поле | Пример |\n|---|---|\n| a | <pre>{x}</pre> |\n")
    rep, ok = check_file(p)
    assert not ok and any("HTML-теговидные" in ln and "<pre>" in ln for ln in rep), rep
    p2 = _make(tmp_path / "d.md", "# К\n\n```html\n<pre>{x}</pre>\n```\n\nзначение `<pre>`\n")
    rep2, ok2 = check_file(p2)
    assert not any("HTML-теговидные" in ln for ln in rep2), rep2


def test_unpaired_triple_does_not_hide_tag(tmp_path):
    p = _make(tmp_path / "c.md", "# К\n\nтекст ``` хвост\n\nразмер <S> = true\n\n```\nкод\n```\n")
    rep, ok = check_file(p)
    assert not ok and any("<S>" in ln for ln in rep), rep


def test_source_candidates_pre_and_blocks():
    # Р5 + Р-2: <pre> ячейки и ~~~ — кандидаты; пары ``` в строках таблицы не
    # склеиваются через строки в мнимый блок
    src = ("| a | <pre>{\"k\": 1}</pre> |\n| b | ```{\"m\": 2}``` |\n| c | x |\n"
           "~~~\n{\"t\": 3}\n~~~\n")
    cands = artifacts._source_candidates(src)
    assert '{"k": 1}' in cands and '{"t": 3}' in cands
    assert not any("\n| c |" in c or "| c | x" in c for c in cands), cands


def test_register_skips_tilde_and_indented_examples(tmp_path):
    # Р6: образец записи в ~~~ и в ограждении с отступом — не запись
    p = _make(tmp_path / "feedback.md",
              "# Замечания\n\n~~~markdown\n## FB-09 — образец\n~~~\n\n"
              "1. Шаг:\n\n   ```markdown\n## FB-08 — образец\n   ```\n\n"
              "## FB-01 — 2026-10-01 — тема\n")
    rep, ok = ld.check_feedback_order(p)
    assert ok and "(1 записей)" in rep[0], rep


def test_register_still_counts_real_entries_after_glued_line(tmp_path):
    # НЕсрабатывание: склейка не открывает блок — записи ниже считаются
    p = _make(tmp_path / "open-questions.md",
              "# Вопросы\n\n" + GLUED + "\n\n## OQ-01 — 2026-10-01 — тема\n\n## OQ-02 — 2026-10-02 — тема\n")
    rep, ok = ld.check_oq_order(p)
    assert ok and "(2 записей)" in rep[0], rep


def test_open_questions_skip_tilde_example(tmp_path):
    # Р8: OQ-образец в ~~~ не открытый вопрос гейта переноса
    oq = _make(tmp_path / "open-questions.md",
               "# Вопросы\n\n~~~markdown\n## OQ-09 — образец\n- **Статус:** открыт\n~~~\n\n"
               "## OQ-01 — тема\n- **Статус:** закрыт\n")
    path, opened = tg.open_questions(tmp_path, tmp_path / "docs", explicit=oq)
    assert path == oq and opened == [], opened
