# tests/test_source_coverage_withdrawn.py
"""OQ-294 КК (2026-10-30): класс «снято с миграции» (DELETE / [DRAFT] / «черновик» вместо
маскировки под справочный вход) и каталоги-узлы без собственной страницы (дефект
выгрузки — только каталог без страницы и без дочерних страниц)."""
import sys
from pathlib import Path

from app.scripts.CI import source_coverage as sc

HEAD = ("| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
        "|---|---|---|---|---|---|---|\n")
PLAN = "| [X_A] | подсервис bc-a | `srs/bc-a/` |\n"


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def page(pid: str, title: str) -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\nтекст страницы\n"


def kit(tmp_path: Path, rows):
    """rows: (pid, title, target, basis); страница 99 покрыта карточкой."""
    root = tmp_path / "kit"
    src, docs = root / "sources/confluence", root / "docs"
    inv = HEAD
    for pid, title, target, basis in rows:
        make(src / f"p{pid}.md", page(pid, title))
        inv += f"| {pid} | {title} | Раздел | integration | 10 | {target} | {basis} |\n"
    make(src / "p99.md", page("99", "Покрытая"))
    make(docs / "srs/bc-a/function/fun-1.md", "---\nid: FUN-1\nconfluence_page_ids: ['99']\n---\n# Ф\n")
    make(root / "inventory.md", "# Опись\n\n" + inv)
    make(root / "migration-plan.md", "# План\n\n" + PLAN)
    return src, docs


def classes(lines):
    return [ln for ln in lines if not ln.startswith("  ")][1:]


def test_delete_in_title_with_reference_only_is_withdrawn(tmp_path):
    src, docs = kit(tmp_path, [
        ("1", "DELETE РКО Ф1 Корпоративные карты", "archiv", "reference-only — индекс"),
        ("2", "РКО Ф1. Представление", "archiv", "помечено DELETE в выгрузке; reference-only"),
        ("3", "[DRAFT] Копия 18.13", "archiv", "reference-only — копия"),
        ("4", "Справочник", "archiv", "reference-only — снято с миграции: преемник покрыт"),
        ("5", "Страница", "archiv", "черновик-копия; reference-only"),
        ("6", "Правила", "doc-rules", "reference-only"),
    ])
    lines, blocking = sc.coverage_report(src, docs)
    assert ("справочные 1, снято с миграции 5, вне плана 0" in lines[0]), lines[0]
    assert classes(lines) == ["справочные: 1", "снято с миграции: 5"], lines
    assert blocking == 0


def test_strict_does_not_block_on_withdrawn(tmp_path, monkeypatch):
    src, docs = kit(tmp_path, [("1", "DELETE Индекс", "archiv", "reference-only")])
    monkeypatch.setattr(sys, "argv", ["source_coverage.py", "--sources", str(src),
                                      "--output", str(docs), "--strict"])
    assert sc.main() == 0


# ---------------------------------------------------------------- несрабатывание

def test_negated_delete_is_gap(tmp_path):
    src, docs = kit(tmp_path, [
        ("1", "Функция А", "srs/bc-a/function", "не DELETE — живая страница"),
        ("2", "Функция Б", "srs/bc-a/function", "не снято с миграции"),
    ])
    lines, blocking = sc.coverage_report(src, docs)
    assert "пробелы миграции 2;" in lines[0] and "снято с миграции" not in lines[0], lines[0]
    assert blocking == 2


def test_chernovik_in_title_only_stays_reference(tmp_path):
    # «Черновик» в названии живой страницы — не метка выгрузки (КК: «Черновик - ПР для
    # выпуска ЦК» — справочный вход концепции сервиса)
    src, docs = kit(tmp_path, [("1", "Черновик - ПР для выпуска ЦК", "brd",
                                "reference-only — источник концепции сервиса")])
    lines, _b = sc.coverage_report(src, docs)
    assert classes(lines) == ["справочные: 1"], lines


def test_lowercase_delete_word_is_not_mark(tmp_path):
    src, docs = kit(tmp_path, [("1", "Метод delete карты", "srs/bc-a/function", "сигналы согласны")])
    lines, _b = sc.coverage_report(src, docs)
    assert classes(lines) == ["пробелы миграции: 1"], lines


def test_frozen_draft_stays_frozen(tmp_path):
    src, docs = kit(tmp_path, [("1", "[КК_KMS] Функция (черновик)", "frozen-KMS",
                                "frozen KMS (unapproved_jira X); черновик")])
    lines, _b = sc.coverage_report(src, docs)
    assert classes(lines) == ["заморожено: 1"], lines


def test_no_withdrawn_keeps_summary_line(tmp_path):
    # без снятых сводная строка прежняя — счётчик печатается, только когда он не ноль
    src, docs = kit(tmp_path, [("1", "Правила", "doc-rules", "reference-only")])
    lines, _b = sc.coverage_report(src, docs)
    assert lines[0].endswith("справочные 1, вне плана 0, бинарные 0; не в описи 0"), lines[0]


# ------------------------------------------------------------------ каталоги

def test_dir_with_children_is_node_empty_dir_is_defect(tmp_path):
    src, docs = kit(tmp_path, [])
    make(src / "node/child.md", page("7", "Дочерняя"))      # узел: дети есть, страницы нет
    (src / "empty").mkdir()                                  # дефект: ни страницы, ни детей
    make(src / "p99/img/a.png", "png")                       # вложения экспортёра — не в счёт
    make(src / "img/b.png", "png")
    lines, _b = sc.coverage_report(src, docs)
    node = next(ln for ln in lines if ln.startswith("каталоги-узлы"))
    assert node.startswith("каталоги-узлы без собственной страницы: 1 (у каталога есть "
                           "дочерние страницы"), node
    assert lines[lines.index(node) + 1] == "  - node/"
    defect = [ln for ln in lines if "нарушение инварианта" in ln]
    assert defect == ["каталогов без парной страницы fileN.md и без дочерних страниц "
                      "(нарушение инварианта имён выгрузки): 1"], lines
    assert lines[lines.index(defect[0]) + 1] == "  - empty/"


def test_no_empty_dirs_no_defect_line(tmp_path):
    src, docs = kit(tmp_path, [])
    make(src / "node/child.md", page("7", "Дочерняя"))
    make(src / "node/img/a.png", "png")
    lines, _b = sc.coverage_report(src, docs)
    assert not any("нарушение инварианта" in ln for ln in lines), lines
    assert any(ln.startswith("каталоги-узлы без собственной страницы: 1") for ln in lines)
