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


# ------------------------------------------------------------- --write (С3)

def _section(text: str, title: str) -> str:
    start = text.index("## " + title)
    nxt = text.find("\n## ", start + 3)
    return text[start:nxt if nxt != -1 else len(text)]


def test_write_rebuilds_derived_keeps_manual_bytes_bom_crlf(tmp_path):
    docs = kit(tmp_path, fun_extra="Показывает [SCR-CL-02 Список](../screen-form/scr-cl-02.md).\n")
    w(docs / "srs/screen-form/scr-cl-02.md", fm("SCR-CL-02", "screen-form", "Список"))
    mx = docs / "traceability-matrix.md"
    text = mx.read_text(encoding="utf-8")
    text = text.replace("## Реестр ID\n\n", "## Реестр ID\n\nВводный текст раздела — ручной.\n\n")
    text = text.replace("| Операция | Артефакты SRS |\n| --- | --- |\n",
                        "| Операция | Артефакты SRS |\n| --- | --- |\n| POST /x | FUN-CL-01 |\n")
    text = text.replace("| Артефакт | Цель | Причина |\n| --- | --- | --- |\n",
                        "| Артефакт | Цель | Причина |\n| --- | --- | --- |\n| FUN-CL-01 | — | долг |\n")
    mx.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
    before = mx.read_bytes()
    report, code = ms.write(docs)
    assert code == 0 and report[0].startswith("✓ выводимые разделы пересобраны"), report
    after = mx.read_bytes()
    assert after.startswith(b"\xef\xbb\xbf") and after.count(b"\n") == after.count(b"\r\n")
    t0 = before.decode("utf-8-sig").replace("\r\n", "\n")
    t1 = after.decode("utf-8-sig").replace("\r\n", "\n")
    for title in ("Покрытие: API ↔ SRS", "Долги по ссылкам"):
        assert _section(t0, title) == _section(t1, title)
    assert "Вводный текст раздела — ручной." in _section(t1, "Реестр ID")
    assert "| SCR-CL-05 | снят 2026-08-30: тип изменён, преемник FUN-CL-01 | — |" in t1
    assert "| SCR-CL-02 | Список | `srs/screen-form/scr-cl-02.md` |" in t1
    assert "| FUN-CL-01 | Сохранение | SCR-CL-01, SCR-CL-02 | ENT-001 | CTL-GRP-1 | — |" in t1
    assert not ms.check(docs)[1], ms.check(docs)[0]


def test_write_second_run_does_not_touch_file(tmp_path):
    docs = kit(tmp_path)
    mx = docs / "traceability-matrix.md"
    before, mtime = mx.read_bytes(), mx.stat().st_mtime_ns
    report, code = ms.write(docs)
    assert code == 0 and "не перезаписан" in report[0], report
    assert mx.read_bytes() == before and mx.stat().st_mtime_ns == mtime


def test_write_refuses_structure_not_by_template(tmp_path):
    docs = kit(tmp_path)
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace("## Источники миграции",
                                                         "## Источники (вне SRS)"), encoding="utf-8")
    before = mx.read_bytes()
    report, code = ms.write(docs)
    assert code == 2 and "структура не по шаблону" in "\n".join(report), report
    assert mx.read_bytes() == before


def test_write_refuses_vanished_document_and_link_only_in_matrix(tmp_path):
    docs = kit(tmp_path, registry=REGISTRY + "| SCR-CL-03 | Удалённая форма | `srs/screen-form/scr-cl-03.md` |\n",
               fun_row="| FUN-CL-01 | Сохранение | SCR-CL-01 | ENT-001, ENT-002 | CTL-GRP-1 | — |")
    w(docs / "srs/data-model/ent-002.md", fm("ENT-002", "data-model", "Клиент"))
    mx = docs / "traceability-matrix.md"
    before = mx.read_bytes()
    report, code = ms.write(docs)
    text = "\n".join(report)
    assert code == 2 and mx.read_bytes() == before, report
    assert "строка без документа" in text and "SCR-CL-03" in text, text
    assert "пересборка потеряет" in text and "ENT-002" in text, text


def test_write_refuses_cell_id_missing_from_kit(tmp_path):
    """Снятый ID в ячейке покрытия — пересборка выбросила бы его молча."""
    docs = kit(tmp_path, fun_row="| FUN-CL-01 | Сохранение | SCR-CL-01, SCR-CL-01.0 | ENT-001 | "
                                 "CTL-GRP-1 | — |")
    report, _warn = ms.check(docs)
    assert "ID не найден в комплекте" in "\n".join(report), report
    mx = docs / "traceability-matrix.md"
    before = mx.read_bytes()
    report, code = ms.write(docs)
    assert code == 2 and mx.read_bytes() == before and "SCR-CL-01.0" in "\n".join(report), report
