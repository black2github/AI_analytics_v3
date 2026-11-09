# tests/test_kit_root_sources_dirs.py
"""Пакет П3 ОНБ-В, п. 1 (решение владельца 2026-11-09): обход комплекта в корне репозитория
(`--docs .`) не заходит в каталог выгрузки (`--sources`, у ОНБ-В — `confluence/`) и в `sources/`
под корнем комплекта. Признак — путь, не содержимое. Раньше страницы выгрузки шли в перепись
как документы комплекта: ⚠ «поля шапки вне схемы» по шапке экспортёра, ⚠ «отсылки за пределы
комплекта» по `sources/README.md` (копия шаблона `sources-readme.md`), а страница выгрузки с
`confluence_page_id` становилась «карточкой» своей же группы.

Инварианты: раскладка «комплект в корне» — ни одной строки по файлам выгрузки и строка i с
числом снятых файлов; раскладка «комплект в `docs/`» — обход прежний."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.md import _kit_md, in_sources_dir, set_source_dirs


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


EXPORT_PAGE = ("---\ndoc_id: x\ntitle: '[Т] Функция'\ndoc_type: requirement\nauthor: ''\n"
               "confluence_page_id: '111222333'\n---\n\n# [Т] Функция\n\nтекст\n")
SOURCES_README = ("# Профиль sources\n\nПортативные правила — в [conventions.md]"
                  "(https://gitlab.gboteam.ru/ED/eco-techbook/-/blob/master/standards/analytics/"
                  "conventions.md) §1.\n")
CARD = ("---\nid: FUN-CL-01\ntitle: '[Т] Функция'\ntype: function\nservice: t\n"
        "confluence_page_ids: [111222333]\n---\n\n# FUN-CL-01. Функция\n\n## 1. Назначение\n\nтекст\n")


def root_kit(tmp_path: Path) -> Path:
    """Комплект в корне: srs/ рядом с confluence/ (выгрузка) и sources/ (профиль)."""
    root = tmp_path / "repo"
    make(root / "srs/function/client/fun-cl-01.md", CARD)
    make(root / "confluence/[Т]-Сервис/[Т]-Функция.md", EXPORT_PAGE)
    make(root / "confluence/index.md", "# Оглавление выгрузки\n")
    make(root / "sources/README.md", SOURCES_README)
    return root


def test_kit_md_skips_sources_and_export_dirs(tmp_path):
    root = root_kit(tmp_path)
    set_source_dirs([root / "confluence"])
    try:
        names = [p.relative_to(root).as_posix() for p in _kit_md(root)]
    finally:
        set_source_dirs([])
    assert names == ["srs/function/client/fun-cl-01.md"]


def test_sources_dir_skipped_without_sources_arg(tmp_path):
    """`sources/` под корнем комплекта исключается всегда; каталог выгрузки — только переданный
    как `--sources` (по пути, не по содержимому)."""
    root = root_kit(tmp_path)
    set_source_dirs([])
    assert in_sources_dir(root / "sources/README.md", root)
    assert not in_sources_dir(root / "confluence/index.md", root)


def test_docs_layout_unchanged(tmp_path):
    """Комплект в `docs/`: выгрузка вне комплекта — обход тот же, `docs/srs/sources-x/` (каталог
    не первого уровня) не снимается."""
    repo = tmp_path / "repo"
    docs = repo / "docs"
    make(docs / "srs/function/client/fun-cl-01.md", CARD)
    make(docs / "srs/sources/note.md", "# Заметка\n")
    make(repo / "sources/confluence/p.md", EXPORT_PAGE)
    set_source_dirs([repo / "sources/confluence"])
    try:
        names = [p.relative_to(docs).as_posix() for p in _kit_md(docs)]
    finally:
        set_source_dirs([])
    assert names == ["srs/function/client/fun-cl-01.md", "srs/sources/note.md"]


def test_selfcheck_root_kit_no_lines_on_export(tmp_path):
    root = root_kit(tmp_path)
    report, _ok = sc.run(root, root / "confluence")
    rest = [x for x in report if not x.startswith("i каталоги выгрузки внутри комплекта")]
    text = "\n".join(rest)
    # нет строк по файлам выгрузки и профиля (строка группы «← [т]-функция.md» — имя страницы
    # источника без каталога, не файл выгрузки в переписи)
    for path in ("confluence\\", "confluence/", "sources\\README.md", "sources/README.md"):
        assert path not in text, path
    assert "поля шапки вне схемы" not in text
    assert "отсылки за пределы комплекта" not in text
    i_line = [x for x in report if x.startswith("i каталоги выгрузки внутри комплекта")]
    assert i_line and "confluence/ (2)" in i_line[0] and "sources/ (1)" in i_line[0]


def test_selfcheck_docs_layout_has_no_i_line(tmp_path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    make(docs / "srs/function/client/fun-cl-01.md", CARD)
    make(repo / "sources/confluence/[Т]-Функция.md", EXPORT_PAGE)
    report, _ok = sc.run(docs, repo / "sources/confluence")
    assert not [x for x in report if x.startswith("i каталоги выгрузки")]


def test_export_attachments_not_orphan_artifacts(tmp_path):
    """Вложения страниц выгрузки (`confluence/…/files/`) — не артефакты комплекта: сироты не дают
    (ОНБ-В: «Сквозной бизнес-процесс….pdf» шёл ✗ «сирота files/»). Вложение под srs/ без
    ссылки — по-прежнему ✗."""
    from app.scripts.CI.kitcheck.checks.artifacts import check_file_artifacts
    root = root_kit(tmp_path)
    make(root / "confluence/[Т]-Сервис/files/процесс.pdf", "x")
    make(root / "sources/files/профиль.pdf", "x")
    rep, ok = check_file_artifacts(root, root / "confluence")
    assert ok and not rep, rep
    make(root / "srs/function/client/files/схема.json", "{}")
    rep, ok = check_file_artifacts(root, root / "confluence")
    assert not ok and any("srs/function/client/files/схема.json" in r for r in rep), rep
    assert not any("confluence/" in r for r in rep), rep


def test_export_attachments_through_selfcheck_run(tmp_path):
    """Тот же случай через прогон selfcheck с --sources: строки-сироты по выгрузке нет."""
    root = root_kit(tmp_path)
    make(root / "confluence/[Т]-Сервис/files/процесс.pdf", "x")
    rep, _ok = sc.run(root, root / "confluence")
    assert not any("сирота files/" in ln and "confluence/" in ln for ln in rep), rep
