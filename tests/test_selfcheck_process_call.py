# tests/test_selfcheck_process_call.py
"""Пакет 2, задача 8 (ЗК-13): согласованность «шаг процесса ↔ карточка вызова»."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fm(i: str, t: str) -> str:
    return f"---\nid: {i}\ntype: {t}\nservice: x\n---\n\n# {i}\n\n"


def proc(docs: Path, rows: str) -> None:
    w(docs / "srs/process/proc-001-a.md", fm("PROC-001", "process")
      + "## Шаги процесса\n\n| № | Шаг | Содержание |\n|---|---|---|\n" + rows)


def call(docs: Path, cid: str, name: str, rows: str) -> None:
    w(docs / f"srs/contract-call/external/{name}", fm(cid, "contract-call")
      + "## Назначение\n\nт\n\n## Использование в сервисе «X»\n\n### Процессы\n\n"
        "| Процесс / функция | Шаг / место | Описание |\n|---|---|---|\n" + rows
      + "\n### Транспорт\n\nт\n")


def test_consistent_pairs_with_range_and_function_rows_silent(tmp_path):
    docs = tmp_path / "docs"
    proc(docs, "| 1.5 | Запрос | Вызов [CALL-EXT-001 Данные](../contract-call/external/c1.md) |\n"
               "| 2 | Ответ | т |\n")
    call(docs, "CALL-EXT-001", "c1.md",
         "| [PROC-001 А](../../process/proc-001-a.md) | Шаг 1.4–1.6 | т |\n"
         "| [FUN-SYS-01 Ф](../../function/f.md) | Шаг 3 | т |\n")
    w(docs / "srs/function/f.md", fm("FUN-SYS-01", "function"))
    assert sc.check_process_call_consistency(docs) == []


def test_missing_back_and_forward_link_warned(tmp_path):
    docs = tmp_path / "docs"
    proc(docs, "| 1 | Запрос | [CALL-EXT-001 Данные](../contract-call/external/c1.md) |\n"
               "| 2 | Ответ | т |\n")
    call(docs, "CALL-EXT-001", "c1.md", "| — | — | т |\n")
    call(docs, "CALL-EXT-002", "c2.md", "| [PROC-001 А](../../process/proc-001-a.md) | Шаг 2 | т |\n")
    rep = sc.check_process_call_consistency(docs)
    assert rep and "расхождений 2" in rep[0], rep
    assert any("нет обратной: PROC-001 шаг 1 → CALL-EXT-001" in x for x in rep), rep
    assert any("нет прямой: CALL-EXT-002 → PROC-001" in x for x in rep), rep


def test_step_number_mismatch_warned(tmp_path):
    docs = tmp_path / "docs"
    proc(docs, "| **3** | Запрос | [CALL-INT-001 Метод](../contract-call/external/c1.md) |\n")
    call(docs, "CALL-INT-001", "c1.md", "| [PROC-001 А](../../process/proc-001-a.md) | Шаг 4 | т |\n")
    rep = sc.check_process_call_consistency(docs)
    assert rep and "номер шага расходится: PROC-001 шаг 3 → CALL-INT-001" in rep[1], rep
