# tests/test_selfcheck_source_silent.py
"""Задача 1 пакета 1 (ПР-12, conventions §6 п.5): перечень формулы
«в постановке не задано» и пометок о пробеле не по формуле — только ⚠."""
from pathlib import Path

from app.scripts.CI import selfcheck


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_formula_listed_and_not_counted_as_other_mark(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/scr.md", "---\nid: SCR-CL-01\n---\n# Э\n\n- **Тип:** В постановке не задано\n")
    rep = selfcheck.check_source_silent(docs)
    assert rep[0].startswith("⚠ формула «в постановке не задано» ×1"), rep
    assert "srs/scr.md:6" in rep[1], rep
    assert not any("не по формуле" in r for r in rep), rep


def test_other_gap_mark_warned(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/call.md", "# В\n\n### Транспорт\n\nТранспорт не задано (вне выгрузки)\n")
    rep = selfcheck.check_source_silent(docs)
    assert len(rep) == 2 and rep[0].startswith("⚠ пометка о пробеле не по формуле ×1"), rep


def test_clean_kit_and_literals_frontmatter_code_silent(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/f.md", "---\nid: FUN-CL-01\nnote: не задано\n---\n# Ф\n\n"
      "Сообщение «Значение не задано» показывается под полем.\n"
      "```\nне задано\n```\n")
    w(docs / "srs/g.md", "# Г\n\nОбычный текст без пометок.\n")
    assert selfcheck.check_source_silent(docs) == []
