"""Пакет П2 ОНБ-В, п. 9 (находка П1): ячейка колонки обязательности, начинающаяся с
«см.», — отсылка, не значение и не брак колонки: строка ⚠ «обязательность отсылкой»,
таблица сверяется дальше. Только нормализация источника."""
from app.scripts.CI.kitcheck.columns import _looks_like_obligation, validate_columns
from app.scripts.CI.normalize_tables import normalize_file

HEAD = ["№ п/п", "Название поля", "Тип", "Обязательность", "Описание"]
DATA = [[f"2.{k}", f"Поле {k}", "Текст", "Да", "описание"] for k in range(1, 17)]
SEE = ["2.17", "Капча", "Текст", "см. описание поля", "описание"]


def _obl(rows, source_mode=True):
    cols = validate_columns(HEAD, rows, path_index=None, source_mode=source_mode)
    return next(c for c in cols if c["role"] == "обязат")


def test_see_ref_not_counted_and_listed_with_row_number():
    # случай ОНБ-В: 16 значений + одна отсылка — было 94.1 %, отказ при пороге 95 %
    col = _obl(DATA + [SEE])
    assert col["valid_pct"] == 100.0 and col["bad"] == 0 and col["total"] == 16
    assert col["see_refs"] == [(17, "см. описание поля")]


def test_see_ref_capitalized_with_tail():
    row = ["2.8", "Капча", "Текст", "См. описание поля 2.8 «Капча (ввод)» на ЭФ Клиента", "о"]
    col = _obl(DATA + [row])
    assert col["see_refs"] and col["see_refs"][0][0] == 17 and col["bad"] == 0


def test_value_with_see_tail_still_bad():
    # НЕсрабатывание: «Да, см. п. 3» начинается со значения — словарь её не принимал и не
    # начал принимать, отсылкой она не считается
    assert not _looks_like_obligation("Да, см. п. 3")
    col = _obl(DATA + [["2.17", "Поле", "Текст", "Да, см. п. 3", "о"]])
    assert col["bad"] == 1 and col["see_refs"] == []


def test_see_without_dot_not_ref():
    # признак — форма «см.» с точкой; слово «смотри» и «см» без точки — не отсылка
    col = _obl(DATA + [["2.17", "Поле", "Текст", "смотри описание", "о"]])
    assert col["bad"] == 1 and col["see_refs"] == []


def test_card_check_mode_unchanged():
    # сверка таблиц карточки (source_mode=False) — как прежде: отсылка — брак словаря
    col = _obl(DATA + [SEE], source_mode=False)
    assert col["bad"] == 1 and col["see_refs"] == []


def test_merged_see_cell_stays_out_of_profile():
    # объединённая ячейка «См. …» — по-прежнему строка вне профиля (поведение П1 не меняется)
    v = "См. описание поля 2.9"
    col = _obl(DATA + [["2.9", "Капча", v, v, v]])
    assert col["out_of_profile"] == [v] and col["see_refs"] == []


def test_normalizer_prints_warning_and_keeps_table(tmp_path):
    # HTML-таблица, как в выгрузке; первая колонка пуста (роль «путь» нормализатора)
    def tr(cells, tag="td"):
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in [""] + cells) + "</tr>"
    md = tmp_path / "page.md"
    md.write_text("<table><tbody>" + tr(HEAD, "th") + "".join(tr(r) for r in DATA + [SEE])
                  + "</tbody></table>\n", encoding="utf-8")
    out, rep, ok = normalize_file(md, None, None)
    assert ok, rep
    assert "   ⚠ обязательность отсылкой: «см. описание поля» (строка 17)" in rep, rep
    assert "см. описание поля" in out
