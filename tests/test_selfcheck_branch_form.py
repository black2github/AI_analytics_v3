# tests/test_selfcheck_branch_form.py
"""Сторож формы ветвления в самопроверке комплекта — одна сводная строка на комплект
(решение владельца пилота 2026-10-20): N мест в M файлах, сколько закроет
`--branch-form --write`, сколько вложенных вручную; строки на файл в отчёте комплекта нет,
одиночная проверка файла её сохраняет; перечень по файлам — только в --out."""
import sys
from pathlib import Path

from app.scripts.CI import normalize_tables as nt
from app.scripts.CI import selfcheck


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid: str, body: str) -> str:
    return f"---\nid: {cid}\ntitle: '[X] {cid}'\ntype: function\n---\n\n# {cid}\n\n{body}"


CELLS = ("| Поле | Логика |\n|---|---|\n"
         "| A | **Если** X, **то** Y, **иначе** Z |\n"
         "| B | **Если** P, **то** Q |\n")
NESTED = "- **Если** A, **то** **Если** B, **то** C\n"


def kit(tmp_path: Path, with_offenders: bool = True) -> Path:
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         "| X-01 | function | Ф | f1.md |\n| X-02 | function | Ф | f2.md |\n"
         "| X-03 | function | Ф | f3.md |\n")
    make(docs / "srs/functions/f1-cells.md", card("X-01", CELLS if with_offenders else "текст\n"))
    make(docs / "srs/functions/f2-nested.md", card("X-02", NESTED if with_offenders else "текст\n"))
    make(docs / "srs/functions/f3-clean.md", card("X-03", "**Если** A,<br>**то** B.\n"))
    return docs


def test_summary_line_counts(tmp_path):
    report, _ok = selfcheck.run(kit(tmp_path), None)
    summary = [ln for ln in report if ln.startswith("⚠ форма ветвления")]
    assert summary == ["⚠ форма ветвления (notation §1): 3 мест в 2 файлах; normalize_tables.py "
                       "--branch-form --write закроет 2, вложенных условий вручную 1 "
                       "(srs/functions/f1-cells.md ×2, srs/functions/f2-nested.md ×1)"], report


def test_no_per_file_line_in_kit_report(tmp_path):
    report, _ok = selfcheck.run(kit(tmp_path), None)
    assert not any("предупреждение: форма ветвления" in ln for ln in report), report
    assert not any("пример:" in ln for ln in report), report


def test_single_file_check_keeps_per_file_line(tmp_path):
    docs = kit(tmp_path)
    rep, _ok = nt.run_check([docs / "srs/functions/f1-cells.md"], None, docs_root=docs)
    assert any(ln.startswith("предупреждение: форма ветвления") and "×2" in ln for ln in rep), rep
    assert sum("пример:" in ln for ln in rep) == 2


def test_no_offenders_no_line(tmp_path):
    report, _ok = selfcheck.run(kit(tmp_path, with_offenders=False), None)
    assert not any("форма ветвления" in ln for ln in report), report


def test_tail_and_listing_only_in_out(tmp_path, monkeypatch, capsys):
    docs = kit(tmp_path)
    for i in range(4, 7):
        make(docs / f"srs/functions/f{i}.md", card(f"X-0{i}", "**Если** K, **то** L\n"))
    out = tmp_path / "report.txt"
    monkeypatch.setattr(sys, "argv", ["selfcheck.py", "--docs", str(docs), "--out", str(out)])
    selfcheck.main()
    console = capsys.readouterr().out
    text = out.read_text(encoding="utf-8")
    head = next(ln for ln in text.splitlines() if ln.startswith("# ⚠ форма ветвления"))
    assert "6 мест в 5 файлах" in head and "закроет 5, вложенных условий вручную 1" in head
    assert head.endswith("(srs/functions/f1-cells.md ×2, srs/functions/f2-nested.md ×1, "
                         "srs/functions/f4.md ×1, и ещё 2 файлов)"), head
    listing = [ln for ln in text.splitlines() if ln.startswith("#    · ")]
    assert listing[0] == "#    · srs/functions/f1-cells.md ×2"
    assert "#    · srs/functions/f2-nested.md ×1 (вручную 1)" in listing and len(listing) == 5
    # в консоли — сводная строка без перечня
    assert head in console and "   · " not in console
