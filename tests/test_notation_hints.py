# tests/test_notation_hints.py
"""ПР-02 (разбор замечаний ОНБ-В): предупреждения нотации — одиночный «=» в
условии и обратная стрелка «←»; присваивание, «==», литералы и код не трогаются."""
from app.scripts.CI.kitcheck.checks.card_run import check_file
from app.scripts.CI.kitcheck.checks.card_form import check_notation_hints


def test_single_eq_in_condition_warned():
    rep = check_notation_hints("# Ф\n\n**Если** «Статус» = EXECUTED, **то** закрыть.\n"
                               "**Далее:** «Статус» = CANCELED → 7; иначе → 8\n")
    assert len(rep) == 1 and "одиночный «=» в условии ×2" in rep[0], rep


def test_eq_not_triggered_for_assignment_double_eq_literals_and_code():
    text = ("---\nid: X\n---\n# Ф\n\n"
            "**Если** «Код типа» == 2, **то** «Сумма» = 0.\n"           # присваивание после «то»
            "**По умолчанию:** = \"RUB\"\n"                            # присваивание
            "**Далее:** «Статус» == EXECUTED → 7; иначе → 8\n"
            "**Если** поле содержит \"a = b\", **то** показать.\n"       # литерал
            "**Если** `x = 1` в коде, **то** ошибка.\n"                  # inline-код
            "**Если** <= 5 или >= 2, **то** ок.\n"
            "```\n**Если** a = b\n```\n")
    assert check_notation_hints(text) == [], check_notation_hints(text)


def test_back_arrow_warned_but_not_in_literal():
    rep = check_notation_hints("# К\n\nответ ← ЕСК; поле «a ← b» дословно\n")
    assert len(rep) == 1 and "обратная стрелка «←» ×1" in rep[0], rep
    assert check_notation_hints("# К\n\nполе «a ← b» дословно\n") == []


def test_check_file_keeps_verdict(tmp_path):
    card = tmp_path / "c.md"
    card.write_text("# Ф\n\n**Если** «Статус» = EXECUTED, **то** закрыть.\n", encoding="utf-8")
    rep, ok = check_file(card)
    assert ok, rep
    assert any(ln.startswith("предупреждение: нотация — одиночный «=»") for ln in rep), rep


def test_forward_arrow_outside_key_lookup_warned():
    rep = check_notation_hints("# Ф\n\nСобытие нажатия → открытие формы.\n")
    assert len(rep) == 1 and "стрелка «→» вне поиска записи по ключу ×1" in rep[0], rep


def test_forward_arrow_allowed_forms_not_warned():
    text = ("# Ф\n\n«ИНН» → [ENT-001 Клиент](ent-001.md).«ИНН» — найти запись.\n"
            "**Далее:** «Статус» == EXECUTED → 7; иначе → 8\n"
            "Значение по ключу → поле.\n"
            "## Связи\n\n| Связь | Сущность | Кратность |\n|---|---|---|\n"
            "| Заявка → История изменений | [ENT-002](e.md) | 1 : N |\n"
            "Переход между экранами: Главная => Профиль.\n")
    assert check_notation_hints(text) == [], check_notation_hints(text)


def test_ui_type_outside_dictionary_warned_messages_table_not():
    text = ("# Э\n\n| № | Блок | Поле | Тип | Обяз. |\n|---|---|---|---|---|\n"
            "| 1 | Б | ИНН | Текст | да |\n| 2 | Б | Дата | Дата (ДД.ММ.ГГГГ) | да |\n"
            "| 3 | Б | Флаг | Логическое | нет |\n\n"
            "| ID | Тип | Показ | Содержание |\n|---|---|---|---|\n"
            "| MSG-1 | Информер | под полем | «Ошибка» |\n")
    rep = check_notation_hints(text)
    assert len(rep) == 1 and "вне словаря UI-типов ×1" in rep[0] and "Логическое" in rep[0], rep


def test_bare_angle_name_warned_dotted_counted():
    rep = check_notation_hints("# Ф\n\nЕсли <Статус заявки> равен черновику, "
                               "[ENT-001 Заявка](e.md).<Номер> не меняется.\n")
    assert len(rep) == 1, rep
    assert "без сущности ×1" in rep[0] and "[Сущность].<…> ×1" in rep[0], rep


def test_angle_not_warned_in_literals_code_html_and_param_tables():
    text = ("# Ф\n\nСообщение «Счёт <номер счёта> закрыт».\n"
            "Код `Метод.<XS>` и тег <br> и <img src=\"a.png\">; условие a <= b > c.\n"
            "| Код параметра | Наименование параметра |\n|---|---|\n| id | <Идентификатор> |\n"
            "```\n<Имя>\n```\n")
    assert check_notation_hints(text) == [], check_notation_hints(text)



# ---- счёт формы «[Сущность].<…>» после перехода на «ёлочки» (постановка 2026-11-19)

def _angle(text):
    rep = [r for r in check_notation_hints(text) if "угловых скобках" in r]
    assert len(rep) == 1, rep
    return rep[0]


def test_dotted_angle_counts_quotes_inside_formula_constant_latin_word_escaped():
    # четыре вида записи «[Сущность].<…>», которые счёт пропускал (КК, SCR-CL-19,
    # строки 537, 706, 909): кавычки внутри скобок, формула с кавычкой в
    # строковой константе, латинское слово с пробелом, экранированные скобки
    text = ("# Ф\n\n"
            "- Формат: Подразделение Банка.<Населенный пункт> + ', \"' + "
            "Подразделение Банка.<Наименование подразделения> + '\"'.\n"
            "- где Доверенности Сотрудника.<ID \"Сотрудник клиента\"> = [Сотрудник](d.md).<Идентификатор записи>.\n"
            "- **если** Клиент Банка.<GUID клиента в ЕСК (EXTERNAL_CLIENT_GUID)> не пусто,**то** "
            "Клиент Банка.<GUID клиента в ЕСК (EXTERNAL_CLIENT_GUID)>,<br>**иначе** пусто;\n"
            "- Идентификатор документа = Входящие параметры.\\<ID документа\\>;\n"
            "- Если <Статус> пуст.\n")
    rep = _angle(text)
    assert "без сущности ×1" in rep and "[Сущность].<…> ×7" in rep, rep


def test_latin_word_name_without_entity_is_bare_not_tag():
    # «<GUID клиента>» — имя, не HTML-тег: хвост не из атрибутов вида имя=значение
    rep = _angle("# Ф\n\n| № | Поле | Значение |\n|---|---|---|\n| 4.8 | GUID | = значение поля <GUID клиента> |\n")
    assert "без сущности ×1" in rep and "'<GUID клиента>'" in rep, rep


def test_real_tags_and_literal_substitutions_not_counted():
    # НЕсрабатывание: настоящие теги (в том числе после точки и с атрибутами)
    # и подстановки в дословных текстах сообщений
    text = ("# Ф\n\n"
            "Заполнено.<br>Далее <u>подчёркнуто</u>, <img src=\"a.png\"/> и "
            "<a href=\"x.md\" title=\"Подсказка\">ссылка</a>; <br/>\n"
            "Сообщение \"Счёт <Номер счёта> закрыт\" и «Карта <Номер карты> выпущена».\n"
            "Сообщение \"Не заполнено Клиент Банка.<ОГРН>\".\n"
            "Константа ', \"' и '\"' без скобок.\n")
    assert check_notation_hints(text) == [], check_notation_hints(text)
