# tests/test_link_debts_awaiters.py
"""Ожидатель долга в карточке без строки долга в матрице — ⚠ (постановка 2026-11-09, П-3; КК 09.11:
FUN-CL-10…21 с формулой «нет целевого артефакта platform-function «[ЦРМ] …»», а FROM строки долга
собран неполно). Признак по форме: формулы строк долга link_debts в теле карточки."""
from pathlib import Path

from app.scripts.CI.link_debts import awaiters_without_debt, check

WRAP = ("- Роли пользователя (см. [ЦРМ] Ролевая модель клиента (нет целевого артефакта "
        "platform-function — требуется заход create-platform-function)).\n")
ROW = ("| FUN-001 | — | нет целевого артефакта platform-function «[ЦРМ] Ролевая модель клиента» — "
       "требуется заход create-platform-function |\n")
CLOSED_ROW = ("| FUN-001 | RBAC-001 | [ЦРМ] Ролевая модель клиента |\n")


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def kit(tmp_path: Path, body: str, rows: str = "", with_debts: bool = True,
        readme: str = "") -> Path:
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-001.md", f"---\nid: FUN-001\ntitle: 'Ф1'\n---\n# Ф1\n\n{body}")
    make(docs / "srs/function/fun-002.md", "---\nid: FUN-002\ntitle: 'Ф2'\n---\n# Ф2\n\nтекст\n")
    reg = ("| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
           "| FUN-001 | function | Ф1 | srs/function/fun-001.md |\n"
           "| FUN-002 | function | Ф2 | srs/function/fun-002.md |\n")
    if readme:
        make(docs / "srs/function/README.md", readme)
        reg += "| FUN-000 | function | Реестр | srs/function/README.md |\n"
    debts = ("\n## 4. Долги по ссылкам\n\n| FROM-ID | Цель | Долг |\n|---|---|---|\n" + rows
             if with_debts else "")
    make(docs / "traceability-matrix.md", "# М\n\n## 1. Реестр ID\n\n" + reg + debts)
    return docs


def _aw(report):
    return [ln for ln in report if ln.startswith("⚠ ожидатель долга")]


def test_wrap_without_debt_row_warned(tmp_path):
    docs = kit(tmp_path, WRAP, rows="| FUN-002 | — | нет целевого артефакта function «Иное» — "
                                    "требуется заход create-function |\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    aw = _aw(report)
    assert len(aw) == 1 and "srs/function/fun-001.md (FUN-001)" in aw[0], report
    assert "«нет целевого артефакта» ×1" in aw[0]
    assert any("карточек с ожидателем долга без строки долга 1" in ln for ln in report)


def test_wrap_with_debt_row_silent(tmp_path):
    # НЕсрабатывание: карточка в FROM открытой строки долга
    docs = kit(tmp_path, WRAP, rows=ROW)
    report, _ok = check(docs / "traceability-matrix.md", docs)
    assert not _aw(report), report


def test_wrap_with_closed_row_silent(tmp_path):
    # НЕсрабатывание: строка долга закрыта (цель во второй колонке), ID в FROM — строка есть
    docs = kit(tmp_path, WRAP, rows=CLOSED_ROW)
    report, _ok = check(docs / "traceability-matrix.md", docs)
    assert not _aw(report), report


def test_base_contract_forms_warned(tmp_path):
    body = ("**Базовый контракт:** `ТЕССА_Получение файла` в docs-external-contracts не заведён — "
            "требуется контур base (долг).\n\nТакже нет базового контракта «Метод Ф1».\n")
    docs = kit(tmp_path, body, rows="")
    report, _ok = check(docs / "traceability-matrix.md", docs)
    aw = _aw(report)
    assert len(aw) == 1 and "«нет базового контракта» ×1" in aw[0] \
        and "«требуется контур base» ×1" in aw[0], report


def test_warning_does_not_break_verdict(tmp_path):
    docs = kit(tmp_path, WRAP, rows="")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert ok and _aw(report), report


def test_comment_code_and_readme_ignored(tmp_path):
    # НЕсрабатывание: формула в HTML-комментарии, в блоке кода; README-реестр не читается
    body = ("<!-- нет целевого артефакта function — требуется заход create-function -->\n\n"
            "```\nнет целевого артефакта data-model\n```\n")
    docs = kit(tmp_path, body, rows="", readme="# Реестр\n\n| CALL-EXT-035 | нет — требуется контур base "
                                              "(долг) |\n")
    report, _ok = check(docs / "traceability-matrix.md", docs)
    assert not _aw(report), report


def test_plain_word_debt_not_awaiter(tmp_path):
    # НЕсрабатывание: слово «долг» и «ожидание» без формулы строки долга — не признак
    docs = kit(tmp_path, "Ожидание ответа банка; см. долг в матрице трассировки.\n", rows="")
    report, _ok = check(docs / "traceability-matrix.md", docs)
    assert not _aw(report), report


def test_no_debts_section_no_check(tmp_path):
    docs = kit(tmp_path, WRAP, with_debts=False)
    text = (docs / "traceability-matrix.md").read_text(encoding="utf-8")
    assert awaiters_without_debt(text, docs, {"FUN-001": ("function", "srs/function/fun-001.md")}) == []
