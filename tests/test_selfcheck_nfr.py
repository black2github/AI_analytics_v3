# tests/test_selfcheck_nfr.py
"""Сторож каталога НФТ output/<service>/nfr/ (шаблон nfr.md, ветка docs/meta
канона 2026-10-14): без каталога молчит; корректная страница типа — ✓;
раздел НФТ внутри фичи, чужое имя файла, вложенный каталог — ✗."""

from pathlib import Path

import pytest

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


# единая таблица страницы типа (шаблон nfr.md канона, ветка meta/nfr-change 19.11)
HDR = "| ID | Параметр | Допустимое значение | Пояснение |\n|---|---|---|---|\n"
PRF_ROW = "| nfr-prf-001 | Время отклика | ≤ 2 с | — |\n"


def _type_page(code: str, name: str, rows: str = HDR) -> str:
    return (f"---\nid: nfr-{code}\ntype: nfr\nnfr_type: {name}\ningress: reverse\n"
            f"confluence_page_ids: 123\n---\n# {name}\n\n{rows}")


def _catalog(tmp_path: Path, prf_rows: str = HDR + PRF_ROW,
             matrix_head: str = "## BRD-6.2. НФТ") -> Path:
    """Законный каталог: README-реестр и все 18 страниц типов с единой таблицей; строка
    nfr-prf-001 — в разделе BRD-6.2 матрицы."""
    from app.scripts.CI.kitcheck.checks.nfr import _NFR_TYPE_BY_CODE
    docs = tmp_path / "output/svc/docs"
    make(docs / "README.md", "# К\n")
    make(docs / "traceability-matrix.md",
         f"# Матрица\n\n{matrix_head}\n\n| ID | Объект |\n|---|---|\n"
         "| nfr-prf-001 | Время отклика |\n")
    nfr = tmp_path / "output/svc/nfr"
    make(nfr / "README.md", "---\nid: nfr\ntype: nfr\n---\n# Реестр НФТ\n")
    for code, name in _NFR_TYPE_BY_CODE.items():
        make(nfr / f"nfr-{code}.md", _type_page(code, name, prf_rows if code == "prf" else HDR))
    return docs


def test_valid_page_ok(tmp_path):
    # норма канона: каталог НФТ — README-реестр и все 18 страниц типов, у каждой — таблица
    # | ID | Параметр | Допустимое значение | Пояснение |, без запрещённых колонок
    report, ok = check_nfr_catalog(_catalog(tmp_path))
    assert ok, report
    assert any("каталог НФТ" in r for r in report), report


def test_forbidden_columns_flagged(tmp_path):
    # прежняя форма страницы с колонкой «Не задано» — ✗
    docs = tmp_path / "output/svc/docs"
    make(docs / "README.md", "# К\n")
    make(tmp_path / "output/svc/nfr/nfr-prf.md", PAGE)
    report, ok = check_nfr_catalog(docs)
    assert not ok and any("nfr-prf.md: запрещены колонки «Не задано»" in r for r in report), report


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


# ------------------------------------- новая норма страниц НФТ (канон, meta/nfr-change)

def test_page_without_required_table_flagged(tmp_path):
    docs = _catalog(tmp_path, prf_rows="Текст без таблицы.\n")
    report, ok = check_nfr_catalog(docs)
    assert not ok and any(r.startswith("✗ nfr") and r.endswith(
        "nfr-prf.md: нужна таблица | ID | Параметр | Допустимое значение | Пояснение |")
        for r in report), report


def test_skeleton_page_with_header_only_ok(tmp_path):
    # несрабатывание: страница-скелет без строк, но с шапкой единой таблицы — законна
    docs = _catalog(tmp_path)
    report, ok = check_nfr_catalog(docs)
    assert ok and not any("нужна таблица" in r for r in report), report


@pytest.mark.parametrize("header", [
    "| ID | Параметр | Допустимое значение | Пояснение | Единица измерения |",
    "| ID | Параметр | Допустимое значение | Пояснение | Способ измерения |",
    "| ID | Показатель | Значение |",
    "| ID | Параметр | Допустимое значение | Пояснение | Основание |",
])
def test_forbidden_new_columns_flagged(tmp_path, header):
    rows = HDR + PRF_ROW + "\n" + header + "\n|" + "---|" * (header.count("|") - 1) + "\n"
    report, ok = check_nfr_catalog(_catalog(tmp_path, prf_rows=rows))
    assert not ok and any("nfr-prf.md: запрещены колонки" in r for r in report), report


def test_parameter_value_columns_not_forbidden(tmp_path):
    # несрабатывание: «Параметр» и «Допустимое значение» — колонки нормы, не пара
    # «Показатель | Значение»
    report, ok = check_nfr_catalog(_catalog(tmp_path))
    assert ok and not any("запрещены колонки" in r for r in report), report


def test_policy_list_flagged(tmp_path):
    rows = HDR + PRF_ROW + "\n- **nfr-prf-002.** Время ответа не более 1 с.\n"
    report, ok = check_nfr_catalog(_catalog(tmp_path, prf_rows=rows))
    assert not ok and any("nfr-prf.md: запрещён список политик (nfr-prf-002)" in r
                          for r in report), report


@pytest.mark.parametrize("head", ["## BRD-6.2. НФТ",
                                  "## BRD-6. НФТ\n\n### BRD-6.2. Атомарное требование"])
def test_brd_6_2_section_found_at_level_2_and_3(tmp_path, head):
    report, ok = check_nfr_catalog(_catalog(tmp_path, matrix_head=head))
    assert ok and not any("BRD-6.2" in r for r in report), report


def test_brd_6_2_row_missing_flagged_under_level_3(tmp_path):
    # срабатывание сверки по секции третьего уровня: строки страницы нет в BRD-6.2
    docs = _catalog(tmp_path, matrix_head="## BRD-6. НФТ\n\n### BRD-6.1. Источники\n\n"
                                          "| nfr-prf-001 | — |\n\n### BRD-6.2. Атомарное")
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace(
        "| ID | Объект |\n|---|---|\n| nfr-prf-001 | Время отклика |\n", "| ID | Объект |\n|---|---|\n"),
        encoding="utf-8")
    report, ok = check_nfr_catalog(docs)
    assert not ok and "✗ BRD-6.2: нет строки nfr-prf-001" in report, report
