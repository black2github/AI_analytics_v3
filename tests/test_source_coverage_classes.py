# tests/test_source_coverage_classes.py
"""FB-28 КК: классы непокрытия по описи inventory.md — заморожено, контейнеры, справочные,
вне плана, бинарные, не в описи; иначе пробел миграции. С описью --strict бракует только
пробелы и страницы вне описи; без описи — прежнее поведение и строка «опись не найдена»."""
import sys
from pathlib import Path

from app.scripts.CI import source_coverage as sc

HEAD = ("| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
        "|---|---|---|---|---|---|---|\n")


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def page(pid: str, title: str, body: str = "текст страницы\n") -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n{body}"


def row(pid, title, parent="Раздел", req="function", target="srs/bc-a/function", basis="сигналы согласны"):
    return f"| {pid} | {title} | {parent} | {req} | 10 | {target} | {basis} |\n"


def kit(tmp_path: Path, plan: str = "| [X_A] | подсервис bc-a | `srs/bc-a/` |\n", inventory=True):
    root = tmp_path / "kit"
    src, docs = root / "sources/confluence", root / "docs"
    pages = {
        "1": ("Заморожено B2B", "", dict(target="frozen-B2B", basis="frozen B2B (unapproved_jira X)")),
        "2": ("Раздел функций", "", dict(target="README-реестр", basis="TOC-контейнер")),
        "3": ("Правила ведения", "", dict(target="doc-rules", basis="правила/стандарт")),
        "4": ("Схема", "![схема](img/s.png)\n", {}),
        "5": ("Виджет ЭФ", "", dict(target="srs/bc-widget/screen-form/client")),
        "6": ("Функция А", "", {}),
        "7": ("Новая страница", "", None),
        "8": ("Покрытая", "", {}),
        "9": ("Под заморозкой", "", dict(parent="Заморожено-КМС")),
        "10": ("Функция флаг", "", dict(req="function+frozen:GBO-1")),
    }
    inv = HEAD
    for pid, (title, body, r) in pages.items():
        make(src / f"p{pid}.md", page(pid, title, body or "текст страницы\n"))
        if r is not None:
            inv += row(pid, title, **r)
    make(docs / "srs/bc-a/function/fun-1.md", "---\nid: FUN-1\nconfluence_page_ids: ['8']\n---\n# Ф\n")
    if inventory:
        make(root / "inventory.md", "# Опись\n\nСкелет.\n\n" + inv)
    if plan is not None:
        make(root / "migration-plan.md", "# План\n\n" + plan)
    return src, docs


def test_classes_and_summary_line(tmp_path):
    src, docs = kit(tmp_path)
    lines, blocking = sc.coverage_report(src, docs)
    assert lines[0] == ("страниц выгрузки: 10; покрыто артефактами: 1; НЕ покрыто: 9 = пробелы "
                        "миграции 1; структурно: заморожено 3, контейнеры 1, справочные 1, вне плана 1, "
                        "бинарные 1; не в описи 1"), lines[0]
    assert blocking == 2  # пробел + не в описи
    heads = [ln for ln in lines if not ln.startswith("  ")]
    assert heads[1:] == ["пробелы миграции: 1", "не в описи: 1", "заморожено: 3", "контейнеры: 1",
                         "справочные: 1", "вне плана: 1", "бинарные: 1"], heads
    gap = lines.index("пробелы миграции: 1")
    assert lines[gap + 1] == "  - Функция А — p6.md"  # прежний формат строки


def test_no_inventory_keeps_old_report(tmp_path):
    src, docs = kit(tmp_path, inventory=False)
    lines, blocking = sc.coverage_report(src, docs)
    assert lines[0] == "страниц выгрузки: 10; покрыто артефактами: 1; НЕ покрыто: 9"
    assert lines[1] == "опись не найдена — классы непокрытия не определены"
    assert blocking == 9 and all(ln.startswith("  - ") for ln in lines[2:])


def test_strict_zero_gaps_with_structural_is_ok(tmp_path, monkeypatch):
    src, docs = kit(tmp_path)
    for pid in ("6", "7"):
        (src / f"p{pid}.md").unlink()
    monkeypatch.setattr(sys, "argv", ["source_coverage.py", "--sources", str(src),
                                      "--output", str(docs), "--strict"])
    assert sc.main() == 0
    make(src / "p7.md", page("7", "Новая страница"))  # опись отстала — F = 1
    lines, blocking = sc.coverage_report(src, docs)
    assert "не в описи 1" in lines[0] and blocking == 1
    assert sc.main() == 2


def test_explicit_inventory_argument(tmp_path):
    src, docs = kit(tmp_path)
    moved = tmp_path / "elsewhere/inventory.md"
    make(moved, (docs.parent / "inventory.md").read_text(encoding="utf-8"))
    (docs.parent / "inventory.md").unlink()
    lines, _b = sc.coverage_report(src, docs, inventory=moved)
    # опись — из аргумента; план — комплекта (рядом с docs/)
    assert "пробелы миграции 1;" in lines[0] and "вне плана 1" in lines[0]
    (docs.parent / "migration-plan.md").unlink()
    lines, _b = sc.coverage_report(src, docs, inventory=moved)
    assert "пробелы миграции 2;" in lines[0] and "вне плана 0" in lines[0]
    assert any(ln.startswith("i вне плана: подсервисы в migration-plan.md не найдены") for ln in lines)


# ---------------------------------------------------------------- несрабатывание

def test_plan_without_subservices_no_out_of_plan(tmp_path):
    src, docs = kit(tmp_path, plan="Обычный сервис без подсервисов: srs/function/\n")
    lines, _b = sc.coverage_report(src, docs)
    assert "вне плана 0" in lines[0] and "пробелы миграции 2" in lines[0]


def test_target_slug_mentioned_in_plan_is_in_plan(tmp_path):
    src, docs = kit(tmp_path, plan="| [X_A] | подсервис bc-a |\nВиджет: каталог `srs/bc-widget/` — заходом W-1.\n")
    lines, _b = sc.coverage_report(src, docs)
    assert "вне плана 0" in lines[0]


def test_image_with_text_is_not_binary(tmp_path):
    src, docs = kit(tmp_path)
    make(src / "p4.md", page("4", "Схема", "![схема](img/s.png)\n\nОписание шагов процесса.\n"))
    lines, _b = sc.coverage_report(src, docs)
    assert "бинарные 0" in lines[0] and "пробелы миграции 2" in lines[0]


def test_empty_page_is_not_binary(tmp_path):
    # пустое тело без вложений — не бинарное (пустоту объясняет опись: заморозка и т. п.)
    src, docs = kit(tmp_path)
    make(src / "p6.md", page("6", "Функция А", "\n"))
    lines, _b = sc.coverage_report(src, docs)
    assert "пробелы миграции 1" in lines[0] and "бинарные 1" in lines[0]


def test_plain_words_in_basis_do_not_classify(tmp_path):
    # «шаблон», «правила» в основании без признаков — пробел, не справочный/контейнер
    src, docs = kit(tmp_path)
    inv = (docs.parent / "inventory.md").read_text(encoding="utf-8").replace(
        "| 6 | Функция А | Раздел | function | 10 | srs/bc-a/function | сигналы согласны |",
        "| 6 | Функция А | Раздел | function | 10 | srs/bc-a/function | правила расчёта, шаблон ответа |")
    make(docs.parent / "inventory.md", inv)
    lines, _b = sc.coverage_report(src, docs)
    assert "пробелы миграции 1" in lines[0]


def test_negated_sign_stays_gap(tmp_path):
    # «НЕ frozen, GBO-… снят» в основании — живая карточка, пробел (КК 2184433380)
    src, docs = kit(tmp_path)
    inv = (docs.parent / "inventory.md").read_text(encoding="utf-8").replace(
        "| 6 | Функция А | Раздел | function | 10 | srs/bc-a/function | сигналы согласны |",
        "| 6 | Функция А | Раздел | function | 10 | srs/bc-a/function | OQ-17 закрыт (НЕ frozen, "
        "GBO-1 снят); не TOC; карточка — долг |")
    make(docs.parent / "inventory.md", inv)
    lines, _b = sc.coverage_report(src, docs)
    assert "пробелы миграции 1;" in lines[0] and "заморожено 3" in lines[0], lines[0]
