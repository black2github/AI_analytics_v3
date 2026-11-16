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


# --- норма aebd488 (16.11.2026): точка вызова; правила «а» и «б» ---

def test_attribute_table_link_is_not_a_step_when_steps_section_exists(tmp_path):
    # правило «а»: ссылка на данные вызова в таблице заполнения атрибутов пары не образует
    docs = tmp_path / "docs"
    w(docs / "srs/process/proc-001-a.md", fm("PROC-001", "process")
      + "## Шаги процесса\n\n| № | Шаг | Содержание |\n|---|---|---|\n| 1 | Сохранить | т |\n\n"
        "## Логика заполнения атрибутов\n\n| № п/п | Наименование реквизита | Логика заполнения |\n"
        "|---|---|---|\n| 5.9 | Признак | **Если** [CALL-EXT-001 Данные](../contract-call/external/c1.md)"
        ".«Исходящие параметры».«Признак» == TRUE, **то** 1 |\n")
    call(docs, "CALL-EXT-001", "c1.md", "| [FUN-SYS-01 Ф](../../function/f.md) | Шаг 3 | т |\n")
    w(docs / "srs/function/f.md", fm("FUN-SYS-01", "function"))
    assert sc.check_process_call_consistency(docs) == []


def test_step_in_steps_section_still_requires_back(tmp_path):
    # шаг раздела шагов, который сам вызывает, — пара есть, обратной нет — предупреждение
    docs = tmp_path / "docs"
    proc(docs, "| 1 | Запрос | Вызов [CALL-EXT-001 Данные](../contract-call/external/c1.md) |\n")
    call(docs, "CALL-EXT-001", "c1.md", "| [FUN-SYS-01 Ф](../../function/f.md) | Шаг 3 | т |\n")
    w(docs / "srs/function/f.md", fm("FUN-SYS-01", "function"))
    rep = sc.check_process_call_consistency(docs)
    assert rep and "нет обратной: PROC-001 шаг 1 → CALL-EXT-001" in rep[1], rep


def test_process_without_steps_section_whole_document(tmp_path):
    # запасной путь: раздела «Шаги процесса» нет — пара считается по всему документу, как прежде
    docs = tmp_path / "docs"
    w(docs / "srs/process/proc-001-a.md", fm("PROC-001", "process")
      + "## Основной сценарий\n\n| № | Шаг | Содержание |\n|---|---|---|\n"
        "| 2 | Запрос | Вызов [CALL-EXT-001 Данные](../contract-call/external/c1.md) |\n")
    call(docs, "CALL-EXT-001", "c1.md", "| [FUN-SYS-01 Ф](../../function/f.md) | Шаг 3 | т |\n")
    w(docs / "srs/function/f.md", fm("FUN-SYS-01", "function"))
    rep = sc.check_process_call_consistency(docs)
    assert rep and "нет обратной: PROC-001 шаг 2 → CALL-EXT-001" in rep[1], rep


def _call_list(docs: Path, cid: str, name: str, items: str) -> None:
    w(docs / f"srs/contract-call/internal/{name}", fm(cid, "contract-call")
      + "## Назначение\n\nт\n\n## Использование в сервисе «X»\n\n### Процессы\n\n" + items
      + "\n### Транспорт\n\nт\n\n### Правила заполнения исходящего сообщения\n\n"
        "Вызывается на шаге 9 в [PROC-001 А](../../process/proc-001-a.md).\n")


def test_back_from_list_pointer_matches_step(tmp_path):
    # правило «б»: обратная — пункт списка «- [PROC…] — шаг N» в «Процессах»
    docs = tmp_path / "docs"
    proc(docs, "| 5 | Проверить | Заполнение — в [CALL-INT-004 П](../contract-call/internal/c4.md) |\n")
    _call_list(docs, "CALL-INT-004", "c4.md", "- [PROC-001. А](../../process/proc-001-a.md) — шаг 5.\n")
    assert sc.check_process_call_consistency(docs) == []


def test_back_from_list_pointer_step_mismatch_and_other_subsection_ignored(tmp_path):
    # номер шага из пункта сверяется как из ячейки; проза «Правил заполнения» указателем не считается
    docs = tmp_path / "docs"
    proc(docs, "| 5 | Проверить | [CALL-INT-004 П](../contract-call/internal/c4.md) |\n")
    _call_list(docs, "CALL-INT-004", "c4.md", "- [PROC-001. А](../../process/proc-001-a.md) — шаг 7.\n")
    rep = sc.check_process_call_consistency(docs)
    assert rep and "расхождений 1" in rep[0] and "номер шага расходится: PROC-001 шаг 5 → CALL-INT-004" in rep[1], rep


def test_list_pointer_without_forward_link_warned(tmp_path):
    # место запуска в «Процессах» списком, процесс на карточку не ссылается — нет прямой
    docs = tmp_path / "docs"
    proc(docs, "| 1 | Запрос | т |\n")
    _call_list(docs, "CALL-INT-004", "c4.md", "- [PROC-001. А](../../process/proc-001-a.md) — шаг 1 (запуск).\n")
    rep = sc.check_process_call_consistency(docs)
    assert rep and "нет прямой: CALL-INT-004 → PROC-001" in rep[1], rep


def test_no_forward_line_names_both_exits_for_item_without_step(tmp_path):
    # пункт без номера шага: строка понятна без контекста и называет оба выхода
    docs = tmp_path / "docs"
    proc(docs, "| 1 | Запрос | т |\n")
    _call_list(docs, "CALL-INT-004", "c4.md", "- [PROC-001 Обработка ответа](../../process/proc-001-a.md);\n")
    rep = sc.check_process_call_consistency(docs)
    line = rep[1]
    assert "нет прямой: CALL-INT-004 → PROC-001 (место без номера шага)" in line, line
    assert "строка «Процессов» карточки называет процесс" in line and "на CALL-INT-004 не ссылаются" in line
    assert "убрать её из «Процессов»" in line and "добавить в шаг ссылку на карточку" in line
