# tests/test_frontmatter_boundary.py
"""Граница шапки (frontmatter) — одна для всех мест прибора (решение
владельца 2026-10-17): правило `read_frontmatter` — BOM снимается, шапка
закрывается строкой «---», «---» внутри значения и сепаратор таблицы — не
граница, ключи шапки (`entity`, `title`, `type`) ищутся только в шапке.
Плюс: строка «>» внутри блока кода — не цитата; заголовок диффа в
delta_report опознаётся по позиции, а не по префиксу строки."""

import subprocess
import sys
from pathlib import Path

from app.scripts.CI.kitcheck import md
from app.scripts.CI.kitcheck.checks import content
from app.scripts.CI import normalize_tables as nt
from app.scripts.CI.selfcheck import _empty_source_note, check_nfr_catalog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import delta_report as dr  # noqa: E402

BOM = "﻿"
FM = "---\nid: F-01\ntitle: '{t}'\nconfluence_page_ids: [2169849859]\ntype: function\n---\n"


def _make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --- граница ----------------------------------------------------------------

def test_split_bom_dash_in_value_and_no_frontmatter():
    head, body = md.frontmatter_split(BOM + "---\ntitle: 'A --- B'\n---\n\n# Т\n")
    assert head == "title: 'A --- B'\n" and body == "\n# Т\n"
    # без шапки сепаратор таблицы — не граница, текст целиком
    text = "Текст\n\n| a | b |\n| --- | --- |\n| x | y |\n"
    assert md.frontmatter_split(text) == (None, text)
    # незакрытая шапка — ничего не отрезается
    assert md.frontmatter_split("---\ntitle: x\n\n# Т\n") == (None, "---\ntitle: x\n\n# Т\n")
    assert md.frontmatter_end(["---", "a: 1", "---", "тело"]) == 3
    assert md.frontmatter_end(["тело", "---"]) == 0


# --- карточка ---------------------------------------------------------------

def test_dash_in_title_not_body_reference(tmp_path):
    # Ф8: «---» в title не выталкивает confluence_page_ids из шапки в тело
    p = _make(tmp_path / "f.md", FM.format(t="Заявка --- счёт") + "\n# Ф\n\nтекст\n")
    rep, ok = nt.check_file(p)
    assert not any("отсылки к страницам источника" in ln for ln in rep), rep


def test_body_reference_still_caught(tmp_path):
    # НЕсрабатывание: отсылка в теле по-прежнему брак
    p = _make(tmp_path / "f.md", FM.format(t="Заявка — счёт")
              + "\n# Ф\n\nсм. confluence page 2169849859\n")
    rep, ok = nt.check_file(p)
    assert not ok and any("отсылки к страницам источника" in ln for ln in rep), rep


def test_source_silent_same_with_and_without_bom(tmp_path):
    # Ф1: пометка в title шапки не считается ни с BOM, ни без
    docs = tmp_path / "docs"
    _make(docs / "a.md", BOM + "---\ntitle: 'Лимит в срезе'\n---\n\n# А\n\nтекст\n")
    _make(docs / "b.md", "---\ntitle: 'Лимит в срезе'\n---\n\n# Б\n\nтекст\n")
    assert content.check_source_silent(docs) == []


def test_source_silent_unclosed_frontmatter_not_hidden(tmp_path):
    # Ф1: незакрытая шапка прежде прятала весь файл
    docs = tmp_path / "docs"
    _make(docs / "a.md", "---\ntitle: 'А'\n\n# А\n\nЛимит TBD\n")
    out = content.check_source_silent(docs)
    assert any("a.md:6" in ln for ln in out), out


def test_notation_ignores_bom_frontmatter():
    # Ф2: стрелка в title шапки с BOM — не нотация тела
    assert nt.check_notation_hints(BOM + "---\ntitle: 'Заявка ← счёт'\n---\n\n# Т\n") == []
    assert nt.check_notation_hints("---\ntitle: 'А'\n---\n\n# Т\n\nЗаявка ← счёт\n")


def test_entity_and_type_only_from_frontmatter():
    # Ф7: entity в тексте — не значение шапки; длинная шапка — не помеха
    assert nt._frontmatter_entity("---\ntype: controls\n---\n\n# К\n\nentity: ENT-999\n") == ""
    long_fm = "---\ntitle: '" + "Д" * 900 + "'\nentity: ENT-001\ntype: screen-form\n---\n\n# К\n"
    assert nt._frontmatter_entity(long_fm) == "ENT-001"
    assert "type: screen-form" in nt._fm_head(long_fm)


def test_quote_in_code_block_not_blockquote(tmp_path):
    # Д4: «>» внутри блока кода — текст примера
    p = _make(tmp_path / "c.md", "# К\n\n```bash\n> ответ сервера\n```\n")
    rep, ok = nt.check_file(p)
    assert not any("blockquote" in ln for ln in rep), rep
    # НЕсрабатывание: цитата вне блока — по-прежнему брак
    p2 = _make(tmp_path / "d.md", "# К\n\n> заметка\n")
    rep2, ok2 = nt.check_file(p2)
    assert not ok2 and any("blockquote" in ln for ln in rep2), rep2


# --- источник ---------------------------------------------------------------

def test_source_without_frontmatter_not_cut_at_table_separator():
    # Ф16–Ф20: прежнее split("---", 2) резало по сепаратору таблицы
    src = "Текст «Первый литерал»\n\n| a | b |\n| --- | --- |\n| x | «Второй литерал» |\n"
    lits = nt.quoted_literals(src)
    assert any("Первый литерал" in x for x in lits), lits


def test_empty_source_with_dash_in_title_detected(tmp_path):
    # Ф9: «---» в title не делает пустую замороженную страницу «непустой»
    p = _make(tmp_path / "s.md", BOM + "---\ntitle: 'A --- B'\nunapproved_jira: ECO-1\n---\n\n")
    note, frozen = _empty_source_note(p)
    assert note and frozen, note


def test_nfr_page_with_bom_ok(tmp_path):
    # Ф11: шапка с BOM прежде оставалась в теле — confluence_page_ids → ✗
    # каталог НФТ по норме канона 49a2c85 (22.10): README-реестр и все 18 страниц типов
    from app.scripts.CI.kitcheck.checks.nfr import _NFR_TYPE_BY_CODE
    page = (BOM + "---\nid: nfr-prf\ntype: nfr\nnfr_type: Производительность\n"
            "ingress: reverse\nconfluence_page_ids: 123\n---\n# Производительность\n\n"
            "| ID | Показатель | Норма |\n|---|---|---|\n"
            "| nfr-prf-001 | Время отклика | ≤ 2 с |\n")
    docs = tmp_path / "output/svc/docs"
    _make(docs / "README.md", "# К\n")
    _make(docs / "traceability-matrix.md",
          "# Матрица\n\n## BRD-6.2. НФТ\n\n| ID | Показатель |\n|---|---|\n"
          "| nfr-prf-001 | Время отклика |\n")
    nfr = tmp_path / "output/svc/nfr"
    _make(nfr / "README.md", "---\nid: nfr\ntype: nfr\n---\n# Реестр НФТ\n")
    for code, name in _NFR_TYPE_BY_CODE.items():
        if code != "prf":
            _make(nfr / f"nfr-{code}.md", f"---\nid: nfr-{code}\ntype: nfr\nnfr_type: {name}\n"
                  f"ingress: reverse\nconfluence_page_ids: 123\n---\n# {name}\n")
    _make(nfr / "nfr-prf.md", page)
    report, ok = check_nfr_catalog(docs)
    assert ok, report


# --- delta_report -----------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=str(repo), check=True, capture_output=True)


def test_diff_lines_starting_with_dashes_kept(tmp_path):
    # Ф14: снятая «-- …» и добавленная «++ …» строки не выпадают
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    f = repo / "a.md"
    f.write_text("x\n-- снятая\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-q", "-m", "base")
    f.write_text("x\n++ добавленная\n", encoding="utf-8", newline="\n")
    added, removed = dr.added_removed_lines(repo, "HEAD", {"path": "a.md", "status": "M", "old": None})
    assert "-- снятая" in removed and "++ добавленная" in added, (added, removed)
    assert not any(ln.startswith(("-- a/", "++ b/")) for ln in added + removed)


def test_id_from_text_bom_and_dash():
    assert dr._id_from_text(BOM + "---\ntitle: 'A --- B'\nid: F-01\n---\n\n# Т\n") == "F-01"
    assert dr._id_from_text("# без шапки\n\nid: X-1\n") == ""
