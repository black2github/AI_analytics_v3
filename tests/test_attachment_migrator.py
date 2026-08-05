# tests/test_attachment_migrator.py
"""Миграция файлов-вложений (/download/attachments/…) в files/ рядом с .md.

Контекст (2026-08-05, страница [БлокН2Н]): ссылки на документы-вложения
(.vsdx и т.п.) оставались серверными путями Confluence — вне сервера мертвы.
Слой attachment_migrator (флаг --with-attachments) скачивает файл в files/
и заменяет ссылку относительной; неудача/превышение лимита — ссылка
ОСТАЁТСЯ серверной (тихих потерь нет).
"""

import pytest

import app.attachment_migrator as am
import app.config as _config
from app.attachment_migrator import migrate_file_attachments_in_content, _target_name


PAGE_ID = "2138953700"
VSDX_URL = ("/download/attachments/2138953700/"
            "%D0%A1%D1%85%D0%B5%D0%BC%D0%B0.vsdx?version=1&api=v2")


@pytest.fixture
def fake_download(monkeypatch):
    calls = []

    def _fake(url):
        calls.append(url)
        return b"FILEDATA"

    monkeypatch.setattr(am, "_browser_get_bytes", _fake)
    return calls


class TestLinkRewrite:
    def test_markdown_link_rewritten(self, tmp_path, fake_download):
        md = f"Схема процесса [Схема.vsdx]({VSDX_URL}) в приложении."
        out, dl, fail, skip = migrate_file_attachments_in_content(
            md, PAGE_ID, tmp_path / "page.md")
        assert dl == 1 and fail == 0 and skip == 0
        assert "](files/" in out and "/download/attachments/" not in out
        saved = list((tmp_path / "files").iterdir())
        assert len(saved) == 1 and saved[0].suffix == ".vsdx"
        assert saved[0].read_bytes() == b"FILEDATA"
        assert saved[0].name.startswith("Схема-")  # имя декодировано и читаемо

    def test_html_href_rewritten(self, tmp_path, fake_download):
        md = f'<td><a href="{VSDX_URL}">Схема</a></td>'
        out, dl, fail, skip = migrate_file_attachments_in_content(
            md, PAGE_ID, tmp_path / "page.md")
        assert dl == 1
        assert '<a href="files/' in out

    def test_same_url_downloaded_once(self, tmp_path, fake_download):
        md = f"[a]({VSDX_URL}) и снова [b]({VSDX_URL})"
        out, dl, _, _ = migrate_file_attachments_in_content(
            md, PAGE_ID, tmp_path / "page.md")
        assert dl == 1 and len(fake_download) == 1
        assert out.count("](files/") == 2

    def test_idempotent_second_run(self, tmp_path, fake_download):
        md = f"[a]({VSDX_URL})"
        migrate_file_attachments_in_content(md, PAGE_ID, tmp_path / "page.md")
        migrate_file_attachments_in_content(md, PAGE_ID, tmp_path / "page.md")
        assert len(fake_download) == 1  # второй прогон не качает повторно


class TestGuards:
    def test_ordinary_links_untouched(self, tmp_path, fake_download):
        md = "[стр](https://confluence.x/pages/viewpage.action?pageId=1) и [img](img/a.png)"
        out, dl, fail, skip = migrate_file_attachments_in_content(
            md, PAGE_ID, tmp_path / "page.md")
        assert out == md and dl == fail == skip == 0 and not fake_download

    def test_foreign_host_left_as_is(self, tmp_path, fake_download, monkeypatch):
        monkeypatch.setattr(_config, "CONFLUENCE_BASE_URL", "https://confluence.our.ru")
        md = "[f](https://confluence.foreign.ru/download/attachments/1/x.docx)"
        out, dl, fail, skip = migrate_file_attachments_in_content(
            md, PAGE_ID, tmp_path / "page.md")
        assert out == md and dl == 0 and not fake_download

    def test_failed_download_keeps_server_link(self, tmp_path, monkeypatch):
        monkeypatch.setattr(am, "_browser_get_bytes", lambda url: None)
        md = f"[a]({VSDX_URL})"
        out, dl, fail, skip = migrate_file_attachments_in_content(
            md, PAGE_ID, tmp_path / "page.md")
        assert out == md and fail == 1  # ссылка не заменена — не потеряна

    def test_oversize_skipped_with_server_link(self, tmp_path, monkeypatch):
        monkeypatch.setattr(am, "_browser_get_bytes", lambda url: b"x" * 2048)
        monkeypatch.setattr(_config, "ATTACHMENT_MAX_MB", 0)  # лимит 0 МБ
        md = f"[a]({VSDX_URL})"
        out, dl, fail, skip = migrate_file_attachments_in_content(
            md, PAGE_ID, tmp_path / "page.md")
        assert out == md and skip == 1 and dl == 0
        assert not (tmp_path / "files").exists()


class TestNaming:
    def test_forbidden_chars_sanitized(self):
        name = _target_name("1", 'от"чё:т?.docx')
        assert all(c not in name for c in '<>:"|?*')
        assert name.endswith(".docx")

    def test_long_name_truncated_keeps_ext_and_uid(self):
        long = "х" * 200 + ".vsdx"
        name = _target_name("1", long)
        assert len(name) < 120 and name.endswith(".vsdx")
        # uid-хвост сохраняет уникальность после усечения
        other = _target_name("1", "х" * 200 + "y.vsdx")
        assert name != other

    def test_same_name_different_pages_differ(self):
        assert _target_name("1", "a.docx") != _target_name("2", "a.docx")
