# tests/test_selfcheck_titles.py
"""ПР-08 (разбор замечаний ОНБ-В): одинаковые названия разных артефактов
одного типа — ⚠; части одной группы суб-ID, README-реестры и одинаковые
названия разных типов — не дубли."""
from pathlib import Path

from app.scripts.CI import selfcheck


def _card(p: Path, cid: str, typ: str, title: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\n---\n\n# Т\n\nтекст\n",
                 encoding="utf-8")


def _titles(docs: Path):
    out = {}
    for p in docs.rglob("*.md"):
        fm = selfcheck.read_frontmatter(p) or {}
        out[p] = (fm["type"], fm["title"], fm["id"])
    return out


def test_same_title_same_type_flagged(tmp_path):
    docs = tmp_path / "docs"
    _card(docs / "srs/a/data-model/dictionaries.md", "DM-A-001", "data-model", "Справочники и параметры")
    _card(docs / "srs/b/data-model/dictionaries.md", "DM-B-001", "data-model", "справочники  и параметры")
    rep = selfcheck.check_title_uniqueness(docs, _titles(docs))
    assert len(rep) == 1 and rep[0].startswith("data-model: DM-A-001, DM-B-001 — «Справочники и параметры» ×2"), rep


def test_group_parts_readme_and_other_types_not_flagged(tmp_path):
    docs = tmp_path / "docs"
    t = "[КК_ВК] ЭФ Клиента «Заявка»"
    _card(docs / "srs/screen-form/scr-cl-01/scr-cl-01-main.md", "SCR-CL-01", "screen-form", t)
    _card(docs / "srs/screen-form/scr-cl-01/scr-cl-01.1-account.md", "SCR-CL-01.1", "screen-form", t)
    _card(docs / "srs/screen-form/scr-cl-01/scr-cl-01.2-issue.md", "SCR-CL-01.2", "screen-form", t)
    _card(docs / "srs/function/fun-cl-01.md", "FUN-CL-01", "function", t)
    _card(docs / "srs/function/README.md", "FUN-000", "function", "Функции")
    _card(docs / "srs/b/function/README.md", "FUN-B-000", "function", "Функции")
    rep = selfcheck.check_title_uniqueness(docs, _titles(docs))
    assert rep == [], rep


def test_selfcheck_run_prints_warning_without_changing_verdict(tmp_path):
    docs = tmp_path / "docs"
    (docs).mkdir()
    (docs / "traceability-matrix.md").write_text(
        "# М\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
        "| FUN-CL-01 | function | Ф | srs/f1.md |\n| FUN-CL-02 | function | Ф | srs/f2.md |\n",
        encoding="utf-8")
    _card(docs / "srs/f1.md", "FUN-CL-01", "function", "Функция просмотра")
    _card(docs / "srs/f2.md", "FUN-CL-02", "function", "Функция просмотра")
    report, _ok = selfcheck.run(docs, None)
    assert any(ln.startswith("⚠ одинаковые названия разных артефактов одного типа") for ln in report), report
    assert any("function: FUN-CL-01, FUN-CL-02 — «Функция просмотра» ×2" in ln for ln in report), report


def test_yo_e_normalized(tmp_path):
    docs = tmp_path / "docs"
    _card(docs / "srs/a.md", "FUN-CL-01", "function", "Функция просмотра счёта")
    _card(docs / "srs/b.md", "FUN-CL-02", "function", "Функция просмотра счета")
    rep = selfcheck.check_title_uniqueness(docs, _titles(docs))
    assert len(rep) == 1 and "FUN-CL-01, FUN-CL-02" in rep[0], rep

