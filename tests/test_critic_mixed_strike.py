# tests/test_critic_mixed_strike.py
#
# Смешанное зачёркивание внутри цветного элемента (2026-09-30, страница
# «[Мультибанкинг_Согл] Запрос openApi»).
#
# Было: `_is_strikethrough` истинен для элемента, лишь СОДЕРЖАЩЕГО <s>, и
# <span color>В пол<s>е</s>ях</span> целиком помечался удалением: {--еях--}.
# apply терял «ях», reject-all возвращал «В полеях» — потеря данных в обе стороны,
# при внешне корректной разметке. Тесты этот случай не покрывали: зачёркнутое
# всегда было единственным содержимым цветного элемента.
#
# Стало: частично зачёркнутый цветной элемент режется на чередование
# {--…--}/{++…++} одной задачи; ячейка с таким содержимым не считается удалением
# строки целиком, а размечается inline.

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "DBOCORPESPLN-103623"
CMAP = {"#800000": TASK}
RED = "rgb(128,0,0)"


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _apply(md):
    return process_text_until_stable(md, "apply", TASK)[0]


def _reject_all(md):
    return process_text_until_stable(md, "reject-all", None)[0]


class TestInline:
    def test_struck_prefix_then_plain_is_del_plus_ins(self):
        html = f'<p>В пол<span style="color: {RED};"><s>е</s>ях</span> сообщения.</p>'
        md = _critic(html)
        assert f"В пол{{--{TASK}: е--}}{{++{TASK}: ях++}} сообщения." in md
        assert "В полях сообщения." in _apply(md)
        assert "В поле сообщения." in _reject_all(md)

    def test_plain_then_struck_suffix(self):
        html = (f'<p>"<span style="color: {RED};">Тело запроса JSON <s>Тело JSON</s>'
                f'</span>" тело.</p>')
        md = _critic(html)
        assert f'"{{++{TASK}: Тело запроса JSON ++}}{{--{TASK}: Тело JSON--}}" тело.' in md
        assert '"Тело запроса JSON " тело.' in _apply(md)
        assert '"Тело JSON" тело.' in _reject_all(md)

    def test_real_paragraph_round_trip(self):
        # абзац со страницы целиком: apply даёт новую редакцию, reject-all — ПРОМ
        html = (f'<p>В пол<span style="color: {RED};"><s>е</s>ях</span>'
                f'<span style="color: rgb(23,43,77);"> "<span style="color: {RED};">'
                f'Тело запроса JSON <s>Тело JSON</s></span>" <span style="color: {RED};">'
                f'<strong>ИЛИ </strong>"Тело ответа JSON"</span> тело запроса или тело '
                f'ответа сообщения сохраняется.</span></p>')
        md = _critic(html)
        assert ('В полях "Тело запроса JSON " **ИЛИ** "Тело ответа JSON" тело запроса '
                'или тело ответа сообщения сохраняется.') in _apply(md)
        assert ('В поле "Тело JSON"  тело запроса или тело ответа сообщения '
                'сохраняется.') in _reject_all(md)

    def test_fully_struck_element_still_single_deletion(self):
        # НЕсрабатывание: целиком зачёркнутый цветной элемент — по-прежнему одно удаление
        html = f'<p>Текст <span style="color: {RED};"><s>старое слово</s></span> конец.</p>'
        md = _critic(html)
        assert f"Текст {{--{TASK}: старое слово--}} конец." in md
        assert "{++" not in md

    def test_unstruck_element_still_single_insertion(self):
        html = f'<p>Текст <span style="color: {RED};">новое слово</span> конец.</p>'
        md = _critic(html)
        assert f"Текст {{++{TASK}: новое слово++}} конец." in md
        assert "{--" not in md

    def test_nested_mixed_child_is_split_recursively(self):
        html = (f'<p>А <span style="color: {RED};">x <em>y <s>z</s> w</em> v</span> Б.</p>')
        md = _critic(html)
        assert "z" in _reject_all(md) and "z" not in _apply(md)
        for ch in "xywv":
            assert ch in _apply(md) and ch not in _reject_all(md)


class TestTableCell:
    def test_mixed_cell_is_not_row_deletion(self):
        html = ('<table><tbody><tr><td>шапка</td></tr>'
                f'<tr><td><span style="color: {RED};">Тело запроса <s>Тело</s></span></td>'
                '</tr></tbody></table>')
        md = _critic(html)
        # ни строкового удаления (столбец status), ни HTML-острова с critic-row-del
        assert f"| -{TASK} |" not in md and "critic-row-del" not in md
        assert "Тело запроса" in _apply(md) and "Тело" in _reject_all(md)
        assert "Тело запроса" not in _reject_all(md)

    def test_fully_struck_cell_is_still_row_deletion(self):
        html = ('<table><tbody><tr><td>шапка</td></tr>'
                f'<tr><td><span style="color: {RED};"><s>Удаляемая</s></span></td>'
                '</tr></tbody></table>')
        md = _critic(html)
        assert f"| Удаляемая | -{TASK} |" in md      # удаление строки через столбец status
