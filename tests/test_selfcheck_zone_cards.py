# tests/test_selfcheck_zone_cards.py
"""Карточки зоны docs/modules/ в selfcheck (2026-11-04): сверка с выгрузкой по первой странице.
Шаблоны module-interface.md и module-kit-readme.md обещают «сверка по первой странице, остальные —
вне выгрузки, без сверки (строка i)»; до правки ветка зоны selfcheck молчала. Только ⚠ и i: вердикт
и счётчики ИТОГО не меняются. Карточки комплекта (не зоны) — как прежде, символ в символ."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks.zone import check_module_zone, check_zone_card


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid: str, title: str, typ: str = "function", pids: str = "", body: str = "текст\n") -> str:
    pid_line = f"confluence_page_ids: [{pids}]\n" if pids else ""
    return f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\n{pid_line}---\n\n# {title}\n\n{body}"


def page(pid: str, title: str, body: str = "текст\n") -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n{body}"


MATRIX = ("# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
          "| FUN-01 | function | А | srs/function/a.md |\n")
IFACE = "modules/widgets-rtl/interface/mod-001.md"


def kit(tmp_path: Path, zone: bool = True, iface_title: str = "[КК_Виджет_ПИН] Клиент: Скрипт",
        iface_pids: str = "2000000222, 2000000901", readme_title: str = "[КК] Паспорт",
        spec: bool = True) -> Path:
    """Комплект с одной карточкой и (по умолчанию) зоной: README (паспорт …333 + чужая …902),
    интерфейс (страница метода …222 + чужая …901), spec/ (страница …444). Выгрузка — …111,
    …222, …333, …444; …901/…902 — вне выгрузки (sources/external)."""
    root = tmp_path / "kit"
    docs = root / "docs"
    src = root / "sources/confluence"
    make(docs / "srs/function/a.md", card("FUN-01", "А", pids="2000000111"))
    make(docs / "traceability-matrix.md", MATRIX)
    make(src / "a.md", page("2000000111", "А"))
    make(src / "m.md", page("2000000222", "[КК_Виджет_ПИН] Клиент: Скрипт"))
    make(src / "p.md", page("2000000333", "[КК] Паспорт"))
    make(src / "s.md", page("2000000444", "[КК_Виджет_ПИН] ЭФ"))
    if zone:
        z = docs / "modules/widgets-rtl"
        make(z / "README.md", card("MOD-WIDGETS-RTL-000", readme_title, "module-kit",
                                   pids="2000000333, 2000000902"))
        make(docs / IFACE, card("MOD-WIDGETS-RTL-001", iface_title, "module-interface",
                                pids=iface_pids))
        if spec:
            make(z / "spec/scr-01.md", card("MOD-WIDGETS-RTL-SCR-01", "ЭФ", "screen-form",
                                            pids="2000000444, 2000000903"))
    return docs


def run(docs: Path, with_sources: bool = True):
    return sc.run(docs, docs.parent / "sources/confluence" if with_sources else None)


def total(report):
    return next(ln for ln in report if ln.startswith("ИТОГО"))


def zone_lines(report):
    return [ln for ln in report if "modules" in ln and ("доп. страницы-источники" in ln
                                                        or "первой страницы" in ln)]


def rel(s: str) -> str:
    return str(Path(s))


# ---------------------------------------------------------------- срабатывание: строка i

def test_zone_card_title_match_gives_one_i_line_per_file(tmp_path):
    report, ok = run(kit(tmp_path))
    base, base_ok = run(kit(tmp_path / "b", zone=False))
    # вердикт и ИТОГО — как у комплекта без зоны (зона вне переписи и счётчиков)
    assert ok == base_ok and total(report) == total(base), (total(report), total(base))
    assert not any(ln.startswith("✗") and "modules" in ln for ln in report), report
    assert not any(ln.startswith("⚠") and "modules" in ln for ln in report), report
    assert (f"i {rel(IFACE)}: доп. страницы-источники (1) — спецификации чужого контура; "
            "вне выгрузки, без сверки: 2000000901") in report
    assert (f"i {rel('modules/widgets-rtl/README.md')}: доп. страницы-источники (1) — "
            "спецификации чужого контура; вне выгрузки, без сверки: 2000000902") in report
    assert ("i карточки зоны — сверка с выгрузкой по первой странице: файлов 2, ⚠ 0, i 2 "
            "(только ⚠ и i, вердикт не меняют)") in report
    # spec/ — вне сверки (постановка: «кроме spec/»)
    assert not any("scr-01.md" in ln for ln in zone_lines(report)), report


def test_zone_extra_page_in_export_listed_separately(tmp_path):
    # доп. страница, оказавшаяся в выгрузке, — тоже без сверки, но названа отдельно (без потери)
    report, _ok = run(kit(tmp_path, iface_pids="2000000222, 2000000901, 2000000111"))
    assert (f"i {rel(IFACE)}: доп. страницы-источники (2) — спецификации чужого контура; "
            "вне выгрузки, без сверки: 2000000901; в выгрузке, без сверки: 2000000111") in report


def test_zone_card_single_page_no_i_line(tmp_path):
    report, _ok = run(kit(tmp_path, iface_pids="2000000222"))
    assert not any(rel(IFACE) in ln for ln in zone_lines(report)), report


# ---------------------------------------------------------------- срабатывание: ⚠

def test_zone_title_mismatch_warns_verdict_unchanged(tmp_path):
    good, good_ok = run(kit(tmp_path / "g"))
    report, ok = run(kit(tmp_path, iface_title="Клиент: Другой скрипт"))
    assert ok == good_ok and total(report) == total(good)
    w = [ln for ln in report if ln.startswith("⚠") and rel(IFACE) in ln]
    assert len(w) == 1 and "title расходится с наименованием первой страницы-источника m.md" in w[0]
    assert "'Клиент: Другой скрипт'" in w[0] and "'[КК_Виджет_ПИН] Клиент: Скрипт'" in w[0]
    assert ("i карточки зоны — сверка с выгрузкой по первой странице: файлов 2, ⚠ 1, i 2 "
            "(только ⚠ и i, вердикт не меняют)") in report


def test_zone_interface_title_without_marker_warns(tmp_path):
    # title дословно с title первой страницы: маркер модуля не снимается (решение владельца
    # канона 2026-11-04) — без маркера при странице с маркером ⚠, вердикт и ИТОГО прежние
    good, good_ok = run(kit(tmp_path / "g"))
    report, ok = run(kit(tmp_path, iface_title="Клиент: Скрипт"))
    assert ok == good_ok and total(report) == total(good)
    w = [ln for ln in report if ln.startswith("⚠") and rel(IFACE) in ln]
    assert len(w) == 1 and "title расходится" in w[0] and "'Клиент: Скрипт'" in w[0], report
    assert not any(ln.startswith("⚠") and rel(IFACE) in ln for ln in good), good


def test_zone_readme_keeps_leading_tag(tmp_path):
    # README мини-комплекта — дословно с ведущим тегом
    report, _ok = run(kit(tmp_path, readme_title="Паспорт"))
    assert any(ln.startswith("⚠") and "README.md" in ln and "title расходится" in ln
               for ln in report), report


def test_zone_first_page_not_in_export_warns(tmp_path):
    report, ok = run(kit(tmp_path, iface_pids="2000000999, 2000000901"))
    _good, good_ok = run(kit(tmp_path / "g"))
    assert ok == good_ok
    assert (f"⚠ {rel(IFACE)}: источник первой страницы не найден в выгрузке (page_id 2000000999) — "
            "title не сверен; зона вне переносимого состояния, вердикт не меняется") in report
    assert not any(ln.startswith("✗") and "2000000999" in ln for ln in report), report


# ---------------------------------------------------------------- НЕсрабатывание

def test_zone_without_sources_silent_as_before(tmp_path):
    report, _ok = run(kit(tmp_path), with_sources=False)
    assert not zone_lines(report) and not any("карточки зоны" in ln for ln in report), report


def test_kit_without_zone_no_zone_card_lines(tmp_path):
    report, _ok = run(kit(tmp_path, zone=False))
    assert not any("карточки зоны" in ln or "мини-комплект" in ln for ln in report), report
    assert check_module_zone(kit(tmp_path / "b", zone=False)) == []


def test_kit_card_two_pids_unchanged(tmp_path):
    # карточка комплекта с двумя page_id — прежняя строка i и прежний ✗ агрегатора (title
    # агрегатора свой, наименования страницы «А» заголовком раздела нет)
    docs = kit(tmp_path, zone=False)
    make(docs / "srs/function/a.md", card("FUN-01", "Сводная", pids="2000000111, 2000000901"))
    report, ok = run(docs)
    assert (f"i {rel('srs/function/a.md')}: доп. страницы-источники (1): таблицы и кавычечные литералы "
            "сверяются по каждой, прочие сторожа — по главной (первой в списке); вне выгрузки, "
            "без сверки: 2000000901") in report
    assert not ok
    assert any("title: карточка-агрегатор 2 страниц — нет заголовков по страницам: 'А' "
               "✗ ПОТЕРЯ НАИМЕНОВАНИЯ" in ln for ln in report), report
    assert not any("спецификации чужого контура" in ln for ln in report)


def test_check_zone_card_unit(tmp_path):
    docs = kit(tmp_path)
    idx, _ = sc.index_sources(docs.parent / "sources/confluence")
    p = docs / IFACE
    assert check_zone_card(p, "x.md", ["2000000222"], idx) == []
    assert check_zone_card(p, "x.md", ["2000000222", "2000000901"], idx) == [
        "i x.md: доп. страницы-источники (1) — спецификации чужого контура; "
        "вне выгрузки, без сверки: 2000000901"]
