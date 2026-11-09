# tests/test_k29_passport_rows_contracts.py
"""К-29 (2026-11-09, постановка «Точки расширения эталона», слово владельца): тяжёлая ячейка
паспорта остаётся строкой двухколоночной таблицы «лейбл | значение» не только у базового
контракта внешней АС (external-integration), но и у внутреннего контракта (internal-contract) и
карточки вызова (contract-call) — шаблон contract-call.md, раздел A, решение 2026-11-08. Тогда —
i-строка с типом; таблица из трёх колонок и больше — ✗, как прежде; другие типы — ✗, как прежде.
Признак — тип карточки в шапке (через normalize_tables --check, как в прогоне комплекта)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.scripts.CI.kitcheck.html import html_fragment_to_markdown

ROOT = Path(__file__).resolve().parents[1]
_CELL = ("<ul><li>ЭФ первого ввода ПИН-кода клиентом в виджете смены ПИН-кода</li>"
         "<li>ЭФ повторного ввода ПИН-кода клиентом в виджете смены ПИН-кода</li>"
         "<li>ЭФ результата смены ПИН-кода с сообщением об успехе или ошибке</li></ul>")
_SRC = ("---\ntitle: '[КК_Виджет_ПИН] Клиент: Скрипт отправки ПИН-кода'\nconfluence_page_id: '2227445624'\n---\n\n"
        "<table><tbody><tr><td><strong>Как вызывается</strong></td><td>" + _CELL + "</td></tr></tbody></table>\n")
_FLAT = html_fragment_to_markdown(_CELL).replace("\n", " ").replace("- ", "")
I_LINE = "i тяжёлая ячейка паспорта остаётся строкой двухколоночной таблицы: 1"


def _card(cid: str, ctype: str, body: str) -> str:
    return (f"---\nid: {cid}\ntitle: '[КК_Виджет_ПИН] Клиент: Скрипт отправки ПИН-кода'\ntype: {ctype}\n"
            f"service: business-cards\nconfluence_page_ids: [2227445624]\n---\n\n# {cid}. Скрипт отправки ПИН-кода\n\n"
            f"## 1. Краткое описание\n\n{body}")


_PASSPORT = f"| Поле | Значение |\n|---|---|\n| Как вызывается | {_FLAT} |\n"
_PARAMS = f"| Параметр | Тип | Правила заполнения |\n|---|---|---|\n| `pin` | string | {_FLAT} |\n"


def _check(tmp_path: Path, name: str, text: str) -> str:
    c, s = tmp_path / name, tmp_path / "page.md"
    c.write_text(text, encoding="utf-8")
    s.write_text(_SRC, encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "app/scripts/CI/normalize_tables.py"), "--check", str(c),
                        "--source", str(s)], capture_output=True, cwd=str(ROOT),
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return (r.stdout + r.stderr).decode("utf-8")


@pytest.mark.parametrize("cid,ctype", [("INTC-015", "internal-contract"), ("CALL-INT-001", "contract-call"),
                                       ("EXTINT-SVFE-002", "external-integration")])
def test_passport_row_of_contract_is_info_with_type(tmp_path, cid, ctype):
    out = _check(tmp_path, f"{cid.lower()}.md", _card(cid, ctype, _PASSPORT))
    assert I_LINE in out and f"контур A шаблона contract-call; тип {ctype}" in out, out
    assert "расплющена" not in out, out


def test_parameter_table_of_internal_contract_still_flagged(tmp_path):
    """НЕсрабатывание: та же ячейка в таблице §2 из трёх колонок — ✗ и у внутреннего контракта."""
    out = _check(tmp_path, "intc-015.md", _card("INTC-015", "internal-contract", _PARAMS))
    assert "расплющена" in out and I_LINE not in out, out


def test_function_with_same_row_still_flagged(tmp_path):
    """НЕсрабатывание: исключение не расползается на другие типы — функция с той же строкой — ✗."""
    out = _check(tmp_path, "fun-cl-99.md", _card("FUN-CL-99", "function", _PASSPORT))
    assert "расплющена" in out and I_LINE not in out, out


def _group(tmp_path: Path, files):
    from app.scripts.CI.kitcheck.checks.card_run import run_check
    paths = []
    for name, text in files:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    s = tmp_path / "page.md"
    s.write_text(_SRC, encoding="utf-8")
    rep, _ok = run_check(paths, s)
    return "\n".join(rep)


def test_group_with_function_main_row_in_intc_passport_is_info(tmp_path):
    """КК С3: группа страницы «Скрипт отправки ПИН-кода» — главная FUN-CL-62 (function), строка
    «Как вызывается» стоит в паспорте INTC-015 — законна по типу своей карточки: i с типом."""
    out = _group(tmp_path, [("fun-cl-62.md", _card("FUN-CL-62", "function", "Функция.\n")),
                            ("intc-015.md", _card("INTC-015", "internal-contract", _PASSPORT))])
    assert I_LINE in out and "тип internal-contract" in out, out
    assert "расплющена" not in out, out


def test_group_with_function_main_row_in_function_still_flagged(tmp_path):
    """НЕсрабатывание: та же строка в паспорте самой функции группы — ✗, хотя в группе есть INTC."""
    out = _group(tmp_path, [("fun-cl-62.md", _card("FUN-CL-62", "function", _PASSPORT)),
                            ("intc-015.md", _card("INTC-015", "internal-contract", "Контракт.\n"))])
    assert "расплющена" in out and I_LINE not in out, out
