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


def test_oq_order_violation_caught(tmp_path):
    from app.scripts.CI.link_debts import check_oq_order
    p = tmp_path / "open-questions.md"
    make(p, "## OQ-001. А\n\n## OQ-003. Б\n\n## OQ-002. В\n")
    report, ok = check_oq_order(p)
    assert not ok and "OQ-002" in report[0]


def test_oq_order_ok_and_missing_file(tmp_path):
    from app.scripts.CI.link_debts import check_oq_order
    p = tmp_path / "open-questions.md"
    make(p, "## OQ-001. А\n\n## OQ-002. Б\n")
    report, ok = check_oq_order(p)
    assert ok and "соблюдён" in report[0]
    r2, ok2 = check_oq_order(tmp_path / "нет.md")
    assert ok2 and not r2


def test_config_param_missing_caught(tmp_path):
    from app.scripts.CI.link_debts import check_config_params
    docs = tmp_path / "docs"
    make(docs / "srs/agents/chd-01.md",
         "Значение параметра [Настраиваемые параметры] БлокН2Н.h2h_in_path\n")
    make(docs / "srs/data-model/dictionaries.md",
         "## Настраиваемые параметры\n\n| Ключ | Значение |\n|---|---|\n")
    report, ok = check_config_params(docs)
    assert not ok and "h2h_in_path" in report[0]


def test_config_param_present_ok(tmp_path):
    # тест на НЕсрабатывание: ключ зафиксирован в справочнике
    from app.scripts.CI.link_debts import check_config_params
    docs = tmp_path / "docs"
    make(docs / "srs/agents/chd-01.md",
         "Значение параметра [Настраиваемые параметры] БлокН2Н.h2h_in_path\n")
    make(docs / "srs/data-model/dictionaries.md",
         "## Настраиваемые параметры\n\n| h2h_in_path | |\n")
    report, ok = check_config_params(docs)
    assert ok and not report


def test_config_param_space_before_dot_caught(tmp_path):
    # дефект набора источника: «БлокН2Н .h2h_out_path» (пробел перед
    # точкой) прятал параметр от сторожа
    from app.scripts.CI.link_debts import check_config_params
    docs = tmp_path / "docs"
    make(docs / "srs/process/prc-002.md",
         "путь из [Настраиваемые параметры] БлокН2Н .h2h_out_path. Если отчет\n")
    make(docs / "srs/data-model/dictionaries.md", "| Ключ | |\n")
    report, ok = check_config_params(docs)
    assert not ok and "h2h_out_path" in report[0]


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


def test_feedback_order_violation_caught(tmp_path):
    # feedback.md — та же append-only дисциплина, что у OQ (цикл
    # обратной связи команд, модель принята 2026-08-17)
    from app.scripts.CI.link_debts import check_feedback_order
    p = tmp_path / "feedback.md"
    make(p, "## FB-01. А\n\n## FB-03. Б\n\n## FB-02. В\n")
    report, ok = check_feedback_order(p)
    assert not ok and "FB-002 стоит после FB-003" in report[0]


def test_feedback_order_ok_and_missing_file(tmp_path):
    # тест на НЕсрабатывание: порядок соблюдён; файла нет — не брак
    from app.scripts.CI.link_debts import check_feedback_order
    p = tmp_path / "feedback.md"
    make(p, "## FB-01. А\n\n## FB-02. Б\n")
    report, ok = check_feedback_order(p)
    assert ok and "feedback" in report[0] and "соблюдён" in report[0]
    r2, ok2 = check_feedback_order(tmp_path / "нет.md")
    assert ok2 and not r2
