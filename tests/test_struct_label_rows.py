"""Строка-блок таблицы полей источника любой длины; объединённая ячейка вне словаря — строка ⚠
«вне профиля таблицы» без отказа по таблице (замечание ОНБ-В 69, 2026-11-07)."""
from app.scripts.CI.kitcheck.columns import _struct_label_row, validate_columns
from app.scripts.CI.normalize_tables import normalize_file

HEAD = ["", "№ п/п", "Название поля", "Тип", "Способ заполнения", "Обязательность", "Описание"]


def _row(*cells):
    return list(cells)


def _obl(rows, source_mode=True):
    cols = validate_columns(HEAD, rows, path_index=None, source_mode=source_mode)
    return next(c for c in cols if c["role"] == "обязат")


DATA = [_row("", f"3.{k}", f"Поле {k}", "Текст", "Ручной ввод", "Да", "описание") for k in range(1, 8)]
# строка-блок из замечания: «4» в двух ячейках, ярлык протянут на четыре, примечание отдельно
LABEL = _row("4", "4", "Блок выбора типа счёта", "Блок выбора типа счёта", "Блок выбора типа счёта",
             "Блок выбора типа счёта", "Название блока на ЭФ не отображается")


def test_long_label_in_merged_cell_is_label():
    assert _struct_label_row(LABEL, 5)


def test_label_row_table_fully_valid_no_refusal():
    col = _obl(DATA + [LABEL])
    assert col["bad"] == 0 and col["valid_pct"] == 100.0 and col["out_of_profile"] == []


def test_phrase_with_comma_is_not_label():
    # НЕсрабатывание: фраза с запятой — не ярлык, даже в объединённой ячейке
    v = "Блок отображается, если заполнен счёт"
    row = _row("", "", v, v, v, v, v)
    assert not _struct_label_row(row, 5)


def test_phrase_merged_goes_out_of_profile_not_label():
    # объединение на три колонки (не строка-раздел на всю ширину)
    v = "Блок отображается, если заполнен счёт"
    row = _row("", "3.9", "Поле", "Текст", v, v, v)
    col = _obl(DATA + [row])
    assert col["out_of_profile"] == [v] and col["bad"] == 0 and col["total"] == len(DATA)


def test_phrase_in_plain_cell_stays_data_bad():
    # НЕсрабатывание: не объединённая ячейка с фразой — данные, вне словаря (брак колонки)
    row = _row("", "3.9", "Поле", "Текст", "Ручной ввод", "Блок отображается, если заполнен счёт", "x")
    col = _obl(DATA + [row])
    assert col["bad"] == 1 and col["out_of_profile"] == []


def test_keyword_without_punct_in_plain_cell_not_label():
    # НЕсрабатывание: ярлык по словам, но ячейка не объединена и строка не пустая — данные
    row = _row("", "3.9", "Поле", "Текст", "Ручной ввод", "Блок выбора типа счёта", "описание")
    col = _obl(DATA + [row])
    assert col["bad"] == 1


def test_label_alone_in_row_is_label():
    row = _row("", "", "", "", "", "Раздел реквизиты получателя платежа", "")
    assert _struct_label_row(row, 5)


def test_card_check_mode_no_relief():
    # --check карточки: послаблений для ярлыков нет
    col = _obl(DATA + [LABEL], source_mode=False)
    assert col["bad"] == 1 and col["out_of_profile"] == []


def test_valid_merged_value_not_out_of_profile():
    row = _row("", "", "Нет", "Нет", "Нет", "Нет", "Нет")
    col = _obl(DATA + [row])
    assert col["out_of_profile"] == [] and col["bad"] == 0


def _html(rows_html):
    return ("<table><tbody><tr><th></th><th>№ п/п</th><th>Название поля</th><th>Тип</th>"
            "<th>Способ заполнения</th><th>Обязательность</th><th>Описание</th></tr>"
            + "".join(f"<tr><td></td><td>3.{k}</td><td>Поле {k}</td><td>Текст</td><td>Ручной</td>"
                      f"<td>Да</td><td>описание</td></tr>" for k in range(1, 8))
            + rows_html + "</tbody></table>\n")


def test_normalize_file_label_row_no_refusal(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(_html('<tr><td colspan="2"><strong>4</strong></td>'
                       '<td colspan="4"><strong>Блок выбора типа счёта</strong></td>'
                       '<td><strong>Название блока на ЭФ не отображается</strong></td></tr>'),
                 encoding="utf-8")
    out, rep, ok = normalize_file(p, None, None)
    assert ok and "Блок выбора типа счёта" in out
    assert not any("вне профиля" in r for r in rep)
    # снятое объявленной словарной эвристикой видно отчёту числом и перечнем
    assert any("i строк-блоков (ярлык ряда, не значение обязательности): 1 — "
               "«Блок выбора типа счёта»" in r for r in rep)


def test_old_quoted_label_also_visible():
    rows = DATA + [_row("", "", "Раздел «Реквизиты»", "", "", "Раздел «Реквизиты»", "")]
    col = _obl(rows)
    assert col["bad"] == 0 and col["struct_labels"] == ["Раздел «Реквизиты»"]


def test_normalize_file_merged_phrase_warns_keeps_row(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(_html('<tr><td colspan="7">По нажатии на кнопку осуществляется вызов функции</td></tr>'),
                 encoding="utf-8")
    out, rep, ok = normalize_file(p, None, None)
    # строка из одной объединённой ячейки ≥3 — строка-раздел (прежний сторож), её не трогаем;
    # объединение не на всю ширину — вне профиля
    p.write_text(_html('<tr><td></td><td>3.8</td><td>Поле 8</td>'
                       '<td colspan="4">По нажатии на кнопку осуществляется вызов функции</td></tr>'),
                 encoding="utf-8")
    out, rep, ok = normalize_file(p, None, None)
    assert ok, rep
    assert any("⚠ строка вне профиля таблицы: «По нажатии на кнопку" in r for r in rep)
    assert "По нажатии на кнопку осуществляется вызов функции" in out
