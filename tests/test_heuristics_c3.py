"""Объявленные словарные эвристики сверки с источником (решения владельца канона 2026-11-06):
колонки «ФЛК»/«Пример», таблицы истории, маркер «Пример:» — снятое видно i-строками; заголовок
«Размерность» и К-19 сняты."""
from app.scripts.CI.kitcheck.checks import card_source
from app.scripts.CI.kitcheck.checks.card_run import run_check
from app.scripts.CI.kitcheck.checks.card_source import (
    check_quoted_literals, check_source_tables, check_unchecked_tables, quoted_literals,
)

HEAD = "---\ntitle: X\n---\n\n"
EXAMPLE_TABLE = "| Атрибут | Тип | Пример |\n|---|---|---|\n| Статус | Строка | \"Новый\" |\n"


def e1_line(rep):
    return next((r for r in rep if r.startswith("i К-18:")), None)


# --- Э1: литерал снимается, только если все его кавычечные вхождения в ячейках таких колонок

def test_literal_only_in_example_cells_not_required():
    rep, ok = check_quoted_literals("карточка", HEAD + EXAMPLE_TABLE)
    assert ok, rep
    assert e1_line(rep) == ("i К-18: ячеек колонок «ФЛК»/«Пример» не требовалось: 1; "
                            "литералов снято: 1 ('Новый')")


def test_literal_in_two_example_cells_not_required():
    src = HEAD + EXAMPLE_TABLE + "| Вид | Строка | \"Новый\" |\n"
    rep, ok = check_quoted_literals("карточка", src)
    assert ok, rep
    assert "не требовалось: 2; литералов снято: 1" in e1_line(rep)


def test_literal_in_example_cell_and_prose_required():
    # тест на НЕсрабатывание: вхождение в прозе — литерал требуется
    src = HEAD + EXAMPLE_TABLE + "\nПосле сохранения статус \"Новый\" показывается клиенту.\n"
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok and any("отсутствуют 1 из 1" in r for r in rep), rep
    assert "литералов снято: 0" in e1_line(rep)


def test_literal_in_example_cell_and_other_column_required():
    # тест на НЕсрабатывание: вхождение в другой колонке — литерал требуется
    src = HEAD + ("| Атрибут | Описание | Пример |\n|---|---|---|\n"
                  "| Статус | Начальное значение \"Новый\" | \"Новый\" |\n")
    assert quoted_literals(src) == ["Новый"]
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep


def test_substring_of_flk_cell_no_longer_removes_literal():
    # прежняя дыра: литерал прозы снимался, потому что был подстрокой текста ячейки ФЛК
    src = HEAD + ("| Атрибут | Тип | ФЛК |\n|---|---|---|\n"
                  "| Статус | Строка | только Новый статус |\n"
                  "\nКнопка \"Новый\" открывает форму.\n")
    assert quoted_literals(src) == ["Новый"]
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep


def test_literal_present_in_card_ok():
    src = HEAD + EXAMPLE_TABLE + "\nСтатус \"Новый\".\n"
    rep, ok = check_quoted_literals("статус Новый", src)
    assert ok, rep


def test_html_cell_only_not_required():
    src = HEAD + ("<table><tbody><tr><th>Атрибут</th><th>ФЛК</th></tr>"
                  "<tr><td>Номер</td><td>Формат \"000001\" по правилам</td></tr>"
                  "</tbody></table>\n")
    rep, ok = check_quoted_literals("карточка", src)
    assert ok, rep
    assert "литералов снято: 1 ('000001')" in e1_line(rep)


def test_html_cell_with_prose_required():
    # тест на НЕсрабатывание для HTML-таблицы
    src = HEAD + ("<table><tbody><tr><th>Атрибут</th><th>ФЛК</th></tr>"
                  "<tr><td>Номер</td><td>Формат \"000001\"</td></tr>"
                  "</tbody></table>\n\nПервый номер \"000001\" выдаёт банк.\n")
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep


def test_xml_in_example_cell_does_not_cover_prose():
    # тест на НЕсрабатывание: значение атрибута XML-примера в ячейке не прикрывает литерал прозы
    src = HEAD + ("<table><tbody><tr><th>Атрибут</th><th>Пример запроса</th></tr>"
                  "<tr><td>Дата</td><td>&lt;EGRUL Дата=\"2022-06-14\" x=\"\"&gt;"
                  "&lt;Док Дата=\"2022-06-14\" /&gt;</td></tr>"
                  "</tbody></table>\n\nДата выписки \"2022-06-14\" в ответе.\n")
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep


def test_xml_only_in_example_cell_not_required():
    src = HEAD + ("<table><tbody><tr><th>Атрибут</th><th>Пример запроса</th></tr>"
                  "<tr><td>Дата</td><td>&lt;EGRUL Дата=\"2022-06-14\" /&gt;</td></tr>"
                  "</tbody></table>\n")
    rep, ok = check_quoted_literals("карточка", src)
    assert ok, rep


def test_unclosed_table_literal_required():
    # тест на НЕсрабатывание: граница таблицы не определена — литерал требуется
    src = HEAD + "<table><tr><th>Атрибут</th><th>ФЛК</th></tr><tr><td>Н</td><td>\"Новый\"</td></tr>\n"
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep


def test_nested_table_is_text_of_parent_cell():
    # заголовок «ФЛК» вложенной таблицы не делает её ячейку ячейкой ФЛК внешней таблицы
    src = HEAD + ("<table><tbody><tr><th>Атрибут</th><th>Описание</th></tr>"
                  "<tr><td>Н</td><td><table><tr><th>ФЛК</th></tr><tr><td>\"Новый\"</td></tr></table>"
                  "</td></tr></tbody></table>\n")
    assert quoted_literals(src) == ["Новый"]


def test_pipe_cell_with_escaped_pipe_positions():
    # экранированная черта не сдвигает колонку: литерал соседней колонки требуется
    src = HEAD + ("| Атрибут | Описание | Пример |\n|---|---|---|\n"
                  "| Статус \\| вид | значение \"Новый\" | \"Старый\" |\n")
    assert quoted_literals(src) == ["Новый"]


def test_rowspan_cell_with_prose_required():
    # тест на НЕсрабатывание: объединённая ячейка не прикрывает вхождение в прозе
    src = HEAD + ("<table><tbody><tr><th>Атрибут</th><th>ФЛК</th></tr>"
                  "<tr><td>А</td><td rowspan=\"2\">Формат \"000001\"</td></tr>"
                  "<tr><td>Б</td></tr>"
                  "</tbody></table>\n\nПервый номер \"000001\" выдаёт банк.\n")
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep


def test_column_position_after_rowspan():
    # колонка считается с учётом rowspan слева: «Описание» второй строки не ячейка ФЛК
    src = HEAD + ("<table><tbody><tr><th>Группа</th><th>Описание</th><th>ФЛК</th></tr>"
                  "<tr><td rowspan=\"2\">Г</td><td>О1</td><td>Ф1</td></tr>"
                  "<tr><td>Значение \"Новый\"</td><td>Ф2</td></tr>"
                  "</tbody></table>\n")
    assert quoted_literals(src) == ["Новый"]


def test_example_cell_and_code_block_goes_to_examples_class():
    # вхождения только в ячейке «Пример» и в блоке кода: класс «примеры», не брак
    src = HEAD + EXAMPLE_TABLE + "\n```json\n{\"status\": \"Новый\"}\n```\n"
    rep, ok = check_quoted_literals("карточка", src)
    assert ok, rep
    assert any(r.startswith("⚠ примеры:") and "Новый" in r for r in rep), rep


def test_e1_list_limited_to_four():
    rows = "".join(f"| А{i} | Строка | \"Значение{i}\" |\n" for i in range(6))
    src = HEAD + "| Атрибут | Тип | Пример |\n|---|---|---|\n" + rows
    rep, ok = check_quoted_literals("карточка", src)
    assert ok, rep
    line = e1_line(rep)
    assert "литералов снято: 6" in line
    assert "'Значение3'" in line and "'Значение4'" not in line and line.endswith("; …)")


def test_e1_no_line_without_columns():
    rep, ok = check_quoted_literals("Новый", HEAD + "Статус \"Новый\".\n")
    assert ok and e1_line(rep) is None, rep


def test_flk_cells_still_not_required_in_table_comparison():
    src = HEAD + ("| Атрибут | Тип | ФЛК |\n|---|---|---|\n"
                  "| Номер | Число | не более 6 знаков |\n"
                  "| Дата | Дата | только рабочие дни |\n")
    rep, ok = check_source_tables("| Номер | Число |\n| Дата | Дата |\n", src)
    assert ok, rep


# --- Э4: маркер «Пример:»

def test_after_marker_line():
    src = HEAD + "<p>Запрос. Пример: {\"fio\":\"Выпискин О. О.\"}</p>\n"
    rep, ok = check_quoted_literals("карточка", src)
    assert ok, rep
    assert ("i значений после маркера «Пример:» не требовалось: 2 "
            "('fio'; 'Выпискин О. О.')") in rep


def test_after_marker_and_plain_required_no_line():
    # тест на НЕсрабатывание: второе вхождение без маркера — литерал требуется
    src = HEAD + "<p>Пример: \"Новый\"</p>\n<p>Статус \"Новый\" обязателен.</p>\n"
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep
    assert not any("маркера" in r for r in rep), rep


def test_marker_in_cell_does_not_count_as_cell_occurrence():
    # тест на НЕсрабатывание: вхождение после маркера снято своей эвристикой и не считается
    # вхождением в ячейку, поэтому не прикрывает литерал прозы
    src = HEAD + ("| Атрибут | Пример |\n|---|---|\n| Статус | Пример: \"Новый\" |\n"
                  "\nСтатус \"Новый\" обязателен.\n")
    rep, ok = check_quoted_literals("карточка", src)
    assert not ok, rep


# --- Э2: таблицы истории

HISTORY = ("| Дата | Описание | Автор |\n|---|---|---|\n"
           "| 01.01.2026 | правка раз | Иванов |\n| 02.01.2026 | правка два | Петров |\n")
DOCS = "| Документ | Дата документа |\n|---|---|\n| Постановка | 03.01.2026 |\n"


def test_history_line_counts_tables_and_rows():
    src = HEAD + HISTORY + "\nТекст\n\n" + DOCS
    rep, ok = check_source_tables("карточка", src)
    assert ok, rep
    assert "i таблиц истории изменений не сверялось: 2 (строк 3)" in rep


def test_no_history_line_for_other_tables():
    # тест на НЕсрабатывание: обычная таблица с датой сверяется и i-строки не даёт
    src = HEAD + "| Дата | Сумма |\n|---|---|\n| 01.01.2026 | 100 |\n| 02.01.2026 | 200 |\n"
    rep, ok = check_source_tables("карточка", src)
    assert not ok and not any("истории" in r for r in rep), rep


def test_history_table_not_in_unchecked():
    assert check_unchecked_tables("карточка", HEAD + HISTORY) == []


# --- Э3: заголовок «Размерность» больше не снимает таблицу

SIZE_PARAMS = ("| Параметр | Размерность |\n|---|---|\n"
               "| requestId | 36 |\n| bankClientId | 20 |\n")


def test_dimension_header_table_compared():
    rep, ok = check_source_tables("карточка", HEAD + SIZE_PARAMS)
    assert not ok and any("отсутствуют 4 значений" in r for r in rep), rep


def test_dimension_header_table_ok_when_present():
    rep, ok = check_source_tables("requestId 36 bankClientId 20", HEAD + SIZE_PARAMS)
    assert ok, rep


def test_figma_row_still_removed_by_layout_rule():
    src = HEAD + ("| Размерность | Макет |\n|---|---|\n"
                  "| S | [макет](https://www.figma.com/file/1) |\n"
                  "| M | [макет](https://www.figma.com/file/2) |\n")
    rep, ok = check_source_tables("карточка", src)
    assert ok, rep


def test_figma_header_without_address_compared():
    # слово «Figma» в заголовке не снимает таблицу: снимает только форма адреса в строке
    src = HEAD + "| Figma | Значение |\n|---|---|\n| А1 | Б1 |\n| А2 | Б2 |\n"
    rep, ok = check_source_tables("карточка", src)
    assert not ok, rep


def test_unchecked_dimension_table_with_plain_values_is_compared():
    # таблица со значениями теперь в дословной сверке: мягкая проверка её не повторяет
    assert check_unchecked_tables("карточка", HEAD + SIZE_PARAMS) == []


def test_unchecked_layout_table_still_soft_checked():
    src = HEAD + "| Размерность экрана | Макет |\n|---|---|\n| S | [м](https://www.figma.com/f) |\n"
    out = check_unchecked_tables("карточка", src)
    assert len(out) == 1 and out[0].startswith("предупреждение: таблица источника"), out


# --- К-19 снята

def test_k19_removed():
    assert not hasattr(card_source, "check_example_values_absent")
    assert not hasattr(card_source, "_example_value_segments")


def test_example_value_in_data_model_card_not_flagged(tmp_path):
    src = tmp_path / "src.md"
    src.write_text(HEAD + "<p>Назначение платежа</p>"
                   "<p>Пример: Оплата просроченного лизингового платежа по договору</p>\n",
                   encoding="utf-8")
    card = tmp_path / "card.md"
    card.write_text("---\nid: ENT-001\ntitle: 'X'\ntype: data-model\n---\n\nНазначение платежа\n"
                    "Оплата просроченного лизингового платежа по договору\n", encoding="utf-8")
    rep, _ok = run_check([card], src)
    assert not any("значения примеров" in r for r in rep), rep
