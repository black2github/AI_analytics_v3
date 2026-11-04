# tests/test_card_source_zone.py
"""Карточки зоны docs/modules/ в card_source (normalize_tables --check, 2026-11-04): источник
сверки — первая страница, правило агрегатора к карточке зоны не применяется; таблица раздела
«Происхождение» (`Источник | Путь в репозитории | Срез / дата выгрузки`) — вне сторожа отсылок к
страницам источника. Вне этой таблицы и у карточек комплекта — как прежде (тесты НЕсрабатывания)."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.card_run import check_file, run_check
from app.scripts.CI.kitcheck.checks.card_source import _strip_origin_table, check_title
from app.scripts.CI.kitcheck.md import is_module_zone_file


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def card(title: str, typ: str = "module-interface", pids: str = "2000000222, 2000000901",
         body: str = "текст\n") -> str:
    return (f"---\nid: MOD-WIDGETS-RTL-001\ntitle: '{title}'\ntype: {typ}\n"
            f"confluence_page_ids: [{pids}]\n---\n\n# MOD-WIDGETS-RTL-001. Скрипт\n\n{body}")


SRC = ("---\ntitle: '[КК_Виджет_ПИН] Клиент: Скрипт'\nconfluence_page_id: '2000000222'\n---\n\n"
       "текст\n")
ORIGIN = ("## Происхождение\n\n| Источник | Путь в репозитории | Срез / дата выгрузки |\n"
          "|---|---|---|\n| Выгрузка Confluence сервиса | `sources/confluence/x/m.md` | "
          "prod-2026-09, дата выгрузки 2026-09-08 |\n| Спецификация Розницы «УС ПИН» | "
          "`sources/external/us/` | 2026-10-21 |\n")
ZONE = "docs/modules/widgets-rtl/interface/mod-001.md"
KIT = "docs/srs/function/fun-01.md"


def lines_with(rep, s):
    return [ln for ln in rep if s in ln]


# ---------------------------------------------------------------- признак зоны

def test_is_module_zone_file_by_path_and_docs(tmp_path):
    z = tmp_path / ZONE
    assert is_module_zone_file(z) and is_module_zone_file(z, tmp_path / "docs")
    assert not is_module_zone_file(tmp_path / KIT)
    assert not is_module_zone_file(tmp_path / KIT, tmp_path / "docs")
    # файл прямо в docs/modules/ — не мини-комплект; корень docs/ задан, файл вне его — не зона
    assert not is_module_zone_file(tmp_path / "docs/modules/x.md")
    assert not is_module_zone_file(z, tmp_path / "other")


# ---------------------------------------------------------------- title: агрегатор

def test_zone_two_pages_no_aggregator_title_ok(tmp_path):
    src = make(tmp_path / "src.md", SRC)
    f = make(tmp_path / ZONE, card("[КК_Виджет_ПИН] Клиент: Скрипт"))
    rep, _ok = run_check([f], src)
    assert not lines_with(rep, "карточка-агрегатор"), rep
    assert "title: дословно перенесён ('[КК_Виджет_ПИН] Клиент: Скрипт') ✓" in rep
    assert ("i title доп. страниц (1) не сверяется у карточки зоны docs/modules/ — спецификации "
            "чужого контура, источник сверки — первая страница") in rep


def test_zone_interface_without_module_marker_flagged(tmp_path):
    # маркер модуля не снимается (решение владельца канона 2026-11-04): прежний ✗ «расходится»
    src = make(tmp_path / "src.md", SRC)
    f = make(tmp_path / ZONE, card("Клиент: Скрипт"))
    rep, ok = run_check([f], src)
    assert not ok and ("title: расходится с источником ✗ (карточка 'Клиент: Скрипт', "
                       "источник '[КК_Виджет_ПИН] Клиент: Скрипт' — перенос дословный)") in rep, rep
    assert not lines_with(rep, "карточка-агрегатор")


def test_zone_title_mismatch_still_flagged(tmp_path):
    # снят не только маркер — расхождение, как прежде (✗ утилиты; в selfcheck — ⚠ зоны)
    src = make(tmp_path / "src.md", SRC)
    f = make(tmp_path / ZONE, card("Клиент: Другой скрипт"))
    rep, ok = run_check([f], src)
    assert not ok and lines_with(rep, "title: расходится с источником ✗"), rep
    assert not lines_with(rep, "карточка-агрегатор")


def test_zone_readme_marker_not_stripped():
    # README мини-комплекта (module-kit) — дословно с тегом
    readme = card("Клиент: Скрипт", typ="module-kit")
    rep, ok = check_title(readme, SRC, zone=True)
    assert not ok and rep[0].startswith("title: расходится с источником ✗"), rep


def test_kit_card_two_pages_aggregator_as_before(tmp_path):
    src = make(tmp_path / "src.md", SRC)
    f = make(tmp_path / KIT, card("Сводная", typ="function"))
    rep, ok = run_check([f], src)
    assert not ok
    assert ("title: карточка-агрегатор 2 страниц — нет заголовков по страницам: "
            "'[КК_Виджет_ПИН] Клиент: Скрипт' ✗ ПОТЕРЯ НАИМЕНОВАНИЯ") in rep


def test_check_title_default_not_zone_unchanged():
    # без zone — прежний путь: агрегатор
    rep, ok = check_title(card("Клиент: Скрипт"), SRC)
    assert not ok and rep[0].startswith("title: карточка-агрегатор 2 страниц"), rep


# ---------------------------------------------------------------- отсылки: «Происхождение»

def test_zone_origin_table_not_page_ref(tmp_path):
    f = make(tmp_path / ZONE, card("Клиент: Скрипт", body="текст\n\n" + ORIGIN))
    rep, _ok = check_file(f, zone=True)
    assert not lines_with(rep, "отсылки к страницам источника"), rep
    # через run_check признак зоны берётся из пути
    rep2, _ok2 = run_check([f], None)
    assert not lines_with(rep2, "отсылки к страницам источника"), rep2


def test_zone_confluence_outside_origin_table_flagged(tmp_path):
    body = "Подробнее — в Confluence.\n\n" + ORIGIN
    f = make(tmp_path / ZONE, card("Клиент: Скрипт", body=body))
    rep, ok = run_check([f], None)
    hit = lines_with(rep, "отсылки к страницам источника в теле карточки ×1 (Confluence)")
    assert not ok and hit, rep


def test_zone_origin_section_prose_still_flagged(tmp_path):
    # абзац в разделе «Происхождение» вне таблицы — не исключение
    body = ORIGIN + "\nСм. страницу Confluence.\n"
    f = make(tmp_path / ZONE, card("Клиент: Скрипт", body=body))
    rep, ok = run_check([f], None)
    assert not ok and lines_with(rep, "отсылки к страницам источника в теле карточки ×1"), rep


def test_kit_card_origin_table_flagged_as_before(tmp_path):
    f = make(tmp_path / KIT, card("Клиент: Скрипт", typ="function", body="текст\n\n" + ORIGIN))
    rep, ok = run_check([f], None)
    assert not ok and lines_with(rep, "отсылки к страницам источника в теле карточки ×2"), rep
    rep2, _ = check_file(f)
    assert lines_with(rep2, "отсылки к страницам источника в теле карточки ×2"), rep2


def test_strip_origin_table_scope():
    other = ("## Происхождение\n\n| Источник | Ссылка |\n|---|---|\n| Confluence | x |\n")
    assert "Confluence" in _strip_origin_table(other)  # другая шапка — не исключение
    numbered = ORIGIN.replace("## Происхождение", "## 9. Происхождение")
    assert "Confluence" not in _strip_origin_table(numbered)
    # та же таблица в другом разделе — не исключение
    moved = ORIGIN.replace("## Происхождение", "## Описание")
    assert "Confluence" in _strip_origin_table(moved)
    # после таблицы и следующего раздела текст сохраняется
    tail = ORIGIN + "\n## Дальше\n\nConfluence\n"
    assert _strip_origin_table(tail).count("Confluence") == 1
