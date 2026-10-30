# tests/test_d49_zone.py
"""Д-49 п. 4 (2026-10-23): мини-комплект зоны «вне Экосистемы» — docs/modules/<имя>/ (перенос
несёт docs/ целиком). Прибор: зона не участвует в переписи карточек, схеме типов, реестре ID и
матрице; участвует в относительных ссылках и нотации; сводная i-строка зоны; переходный сторож
старого места modules/ рядом с docs/; мини-комплект без README; покрытие страниц, порог ссылок
нормализатора и долги формы 1 видят docs/modules/. На каждое — срабатывание и НЕсрабатывание."""
from pathlib import Path

from app.scripts.CI import link_debts as ld
from app.scripts.CI import selfcheck as sc
from app.scripts.CI import source_coverage as cov
from app.scripts.CI.kitcheck.checks.zone import check_module_zone
from app.scripts.CI.kitcheck.md import _kit_md, in_module_zone
from app.scripts.CI.kitcheck.checks.card_clean import check_clean_document


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid: str, title: str, typ: str = "function", pids: str = "", body: str = "текст\n") -> str:
    pid_line = f"confluence_page_ids: [{pids}]\n" if pids else ""
    return f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\n{pid_line}---\n\n# {title}\n\n{body}"


MATRIX = ("# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
          "| FUN-01 | function | А | srs/function/a.md |\n")


def kit(tmp_path: Path, zone: bool = True, readme: bool = True) -> Path:
    docs = tmp_path / "docs"
    make(docs / "srs/function/a.md", card("FUN-01", "А"))
    make(docs / "traceability-matrix.md", MATRIX)
    if zone:
        z = docs / "modules/widgets-rtl"
        if readme:
            make(z / "README.md", card("MOD-WIDGETS-RTL-000", "Паспорт", "module-kit"))
        make(z / "interface/mod-001.md", card("MOD-WIDGETS-RTL-001", "Скрипт", "module-interface"))
        make(z / "spec/scr-01.md", card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", "screen-form"))
    return docs


# ---------------------------------------------------------------- C1: зона не карточки

def test_in_module_zone_and_kit_md(tmp_path):
    docs = kit(tmp_path)
    z = docs / "modules/widgets-rtl/spec/scr-01.md"
    assert in_module_zone(z, docs) and not in_module_zone(docs / "srs/function/a.md", docs)
    assert z not in _kit_md(docs) and z in _kit_md(docs, zone=True)
    # файл прямо в docs/modules/ (не мини-комплект) — не зона
    assert not in_module_zone(docs / "modules/x.md", docs)


def test_zone_files_outside_census_and_registry(tmp_path):
    docs = kit(tmp_path)
    report, ok = sc.run(docs, None)
    total = next(ln for ln in report if ln.startswith("ИТОГО"))
    base, _ = sc.run(kit(tmp_path / "b", zone=False), None)
    assert total == next(ln for ln in base if ln.startswith("ИТОГО")), (total, base)
    assert not any("фантомные id" in ln or "MOD-WIDGETS-RTL" in ln and "реестр" in ln for ln in report)
    assert not any("поля шапки вне схемы" in ln for ln in report)
    assert "i мини-комплектов зоны: 1 (docs/modules/widgets-rtl, файлов 3)" in report


def test_kit_without_zone_has_no_zone_lines(tmp_path):
    report, _ok = sc.run(kit(tmp_path, zone=False), None)
    assert not any("мини-комплект" in ln for ln in report), report


def test_zone_relative_links_checked(tmp_path):
    # ссылки зоны участвуют в проверке относительных ссылок: битая — ✗
    docs = kit(tmp_path)
    make(docs / "modules/widgets-rtl/spec/scr-01.md",
         card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", "screen-form", body="[нет](../../../srs/none.md)\n"))
    report, ok = sc.run(docs, None)
    assert not ok and any("битые относительные ссылки" in ln for ln in report), report
    make(docs / "modules/widgets-rtl/spec/scr-01.md",
         card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", "screen-form",
              body="[А](../../../srs/function/a.md)\n"))
    report, ok = sc.run(docs, None)
    assert not any("битые относительные ссылки" in ln for ln in report), report


def test_zone_branch_form_counted(tmp_path):
    docs = kit(tmp_path)
    body = "| Поле | Логика |\n|---|---|\n| A | **Если** X, **то** Y, **иначе** Z |\n"
    make(docs / "modules/widgets-rtl/spec/scr-01.md",
         card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", "screen-form", body=body))
    report, _ok = sc.run(docs, None)
    bf = [ln for ln in report if ln.startswith("⚠ форма ветвления")]
    assert bf and "modules/widgets-rtl/spec/scr-01.md ×1" in bf[0], report
    # НЕсрабатывание: без нарушений в зоне строки формы ветвления нет
    report, _ok = sc.run(kit(tmp_path / "b"), None)
    assert not any(ln.startswith("⚠ форма ветвления") for ln in report)


# ---------------------------------------------------------------- C2, C3

def test_old_place_next_to_docs_warns_once_and_root_stays_legit(tmp_path):
    docs = kit(tmp_path, zone=False)
    make(tmp_path / "modules/widgets-rtl/README.md", card("MOD-WIDGETS-RTL-000", "Паспорт", "module-kit"))
    report, _ok = sc.run(docs, None)
    old = [ln for ln in report if ln.startswith("⚠ мини-комплект вне docs/")]
    assert old == ["⚠ мини-комплект вне docs/ — переносом не переезжает (Д-49), перенести в "
                   "docs/modules/<имя>/: modules/widgets-rtl"]
    assert not any("посторонние файлы" in ln for ln in report)


def test_docs_repo_layout_no_old_place_warning(tmp_path):
    # репозиторий документации: комплект в корне, modules/ рядом с srs/ — это и есть зона
    repo = tmp_path / "docs-x"
    make(repo / "srs/function/a.md", card("FUN-01", "А"))
    make(repo / "traceability-matrix.md", MATRIX)
    make(repo / "modules/widgets-rtl/README.md", card("MOD-WIDGETS-RTL-000", "Паспорт", "module-kit"))
    assert check_module_zone(repo) == ["i мини-комплектов зоны: 1 (docs/modules/widgets-rtl, файлов 1)"]


def test_zone_kit_without_readme_warns(tmp_path):
    docs = kit(tmp_path, readme=False)
    rep = check_module_zone(docs)
    assert ("⚠ мини-комплект без паспорта границы (module-kit-readme.md): "
            "docs/modules/widgets-rtl/ — нет README.md") in rep
    assert not any("паспорта" in ln for ln in check_module_zone(kit(tmp_path / "b")))


# ---------------------------------------------------------------- разметка подсервисов

PROFILE = ("# Профиль\n\n## Разметка подсервисов\n\n| Источник | Зона |\n|---|---|\n"
           "| [КК_Виджет_ПИН] | вне Экосистемы |\n| [КК_ВК] | подсервис bc-issue |\n")


def _mapping_kit(tmp_path):
    root = tmp_path / "kit"
    src = root / "sources/confluence"
    make(root / "README.md", PROFILE)  # профиль источников — README корня репозитория
    make(src / "p1.md", "---\ntitle: '[КК_Виджет_ПИН] ЭФ Клиента'\nconfluence_page_id: '1001'\n---\n\nтекст\n")
    make(src / "p2.md", "---\ntitle: '[КК_ВК] Функция'\nconfluence_page_id: '1002'\n---\n\nтекст\n")
    docs = root / "docs"
    make(docs / "traceability-matrix.md", MATRIX)
    return src, docs


def test_mapping_zone_page_in_docs_modules_ok(tmp_path):
    from app.scripts.CI.kitcheck.checks.source_profile import check_subservice_mapping
    src, docs = _mapping_kit(tmp_path)
    zf = docs / "modules/widgets-rtl/spec/scr-01.md"
    make(zf, card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", "screen-form", pids="'1001'"))
    rep, ok = check_subservice_mapping(docs, src, {"1001": zf})
    assert ok, rep


def test_mapping_zone_page_in_srs_still_flagged(tmp_path):
    from app.scripts.CI.kitcheck.checks.source_profile import check_subservice_mapping
    src, docs = _mapping_kit(tmp_path)
    f = docs / "srs/bc-issue/screen-form/scr-1.md"
    make(f, card("SCR-1", "ЭФ", "screen-form", pids="'1001'"))
    rep, ok = check_subservice_mapping(docs, src, {"1001": f})
    assert not ok and "docs/modules/<имя>/" in rep[0], rep


def test_mapping_ecosystem_page_in_zone_flagged(tmp_path):
    # НЕсрабатывание исключения: страница подсервиса в мини-комплекте зоны — ✗
    from app.scripts.CI.kitcheck.checks.source_profile import check_subservice_mapping
    src, docs = _mapping_kit(tmp_path)
    zf = docs / "modules/widgets-rtl/spec/fun-01.md"
    make(zf, card("MOD-WIDGETS-RTL-FUN-01", "Ф", "function", pids="'1002'"))
    rep, ok = check_subservice_mapping(docs, src, {"1002": zf})
    assert not ok and "зона только для страниц вне Экосистемы" in rep[0], rep


# ---------------------------------------------------------------- C4: покрытие

INV_HEAD = ("| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
            "|---|---|---|---|---|---|---|\n")


def _cov_kit(tmp_path):
    root = tmp_path / "kit"
    src, docs = root / "sources/confluence", root / "docs"
    for pid, title in (("1", "[КК_Виджет_ПИН] ЭФ Клиента"), ("2", "Функция А")):
        make(src / f"p{pid}.md", f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\nтекст\n")
    make(docs / "srs/bc-a/function/fun-1.md", card("FUN-1", "Ф", pids="'2'"))
    make(root / "inventory.md", "# Опись\n\n" + INV_HEAD
         + "| 1 | [КК_Виджет_ПИН] ЭФ Клиента | Виджеты | screenItemForm | 10 | вне Экосистемы "
           "(docs/modules/widgets-rtl/) | Д-49 |\n"
         + "| 2 | Функция А | Р | function | 10 | srs/bc-a/function | сигналы согласны |\n")
    make(root / "migration-plan.md", "| [X_A] | подсервис bc-a | `srs/bc-a/` |\n")
    return src, docs


def test_coverage_zone_page_covered_under_docs_modules(tmp_path):
    src, docs = _cov_kit(tmp_path)
    make(docs / "modules/widgets-rtl/spec/scr-1.md", card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", pids="'1'"))
    lines, blocking = cov.coverage_report(src, docs)
    assert "пробелы миграции 0" in lines[0] and blocking == 0
    assert lines[0].endswith("вне Экосистемы 1 (покрыто мини-комплектом 1)"), lines[0]


def test_coverage_old_place_still_covers(tmp_path):
    src, docs = _cov_kit(tmp_path)
    make(docs.parent / "modules/widgets-rtl/spec/scr-1.md", card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", pids="'1'"))
    lines, blocking = cov.coverage_report(src, docs)
    assert lines[0].endswith("вне Экосистемы 1 (покрыто мини-комплектом 1)") and blocking == 0


def test_coverage_zone_page_in_srs_is_gap(tmp_path):
    src, docs = _cov_kit(tmp_path)
    make(docs / "srs/bc-a/screen-form/scr-1.md", card("SCR-1", "ЭФ", pids="'1'"))
    lines, blocking = cov.coverage_report(src, docs)
    assert "пробелы миграции 1" in lines[0] and blocking == 1


# ---------------------------------------------------------------- C5: порог ссылок

def test_clean_link_into_docs_modules_ok(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "modules/widgets-rtl/interface/mod-001.md", "# M\n")
    make(docs / "srs/contract-call/module/call-mod-001.md",
         "---\nid: CALL-MOD-001\n---\n\n[MOD-WIDGETS-RTL-001](../../../modules/widgets-rtl/interface/mod-001.md)\n")
    rep, ok = check_clean_document(docs / "srs/contract-call/module/call-mod-001.md", docs)
    assert ok and not rep, rep


def test_clean_link_to_sources_still_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(tmp_path / "sources/стр.md", "x")
    make(docs / "srs/contract-call/call-1.md", "---\nid: CALL-1\n---\n\n[в](../../../sources/стр.md)\n")
    rep, ok = check_clean_document(docs / "srs/contract-call/call-1.md", docs)
    assert not ok and any("ВНЕ docs" in r for r in rep)


# ---------------------------------------------------------------- C6: долги формы 1

def _debts(tmp_path, zone_file: bool):
    root = tmp_path / "kit"
    docs = root / "docs"
    make(docs / "srs/function/fun-001.md",
         "---\nid: FUN-001\ntitle: 'Ф'\n---\n# Ф\n\nвызов [КК_Виджет_ПИН] ЭФ Клиента\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         "| FUN-001 | function | Ф | srs/function/fun-001.md |\n\n"
         "## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n"
         "| FUN-001 | — | нет целевого артефакта screen-form «[КК_Виджет_ПИН] ЭФ Клиента» — "
         "требуется заход create-screen-form |\n")
    make(root / "inventory.md", "# Опись\n\n" + INV_HEAD
         + "| 1001 | [КК_Виджет_ПИН] ЭФ Клиента | В | screenItemForm | 10 | вне Экосистемы "
           "(docs/modules/widgets-rtl/) | Д-49 |\n")
    if zone_file:
        make(docs / "modules/widgets-rtl/spec/scr-01.md",
             card("MOD-WIDGETS-RTL-SCR-01", "ЭФ виджета", "screen-form", pids="'1001'"))
    return ld.check(docs / "traceability-matrix.md", docs)


def test_debt_on_zone_target_covered_by_docs_modules(tmp_path):
    report, _ok = _debts(tmp_path, zone_file=True)
    ln = next(r for r in report if r.startswith("⚠ долг FUN-001"))
    assert "покрыта мини-комплектом (docs/modules/widgets-rtl/spec/scr-01.md)" in ln, report


def test_debt_on_zone_target_not_covered_points_to_docs_modules(tmp_path):
    report, _ok = _debts(tmp_path, zone_file=False)
    ln = next(r for r in report if r.startswith("⚠ долг FUN-001"))
    assert "цель — мини-комплект docs/modules/<имя>/ (Д-49)" in ln and "покрыта" not in ln, report
