# tests/test_layer_marks.py
"""Пометка слоя в утилитах прибора: модуль миграционного слоя несёт второй строкой
файла (сразу под строкой с путём) комментарий «# Слой: миграция»; ядро пометки не несёт.

Дом перечня — таблица «Слои прибора» в `_meta/tools/README.md` канона; новая утилита
миграционного слоя добавляется в оба места одним изменением. README канона в
репозитории прибора нет, поэтому список здесь явный."""
from pathlib import Path

import pytest

CI = Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"
MARK = "# Слой: миграция"

# модули миграционного слоя (пути от app/scripts/CI)
MIGRATION = (
    "source_inventory.py",
    "source_coverage.py",
    "normalize_tables.py",
    "raw_oracle.py",
    "kitcheck/checks/source_profile.py",
)


def _lines(rel: str):
    return (CI / rel).read_text(encoding="utf-8").splitlines()


def _all_modules():
    files = list(CI.glob("*.py")) + list(CI.glob("kitcheck/*.py")) + list(CI.glob("kitcheck/checks/*.py"))
    return sorted(p.relative_to(CI).as_posix() for p in files)


@pytest.mark.parametrize("rel", MIGRATION)
def test_migration_module_marked_on_second_line(rel):
    lines = _lines(rel)
    assert lines[0] == f"# app/scripts/CI/{rel}"
    assert lines[1].startswith(MARK), f"{rel}: второй строкой нет «{MARK}»"


def test_core_modules_not_marked():
    # асимметрия: лишняя пометка на ядре — тоже расхождение с таблицей README канона
    marked = [rel for rel in _all_modules()
              if rel not in MIGRATION and "Слой: миграция" in (CI / rel).read_text(encoding="utf-8")]
    assert marked == []


def test_migration_list_points_to_existing_files():
    assert [rel for rel in MIGRATION if not (CI / rel).is_file()] == []
