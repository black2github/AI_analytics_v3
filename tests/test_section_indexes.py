# tests/test_section_indexes.py
#
# Pass 3 миграции (флаг --with-index): генерация навигационных index.md по папкам.
# Покрывает generate_section_indexes (листинг детей/подпапок, заголовки из frontmatter,
# исключение img/ и самого index.md, угловые скобки для спецсимволов, идемпотентность)
# и исключение index.md/README.md из линтера.

from pathlib import Path

from app.scripts.migrate_confluence_tree import (
    generate_section_indexes,
    INDEX_FILENAME,
)
from app.scripts.lint_frontmatter import lint_file


def _write_md(path: Path, title: str | None = None, body: str = "тело"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if title is not None:
        text = f"---\ntitle: {title!r}\n---\n\n{body}\n"
    else:
        text = body
    path.write_text(text, encoding="utf-8")


def _index(d: Path) -> str:
    return (d / INDEX_FILENAME).read_text(encoding="utf-8")


class TestGenerateSectionIndexes:
    def test_lists_md_children_with_frontmatter_titles(self, tmp_path):
        _write_md(tmp_path / "Заявка.md", title="[КК] Заявка на карту")
        _write_md(tmp_path / "Лимиты.md", title="[КК] Лимиты")

        created = generate_section_indexes(tmp_path)

        assert created == 1
        idx = _index(tmp_path)
        assert "- [[КК] Заявка на карту](<Заявка.md>)" in idx
        assert "- [[КК] Лимиты](<Лимиты.md>)" in idx

    def test_title_falls_back_to_filename(self, tmp_path):
        _write_md(tmp_path / "Без-заголовка.md", title=None)
        generate_section_indexes(tmp_path)
        assert "- [Без-заголовка](<Без-заголовка.md>)" in _index(tmp_path)

    def test_index_does_not_list_itself(self, tmp_path):
        _write_md(tmp_path / "Страница.md", title="Страница")
        generate_section_indexes(tmp_path)
        # повторный прогон: index.md уже существует, но не должен попасть в перечень
        generate_section_indexes(tmp_path)
        idx = _index(tmp_path)
        assert "index.md" not in idx

    def test_nested_subfolder_linked_to_its_index(self, tmp_path):
        _write_md(tmp_path / "Раздел" / "Дочерняя.md", title="Дочерняя")
        created = generate_section_indexes(tmp_path)

        # index.md в корне и в подпапке
        assert created == 2
        root_idx = _index(tmp_path)
        assert "- [Раздел/](<Раздел/index.md>)" in root_idx
        assert "- [Дочерняя](<Дочерняя.md>)" in _index(tmp_path / "Раздел")

    def test_img_dir_excluded(self, tmp_path):
        _write_md(tmp_path / "Страница.md", title="Страница")
        (tmp_path / "img").mkdir()
        (tmp_path / "img" / "pic.png").write_bytes(b"x")

        generate_section_indexes(tmp_path)

        assert not (tmp_path / "img" / INDEX_FILENAME).exists()
        assert "img/" not in _index(tmp_path)

    def test_empty_dir_gets_no_index(self, tmp_path):
        (tmp_path / "Пусто").mkdir()
        created = generate_section_indexes(tmp_path / "Пусто")
        assert created == 0
        assert not (tmp_path / "Пусто" / INDEX_FILENAME).exists()

    def test_special_chars_in_name_wrapped_in_angle_brackets(self, tmp_path):
        _write_md(tmp_path / "Создать-заявку-(115).md", title="Создать заявку (115)")
        generate_section_indexes(tmp_path)
        # скобки в URL обёрнуты <...>, чтобы не ломать markdown-ссылку
        assert "(<Создать-заявку-(115).md>)" in _index(tmp_path)

    def test_subfolder_without_listing_shown_without_link(self, tmp_path):
        _write_md(tmp_path / "Страница.md", title="Страница")
        # подпапка только с img/ → листать нечего → без ссылки
        (tmp_path / "Пустой-раздел" / "img").mkdir(parents=True)
        generate_section_indexes(tmp_path)
        root_idx = _index(tmp_path)
        assert "- Пустой-раздел/" in root_idx
        assert "(<Пустой-раздел/index.md>)" not in root_idx

    def test_idempotent_rerun(self, tmp_path):
        _write_md(tmp_path / "Страница.md", title="Страница")
        generate_section_indexes(tmp_path)
        first = _index(tmp_path)
        generate_section_indexes(tmp_path)
        assert _index(tmp_path) == first


class TestLinterIgnoresGeneratedFiles:
    def test_index_md_skipped(self, tmp_path):
        f = tmp_path / "index.md"
        f.write_text("# Раздел\n\n- [x](<x.md>)\n", encoding="utf-8")
        assert lint_file(f) == []

    def test_readme_md_skipped(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text("# нет frontmatter\n", encoding="utf-8")
        assert lint_file(f) == []
