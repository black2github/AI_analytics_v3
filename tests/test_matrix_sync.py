# tests/test_matrix_sync.py
"""Пакет 2, задача 10, шаг 2: matrix_sync — выводимые разделы матрицы
трассировки сверяются с телами документов (--check)."""
from pathlib import Path

from app.scripts.CI import matrix_sync as ms


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fm(i: str, t: str, title: str, extra: str = "") -> str:
    return f"---\nid: {i}\ntype: {t}\ntitle: '{title}'\nservice: x\n{extra}---\n\n# {title}\n\n"


REGISTRY = """| ID | Название | Файл |
| --- | --- | --- |
| CTL-000 | Контроли | `srs/control/README.md` |
| CTL-GRP-1 | Группа сохранения | `srs/control/README.md` |
| ENT-001 | Заявка | `srs/data-model/ent-001.md` |
| FUN-CL-01 | Сохранение | `srs/function/fun-cl-01.md` |
| PROC-001 | Обработка | `srs/process/proc-001.md` |
| SCR-CL-01 | Форма | `srs/screen-form/scr-cl-01.md` |
| SCR-CL-05 | снят 2026-08-30: тип изменён, преемник FUN-CL-01 | — |
| SCR-CL-09 | Будущая форма | — |
"""


def kit(tmp_path: Path, fun_extra: str = "", registry: str = REGISTRY,
        fun_row: str = "| FUN-CL-01 | Сохранение | SCR-CL-01 | ENT-001 | CTL-GRP-1 | — |") -> Path:
    docs = tmp_path / "docs"
    w(docs / "srs/control/README.md", fm("CTL-000", "control", "Контроли")
      + "## Группы контролей\n\n| ID | Суть |\n|---|---|\n"
        "| CTL-GRP-1 | Группа сохранения — [FUN-CL-01](../function/fun-cl-01.md) |\n")
    w(docs / "srs/data-model/ent-001.md", fm("ENT-001", "data-model", "Заявка"))
    w(docs / "srs/function/fun-cl-01.md", fm("FUN-CL-01", "function", "Сохранение")
      + "## Поведение\n\nПишет [ENT-001 Заявка](../data-model/ent-001.md).\n" + fun_extra)
    w(docs / "srs/screen-form/scr-cl-01.md", fm("SCR-CL-01", "screen-form", "Форма",
                                                "confluence_page_ids: ['2166860001']\n")
      + "## Реестр полей\n\n| ID | Поле |\n|---|---|\n| FLD-1 | Номер |\n\n"
        "Кнопка вызывает [FUN-CL-01](../function/fun-cl-01.md).\n")
    w(docs / "srs/process/proc-001.md", fm("PROC-001", "process", "Обработка")
      + "## Шаги\n\n| № | Шаг |\n|---|---|\n| 1 | [FUN-CL-01](../function/fun-cl-01.md) |\n")
    w(docs / "traceability-matrix.md", "# Матрица трассировки\n\n"
      "## Реестр ID\n\n" + registry + "\n"
      "## Покрытие: функции → артефакты\n\n"
      "| Функция | Название | Экраны | Данные | Контроли | Печатные формы |\n"
      "| --- | --- | --- | --- | --- | --- |\n" + fun_row + "\n\n"
      "## Покрытие: процессы → артефакты\n\n"
      "| Процесс | Название | Вызывает | Функции | Вызовы | Экраны | Контроли | Данные | Печатные формы |\n"
      "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
      "| PROC-001 | Обработка | — | FUN-CL-01 | — | — | — | — | — |\n\n"
      "## Покрытие: API ↔ SRS\n\n| Операция | Артефакты SRS |\n| --- | --- |\n\n"
      "## Источники миграции\n\n| Page ID | Целевые артефакты | Основание |\n| --- | --- | --- |\n"
      "| 2166860001 | SCR-CL-01 | — |\n\n"
      "## Долги по ссылкам\n\n| Артефакт | Цель | Причина |\n| --- | --- | --- |\n")
    return docs


def test_consistent_matrix_silent_with_retired_and_planned_rows(tmp_path):
    report, warn = ms.check(kit(tmp_path))
    assert not warn, report
    assert report[-1].startswith("✓"), report


def test_missing_registry_row_and_coverage_cell_warned(tmp_path):
    docs = kit(tmp_path, fun_extra="Показывает [SCR-CL-02 Список](../screen-form/scr-cl-02.md).\n")
    w(docs / "srs/screen-form/scr-cl-02.md", fm("SCR-CL-02", "screen-form", "Список"))
    report, warn = ms.check(docs)
    text = "\n".join(report)
    assert warn and "нет строки для ID из документов ×1: SCR-CL-02" in text, text
    assert "FUN-CL-01 «Экраны»: нет SCR-CL-02" in text, text
    assert "структура матрицы" not in text, text


def test_link_only_in_matrix_warned_and_reused_retired_id(tmp_path):
    docs = kit(tmp_path, fun_row="| FUN-CL-01 | Сохранение | SCR-CL-01, SCR-CL-05 | ENT-001 | "
                                 "CTL-GRP-1 | — |")
    w(docs / "srs/screen-form/scr-cl-05.md", fm("SCR-CL-05", "screen-form", "Новая форма"))
    report, warn = ms.check(docs)
    text = "\n".join(report)
    assert warn and "связь только в матрице" in text and "FUN-CL-01 «Экраны»: SCR-CL-05" in text, text
    assert "ID переиспользован) ×1: SCR-CL-05" in text, text
