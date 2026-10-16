# tests/test_selfcheck_h1_service.py
"""Пакет 2, задача 9 (ЗК-26): H1 без названия сервиса — ⚠."""
import json
from pathlib import Path

from app.scripts.CI import selfcheck as sc


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _cat(tmp_path: Path) -> Path:
    c = tmp_path / "services.json"
    c.write_text(json.dumps([{"code": "lk-mp", "name": "[ЛК МП] Сервис подключения к ЛК МП"}],
                            ensure_ascii=False), encoding="utf-8")
    return c


def test_service_name_or_code_in_h1_warned(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "service-vision.md", "---\nid: VIS-001\ntype: vision\nservice: lk-mp\n---\n\n"
      "# Концепция сервиса (Service Vision): lk-mp\n")
    w(docs / "srs/process/README.md", "---\nid: PROC-000\ntype: process\nservice: lk-mp\n---\n\n"
      "# Процессы — Сервис подключения к ЛК МП\n")
    rep = sc.check_h1_service(docs, _cat(tmp_path))
    assert rep and "файлов 2" in rep[0], rep


def test_name_inside_quotes_root_readme_domain_glossary_silent(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "README.md", "---\nid: X\ntype: readme\nservice: lk-mp\n---\n\n# Сервис подключения к ЛК МП\n")
    w(docs / "srs/scr.md", "---\nid: SCR-CL-08\ntype: screen-form\nservice: lk-mp\n---\n\n"
      "# ЭФ Клиента «Посадочная страница \"Сервис подключения к ЛК МП\"»\n")
    w(docs / "glossary.md", "---\nid: GLO-000\ntype: glossary\ndomain: cards\nservice: lk-mp\n---\n\n"
      "# Глоссарий домена lk-mp\n")
    w(docs / "srs/f.md", "---\nid: FUN-CL-01\ntype: function\nservice: lk-mp\n---\n\n# Функция просмотра\n")
    assert sc.check_h1_service(docs, _cat(tmp_path)) == []


def test_without_catalog_code_only(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "glossary.md", "---\nid: GLO-001\ntype: glossary\nservice: lk-mp\n---\n\n"
      "# Глоссарий (lk-mp)\n")
    rep = sc.check_h1_service(docs, None)
    assert rep and "glossary.md" in rep[1], rep
