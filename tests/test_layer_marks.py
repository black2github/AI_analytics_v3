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
    "kitcheck/checks/card_deviation.py",
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


# проверки ядра, слой которых записан явно строкой таблицы «Слои прибора» README канона: пометки
# не несут, без выгрузки работают полностью
CORE_EXPLICIT = (
    "kitcheck/checks/call_algorithms.py",  # сторож «в карточке вызова нет алгоритмов», 11.11
    "kitcheck/checks/call_contract_props.py",  # сторож свойств контракта и кодов параметров, 13.11
    "kitcheck/checks/intc_algorithms.py",  # сторож «в карточке внутреннего контракта нет алгоритма», 13.11
    "kitcheck/checks/method_function_contour.py",  # сторож контура функции метода, 14.11
)


@pytest.mark.parametrize("rel", CORE_EXPLICIT)
def test_core_check_explicit_not_marked(rel):
    assert (CI / rel).is_file() and rel not in MIGRATION
    lines = _lines(rel)
    assert lines[0] == f"# app/scripts/CI/{rel}"
    assert not any("Слой: миграция" in ln for ln in lines)


def test_migration_list_points_to_existing_files():
    assert [rel for rel in MIGRATION if not (CI / rel).is_file()] == []


def test_own_debts_check_marked_pipeline_layer():
    # проверка внутри смешанного модуля: пометка у раздела проверки, не второй строкой файла;
    # строка таблицы «Слои прибора» — в README канона
    text = (CI / "transfer_gate.py").read_text(encoding="utf-8")
    mark = text.index("# Слой проверки: конвейер")
    assert text.rindex("# --- долги на собственный заход", 0, mark) < mark < text.index("def check_own_debts")
