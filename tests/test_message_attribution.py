# tests/test_message_attribution.py
"""FB-12 КК (замер 2026-10-29, решение владельца 29.10): сторож приписки источнику обратного
направления — карточка контроля задаёт текст сообщения, а ячейка сообщения однозначно
сопоставленной строки источника пуста и не объединена. Только ⚠ / i, вердикт не меняется."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.card_run import check_file
from app.scripts.CI.kitcheck.checks.card_controls import message_attribution, message_rows

HEAD = ("<table><tbody>"
        "<tr><th>№</th><th>Проверяемый реквизит</th><th>Название проверки</th>"
        "<th>Логика выполнения проверки</th><th>Сообщение об ошибке</th></tr>")


def _src(rows: str, head: str = HEAD) -> str:
    return "---\ntitle: 'Контроли'\nconfluence_page_id: '111'\n---\n\n" + head + rows + "</tbody></table>\n"


def _card(cid: str, title: str, logic: str, msg: str) -> str:
    return (f"### {cid}. {title}\n\n- **Проверяемый атрибут:** «{title.split(':')[0]}».\n"
            f"- **Логика проверки:** {logic}\n- **Сообщение об ошибке:** {msg}\n"
            "- **Группы:** CTL-GRP-1.\n\n")


def _file(tmp_path: Path, body: str, pids: str = "['111']") -> Path:
    p = tmp_path / "cards-ent-023-card-limit.md"
    head = "---\npartOf: CTL-046\ntitle: 'Контроли'\ntype: control\n"
    if pids:
        head += f"confluence_page_ids: {pids}\n"
    p.write_text(head + "entity: ENT-023\n---\n\n# Контроли\n\n" + body, encoding="utf-8")
    return p


# CTL-052 КК: текст «Укажите новое значение» стоит в соседних строках, в своей — пусто
LIMITS = _src(
    "<tr><td>1</td><td rowspan=\"3\">Значение</td><td>Не больше чем лимит текущего типа</td>"
    "<td>Если категория == 0, то проверка пройдена</td><td> \"Укажите новое значение\"</td></tr>"
    "<tr><td>2</td><td>Не больше чем лимит старшего типа</td>"
    "<td>Если в справочнике иерархии существует старший тип, то сравнить</td><td>\n</td></tr>"
    "<tr><td>3</td><td>Не меньше чем лимит младшего типа</td>"
    "<td>Если в справочнике иерархии существует младший тип, то сравнить</td>"
    "<td> \"Укажите новое значение\"</td></tr>")


def test_empty_cell_with_card_text_warns():
    card = _card("CTL-052", "Значение: Не больше чем лимит старшего типа",
                 "**Если** в справочнике иерархии существует старший тип, **то** сравнить.",
                 "«Укажите новое значение»; способ отображения — списком.")
    rep, n = message_attribution(card, [("111", LIMITS)])
    assert n == 3
    assert len(rep) == 1 and rep[0].startswith("предупреждение: CTL-052 — поле «Сообщение об ошибке» задано")
    assert "на странице 111 пуста" in rep[0]


def test_unquoted_explanation_on_empty_cell_warns_about_formula():
    # стенд CTL-029: пояснение без цитаты при пустой ячейке — ⚠ о формуле, не «приписка»
    card = _card("CTL-052", "Значение: Не больше чем лимит старшего типа",
                 "Если в справочнике иерархии существует старший тип, то сравнить",
                 "мягкий контроль — сообщение пользователю не отображается.")
    rep = message_attribution(card, [("111", LIMITS)])[0]
    assert len(rep) == 1 and "поле без цитаты" in rep[0] and "приписка" not in rep[0]


def test_neighbour_rows_with_text_silent():
    # НЕсрабатывание: у соседних строк ячейка заполнена
    card = _card("CTL-051", "Значение: Не больше чем лимит текущего типа",
                 "Если категория == 0, то проверка пройдена", "«Укажите новое значение».")
    assert message_attribution(card, [("111", LIMITS)])[0] == []


def test_not_set_formula_on_empty_cell_silent():
    card = _card("CTL-052", "Значение: Не больше чем лимит старшего типа",
                 "Если в справочнике иерархии существует старший тип, то сравнить",
                 "в постановке не задано.")
    assert message_attribution(card, [("111", LIMITS)])[0] == []


MERGED = _src(
    "<tr><td>1</td><td>Номер счета</td><td>Проверка длины</td>"
    "<td colspan=\"2\"><p>Проверка выполняется согласно п.4.2 Контроли единых полей</p></td></tr>"
    "<tr><td>2</td><td>Номер счета</td><td>Проверка заполненности</td>"
    "<td>Если реквизит указан, то проверка пройдена</td><td>Обязательное поле</td></tr>")


def test_merged_logic_message_cell_with_formula_silent():
    card = _card("CTL-105", "Номер счета: Проверка длины",
                 "проверка выполняется согласно п. 4.2 «Контроли единых полей»",
                 "в постановке не задано: ячейка объединена с логикой проверки.")
    assert message_attribution(card, [("111", MERGED)])[0] == []


def test_merged_logic_message_cell_with_text_silent():
    # другой класс (ячейка не пуста) — ловит ревью, не этот сторож
    card = _card("CTL-105", "Номер счета: Проверка длины",
                 "проверка выполняется согласно п. 4.2 «Контроли единых полей»",
                 "«Проверка выполняется согласно п.4.2 Контроли единых полей».")
    assert message_attribution(card, [("111", MERGED)])[0] == []


def test_message_split_by_condition_columns_silent():
    # НЕсрабатывание: две колонки сообщения по условию («файлов == 0» / «> 0», стенд CTL-009);
    # текст стоит во второй — ячейка не пуста
    head = ("<table><tbody><tr><th rowspan=\"2\">№</th><th rowspan=\"2\">Название проверки</th>"
            "<th colspan=\"2\">Логика работы проверки</th><th colspan=\"2\">Сообщение об ошибке</th></tr>"
            "<tr><th>Файлов == 0</th><th>Файлов &gt; 0</th><th>Файлов == 0</th><th>Файлов &gt; 0</th></tr>")
    src = _src("<tr><td>1</td><td>Контроль идентичности файлов</td><td>-</td>"
               "<td>Если хеш сумма совпадает, то ошибка</td><td></td>"
               "<td>\"Данный файл уже загружен\"</td></tr>", head)
    rows = message_rows(src)
    assert len(rows) == 1 and not rows[0]["empty"]
    card = _card("CTL-009", "Хеш сумма: Контроль идентичности файлов",
                 "Если хеш сумма совпадает, то ошибка", "«Данный файл уже загружен».")
    assert message_attribution(card, [("111", src)])[0] == []


def test_rowspan_tail_is_not_a_data_row():
    src = _src(
        "<tr><td>1</td><td rowspan=\"2\">Номер счета</td><td>Проверка заполненности</td>"
        "<td>Если реквизит указан, то проверка пройдена</td><td>Обязательное поле</td></tr>"
        "<tr><td></td><td></td><td></td><td></td></tr>")
    rows = message_rows(src)
    assert len(rows) == 1 and not rows[0]["empty"]


def test_typical_logic_resolved_by_title():
    # одна и та же типовая логика у двух реквизитов: строка выбирается по заголовку карточки
    src = _src(
        "<tr><td>1</td><td>Фамилия</td><td>Проверка заполненности</td>"
        "<td>Если значение реквизита указано, то проверка пройдена</td><td>Укажите фамилию</td></tr>"
        "<tr><td>2</td><td>Имя</td><td>Проверка заполненности</td>"
        "<td>Если значение реквизита указано, то проверка пройдена</td><td></td></tr>")
    ok_card = _card("CTL-001", "Фамилия: Проверка заполненности",
                    "**Если** значение реквизита указано, **то** проверка пройдена", "«Укажите фамилию».")
    bad_card = _card("CTL-002", "Имя: Проверка заполненности",
                     "**Если** значение реквизита указано, **то** проверка пройдена", "«Укажите имя».")
    assert message_attribution(ok_card, [("111", src)])[0] == []
    rep = message_attribution(bad_card, [("111", src)])[0]
    assert len(rep) == 1 and "CTL-002" in rep[0]


def test_equal_candidates_with_different_fill_silent():
    # заголовок карточки строку не указывает, логика одинакова, заполненность разная — молчать
    src = _src(
        "<tr><td>1</td><td>Фамилия</td><td>Заполненность</td>"
        "<td>Если значение реквизита указано, то проверка пройдена</td><td>Укажите фамилию</td></tr>"
        "<tr><td>2</td><td>Имя</td><td>Заполненность</td>"
        "<td>Если значение реквизита указано, то проверка пройдена</td><td></td></tr>")
    card = _card("CTL-003", "Отчество: Обязательность",
                 "Если значение реквизита указано, то проверка пройдена", "«Укажите отчество».")
    assert message_attribution(card, [("111", src)])[0] == []


def test_integration_message_structure_column_not_a_message_column():
    head = ("<table><tbody><tr><th>Проверяемый реквизит</th><th>Название проверки</th>"
            "<th>Логика выполнения проверки</th><th>Структура сообщения</th></tr>")
    src = _src("<tr><td>Номер</td><td>Проверка</td><td>Если указан, то пройдена</td><td></td></tr>", head)
    assert message_rows(src) == []
    card = _card("CTL-004", "Номер: Проверка", "Если указан, то пройдена", "«Ошибка».")
    rep, n = message_attribution(card, [("111", src)])
    assert rep == [] and n == 0


def test_header_section_row_not_header_and_not_data():
    # строка-раздел «Контроли <сущность>» на всю ширину в шапке (страница 2166859942 КК)
    head = (HEAD + "<tr><th colspan=\"5\">Контроли [КК_ЛК] Заявка на управление лимитами</th></tr>")
    src = _src("<tr><td>1</td><td>Значение</td><td>Не больше чем лимит старшего типа</td>"
               "<td>Если существует старший тип, то сравнить</td><td></td></tr>", head)
    rows = message_rows(src)
    assert len(rows) == 1 and rows[0]["empty"]
    card = _card("CTL-052", "Значение: Не больше чем лимит старшего типа",
                 "Если существует старший тип, то сравнить", "«Укажите новое значение».")
    assert len(message_attribution(card, [("111", src)])[0]) == 1


def test_gate_file_without_page_ids_one_info_line(tmp_path):
    body = (_card("CTL-001", "Фамилия: Проверка заполненности", "Если указано, то пройдена", "«Укажите»")
            + _card("CTL-002", "Имя: Проверка заполненности", "Если указано, то пройдена", "«Укажите»"))
    p = _file(tmp_path, body, pids="")
    rep, _ok = check_file(p, source_text=None)
    info = [r for r in rep if r.startswith("i сверка сообщений")]
    assert info == ["i сверка сообщений карточек с источником не выполнена: страница не указана"]
    assert not any("приписка" in r for r in rep)
    # в самопроверке комплекта строка на файл не пишется — сводной строкой комплекта
    rep, _ok = check_file(p, source_text=None, kit_summary=True)
    assert not any(r.startswith("i сверка сообщений") for r in rep)


def test_gate_warns_without_changing_verdict(tmp_path):
    card = _card("CTL-052", "Значение: Не больше чем лимит старшего типа",
                 "Если в справочнике иерархии существует старший тип, то сравнить",
                 "«Укажите новое значение».")
    p = _file(tmp_path, card)
    rep_src, ok_src = check_file(p, source_text=LIMITS)
    rep_none, ok_none = check_file(p, source_text=None)
    assert sum("приписка" in r for r in rep_src) == 1
    assert ok_src == ok_none


def test_kit_summary_line(tmp_path):
    from app.scripts.CI import selfcheck
    docs = tmp_path / "docs"
    (docs / "srs" / "control").mkdir(parents=True)
    body = _card("CTL-001", "Фамилия: Проверка заполненности", "Если указано, то пройдена", "«Укажите»")
    for name in ("cards-a.md", "cards-b.md"):
        (docs / "srs" / "control" / name).write_text(
            "---\ntype: control\nentity: ENT-001\n---\n\n# К\n\n" + body, encoding="utf-8")
    ctx = selfcheck._KitCtx(docs=docs, sources=None, strict=False, catalog=None, card_ids={},
                            card_titles={}, fm_schema_issues=[], groups={}, idx={})
    rep, ok = selfcheck._kc_message_attribution_unchecked(ctx)
    assert ok and rep[0] == ("i сверка сообщений карточек контролей с источником не выполнена: "
                             "2 файлов (страница не указана ×2)")
