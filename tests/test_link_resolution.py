# tests/test_link_resolution.py
#
# Pass 2 миграции дерева: разрешение плейсхолдеров confluence:// в относительные
# пути. Покрывает:
#   • _title_key — нормализация заголовка в ключ реестра (html.unescape + пробелы);
#   • resolve_confluence_links — резолв ID- и title-ссылок (md и HTML-формы),
#     включая баг с &quot; в заголовках внутри HTML-таблиц и fallback'и;
#   • seed_registries_from_disk — подмешивание ранее сохранённых .md по frontmatter
#     (confluence_page_id + title) и приоритет записей текущего запуска.

import pytest

import app.scripts.migrate_confluence_tree as mig
from app.scripts.migrate_confluence_tree import (
    _title_key,
    resolve_confluence_links,
    seed_registries_from_disk,
)
from app.content_extractor import create_all_fragments_extractor


class TestPlaceholderProducer:
    """Контракт генерации плейсхолдеров в content_extractor — должен совпадать
    с тем, что парсит resolve_confluence_links (Pass 2)."""

    def _extract(self, html):
        return create_all_fragments_extractor().extract(html)

    def test_id_with_title_emits_title_suffix(self):
        # ac:link с ID и заголовком → confluence://ID?title=SPACE/Encoded
        # (суффикс нужен для fallback-резолва по заголовку при промахе ID).
        html = ('<p><ac:link><ri:page ri:content-id="123" ri:content-title="Моя страница" '
                'ri:space-key="SP"/><ac:plain-text-link-body>текст</ac:plain-text-link-body>'
                '</ac:link></p>')
        assert "confluence://123?title=SP/Моя+страница" in self._extract(html)

    def test_title_only_emits_title_placeholder(self):
        # Без ID → confluence://title/SPACE/Encoded (формат не изменился).
        html = ('<p><ac:link><ri:page ri:content-title="Моя страница" ri:space-key="SP"/>'
                '<ac:plain-text-link-body>текст</ac:plain-text-link-body></ac:link></p>')
        out = self._extract(html)
        assert "confluence://title/SP/Моя+страница" in out
        assert "?title=" not in out


class TestTitleKey:
    def test_unescapes_html_entities(self):
        # &quot; из плейсхолдера HTML-таблицы должен раскрыться в настоящую кавычку,
        # иначе заголовок никогда не совпадёт с ключом реестра.
        assert _title_key('[КК_СК] ЭФ Клиента &quot;Список карт&quot;') == \
               _title_key('[КК_СК] ЭФ Клиента "Список карт"')

    def test_amp_entity(self):
        assert _title_key("Карты &amp; Счета") == _title_key("Карты & Счета")

    def test_collapses_whitespace_and_lowercases(self):
        assert _title_key("  Заявка   на\nзакрытие  ") == "заявка на закрытие"


class TestResolveConfluenceLinks:
    def _setup(self, tmp_path, body):
        """Создаёт целевой файл (sub/Целевая.md) и файл-источник с body."""
        target = tmp_path / "sub" / "Целевая.md"
        target.parent.mkdir(parents=True)
        target.write_text("целевая страница", encoding="utf-8")
        source = tmp_path / "Источник.md"
        source.write_text(body, encoding="utf-8")
        return source, target

    def test_markdown_id_link_resolved_to_relative(self, tmp_path):
        source, target = self._setup(tmp_path, "[Текст](confluence://123)")
        resolved, unresolved = resolve_confluence_links(
            {"123": target}, {}, files={source}
        )
        assert source.read_text(encoding="utf-8") == "[Текст](sub/Целевая.md)"
        assert (resolved, unresolved) == (1, 0)

    def test_markdown_title_link_resolved(self, tmp_path):
        source, target = self._setup(
            tmp_path, "[Текст](confluence://title/SPACE/Заголовок+страницы)"
        )
        title_registry = {_title_key("Заголовок страницы"): target}
        resolved, unresolved = resolve_confluence_links({}, title_registry, files={source})
        assert source.read_text(encoding="utf-8") == "[Текст](sub/Целевая.md)"
        assert (resolved, unresolved) == (1, 0)

    def test_html_id_link_resolved(self, tmp_path):
        source, target = self._setup(
            tmp_path, '<a href="confluence://123">текст</a>'
        )
        resolve_confluence_links({"123": target}, {}, files={source})
        assert source.read_text(encoding="utf-8") == '<a href="sub/Целевая.md">текст</a>'

    def test_html_title_link_with_quotes_resolved(self, tmp_path):
        # Регрессия: внутри HTML-таблиц кавычки кодируются как &quot;.
        # Без html.unescape в Pass 2 эта ссылка никогда не разрешалась.
        source, target = self._setup(
            tmp_path,
            '<a href="confluence://title/SPACE/[КК_СК]+ЭФ+Клиента+&quot;Список+карт&quot;">текст</a>',
        )
        title_registry = {_title_key('[КК_СК] ЭФ Клиента "Список карт"'): target}
        resolved, unresolved = resolve_confluence_links({}, title_registry, files={source})
        assert source.read_text(encoding="utf-8") == '<a href="sub/Целевая.md">текст</a>'
        assert (resolved, unresolved) == (1, 0)

    def test_id_link_with_title_suffix_prefers_id(self, tmp_path):
        # ID есть в реестре — резолвим по нему, title-суффикс игнорируется.
        source, target = self._setup(
            tmp_path, "[Текст](confluence://123?title=SPACE/Неважно)"
        )
        resolved, unresolved = resolve_confluence_links({"123": target}, {}, files={source})
        assert source.read_text(encoding="utf-8") == "[Текст](sub/Целевая.md)"
        assert (resolved, unresolved) == (1, 0)

    def test_id_link_with_title_suffix_falls_back_to_title(self, tmp_path):
        # ID нет в page_registry, но плейсхолдер несёт ?title=... и заголовок
        # есть в title_registry (например, страница из прошлого прогона на диске).
        source, target = self._setup(
            tmp_path, "[Текст](confluence://999?title=SPACE/Заголовок+страницы)"
        )
        title_registry = {_title_key("Заголовок страницы"): target}
        resolved, unresolved = resolve_confluence_links({}, title_registry, files={source})
        assert source.read_text(encoding="utf-8") == "[Текст](sub/Целевая.md)"
        assert (resolved, unresolved) == (1, 0)

    def test_id_link_with_title_suffix_unresolved_uses_bare_pageid_url(self, tmp_path):
        # Ни ID, ни заголовок не найдены — URL строится по «голому» pageId без суффикса.
        source, _ = self._setup(tmp_path, "[Текст](confluence://999?title=SPACE/Нет+такой)")
        resolved, unresolved = resolve_confluence_links({}, {}, files={source})
        assert source.read_text(encoding="utf-8") == \
            f"[Текст]({mig.CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId=999)"
        assert (resolved, unresolved) == (0, 1)

    def test_html_id_link_with_title_suffix_falls_back_to_title(self, tmp_path):
        # HTML-форма в таблицах: ID-промах, заголовок (с &quot;) находится по title.
        source, target = self._setup(
            tmp_path,
            '<a href="confluence://999?title=SPACE/[КК_СК]+ЭФ+Клиента+&quot;Список+карт&quot;">текст</a>',
        )
        title_registry = {_title_key('[КК_СК] ЭФ Клиента "Список карт"'): target}
        resolved, unresolved = resolve_confluence_links({}, title_registry, files={source})
        assert source.read_text(encoding="utf-8") == '<a href="sub/Целевая.md">текст</a>'
        assert (resolved, unresolved) == (1, 0)

    def test_unresolved_id_falls_back_to_absolute_url(self, tmp_path):
        source, _ = self._setup(tmp_path, "[Текст](confluence://999)")
        resolved, unresolved = resolve_confluence_links({}, {}, files={source})
        assert source.read_text(encoding="utf-8") == \
            f"[Текст]({mig.CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId=999)"
        assert (resolved, unresolved) == (0, 1)

    def test_unresolved_markdown_title_kept_as_text(self, tmp_path):
        source, _ = self._setup(tmp_path, "[Текст](confluence://title/Неизвестная)")
        resolve_confluence_links({}, {}, files={source})
        # title-ссылку без цели нельзя осмысленно адресовать — остаётся текст в скобках.
        assert source.read_text(encoding="utf-8") == "[Текст]"

    def test_unresolved_html_title_with_space_falls_back_to_display(self, tmp_path):
        source, _ = self._setup(
            tmp_path, '<a href="confluence://title/CARDS/Заявка+на+закрытие">x</a>'
        )
        resolve_confluence_links({}, {}, files={source})
        assert source.read_text(encoding="utf-8") == \
            f'<a href="{mig.CONFLUENCE_BASE_URL}/display/CARDS/Заявка+на+закрытие">x</a>'

    def test_unresolved_html_title_without_space_falls_back_to_search(self, tmp_path):
        source, _ = self._setup(
            tmp_path, '<a href="confluence://title/Заявка+на+закрытие">y</a>'
        )
        resolve_confluence_links({}, {}, files={source})
        assert source.read_text(encoding="utf-8") == \
            f'<a href="{mig.CONFLUENCE_BASE_URL}/dosearchsite.action?queryString=Заявка+на+закрытие">y</a>'

    def test_only_listed_files_are_rewritten(self, tmp_path):
        # files=... ограничивает запись; чужие файлы с плейсхолдерами не трогаем.
        source, target = self._setup(tmp_path, "[Текст](confluence://123)")
        other = tmp_path / "Чужой.md"
        other.write_text("[Другой](confluence://123)", encoding="utf-8")
        resolve_confluence_links({"123": target}, {}, files={source})
        assert other.read_text(encoding="utf-8") == "[Другой](confluence://123)"


class TestSeedRegistriesFromDisk:
    def _write_md(self, path, title, page_id):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\ntitle: {title!r}\nconfluence_page_id: '{page_id}'\n---\n\nтело\n",
            encoding="utf-8",
        )

    def test_seeds_page_id_and_title_from_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mig, "OUTPUT_ROOT", tmp_path)
        f = tmp_path / "Старая.md"
        self._write_md(f, "Старая страница", "777")

        page_registry, title_registry = {}, {}
        added = seed_registries_from_disk(page_registry, title_registry)

        assert added == 1
        assert page_registry["777"] == f
        assert title_registry[_title_key("Старая страница")] == f

    def test_does_not_overwrite_current_run_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mig, "OUTPUT_ROOT", tmp_path)
        self._write_md(tmp_path / "Диск.md", "Общий заголовок", "1")

        current = tmp_path / "Текущий.md"  # запись текущего прогона (приоритетна)
        page_registry = {"1": current}
        title_registry = {_title_key("Общий заголовок"): current}
        seed_registries_from_disk(page_registry, title_registry)

        assert page_registry["1"] == current
        assert title_registry[_title_key("Общий заголовок")] == current

    def test_skips_files_without_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mig, "OUTPUT_ROOT", tmp_path)
        (tmp_path / "Просто.md").write_text("# без frontmatter\n", encoding="utf-8")

        page_registry, title_registry = {}, {}
        added = seed_registries_from_disk(page_registry, title_registry)

        assert added == 0
        assert page_registry == {} and title_registry == {}

    def test_seeded_file_resolves_links(self, tmp_path, monkeypatch):
        # Сквозной сценарий: ссылка на страницу из прошлого прогона (на диске)
        # резолвится за счёт frontmatter, а не текущего обхода дерева.
        monkeypatch.setattr(mig, "OUTPUT_ROOT", tmp_path)
        old = tmp_path / "Раздел" / "Заявка-на-закрытие.md"
        self._write_md(old, "[КК_ЗК] Заявка на закрытие карты", "555")

        source = tmp_path / "Журнал.md"
        source.write_text(
            '<a href="confluence://title/CARDS/[КК_ЗК]+Заявка+на+закрытие+карты">ссылка</a>',
            encoding="utf-8",
        )

        page_registry, title_registry = {}, {}
        seed_registries_from_disk(page_registry, title_registry)
        resolved, _ = resolve_confluence_links(page_registry, title_registry, files={source})

        assert source.read_text(encoding="utf-8") == \
            '<a href="Раздел/Заявка-на-закрытие.md">ссылка</a>'
        assert resolved == 1
