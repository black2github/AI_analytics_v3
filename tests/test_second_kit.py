# tests/test_second_kit.py
"""Второй комплект в исходном репозитории команды (постановка 11.11.2026): сервис нескольких
команд ведётся доменным репозиторием с комплектом на команду; команда держит свой комплект такого
сервиса вторым корнем рядом с docs/. Объявление — строка «комплект <путь>» таблицы «Разметка
подсервисов» профиля источников; матчер из одних цифр — page_id страницы.

Инварианты:
1. один разбор таблицы, два независимых измерения: комплект — первая подошедшая строка
   «комплект …», зона части — первая подошедшая из прочих строк;
2. корень репозитория: верхний каталог объявленного корня штатный, объявленный без каталога — ⚠,
   необъявленный — прежний ✗; прогон второго комплекта проверяет тот же корень репозитория;
3. «страница → свой комплект» — ✗ в обе стороны, по главному источнику карточки (доп. источник
   из другого комплекта — без ✗);
4. покрытие: страница другого комплекта — класс «другой комплект», не пробел; страница своего
   комплекта без карточки — пробел; ни одна страница не выпадает из обоих прогонов;
5. опись, план и журнал — одни на репозиторий: из второго корня находятся в корне репозитория;
6. без строк «комплект …» — прежнее поведение.
"""
import sys
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI import source_coverage as cov
from app.scripts.CI.kitcheck import fs as kfs
from app.scripts.CI.kitcheck.checks import source_profile as sp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402

KIT = "docs-f1/bc"


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def source(title: str, pid: str) -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\nтекст\n"


def card(cid: str, pids: str) -> str:
    return (f"---\nid: {cid}\ntitle: 'К'\ntype: function\nconfluence_page_ids: [{pids}]\n---\n\n"
            f"# {cid}. К\n\nт\n")


def profile(rows: str) -> str:
    return ("# Профиль источников\n\n## Разметка подсервисов\n\n"
            "| Матчер (тег или ветвь) | Зона |\n|---|---|\n" + rows + "\n## Прочее\n")


ROWS = (f"| [КК_БК] | подсервис bc-status |\n"
        f"| 900002 | комплект {KIT} |\n"
        f"| 900003 | комплект {KIT} |\n")


def repo(tmp_path: Path, rows: str = ROWS, second: bool = True) -> Path:
    """Исходный репозиторий: страница 900001 — основной комплект (подсервис bc-status), 900002 и
    900003 — второй комплект (page_id), 900004 — дочерняя страница 900002 (не размечена)."""
    root = tmp_path / "src-x"
    (root / ".git").mkdir(parents=True)  # корень репозитория: --docs <root>/docs
    make(root / "README.md", profile(rows))
    conf = root / "sources" / "confluence"
    make(conf / "kk" / "p1.md", source("[КК_БК] Функция", "900001"))
    make(conf / "kk" / "p2.md", source("Метод адаптера", "900002"))
    make(conf / "kk" / "p2" / "p4.md", source("Пример метода", "900004"))
    make(conf / "kk" / "p3.md", source("Обмен адаптера", "900003"))
    make(root / "docs" / "srs" / "bc-status" / "function" / "fun-1.md", card("FUN-1", "900001"))
    if second:
        make(root / KIT / "srs" / "calls" / "call-1.md", card("CALL-EXT-001", "900002"))
    return root


def ctx(docs: Path, sources=None, kit: str = "") -> "sc._KitCtx":
    return sc._KitCtx(docs=docs, sources=sources, strict=False, catalog=None, card_ids={},
                      card_titles={}, fm_schema_issues=[], groups={}, idx={}, kit=kit)


# ---------------------------------------------------------------- разбор профиля

def test_kit_rows_and_declared_kits(tmp_path):
    root = repo(tmp_path)
    prof = root / "README.md"
    assert sp.kit_rows(prof) == [("900002", KIT), ("900003", KIT)]
    assert sp.declared_kits(prof) == [KIT]


def test_kit_row_is_not_zone_row(tmp_path):
    # строка «комплект …» зону части не задаёт: карта зон — как без неё
    root = repo(tmp_path)
    assert sp._load_subservice_map(root / "README.md") == [
        ("[КК_БК]", "bc-status", "slug", None)]


def test_kit_row_with_part_zone_after_comma(tmp_path):
    prof = make(tmp_path / "README.md", profile(f"| 900002 | комплект {KIT}, подсервис bc-a |\n"))
    assert sp.kit_rows(prof) == [("900002", KIT)]
    assert sp._load_subservice_map(prof) == [("900002", "bc-a", "slug", None)]


def test_kit_row_bad_forms_not_recognised(tmp_path):
    prof = make(tmp_path / "README.md", profile(
        "| 1 | комплект ../чужое |\n| 2 | комплект a/b, нечто |\n| 3 | комплект a/b, сервис z |\n"))
    assert sp.kit_rows(prof) == []
    assert sp._load_subservice_map(prof) is None


def test_backticks_and_trailing_slash_in_kit_path(tmp_path):
    prof = make(tmp_path / "README.md", profile(f"| 900002 | комплект `{KIT}/` |\n"))
    assert sp.declared_kits(prof) == [KIT]


def test_page_id_matcher_exact_page_only():
    # цифровой матчер — ровно страница: не префикс титула, не ветвь, не потомки
    assert sp.row_matches("900002", "Метод", "kk", "900002")
    assert not sp.row_matches("900002", "900002 Метод", "900002", "900004")
    # прежние виды матчера — как были
    assert sp.row_matches("[КК_БК]", "[КК_БК] Функция", "kk", "1")
    assert sp.row_matches("[kk]", "Т", "kk", "1")


def test_kit_and_zone_are_independent_dimensions(tmp_path):
    # 2.2: строка зоны части выше строки комплекта, обе подходят странице — комплект определён
    rows = f"| [КК_БК] | подсервис bc-status |\n| 900005 | комплект {KIT} |\n"
    root = repo(tmp_path, rows=rows, second=False)
    make(root / "sources/confluence/kk/p5.md", source("[КК_БК] Метод адаптера", "900005"))
    krows = sp.kit_rows(root / "README.md")
    assert sp.kit_of_page(krows, "[КК_БК] Метод адаптера", "kk", "900005") == KIT
    # и зона части у страницы второго комплекта — по своей строке
    make(root / KIT / "srs/calls/call-5.md", card("CALL-EXT-005", "900005"))
    rep, ok = sp.check_subservice_mapping(root / KIT, root / "sources/confluence",
                                          {"900005": root / KIT / "srs/calls/call-5.md"}, KIT)
    assert not ok and any("подсервис «bc-status»" in ln for ln in rep), rep


def test_kit_of_root(tmp_path):
    root = repo(tmp_path)
    assert sp.kit_of_root(root / KIT) == (root.resolve(), KIT)
    assert sp.kit_of_root(root / "docs") is None
    assert sp.kit_of_root(root / "docs-f1") is None


# ---------------------------------------------------------------- опись из второго корня

def test_find_kit_file_from_second_kit(tmp_path):
    root = repo(tmp_path)
    inv = make(root / "inventory.md", "# Опись\n")
    assert kfs.find_kit_file(root / KIT, "inventory.md") == inv.resolve()
    assert kfs.find_kit_file(root / "docs", "inventory.md") == root / "inventory.md"


def test_find_kit_file_undeclared_root_not_found(tmp_path):
    # без объявления — прежний поиск: корень и родитель, корень репозитория не смотрится
    root = repo(tmp_path, rows="| [КК_БК] | подсервис bc-status |\n")
    make(root / "inventory.md", "# Опись\n")
    assert kfs.find_kit_file(root / KIT, "inventory.md") is None


# ---------------------------------------------------------------- корень репозитория

def test_repo_root_declared_kit_dir_is_regular(tmp_path):
    root = repo(tmp_path)
    rep, ok = sc._kc_repo_root(ctx(root / "docs", root / "sources/confluence"))
    assert ok, rep
    assert not any("посторонние" in ln for ln in rep), rep


def test_repo_root_undeclared_dir_still_junk(tmp_path):
    root = repo(tmp_path)
    make(root / "docs-чужое" / "x.md", "# x\n")
    rep, ok = sc._kc_repo_root(ctx(root / "docs", root / "sources/confluence"))
    assert not ok and any("посторонние файлы ×1 (docs-чужое)" in ln for ln in rep), rep


def test_repo_root_declared_kit_missing_warns(tmp_path):
    root = repo(tmp_path, second=False)
    rep, ok = sc._kc_repo_root(ctx(root / "docs"))
    assert ok
    assert [ln for ln in rep if ln.startswith("⚠")] == [
        f"⚠ корень репозитория: комплект {KIT}/ объявлен в профиле источников (строка "
        "«комплект …» таблицы «Разметка подсервисов»), каталога нет — объявление без комплекта"]


def test_repo_root_second_kit_run_checks_repo_root(tmp_path):
    # прогон второго комплекта: корень проверки — корень репозитория (посторонний там — ✗)
    root = repo(tmp_path)
    rep, ok = sc._kc_repo_root(ctx(root / KIT, kit=KIT))
    assert ok, rep
    make(root / "tool.py", "x = 1\n")
    rep, ok = sc._kc_repo_root(ctx(root / KIT, kit=KIT))
    assert not ok and any("tool.py" in ln for ln in rep), rep


def test_repo_root_without_kit_rows_unchanged(tmp_path):
    root = repo(tmp_path, rows="| [КК_БК] | подсервис bc-status |\n")
    rep, ok = sc._kc_repo_root(ctx(root / "docs"))
    assert not ok and any("посторонние файлы ×1 (docs-f1)" in ln for ln in rep), rep


# ---------------------------------------------------------------- страница → свой комплект

def _cards(root: Path, base: Path, **pid_rel):
    return {pid: base / rel for pid, rel in pid_rel.items()}


def test_kit_mapping_ok_both_runs(tmp_path):
    root = repo(tmp_path)
    src = root / "sources/confluence"
    rep, ok = sp.check_kit_mapping(root / "docs", src,
                                   {"900001": root / "docs/srs/bc-status/function/fun-1.md"})
    assert ok and rep[0].startswith("разметка комплектов: соответствие"), rep
    rep, ok = sp.check_kit_mapping(root / KIT, src,
                                   {"900002": root / KIT / "srs/calls/call-1.md"}, KIT)
    assert ok and "прогон: docs-f1/bc/" in rep[0], rep


def test_kit_mapping_second_kit_page_in_main(tmp_path):
    root = repo(tmp_path)
    c = make(root / "docs/srs/calls/call-2.md", card("CALL-EXT-002", "900002"))
    rep, ok = sp.check_kit_mapping(root / "docs", root / "sources/confluence", {"900002": c})
    assert not ok
    assert rep == ["✗ разметка комплекта: основной docs/srs/calls/call-2.md — источник «Метод "
                   "адаптера» размечен в комплект docs-f1/bc/, карточка лежит в комплекте основной "
                   "docs/ (профиль источников: страница → свой комплект; карточку перенести в свой "
                   "комплект)"], rep


def test_kit_mapping_main_page_in_second_kit(tmp_path):
    root = repo(tmp_path)
    c = make(root / KIT / "srs/function/fun-1.md", card("FUN-1", "900001"))
    rep, ok = sp.check_kit_mapping(root / KIT, root / "sources/confluence", {"900001": c}, KIT)
    assert not ok and len(rep) == 1
    assert rep[0].startswith("✗ разметка комплекта: docs-f1/bc/srs/function/fun-1.md — источник "
                             "«[КК_БК] Функция» размечен в комплект основной docs/"), rep


def test_kit_mapping_extra_source_from_other_kit_no_fail(tmp_path):
    # карточка вызова основного комплекта называет страницу метода второго в доп. источниках
    root = repo(tmp_path)
    make(root / "docs/srs/bc-status/function/fun-1.md", card("FUN-1", "900001, 900002"))
    report, _ok = sc.run(root / "docs", root / "sources/confluence")
    assert not any("✗ разметка комплекта" in ln for ln in report), report
    assert any(ln.startswith("разметка комплектов: соответствие") for ln in report), report


def test_kit_mapping_absent_page_id_warns(tmp_path):
    root = repo(tmp_path, rows=ROWS + f"| 977777 | комплект {KIT} |\n")
    rep, ok = sp.check_kit_mapping(root / "docs", root / "sources/confluence", {})
    assert ok
    assert rep[1:] == [f"⚠ разметка комплекта: строка «комплект {KIT}» с матчером page_id 977777 "
                       "— страницы в выгрузке нет, строка ничего не размечает"], rep


def test_kit_mapping_silent_without_kit_rows(tmp_path):
    root = repo(tmp_path, rows="| [КК_БК] | подсервис bc-status |\n")
    assert sp.check_kit_mapping(root / "docs", root / "sources/confluence", {}) == ([], True)


def test_subservice_mapping_skips_other_kit_pages(tmp_path):
    # зона части по странице другого комплекта в прогоне основного не судится (её ловит
    # «страница → свой комплект»)
    rows = f"| [КК_БК] | подсервис bc-status |\n| 900005 | комплект {KIT} |\n"
    root = repo(tmp_path, rows=rows, second=False)
    make(root / "sources/confluence/kk/p5.md", source("[КК_БК] Метод адаптера", "900005"))
    c = make(root / "docs/srs/calls/call-5.md", card("CALL-EXT-005", "900005"))
    rep, ok = sp.check_subservice_mapping(root / "docs", root / "sources/confluence",
                                          {"900005": c})
    assert ok, rep


def test_selfcheck_cli_derives_kit(tmp_path):
    root = repo(tmp_path)
    report, _ok = sc.run(root / KIT, root / "sources/confluence")
    assert any("прогон: docs-f1/bc/" in ln for ln in report), report
    assert not any("✗ разметка комплекта" in ln for ln in report), report


# ---------------------------------------------------------------- покрытие

def _head(lines):
    return lines[0]


def test_coverage_main_run_other_kit_class(tmp_path):
    root = repo(tmp_path)
    lines, blocking = cov.coverage_report(root / "sources/confluence", root / "docs")
    # 900001 покрыта; 900002, 900003 — другой комплект; 900004 (дочерняя, без строки) — пробел
    assert _head(lines) == ("страниц выгрузки: 4; покрыто артефактами: 1; другой комплект: 2; "
                            "НЕ покрыто: 1")
    assert lines[1] == ("i другой комплект docs-f1/bc/: страниц 2 — по строкам «комплект …» "
                        "профиля источников, покрытие — в прогоне того комплекта (измеряется "
                        "основной docs/)")
    assert blocking == 1
    assert not any("Метод адаптера" in ln for ln in lines), lines


def test_coverage_second_kit_run_gap_stays_gap(tmp_path):
    root = repo(tmp_path)
    lines, blocking = cov.coverage_report(root / "sources/confluence", root / KIT)
    # своё: 900002 покрыта, 900003 — пробел; 900001 и 900004 — основной комплект
    assert _head(lines) == ("страниц выгрузки: 4; покрыто артефактами: 1; другой комплект: 2; "
                            "НЕ покрыто: 1")
    assert "i другой комплект основной docs/: страниц 2" in lines[1]
    assert blocking == 1
    assert any("Обмен адаптера" in ln for ln in lines), lines


def test_coverage_no_page_lost_between_runs(tmp_path):
    # каждая страница своя ровно в одном прогоне: там она покрыта либо пробел
    root = repo(tmp_path)
    src = root / "sources/confluence"
    own_runs = {}
    gaps = set()
    for out, kit in ((root / "docs", ""), (root / KIT, KIT)):
        lines, _b = cov.coverage_report(src, out, kit=kit)
        p, _par, covered, _n, _o = cov.collect(src, out)
        other, _k, _abs = cov.classify_kits(p, src, kit)
        for pid in p:
            if pid not in other:
                own_runs[pid] = own_runs.get(pid, 0) + 1
                if pid not in covered:
                    gaps.add(pid)
    assert own_runs == {"900001": 1, "900002": 1, "900003": 1, "900004": 1}
    assert gaps == {"900003", "900004"}


def test_coverage_no_page_lost_kit_declared_without_dir(tmp_path):
    # объявлен комплект без каталога: прогона второго нет — его страницы пробелы основного
    root = repo(tmp_path, second=False)
    src = root / "sources/confluence"
    p, _par, covered, _n, _o = cov.collect(src, root / "docs")
    other, _k, absent = cov.classify_kits(p, src, "")
    assert other == {} and absent == {KIT: 2}
    assert {pid for pid in p if pid not in covered} == {"900002", "900003", "900004"}


def test_coverage_kit_declared_without_dir_stays_gap_with_warning(tmp_path):
    root = repo(tmp_path, second=False)
    lines, blocking = cov.coverage_report(root / "sources/confluence", root / "docs")
    assert lines[0] == ("страниц выгрузки: 4; покрыто артефактами: 1; другой комплект: 0; "
                        "НЕ покрыто: 3")
    assert lines[1] == (f"⚠ комплект {KIT}/ объявлен, каталога нет — его страницы (2) "
                        "считаются в этом комплекте")
    assert blocking == 3
    assert any("Метод адаптера" in ln for ln in lines), lines


def test_coverage_kit_dir_appears_empty(tmp_path):
    # каталог появился (пустой): страницы уходят в «другой комплект» основного и пробелами
    # в прогон второго
    root = repo(tmp_path, second=False)
    (root / KIT).mkdir(parents=True)
    src = root / "sources/confluence"
    lines, blocking = cov.coverage_report(src, root / "docs")
    assert lines[0] == ("страниц выгрузки: 4; покрыто артефактами: 1; другой комплект: 2; "
                        "НЕ покрыто: 1")
    assert not any(ln.startswith("⚠ комплект") for ln in lines), lines
    lines, blocking = cov.coverage_report(src, root / KIT)
    assert lines[0] == ("страниц выгрузки: 4; покрыто артефактами: 0; другой комплект: 2; "
                        "НЕ покрыто: 2")
    assert blocking == 2


def test_coverage_with_inventory_from_second_kit(tmp_path):
    root = repo(tmp_path)
    make(root / "inventory.md", "# Опись\n\n| page_id | title | родитель | req_type | строк | "
         "целевой тип (гипотеза) | основание |\n|---|---|---|---|---|---|---|\n"
         "| 900003 | Обмен адаптера | М | x | 1 | srs/calls | р |\n")
    lines, blocking = cov.coverage_report(root / "sources/confluence", root / KIT)
    assert lines[0].startswith("страниц выгрузки: 4; покрыто артефактами: 1; другой комплект: 2; "
                               "НЕ покрыто: 1 = пробелы миграции 1;"), lines[0]
    assert blocking == 1


def test_coverage_kit_row_unmatched_removes_nothing(tmp_path):
    root = repo(tmp_path, rows="| 977777 | комплект docs-f1/bc |\n")
    lines, blocking = cov.coverage_report(root / "sources/confluence", root / "docs")
    assert _head(lines) == ("страниц выгрузки: 4; покрыто артефактами: 1; другой комплект: 0; "
                            "НЕ покрыто: 3")
    assert blocking == 3
    assert not any(ln.startswith("i другой комплект") for ln in lines), lines


def test_coverage_without_kit_rows_unchanged(tmp_path):
    root = repo(tmp_path, rows="| [КК_БК] | подсервис bc-status |\n")
    lines, blocking = cov.coverage_report(root / "sources/confluence", root / "docs")
    assert _head(lines) == "страниц выгрузки: 4; покрыто артефактами: 1; НЕ покрыто: 3"
    assert blocking == 3


def test_class_order_other_kit_last():
    assert cov.CLASS_ORDER[-1] == cov.OTHER_KIT == "другой комплект"


# ---------------------------------------------------------------- гейт переноса

def test_gate_second_kit_passes_kit(tmp_path):
    root = repo(tmp_path)
    make(root / "inventory.md", "# Опись\n")
    lines, _ready, _data = tg.run_gate(root, docs_name=KIT, no_validator=True)
    text = "\n".join(lines)
    assert f"комплект {KIT}/ объявлен в профиле источников" in text, text
    assert "разметка комплекта" not in text, text
    assert f"опись: {(root / 'inventory.md').resolve().as_posix()}" in text, text


def test_gate_main_kit_no_kit_line(tmp_path):
    root = repo(tmp_path)
    lines, _ready, _data = tg.run_gate(root, no_validator=True)
    text = "\n".join(lines)
    assert "объявлен в профиле источников" not in text, text
    assert "разметка комплекта" not in text, text


# ---------------------------------------------------------------- журнал вопросов: поле «Комплект»

def _oq(*entries):
    return "# Открытые вопросы\n\n" + "\n".join(entries)


def _entry(num, status="открыт", kit_line="", body="", head="Вопрос"):
    return (f"## OQ-{num}. {head}\n" + (f"{kit_line}\n" if kit_line else "")
            + f"- **Статус:** {status}\n{body}\n")


def _opened(root, kit):
    info = {}
    _f, opened = tg.open_questions(root, root / (kit or "docs"),
                                   root / "sources/confluence", None, kit, info)
    return opened, info


def test_oq_kit_field_counts_only_in_its_kit(tmp_path):
    root = repo(tmp_path)
    make(root / "open-questions.md", _oq(
        _entry("001", kit_line=f"- **Комплект:** {KIT}"),
        _entry("002"),
        _entry("003", kit_line="- Комплект: docs"),
        _entry("004", kit_line=f"- Комплект: `{KIT}/`")))
    opened, info = _opened(root, KIT)
    assert opened == ["OQ-001", "OQ-004"] and info["other"] == 2 and info["warns"] == []
    opened, info = _opened(root, "")
    assert opened == ["OQ-002", "OQ-003"] and info["other"] == 2 and info["warns"] == []


def test_oq_closed_entry_with_field_counted_nowhere(tmp_path):
    root = repo(tmp_path)
    make(root / "open-questions.md", _oq(_entry("001", status="закрыт",
                                                kit_line=f"- Комплект: {KIT}")))
    assert _opened(root, KIT)[0] == [] and _opened(root, "")[0] == []
    assert _opened(root, "")[1]["other"] == 0


def test_oq_unknown_kit_value_warns_and_stays_main(tmp_path):
    root = repo(tmp_path)
    make(root / "open-questions.md", _oq(_entry("007", kit_line="- Комплект: docs-f1/чужое")))
    opened, info = _opened(root, "")
    assert opened == ["OQ-007"]
    assert info["warns"] == ["OQ-007: поле «Комплект: docs-f1/чужое» не совпало ни с одним "
                             "комплектом профиля источников (строки «комплект …») и не «docs» — "
                             "запись считается за основным комплектом; поправить значение поля"]
    opened, info = _opened(root, KIT)
    assert opened == [] and len(info["warns"]) == 1


def test_oq_main_entry_naming_second_kit_page_warns(tmp_path):
    root = repo(tmp_path)
    make(root / "open-questions.md", _oq(
        _entry("010", body="Страница 900002 — что вернуть?"),
        _entry("011", status="закрыт", body="Страница 900003"),
        _entry("012", head="Про 900001")))
    opened, info = _opened(root, "")
    assert opened == ["OQ-010", "OQ-012"]
    assert info["warns"] == ["OQ-010: открытая запись без поля «Комплект» называет страницу "
                             f"900002, объявленную в комплект {KIT}/ — запись считается за "
                             f"основным комплектом; если вопрос того комплекта — поле «Комплект: "
                             f"{KIT}»"]
    # в прогоне второго комплекта предупреждение не печатается
    assert _opened(root, KIT)[1]["warns"] == []


def test_oq_without_kit_rows_whole_journal(tmp_path):
    root = repo(tmp_path, rows="| [КК_БК] | подсервис bc-status |\n")
    make(root / "open-questions.md", _oq(_entry("001", kit_line=f"- Комплект: {KIT}"),
                                         _entry("002")))
    opened, info = _opened(root, "")
    assert opened == ["OQ-001", "OQ-002"] and info == {}


def test_gate_oq_lines(tmp_path):
    root = repo(tmp_path)
    make(root / "open-questions.md", _oq(_entry("001", kit_line=f"- Комплект: {KIT}"),
                                         _entry("002", body="страница 900002")))
    text = "\n".join(tg.run_gate(root, docs_name=KIT, no_validator=True)[0])
    assert "открытые вопросы без долга в матрице: 1 (OQ-001)" in text, text
    assert "открытых записей других комплектов: 1" in text, text
    text = "\n".join(tg.run_gate(root, no_validator=True)[0])
    assert "открытые вопросы без долга в матрице: 1 (OQ-002)" in text, text
    assert "OQ-002: открытая запись без поля «Комплект» называет страницу 900002" in text, text


def test_gate_oq_without_kit_rows_unchanged(tmp_path):
    root = repo(tmp_path, rows="| [КК_БК] | подсервис bc-status |\n", second=False)
    make(root / "open-questions.md", _oq(_entry("001", kit_line=f"- Комплект: {KIT}")))
    text = "\n".join(tg.run_gate(root, no_validator=True)[0])
    assert "журнал вопросов общий" not in text and "поле «Комплект»" not in text, text
    assert "открытые вопросы без долга в матрице: 1 (OQ-001)" in text, text
