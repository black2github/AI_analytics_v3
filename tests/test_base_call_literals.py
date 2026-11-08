# -*- coding: utf-8 -*-
"""normalize_tables.py --check --call: у базового контракта литерал источника, вынесенный в
карточку вызова потребителя по правилу границы (шаблон contract-call.md, раздел A), найден в
переданной карточке — i-строка, не ✗; без ключа — ✗ как прежде (решение 2026-11-08, опись
наследия f1: EXTINT-F1-029 «Филиалы и подразделения» → CALL-EXT-006)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ("---\ntitle: 'РКО Ф1. Представление \"Корп. карты Клиента\"'\n---\n\n"
       "<p>Представление содержит карты клиента. Поле PODR может быть использовано для связи с записью "
       "в справочнике \"Филиалы и подразделения\" Эко.</p>\n")
BASE = ("---\nid: EXTINT-F1-029\ntitle: 'РКО Ф1. Представление \"Корп. карты Клиента\"'\ntype: {typ}\n"
        "kind: operation\nchannel: db\n---\n\n# EXTINT-F1-029. РКО Ф1. Представление «Корп. карты Клиента»\n\n"
        "Представление содержит карты клиента. Поле PODR — код подразделения.\n")
CALL = ("---\nid: CALL-EXT-006\ntitle: 'РКО Ф1. Представление \"Корп. карты Клиента\"'\ntype: contract-call\n---\n\n"
        "# CALL-EXT-006\n\nPODR используется для связи с записью в справочнике «Филиалы и подразделения» Эко.\n")


def run(tmp_path, typ="external-integration", with_call=True):
    card = tmp_path / "extint-f1-029.md"
    card.write_text(BASE.format(typ=typ), encoding="utf-8")
    src = tmp_path / "src.md"
    src.write_text(SRC, encoding="utf-8")
    call = tmp_path / "call-ext-006.md"
    call.write_text(CALL, encoding="utf-8")
    argv = [sys.executable, str(ROOT / "app/scripts/CI/normalize_tables.py"), "--check", str(card), "--source", str(src)]
    if with_call:
        argv += ["--call", str(call)]
    r = subprocess.run(argv, capture_output=True, cwd=str(ROOT), env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return (r.stdout + r.stderr).decode("utf-8"), r.returncode


def test_literal_found_in_call_card_is_info(tmp_path):
    out, code = run(tmp_path)
    assert "i кавычечные литералы: вынесено в карточку вызова: 1 (call-ext-006.md): 'Филиалы и подразделения'" in out, out
    assert "в карточке отсутствуют" not in out, out


def test_without_call_still_flagged(tmp_path):
    # НЕсрабатывание: без --call — ✗ как прежде
    out, code = run(tmp_path, with_call=False)
    assert "кавычечные литералы источника: в карточке отсутствуют 1" in out and code == 2, out


def test_call_not_applied_to_other_types(tmp_path):
    # НЕсрабатывание: --call учитывается только у базового контракта
    out, code = run(tmp_path, typ="function")
    assert "i --call: карточки вызова учитываются только у базового контракта" in out, out
    assert "кавычечные литералы источника: в карточке отсутствуют 1" in out, out


def test_call_line_visible_on_green_card():
    from app.scripts.CI.kitcheck.core import is_soft_signal
    assert is_soft_signal("i кавычечные литералы: вынесено в карточку вызова: 1 (call-ext-006.md): 'X'")


def test_literal_absent_in_call_card_flagged(tmp_path):
    # НЕсрабатывание: в переданной карточке вызова литерала нет — ✗
    card = tmp_path / "extint-f1-029.md"
    card.write_text(BASE.format(typ="external-integration"), encoding="utf-8")
    (tmp_path / "src.md").write_text(SRC, encoding="utf-8")
    call = tmp_path / "call-other.md"
    call.write_text("# CALL-EXT-999\n\nДругой текст.\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "app/scripts/CI/normalize_tables.py"), "--check", str(card),
                        "--source", str(tmp_path / "src.md"), "--call", str(call)],
                       capture_output=True, cwd=str(ROOT), env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = (r.stdout + r.stderr).decode("utf-8")
    assert "в карточке отсутствуют 1" in out and "вынесено в карточку вызова" not in out, out
