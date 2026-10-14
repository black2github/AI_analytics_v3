# tests/test_link_debts.py
"""Сторож долгов ссылок: просрочка (цель существует — ссылка не
проставлена) и исполнимость (дословное имя находится в ожидателе)."""

import re
from pathlib import Path

from app.scripts.CI.link_debts import check, parse_matrix

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


_ISSUE_ROW_OK = ("| FUN-001 | — | долг открытый вопрос: «Что такое сегмент» — причина: процессы и "
                 "статусы называют сегмент, определения нет; ответственный: аналитик lk-mp; "
                 "ограничение: шаги предоставления доступа к сегменту; закрытие: определение в "
                 "глоссарии; источник: OQ-033 |\n")


def _issue_docs(tmp_path, row):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-001.md",
         "---\nid: FUN-001\ntitle: 'Ф'\n---\n# Ф\n\nшаг процесса\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         "| FUN-001 | function | Ф | srs/function/fun-001.md |\n\n"
         "## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n" + row)
    return docs


def test_issue_debt_complete_parsed_and_clean(tmp_path):
    # НЕсрабатывание: долг без цели со всеми полями — разобран, брака нет
    from app.scripts.CI.link_debts import parse_matrix, issue_fields
    docs = _issue_docs(tmp_path, _ISSUE_ROW_OK)
    _reg, debts = parse_matrix((docs / "traceability-matrix.md").read_text(encoding="utf-8"))
    assert len(debts) == 1 and debts[0][1] == "долг:открытый вопрос"
    assert debts[0][2] == "Что такое сегмент" and debts[0][3] is None
    f = issue_fields(debts[0][4])
    assert f["source"] == "OQ-033" and f["responsible"] == "аналитик lk-mp" and f["missing"] == []
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert ok, "\n".join(report)
    assert any("долгов без отсутствующей цели 1" in r for r in report)


def test_issue_debt_incomplete_caught(tmp_path):
    # срабатывание: нет ограничения и закрытия, у открытого вопроса нет источника
    row = ("| FUN-001 | — | долг открытый вопрос: «Что такое сегмент» — причина: нет определения; "
           "ответственный: аналитик lk-mp |\n")
    docs = _issue_docs(tmp_path, row)
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok
    bad = [r for r in report if "НЕПОЛОН" in r]
    assert bad and "ограничение" in bad[0] and "закрытие" in bad[0] and "OQ-NNN" in bad[0]


def test_issue_debt_unknown_from_id_caught(tmp_path):
    # срабатывание: FROM-ID вне реестра — как у долгов по ссылкам
    docs = _issue_docs(tmp_path, _ISSUE_ROW_OK.replace("| FUN-001 |", "| FUN-999 |"))
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok and any("FUN-999: ID отсутствует" in r for r in report)


def test_issue_kind_outside_list_not_a_debt(tmp_path):
    # НЕсрабатывание: вид вне закрытого перечня — строкой долга не считается (как и прежде)
    from app.scripts.CI.link_debts import parse_matrix
    docs = _issue_docs(tmp_path, "| FUN-001 | — | долг пожелание: «сделать красиво» |\n")
    _reg, debts = parse_matrix((docs / "traceability-matrix.md").read_text(encoding="utf-8"))
    assert debts == []


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


def test_registry_variant_columns_parsed(tmp_path):
    # реальные реестры матрицы разноколонны и пишут файл ссылкой:
    # «| ID | Название | Файл-ссылка |», «| ID | page_id | Файл |» —
    # жёсткая 4-колонная форма их не видела (пилот-3: первый именованный
    # долг от FUN-ID дал ложное «ID отсутствует в реестре»)
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", """# Матрица

## Реестр ID (модель данных)

| ID | Название | Файл |
|---|---|---|
| ENT-001 | Поручение | [srs/data-model/ent-001.md](srs/data-model/ent-001.md) |

## Реестр ID (функции)

| ID | page_id | Файл |
|---|---|---|
| FUN-SYS-03 | 2169849256 | [srs/functions/fun-sys-03.md](srs/functions/fun-sys-03.md) |

## Долги

| Источник | — | Долг |
|---|---|---|
| FUN-SYS-03 | — | нет целевого артефакта function «[РРКО_ИПИ] Система: Функция сохранения статуса» — требуется заход create-function |
""")
    make(docs / "srs/data-model/ent-001.md",
         "---\nid: ENT-001\ntitle: 'Поручение'\n---\n# Е\n")
    make(docs / "srs/functions/fun-sys-03.md",
         "---\nid: FUN-SYS-03\ntitle: 'Ф'\n---\nвызов функции "
         "[РРКО_ИПИ] Система: Функция сохранения статуса, далее\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert ok, report
    assert not any("ID отсутствует в реестре" in r for r in report)


def test_registry_id_still_missing_caught(tmp_path):
    # НЕсрабатывание наоборот: долг от ID, которого в реестрах
    # действительно нет, — по-прежнему брак
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", """# Матрица

| ID | Название | Файл |
|---|---|---|
| ENT-001 | Поручение | [srs/data-model/ent-001.md](srs/data-model/ent-001.md) |

| Источник | — | Долг |
|---|---|---|
| FUN-SYS-99 | — | нет целевого артефакта function «Функция призрачная где-то там» — требуется заход create-function |
""")
    make(docs / "srs/data-model/ent-001.md",
         "---\nid: ENT-001\ntitle: 'Поручение'\n---\n# Е\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok and any("ID отсутствует в реестре" in r for r in report)


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


MATRIX_CROSS = """# Матрица

## Реестр ID

| ID | Тип | Наименование | Файл |
|---|---|---|---|
| FUN-BNK-01 | function | Функция изменения статуса | srs/functions/fun-bnk-01.md |

## Связи

| От | К | Связь |
|---|---|---|
| FUN-BNK-01 | — | нет целевого артефакта internal-contract «Метод получения данных о блокировках» у владельца file-storage — требуется публикация владельцем |
"""


def test_cross_service_debt_skips_local_overdue(tmp_path):
    # межсервисный долг («у владельца <service-id>»): локальный документ
    # с совпадающим title НЕ делает долг просроченным — цель в чужом репо
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", MATRIX_CROSS)
    make(docs / "srs/functions/fun-bnk-01.md",
         "---\nid: FUN-BNK-01\ntitle: 'Ф1'\n---\n"
         "вызов Метод получения данных о блокировках\n")
    make(docs / "srs/internal-contract/intc-001.md",
         "---\nid: INTC-001\ntitle: '[ФС] Метод получения данных о "
         "блокировках'\n---\n# М\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert ok, report
    assert not any("ПРОСРОЧЕН" in r for r in report)
    assert any("межсервисных долгов 1" in r and "file-storage" in r
               for r in report)


def test_cross_service_debt_unfulfillable_still_caught(tmp_path):
    # исполнимость имени для межсервисного долга проверяется как обычно
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", MATRIX_CROSS)
    make(docs / "srs/functions/fun-bnk-01.md",
         "---\nid: FUN-BNK-01\ntitle: 'Ф1'\n---\nпересказ без имени\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok and any("НЕИСПОЛНИМ" in r for r in report)


def test_dotted_sub_id_in_registry_resolved(tmp_path):
    # FRAME-01 (2026-08-31): суб-ID с точкой — легальный ID реестра;
    # долг от SCR-CL-01.0 резолвится в его файл-ожидатель
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n## Реестр ID\n\n"
         "| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         "| SCR-CL-01.0 | screen-form | Главная карточка | "
         "srs/screen-form/scr-cl-01-main.md |\n\n"
         "## Связи\n\n| От | К | Связь |\n|---|---|---|\n"
         "| SCR-CL-01.0 | — | нет целевого артефакта function «Функция "
         "создания заявки» — требуется заход create-function |\n")
    make(docs / "srs/screen-form/scr-cl-01-main.md",
         "---\nid: SCR-CL-01.0\ntitle: 'Гл'\n---\n"
         "Вызов: Функция создания заявки.\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert ok, report

    # НЕсрабатывание послабления: имени нет в ожидателе — брак виден
    make(docs / "srs/screen-form/scr-cl-01-main.md",
         "---\nid: SCR-CL-01.0\ntitle: 'Гл'\n---\nпусто\n")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert not ok
    assert any("не найдено дословно" in ln for ln in report)


class TestRegisterCountSkipsCodeBlocks:
    """FB-04: заголовок-образец в блоке кода не считается записью реестра."""

    def test_example_heading_in_code_block_not_counted(self, tmp_path):
        from app.scripts.CI import link_debts as ld
        p = tmp_path / "open-questions.md"
        p.write_text("# Открытые вопросы\n\nФормат записи:\n\n```markdown\n"
                     "## OQ-01 — <дата> — <тема>\n```\n", encoding="utf-8")
        rep, ok = ld.check_oq_order(p)
        assert ok and "(0 записей)" in rep[0], rep

    def test_real_entries_still_counted_and_order_checked(self, tmp_path):
        # тест на НЕсрабатывание исключения: настоящие записи вне блоков
        # кода считаются, нарушение порядка по-прежнему брак
        from app.scripts.CI import link_debts as ld
        p = tmp_path / "open-questions.md"
        p.write_text("# Открытые вопросы\n\n```markdown\n## OQ-09 — пример\n```\n\n"
                     "## OQ-01 — 2026-09-11 — тема\n\n## OQ-02 — 2026-09-15 — тема\n",
                     encoding="utf-8")
        rep, ok = ld.check_oq_order(p)
        assert ok and "(2 записей)" in rep[0], rep
        p.write_text("## OQ-02 — тема\n\n## OQ-01 — тема\n", encoding="utf-8")
        rep, ok = ld.check_oq_order(p)
        assert not ok and "порядок реестра нарушен" in rep[0]


class TestCoordinationLogEntryLength:
    """Д-34 (2026-10-09): запись журнала координации длиннее 600 знаков — ⚠;
    вердикт не трогает; файла нет — пусто."""

    def _log(self, tmp_path, entries):
        p = tmp_path / "coordination-log.md"
        p.write_text("# Журнал\n\n---\n\n" + "\n".join(entries) + "\n",
                     encoding="utf-8")
        return p

    def test_short_entries_ok(self, tmp_path):
        from app.scripts.CI import link_debts as ld
        p = self._log(tmp_path, [
            "- 2026-10-09 | прогноз z02 | ожидаю: журнал; риск: натяжка",
            "- 2026-10-09 | приёмка z02 | принято; FB-03 заведён",
            "  - подробность с отступом — часть записи",
        ])
        rep, ok = ld.check_coordination_log(p)
        assert ok and rep == ["coordination-log: записей 2, сверх лимита 600 знаков — 0 ✓"]

    def test_long_entry_warned_with_date_and_topic(self, tmp_path):
        from app.scripts.CI import link_debts as ld
        p = self._log(tmp_path, [
            "- 2026-10-09 | короткая | ок",
            "- 2026-10-09 | техприёмка STS-02 | " + "дословный вывод " * 60,
        ])
        rep, ok = ld.check_coordination_log(p)
        assert ok  # вердикт не трогает
        assert rep[0].startswith("coordination-log: записей 2, сверх лимита 600 знаков — 1")
        assert any(l.startswith("предупреждение: запись журнала «2026-10-09 | техприёмка STS-02» — ")
                   and "(лимит 600)" in l for l in rep), rep

    def test_continuation_lines_count_into_entry(self, tmp_path):
        from app.scripts.CI import link_debts as ld
        p = self._log(tmp_path, ["- 2026-10-09 | заход | старт"]
                      + ["  - пункт " + "x" * 80 for _ in range(10)])
        rep, _ = ld.check_coordination_log(p)
        assert "сверх лимита 600 знаков — 1" in rep[0]

    def test_missing_file_silent(self, tmp_path):
        from app.scripts.CI import link_debts as ld
        assert ld.check_coordination_log(tmp_path / "coordination-log.md") == ([], True)

    def test_wired_into_selfcheck(self, tmp_path):
        from app.scripts.CI import selfcheck
        docs = tmp_path / "docs"; docs.mkdir()
        (docs / "traceability-matrix.md").write_text(
            "# Матрица\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n",
            encoding="utf-8")
        self._log(tmp_path, ["- 2026-10-09 | длинная | " + "y" * 700])
        report, _ = selfcheck.run(docs, None)
        assert any(l.startswith("i журнал координации:") for l in report)
        assert any("запись журнала «2026-10-09 | длинная»" in l for l in report)


def test_overdue_not_triggered_by_word_in_other_title(tmp_path):
    # FB-02 common-dictionary: долг data-model «Пользователь» — функция с
    # «пользователь» в заголовке целью не является
    docs = setup_docs(tmp_path, "сущность Пользователь")
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace(
        "PRC «Процесс обработки сообщения о блокировке»",
        "data-model «Пользователь»"), encoding="utf-8")
    make(docs / "srs/function/client/fun-cl-01-hint.md",
         "---\nid: FUN-CL-01\ntitle: '[УЛ] Клиент: Функция получения подсказки, "
         "что пользователь является УЛ'\n---\n# Ф\n")
    report, ok = check(mx, docs)
    assert ok and not any("ПРОСРОЧЕН" in r for r in report), report


def test_overdue_requires_same_type_when_known(tmp_path):
    # карточка с тем же заголовком, но другого типа (по реестру) — не цель;
    # того же типа — просрочка
    docs = setup_docs(tmp_path, "сущность Пользователь")
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace(
        "PRC «Процесс обработки сообщения о блокировке»",
        "data-model «Пользователь»"), encoding="utf-8")
    make(docs / "srs/screen-form/scr-bnk-01-user.md",
         "---\nid: SCR-BNK-01\ntitle: '[УЛ] Пользователь'\n---\n# Э\n")
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8")
                  + "| SCR-BNK-01 | screen-form | Пользователь | srs/screen-form/scr-bnk-01-user.md |\n",
                  encoding="utf-8")
    report, ok = check(mx, docs)
    assert ok and not any("ПРОСРОЧЕН" in r for r in report), report
    make(docs / "srs/data-model/ent-009-user.md",
         "---\nid: ENT-009\ntitle: '[УЛ] Пользователь'\n---\n# С\n")
    mx.write_text(mx.read_text(encoding="utf-8")
                  + "| ENT-009 | data-model | Пользователь | srs/data-model/ent-009-user.md |\n",
                  encoding="utf-8")
    report, ok = check(mx, docs)
    assert not ok and any("ПРОСРОЧЕН" in r and "ent-009-user.md" in r for r in report), report



NFR_PAGE = """---
id: nfr-prf
type: nfr
nfr_type: Производительность
ingress: reverse
confluence_page_ids: 123
---
# Производительность

| ID | Показатель | Норма | Не задано |
|---|---|---|---|
| nfr-prf-001 | Время отклика | ≤ 2 с | окно измерения |
"""


def _nfr_docs(tmp_path, gap_text):
    docs = setup_docs(tmp_path, "функция")
    make(tmp_path / "nfr/nfr-prf.md", NFR_PAGE)
    mx = docs / "traceability-matrix.md"
    # строка долга фикстуры целиком → запись реестра страницы типа + пробел
    mx.write_text(re.sub(
        r"(?m)^\| FUN-BNK-01…02 \|.*$",
        "| nfr-prf | nfr | Производительность | ../nfr/nfr-prf.md |\n"
        f"| nfr-prf | — | «{gap_text}» |",
        mx.read_text(encoding="utf-8")), encoding="utf-8")
    return docs, mx


def test_nfr_gap_is_not_overdue(tmp_path):
    # пробел НФТ: страница типа существует, но это не «цель существует»
    docs, mx = _nfr_docs(tmp_path, "окно измерения")
    report, ok = check(mx, docs)
    assert ok, report
    assert not any("ПРОСРОЧЕН" in r for r in report), report
    assert any("пробелов НФТ 1" in r for r in report), report


def test_nfr_gap_quote_must_be_on_page(tmp_path):
    # цитата пробела не на странице — долг неисполним
    docs, mx = _nfr_docs(tmp_path, "доля запросов")
    report, ok = check(mx, docs)
    assert not ok and any("НЕИСПОЛНИМ" in r and "доля запросов" in r
                          for r in report), report


def test_nfr_lowercase_ids_in_registry(tmp_path):
    # строчные nfr-ID реестра читаются как записи реестра
    registry, debts = parse_matrix(
        "| nfr | nfr | Реестр НФТ | ../nfr/README.md |\n"
        "| nfr-prf | nfr | Производительность | ../nfr/nfr-prf.md |\n"
        "| nfr-prf-001 | nfr | Время отклика | ../nfr/nfr-prf.md |\n"
        "| nfr-xx | nfr | мусор | ../nfr/x.md |\n")
    assert set(registry) == {"nfr", "nfr-prf", "nfr-prf-001"}, registry
