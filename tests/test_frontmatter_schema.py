# tests/test_frontmatter_schema.py
#
# Переход на целевую схему frontmatter (Вариант B):
#   • status: approved → active (enum draft|review|active|deprecated);
#   • reviewers (вместо reviewed_by) и tags — YAML-списки, а не строки;
#   • добавлено поле date.
# Покрывает генератор (page_to_frontmatter), сериализацию (write_md_file)
# и линтер (lint_file).

import yaml

from app.scripts.migrate_confluence_page import page_to_frontmatter, write_md_file
from app.scripts.lint_frontmatter import lint_file


def _fm(**kwargs):
    page = {"id": "123", "title": "T", "requirement_type": "function"}
    return page_to_frontmatter(page, "CC", "DBOCORPESPLN", "{{CC: T}}", **kwargs)


class TestGeneratorSchema:
    def test_reviewers_and_tags_are_lists(self):
        fm = _fm()
        assert fm["reviewers"] == []
        assert fm["tags"] == []
        assert isinstance(fm["reviewers"], list)
        assert isinstance(fm["tags"], list)

    def test_no_legacy_reviewed_by_field(self):
        # Старое строковое поле должно исчезнуть из схемы.
        assert "reviewed_by" not in _fm()

    def test_date_field_present(self):
        assert "date" in _fm()

    def test_status_active_by_default(self):
        # Подтверждённый контент → active (а не прежнее approved).
        assert _fm()["status"] == "active"

    def test_status_draft_for_unapproved(self):
        assert _fm(include_unapproved=True, has_unapproved=True)["status"] == "draft"


class TestYamlSerialization:
    def test_empty_list_renders_as_flow_brackets(self, tmp_path):
        fp = tmp_path / "f.md"
        write_md_file(fp, _fm(), "тело")
        text = fp.read_text(encoding="utf-8")
        assert "tags: []" in text
        assert "reviewers: []" in text

    def test_filled_list_renders_as_block_array(self, tmp_path):
        fm = _fm()
        fm["tags"] = ["карты", "лимиты"]
        fp = tmp_path / "f.md"
        write_md_file(fp, fm, "тело")
        reparsed = yaml.safe_load(fp.read_text(encoding="utf-8").split("---")[1])
        assert reparsed["tags"] == ["карты", "лимиты"]


class TestLinterSchema:
    def _write(self, tmp_path, **overrides):
        meta = {
            "doc_id": "{{CC: [КК_ВК] Заявка}}",
            "title": "[КК_ВК] Заявка",
            "doc_type": "requirement",
            "requirement_type": "function",
            "service_code": "CC",
            "status": "active",
            "owner": "ivanov",
            "jira_id": "DBO-1",
            "source": "DBOCORPESPLN",
            "reviewers": [],
            "tags": [],
        }
        meta.update(overrides)
        fp = tmp_path / "f.md"
        fp.write_text(
            "---\n" + yaml.dump(meta, allow_unicode=True, sort_keys=False) + "---\n\nтело\n",
            encoding="utf-8",
        )
        return fp

    def test_active_status_and_list_fields_pass(self, tmp_path):
        assert lint_file(self._write(tmp_path)) == []

    def test_filled_lists_pass(self, tmp_path):
        fp = self._write(tmp_path, reviewers=["Иванов И.И."], tags=["карты", "лимиты"])
        assert lint_file(fp) == []

    def test_legacy_approved_status_rejected(self, tmp_path):
        errors = lint_file(self._write(tmp_path, status="approved"))
        assert any("invalid status" in e for e in errors)

    def test_tags_as_string_rejected(self, tmp_path):
        errors = lint_file(self._write(tmp_path, tags="карты, лимиты"))
        assert any("'tags' must be a YAML list" in e for e in errors)

    def test_reviewers_as_string_rejected(self, tmp_path):
        errors = lint_file(self._write(tmp_path, reviewers="Иванов"))
        assert any("'reviewers' must be a YAML list" in e for e in errors)
