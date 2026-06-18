# tests/test_manifest_card_url.py
#
# Фаза 2 перехода к location-независимому doc_id (см.
# app/scripts/CI/design-smart-link-doc-id.md, §7.4):
#   • url карточки в манифесте = путь источника относительно каталога сервиса
#     (зеркало дерева), а НЕ f"{doc_id}.md" (doc_id теперь смарт-ссылка {{...}}).
#
# Модули в app/scripts/CI используют sibling-импорты, поэтому каталог добавляется
# в sys.path перед импортом manifest_builder.

import sys
from pathlib import Path

_CI_DIR = Path(__file__).resolve().parent.parent / "app" / "scripts" / "CI"
if str(_CI_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_DIR))

import manifest_builder  # noqa: E402


_CARD_CONFIG = {"types": {"function": {"resolve_target": "card", "generate_card": True}}}


class TestCardRelUrl:
    def test_mirrors_source_path_posix(self):
        assert manifest_builder.card_rel_url("conf/cc/sub/f.md", "conf/cc") == "sub/f.md"

    def test_no_service_prefix_duplication(self):
        # service_dir уже включает сервис → префикс не дублируется в url.
        assert manifest_builder.card_rel_url("conf/cc/a/b.md", "conf/cc") == "a/b.md"


class TestDocIdToUrl:
    def test_card_returns_mirror_path_not_doc_id(self):
        url = manifest_builder._doc_id_to_url("{{CC: T}}", "card", card_rel_path="sub/f.md")
        assert url == "sub/f.md"

    def test_swagger_explicit_url_wins(self):
        assert manifest_builder._doc_id_to_url("op", "swagger", swagger_url="http://x") == "http://x"


class TestBuildEntry:
    def test_card_url_is_mirror_path(self):
        meta = {
            "title": "[КК] Заявка",
            "doc_id": "{{CC: [КК] Заявка}}",
            "requirement_type": "function",
        }
        entry = manifest_builder.build_entry(meta, _CARD_CONFIG, card_rel_path="sub/f.md")
        assert entry is not None
        assert entry.kind == "card"
        assert entry.doc_id == "{{CC: [КК] Заявка}}"
        assert entry.url == "sub/f.md"  # не "{{CC: [КК] Заявка}}.md"


class TestBuildManifest:
    def test_card_url_computed_from_service_dir(self, tmp_path):
        svc = tmp_path / "cc"
        f = svc / "sub" / "f.md"
        f.parent.mkdir(parents=True)
        f.write_text(
            "---\ntitle: T\ndoc_id: '{{CC: T}}'\nrequirement_type: function\n"
            "service_code: CC\n---\n\nтело\n",
            encoding="utf-8",
        )
        result = manifest_builder.build_manifest(
            [str(f)], _CARD_CONFIG, service_code="CC", service_dir=str(svc)
        )
        assert len(result.entries) == 1
        assert result.entries[0].url == "sub/f.md"
        assert result.entries[0].doc_id == "{{CC: T}}"
