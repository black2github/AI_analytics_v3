# tests/test_matrix_sync.py
"""Пакет 2, задача 10, шаг 2: matrix_sync — выводимые разделы матрицы
трассировки сверяются с телами документов (--check)."""
from pathlib import Path

import pytest

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
        fun_row: str = "| FUN-CL-01 | Сохранение | SCR-CL-01 | ENT-001 | CTL-GRP-1 | — |",
        legacy: bool = False) -> Path:
    """legacy — матрица по шаблону до колонки «Уведомления» (2026-10-19); иначе строка
    функции в прежнем виде (6 ячеек) получает «—» в «Уведомлениях»."""
    docs = tmp_path / "docs"
    if legacy:
        fun_hdr = "| Функция | Название | Экраны | Данные | Контроли | Печатные формы |\n| --- | --- | --- | --- | --- | --- |\n"
        proc_hdr = ("| Процесс | Название | Вызывает | Функции | Вызовы | Экраны | Контроли | Данные | Печатные формы |\n"
                    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        proc_row = "| PROC-001 | Обработка | — | FUN-CL-01 | — | — | — | — | — |\n"
    else:
        cells = [c.strip() for c in fun_row.strip().strip("|").split("|")]
        if len(cells) == 6:
            cells.insert(5, "—")
            fun_row = "| " + " | ".join(cells) + " |"
        fun_hdr = ("| Функция | Название | Экраны | Данные | Контроли | Уведомления | Печатные формы |\n"
                   "| --- | --- | --- | --- | --- | --- | --- |\n")
        proc_hdr = ("| Процесс | Название | Вызывает | Функции | Вызовы | Уведомления | Экраны | Контроли | Данные | Печатные формы |\n"
                    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        proc_row = "| PROC-001 | Обработка | — | FUN-CL-01 | — | — | — | — | — | — |\n"
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
      + fun_hdr + fun_row + "\n\n"
      "## Покрытие: процессы → артефакты\n\n"
      + proc_hdr + proc_row + "\n"
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


def test_part_name_title_with_tab_tail_own_title_and_forward():
    """Название части: title главной + хвост H1; свой title — как есть; без title — H1."""
    base_t, base_h = '[КК_ВК] ЭФ Банка: "Просмотр заявки"', 'ЭФ Банка: «Просмотр заявки»'
    assert ms.part_name(base_t, base_h + " — вкладка «Анкеты»", base_t, base_h) \
        == base_t + " — вкладка «Анкеты»"
    assert ms.part_name(base_t + " — вкладка «Анкеты»", base_h + " — вкладка «Анкеты»",
                        base_t, base_h) == base_t + " — вкладка «Анкеты»"
    own = "[КК_ЛК] Карты на ЭФ Банка «Просмотр заявки»"
    assert ms.part_name(own, base_h + " — «Карты»", base_t, base_h) == own
    assert ms.part_name("", base_h + " — вкладка «Реквизиты»", "", base_h) \
        == base_h + " — вкладка «Реквизиты»"


# ------------------------------------- задача 13: текст без ID в выводимой ячейке

def test_write_refuses_text_in_coverage_cell(tmp_path):
    """Пометка в ячейке покрытия — пересборка заменила бы её на «—» молча."""
    docs = kit(tmp_path, fun_row="| FUN-CL-01 | Сохранение | SCR-CL-01 | ENT-001 | CTL-GRP-1 | "
                                 "— (долг L835) |")
    report, warn = ms.check(docs)
    text = "\n".join(report)
    assert warn and "текст без ID в выводимой ячейке" in text, text
    assert "FUN-CL-01 / Печатные формы: «— (долг L835)»" in text, text
    mx = docs / "traceability-matrix.md"
    before = mx.read_bytes()
    report, code = ms.write(docs)
    text = "\n".join(report)
    assert code == 2 and mx.read_bytes() == before, report
    assert "«Покрытие: функции → артефакты»: текст без ID в выводимой ячейке ×1" in text, text
    assert "перенесите в ручной раздел («Долги по ссылкам», приложение) или снимите" in text


def test_write_refuses_text_in_sources_target_cell(tmp_path):
    docs = kit(tmp_path)
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace(
        "| 2166860001 | SCR-CL-01 | — |", "| 2166860001 | SCR-CL-01, см. OQ-158 | — |"),
        encoding="utf-8")
    before = mx.read_bytes()
    report, code = ms.write(docs)
    text = "\n".join(report)
    assert code == 2 and mx.read_bytes() == before, report
    assert "2166860001 / Целевые артефакты: «SCR-CL-01, см. OQ-158»" in text, text


@pytest.mark.parametrize("cell", [
    "SCR-CL-01", "SCR-CL-01, SCR-CL-02", "SCR-CL-01; SCR-CL-03.1", "CTL-001 … CTL-005",
    "CTL-001...CTL-005", "CTL-001–CTL-005", "—", "-", "", "EXTINT-005-A",
    "[SCR-CL-01](srs/screen-form/scr-cl-01.md)", "**SCR-CL-01**", "`ENT-001`",
])
def test_id_only_cells_have_no_text(cell):
    """Несрабатывание: ID, диапазоны, «—», пустая ячейка, ссылка и выделение."""
    assert ms.cell_text_residue(cell) == "", cell


@pytest.mark.parametrize("cell", ["— (долг L835)", "см. OQ-158", "заглушка", "SCR-CL-01 (вкладка)"])
def test_free_text_cells_detected(cell):
    assert ms.cell_text_residue(cell), cell


def test_text_in_name_and_basis_columns_not_checked(tmp_path):
    """Несрабатывание: «Название» покрытия и «Основание» источников — не выводимые
    колонки; текст в них --write не останавливает."""
    docs = kit(tmp_path, fun_row="| FUN-CL-01 | Сохранение (см. OQ-158) | SCR-CL-01 | ENT-001 | "
                                 "CTL-GRP-1 | — |")
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace(
        "| 2166860001 | SCR-CL-01 | — |", "| 2166860001 | SCR-CL-01 | страница-родитель, OQ-158 |"),
        encoding="utf-8")
    report, _warn = ms.check(docs)
    assert "текст без ID" not in "\n".join(report), report
    report, code = ms.write(docs)
    assert code == 0, report
    assert "текст без ID" not in "\n".join(report), report


# ------------------------------------- приложения: ручные разделы после шаблона

APPENDIX = ("## Приложение. Связи: внешние интеграции ↔ процессы\n\n"
            "Навигация, ведётся вручную.\n\n"
            "| EXTINT | PRC | Шаг | Направление |\n|---|---|---|---|\n"
            "| EXTINT-001 | PROC-001 | 3 | исходящий — (см. OQ-158) |\n")


def test_appendix_after_template_sections_is_by_template_and_kept_byte_for_byte(tmp_path):
    docs = kit(tmp_path, fun_extra="Показывает [SCR-CL-02 Список](../screen-form/scr-cl-02.md).\n")
    w(docs / "srs/screen-form/scr-cl-02.md", fm("SCR-CL-02", "screen-form", "Список"))
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8") + "\n" + APPENDIX + "\n"
                  + APPENDIX.replace("## Приложение.", "## Приложение 2."), encoding="utf-8")
    report, _warn = ms.check(docs)
    assert "структура матрицы" not in "\n".join(report), report
    report, code = ms.write(docs)
    assert code == 0, report
    text = mx.read_text(encoding="utf-8")
    assert text.endswith(APPENDIX + "\n" + APPENDIX.replace("## Приложение.", "## Приложение 2."))
    assert "SCR-CL-01, SCR-CL-02" in text


def test_appendix_before_template_section_is_structure_issue(tmp_path):
    docs = kit(tmp_path)
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace("## Долги по ссылкам",
                                                         APPENDIX + "\n## Долги по ссылкам"),
                  encoding="utf-8")
    before = mx.read_bytes()
    st = ms.structure_issues(ms.parse_matrix(mx.read_text(encoding="utf-8")))
    assert any("приложение «Приложение. Связи" in x and "«Долги по ссылкам»" in x for x in st), st
    report, code = ms.write(docs)
    assert code == 2 and mx.read_bytes() == before, report


def test_section_without_appendix_prefix_still_outside_template(tmp_path):
    """Несрабатывание исключения: раздел без префикса «Приложение» (опечатка в
    имени раздела шаблона, «Приложения», произвольное имя) — вне шаблона."""
    for title in ("Артефакты вне трассировки", "Приложения", "Долги по ссылкaм"):
        assert ms.section_key(title) == "unknown", title
    assert ms.section_key("Приложение 3. Артефакты вне трассировки") == "appendix"


# ------------------------- ID нестандартной формы: --check сходится после --write

def test_nonstandard_document_ids_recognized_in_first_cell_and_cells():
    assert ms._first_id("API-ASYNC-SEQ") == "API-ASYNC-SEQ"
    assert ms._first_id("[EXTINT-005-A](srs/x.md)") == "EXTINT-005-A"
    assert ms._first_id("`API-ASYNC-SEQ`") == "API-ASYNC-SEQ"
    assert ms.cell_ids("PRC-011, EXTINT-005, EXTINT-005-A") == {"PRC-011", "EXTINT-005", "EXTINT-005-A"}


def test_nonstandard_forms_not_taken_from_free_text():
    """Несрабатывание: ID без номера (`API-ASYNC-SEQ`) берётся только из ячейки,
    которая целиком и есть ID; в тексте и в ячейках покрытия он не ID."""
    assert ms._first_id("последовательность API-ASYNC-SEQ") == ""
    assert ms._first_id("Операция") == ""
    assert ms.cell_ids("API-ASYNC-SEQ") == set()
    assert ms.cell_ids("SCR-CL-01") == {"SCR-CL-01"}


def test_new_registry_row_name_link_becomes_text(tmp_path):
    """Название новой строки из ячейки таблицы чужого файла — без ссылки: её
    относительный путь и якорь в матрице битые. Существующее название — как есть."""
    docs = kit(tmp_path, registry=REGISTRY.replace(
        "| CTL-GRP-1 | Группа сохранения | `srs/control/README.md` |\n", ""))
    report, code = ms.write(docs)
    assert code == 0, report
    text = (docs / "traceability-matrix.md").read_text(encoding="utf-8")
    assert "| CTL-GRP-1 | Группа сохранения — FUN-CL-01 | `srs/control/README.md` |" in text, text
    assert "](../function/fun-cl-01.md)" not in text.split("## Покрытие")[0]


def test_write_then_check_converges_on_nonstandard_ids(tmp_path):
    docs = kit(tmp_path, fun_extra="Вызывает [EXTINT-005-A Приложение](../ext/extint-005-a.md).\n")
    w(docs / "srs/ext/extint-005-a.md", fm("EXTINT-005-A", "contract-call", "Приложение"))
    w(docs / "srs/ext/api-async-seq.md", fm("API-ASYNC-SEQ", "contract-call", "Последовательность"))
    report, code = ms.write(docs)
    assert code == 0, report
    report, warn = ms.check(docs)
    assert not warn, report
    report, code = ms.write(docs)
    assert code == 0 and "не перезаписан" in report[0], report


# ---------------------------------------------------------------- колонка «Уведомления», INTC в «Вызовах» (2026-10-19)

def _ntf(docs: Path) -> None:
    w(docs / "srs/ntf-notification.md", fm("NTF-000", "notification", "Нотификации"))
    w(docs / "srs/internal-contracts/intc-001.md", fm("INTC-001", "internal-contract", "Метод"))
    p = docs / "srs/process/proc-001.md"
    p.write_text(p.read_text(encoding="utf-8")
                 + "| 2 | Уведомление [NTF-000](../ntf-notification.md), вызов [INTC-001](../internal-contracts/intc-001.md) |\n",
                 encoding="utf-8")


def test_legacy_matrix_without_ntf_column_warns_not_structure(tmp_path):
    report, warn = ms.check(kit(tmp_path, legacy=True))
    text = "\n".join(report)
    assert warn and "нет колонки «Уведомления» — --write добавит" in text, text
    assert "структура матрицы не по шаблону" not in text, text


def test_write_adds_ntf_column_and_keeps_other_cells(tmp_path):
    docs = kit(tmp_path, legacy=True)
    m = docs / "traceability-matrix.md"
    before = m.read_text(encoding="utf-8")
    rep_, code = ms.write(docs)
    assert code == 0, rep_
    after = m.read_text(encoding="utf-8")
    assert ("| Функция | Название | Экраны | Данные | Контроли | Уведомления | Печатные формы |" in after)
    assert "| FUN-CL-01 | Сохранение | SCR-CL-01 | ENT-001 | CTL-GRP-1 | — | — |" in after, after
    assert "| PROC-001 | Обработка | — | FUN-CL-01 | — | — | — | — | — | — |" in after, after
    # вне таблиц покрытия — байт в байт
    assert before.split("## Покрытие: функции")[0] == after.split("## Покрытие: функции")[0]
    assert before.split("## Покрытие: API")[1] == after.split("## Покрытие: API")[1]
    report, warn = ms.check(docs)
    assert not warn, report


def test_ntf_and_intc_go_to_their_columns(tmp_path):
    docs = kit(tmp_path)
    _ntf(docs)
    reg = docs / "traceability-matrix.md"
    t = reg.read_text(encoding="utf-8").replace(
        "| PROC-001 | Обработка | `srs/process/proc-001.md` |",
        "| INTC-001 | Метод | `srs/internal-contracts/intc-001.md` |\n| NTF-000 | Нотификации | `srs/ntf-notification.md` |\n"
        "| PROC-001 | Обработка | `srs/process/proc-001.md` |")
    reg.write_text(t, encoding="utf-8")
    rep_, code = ms.write(docs)
    assert code == 0, rep_
    after = reg.read_text(encoding="utf-8")
    assert "| PROC-001 | Обработка | — | FUN-CL-01 | INTC-001 | NTF-000 | — | — | — | — |" in after, after
    report, warn = ms.check(docs)
    assert not warn, report


def test_column_order_deviation_is_still_structure(tmp_path):
    docs = kit(tmp_path)
    m = docs / "traceability-matrix.md"
    m.write_text(m.read_text(encoding="utf-8").replace(
        "| Функция | Название | Экраны | Данные | Контроли | Уведомления | Печатные формы |",
        "| Функция | Название | Данные | Экраны | Контроли | Уведомления | Печатные формы |"), encoding="utf-8")
    report, warn = ms.check(docs)
    assert "структура матрицы не по шаблону" in "\n".join(report), report
    _r, code = ms.write(docs)
    assert code == 2
