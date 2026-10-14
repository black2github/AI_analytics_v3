# tests/test_selfcheck_nfr.py
"""Сторож каталога НФТ output/<service>/nfr/ (шаблон nfr.md, ветка docs/meta
канона 2026-10-14): без каталога молчит; корректная страница типа — ✓;
раздел НФТ внутри фичи, чужое имя файла, вложенный каталог — ✗."""

from pathlib import Path

from app.scripts.CI.selfcheck import check_nfr_catalog


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


PAGE = ("---\nid: nfr-prf\ntype: nfr\nnfr_type: Производительность\n"
        "ingress: reverse\nconfluence_page_ids: 123\n---\n# Производительность\n\n"
        "| ID | Показатель | Норма | Не задано |\n|---|---|---|---|\n"
        "| nfr-prf-001 | Время отклика | ≤ 2 с | окно измерения |\n")


def test_no_catalog_is_silent(tmp_path):
    docs = tmp_path / "output/svc/docs"
    make(docs / "README.md", "# К\n")
    report, ok = check_nfr_catalog(docs)
    assert ok and report == []


def test_valid_page_ok(tmp_path):
    docs = tmp_path / "output/svc/docs"
    make(docs / "README.md", "# К\n")
    # строки страниц типов обязаны стоять в разделе BRD-6.2 матрицы
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n## BRD-6.2. НФТ\n\n| ID | Показатель |\n|---|---|\n"
         "| nfr-prf-001 | Время отклика |\n")
    make(tmp_path / "output/svc/nfr/nfr-prf.md", PAGE)
    report, ok = check_nfr_catalog(docs)
    assert ok, report
    assert any("каталог НФТ" in r for r in report), report


def test_nfr_section_in_feature_and_bad_names_flagged(tmp_path):
    docs = tmp_path / "output/svc/docs"
    make(docs / "brd/features/f-cl-01.md",
         "---\nid: F-CL-01\n---\n# Ф\n\n## Нефункциональные требования\n\nтекст\n")
    make(tmp_path / "output/svc/nfr/nfr-xyz.md", PAGE)
    make(tmp_path / "output/svc/nfr/sub/x.md", "# x\n")
    report, ok = check_nfr_catalog(docs)
    assert not ok
    joined = "\n".join(report)
    assert "внутри фичи" in joined, report
    assert "имя файла не из каталога" in joined, report
    assert "вложенный каталог" in joined, report
