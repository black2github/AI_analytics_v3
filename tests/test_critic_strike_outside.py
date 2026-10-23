# tests/test_critic_strike_outside.py
#
# Зачёркивание СНАРУЖИ цвета: <s><span color>текст</span></s> (2026-10-23,
# страница «[КК_ВК] ЭФ Клиента: Заявка на выпуск карты», задача TEAMTB-3633).
#
# Было: признак удаления смотрел на сам цветной элемент и его потомков, но не
# на предков. Внешний <s> цвета не имеет — маркер на нём не ставился; на цветном
# спане зачёркивания «не видно» — он помечался ВСТАВКОЙ. Семантика переворачивалась:
# reject-all убирал из ПРОМ текст, который в ПРОМ есть, apply задачи возвращал то,
# что задача удаляет. Табличный путь (строка целиком) поднимался по предкам и был
# прав — отсюда страницы, где абзац «вставлен», а таблица под ним «удалена».
# На одной странице источника таких мест 392 против 94 «правильных».
#
# Три пути разметки проверяются каждый (урок 1.9.2 → 1.9.3): текстовые маркеры,
# строка таблицы, HTML-остров. Пары: обратный шаблон → удаление; прямой шаблон и
# незачёркнутый цвет — без изменений.

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "TEAMTB-3633"
ORANGE = "rgb(255,102,0)"
CMAP = {"#ff6600": TASK}


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _apply(md):
    return process_text_until_stable(md, "apply", TASK)[0]


def _reject(md):
    return process_text_until_stable(md, "reject", None)[0]


class TestInline:
    def test_strike_outside_color_is_deletion(self):
        md = _critic(f'<p><s><span style="color: {ORANGE};">ЭФ состоит из трех страниц:</span></s></p>')
        assert f"{{--{TASK}: ЭФ состоит из трех страниц:--}}" in md
        assert "{++" not in md
        assert "ЭФ состоит" not in _apply(md)        # задача удаляет текст
        assert "ЭФ состоит" in _reject(md)           # в ПРОМ текст остаётся

    def test_strike_inside_color_unchanged(self):
        # НЕсрабатывание: прямой шаблон размечался верно и раньше
        md = _critic(f'<p><span style="color: {ORANGE};"><s>текст</s></span></p>')
        assert f"{{--{TASK}: текст--}}" in md

    def test_unstruck_color_is_still_insertion(self):
        md = _critic(f'<p>До <span style="color: {ORANGE};">новое</span> после</p>')
        assert f"{{++{TASK}: новое++}}" in md and "{--" not in md

    def test_strike_outside_with_black_neighbour(self):
        # внешний <s> накрывает и чёрный текст, и цветной: чёрное зачёркнутое —
        # ПРОМ-текст, остаётся как есть; цветное — удаление задачи
        md = _critic(f'<p><s>чёрное <span style="color: {ORANGE};">цветное</span></s> хвост</p>')
        assert f"чёрное {{--{TASK}: цветное--}} хвост" in md

    def test_deeper_ancestor_strike_counts(self):
        # зачёркивание не прямым родителем, а выше: <s><em><span color>
        md = _critic(f'<p><s><em><span style="color: {ORANGE};">курсив</span></em></s></p>')
        assert f"{{--{TASK}: " in md and "{++" not in md


class TestTableRow:
    def test_row_struck_outside_color_is_row_deletion(self):
        # НЕсрабатывание регресса: табличный путь и раньше был прав
        html = ('<table><tbody><tr><th>Имя</th></tr>'
                f'<tr><td><s><span style="color: {ORANGE};">Строка</span></s></td></tr></tbody></table>')
        md = _critic(html)
        assert f"| Строка | -{TASK} |" in md


class TestHtmlIsland:
    @staticmethod
    def _island(cell):
        inner = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
        return f"<table><tbody><tr><td>внешняя</td><td>{inner}</td></tr></tbody></table>"

    def test_strike_outside_color_is_critic_del(self):
        md = _critic(self._island(f'<s><span style="color: {ORANGE};">удал</span></s> остаётся'))
        assert f'<span class="critic-del" data-task="{TASK}">удал</span>' in md
        assert "critic-ins" not in md
        assert "удал" not in _apply(md) and "удал" in _reject(md)

    def test_strike_inside_color_in_island_unchanged(self):
        md = _critic(self._island(f'<span style="color: {ORANGE};"><s>удал</s></span> остаётся'))
        assert f'<span class="critic-del" data-task="{TASK}">удал</span>' in md

    def test_unstruck_color_in_island_is_critic_ins(self):
        md = _critic(self._island(f'<span style="color: {ORANGE};">новое</span> остаётся'))
        assert "critic-ins" in md and "critic-del" not in md
