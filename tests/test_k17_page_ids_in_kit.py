# tests/test_k17_page_ids_in_kit.py
"""К-17 на все файлы комплекта (2026-11-09, постановка «Точки расширения эталона», слово
владельца): идентификатор страницы Confluence живёт только во frontmatter карточки и в матрице
«Источники миграции». ✗ — page_id из множества страниц комплекта (шапки, матрица, выгрузка при
--sources) или адрес страницы Confluence в теле любого файла комплекта; прочие числа из 9–10
цифр — i-строкой (ИНН, суммы, номера из примеров). Вне сверки: шапка, блоки кода, матрица,
open-questions (прежнее правило), sources/, sandbox/, каталог --sources."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks.card_clean import check_page_ids_in_kit

PID = "2166860243"


def w(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def card(docs: Path, rel: str, cid: str, body: str = "Текст.\n", pids: str = PID) -> Path:
    return w(docs / rel, f"---\nid: {cid}\ntype: screen-form\nservice: x\ntitle: Т\n"
                         f"confluence_page_ids: ['{pids}']\n---\n\n# {cid} Т\n\n{body}")


def test_page_id_in_card_body_blocks(tmp_path):
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01", f"Страница {PID} перенесена.\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert not ok
    assert rep[0].startswith("✗ К-17: идентификатор страницы Confluence вне frontmatter — строк 1 в файлах 1; "
                             "дом — `confluence_page_ids` карточки и матрица «Источники миграции»"), rep
    assert (f"srs/screen-form/scr-cl-01.md: строка 11 — идентификатор страницы Confluence вне frontmatter: "
            f"`{PID}` (страница комплекта: frontmatter SCR-CL-01)") in rep[1], rep


def test_page_id_in_readme_registry_inline_code_blocks(tmp_path):
    """По КК: в README-реестре ЭФ идентификатор стоит в обратных кавычках — инлайн-код не снимает."""
    docs = tmp_path / "docs"
    card(docs, "srs/bc-issue/screen-form/scr-cl-01.md", "SCR-CL-01")
    w(docs / "srs/bc-issue/screen-form/README.md",
      f"# Экранные формы\n\n| ID | Название | Источник |\n|---|---|---|\n| SCR-CL-01 | Т | `{PID}` |\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert not ok and "srs/bc-issue/screen-form/README.md: строка 5" in rep[1], rep


def test_frontmatter_only_silent(tmp_path):
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01")
    assert check_page_ids_in_kit(docs) == ([], True)


def test_matrix_is_home_and_source_of_known_ids(tmp_path):
    """В матрице — молчит (законный дом); число из матрицы в теле README — ✗ с происхождением."""
    docs = tmp_path / "docs"
    w(docs / "traceability-matrix.md", f"# М\n\n## Источники миграции\n\n| page_id | ID |\n|---|---|\n| {PID} | SCR-CL-01 |\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert (rep, ok) == ([], True)
    w(docs / "README.md", f"# Комплект\n\nСтраница {PID}.\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert not ok and "(страница комплекта: матрица)" in rep[1], rep


def test_sentence_final_period_still_number(tmp_path):
    """Точка после числа — конец предложения: «… страница 2166860243.» ловится (у прежнего
    `_OQ_PAGE_NUM_RE` такая строка молчала); дробь «2166860243.5» — не номер страницы."""
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01", f"Страница {PID}.\n\nКурс {PID}.5 за единицу\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert not ok and rep[0].startswith("✗ К-17: идентификатор страницы Confluence вне frontmatter — строк 1 "), rep
    assert "scr-cl-01.md: строка 11 —" in rep[1], rep


def test_fenced_block_silent(tmp_path):
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01", f"```\npageId={PID}\n```\n")
    assert check_page_ids_in_kit(docs) == ([], True)


def test_other_numbers_info_not_blocking(tmp_path):
    """НЕсрабатывание ✗: ИНН/КПП/БИК в примерах (эталон, замер 09.11: 17 таких строк) — i-строка."""
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01", "Пример: ИНН 7707083893, БИК 044525225.\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert ok
    assert rep == ["i К-17: числа вида page_id вне множества страниц комплекта: 2: "
                   "srs/screen-form/scr-cl-01.md:11 `7707083893`; srs/screen-form/scr-cl-01.md:11 `044525225`"], rep


def test_confluence_address_blocks_other_hosts_silent(tmp_path):
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01",
         "См. [страницу](https://confluence.example.ru/pages/viewpage.action?pageId=123456).\n\n"
         "Утилита — https://github.com/x/confluence-tree-exporter.\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert not ok and rep[0].startswith("✗ К-17: идентификатор страницы Confluence вне frontmatter — строк 1 "), rep
    assert "(адрес страницы Confluence)" in rep[1], rep


def test_open_questions_and_work_dirs_skipped(tmp_path):
    """open-questions — прежнее правило К-17; sources/, sandbox/, каталог --sources — не документы."""
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01")
    w(docs / "open-questions.md", f"# OQ\n\nСтраница {PID}.\n")
    w(docs / "sources/README.md", f"# Профиль\n\nСтраница {PID}.\n")
    w(docs / "sandbox/normalized/x.md", f"Страница {PID}.\n")
    w(docs / "confluence/p.md", f"---\nconfluence_page_id: '{PID}'\n---\n\nСтраница {PID}.\n")
    assert check_page_ids_in_kit(docs, docs / "confluence") == ([], True)


def test_sources_pages_extend_known_set(tmp_path):
    """При --sources page_id страниц выгрузки — тоже страницы комплекта (КК: 51 файл / 92 строки)."""
    root = tmp_path
    docs = root / "docs"
    w(root / "sources/confluence/p.md", "---\nconfluence_page_id: '2184430096'\n---\n\nТ.\n")
    card(docs, "srs/function/fun-cl-55.md", "FUN-CL-55", "Справочник страницы 2184430096 — текстом.\n")
    rep, ok = check_page_ids_in_kit(docs)
    assert ok and rep[0].startswith("i К-17: числа вида page_id"), rep
    rep, ok = check_page_ids_in_kit(docs, root / "sources")
    assert not ok and "(страница комплекта: выгрузка)" in rep[1], rep


def test_kit_check_changes_verdict(tmp_path):
    docs = tmp_path / "docs"
    card(docs, "srs/screen-form/scr-cl-01.md", "SCR-CL-01")
    w(docs / "README.md", f"# Комплект\n\nСтраница `{PID}`.\n")
    rep, ok = sc.run(docs, None)
    assert not ok
    assert any(ln.startswith("✗ К-17: идентификатор страницы Confluence вне frontmatter") for ln in rep), rep
