# tests/test_stray_table_lines.py
"""Строка таблицы без ведущего «|» (в том числе с BOM) в разделах матрицы и описи — ⚠
(постановка 2026-11-09, П-6; КК 7d6781c9: обрубок строки долга с BOM после строк таблицы)."""
from pathlib import Path

from app.scripts.CI.kitcheck.md import stray_table_lines
from app.scripts.CI.link_debts import check

TABLE = "| A | B |\n|---|---|\n| 1 | 2 |\n"


def test_tail_after_rows_found():
    text = "# М\n\n" + TABLE + "035d8 (﻿PROM-5.4 заход 2)\n\nабзац\n"
    assert stray_table_lines(text) == [(6, "035d8 (﻿PROM-5.4 заход 2)")]


def test_bom_row_found_even_after_blank_line():
    text = "# М\n\n| A | B |\n|---|---|\n\n﻿| 3 | 4 |\n"
    assert [n for n, _ in stray_table_lines(text)] == [6]


def test_paragraph_after_blank_line_silent():
    # НЕсрабатывание: абзац-пояснение между таблицами через пустую строку
    text = "# М\n\n" + TABLE + "\nПояснение к таблице.\n\n" + TABLE
    assert stray_table_lines(text) == []


def test_heading_after_table_and_code_silent():
    text = ("﻿# М\n\n" + TABLE + "## Следующий раздел\n\n```\n| a |\nне таблица\n```\n")
    assert stray_table_lines(text) == []


def test_crlf_lines_numbered():
    text = ("# М\r\n\r\n" + TABLE.replace("\n", "\r\n") + "обрубок\r\n")
    assert stray_table_lines(text) == [(6, "обрубок")]


def test_link_debts_reports_stray_row(tmp_path):
    docs = tmp_path / "docs"
    (docs / "srs").mkdir(parents=True)
    (docs / "srs/f.md").write_text("---\nid: FUN-1\ntitle: 'Ф'\n---\n# Ф\n", encoding="utf-8")
    (docs / "traceability-matrix.md").write_text(
        "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
        "| FUN-1 | function | Ф | srs/f.md |\n\n## 4. Долги по ссылкам\n\n| FROM | Цель | Долг |\n"
        "|---|---|---|\n﻿FUN-1 | — | нет целевого артефакта process «П» — требуется заход "
        "create-process |\n", encoding="utf-8")
    report, ok = check(docs / "traceability-matrix.md", docs)
    hit = [ln for ln in report if ln.startswith("⚠ строка вне таблицы: traceability-matrix.md:13")]
    assert hit and "FUN-1 | —" in hit[0], report
    assert ok


def test_source_coverage_reports_stray_inventory_row(tmp_path):
    from app.scripts.CI import source_coverage as sc
    root = tmp_path / "kit"
    src = root / "sources/confluence"
    src.mkdir(parents=True)
    (src / "p1.md").write_text("---\ntitle: 'Т'\nconfluence_page_id: '1'\n---\n\nтекст\n",
                               encoding="utf-8")
    (root / "docs").mkdir()
    (root / "inventory.md").write_text(
        "# Опись\n\n| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
        "|---|---|---|---|---|---|---|\n| 1 | Т | Р | function | 1 | srs/bc-a/function | с |\n"
        "2 | Обрубок | Р | function | 1 | srs/bc-a/function | с |\n", encoding="utf-8")
    (root / "migration-plan.md").write_text("# План\n\n| [X] | подсервис bc-a | `srs/bc-a/` |\n",
                                            encoding="utf-8")
    lines, _n = sc.coverage_report(src, root / "docs")
    assert any(ln.startswith("⚠ строка вне таблицы: inventory.md:6") for ln in lines), lines
