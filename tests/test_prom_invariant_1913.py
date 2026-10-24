# tests/test_prom_invariant_1913.py
#
# Сторож --check-prom, правки 1.9.13 (выгрузка КК 1.9.11: 14 сигналов, из них ложные):
#   * столбец источника с именем «status» вырезался как служебный («потеряно: status»
#     на двух [DEV]-страницах) — теперь слово «status» не вырезается вовсе: критик сам
#     удаляет свой служебный столбец при apply/reject;
#   * нумерация «N. » снималась в источнике только в первом узле блока — номер в
#     отдельном узле, после <br>, в заголовке, в жирном, номер из узлов разного цвета и
#     строка с цифры внутри HTML-острова давали ложные «потеряно / лишнее: 1, 2, 3»
#     (десять страниц). Теперь из источника строятся те же два среза, что даёт критик
#     (ПРОМ = чёрное + удаления, apply = чёрное + вставки), и номер снимается в начале
#     строки каждого среза — как md_plain в результатах reject/apply.
# Тесты парами: ложный сигнал ушёл / настоящая потеря по-прежнему видна.

from collections import Counter

from app.content_extractor import create_critic_extractor
from app.prom_invariant import check_prom_invariant, md_plain, words
from app.scripts.CI.critic import postpass_drop_contained_deletions

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
CMAP = {"#008000": TASK}


def _check(html, md=None):
    ext = create_critic_extractor(CMAP)
    real, dropped = postpass_drop_contained_deletions(ext.extract(html))
    return check_prom_invariant(html, real if md is None else md, ext,
                                [d["text"] for d in dropped])


def _table(rows):
    body = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
    return f"<table><tbody><tr><th>Поле</th><th>status</th></tr>{body}</tbody></table>"


class TestStatusColumnOfSource:
    def test_source_status_column_is_text(self):
        assert _check(_table([("a", "ACTIVE"), ("b", "CLOSED")])).ok

    def test_source_status_column_with_task_rows(self):
        html = _table([("a", "ACTIVE"),
                       (f'<span style="color: {GREEN};">b</span>',
                        f'<span style="color: {GREEN};">NEW</span>')])
        assert _check(html).ok

    def test_task_cell_still_stripped(self):
        md = f"| a | b |\n| --- | --- |\n| x | +{TASK} |"
        assert words(md_plain(md)) == Counter({"a": 1, "b": 1, "x": 1})

    def test_lost_status_word_detected(self):
        chk = _check(_table([("a", "ACTIVE")]), "| Поле |\n| --- |\n| a | ACTIVE |")
        assert chk.lost_reject == Counter({"status": 1})


class TestLineStartNumbers:
    def test_number_in_separate_node(self):
        assert _check("<p><span>2.</span> Текст абзаца</p>").ok

    def test_numbers_after_br_in_prose(self):
        assert _check("<p>Итоги:<br/>1. первое<br/>2. второе<br/>3. третье</p>").ok

    def test_numbers_after_br_in_html_island(self):
        html = ('<table><tbody><tr><td colspan="2">Договорённости</td></tr>'
                '<tr><td>11.05</td><td><p>1. фильтр<br/>2. кнопки<br/>3. статус</p></td></tr>'
                '</tbody></table>')
        assert _check(html).ok

    def test_number_in_heading_and_bold(self):
        assert _check("<h2>1. Требование к ФЛК</h2><p><strong>2. Если</strong> атрибут заполнен</p>").ok

    def test_number_built_from_colored_nodes(self):
        # после reject «4. Информация», после apply «5. Информация»
        html = (f'<p>заголовок<br/><span style="color: {GREEN};">5</span>'
                f'<s><span style="color: {GREEN};">4</span></s>. Информация о согласиях</p>')
        assert _check(html).ok

    def test_number_inside_list_item_kept(self):
        assert _check("<ol><li>1. уже пронумерованный текст</li></ol>").ok

    # --- НЕсрабатывание: настоящая потеря видна ---

    def test_lost_numbered_paragraph_detected(self):
        html = "<p>1. первое</p><p>2. второе</p>"
        chk = _check(html, "1. первое\n")
        assert chk.lost_reject == Counter({"второе": 1})

    def test_lost_island_number_detected(self):
        html = '<table><tbody><tr><td colspan="2">Т</td></tr><tr><td>a</td><td><p>1. x<br/>2. y</p></td></tr></tbody></table>'
        md = '<table>\n<tbody>\n<tr>\n<td colspan="2">Т</td>\n</tr>\n<tr>\n<td>a</td>\n<td><p>1. x\ny</p></td>\n</tr>\n</tbody>\n</table>'
        assert _check(html, md).lost_reject == Counter({"2": 1})
