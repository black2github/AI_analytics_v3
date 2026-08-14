# tests/test_link_debts.py
"""Сторож долгов ссылок: просрочка (цель существует — ссылка не
проставлена) и исполнимость (дословное имя находится в ожидателе)."""

from pathlib import Path

from app.scripts.CI.link_debts import check

MATRIX = """# Матрица

## Реестр ID

| ID | Тип | Наименование | Файл |
|---|---|---|---|
| FUN-BNK-01 | function | Функция изменения статуса | srs/functions/fun-bnk-01.md |
| FUN-BNK-02 | function | Функция запуска | srs/functions/fun-bnk-02.md |

## Связи

| От | К | Связь |
|---|---|---|
| FUN-BNK-01…02 | — | нет целевого артефакта PRC «Процесс обработки сообщения о блокировке» — требуется заход create-process |
"""


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def setup_docs(tmp_path, fun_text):
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", MATRIX)
    for n in ("01", "02"):
        make(docs / "srs/functions" / f"fun-bnk-{n}.md",
             f"---\nid: FUN-BNK-{n}\ntitle: 'Ф{n}'\n---\n{fun_text}\n")
    return docs


def test_pending_debt_clean(tmp_path):
    # цель не существует, имя находится дословно — долг легален
    docs = setup_docs(tmp_path,
                      "шаг процесса Процесс обработки сообщения о блокировке")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert ok and "OK" in report[-1]


def test_overdue_debt_caught(tmp_path):
    # цель ПОЯВИЛАСЬ (title содержит имя долга) — долг просрочен
    docs = setup_docs(tmp_path,
                      "шаг процесса Процесс обработки сообщения о блокировке")
    make(docs / "srs/process/prc-001.md",
         "---\nid: PRC-001\ntitle: '[БлокН2Н] Процесс обработки сообщения о блокировке'\n---\n# П\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok and any("ПРОСРОЧЕН" in r for r in report)


def test_unfulfillable_debt_caught(tmp_path):
    # имя долга не находится дословно в ожидателе — замена невозможна
    docs = setup_docs(tmp_path, "шаг процесса обработки (пересказ)")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok and any("НЕИСПОЛНИМ" in r for r in report)


def test_range_expansion_checks_both(tmp_path):
    # диапазон FUN-BNK-01…02: имя ищется в ОБОИХ ожидателях
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", MATRIX)
    make(docs / "srs/functions/fun-bnk-01.md",
         "---\nid: A\ntitle: 'Ф1'\n---\nПроцесс обработки сообщения о блокировке\n")
    make(docs / "srs/functions/fun-bnk-02.md",
         "---\nid: B\ntitle: 'Ф2'\n---\nдругой текст\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok and any("fun-bnk-02" in r for r in report)
