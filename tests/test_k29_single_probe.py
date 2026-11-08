# -*- coding: utf-8 -*-
"""К-29 (check_heavy_cells): ✗ только при двух пробах и больше в ОДНОЙ |-строке
карточки или при пробе в строке без содержимого ячейки вне таблиц; одна проба
при содержимом вне таблиц — i-строка (замечание 2026-11-08: ложный ✗ на
EXTINT-SVFE-002, проба — имя метода из правила §2)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.scripts.CI.kitcheck.checks.card_passport import check_heavy_cells
from app.scripts.CI.kitcheck.html import html_fragment_to_markdown

_CELL = ("<ul><li>ЭКО_Получение данных одной корпоративной карты</li>"
         "<li>ЭКО_Получение списка корпоративных карт</li>"
         "<li>[КК_СК] Клиент: Функция получения информации по картам клиента "
         "для отображения в списке карт и в карточке</li></ul>")
_SRC = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
        "<td><strong>Где используется</strong></td>"
        "<td>" + _CELL + "</td></tr></tbody></table>\n")
_EXPANDED = html_fragment_to_markdown(_CELL)
_FLAT = _EXPANDED.replace("\n", " ").replace("- ", "")


def _ok(card):
    return check_heavy_cells(card, _SRC)


def test_one_probe_in_row_content_outside_is_info():
    # совпадение начала ячейки с правилом заполнения §2 (имя метода), содержимое
    # ячейки раскрыто вне таблиц — не расплющивание
    card = ("| Параметр | Правила заполнения |\n|---|---|\n"
            "| `data.type` | Как в методе ЭКО_Получение данных одной корпоративной карты |\n\n"
            "**Где используется**\n\n" + _EXPANDED + "\n")
    rep, ok = _ok(card)
    assert ok, rep
    assert any(r.startswith("i К-29") for r in rep), rep


def test_probes_in_different_rows_content_outside_is_info():
    card = ("| A | ЭКО_Получение данных одной корпоративной карты |\n"
            "| B | карты ЭКО_Получение списка корпоративных карт [кк |\n\n"
            + _EXPANDED + "\n")
    rep, ok = _ok(card)
    assert ok, rep


def test_collapsed_row_flagged_even_with_copy_outside():
    # НЕсрабатывание послабления: две пробы и больше в одной строке — коллапс
    card = f"| Где используется | {_FLAT} |\n\n" + _EXPANDED + "\n"
    rep, ok = _ok(card)
    assert not ok and any("расплющена" in r for r in rep), rep


def test_collapsed_row_flagged():
    card = f"| Где используется | {_FLAT} |\n"
    rep, ok = _ok(card)
    assert not ok and any("расплющена" in r for r in rep), rep


def test_one_probe_in_row_without_content_outside_flagged():
    # НЕсрабатывание послабления: проба в строке, вне таблиц содержимого нет
    card = ("| Параметр | Правила заполнения |\n|---|---|\n"
            "| `data.type` | ЭКО_Получение данных одной корпоративной карты |\n")
    rep, ok = _ok(card)
    assert not ok and any("расплющена" in r for r in rep), rep


def test_clean_card_silent():
    card = "| Поле | Значение |\n|---|---|\n| Alias | /x |\n\n" + _EXPANDED + "\n"
    rep, ok = _ok(card)
    assert ok and not rep, rep


_PASSPORT = f"| Поле | Значение |\n|---|---|\n| Внешняя система | ПЦ |\n| Где используется | {_FLAT} |\n"


def test_passport_row_of_base_contract_is_info():
    """Базовый контракт: тяжёлая ячейка паспорта законно остаётся строкой таблицы «лейбл | значение»."""
    rep, ok = check_heavy_cells(_PASSPORT, _SRC, passport_rows_ok=True)
    assert ok, rep
    assert any(r.startswith("i тяжёлая ячейка паспорта перенесена строкой: 1") for r in rep), rep


def test_passport_row_other_types_still_flagged():
    # НЕсрабатывание послабления: без признака базового контракта — прежний ✗
    rep, ok = check_heavy_cells(_PASSPORT, _SRC)
    assert not ok and any("расплющена" in r for r in rep), rep


def test_parameter_table_of_base_contract_still_flagged():
    # НЕсрабатывание послабления: таблица параметров (три колонки и больше) — ✗ и у базового контракта
    card = f"| Код | Наименование | Правила заполнения |\n|---|---|---|\n| `x` | X | {_FLAT} |\n"
    rep, ok = check_heavy_cells(card, _SRC, passport_rows_ok=True)
    assert not ok and any("расплющена" in r for r in rep), rep


# живой случай: EXTINT-SVFE-002 до переделки (docs-external-contracts 89f6530) против
# страницы-источника из выгрузки КК (src-business-cards d2e3902a); без клонов — skip
_EXTC = Path(os.environ.get("EXTC_ROOT", r"C:\doc-as-code\EAN\docs-external-contracts"))
_KK = Path(os.environ.get("KK_ROOT", r"C:\doc-as-code\EAS\src-business-cards"))
_CARD = "89f6530:svfe/extint-svfe-002-card-info.md"
_PAGE = ("d2e3902a:sources/confluence/[КК]-Корпоративные-Карты/[КК]-Общая-часть-сервиса-КК/"
         "[КК]-Интеграции/[КК]-ПЦ-SVFE/ПЦ-SVFE_СИП_Получение-детальной-информации-по-карте.md")


def _git_show(repo: Path, spec: str):
    if not (repo / ".git").exists():
        return None
    r = subprocess.run(["git", "-C", str(repo), "show", spec], capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def test_live_svfe_002_method_name_probe_not_flagged():
    card, page = _git_show(_EXTC, _CARD), _git_show(_KK, _PAGE)
    if card is None or page is None:
        pytest.skip("нет клона docs-external-contracts (89f6530) или src-business-cards (d2e3902a)")
    rep, ok = check_heavy_cells(card, page, passport_rows_ok=True)
    assert ok, rep
    assert any(r.startswith("i К-29") and "эко_получение данных одной корпоративной" in r for r in rep), rep


def test_live_svfe_002_redone_no_k29_through_cli(tmp_path):
    """Переделанная SVFE-002 (b66d1e1): «Протокол взаимодействия» строкой §1 — i, ✗ К-29 нет.
    Через normalize_tables --check: признак базового контракта берётся из шапки карточки."""
    card = _git_show(_EXTC, "b66d1e1:svfe/extint-svfe-002-card-info.md")
    page = _git_show(_KK, _PAGE)
    if card is None or page is None:
        pytest.skip("нет клона docs-external-contracts (b66d1e1) или src-business-cards (d2e3902a)")
    c, s = tmp_path / "extint-svfe-002-card-info.md", tmp_path / "page.md"
    c.write_text(card, encoding="utf-8")
    s.write_text(page, encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, str(root / "app/scripts/CI/normalize_tables.py"), "--check", str(c),
                        "--source", str(s)], capture_output=True, cwd=str(root),
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = (r.stdout + r.stderr).decode("utf-8")   # отчёт --check идёт в stderr
    assert "i тяжёлая ячейка паспорта перенесена строкой" in out, out
    assert "расплющена" not in out, out
