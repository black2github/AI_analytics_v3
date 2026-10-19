# tests/test_selfcheck_frontmatter_schema.py
"""Пакет 2, задача 6 (ПР-04): состав полей шапки закрыт по типу документа
(conventions §5) — поля вне схемы и устаревший version дают ⚠."""
from app.scripts.CI import selfcheck as sc


def test_lawful_fields_by_type_silent():
    assert sc.frontmatter_schema_issues({"id": "FUN-CL-01", "type": "function", "service": "x",
                                         "title": "Ф", "confluence_page_ids": "[1]",
                                         "kind": "operation"}) == ([], False)
    assert sc.frontmatter_schema_issues({"id": "F-CL-01", "type": "feature", "service": "x",
                                         "origin": "reconstructed-from-srs"}) == ([], False)
    assert sc.frontmatter_schema_issues({"type": "control", "service": "x", "partOf": "CTL-000",
                                         "entity": "ENT-001"}) == ([], False)


def test_kind_on_screen_form_and_status_warned():
    bad, ver = sc.frontmatter_schema_issues({"id": "SCR-CL-01", "type": "screen-form",
                                             "service": "x", "kind": "operation", "status": "draft"})
    assert bad == ["kind", "status"] and not ver


def test_wave5_schema_fields_lawful_by_type():
    # волна 5 ОНБ-В: domain, nfr_type, ingress, created — в схеме стандарта по типам
    assert sc.frontmatter_schema_issues({"id": "nfr-prf", "type": "nfr", "service": "x",
                                         "nfr_type": "Производительность", "ingress": "reverse"}) == ([], False)
    assert sc.frontmatter_schema_issues({"id": "VIS-000", "type": "domain-vision",
                                         "domain": "cards"}) == ([], False)
    assert sc.frontmatter_schema_issues({"id": "GLO-001", "type": "glossary", "domain": "cards"}) == ([], False)
    assert sc.frontmatter_schema_issues({"type": "task", "created": "2026-10-19"}) == ([], False)


def test_wave5_fields_outside_their_type_warned():
    bad, _v = sc.frontmatter_schema_issues({"id": "FUN-CL-01", "type": "function", "service": "x",
                                            "domain": "cards", "nfr_type": "Доступность",
                                            "created": "2026-10-19"})
    assert bad == ["created", "domain", "nfr_type"]


def test_version_warned_for_every_type_including_nfr():
    # временное освобождение nfr снято: version не используется ни у одного типа
    assert sc.frontmatter_schema_issues({"id": "nfr-prf", "type": "nfr", "service": "x",
                                         "nfr_type": "Производительность", "version": "1"}) == ([], True)
    assert sc.frontmatter_schema_issues({"id": "FUN-CL-01", "type": "function", "service": "x",
                                         "version": "prod-2026-08"}) == ([], True)


def test_format_lines():
    rep = sc.format_frontmatter_schema([("srs/a.md", ["status"], True), ("srs/b.md", [], True)])
    assert rep[0].startswith("⚠ поля шапки вне схемы типа") and "файлов 1" in rep[0]
    assert "   srs/a.md: status" in rep and "   по полям: status ×1" in rep
    assert rep[-1].startswith("⚠ поле шапки version устарело") and "файлов 2" in rep[-1]
