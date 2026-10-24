# tests/test_critic_prose_list_item.py
#
# Пункт списка в ПРОЗЕ, окрашенный целиком — цвет на самом <li> (1.9.13; нашлось при
# разборе сигналов сторожа на выгрузке КК 1.9.11): маркер ставился только на цветных
# потомках пункта, текст прямо в <li> маркера не получал — вставка уходила в ПРОМ. В
# HTML-островах это починено в 1.9.8, в прозе нет. Вложенный список цветного пункта
# наследует цвет (CSS) — его пункты без своего цвета тоже размечаются.
# Тесты парами: срабатывание (вставка, удаление, смешанное зачёркивание, частичное
# перекрытие чёрным, вложенный список) и НЕсрабатывание (чёрный пункт, цветной спан в
# пункте, чёрный пункт во вложенном списке, острова — как в 1.9.8).

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
BLACK = "rgb(0,0,0)"
CMAP = {"#008000": TASK}


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _reject(md):
    return process_text_until_stable(md, "reject", None)[0]


def _apply(md):
    return process_text_until_stable(md, "apply", TASK)[0]


class TestColoredItem:
    def test_inserted_item(self):
        md = _critic(f'<ol><li>старый</li><li style="color: {GREEN};">новый</li><li>ещё</li></ol>')
        assert md.strip() == f"1. старый\n2. {{++{TASK}: новый++}}\n3. ещё"
        assert "новый" not in _reject(md) and "новый" in _apply(md)

    def test_deleted_item(self):
        md = _critic(f'<ul><li style="color: {GREEN};"><s>удаляемый</s></li><li>чёрный</li></ul>')
        assert f"{{--{TASK}: удаляемый--}}" in md
        assert "удаляемый" in _reject(md) and "удаляемый" not in _apply(md)

    def test_mixed_strike_item(self):
        md = _critic(f'<ul><li style="color: {GREEN};">В пол<s>е</s>ях</li></ul>')
        assert f"{{--{TASK}: е--}}" in md and f"{{++{TASK}: ях++}}" in md

    def test_item_with_black_part(self):
        md = _critic(f'<ul><li style="color: {GREEN};">новое <span style="color: {BLACK};">ПРОМ</span></li></ul>')
        assert md.strip() == f"- {{++{TASK}: новое ++}}ПРОМ"
        assert _reject(md).strip() == "- ПРОМ"

    def test_nested_list_inherits_item_color(self):
        md = _critic(f'<ul><li style="color: {GREEN};">родитель<ul><li>дочерний</li>'
                     f'<li style="color: {BLACK};">чёрный</li></ul></li></ul>')
        assert f"{{++{TASK}: дочерний++}}" in md
        r = _reject(md)
        assert "дочерний" not in r and "родитель" not in r and "чёрный" in r

    # --- НЕсрабатывание ---

    def test_black_item_unchanged(self):
        assert _critic("<ul><li>чёрный</li><li>ещё</li></ul>").strip() == "- чёрный\n- ещё"

    def test_colored_span_in_item_unchanged(self):
        md = _critic(f'<ul><li>а <span style="color: {GREEN};">б</span></li></ul>')
        assert md.strip() == f"- а {{++{TASK}: б++}}"

    def test_item_fully_overridden_black_unchanged(self):
        md = _critic(f'<ul><li style="color: {GREEN};"><span style="color: {BLACK};">всё чёрное</span></li></ul>')
        assert md.strip() == "- всё чёрное"

    def test_island_item_as_before(self):
        html = (f'<table><tbody><tr><td>в</td><td><table><tr><td><ul>'
                f'<li style="color: {GREEN};">новый</li></ul></td></tr></table></td></tr></tbody></table>')
        assert f'<li><span class="critic-ins" data-task="{TASK}">новый</span></li>' in _critic(html)
