# tests/test_source_coverage.py
"""Гейт покрытия выгрузки: страницы источника ↔ confluence_page_ids
артефактов; целостность иерархии fileN.md ↔ fileN/."""

from pathlib import Path

from app.scripts.CI.source_coverage import collect, source_title


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fm_source(pid: str) -> str:
    return f"---\nconfluence_page_id: '{pid}'\n---\n# стр\n"


def fm_artifact(ids: str) -> str:
    return f"---\nid: X-001\nconfluence_page_ids: [{ids}]\n---\n# док\n"


def test_coverage_and_child_diagnostics(tmp_path):
    src = tmp_path / "src"; out = tmp_path / "out"
    make(src / "метод.md", fm_source("100"))
    make(src / "метод" / "логика.md", fm_source("101"))   # дочерняя
    make(src / "другая.md", fm_source("200"))
    make(out / "docs" / "intc-001.md", fm_artifact("'100'"))
    pages, parents, covered, no_id, orphans = collect(src, out)
    assert set(pages) == {"100", "101", "200"}
    assert parents["101"] == "100" and parents["100"] is None
    assert "100" in covered and "101" not in covered and "200" not in covered
    assert not no_id and not orphans


def test_orphan_dir_and_no_id(tmp_path):
    src = tmp_path / "src"; out = tmp_path / "out"; out.mkdir()
    make(src / "обрезанный" / "лог.md", fm_source("300"))  # каталога-пары нет
    make(src / "безid.md", "# страница без frontmatter\n")
    pages, parents, covered, no_id, orphans = collect(src, out)
    assert parents["300"] is None                    # родитель не найден
    assert len(no_id) == 1 and len(orphans) == 1


def test_source_title(tmp_path):
    # человеческое наименование для отчёта: кавычки снимаются; без title — None
    p = tmp_path / "s.md"
    make(p, "---\ntitle: '[Файловый сервис] Функции'\nconfluence_page_id: '7'\n---\n")
    assert source_title(p) == "[Файловый сервис] Функции"
    q = tmp_path / "t.md"
    make(q, "---\nconfluence_page_id: '8'\n---\n")
    assert source_title(q) is None
    r = tmp_path / "u.md"
    make(r, "---\ntitle: '[БлокН2Н] Банк: Функция повторного запуска обработки сообщения о блокировках\n"
            "  Н2Н'\nconfluence_page_id: '9'\n---\n")
    assert source_title(r).endswith("блокировках Н2Н")


def test_report_uncovered_without_page_id(tmp_path):
    # К-17: блок непокрытых — «title — файл выгрузки», БЕЗ page_id
    # (язык прибора диктует язык документа: прежний формат копировался
    # исполнителями в open-questions как есть)
    from app.scripts.CI.source_coverage import coverage_report
    src = tmp_path / "src"; out = tmp_path / "out"; out.mkdir()
    make(src / "стр.md",
         "---\ntitle: '[X] Функция импорта'\n"
         "confluence_page_id: '2169849965'\n---\n# с\n")
    lines, n = coverage_report(src, out)
    assert n == 1
    joined = "\n".join(lines)
    assert "[X] Функция импорта — стр.md" in joined
    assert "2169849965" not in joined


def test_full_coverage_ok(tmp_path):
    # тест на НЕсрабатывание: всё покрыто — пусто во всех списках
    src = tmp_path / "src"; out = tmp_path / "out"
    make(src / "a.md", fm_source("1"))
    make(src / "a" / "b.md", fm_source("2"))
    make(out / "x.md", fm_artifact("'1', '2'"))
    pages, _parents, covered, no_id, orphans = collect(src, out)
    assert set(pages) <= set(covered) and not no_id and not orphans
