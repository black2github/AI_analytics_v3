# tests/test_kit_inventory_locator.py
"""Опись выгрузки (inventory.md) для доводов прибора по описи — один локатор
(kitcheck.fs.find_kit_file: в корне комплекта, затем рядом с ним) и явный параметр
inventory прогона. Гейт переноса гоняет selfcheck на временной копии docs/, где описи нет:
он передаёт опись источника, иначе доводы (копия страницы метода, страница вне
подсервиса) не срабатывали и гейт давал ложные ✗ против прямого прогона (КК r07, 02.11)."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402

from app.scripts.CI import selfcheck  # noqa: E402
from app.scripts.CI.kitcheck.checks.card_run import run_check  # noqa: E402
from app.scripts.CI.kitcheck.fs import find_kit_file  # noqa: E402

_INV = ("| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 333444 | Копия [КК] ЕСК_ОА_Проверка полномочий | [КК]-ЕСК | integration | 10 | "
        "srs/bc-issue/contract-call/external | x |\n")
_CALL_REL = "srs/bc-issue/contract-call/external/call-ext-011.md"
_CALL = ("---\nid: CALL-EXT-011\ntitle: '[КК_ВК] ЭФ Подтверждение'\ntype: contract-call\n"
         "confluence_page_ids: ['111222', '333444']\n---\n\n# CALL-EXT-011. Вызов\n\nПривязка данных.\n")
_BY_LINK = "по ссылке (метод / общая функция вне подсервиса): 333444"
_NO_HEADING = "нет заголовков разделов по страницам: 333444"
_CARD_LINE = "call-ext-011.md ← main.md"


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _src(title: str, pid: str) -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\nтекст\n"


def _sources(root: Path) -> Path:
    conf = root / "sources" / "confluence"
    _w(conf / "main.md", _src("[КК_ВК] ЭФ Подтверждение", "111222"))
    _w(conf / "extra.md", _src("Копия [КК] ЕСК_ОА_Проверка полномочий", "333444"))
    return conf


def make_kit(tmp_path: Path, inventory: bool = True) -> Path:
    """Рабочий репозиторий `<root>/docs` + выгрузка + опись рядом с docs/ (раскладка КК)."""
    root = tmp_path / "src-x"
    docs = root / "docs"
    _w(docs / "README.md", "# К\n")
    _w(docs / "traceability-matrix.md",
       "# Матрица\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
       f"| CALL-EXT-011 | contract-call | Вызов | {_CALL_REL} |\n")
    _w(docs / _CALL_REL, _CALL)
    _sources(root)
    if inventory:
        _w(root / "inventory.md", _INV)
    return root


def _card_mark(lines) -> str:
    """Знак строки карточки вызова в отчёте selfcheck или гейта (✓ / ✗); у ✓ строки i с
    доводом не печатаются — сравнивается вердикт карточки."""
    hit = [ln for ln in lines if _CARD_LINE in ln]
    assert len(hit) == 1, "\n".join(lines)
    return hit[0].strip()[0]


# ---------------------------------------------------------------- локатор

def test_find_kit_file_root_then_parent(tmp_path):
    docs = tmp_path / "repo" / "docs"
    docs.mkdir(parents=True)
    assert find_kit_file(docs, "inventory.md") is None
    _w(tmp_path / "repo" / "inventory.md", "x")
    assert find_kit_file(docs, "inventory.md") == tmp_path / "repo" / "inventory.md"
    _w(docs / "inventory.md", "y")  # в корне комплекта — первым
    assert find_kit_file(docs, "inventory.md") == docs / "inventory.md"


def test_source_coverage_uses_same_locator():
    # один дом адреса: имя в source_coverage — тот же локатор kitcheck.fs (модуль грузится
    # двумя путями импорта, поэтому сравнение по происхождению функции, а не по объекту)
    from app.scripts.CI import source_coverage
    f = source_coverage.find_kit_file
    assert f.__module__.endswith("kitcheck.fs")
    assert f.__code__.co_filename == find_kit_file.__code__.co_filename


# ---------------------------------------------------------------- гейт = прямой прогон

def test_gate_selfcheck_matches_direct_run(tmp_path):
    root = make_kit(tmp_path)
    direct, _ = selfcheck.run(root / "docs", root / "sources" / "confluence")
    assert _card_mark(direct) == "✓", "\n".join(direct)
    lines, _ready, _data = tg.run_gate(root, no_validator=True)
    # ✓ карточек гейт не печатает: строки карточки нет, сводка прибора — без брака
    # (до правки: «✗ [ПРИБОР] …call-ext-011.md ← main.md», ✗ 1)
    assert not any(_CARD_LINE in ln for ln in lines), "\n".join(lines)
    assert any(ln.startswith("✓ [ПРИБОР] файлов 3 — ✓ 1, ✗ 0") for ln in lines), "\n".join(lines)


def test_gate_without_inventory_keeps_defect(tmp_path):
    # НЕсрабатывание: описи нет нигде — доводы не срабатывают, ✗ остаётся (как прежде)
    root = make_kit(tmp_path, inventory=False)
    direct, _ = selfcheck.run(root / "docs", root / "sources" / "confluence")
    assert _card_mark(direct) == "✗" and _NO_HEADING in "\n".join(direct), "\n".join(direct)
    lines, _ready, _data = tg.run_gate(root, no_validator=True)
    assert _card_mark(lines) == "✗", "\n".join(lines)


def test_staged_copy_with_explicit_inventory(tmp_path):
    # копия docs/ без описи рядом (как у гейта): без параметра — ✗, с параметром — ✓
    root = make_kit(tmp_path)
    staged = tmp_path / "staged"
    shutil.copytree(root / "docs", staged)
    sources = root / "sources" / "confluence"
    bare, _ = selfcheck.run(staged, sources)
    assert _card_mark(bare) == "✗" and _NO_HEADING in "\n".join(bare), "\n".join(bare)
    rep, _ = selfcheck.run(staged, sources, inventory=root / "inventory.md")
    text = "\n".join(rep)
    assert _card_mark(rep) == "✓" and _NO_HEADING not in text, text
    assert f"i опись выгрузки (--inventory): {root / 'inventory.md'}" in text, text


# ---------------------------------------------------------------- раскладки и НЕсрабатывание

def test_docs_repo_layout_inventory_in_root(tmp_path):
    # репозиторий документации: комплект и опись в одном корне (прежний адрес — родитель корня)
    repo = tmp_path / "docs-x"
    _w(repo / _CALL_REL, _CALL)
    _w(repo / "inventory.md", _INV)
    conf = _sources(tmp_path / "work")
    rep, _ = run_check([repo / _CALL_REL], conf / "main.md", docs_root=repo,
                       amnesty_sources=[conf / "extra.md"])
    text = "\n".join(rep)
    assert _BY_LINK in text and _NO_HEADING not in text, text


def test_no_inventory_anywhere_unchanged(tmp_path):
    repo = tmp_path / "docs-x"
    _w(repo / _CALL_REL, _CALL)
    conf = _sources(tmp_path / "work")
    rep, _ = run_check([repo / _CALL_REL], conf / "main.md", docs_root=repo,
                       amnesty_sources=[conf / "extra.md"])
    assert _NO_HEADING in "\n".join(rep), "\n".join(rep)


def test_explicit_missing_inventory_is_defect_not_fallback(tmp_path):
    # явный путь, которого нет: ✗ с причиной, без краша и без тихого отката к описи рядом с docs
    root = make_kit(tmp_path)
    missing = tmp_path / "nope" / "inventory.md"
    rep, ok = selfcheck.run(root / "docs", root / "sources" / "confluence", inventory=missing)
    text = "\n".join(rep)
    assert not ok
    assert f"✗ опись выгрузки (--inventory) не найдена: {missing}" in text, text
    assert _NO_HEADING in text, text
    assert "КРАШ" not in text, text
