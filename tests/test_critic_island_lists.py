# tests/test_critic_island_lists.py
#
# Списки внутри HTML-острова (ячейка вложенной таблицы) в режиме CriticMarkup
# (2026-10-23, страница «[КК_ВК] ЭФ Клиента: Заявка на выпуск карты в режиме
# просмотра», плашка статуса TEAMTB-4518).
#
# Было: _list_to_html рендерил пункты <li> без маркеров — цветной <span> внутри
# пункта уходил в общую ветку как обычный текст, а соседние <p> той же ячейки
# маркеры получали. После reject-all текст задачи оставался в ПРОМ. Форма
# вывода — «каждый абзац размечен, каждый список голый» — и выдала дефект.
#
# Стало: цветной потомок пункта оборачивается <span class="critic-ins|critic-del">
# как в ячейке; пункт, цветной целиком (<li style="color">), — весь; смешанное
# зачёркивание режется, как в 1.9.3. Пары: чёрный пункт остаётся голым, проза
# и простая таблица — без изменений.

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "TEAMTB-4518"
PINK = "rgb(255,153,204)"
CMAP = {"#ff99cc": TASK}


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _island(cell):
    inner = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
    return f"<table><tbody><tr><td>внешняя</td><td>{inner}</td></tr></tbody></table>"


def _apply(md):
    return process_text_until_stable(md, "apply", TASK)[0]


def _reject(md):
    return process_text_until_stable(md, "reject", None)[0]


INS = f'<span class="critic-ins" data-task="{TASK}">'
DEL = f'<span class="critic-del" data-task="{TASK}">'


class TestColoredItems:
    def test_colored_span_in_item_gets_marker(self):
        md = _critic(_island(
            f'<p><span style="color: {PINK};">Плашка.</span></p>'
            f'<ol><li><span style="color: {PINK};"><strong>Если</strong> все исполнены</span></li></ol>'))
        assert f"<li>{INS}<strong>Если</strong> все исполнены</span></li>" in md
        assert "Если" not in _reject(md)           # вставка задачи — в ПРОМ её нет
        assert "Если" in _apply(md)

    def test_item_colored_as_a_whole(self):
        md = _critic(_island(f'<ul><li style="color: {PINK};">весь пункт</li></ul>'))
        assert f"<li>{INS}весь пункт</span></li>" in md

    def test_struck_colored_item_is_deletion(self):
        md = _critic(_island(f'<ul><li><span style="color: {PINK};"><s>старый пункт</s></span></li></ul>'))
        assert f"<li>{DEL}старый пункт</span></li>" in md
        assert "старый пункт" in _reject(md) and "старый пункт" not in _apply(md)

    def test_strike_outside_color_in_item(self):
        # обратный шаблон (1.9.7) внутри пункта
        md = _critic(_island(f'<ul><li><s><span style="color: {PINK};">снаружи</span></s></li></ul>'))
        assert f"{DEL}снаружи</span>" in md and "critic-ins" not in md

    def test_mixed_item_black_and_colored(self):
        md = _critic(_island(f'<ul><li>чёрное <span style="color: {PINK};">цветное</span> хвост</li></ul>'))
        assert f"<li>чёрное {INS}цветное</span> хвост</li>" in md
        assert "чёрное  хвост" in _reject(md)

    def test_nested_list_items_marked(self):
        md = _critic(_island(
            f'<ul><li>внешний<ul><li><span style="color: {PINK};">глубже</span></li></ul></li></ul>'))
        assert f"<li>{INS}глубже</span></li>" in md

    def test_colored_item_with_partial_strike_is_split(self):
        md = _critic(_island(
            f'<ul><li style="color: {PINK};">остаётся <s>убрано</s></li></ul>'))
        assert f"{INS}остаётся </span>{DEL}убрано</span>" in md


class TestNotTriggered:
    def test_black_item_stays_bare(self):
        md = _critic(_island(
            f'<p><span style="color: {PINK};">Плашка.</span></p><ul><li>чёрный пункт</li></ul>'))
        assert "<li>чёрный пункт</li>" in md

    def test_prose_list_unchanged(self):
        md = _critic(f'<ul><li><span style="color: {PINK};">пункт</span></li></ul>')
        assert f"- {{++{TASK}: пункт++}}" in md

    def test_uniform_simple_table_row_unchanged(self):
        # ячейка целиком цветная в простой таблице — удаление/вставка строки
        html = (f'<table><tbody><tr><th>А</th></tr>'
                f'<tr><td><p style="color: {PINK};">Плашка</p>'
                f'<ul><li style="color: {PINK};">пункт</li></ul></td></tr></tbody></table>')
        md = _critic(html)
        assert f'<tr class="critic-row-ins" data-task="{TASK}">' in md
        assert "critic-ins\"" not in md.replace("critic-row-ins", "")
