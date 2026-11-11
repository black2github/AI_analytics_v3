# tests/test_call_algorithms.py
"""Сторож «в карточке вызова нет алгоритмов» (шаблон contract-call.md, раздел B, 11.11.2026;
постановка прибору 2026-11-11, правило признака 1 — вариант B, принят 11.11): ⚠ — раздел вне
состава карточки, прежнее имя раздела (отдельно), «Процессы» не указатель, шаги вне таблиц
привязки; i — раздел «Из источника, вне разделов шаблона», нет раздела «Процессы».
Ограничители: условие значения и присваивания в привязке, временный снимок контракта, блоки
кода, карточки других типов и README — вне проверки."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.call_algorithms import analyse, check_call_algorithms

OUT = "   · "
LF = chr(10)
HEAD = "---\nid: CALL-EXT-001\ntitle: 'Вызов'\ntype: contract-call\nservice: x\n---\n\n# CALL-EXT-001. Вызов\n\n"
PROC_OK = ("### Процессы\n\n| Процесс / функция | Шаг / место |\n|---|---|\n"
           "| [FUN-001 Функция](../function/fun-001.md) | Шаг 4. Формирование запроса |\n\n")
BIND_OK = ("### Правила заполнения исходящего сообщения\n\n| Параметр контракта | Правило сервиса |\n"
           "|---|---|\n| `code` | **Если** атрибут пуст, **то** = \"0\" |\n\n"
           "### Сопоставление входящего сообщения\n\n| Параметр контракта | Куда записывается в сервисе |\n"
           "|---|---|\n| `result` | [ENT-001 Заявка](../ent-001.md).«Статус» |\n")


def card(body: str = "", procs: str = PROC_OK, binding: str = BIND_OK, purpose: str = "") -> str:
    return (HEAD + "**Базовый контракт:** [EXTINT-X-001](https://h/x.md)\n\n## Назначение\n\n"
            "Сервис обращается к АС X.\n\n" + purpose + "## Использование в сервисе «Сервис»\n\n"
            + procs + "### Транспорт\n\nВ постановке не задано.\n\n" + binding + body)


def s(text: str, key: str):
    return analyse(text)[key]


def silent(text: str, *, but=()) -> bool:
    return not any(v for k, v in analyse(text).items() if k not in but)


# --- норма: карточка по шаблону — тихо по всем признакам ---

def test_template_card_silent():
    assert silent(card())


def test_heading_variants_silent():
    # номер раздела, «ё», двоеточие в конце и регистр не делают раздел чужим
    t = card().replace("## Назначение", "## 1. Назначение:").replace(
        "### Транспорт", "### ТРАНСПОРТ")
    assert s(t, "s1") == []


# --- признак 1: раздел вне состава ---

def test_logic_section_outside_composition():
    t = card(body="\n## Логика работы\n\nТекст.\n")
    assert [w for _n, w in s(t, "s1")] == ["«Логика работы» — раздел вне состава"]


def test_template_h3_under_wrong_h2():
    # H3 из состава под чужим H2 и «Где используется» внутри «Назначения» — вне состава
    t = card(purpose="### Где используется\n\n- [FUN-001](f.md)\n\n")
    assert [w for _n, w in s(t, "s1")] == [
        "«Где используется» — раздел вне состава; указатель мест вызова — в «Процессы»"]


def test_old_section_name_is_own_kind():
    t = card(binding=BIND_OK.replace("Сопоставление входящего сообщения", "Обработка входящих ответов"))
    # своим счётчиком: в «вне состава» не смешивается
    assert s(t, "s1") == []
    out = s(t, "s1old")
    assert len(out) == 1 and out[0][1] == ("«Обработка входящих ответов» — теперь "
                                           "«Сопоставление входящего сообщения»")


def test_binding_subsection_prose_vs_table():
    prose = BIND_OK.replace("### Сопоставление",
                            "#### UI-компонент вывода статистики\n\nКомпонент формирует вывод.\n\n### Сопоставление")
    out = s(card(binding=prose), "s1")
    assert [w for _n, w in out] == ["«UI-компонент вывода статистики» — подраздел таблицы привязки: "
                                    "текст сверх таблицы и присваиваний"]
    # подраздел с таблицей параметров — привязка данных (CALL-INT-007 КК «Заполнение параметров»)
    table = BIND_OK.replace("### Сопоставление",
                            "#### Заполнение параметров\n\n| № | Параметр |\n|---|---|\n| 1 | = 0 |\n\n### Сопоставление")
    assert s(card(binding=table), "s1") == []


def test_snapshot_and_common_sections_silent():
    # ограничитель: временный снимок контракта с таблицами запроса и ответа — не признак;
    # общие для типов «Приложенные артефакты» и «Из источника, вне разделов шаблона» — тоже
    snap = ("### Временный снимок контракта\n\nИсточник снимка: файл, 2026-11-01.\n\n#### Запрос\n\n"
            "| Параметр | Тип |\n|---|---|\n| a | Строка |\n\n#### Ответ\n\nШаг 1. ответ владельца\n\n")
    t = card(purpose=snap, body="\n## Приложенные артефакты\n\n- [s.xsd](files/s.xsd)\n\n"
                                "## Из источника, вне разделов шаблона\n\n- Метка: значение\n")
    assert silent(t, but=("i_src",))
    assert [w for _n, w in s(t, "i_src")] == ["Из источника, вне разделов шаблона"]


def test_heading_in_code_block_silent():
    t = card(body="\n```markdown\n## Логика работы\n**Шаг 1.** x\n```\n")
    assert silent(t)


# --- признак 2: «Процессы» не указатель ---

def test_processes_three_columns():
    procs = ("### Процессы\n\n| Процесс / функция | Шаг / место | Описание |\n|---|---|---|\n"
             "| [FUN-001](f.md) | Шаг 1 | Выполняется запрос |\n\n")
    out = s(card(procs=procs), "s2")
    assert len(out) == 1 and "таблица в 3 колонки" in out[0][1]


def test_processes_branch_in_cell():
    procs = PROC_OK.replace("Шаг 4. Формирование запроса", "**Если** признак, **то** шаг 4")
    assert [w for _n, w in s(card(procs=procs), "s2")] == ["ветвление в ячейке"]


def test_sentence_boundary_ignores_step_number_and_abbreviation():
    for place in ("Шаг 12. Формирование запроса", "Шаг 4, п. 2 «Проверка»", "раздел «Поведение», см. Шаг 3"):
        procs = PROC_OK.replace("Шаг 4. Формирование запроса", place)
        assert s(card(procs=procs), "s2") == [], place


def test_processes_retelling_in_cell():
    procs = PROC_OK.replace("Шаг 4. Формирование запроса",
                            "Шаг 4. Выполняется запрос в АС. Ответ сохраняется в заявку")
    assert [w for _n, w in s(card(procs=procs), "s2")] == ["текст сверх ссылки и места вызова"]
    br = PROC_OK.replace("Шаг 4. Формирование запроса", "Шаг 4<br>затем шаг 5")
    assert [w for _n, w in s(card(procs=br), "s2")] == ["текст сверх ссылки и места вызова"]


def test_processes_prose_instead_of_table():
    procs = "### Процессы\n\nСервис вызывает метод при открытии формы.\n\n"
    assert [w for _n, w in s(card(procs=procs), "s2")] == ["проза вместо таблицы-указателя"]


def test_processes_pointer_phrase_and_link_list_silent():
    # ограничитель: одна фраза-указатель со ссылкой; список ссылок с местом вызова
    one = "### Процессы\n\nВызов — из функции [FUN-001 Функция](f.md), шаг №5.\n\n"
    lst = "### Процессы\n\n- [FUN-001](f.md) — шаг 5.\n- [PROC-002](p.md) — шаг 2.\n\n"
    assert s(card(procs=one), "s2") == [] and s(card(procs=lst), "s2") == []


# --- признак 3: шаги вне таблиц привязки ---

def test_steps_in_out_of_template_section():
    body = "\n## Алгоритм выполнения метода\n\n**Шаг 1.** ФЛК запроса.\n\nПри ошибке — переход на шаг 3.\n"
    t = card(body=body)
    lines = t.splitlines()
    out = s(t, "s3")
    assert [lines[n - 1] for n, _w in out] == ["**Шаг 1.** ФЛК запроса.", "При ошибке — переход на шаг 3."]


def test_step_jump_in_purpose():
    t = card(purpose="После ответа переход к шагу №2 функции.\n\n")
    assert len(s(t, "s3")) == 1


def test_steps_in_old_named_section_counted():
    # раздел с прежним именем таблицей привязки не считается: ссылка на номер шага — признак
    old = ("### Обработка входящих ответов\n\n| Параметр | Куда |\n|---|---|\n"
           "| code | Шаг №3 [PROC-030](p.md): переход на шаг №9 |\n")
    assert len(s(card(binding=old), "s3")) == 1


def test_value_condition_in_binding_not_signal():
    # ограничитель: условие значения в таблицах привязки — не признак
    b = BIND_OK.replace("| `code` |", "| `code` | **Если** признак, **то** = \"1\", **иначе** = \"2\" |"
                        + LF + "| `x` |")
    assert silent(card(binding=b))


def test_step_label_in_binding_table_is_sign3():
    b = BIND_OK.replace("| `result` |", "| Шаг 1 `result` |")
    assert len(s(card(binding=b), "s3")) == 1


def test_step_place_in_processes_not_sign3():
    # «Шаг 4» в колонке места вызова — указатель; признак 3 «Процессы» не читает
    assert s(card(), "s3") == []


def test_line_numbers_survive_multiline_comment():
    body = "\n<!-- комментарий\nв две строки -->\n## Логика работы\n"
    t = card(body=body)
    n = s(t, "s1")[0][0]
    assert t.splitlines()[n - 1] == "## Логика работы"


# --- уровень комплекта: типы, README, строки отчёта ---

def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_kit_lines_and_other_types_silent(tmp_path):
    docs = tmp_path / "docs"
    bad = card(body="\n## Логика работы\n\n**Шаг 1.** x\n")
    _w(docs / "srs/contract-call/external/call-ext-001-x.md", bad)
    _w(docs / "srs/contract-call/external/call-ext-002-y.md", card().replace("CALL-EXT-001", "CALL-EXT-002"))
    # тот же текст у карточки собственного метода, базового контракта и README — вне проверки
    _w(docs / "srs/internal-contract/intc-001.md", bad.replace("type: contract-call", "type: internal-contract"))
    _w(docs / "srs/contract-call/README.md", bad.replace("type: contract-call", "type: contract-call-registry"))
    _w(docs / "srs/contract-call/external/README.md", bad)
    _w(docs / "ext/extint-x-001.md", bad.replace("type: contract-call", "type: external-integration"))
    rep = check_call_algorithms(docs)
    heads = [l for l in rep if not l.startswith(OUT)]
    assert len(heads) == 2, rep
    assert heads[0].startswith("⚠ карточка вызова — раздел вне состава карточки вызова: "
                               "1 карточек (CALL-EXT-001) — шаги и ветвления — в вызывающую функцию")
    assert "алгоритм" not in heads[0]  # прибор смысл заголовка не различает
    assert "формат метода, коды, примеры — в контракт владельца или раздел «Временный снимок" in heads[0]
    assert heads[0].endswith("вырезать из карточки только при подтверждённом доме-приёмнике")
    assert heads[1].startswith("⚠ карточка вызова — шаги в тексте карточки, в том числе в разделах привязки")
    rows = [l for l in rep if l.startswith(OUT)]
    assert rows and all(r.startswith(OUT + "srs/contract-call/external/call-ext-001-x.md:") for r in rows)


def test_selfcheck_line_does_not_change_verdict(tmp_path):
    from app.scripts.CI import selfcheck as sc
    chk = [c for c in sc.KIT_CHECKS if getattr(c, "id", None) == "call_algorithms"]
    assert len(chk) == 1 and chk[0].affects_verdict is False
    # прогон комплекта: строка ⚠ есть, вердикт тот же, что у комплекта без находок
    docs = tmp_path / "docs"
    _w(docs / "srs/contract-call/external/call-ext-001-x.md", card(body=LF + "## Логика работы" + LF))
    rep, _ok = chk[0].run(type("Ctx", (), {"docs": docs})())
    assert _ok is True and rep[0].startswith("⚠ карточка вызова — раздел вне состава")


def test_gate_line_without_blocking(tmp_path):
    # строка гейта — ⚠ с числом карточек; блокеры те же, что у карточки без находок
    from tests.test_transfer_gate import _run, make_src, _w as gw
    src = make_src(tmp_path)
    path = src / "docs/srs/contract-call/external/call-ext-001-x.md"
    gw(path, card())
    lines0, ready0, data0 = _run(src)
    assert not [l for l in lines0 if "карточка вызова — " in l]
    gw(path, card(body=LF + "## Логика работы" + LF + LF + "**Шаг 1.** x" + LF))
    lines, ready, data = _run(src)
    hits = [l for l in lines if "карточка вызова — " in l]
    assert len(hits) == 2 and all(h.startswith("⚠ ") for h in hits), hits
    assert ready == ready0 and data["blockers"] == data0["blockers"]
    assert not any("· srs/" in l for l in lines)  # перечень — только в --out selfcheck


# --- привязка списком присваиваний (уточнение владельца 11.11): равноценна таблице ---

ASSIGN = ("- <Пользователь> = [ENT-007 Заявка](e.md).«Автор»;" + LF
          + "- <Канал> = \"ЭКО\";" + LF
          + "- <Признак> = **Если** заявка срочная, **то** = true, **иначе** = false." + LF)


def _sub(body: str) -> str:
    return card(binding=BIND_OK.replace("### Сопоставление",
                                        "#### Заполнение параметров" + LF + LF + body + LF + "### Сопоставление"))


def test_subsection_of_assignments_silent():
    assert s(_sub(ASSIGN), "s1") == []


def test_subsection_intro_plus_assignments_or_tables_silent():
    assert s(_sub("Параметры заполняются так:" + LF + LF + ASSIGN), "s1") == []
    # подпись перед каждой таблицей — вводная строка (CALL-INT-007 КК: «Набор …: Запись №1»)
    two = LF.join(["Заполнение:", "", "| № | П |", "|---|---|", "| 1 | = 0 |", "", "**Запись №1**", "",
                   "| № | П |", "|---|---|", "| 2 | = 1 |", ""])
    assert s(_sub(two), "s1") == []


def test_assignment_with_value_condition():
    from app.scripts.CI.kitcheck.checks.call_algorithms import is_assignment
    assert is_assignment("- <Признак> = **Если** заявка срочная, **то** = true, **иначе** = false.")
    assert is_assignment("**Если** атрибут пуст, **то** = \"0\"")
    assert not is_assignment("Если a == b, выполняется запрос.")
    assert not is_assignment("Компонент формирует вывод статистики.")


def test_subsection_assignments_plus_paragraph_is_signal():
    body = ASSIGN + LF + "После заполнения выполняется запрос, при ошибке форма закрывается." + LF
    out = s(_sub(body), "s1")
    assert [w for _n, w in out] == ["«Заполнение параметров» — подраздел таблицы привязки: "
                                    "текст сверх таблицы и присваиваний"]
    # три вводные строки подряд — текст сверх привязки (вводная часть — не больше двух)
    assert s(_sub("Первая фраза." + LF + "Вторая фраза." + LF + "Третья фраза." + LF + LF + ASSIGN), "s1") != []


def test_empty_wrapper_subsection_judged_by_children():
    # H4-обёртка без своих строк: судят вложенные H5 (CALL-INT-009 КК)
    body = LF.join(["##### Входные параметры", "", "На вход подаётся массив.", "", "##### Состав", ""]) + ASSIGN
    out = [w for _n, w in s(_sub(body), "s1")]
    assert out == ["«Входные параметры» — подраздел таблицы привязки: текст сверх таблицы и присваиваний"]


def test_processes_assignment_is_not_prose():
    procs = LF.join(["### Процессы", "", "- Вызывающая функция = [FUN-001](f.md), шаг 5", "- Канал = веб", "", ""])
    assert s(card(procs=procs), "s2") == []


def test_info_no_processes_section():
    t = card(procs=LF.join(["### Где используется", "", "- [FUN-001](f.md)", "", ""]))
    assert [w for _n, w in s(t, "i_noproc")] == ["нет раздела «Процессы»"]
    assert s(card(), "i_noproc") == []


def test_kit_info_lines(tmp_path):
    docs = tmp_path / "docs"
    _w(docs / "srs/contract-call/external/call-ext-001-x.md",
       card(procs="", body=LF.join(["", "## Из источника, вне разделов шаблона", "", "- Метка: значение", ""])))
    rep = check_call_algorithms(docs)
    heads = [l for l in rep if not l.startswith(OUT)]
    assert heads == [
        "i карточка вызова — раздел «Из источника, вне разделов шаблона»: 1 карточек (CALL-EXT-001) — "
        "признаком не считается; проверить, что в нём нет шагов и ветвлений",
        "i карточка вызова — нет раздела «Процессы»: 1 карточек (CALL-EXT-001) — места вызова не указаны"]
    assert OUT + "srs/contract-call/external/call-ext-001-x.md" in rep


def test_processes_summary_split(tmp_path):
    # сводка признака 2: всего и из них с ветвлением, текстом в ячейке или прозой
    docs = tmp_path / "docs"
    three = ("### Процессы\n\n| Процесс / функция | Шаг / место | Описание |\n|---|---|---|\n"
             "| [FUN-001](f.md) | Шаг 1 | Инициализация цепочки |\n\n")
    body = three.replace("Инициализация цепочки", "Выполняется запрос. Ответ сохраняется в заявку")
    _w(docs / "srs/contract-call/external/call-ext-001-x.md", card(procs=three))
    _w(docs / "srs/contract-call/external/call-ext-002-y.md",
       card(procs=body).replace("CALL-EXT-001", "CALL-EXT-002"))
    head = [l for l in check_call_algorithms(docs) if "«Процессы» не указатель" in l]
    assert len(head) == 1
    assert ": 2 карточек (CALL-EXT-001, CALL-EXT-002), из них с ветвлением или текстом в ячейке " \
           "либо прозой — 1 — " in head[0]


def test_step_jump_in_description_cell_is_text():
    procs = ("### Процессы\n\n| Процесс / функция | Шаг / место | Описание |\n|---|---|---|\n"
             "| [FUN-001](f.md) | Шаг 1 | при ошибке переход на шаг 5 |\n\n")
    kinds = [w for _n, w in s(card(procs=procs), "s2")]
    assert kinds[1:] == ["текст сверх ссылки и места вызова"]



# --- лазейка «шаги присваиваниями» в разделах привязки (вопрос владельца 11.11) ---

STEPS_ASSIGN = LF.join([
    "- **Шаг 1.** <Пользователь> = [ENT-007](e.md).«Автор»;",
    "- **Шаг 2.** **Если** статус = \"NEW\", **то** <Тип> = \"A\", **иначе** переход на шаг 4;", ""])
STEPS_PROSE = LF.join(["**Шаг 1.** Формируется запрос.", "", "**Шаг 2.** Выполняется вызов.", ""])
OUT_RULES = "### Правила заполнения исходящего сообщения" + LF + LF


def _rules_body(body: str) -> str:
    return card(binding=BIND_OK.replace(OUT_RULES, OUT_RULES + body + LF))


def test_loophole_steps_as_assignments_in_section():
    t = _rules_body(STEPS_ASSIGN)
    assert [w for _n, w in s(t, "s1")] == [
        "«Правила заполнения исходящего сообщения» — текст в разделе привязки сверх таблицы и присваиваний"]
    assert len(s(t, "s3")) == 2


def test_loophole_steps_as_assignments_in_subsection():
    t = _sub(STEPS_ASSIGN)
    assert [w for _n, w in s(t, "s1")] == [
        "«Заполнение параметров» — подраздел таблицы привязки: текст сверх таблицы и присваиваний"]
    assert len(s(t, "s3")) == 2


def test_loophole_step_prose_in_section():
    t = _rules_body(STEPS_PROSE)
    assert len(s(t, "s1")) == 1 and len(s(t, "s3")) == 2


def test_binding_section_body_allowed_forms():
    # «В постановке не задано», вводная строка перед таблицей и перед подразделом — не признак
    t = card(binding=BIND_OK.replace(OUT_RULES, OUT_RULES + "Параметры заполняются так:" + LF + LF)
             .replace("### Сопоставление входящего сообщения" + LF + LF,
                      "### Сопоставление входящего сообщения" + LF + LF + "В постановке не задано." + LF + LF))
    assert silent(t)
    intro_sub = BIND_OK.replace("### Сопоставление",
                                "Раздел описывает заполнение:" + LF + LF + "#### Заполнение параметров"
                                + LF + LF + ASSIGN + LF + "### Сопоставление")
    assert silent(card(binding=intro_sub))


# --- вводная часть перед таблицей: до двух строк, в каждой одно предложение (правка 11.11) ---

TABLE = LF.join(["| Параметр | Правило |", "|---|---|", "| `code` | = 0 |", ""])


def test_two_single_sentence_intro_lines_silent():
    # INT-004/005/006/010 КК: две дословные фразы источника перед таблицей
    body = LF.join(["Данный раздел описывает заполнение параметров функции.",
                    "Для инициации метода нужно заполнить параметры:", "", ""]) + TABLE
    assert s(_rules_body(body), "s1") == []


def test_intro_line_with_two_sentences_is_text():
    body = ("Сначала система формирует запрос. Затем проверяет ответ и при ошибке повторяет вызов."
            + LF + LF + TABLE)
    assert [w for _n, w in s(_rules_body(body), "s1")] == [
        "«Правила заполнения исходящего сообщения» — текст в разделе привязки сверх таблицы и присваиваний"]


def test_three_intro_lines_is_text():
    body = LF.join(["Первая фраза.", "Вторая фраза.", "Третья фраза.", "", ""]) + TABLE
    assert len(s(_rules_body(body), "s1")) == 1


def test_intro_with_branch_notation_is_text():
    body = "**Если** заявка срочная, параметры такие:" + LF + LF + TABLE
    assert len(s(_rules_body(body), "s1")) == 1
