# tests/test_oq_close_guard.py
"""Норма закрытия OQ (решение владельца 2026-11-03): запись закрывает коммит канала изменения.
B10 (review_guards) — запись закрыта с даты нормы без коммита, тега или «без изменений»;
link_debts — долг «открытый вопрос» и запись журнала расходятся по закрытию; закрытый долг
без цели в счёт открытых не входит. Оба сторожа — ⚠/i; срабатывание и НЕсрабатывание."""
from datetime import date
from pathlib import Path

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.checks import review_guards as rg
from app.scripts.CI.link_debts import check, issue_closed

SINCE = rg.OQ_CLOSE_FORM_SINCE
AFTER = date.fromordinal(SINCE.toordinal() + 2).isoformat()


def make(p: Path, text: str, eol: str = "\n", bom: bool = False) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\n", eol).encode("utf-8")
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def journal(*statuses: str) -> str:
    out = "# Открытые вопросы\n\n"
    for i, st in enumerate(statuses, 1):
        out += f"## OQ-{i:03d} — 2026-10-01 — вопрос {i}\n\n- Вопрос: текст\n- Статус: {st}\n\n"
    return out


# ---------------------------------------------------------------- B10: разбор строки статуса

def test_b10_status_forms():
    assert rg.oq_closed_new_form(f"закрыт: {AFTER}") == date.fromisoformat(AFTER)
    assert rg.oq_close_ref(f"закрыт: {AFTER}") is None
    assert rg.oq_close_ref(f"закрыт: {AFTER}, a1b2c3d4, затронуто: CALL-EXT-011") == "a1b2c3d4"
    assert rg.oq_close_ref(f"закрыт: {AFTER}, src/OQ-378") == "src/OQ-378"
    assert rg.oq_close_ref(f"закрыт: {AFTER}, тег prom-slice-0e32b01-accepted") \
        == "prom-slice-0e32b01-accepted"
    assert rg.oq_close_ref(f"закрыт: {AFTER}, без изменений: аналитик КК, приёмка 03.11") \
        == "без изменений"
    # дата ДД.ММ.ГГГГ — тоже дата нормы
    d = date.fromisoformat(AFTER)
    assert rg.oq_closed_new_form(f"закрыт: {d:%d.%m.%Y}") == d


def test_b10_page_id_is_not_commit():
    # НЕсрабатывание ложного канала: 9–10 цифр — page_id Confluence, не коммит;
    # шесть цифр номера задачи Jira — тоже
    assert rg.oq_close_ref(f"закрыт: {AFTER}, задача на странице 2166861010") is None
    assert rg.oq_close_ref(f"закрыт: {AFTER}, задача DBOCORPESPLN-104756") is None
    assert rg.oq_close_ref(f"закрыт: {AFTER}, 1234567") == "1234567"


def test_b10_legacy_and_open_untouched():
    # НЕсрабатывание: прежняя форма (дата раньше нормы), без даты, промежуточные статусы
    assert rg.oq_closed_new_form("закрыт 2026-09-17 — принято решение: вариант 1") is None
    assert rg.oq_closed_new_form("закрыт (2026-10-30, ответ аналитиков — вариант 2)") is None
    assert rg.oq_closed_new_form("закрыта") is None
    assert rg.oq_status_class("ответ получен, разбор") == "открыт"
    assert rg.oq_status_class("ответ получен, канал: источник, задача DBO-1") == "открыт"
    assert rg.oq_closed_new_form(f"ответ получен, разбор ({AFTER})") is None


# ---------------------------------------------------------------- B10: журнал

def test_b10_flags_close_without_channel(tmp_path):
    oq = tmp_path / "open-questions.md"
    make(oq, journal(
        "закрыт 2026-09-17 — принято решение: вариант 1",
        f"закрыт: {AFTER}, без изменений: аналитик КК, приёмка 03.11",
        f"закрыт: {AFTER}, a1b2c3d4, затронуто: CALL-EXT-011",
        f"закрыт: {AFTER}, src/OQ-378",
        f"закрыт: {AFTER}",
        "ответ получен, разбор",
    ))
    out = rg.check_oq_close_form(oq)
    assert out == [f"⚠ OQ закрыт без коммита, тега или «без изменений» (норма закрытия с "
                   f"{SINCE.isoformat()}): 1 — OQ-005"]


def test_b10_clean_journal_silent(tmp_path):
    oq = tmp_path / "open-questions.md"
    make(oq, journal("закрыт 2026-09-17 — решение", f"закрыт: {AFTER}, src/OQ-2", "открыт"))
    assert rg.check_oq_close_form(oq) == []
    assert rg.check_oq_close_form(tmp_path / "нет.md") == []


def test_b10_crlf_bom_journal(tmp_path):
    oq = tmp_path / "open-questions.md"
    make(oq, journal(f"закрыт: {AFTER}", f"закрыт: {AFTER}, a1b2c3d"), eol="\r\n", bom=True)
    out = rg.check_oq_close_form(oq)
    assert len(out) == 1 and out[0].endswith(": 1 — OQ-001")


def test_b10_in_selfcheck_report(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "README.md", "# К\n")
    make(tmp_path / "open-questions.md", journal(f"закрыт: {AFTER}"))
    rep, _ = selfcheck._kc_oq_classes(type("C", (), {"docs": docs})())
    assert any(r.startswith("i OQ: всего 1") for r in rep)
    assert any(r.startswith("⚠ OQ закрыт без коммита") and "OQ-001" in r for r in rep)


# ---------------------------------------------------------------- link_debts

def _row(src: str = "OQ-001", tail: str = "") -> str:
    return ("| FUN-001 | — | долг открытый вопрос: «Что такое сегмент» — причина: определения нет; "
            "ответственный: аналитик; ограничение: шаги доступа; закрытие: определение в глоссарии; "
            f"источник: {src}{tail} |\n")


def _kit(tmp_path: Path, rows: str, oq_text=None, oq_in_docs: bool = False,
         eol: str = "\n", bom: bool = False) -> Path:
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-001.md", "---\nid: FUN-001\ntitle: 'Ф'\n---\n# Ф\n\nшаг\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         "| FUN-001 | function | Ф | srs/function/fun-001.md |\n\n"
         "## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n" + rows)
    if oq_text is not None:
        make((docs if oq_in_docs else tmp_path) / "open-questions.md", oq_text, eol=eol, bom=bom)
    return docs


def _run(docs: Path):
    report, ok = check(docs / "traceability-matrix.md", docs)
    return report, ok, [r for r in report if r.startswith("⚠ долг FUN-001 по OQ")]


def test_issue_closed_parse():
    assert issue_closed(_row(tail=f"; закрыт: {AFTER}, a1b2c3d4")) == f"{AFTER}, a1b2c3d4"
    assert issue_closed(_row(tail=f"; закрыт: {AFTER}, без изменений")) == f"{AFTER}, без изменений"
    # поле «закрытие:» закрытием долга не считается
    assert issue_closed(_row()) is None


def test_debt_open_entry_closed_new_form(tmp_path):
    docs = _kit(tmp_path, _row(), journal(f"закрыт: {AFTER}, a1b2c3d4, затронуто: FUN-001"))
    report, ok, warns = _run(docs)
    assert ok
    assert warns == [f"⚠ долг FUN-001 по OQ-001 открыт, а запись закрыта {AFTER} (a1b2c3d4) — "
                     "допишите закрытие долга или снимите статус"]


def test_debt_closed_entry_open(tmp_path):
    docs = _kit(tmp_path, _row(tail=f"; закрыт: {AFTER}, a1b2c3d4"), journal("ответ получен, разбор"))
    _report, ok, warns = _run(docs)
    assert ok and len(warns) == 1
    assert warns[0].startswith(f"⚠ долг FUN-001 по OQ-001 закрыт ({AFTER}, a1b2c3d4), а запись "
                               "журнала открыта («ответ получен, разбор»)")


def test_both_closed_counts_closed_debt(tmp_path):
    # НЕсрабатывание: оба закрыты; закрытый долг вне счёта открытых — строка i
    docs = _kit(tmp_path, _row(tail=f"; закрыт: {AFTER}, a1b2c3d4"),
                journal(f"закрыт: {AFTER}, a1b2c3d4"))
    report, ok, warns = _run(docs)
    assert ok and warns == []
    assert "i закрытых долгов без цели: 1" in report
    assert not any(r.startswith("долгов без отсутствующей цели") for r in report)
    assert any(r.startswith("OK: долгов 0,") for r in report)


def test_debt_open_entry_fixed_or_legacy_silent(tmp_path):
    # НЕсрабатывание: «зафиксировано» и закрытие прежней формы (до нормы)
    for st in ("зафиксировано: решение в карточке", "закрыт 2026-09-17 — принято решение"):
        docs = _kit(tmp_path, _row(), journal(st))
        report, ok, warns = _run(docs)
        assert ok and warns == [], st
        assert any(r.startswith("долгов без отсутствующей цели 1") for r in report)


def test_journal_in_docs_root_and_crlf_bom(tmp_path):
    # журнал по адресу файлов комплекта: корень docs-репозитория; CRLF и BOM не мешают
    docs = _kit(tmp_path, _row(), journal(f"закрыт: {AFTER}, src/OQ-001"), oq_in_docs=True,
                eol="\r\n", bom=True)
    _report, _ok, warns = _run(docs)
    assert len(warns) == 1 and "(src/OQ-001)" in warns[0]


def test_journal_absent_info_line(tmp_path):
    docs = _kit(tmp_path, _row(), None)
    report, ok, warns = _run(docs)
    assert ok and warns == []
    assert ("i журнал open-questions.md не найден — закрытие долгов «открытый вопрос» с записями "
            "OQ не сверяется") in report


def test_no_oq_debts_no_info_line(tmp_path):
    # без долгов по OQ строки о журнале нет (шум)
    row = _row(src="T-DBO-1")
    docs = _kit(tmp_path, row, None)
    report, _ok, _w = _run(docs)
    assert not any("open-questions.md не найден" in r for r in report)


def test_entry_number_padding_matches(tmp_path):
    # «источник: OQ-1» и запись «## OQ-001» — один вопрос
    docs = _kit(tmp_path, _row(src="OQ-1"), journal(f"закрыт: {AFTER}, a1b2c3d4"))
    _report, _ok, warns = _run(docs)
    assert len(warns) == 1 and "по OQ-1 открыт" in warns[0]
