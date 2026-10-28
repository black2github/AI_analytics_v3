# tests/test_review_guards.py
"""Сторожа П1 разбора замечаний к миграции КК (2026-10-22), срез 1: B2 страница-копия,
B4 способ показа в контроле, B5 вызыватель без ссылки, B7 строка паспорта вне таблицы,
B9 счётчик OQ. Только ⚠/i; на каждый — срабатывание и НЕсрабатывание."""
from datetime import date
from pathlib import Path

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.checks import review_guards as rg


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid: str, title: str, typ: str, body: str = "текст\n") -> str:
    return f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\n---\n\n# {title}\n\n{body}"


# ---------------------------------------------------------------- B2

def test_b2_copy_title_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-1.md", card("FUN-1", "Копия Функция проверки в ЕСК", "function"))
    make(docs / "srs/contract-call/call-1.md", card("CALL-EXT-1", "[КК] Метод запроса (Копия)", "contract-call"))
    out = rg.check_copy_titles(docs)
    assert out[0].startswith("⚠ страница-копия перенесена как своя ×2")


def test_b2_word_inside_title_not_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-1.md", card("FUN-1", "[КК] Клиент: Функция выгрузки копии договора", "function"))
    make(docs / "srs/function/fun-2.md", card("FUN-2", "Копирование реквизитов", "function"))
    assert rg.check_copy_titles(docs) == []


# ---------------------------------------------------------------- B4

CTL = ("- **Сообщение об ошибке:** «Обязательное поле не заполнено»; способ отображения — ошибка "
       "обработки сообщения\n- **Сообщение об ошибке:** «Неверный формат», отображается под полем\n")


def test_b4_display_mode_in_error_field(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/control/cards-ent-1.md", card("CTL-1", "Контроли", "control", CTL))
    out = rg.check_control_display_mode(docs)
    assert out[0].startswith("⚠ способ показа в контроле — дом §7 ЭФ (controls.md): мест 2 в 1 файлах")


def test_b4_words_inside_quoted_message_or_other_field_not_flagged(tmp_path):
    # литерал сообщения в кавычках и другие поля — не способ показа
    body = ("- **Сообщение об ошибке:** «Модальное окно закрыто, повторите ввод»\n"
            "- **Логика проверки:** способ отображения не задан\n")
    docs = tmp_path / "docs"
    make(docs / "srs/control/cards-ent-1.md", card("CTL-1", "Контроли", "control", body))
    make(docs / "srs/function/fun-1.md", card("FUN-1", "Ф", "function", CTL))  # не контроль
    assert rg.check_control_display_mode(docs) == []


# ---------------------------------------------------------------- B5

def _caller_kit(tmp_path, item):
    docs = tmp_path / "docs"
    make(docs / "srs/screen-form/scr-cl-01.md", card("SCR-CL-01", '[КК_СК] ЭФ Клиента "Список карт"', "screen-form"))
    make(docs / "srs/data-model/ent-007.md", card("ENT-007", "[КК_ВК] Заявка на выпуск карты", "data-model"))
    make(docs / "srs/function/fun-1.md",
         card("FUN-1", "Функция", "function", f"## 3. Вызов функции\n\n- {item}\n\n## 4. Поведение\n\nшаг\n"))
    return docs


def test_b5_caller_without_link_flagged(tmp_path):
    docs = _caller_kit(tmp_path, 'при нажатии кнопки на ЭФ [КК_СК] ЭФ Клиента "Список карт" (нет целевого артефакта)')
    out = rg.check_caller_links(docs)
    assert out[0].startswith("⚠ вызыватель есть в комплекте, ссылки нет ×1")
    assert "SCR-CL-01" in out[1]


def test_b5_tagless_and_yo_match(tmp_path):
    docs = _caller_kit(tmp_path, "из ЭФ Клиента «Список карт»")
    assert rg.check_caller_links(docs)[1].endswith("«из ЭФ Клиента «Список карт»»")


def test_b5_linked_absent_or_non_caller_type_silent(tmp_path):
    # ссылка есть; цели нет; совпадение с сущностью (не вызыватель) — молчим
    for item in ('[SCR-CL-01 ЭФ Клиента "Список карт"](../screen-form/scr-cl-01.md)',
                 "из функции «[КК] Клиент: Функция входа в сервис КК» (нет целевого артефакта)",
                 "[КК_ВК] Заявка на выпуск карты"):
        docs = _caller_kit(tmp_path / str(abs(hash(item))), item)
        assert rg.check_caller_links(docs) == [], item


# ---------------------------------------------------------------- B7

PASSPORT = "| Поле | Значение |\n|---|---|\n| Назначение | X |\n\n"


def test_b7_passport_line_after_table(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/internal-contract/intc-1.md",
         card("INTC-1", "К", "internal-contract", PASSPORT + "Где используется:\n\n- ЭФ\n\nПривилегии:\n\n- П\n"))
    out = rg.check_passport_after_table(docs)
    assert out[0] == "⚠ строка паспорта вне таблицы — вернуть в таблицу: файлов 1"
    assert out[1].endswith("«Где используется», «Привилегии»")


def test_b7_lawful_forms_silent(tmp_path):
    docs = tmp_path / "docs"
    # строка справочника под заголовком (норма data-model) — до таблицы
    make(docs / "srs/data-model/dictionaries.md",
         card("DM-1", "Справочники", "data-model", "### Статусы\n\nГде используется: [ENT-1](e.md)\n\n" + PASSPORT))
    # отдельный подраздел после таблицы — заголовок сбрасывает «после таблицы»
    make(docs / "srs/internal-contract/intc-1.md",
         card("INTC-1", "К", "internal-contract", PASSPORT + "### Доступность\n\nПривилегии:\n\n- П\n"))
    # тип вне перечня
    make(docs / "srs/function/fun-1.md", card("FUN-1", "Ф", "function", PASSPORT + "Где используется:\n"))
    assert rg.check_passport_after_table(docs) == []


# ---------------------------------------------------------------- B9

OQ = ("# OQ\n\n## OQ-01 — 2026-08-01 — старый открытый\n\n- Статус: открыт\n\n"
      "## OQ-02 — 2026-10-20 — новый открытый\n\n- Статус: открыт\n\n"
      "## OQ-03 — 2026-08-01 — закрытый\n\n- Статус: закрыт 2026-08-02\n\n"
      "## OQ-04 — 2026-09-01 — частично\n\n- Статус: частично (вариант 1)\n\n"
      "## OQ-05 — 2026-09-02 — фиксация\n\n- Статус: зафиксировано\n\n"
      "## OQ-06 — 2026-09-03 — решён\n\n- Статус: решён\n\n"
      "## OQ-07 — 2026-09-04 — без статуса\n\n- Вопрос: ?\n")


def test_b9_counter(tmp_path):
    p = tmp_path / "open-questions.md"
    make(p, OQ)
    assert rg.oq_class_counter(p, today=date(2026, 10, 22)) == [
        "i OQ: всего 7, открыт 2, частично 1, зафиксировано 1, закрыт 2, прочие 1; "
        "открытых старше 30 дней — 1"]


def test_b9_no_journal_silent(tmp_path):
    assert rg.oq_class_counter(tmp_path / "open-questions.md") == []


# заголовки не по формату (FB-39 КК, 2026-10-28): запись считается, формат — отдельной строкой ⚠
OQ_ODD = ("# OQ\n\n## OQ-01 — 2026-08-01 — по формату\n\n- Статус: открыт\n\n"
          "## OQ-02 — TEAMTB-4518: без даты\n\n- Статус: открыт\n\n"
          "## OQ-03 — 01.08.2026 — дата не ISO\n\n- Статус: открыт\n\n"
          "## OQ-04 — 27.10.2026 — дата не ISO\n\n- Статус: частично закрыт (2026-10-28)\n\n"
          "## OQ-05 — 27.10.2026 — дата не ISO\n\n- Статус: закрыт\n\n"
          "## OQ-06 - 27.10.2026 - разделитель\n\n- Вопрос: без статуса\n")


def test_b9_odd_heads_counted_in_classes(tmp_path):
    # (а) все формы заголовка в «всего» и в классах; (д) запись без строки статуса — «прочие»
    p = tmp_path / "open-questions.md"
    make(p, OQ_ODD)
    out = rg.oq_class_counter(p, today=date(2026, 10, 28))
    assert out[0] == ("i OQ: всего 6, открыт 3, частично 1, зафиксировано 0, закрыт 1, прочие 1; "
                      "открытых старше 30 дней — 2")


def test_b9_odd_heads_warning_with_ranges(tmp_path):
    # (б) строка ⚠: номера подряд с одной причиной — диапазоном; причина разделителя — раньше даты
    p = tmp_path / "open-questions.md"
    make(p, OQ_ODD)
    out = rg.oq_class_counter(p, today=date(2026, 10, 28))
    assert out[1:] == ["⚠ заголовки реестра OQ не по формату «## OQ-NNN — ГГГГ-ММ-ДД — …» или "
                       "«## OQ-NNN. …»: 5 — "
                       "OQ-02 (нет даты), OQ-03 (дата 01.08.2026), OQ-04, OQ-05 (дата 27.10.2026), "
                       "OQ-06 (разделитель «-»)"]


def test_b9_dmy_date_counts_as_stale(tmp_path):
    # (в) дата ДД.ММ.ГГГГ входит в «старше 30 дней»; без даты — не входит
    p = tmp_path / "open-questions.md"
    make(p, "## OQ-1 — 01.08.2026 — старый\n\n- Статус: открыт\n\n"
            "## OQ-2 — без даты\n\n- Статус: открыт\n")
    assert rg.oq_class_counter(p, today=date(2026, 10, 28))[0].endswith("открытых старше 30 дней — 1")


def test_b9_canonical_heads_no_warning(tmp_path):
    # (г) без нестандартных заголовков строки ⚠ нет, вывод прежний (сверка — test_b9_counter)
    p = tmp_path / "open-questions.md"
    make(p, OQ)
    assert len(rg.oq_class_counter(p, today=date(2026, 10, 22))) == 1


def test_b9_head_defect_reasons():
    chk = rg._oq_head_check
    assert chk(" — 2026-08-01 — текст") == (date(2026, 8, 1), None)
    assert chk(" — 27.10.2026 — текст") == (date(2026, 10, 27), "дата 27.10.2026")
    assert chk(" - 27.10.2026 - текст")[1] == "разделитель «-»"
    assert chk(" — 2026-08-01—текст")[1] == "разделитель «—» без пробелов"
    assert chk(" 2026-08-01 — текст")[1] == "нет разделителя «—»"
    assert chk(" — 2026-08-01")[1] == "нет формулировки"
    assert chk(" — ENT-007: 2026-08-01") == (None, "нет даты")
    assert chk("") == (None, "нет даты")
    # вторая форма нормы — «## OQ-NNN. <формулировка>» без даты: по форме, в давность не входит
    assert chk(". Расхождение копии") == (None, None)
    assert chk(".Без пробела")[1] == "нет даты"


def test_b9_dot_form_no_warning(tmp_path):
    # журнал формы «## OQ-NNN. …» (стенд, эталон, команды): счётчик есть, строки ⚠ нет;
    # прежняя регулярка такой журнал не видела вовсе — строки «i OQ» не было
    p = tmp_path / "open-questions.md"
    make(p, "## OQ-001. Первый\n\n- **Статус:** открыт\n\n## OQ-002. Второй\n\n- **Статус:** закрыт\n")
    assert rg.oq_class_counter(p, today=date(2026, 10, 28)) == [
        "i OQ: всего 2, открыт 1, частично 0, зафиксировано 0, закрыт 1; открытых старше 30 дней — 0"]


def test_b9_code_block_example_not_an_entry(tmp_path):
    # образец формата в блоке кода записью не является — как у порядка реестра link_debts
    p = tmp_path / "open-questions.md"
    make(p, "```\n## OQ-001 — 2026-01-01 — образец\n- Статус: открыт\n```\n\n"
            "## OQ-01 — 2026-10-20 — запись\n\n- Статус: открыт\n")
    assert rg.oq_class_counter(p, today=date(2026, 10, 28))[0].startswith("i OQ: всего 1, открыт 1,")


def test_oq_entry_boundary_one_for_guard_gate_and_order(tmp_path):
    # одна граница записи у B9, гейта переноса и порядка реестра: нестандартные заголовки не теряются
    from app.scripts.CI import link_debts as ld, transfer_gate as tg
    p = tmp_path / "open-questions.md"
    make(p, OQ_ODD)
    assert ld.check_oq_order(p)[0][0] == "open-questions: порядок реестра append-only соблюдён (6 записей) ✓"
    _, opened = tg.open_questions(tmp_path, tmp_path, explicit=p)
    assert opened == ["OQ-01", "OQ-02", "OQ-03", "OQ-04", "OQ-06 (без строки «Статус»)"]


# ---------------------------------------------------------------- подключение к selfcheck

def test_selfcheck_runs_guards_without_verdict_change(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-1.md", card("FUN-1", "Копия Функция", "function"))
    make(docs / "traceability-matrix.md",
         "# М\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n| FUN-1 | function | Ф | srs/function/fun-1.md |\n")
    make(tmp_path / "open-questions.md", OQ)
    report, ok = selfcheck.run(docs, None)
    assert any(ln.startswith("⚠ страница-копия перенесена как своя ×1") for ln in report)
    assert any(ln.startswith("i OQ: всего 7") for ln in report)
    report2, ok2 = selfcheck.run(docs, None)
    assert ok == ok2


# ================================================================ срез 2

# ---------------------------------------------------------------- B1

def test_b1_button_without_fields_and_messages_list(tmp_path):
    body = ("## 6. Кнопки\n\n### B-1. «Удалить заявку»\n\n- **Видимость:** всегда\n- Шаг 1. удалить. Шаг 2. закрыть\n\n"
            "### B-2. Кнопка сворачивания\n\nтекст\n\n## 7. Сообщения\n\n- MSG-1 — «Ошибка»\n")
    docs = tmp_path / "docs"
    make(docs / "srs/screen-form/scr-1.md", card("SCR-CL-01", "ЭФ", "screen-form", body))
    out = rg.check_button_fields(docs)
    assert out[0].startswith("⚠ кнопка B-N без полей шаблона (Видимость / При нажатии) ×2")
    assert out[1].endswith("B-1 — нет «При нажатии»") and out[2].endswith("B-2 — нет «Видимость», «При нажатии»")
    assert any(ln.startswith("⚠ сообщения ЭФ списком") for ln in out)


def test_b1_prose_instead_of_field_flagged(tmp_path):
    # «При нажатии проводятся…» — проза, не поле «ярлык: значение»; видимость в скобках
    # заголовка — тоже не поле
    body = ("## 6. Кнопки\n\n### B-1. «Продолжить»\n\n- **Видимость:** всегда\n- При нажатии проводятся проверки\n\n"
            "### B-2. «Действия» (в строке записи; отображается всегда)\n\n- **При нажатии:** меню\n")
    docs = tmp_path / "docs"
    make(docs / "srs/screen-form/scr-1.md", card("SCR-CL-01", "ЭФ", "screen-form", body))
    out = rg.check_button_fields(docs)
    assert out[1].endswith("B-1 — нет «При нажатии»") and out[2].endswith("B-2 — нет «Видимость»")


def test_b1_lawful_forms_silent(tmp_path):
    body = ("## 6. Кнопки\n\n### B-1. «Сохранить»\n\n- **Видимость:** всегда\n- **При нажатии:** сохранить\n\n"
            "### B-2. «Продолжить»\n\n- Видимость: всегда\n- **При нажатии**: проверки группы 5\n\n"
            "### B-3. «Действия»\n\n**Видимость:** в строке записи\n\nПри нажатии: отображается меню\n\n"
            "## 7. Сообщения\n\n| ID | Тип | Показ | Содержание |\n|---|---|---|---|\n| MSG-1 | Информер | B-1 | «Ошибка» |\n")
    docs = tmp_path / "docs"
    make(docs / "srs/screen-form/scr-1.md", card("SCR-CL-01", "ЭФ", "screen-form", body))
    make(docs / "srs/function/fun-1.md", card("FUN-1", "Ф", "function", "### B-1. не ЭФ\n"))
    assert rg.check_button_fields(docs) == []


# ---------------------------------------------------------------- B3

def test_b3_thick_call_flagged(tmp_path):
    body = ("**Базовый контракт:** [EXTINT-F1-008](https://x/-/blob/HEAD/f1/e.md)\n\n## Назначение\n\nX\n\n"
            "### Паспорт метода взаимодействия\n\n| a | b |\n\n### Атрибутный состав представления VW_X\n\n| c |\n")
    docs = tmp_path / "docs"
    make(docs / "srs/contract-call/external/call-ext-001.md", card("CALL-EXT-001", "В", "contract-call", body))
    make(docs / "srs/contract-call/external/call-ext-010.md", card("CALL-EXT-010", "В", "contract-call",
         "**Базовый контракт:** [EXTINT-TESSA-001](https://x/-/blob/HEAD/tessa/e.md)\n\n### Логика работы\n\nшаги\n"))
    out = rg.check_thick_calls(docs)
    assert out[0].startswith("⚠ карточка вызова не тонкая") and out[0].endswith("×2")
    assert out[1].endswith("«Паспорт метода взаимодействия», «Атрибутный состав»")
    assert out[2].endswith("call-ext-010.md: «Логика работы»")


def test_b3_thin_call_or_no_base_link_silent(tmp_path):
    docs = tmp_path / "docs"
    thin = ("**Базовый контракт:** [EXTINT-F1-008](https://x/-/blob/HEAD/f1/e.md)\n\n## Назначение\n\nX\n\n"
            "## Использование в сервисе\n\n### Транспорт\n\nODS\n")
    make(docs / "srs/contract-call/external/call-ext-001.md", card("CALL-EXT-001", "В", "contract-call", thin))
    # до переноса базы (временный снимок, ссылки на базу нет) — разделы законны
    snap = "## Назначение\n\nX\n\n### Временный снимок контракта\n\n### Паспорт метода взаимодействия\n\n| a |\n"
    make(docs / "srs/contract-call/external/call-ext-002.md", card("CALL-EXT-002", "В", "contract-call", snap))
    assert rg.check_thick_calls(docs) == []


# ---------------------------------------------------------------- B6 (а)

def test_b6a_glued_cell_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-1.md", card("FUN-1", "Ф", "function",
         "| Поле | Тип | Формат |\n|---|---|---|\n| Код | Строка(19)Допустимый алфавит: цифры | — |\n"
         "| Сумма | Число(19,2)Положительное | — |\n"))
    out = rg.check_cell_glue(docs)
    assert out[0] == "⚠ склейка абзацев ячейки источника — вставить <br>: мест 2 в 1 файлах"


def test_b6a_lawful_cells_silent(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-1.md", card("FUN-1", "Ф", "function",
         "| Поле | Тип |\n|---|---|\n| Код | Строка(19)<br>Допустимый алфавит |\n| ИНН | Строка(12) ОГРН/ОГРНИП |\n"
         "\nСтрока(19)Вне таблицы — не ячейка\n"))
    assert rg.check_cell_glue(docs) == []


# ---------------------------------------------------------------- B6 (б)

def _norm_kit(tmp_path, normalized=True):
    root = tmp_path / "kit"
    docs, src = root / "docs", root / "sources/confluence"
    make(src / "p1.md", "---\nconfluence_page_id: '2166860395'\n---\n\n<table><tr><td><p>Строка(19)</p><p>Алфавит</p></td></tr></table>\n")
    make(src / "p2.md", "---\nconfluence_page_id: '2166860396'\n---\n\nтекст без таблиц\n")
    make(docs / "srs/function/fun-1.md",
         "---\nid: FUN-1\ntitle: 'Ф'\ntype: function\nconfluence_page_ids: ['2166860395']\n---\n\n| a | b |\n|---|---|\n| x | y |\n")
    make(docs / "srs/function/fun-2.md",
         "---\nid: FUN-2\ntitle: 'Ф2'\ntype: function\nconfluence_page_ids: ['2166860396']\n---\n\n| a | b |\n|---|---|\n| x | y |\n")
    if normalized:
        (root / "sandbox/normalized").mkdir(parents=True)
    idx, _ = selfcheck.index_sources(src)
    return docs, idx


def test_b6b_unnormalized_source_flagged(tmp_path):
    docs, idx = _norm_kit(tmp_path)
    out = rg.check_unnormalized_sources(docs, idx)
    assert out[0] == ("⚠ источник с таблицами перенесён без нормализованной копии (протокол §5): "
                      "1 карточек (srs/function/fun-1.md)")
    assert out[1] == "   · srs/function/fun-1.md ← 2166860395"  # перечень — только в --out


def test_b6b_copy_present_or_no_normalized_dir_silent(tmp_path):
    docs, idx = _norm_kit(tmp_path / "a")
    make(docs.parent / "sandbox/normalized/ISS-01/p1.md", "---\nconfluence_page_id: '2166860395'\n---\n\n| x |\n")
    assert rg.check_unnormalized_sources(docs, idx) == []
    docs2, idx2 = _norm_kit(tmp_path / "b", normalized=False)
    assert rg.check_unnormalized_sources(docs2, idx2) == []


# ---------------------------------------------------------------- B8

def test_b8_not_a_function_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-cl-51.md",
         "---\nid: FUN-CL-51\ntitle: '[КК_ВК] СПП Заявки на выпуск карты'\ntype: function\nkind: operation\n---\n\n"
         "## 1. Назначение\n\nX\n\n## 5. Состав\n\n| Поле | № |\n")
    make(docs / "srs/function/fun-cl-50.md",
         "---\nid: FUN-CL-50\ntitle: '[КК_ВК] Клиент: Параметры вызова универсальной функции ЭП'\ntype: function\n---\n\n"
         "## 5. Поведение\n\nПараметры перечислены таблицей.\n")
    out = rg.check_function_kind_suspect(docs)
    assert out[0].startswith("⚠ похоже не функция ×2")


def test_b8_function_with_steps_or_other_title_silent(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-cl-22.md",
         "---\nid: FUN-CL-22\ntitle: '[КК_ЛК] Клиент: Параметры вызова функции проверки ЭП'\ntype: function\nkind: operation\n---\n\n"
         "## Поведение\n\n- **Шаг 1.** Вызывающий процесс передаёт параметры\n")
    make(docs / "srs/function/fun-1.md",
         "---\nid: FUN-1\ntitle: 'Клиент: Функция просмотра составителей'\ntype: function\nkind: operation\n---\n\nX\n")
    make(docs / "srs/function/fun-2.md",
         "---\nid: FUN-2\ntitle: 'СПП библиотеки'\ntype: function\nkind: library\n---\n\nX\n")
    assert rg.check_function_kind_suspect(docs) == []
