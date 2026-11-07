# tests/test_outside_refs.py
"""Пакет П2 ОНБ-В, п. 6 (остаток замечания 14): текстовые отсылки за пределы комплекта —
техбук conventions §5, «комплект переносим». Только ⚠, вердикт не меняется."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


FM = "---\nid: X-001\ntype: glossary\nservice: x\n---\n\n# Документ\n\n"


def test_project_conventions_reference_warned(tmp_path):
    docs = tmp_path / "docs"
    # формулировка старого README комплектов (замер 2026-11-07: lkmp, ul, stand)
    w(docs / "README.md", FM + "Карта префиксов (полная схема ID — в конвенциях проекта; ниже — набор).\n")
    rep = sc.check_outside_refs(docs)
    assert rep and rep[0].startswith("⚠ отсылки за пределы комплекта ×1"), rep
    assert "README.md:9: «конвенциях проекта»" in rep[1], rep


def test_techbook_kb_toolkit_warned_including_link_address(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "a.md", FM + "Общее правило eco-techbook.\n\nСм. eco-kb и toolkit.\n\n"
      "Правила — в [conventions.md](https://gitlab.example/ED/eco-techbook/-/blob/master/x.md).\n")
    rep = sc.check_outside_refs(docs)
    assert rep[0].startswith("⚠ отсылки за пределы комплекта ×3"), rep


def test_code_quotes_frontmatter_not_warned(tmp_path):
    # НЕсрабатывание: код, кавычечный литерал, шапка
    docs = tmp_path / "docs"
    w(docs / "a.md", "---\nid: X-001\ntype: glossary\nservice: x\ntitle: eco-techbook\n---\n\n# Д\n\n"
      "```\neco-kb toolkit\n```\n\nСообщение «см. конвенции проекта» дословно.\n\n`eco-techbook`\n")
    assert sc.check_outside_refs(docs) == []


def test_lookalike_words_not_warned(tmp_path):
    # НЕсрабатывание: часть другого слова, «src-репозитории» (вне перечня по замеру),
    # «конвенции» без «проекта»
    docs = tmp_path / "docs"
    w(docs / "a.md", FM + "my-toolkit-x и eco-kb-old; Вне охвата: src-репозитории; "
      "конвенции именования ниже.\n")
    assert sc.check_outside_refs(docs) == []


def test_kit_check_does_not_change_verdict(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/glossary.md", FM.replace("X-001", "GLO-001") + "Т.\n")
    _r, ok_clean = sc.run(docs, None)
    w(docs / "srs/glossary.md", FM.replace("X-001", "GLO-001") + "Схема — в конвенциях проекта.\n")
    rep, ok_ref = sc.run(docs, None)
    assert ok_clean == ok_ref
    assert any(ln.startswith("⚠ отсылки за пределы комплекта ×1") for ln in rep), rep
