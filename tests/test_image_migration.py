# tests/test_image_migration.py

import hashlib
from pathlib import Path

import pytest

from app.content_extractor import ContentExtractor, ExtractionConfig
import app.image_migrator as image_migrator


def _extract(html: str, migrate_images: bool) -> str:
    return ContentExtractor(ExtractionConfig(migrate_images=migrate_images)).extract(html)


class TestImageConverter:
    """Конвертер: <ac:image> -> HTML <img> с плейсхолдером вложения (под флагом)."""

    ATTACH = (
        '<p><ac:image ac:width="400" ac:height="250">'
        '<ri:attachment ri:filename="diagram.png"/></ac:image></p>'
    )

    def test_disabled_by_default_image_dropped(self):
        # По умолчанию (флаг выключен) картинка выкидывается — прежнее поведение.
        assert "<img" not in _extract(self.ATTACH, migrate_images=False)

    def test_attachment_becomes_placeholder_with_scaling(self):
        out = _extract(self.ATTACH, migrate_images=True)
        assert '<img src="confluence-attachment://diagram.png"' in out
        assert 'width="400"' in out and 'height="250"' in out
        # размеры сохранены, атрибуты не «склеены» чисткой треугольных скобок
        assert '"width=' not in out

    def test_external_url_image_kept_inline(self):
        html = '<p><ac:image ac:width="120"><ri:url ri:value="https://host/y.png"/></ac:image></p>'
        out = _extract(html, migrate_images=True)
        assert '<img src="https://host/y.png"' in out
        assert "confluence-attachment://" not in out  # внешние не качаем

    def test_image_in_table_cell_preserved(self):
        html = (
            '<table><tbody><tr><td>cell</td>'
            '<td><ac:image ac:width="50"><ri:attachment ri:filename="ico.svg"/></ac:image></td>'
            '</tr></tbody></table>'
        )
        out = _extract(html, migrate_images=True)
        assert '<img src="confluence-attachment://ico.svg"' in out

    def test_filename_with_ampersand_escaped(self):
        html = '<p><ac:image><ri:attachment ri:filename="a&amp;b.png"/></ac:image></p>'
        out = _extract(html, migrate_images=True)
        assert 'confluence-attachment://a&amp;b.png' in out


class TestRenderedImageConverter:
    """Конвертер: рендеренный <img> (HTTP-режим, закрытый контур)."""

    def test_embedded_attachment_becomes_download_placeholder(self):
        html = (
            '<p><span class="confluence-embedded-file-wrapper">'
            '<img class="confluence-embedded-image" '
            'data-image-src="/download/attachments/192316823/d.png?version=1&amp;api=v2" '
            'data-width="400" data-height="250" data-linked-resource-default-alias="d.png" '
            'src="/download/attachments/192316823/d.png?version=1"></span></p>'
        )
        out = _extract(html, migrate_images=True)
        # data-image-src (с query) предпочтительнее src; размеры из data-*, alt из alias
        assert 'src="confluence-download:///download/attachments/192316823/d.png?version=1&amp;api=v2"' in out
        assert 'width="400"' in out and 'height="250"' in out and 'alt="d.png"' in out

    def test_external_rendered_image_kept(self):
        html = '<p><img class="confluence-embedded-image" src="https://ext/p.png" width="100"></p>'
        out = _extract(html, migrate_images=True)
        assert '<img src="https://ext/p.png"' in out
        assert "confluence-download://" not in out

    def test_service_graphics_dropped(self):
        html = '<p>a <img class="emoticon" src="/images/icons/emoticons/smile.png" width="16"> b</p>'
        out = _extract(html, migrate_images=True)
        assert "<img" not in out  # иконки/эмотиконы не попадают в вывод


class TestImageMigrator:
    """Слой миграции: скачивание вложений в img/ и переписывание плейсхолдеров."""

    @pytest.fixture
    def mock_network(self, monkeypatch):
        monkeypatch.setattr(
            image_migrator, "_get_attachment_download_urls",
            lambda pid: {"diagram.png": "http://x/d.png", "a&b.png": "http://x/ab.png"},
        )
        calls = {"n": 0}

        def fake_get(url):
            calls["n"] += 1
            return b"BINARYDATA"

        monkeypatch.setattr(image_migrator, "_http_get_bytes", fake_get)
        return calls

    def _content(self):
        return (
            'a <img src="confluence-attachment://diagram.png" width="400" alt="diagram.png"> '
            'b <img src="confluence-attachment://a&amp;b.png" alt="a&amp;b.png"> '
            'c <img src="https://host/y.png" alt="">'
        )

    def test_downloads_and_rewrites(self, tmp_path, mock_network):
        md = tmp_path / "sub" / "page.md"
        md.parent.mkdir(parents=True)
        page_id = "192316823"

        new, downloaded, failed = image_migrator.migrate_images_in_content(
            self._content(), page_id, md
        )

        assert (downloaded, failed) == (2, 0)
        uid = hashlib.sha1(f"{page_id}/diagram.png".encode("utf-8")).hexdigest()[:8]
        assert f'<img src="img/{uid}.png"' in new          # детерминированное имя
        assert "https://host/y.png" in new                  # внешняя не тронута
        assert "confluence-attachment://" not in new        # все плейсхолдеры разрешены
        assert (md.parent / "img" / f"{uid}.png").exists()  # файл рядом с .md

    def test_idempotent_rerun_no_redownload(self, tmp_path, mock_network):
        md = tmp_path / "page.md"
        page_id = "192316823"
        image_migrator.migrate_images_in_content(self._content(), page_id, md)
        assert mock_network["n"] == 2
        # Повторный прогон: файлы уже есть — повторных скачиваний нет.
        image_migrator.migrate_images_in_content(self._content(), page_id, md)
        assert mock_network["n"] == 2

    def test_failed_download_falls_back_to_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            image_migrator, "_get_attachment_download_urls",
            lambda pid: {"diagram.png": "http://x/d.png"},
        )
        monkeypatch.setattr(image_migrator, "_http_get_bytes", lambda url: None)  # сбой скачивания
        md = tmp_path / "page.md"
        content = '<img src="confluence-attachment://diagram.png" alt="d">'

        new, downloaded, failed = image_migrator.migrate_images_in_content(content, "777", md)

        assert (downloaded, failed) == (0, 1)
        assert "confluence-attachment://" not in new                  # плейсхолдер снят
        assert "/download/attachments/777/diagram.png" in new         # fallback на абсолютный URL


class TestImageMigratorHttp:
    """Слой миграции: confluence-download:// (HTTP-режим, закрытый контур)."""

    def test_download_placeholder_resolved_via_browser(self, tmp_path, monkeypatch):
        captured = {}

        def fake_browser(url):
            captured["url"] = url
            return b"PNGDATA"

        monkeypatch.setattr(image_migrator, "_browser_get_bytes", fake_browser)
        md = tmp_path / "page.md"
        page_id = "192316823"
        content = (
            'x <img src="confluence-download:///download/attachments/192316823/d.png'
            '?version=1&amp;modificationDate=123" width="400" alt="d.png"> y'
        )

        new, downloaded, failed = image_migrator.migrate_images_in_content(content, page_id, md)

        assert (downloaded, failed) == (1, 0)
        uid = hashlib.sha1(f"{page_id}/d.png".encode("utf-8")).hexdigest()[:8]
        assert f'<img src="img/{uid}.png"' in new            # детерминированное имя (как в API-режиме)
        assert (md.parent / "img" / f"{uid}.png").exists()
        # query-параметры сохранены, &amp; разэкранирован для запроса
        assert captured["url"].endswith("d.png?version=1&modificationDate=123")
        assert captured["url"].startswith("http")            # достроен до абсолютного URL

    def test_failed_browser_download_falls_back_to_absolute_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_migrator, "_browser_get_bytes", lambda url: None)
        md = tmp_path / "page.md"
        content = '<img src="confluence-download:///download/attachments/55/a.jpg" alt="a">'

        new, downloaded, failed = image_migrator.migrate_images_in_content(content, "55", md)

        assert (downloaded, failed) == (0, 1)
        assert "confluence-download://" not in new            # плейсхолдер снят
        assert "/download/attachments/55/a.jpg" in new        # fallback на абсолютный URL


class TestLinkResourceConverter:
    """Конвертер: ac:link с ri:url (внешний URL) и ri:attachment (вложение)."""

    def test_external_url_link_preserved_regardless_of_flag(self):
        html = ('<p><ac:link><ri:url ri:value="https://ext.example/doc"/>'
                '<ac:plain-text-link-body>док</ac:plain-text-link-body></ac:link></p>')
        # ri:url не зависит от migrate_images — внешний адрес доступен без скачивания
        assert "[док](https://ext.example/doc)" in _extract(html, migrate_images=False)
        assert "[док](https://ext.example/doc)" in _extract(html, migrate_images=True)

    def test_external_url_link_text_falls_back_to_url(self):
        html = '<p><ac:link><ri:url ri:value="https://ext/x"/></ac:link></p>'
        assert "[https://ext/x](https://ext/x)" in _extract(html, migrate_images=False)

    def test_attachment_link_becomes_placeholder_with_flag(self):
        html = ('<p><ac:link><ri:attachment ri:filename="spec.pdf"/>'
                '<ac:plain-text-link-body>Спека</ac:plain-text-link-body></ac:link></p>')
        assert "[Спека](confluence-attachment://spec.pdf)" in _extract(html, migrate_images=True)

    def test_attachment_link_text_falls_back_to_filename(self):
        html = '<p><ac:link><ri:attachment ri:filename="spec.pdf"/></ac:link></p>'
        assert "[spec.pdf](confluence-attachment://spec.pdf)" in _extract(html, migrate_images=True)

    def test_attachment_link_without_flag_keeps_text_only(self):
        html = ('<p><ac:link><ri:attachment ri:filename="spec.pdf"/>'
                '<ac:plain-text-link-body>Спека</ac:plain-text-link-body></ac:link></p>')
        out = _extract(html, migrate_images=False)
        assert "confluence-attachment://" not in out
        assert "[Спека]" in out  # текст без адреса — прежнее поведение

    def test_attachment_link_in_simple_table_cell_markdown_form(self):
        # Простая таблица рендерится как markdown → ссылка в md-форме (тоже плейсхолдер).
        html = ('<table><tbody><tr><td>c</td>'
                '<td><ac:link><ri:attachment ri:filename="f.docx"/>'
                '<ac:plain-text-link-body>Файл</ac:plain-text-link-body></ac:link></td>'
                '</tr></tbody></table>')
        out = _extract(html, migrate_images=True)
        assert "[Файл](confluence-attachment://f.docx)" in out

    def test_attachment_link_in_complex_table_cell_html_form(self):
        # Сложная ячейка (вложенный список) форсит HTML-таблицу → ссылка в html-форме.
        html = ('<table><tbody><tr><td>c</td>'
                '<td><ul><li>пункт</li></ul>'
                '<ac:link><ri:attachment ri:filename="f.docx"/>'
                '<ac:plain-text-link-body>Файл</ac:plain-text-link-body></ac:link></td>'
                '</tr></tbody></table>')
        out = _extract(html, migrate_images=True)
        assert '<a href="confluence-attachment://f.docx">Файл</a>' in out


class TestAttachmentLinkMigrator:
    """Слой миграции: ссылки на вложения (md и html формы) -> img/ или fallback-URL."""

    def test_markdown_link_downloaded_and_rewritten(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_migrator, "_get_attachment_download_urls",
                            lambda pid: {"spec.pdf": "http://x/spec.pdf"})
        monkeypatch.setattr(image_migrator, "_http_get_bytes", lambda url: b"PDF")
        md = tmp_path / "page.md"
        content = "см. [Спека](confluence-attachment://spec.pdf) тут"

        new, downloaded, failed = image_migrator.migrate_images_in_content(content, "777", md)

        uid = hashlib.sha1("777/spec.pdf".encode("utf-8")).hexdigest()[:8]
        assert (downloaded, failed) == (1, 0)
        assert f"[Спека](img/{uid}.pdf)" in new
        assert (md.parent / "img" / f"{uid}.pdf").exists()

    def test_html_link_downloaded_and_rewritten(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_migrator, "_get_attachment_download_urls",
                            lambda pid: {"f.docx": "http://x/f.docx"})
        monkeypatch.setattr(image_migrator, "_http_get_bytes", lambda url: b"DOC")
        md = tmp_path / "page.md"
        content = '<a href="confluence-attachment://f.docx">Файл</a>'

        new, downloaded, failed = image_migrator.migrate_images_in_content(content, "777", md)

        uid = hashlib.sha1("777/f.docx".encode("utf-8")).hexdigest()[:8]
        assert (downloaded, failed) == (1, 0)
        assert f'<a href="img/{uid}.docx">Файл</a>' in new

    def test_link_falls_back_to_absolute_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_migrator, "_get_attachment_download_urls", lambda pid: {})
        md = tmp_path / "page.md"
        content = "[Спека](confluence-attachment://spec.pdf)"

        new, downloaded, failed = image_migrator.migrate_images_in_content(content, "55", md)

        assert (downloaded, failed) == (0, 1)
        assert "confluence-attachment://" not in new
        assert "[Спека](" in new and "/download/attachments/55/spec.pdf" in new

    def test_same_attachment_in_img_and_link_downloaded_once(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_migrator, "_get_attachment_download_urls",
                            lambda pid: {"d.png": "http://x/d.png"})
        calls = {"n": 0}

        def fake_get(url):
            calls["n"] += 1
            return b"BIN"

        monkeypatch.setattr(image_migrator, "_http_get_bytes", fake_get)
        md = tmp_path / "page.md"
        content = ('<img src="confluence-attachment://d.png" alt="d.png"> '
                   "и [тот же файл](confluence-attachment://d.png)")

        new, downloaded, failed = image_migrator.migrate_images_in_content(content, "777", md)

        # одно и то же вложение в <img> и в ссылке — скачано один раз (кэш по странице)
        assert calls["n"] == 1
        assert downloaded == 1
        assert "confluence-attachment://" not in new
