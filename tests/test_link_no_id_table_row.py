# tests/test_link_no_id_table_row.py
"""Пакет П3 ОНБ-В, п. 5 (решение владельца 2026-11-09): ссылка на карточку без ID в подписи,
стоящая в строке таблицы, где ID того же типа есть в другой ячейке той же строки, — «ID +
название», не сигнал (оглавления SCR-CL-07 / SCR-CL-28 КК: `| SCR-CL-01 | [файл](…) | название |`).
Строка таблицы без ID этого типа, ссылка вне таблицы и ID другого типа в строке — по-прежнему ⚠."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.links import check_link_anchors_and_ids

CARD = "---\nid: {id}\ntitle: '{t}'\ntype: {type}\nservice: t\n---\n\n# {id}. {t}\n\nтекст\n"


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def kit(tmp_path: Path, body: str) -> Path:
    docs = tmp_path / "docs"
    make(docs / "srs/screen-form/client/scr-cl-01-main.md",
         CARD.format(id="SCR-CL-01", t="Список", type="screen-form"))
    make(docs / "srs/contract-call/external/call-ext-001-x.md",
         CARD.format(id="CALL-EXT-001", t="Вызов", type="contract-call"))
    make(docs / "srs/screen-form/client/scr-cl-07-index.md",
         CARD.format(id="SCR-CL-07", t="Индекс", type="screen-form") + "\n" + body)
    return docs


def no_id_lines(docs: Path):
    out = check_link_anchors_and_ids(docs)
    return [x for x in out if x.startswith("   ") and "scr-cl-07-index.md" in x]


HEAD = "| ID | Файл | Экранная форма |\n|----|------|----------------|\n"


def test_row_with_scr_id_in_neighbor_cell_silent(tmp_path):
    docs = kit(tmp_path, HEAD + "| SCR-CL-01 | [`scr-cl-01-main.md`](scr-cl-01-main.md) | Список |\n")
    assert no_id_lines(docs) == []


def test_row_without_id_still_signals(tmp_path):
    """НЕсрабатывание исключения: строка таблицы без ID ни в одной ячейке — ⚠ как прежде."""
    docs = kit(tmp_path, HEAD + "| — | [`scr-cl-01-main.md`](scr-cl-01-main.md) | Список |\n")
    assert len(no_id_lines(docs)) == 1


def test_row_with_other_type_id_still_signals(tmp_path):
    """ID другого типа в строке (CALL рядом со ссылкой на ЭФ) связку «ID + название» не даёт."""
    docs = kit(tmp_path, HEAD + "| CALL-EXT-001 | [`scr-cl-01-main.md`](scr-cl-01-main.md) | Список |\n")
    assert len(no_id_lines(docs)) == 1


def test_link_outside_table_still_signals(tmp_path):
    docs = kit(tmp_path, "Переход на [список](scr-cl-01-main.md) — см. SCR-CL-01.\n")
    assert len(no_id_lines(docs)) == 1


def test_call_row_with_call_id_silent(tmp_path):
    docs = kit(tmp_path, "| Вызов | Карточка |\n|---|---|\n"
                         "| CALL-EXT-001 | [Вызов](../../contract-call/external/call-ext-001-x.md) |\n")
    assert no_id_lines(docs) == []


def test_call_row_without_id_signals(tmp_path):
    docs = kit(tmp_path, "| Вызов | Карточка |\n|---|---|\n"
                         "| вызов | [Вызов](../../contract-call/external/call-ext-001-x.md) |\n")
    assert len(no_id_lines(docs)) == 1


def test_id_in_same_cell_still_signals(tmp_path):
    """НЕсрабатывание исключения: ID того же типа в ТОЙ ЖЕ ячейке, что и ссылка (ячейка шага
    процесса с текстом, КК proc-018 шаг 6), — не строка оглавления, ⚠ как прежде."""
    docs = kit(tmp_path, "| № | Шаг | Описание |\n|---|---|---|\n"
                         "| 6 | Сохранить | Если нет ошибки (параметр [Исходящие параметры]"
                         "(../../contract-call/external/call-ext-001-x.md)) — вызов CALL-EXT-001 |\n")
    assert len(no_id_lines(docs)) == 1
