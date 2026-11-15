# tests/test_call_one_caller.py
"""Сторож «карточка вызова — одна вызывающая функция» (шаблон contract-call.md, раздел B; решение
владельца канона 16.11.2026, постановка прибору 2026-11-16): в одном разделе карточки две и более
таблицы, у каждой подпись со ссылкой на документ-вызыватель (function, process, screen-form, control —
по frontmatter цели), наборы документов различаются — ✗ строкой на карточку. Несрабатывание: таблицы
без подписей, одна подпись, подписи двух функций над одной таблицей, «Процессы» с функцией и
процессом, две подписи на одну функцию (шаги), подписи на модель данных, документ другого типа,
блок кода."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.call_one_caller import analyse, check_call_one_caller

CARD = "srs/contract-call/internal/call-int-001-x.md"
TABLE = "| Параметр контракта | Правило сервиса |\n|---|---|\n| `a` | = 1 |\n"
TABLE2 = "| Параметр | Значение |\n|---|---|\n| b | 2 |\n"  # шапка не по шаблону — тоже таблица
PROC = ("### Процессы\n\n| Процесс / функция | Шаг / место |\n|---|---|\n"
        "| [FUN-CL-01 Функция А](../../function/fun-cl-01-a.md) | Шаг 4 |\n\n")


def fun(n: int) -> str:
    return f"[FUN-CL-0{n} Функция {n}](../../function/fun-cl-0{n}-f.md)"


def card(body: str, typ: str = "contract-call", proc: str = PROC) -> str:
    return (f"---\nid: CALL-INT-001\ntitle: 'Вызов'\ntype: {typ}\nservice: x\n---\n\n# CALL-INT-001. Вызов\n\n"
            "**Базовый контракт:** [INTC-001. Метод](https://h/intc-001.md)\n\n## Назначение\n\nТекст.\n\n"
            "## Использование в сервисе «Сервис»\n\n" + proc + body)


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _kit(tmp_path: Path, text: str, rel: str = CARD) -> Path:
    docs = tmp_path / "docs"
    for n in (1, 2, 3):
        _w(docs / f"srs/function/fun-cl-0{n}-f.md",
           f"---\nid: FUN-CL-0{n}\ntitle: 'Ф{n}'\ntype: function\n---\n\n# FUN-CL-0{n}\n")
    _w(docs / "srs/function/fun-cl-01-a.md", "---\nid: FUN-CL-01\ntype: function\n---\n")
    _w(docs / "srs/process/proc-001-p.md", "---\nid: PROC-001\ntitle: 'П'\ntype: process\n---\n")
    _w(docs / "srs/screen-form/scr-cl-01-s.md", "---\nid: SCR-CL-01\ntype: screen-form\n---\n")
    _w(docs / "srs/control/ctl-reg.md", "---\nid: CTL-REG\ntype: control\n---\n")
    _w(docs / "srs/data-model/ent-001-e.md", "---\nid: ENT-001\ntype: entity\n---\n")
    _w(docs / "srs/data-model/ent-002-e.md", "---\nid: ENT-002\ntype: entity\n---\n")
    _w(docs / "srs/contract-call/internal/call-int-002-y.md",
       "---\nid: CALL-INT-002\ntype: contract-call\n---\n\n# CALL-INT-002\n")
    _w(docs / rel, text)
    return docs


def _run(tmp_path: Path, text: str, rel: str = CARD):
    return check_call_one_caller(_kit(tmp_path, text, rel))


RULES = "### Правила заполнения исходящего сообщения\n\n"


# --- срабатывание ---

def test_two_captioned_tables_of_different_functions(tmp_path):
    body = RULES + f"Вызов из {fun(1)}:\n\n" + TABLE + f"\nВызов из {fun(2)}:\n\n" + TABLE
    rep, ok = _run(tmp_path, card(body))
    assert ok is False and len(rep) == 1
    line = rep[0]
    assert line.startswith("✗ карточка вызова CALL-INT-001 (srs/contract-call/internal/call-int-001-x.md)")
    assert "FUN-CL-01, FUN-CL-02" in line and "разнести по карточкам" in line
    assert "строки перенести дословно" in line and "«Карточка — одна вызывающая функция»" in line


def test_caption_words_not_in_sign(tmp_path):
    # подпись любыми словами — признак ссылка, а не «Вызов из»
    body = RULES + f"Для {fun(1)}:\n\n" + TABLE + f"\n{fun(2)} передаёт:\n\n" + TABLE2
    rep, ok = _run(tmp_path, card(body))
    assert ok is False and "FUN-CL-01, FUN-CL-02" in rep[0]


def test_caption_heading_with_link(tmp_path):
    # подпись — заголовок со ссылкой; раздел он не открывает, обе таблицы в одном разделе
    body = RULES + f"#### Вызов из {fun(1)}\n\n" + TABLE + f"\n#### Вызов из {fun(2)}\n\n" + TABLE
    rep, ok = _run(tmp_path, card(body))
    assert ok is False and "FUN-CL-01, FUN-CL-02" in rep[0]


def test_function_and_screen_form_captions(tmp_path):
    # КК CALL-INT-022: функция и экранная форма — две точки вызова
    body = (RULES + f"Вызов из {fun(1)}:\n\n" + TABLE
            + "\nВызов из [SCR-CL-01 ЭФ](../../screen-form/scr-cl-01-s.md):\n\n" + TABLE)
    rep, ok = _run(tmp_path, card(body))
    assert ok is False and "FUN-CL-01, SCR-CL-01" in rep[0]


def test_matching_section_counts_too(tmp_path):
    body = ("### Сопоставление входящего сообщения\n\n" + f"Ответ для {fun(1)}:\n\n" + TABLE
            + f"\nОтвет для {fun(2)}:\n\n" + TABLE)
    rep, ok = _run(tmp_path, card(body))
    assert ok is False


def test_controls_by_anchor(tmp_path):
    # контроли живут якорями в одном файле реестра — разные якоря = разные точки вызова
    c1 = "[CTL-034 Контроль 1](../../control/ctl-reg.md#ctl-034-a)"
    c2 = "[CTL-035 Контроль 2](../../control/ctl-reg.md#ctl-035-b)"
    body = RULES + f"Вызов из {c1}:\n\n" + TABLE + f"\nВызов из {c2}:\n\n" + TABLE
    rep, ok = _run(tmp_path, card(body))
    assert ok is False and "CTL-034, CTL-035" in rep[0]


def test_line_numbers_point_to_captions(tmp_path):
    body = RULES + f"Вызов из {fun(1)}:\n\n" + TABLE + f"\nВызов из {fun(2)}:\n\n" + TABLE
    text = card(body)
    docs = _kit(tmp_path, text)
    hits = analyse(text, docs / CARD)
    lines = text.splitlines()
    assert [names for _n, names in hits] == [["FUN-CL-01"], ["FUN-CL-02"]]
    assert all(lines[n - 1].startswith("Вызов из") for n, _names in hits)


# --- несрабатывание ---

def test_tables_without_captions_silent(tmp_path):
    # несколько таблиц одного вызова (блоки сообщения, записи массива) — без подписей-ссылок
    body = RULES + "Блок `HEADER`:\n\n" + TABLE + "\nБлок `BODY`:\n\n" + TABLE + "\n" + TABLE2
    assert _run(tmp_path, card(body)) == ([], True)


def test_single_caption_silent(tmp_path):
    body = RULES + f"Вызов из {fun(1)}:\n\n" + TABLE + "\nБлок `BODY`:\n\n" + TABLE
    assert _run(tmp_path, card(body)) == ([], True)


def test_two_functions_one_table_silent(tmp_path):
    # подписи двух функций над одной таблицей — класс «несколько функций при одной таблице» вне сторожа
    body = RULES + f"Вызов из {fun(1)} и {fun(2)}:\n\n" + TABLE
    assert _run(tmp_path, card(body)) == ([], True)


def test_processes_with_function_and_process_silent(tmp_path):
    # КК CALL-EXT-038: общая функция и процесс, откуда она запускается, — законный случай
    proc = ("### Процессы\n\n| Процесс / функция | Шаг / место |\n|---|---|\n"
            f"| {fun(1)} | Шаг 4 |\n| [PROC-001 Процесс](../../process/proc-001-p.md) | Шаг 5 |\n"
            f"| {fun(2)} | Шаг 1 |\n\n")
    body = RULES + f"Вызов из {fun(2)}:\n\n" + TABLE
    assert _run(tmp_path, card(body, proc=proc)) == ([], True)


def test_same_function_two_steps_silent(tmp_path):
    # несколько шагов одной функции — документ различается по файлу, якорь шага не в счёт
    f1 = "[FUN-CL-01 Ф](../../function/fun-cl-01-f.md#шаг-3)"
    f2 = "[FUN-CL-01 Ф](../../function/fun-cl-01-f.md#шаг-5)"
    body = RULES + f"Шаг 3 {f1}:\n\n" + TABLE + f"\nШаг 5 {f2}:\n\n" + TABLE
    assert _run(tmp_path, card(body)) == ([], True)


def test_data_model_captions_silent(tmp_path):
    # docs-account-opening-request CALL-EXT-003: подписи блоков ссылаются на сущности — не вызыватели
    e1 = "[ENT-001](../../data-model/ent-001-e.md)"
    e2 = "[ENT-002](../../data-model/ent-002-e.md)"
    body = RULES + f"Для сущности {e1}:\n\n" + TABLE + f"\nБлок по {e2}:\n\n" + TABLE
    assert _run(tmp_path, card(body)) == ([], True)


def test_reference_to_other_call_card_not_a_caller(tmp_path):
    # отсылка к другой карточке вызова в признак не входит (квитанция, ответ как источник данных)
    other = "[CALL-INT-002](call-int-002-y.md)"
    body = (RULES + f"Вызов из {fun(1)}:\n\n" + TABLE + f"\nКвитанция — {other}:\n\n" + TABLE
            + f"\nИсточник — ответ {other}.\n")
    assert _run(tmp_path, card(body)) == ([], True)


def test_other_document_type_silent(tmp_path):
    body = RULES + f"Вызов из {fun(1)}:\n\n" + TABLE + f"\nВызов из {fun(2)}:\n\n" + TABLE
    rel = "srs/internal-contract/intc-001-x.md"
    assert _run(tmp_path, card(body, typ="internal-contract"), rel=rel) == ([], True)


def test_captions_in_code_block_silent(tmp_path):
    body = (RULES + "```\n" + f"Вызов из {fun(1)}:\n\n" + TABLE + f"\nВызов из {fun(2)}:\n\n" + TABLE
            + "```\n")
    assert _run(tmp_path, card(body)) == ([], True)


def test_missing_target_silent(tmp_path):
    # цель ссылки не найдена — тип не определён, вызывателем не считается
    body = (RULES + "Вызов из [FUN-CL-08](../../function/nope-8.md):\n\n" + TABLE
            + "\nВызов из [FUN-CL-09](../../function/nope-9.md):\n\n" + TABLE)
    assert _run(tmp_path, card(body)) == ([], True)


# --- реестр selfcheck ---

def test_selfcheck_registry_affects_verdict(tmp_path):
    from app.scripts.CI import selfcheck as sc
    chk = [c for c in sc.KIT_CHECKS if getattr(c, "id", None) == "call_one_caller"]
    assert len(chk) == 1 and chk[0].affects_verdict is True
    body = RULES + f"Вызов из {fun(1)}:\n\n" + TABLE + f"\nВызов из {fun(2)}:\n\n" + TABLE
    docs = _kit(tmp_path, card(body))
    rep, ok = chk[0].run(type("Ctx", (), {"docs": docs})())
    assert ok is False and rep[0].startswith("✗ карточка вызова CALL-INT-001")
