# tests/test_critic_mixed_strike_black.py
#
# Остаток дефекта 1.9.9 (2026-10-23, страница «Заявка на выпуск карты» 2166860176,
# нашёл сторож --check-prom):
#   <span color><s>И</s> <span black>выбранный в анкете держатель является</span> …</span>
# Проверка смешанного зачёркивания (1.9.2/1.9.3) стоит раньше проверки частичного
# перекрытия чёрным, и _split_mixed_strike помечал ВСЕ незачёркнутые потомки
# вставкой — чёрный ПРОМ-текст уходил в {++…++}, reject-all его терял.
#
# Стало: незачёркнутый потомок классифицируется по эффективному цвету — чёрный без
# маркера, смешанный режется как при частичном перекрытии. Три пути парами с
# НЕсрабатыванием (смешанное зачёркивание без чёрного — как раньше).

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
BLACK = "rgb(0,51,102)"
CMAP = {"#008000": TASK}


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _reject(md):
    return process_text_until_stable(md, "reject", None)[0]


def _apply(md):
    return process_text_until_stable(md, "apply", TASK)[0]


def _island(cell):
    inner = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
    return f"<table><tbody><tr><td>внешняя</td><td>{inner}</td></tr></tbody></table>"


MIXED = (f'<span style="color: {GREEN};"><s>И</s> <span style="color: {BLACK};">ПРОМ-текст</span>'
         f' новое</span>')


def _check_semantics(md):
    r, a = _reject(md), _apply(md)
    assert "ПРОМ-текст" in r and "ПРОМ-текст" in a      # чёрное живёт в обоих срезах
    assert "новое" not in r and "новое" in a             # вставка задачи
    assert "И" in r.split("ПРОМ")[0] and "И " not in a   # удаление задачи


class TestProse:
    def test_black_child_outside_markers(self):
        md = _critic(f"<p>{MIXED}</p>")
        assert f"{{--{TASK}: И--}}" in md
        assert f"{{++{TASK}: новое++}}" in md
        assert "ПРОМ-текст" in md and f"{TASK}: ПРОМ-текст" not in md
        _check_semantics(md)

    def test_mixed_child_split_recursively(self):
        md = _critic(f'<p><span style="color: {GREEN};"><s>И</s> <em>а <span style="color: {BLACK};">б</span></em></span></p>')
        r = _reject(md)
        assert "б" in r and "а " not in r

    def test_no_black_unchanged(self):
        # НЕсрабатывание: смешанное зачёркивание без чёрного — как в 1.9.2
        md = _critic(f'<p><span style="color: {GREEN};">В пол<s>е</s>ях</span></p>')
        assert f"{{--{TASK}: е--}}" in md and f"{{++{TASK}: ях++}}" in md


class TestHtmlIsland:
    def test_cell_child(self):
        md = _critic(_island(f"<p>{MIXED}</p>"))
        assert f'<span class="critic-del" data-task="{TASK}">И</span>' in md
        assert f'<span class="critic-ins" data-task="{TASK}"> новое</span>' in md
        assert f'data-task="{TASK}">ПРОМ-текст' not in md
        _check_semantics(md)

    def test_list_item_child(self):
        md = _critic(_island(f"<ul><li>{MIXED}</li></ul>"))
        assert f'data-task="{TASK}">ПРОМ-текст' not in md
        _check_semantics(md)

    def test_list_item_colored_as_whole(self):
        md = _critic(_island(
            f'<ul><li style="color: {GREEN};"><s>И</s> <span style="color: {BLACK};">ПРОМ-текст</span> новое</li></ul>'))
        assert f'data-task="{TASK}">ПРОМ-текст' not in md
        _check_semantics(md)

    def test_no_black_unchanged(self):
        md = _critic(_island(f'<p><span style="color: {GREEN};">В пол<s>е</s>ях</span></p>'))
        assert f'<span class="critic-del" data-task="{TASK}">е</span>' in md
        assert f'<span class="critic-ins" data-task="{TASK}">ях</span>' in md


class TestTableRow:
    def test_cell_with_black_part_not_row_edit(self):
        html = (f'<table><tbody><tr><th>А</th></tr>'
                f'<tr><td>{MIXED}</td></tr></tbody></table>')
        md = _critic(html)
        assert f"| +{TASK} |" not in md and f"| -{TASK} |" not in md
        assert "ПРОМ-текст" in _reject(md) and "новое" not in _reject(md)
