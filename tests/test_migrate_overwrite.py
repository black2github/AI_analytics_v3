# tests/test_migrate_overwrite.py
#
# Часть A гибрида: при коллизии имён файл ПЕРЕЗАПИСЫВАЕТСЯ с предупреждением
# (а не молча пропускается). Миграция разовая, далее работа по ФС под git —
# перезапись безопасна. См. app/scripts/CI/analysis-naming-strategies.md.

import app.config as cfg
import app.scripts.migrate_confluence_tree as mig


def _page_data():
    return {
        "approved_content": "# Новое\nновый текст",
        "full_content": "# Новое\nновый текст",
        "requirement_type": "function",
    }


def test_overwrites_existing_file_and_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MIGRATE_IMAGES", False)
    fp = tmp_path / "Страница.md"
    fp.write_text("СТАРОЕ СОДЕРЖИМОЕ", encoding="utf-8")

    stats = {"migrated": 0, "skipped": 0, "overwritten": 0}
    ok = mig.save_page_file(
        _page_data(), "123", "Страница", "CC", "SRC", fp, stats, {}, {}
    )

    assert ok is True
    assert stats == {"migrated": 1, "skipped": 0, "overwritten": 1}
    text = fp.read_text(encoding="utf-8")
    assert "СТАРОЕ СОДЕРЖИМОЕ" not in text
    assert "новый текст" in text


def test_fresh_file_not_counted_as_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MIGRATE_IMAGES", False)
    fp = tmp_path / "Новая.md"  # файла ещё нет

    stats = {"migrated": 0, "skipped": 0, "overwritten": 0}
    ok = mig.save_page_file(
        _page_data(), "456", "Новая", "CC", "SRC", fp, stats, {}, {}
    )

    assert ok is True
    assert stats == {"migrated": 1, "skipped": 0, "overwritten": 0}


def test_registry_points_to_overwritten_file(tmp_path, monkeypatch):
    # Коллизия по заголовку: последний победил — реестры указывают на актуальный файл.
    monkeypatch.setattr(cfg, "MIGRATE_IMAGES", False)
    fp = tmp_path / "Дубль.md"
    fp.write_text("первое", encoding="utf-8")

    page_registry, title_registry = {}, {}
    stats = {"migrated": 0, "skipped": 0, "overwritten": 0}
    mig.save_page_file(
        _page_data(), "789", "Дубль", "CC", "SRC", fp, stats,
        page_registry, title_registry,
    )

    assert page_registry["789"] == fp
    assert title_registry[mig._title_key("Дубль")] == fp
