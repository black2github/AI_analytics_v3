# tests/test_migrate_tasks.py
#
# Консолидация: режим --tasks (CriticMarkup) в migrate_confluence_tree. Проверяет, что
# save_page_file в критик-режиме пишет .md с маркерами через штатный путь (frontmatter,
# картинки, ссылки — как у approved/all) и наполняет аккумулятор манифеста/отчёта.

import app.config as cfg
import app.scripts.migrate_confluence_tree as mig
from app.scripts.migrate_colors import new_accumulator, finalize


def _history(color: str, jira: str) -> str:
    return ('<table><thead><tr><th>Дата</th><th>Описание</th><th>Автор</th>'
            '<th>Задача в JIRA</th></tr></thead><tbody>'
            '<tr><td><time datetime="2025-01-01">01.01.2025</time></td>'
            f'<td><span style="color: {color}">описание</span></td>'
            f'<td>автор</td><td>{jira}</td></tr></tbody></table>')


def _page(raw_html: str) -> dict:
    # full != approved → has_unapproved=True (на странице есть цветное)
    return {"raw_html": raw_html, "requirement_type": "function",
            "full_content": "ПОЛНОЕ", "approved_content": "ПОДТВЕРЖДЁННОЕ"}


def test_tasks_mode_writes_markers_and_fills_report(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MIGRATE_IMAGES", False)
    raw = (_history("rgb(255,153,204)", "GBO-1") +
           '<p>Текст <span style="color: rgb(255,153,204)">правка</span>.</p>')
    acc = new_accumulator()
    stats = {"migrated": 0, "skipped": 0, "overwritten": 0}
    fp = tmp_path / "Страница.md"

    ok = mig.save_page_file(
        _page(raw), "123", "Страница", "CC", "SRC", fp, stats, {}, {},
        critic=True, critic_acc=acc,
    )
    assert ok is True

    md = fp.read_text(encoding="utf-8")
    assert md.startswith("---")                    # полноценный frontmatter, как у approved/all
    assert "{++GBO-1: правка++}" in md             # маркер задачи в теле
    assert "История изменений" not in md           # секция истории удалена (в тело не попала)

    # Аккумулятор наполнен → finalize даёт манифест с задачей и корректную статистику.
    manifest, report = finalize(acc, "CC", "2026-08-15")
    assert "GBO-1" in manifest["tasks"]
    assert manifest["tasks"]["GBO-1"]["markers"] >= 1
    assert report["stats"]["pages_processed"] == 1


def test_approved_mode_unchanged_by_default(tmp_path, monkeypatch):
    # Без critic=True поведение прежнее: пишется approved_content, маркеров нет.
    monkeypatch.setattr(cfg, "MIGRATE_IMAGES", False)
    stats = {"migrated": 0, "skipped": 0, "overwritten": 0}
    fp = tmp_path / "Обычная.md"
    page = {"raw_html": "<p>x</p>", "requirement_type": "function",
            "full_content": "# T\nполное", "approved_content": "# T\nтолько подтверждённое"}

    ok = mig.save_page_file(page, "456", "Обычная", "CC", "SRC", fp, stats, {}, {})
    assert ok is True
    md = fp.read_text(encoding="utf-8")
    assert "только подтверждённое" in md
    assert "{++" not in md and 'class="critic-' not in md
