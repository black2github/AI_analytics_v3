# tests/test_d46_zone.py
"""Д-46: зона «вне Экосистемы» — мини-комплект modules/<имя>/ рядом с docs/. Сторож корня и
сторож чистовика принимают modules/; source_coverage считает страницу зоны покрытой только
мини-комплектом (иначе — пробел миграции, не структурный класс); link_debts предупреждает о
долге формы 1 на цель зоны."""
from pathlib import Path

from app.scripts.CI import link_debts as ld
from app.scripts.CI import selfcheck as sc
from app.scripts.CI import source_coverage as cov
from app.scripts.CI.normalize_tables import check_clean_document


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid: str, title: str, pids: str = "") -> str:
    pid_line = f"confluence_page_ids: [{pids}]\n" if pids else ""
    return f"---\nid: {cid}\ntitle: '{title}'\ntype: function\n{pid_line}---\n\n# {title}\n\nтекст\n"


# ---------------------------------------------------------------- сторож корня

def test_root_modules_dir_is_legit_and_junk_still_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "a.md", card("X-01", "[Т] А"))
    make(docs / "traceability-matrix.md",
         "# М\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n| X-01 | function | А | a.md |\n")
    make(tmp_path / "modules/widgets-rtl/README.md", "# MOD-WIDGETS-RTL-000\n")
    report, _ok = sc.run(docs, None)
    assert not any("посторонние файлы" in ln for ln in report), report
    (tmp_path / "widgets-rtl").mkdir()  # мини-комплект не в modules/ — посторонний
    report, ok = sc.run(docs, None)
    junk = [ln for ln in report if "посторонние файлы" in ln]
    assert not ok and junk and "widgets-rtl" in junk[0] and "modules" not in junk[0].split("(")[1].split(")")[0]


# ---------------------------------------------------------------- сторож чистовика

def _clean(tmp_path, body):
    docs = tmp_path / "docs"
    make(docs / "srs/contract-call/call-int-001.md", "---\nid: CALL-INT-001\n---\n\n" + body)
    return check_clean_document(docs / "srs/contract-call/call-int-001.md", docs)


def test_clean_link_into_modules_ok(tmp_path):
    make(tmp_path / "modules/widgets-rtl/interface/mod-widgets-rtl-001-pin-input.md", "# M\n")
    rep, ok = _clean(tmp_path, "[MOD-WIDGETS-RTL-001](../../../modules/widgets-rtl/interface/"
                               "mod-widgets-rtl-001-pin-input.md)\n")
    assert ok and not rep, rep


def test_clean_missing_modules_target_and_sources_still_flagged(tmp_path):
    rep, ok = _clean(tmp_path, "[нет](../../../modules/widgets-rtl/interface/missing.md)\n")
    assert not ok and any("битая" in r for r in rep)
    make(tmp_path / "sources/стр.md", "x")
    rep, ok = _clean(tmp_path, "[выгрузка](../../../sources/стр.md)\n")
    assert not ok and any("ВНЕ docs" in r for r in rep)


# ---------------------------------------------------------------- source_coverage

INV_HEAD = ("| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
            "|---|---|---|---|---|---|---|\n")


def _kit(tmp_path, zone_target="вне Экосистемы (modules/widgets-rtl/)"):
    root = tmp_path / "kit"
    src, docs = root / "sources/confluence", root / "docs"
    for pid, title in (("1", "[КК_Виджет_ПИН] ЭФ Клиента"), ("2", "Функция А"), ("3", "Виджет чужого")):
        make(src / f"p{pid}.md", f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\nтекст\n")
    make(docs / "srs/bc-a/function/fun-1.md", card("FUN-1", "Ф", "'2'"))
    make(root / "inventory.md", "# Опись\n\n" + INV_HEAD
         + f"| 1 | [КК_Виджет_ПИН] ЭФ Клиента | Виджеты | screenItemForm | 10 | {zone_target} | Д-46 |\n"
         + "| 2 | Функция А | Р | function | 10 | srs/bc-a/function | сигналы согласны |\n"
         + "| 3 | Виджет чужого | Р | function | 10 | srs/bc-widget/function/client | сигналы согласны |\n")
    make(root / "migration-plan.md", "| [X_A] | подсервис bc-a | `srs/bc-a/` |\n")
    return src, docs


def test_zone_page_without_mini_kit_is_gap(tmp_path):
    src, docs = _kit(tmp_path)
    lines, blocking = cov.coverage_report(src, docs)
    assert lines[0].endswith("пробелы миграции 1; структурно: заморожено 0, контейнеры 0, справочные 0, "
                             "вне плана 1, бинарные 0; не в описи 0; вне Экосистемы 1 (покрыто "
                             "мини-комплектом 0)"), lines[0]
    assert blocking == 1
    gap = lines.index("пробелы миграции: 1")
    assert "зона «вне Экосистемы»: дом — мини-комплект docs/modules/<имя>/" in lines[gap + 1]


def test_zone_page_covered_by_mini_kit(tmp_path):
    src, docs = _kit(tmp_path)
    make(docs.parent / "modules/widgets-rtl/screen-form/scr-1.md", card("MOD-WIDGETS-RTL-010", "ЭФ", "'1'"))
    lines, blocking = cov.coverage_report(src, docs)
    assert "покрыто артефактами: 2; НЕ покрыто: 1" in lines[0] and "пробелы миграции 0" in lines[0]
    assert lines[0].endswith("вне Экосистемы 1 (покрыто мини-комплектом 1)") and blocking == 0


def test_zone_page_covered_only_in_docs_is_gap(tmp_path):
    # карточка зоны в docs/ — не дом зоны: страница остаётся пробелом с пометкой
    src, docs = _kit(tmp_path)
    make(docs / "srs/bc-a/screen-form/scr-1.md", card("SCR-1", "ЭФ", "'1'"))
    lines, _b = cov.coverage_report(src, docs)
    assert "пробелы миграции 1" in lines[0]
    assert any("(покрыта карточкой комплекта — не дом зоны)" in ln for ln in lines), lines


def test_zone_by_basis_word_modules(tmp_path):
    src, docs = _kit(tmp_path, zone_target="srs/bc-widget/screen-form/client")
    inv = (docs.parent / "inventory.md").read_text(encoding="utf-8").replace("| Д-46 |", "| → modules/widgets-rtl/ |")
    make(docs.parent / "inventory.md", inv)
    lines, _b = cov.coverage_report(src, docs)
    assert "вне Экосистемы 1" in lines[0] and "вне плана 1" in lines[0]


def test_no_zone_rows_no_suffix(tmp_path):
    # НЕсрабатывание: без страниц зоны сводная строка прежняя, «вне плана» — как было
    src, docs = _kit(tmp_path, zone_target="srs/bc-widget/screen-form/client")
    lines, _b = cov.coverage_report(src, docs)
    assert "вне Экосистемы" not in lines[0] and "вне плана 2" in lines[0]


# ---------------------------------------------------------------- link_debts

def _debts(tmp_path, row, zone_target="вне Экосистемы (modules/widgets-rtl/)"):
    root = tmp_path / "kit"
    docs = root / "docs"
    make(docs / "srs/function/fun-001.md",
         "---\nid: FUN-001\ntitle: 'Ф'\n---\n# Ф\n\nвызов [КК_Виджет_ПИН] ЭФ Клиента; переход на "
         "[КК_Виджет_ПИН] ПИН-код установлен/изменен\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         "| FUN-001 | function | Ф | srs/function/fun-001.md |\n\n"
         "## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n" + row)
    make(root / "inventory.md", "# Опись\n\n" + INV_HEAD
         + f"| 1 | [КК_Виджет_ПИН] ЭФ Клиента | В | screenItemForm | 10 | {zone_target} | Д-46 |\n"
         + f"| 2 | [КК_Виджет_ПИН] ЭФ Клиента: ПИН-код установлен/изменен | В | screenItemForm | 10 | {zone_target} | Д-46 |\n")
    return ld.check(docs / "traceability-matrix.md", docs)


def test_form1_debt_on_zone_target_warns(tmp_path):
    report, ok = _debts(tmp_path, "| FUN-001 | — | нет целевого артефакта screen-form «[КК_Виджет_ПИН] ЭФ "
                                  "Клиента» — требуется заход create-screen-form |\n")
    assert ok
    assert any(r.startswith("⚠ долг FUN-001 «[КК_Виджет_ПИН] ЭФ Клиента» — цель в зоне «вне Экосистемы»")
               for r in report), report


def test_form1_debt_tail_title_match_warns(tmp_path):
    # ЭФ виджета в описи — «ЭФ Клиента: X», в долге — «[тег] X» (L1424 КК)
    report, _ok = _debts(tmp_path, "| FUN-001 | — | нет целевого артефакта screen-form «[КК_Виджет_ПИН] "
                                   "ПИН-код установлен/изменен» — требуется заход create-screen-form |\n")
    assert any("цель в зоне «вне Экосистемы»" in r for r in report), report


def test_form1_debt_without_zone_no_warning(tmp_path):
    # НЕсрабатывание: та же строка, но опись не относит страницы к зоне
    report, _ok = _debts(tmp_path, "| FUN-001 | — | нет целевого артефакта screen-form «[КК_Виджет_ПИН] ЭФ "
                                   "Клиента» — требуется заход create-screen-form |\n",
                         zone_target="srs/bc-widget/screen-form/client")
    assert not any("вне Экосистемы" in r for r in report), report


def test_out_of_plan_issue_row_not_flagged_as_form1(tmp_path):
    # строка вида «вне плана» (второй формат) — не долг формы 1, ⚠ зоны нет
    report, _ok = _debts(tmp_path, "| FUN-001 | — | долг вне плана: «[КК_Виджет_ПИН] ЭФ Клиента» — причина: "
                                   "подсервис bc-widget вне плана миграции (OQ-1); ответственный: владелец; "
                                   "ограничение: нет; закрытие: включение подсервиса в план |\n")
    assert not any("цель в зоне «вне Экосистемы»" in r for r in report), report
