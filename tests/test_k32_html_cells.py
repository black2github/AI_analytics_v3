"""К-32 на HTML-таблицах источника (замечание ОНБ-В 67, 2026-11-07): граница ячейки или
блока не склеивает тег с текстом следующей ячейки; дефейс внутри ячейки по-прежнему ✗."""
from app.scripts.CI.kitcheck.checks.card_clean import check_source_tag_mentions

_SRC_ROW = (
    "---\ntitle: '[КК_БК] ЖЦ заявки'\n---\n"
    "<table><tbody><tr><td>2.9</td><td>Отправка [КК_БК] Нотификация</td>"
    "<td>Далее выполняется переход на шаг 2.10</td></tr></tbody></table>\n")


def _k32(rep):
    return [r for r in rep if "К-32" in r or "теговое упоминание" in r]


def test_tag_mention_at_cell_end_verbatim_no_signal():
    # НЕсрабатывание: упоминание в карточке дословно, следующая ячейка — отдельный текст
    card = "| 2.9 | Отправка [КК_БК] Нотификация | Далее выполняется переход на шаг 2.10 |\n"
    rep, ok = check_source_tag_mentions(card, _SRC_ROW)
    assert ok and _k32(rep) == []


def test_tag_mention_defaced_in_cell_still_flags():
    # срабатывание: тег снят в карточке — ✗ остаётся
    card = "| 2.9 | Отправка Нотификация | Далее выполняется переход на шаг 2.10 |\n"
    rep, ok = check_source_tag_mentions(card, _SRC_ROW)
    assert not ok and any("дефейс" in r and "Нотификация" in r for r in rep)


def test_core_does_not_take_next_cell_words():
    # ядро имени — только из своей ячейки: в отчёте нет слов следующей ячейки
    rep, _ = check_source_tag_mentions("| 2.9 | что-то другое |\n", _SRC_ROW)
    lines = _k32(rep)
    assert len(lines) == 1 and "Нотификация" in lines[0] and "Далее" not in lines[0]


def test_th_and_tr_are_boundaries():
    src = ("<table><tr><th>Ссылка [КК_ВК] Контроли</th><th>Описание</th></tr>"
           "<tr><td>[О2] ЭФ Клиента</td></tr></table>\n")
    rep, ok = check_source_tag_mentions("[КК_ВК] Контроли и [О2] ЭФ Клиента\n", src)
    assert ok and _k32(rep) == []


def test_li_and_p_are_boundaries():
    src = "<ul><li>см. [КК] Справочник клиентов</li><li>Может отсутствовать</li></ul>" \
          "<p>Раздел [КК] Нотификации</p><p>После выполнения</p>\n"
    rep, ok = check_source_tag_mentions(
        "- см. [КК] Справочник клиентов\n- Может отсутствовать\n\nРаздел [КК] Нотификации\n", src)
    assert ok and _k32(rep) == []


def test_br_in_any_spelling_is_boundary():
    for br in ("<br>", "<br/>", "<br />", "<BR>", "<Br/>"):
        src = f"<td>[КК_ВК] Карточный продукт{br}CORP - Именная</td>\n"
        rep, ok = check_source_tag_mentions(
            "[КК_ВК] Карточный продукт\nCORP - Именная\n", src)
        assert ok and _k32(rep) == [], br


def test_inline_tags_stay_spaces():
    # НЕ граница: строчная разметка внутри ячейки — пробел, упоминание целое
    src = "<td><strong>[КК_БК]</strong> <em>Функции</em> Банка</td>\n"
    rep, ok = check_source_tag_mentions("Отправка Функции Банка\n", src)
    assert not ok and any("дефейс" in r and "Функции Банка" in r for r in rep)


def test_markdown_mention_unchanged():
    # markdown-источник: прежнее поведение (дефейс в строке)
    src = "Проверки см в [РРКО_ИПИ] Методы для конкретной функции\n"
    rep, ok = check_source_tag_mentions("Проверки см в Методы для конкретной функции\n", src)
    assert not ok and any("дефейс" in r for r in rep)
    rep, ok = check_source_tag_mentions(
        "Проверки см в [РРКО_ИПИ] Методы для конкретной функции\n", src)
    assert ok and _k32(rep) == []


def test_tag_alone_at_line_end_is_not_mention():
    # тег в конце строки без имени: имя следующей строки к нему не приклеивается
    src = "<td>regulatoryReport</td><td>[1_N]</td><td>Нормативная отчетность</td>\n" \
          "Статус [DRAFT]\nСертификаты ДБО\n"
    rep, ok = check_source_tag_mentions("ничего\n", src)
    assert ok and _k32(rep) == []
