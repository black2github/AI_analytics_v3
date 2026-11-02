# tests/test_source_coverage_base_contract.py
"""Класс непокрытия «базовый контракт» (решение владельца канона 2026-11-02, КК CALL-EXT-010 ←
страницы-копии метода ТЕССА): страница метода внешней АС — копия страницы владельца; дом —
базовый контракт в docs-external-contracts. Признак узкий: «базовый контракт EXTINT-<AS>-NNN»
с реальным ID в целевом типе или основании описи; без ID и с отрицанием — пробел."""
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


def kit(tmp_path: Path, rows, covered=("99",)):
    """rows: (pid, title, target, basis); страницы covered покрыты карточкой."""
    root = tmp_path / "kit"
    src, docs = root / "sources/confluence", root / "docs"
    inv = HEAD
    for pid, title, target, basis in rows:
        make(src / f"p{pid}.md", page(pid, title))
        inv += f"| {pid} | {title} | Раздел | integration | 10 | {target} | {basis} |\n"
    make(src / "p99.md", page("99", "Покрытая"))
    ids = ", ".join(f"'{c}'" for c in covered)
    make(docs / "srs/bc-a/function/fun-1.md", f"---\nid: FUN-1\nconfluence_page_ids: [{ids}]\n---\n# Ф\n")
    make(root / "inventory.md", "# Опись\n\n" + inv)
    make(root / "migration-plan.md", "# План\n\n" + PLAN)
    return src, docs


def classes(lines):
    return [ln for ln in lines if not ln.startswith("  ")][1:]


def test_base_contract_class_summary_and_group(tmp_path):
    src, docs = kit(tmp_path, [
        ("1", "Копия [КК] ТЕССА_Метод загрузки", "вне SRS: базовый контракт EXTINT-TESSA-001",
         "страница метода владельца"),
        ("2", "[КК] ТЕССА_Входящие параметры", "вне SRS", "базовый контракт EXTINT-TESSA-001 §2"),
    ])
    lines, blocking = sc.coverage_report(src, docs)
    assert "снято с миграции" not in lines[0]
    assert ("справочные 0, базовый контракт 2, вне плана 0" in lines[0]), lines[0]
    assert classes(lines) == ["базовый контракт: 2"], lines
    assert any(ln.startswith("  - Копия [КК] ТЕССА_Метод загрузки — ")
               and ln.endswith(" → EXTINT-TESSA-001") for ln in lines), lines
    assert blocking == 0


def test_strict_does_not_block_on_base_contract(tmp_path, monkeypatch):
    src, docs = kit(tmp_path, [("1", "Метод", "вне SRS: базовый контракт EXTINT-TESSA-001", "x")])
    monkeypatch.setattr(sys, "argv", ["source_coverage.py", "--sources", str(src),
                                      "--output", str(docs), "--strict"])
    assert sc.main() == 0


# ---------------------------------------------------------------- несрабатывание

def test_base_contract_without_id_is_gap(tmp_path):
    src, docs = kit(tmp_path, [("1", "Метод", "вне SRS: базовый контракт", "страница метода")])
    lines, blocking = sc.coverage_report(src, docs)
    assert "пробелы миграции 1;" in lines[0] and "базовый контракт" not in lines[0], lines[0]
    assert blocking == 1


def test_negated_base_contract_is_gap(tmp_path):
    src, docs = kit(tmp_path, [("1", "Функция", "srs/bc-a/function",
                                "не базовый контракт EXTINT-X-001 — своя функция")])
    lines, blocking = sc.coverage_report(src, docs)
    assert "пробелы миграции 1;" in lines[0] and "базовый контракт" not in lines[0], lines[0]
    assert blocking == 1


def test_covered_base_contract_page_not_listed(tmp_path):
    src, docs = kit(tmp_path, [("1", "Метод", "вне SRS: базовый контракт EXTINT-TESSA-001", "x")],
                    covered=("99", "1"))
    lines, blocking = sc.coverage_report(src, docs)
    assert "базовый контракт" not in "\n".join(lines) and blocking == 0, lines
