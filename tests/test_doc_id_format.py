# tests/test_doc_id_format.py
#
# Фаза 1 перехода к location-независимому doc_id (см.
# app/scripts/CI/design-smart-link-doc-id.md):
#   • build_doc_id строит смарт-ссылку {{SERVICE: label}}, label = полный заголовок;
#   • линтер валидирует формат doc_id (смарт-ссылка, а не путь).

import yaml

from app.scripts.migrate_confluence_page import build_doc_id
from app.scripts.lint_frontmatter import _DOC_ID_RE, lint_file


class TestBuildDocId:
    def test_basic(self):
        assert build_doc_id("CC", "[КК_ВК] Заявка") == "{{CC: [КК_ВК] Заявка}}"

    def test_label_keeps_prefix_colons_and_quotes(self):
        # label == title целиком: префикс, двоеточие и кавычки сохраняются как есть.
        title = '[КК_БК] ЭФ Клиента: "Заявка на блокировку КК" в режиме просмотра'
        assert build_doc_id("CC", title) == f'{{{{CC: {title}}}}}'

    def test_service_code_verbatim(self):
        # Код сервиса не нормализуется (в отличие от пути) — тот же вид, что во frontmatter.
        assert build_doc_id("SBP", "Заголовок") == "{{SBP: Заголовок}}"


class TestDocIdRegex:
    def test_accepts_smart_link(self):
        assert _DOC_ID_RE.match("{{CC: [КК_ВК] Заявка}}")

    def test_accepts_colons_and_quotes_in_label(self):
        assert _DOC_ID_RE.match('{{CC: ЭФ Клиента: "Заявка"}}')

    def test_rejects_path_form(self):
        # Старый формат doc_id (путь) должен отвергаться.
        assert not _DOC_ID_RE.match("cc/[КК_ВК]-Заявка/file")

    def test_rejects_plain_text(self):
        assert not _DOC_ID_RE.match("просто строка")

    def test_rejects_empty_label(self):
        assert not _DOC_ID_RE.match("{{CC: }}")


class TestLintDocId:
    def _write(self, tmp_path, **overrides):
        meta = {
            "doc_id": "{{CC: [КК_ВК] Заявка}}",
            "title": "[КК_ВК] Заявка",
            "doc_type": "requirement",
            "requirement_type": "function",
            "service_code": "CC",
            "status": "approved",
            "owner": "ivanov",
            "jira_id": "DBO-1",
            "source": "DBOCORPESPLN",
        }
        meta.update(overrides)
        fp = tmp_path / "f.md"
        fp.write_text(
            "---\n" + yaml.dump(meta, allow_unicode=True, sort_keys=False) + "---\n\nтело\n",
            encoding="utf-8",
        )
        return fp

    def test_valid_smart_link_passes(self, tmp_path):
        # Полностью валидный frontmatter со смарт-ссылкой → ноль ошибок.
        assert lint_file(self._write(tmp_path)) == []

    def test_path_form_doc_id_flagged(self, tmp_path):
        fp = self._write(tmp_path, doc_id="cc/[КК_ВК]-Заявка/file")
        errors = lint_file(fp)
        assert any("invalid doc_id" in e for e in errors)
