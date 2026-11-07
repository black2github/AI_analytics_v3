# tests/test_nav_readme_info_level.py
"""Пакет П2 ОНБ-В, п. 8 (замечание 71): навигационный README без frontmatter —
норма (conventions §5), строка уровня i; файл остаётся в переписи ИТОГО."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def kit(root: Path, readme: bool = True) -> Path:
    docs = root / "docs"
    w(docs / "srs/glossary.md", "---\nid: GLO-001\ntype: glossary\nservice: x\ntitle: Г\n---\n\n"
      "# Глоссарий\n\nт\n")
    if readme:
        w(docs / "srs/screen-form/client/scr-cl-02-edit/README.md", "# ЭФ «Ред.»\n\nт\n")
    return docs


def _total(report):
    return next(ln for ln in report if ln.startswith("ИТОГО"))


def test_nav_readme_is_info_and_counted(tmp_path):
    report, ok = sc.run(kit(tmp_path), None)
    line = next(ln for ln in report if "навигационный README" in ln)
    assert line.startswith("i ") and "норма (conventions §5), вне сверки" in line, line
    assert "Р-9" not in line and "освобождён" not in line
    total = _total(report)
    assert "файлов 2 —" in total and "⚠ 0," in total and "i 1, ⚠ примеры" in total, total


def test_verdict_unchanged_by_level(tmp_path):
    _r1, ok_with = sc.run(kit(tmp_path / "a"), None)
    _r2, ok_without = sc.run(kit(tmp_path / "b", readme=False), None)
    assert ok_with == ok_without


def test_no_i_counter_without_nav_readme(tmp_path):
    # формат ИТОГО комплекта без таких README не меняется
    report, _ok = sc.run(kit(tmp_path, readme=False), None)
    assert ", i " not in _total(report), _total(report)


def test_other_file_without_frontmatter_still_warned(tmp_path):
    # НЕсрабатывание понижения: прочий документ без frontmatter — по-прежнему ⚠
    docs = kit(tmp_path, readme=False)
    w(docs / "srs/notes.md", "# Заметки\n\nт\n")
    report, _ok = sc.run(docs, None)
    assert any(ln.startswith("⚠ ") and "notes.md: без frontmatter" in ln for ln in report), report
    assert "⚠ 1," in _total(report)
