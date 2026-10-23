# tests/test_critic_partial_override.py
#
# Частичное перекрытие цвета чёрным (2026-10-23, страница «[КК_СК] ЭФ Клиента
# "Детальная информация по карте"», плейсхолдер UNKNOWN-ff00ff):
#   <span color><span black>Лимиты на снятие наличных</span>: <a>ссылка</a></span>
#
# Было: правило «внутренний цвет перекрывает внешний» (инцидент 2026-08-06) снимало
# маркер, только когда перекрыт ВЕСЬ текст элемента; при частичном перекрытии
# элемент оборачивался целиком вместе с чёрным текстом — reject-all удалял из ПРОМ
# «Лимиты на снятие наличных». На четырёх страницах ЭФ таких спанов 76. Тестов на
# частичный случай не было: существующий закрывал только полное перекрытие.
#
# Стало: чёрные прогоны — без маркера, цветные — в маркер; три пути разметки
# (проза, строка таблицы, HTML-остров) парами с несрабатыванием.

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"       # #008000 — задача в карте
BLACK = "rgb(0,51,102)"      # тёмно-синий из палитры чёрных
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


FRAG = (f'<p><span style="color: {GREEN};"><span style="color: {BLACK};">Лимиты на снятие '
        f'наличных</span>: <a href="https://x/y">ссылка</a></span></p>')


class TestProse:
    def test_black_part_stays_outside_marker(self):
        md = _critic(FRAG)
        assert f"Лимиты на снятие наличных{{++{TASK}: : [ссылка](https://x/y)++}}" in md
        assert "Лимиты на снятие наличных" in _reject(md)          # ПРОМ не теряется
        assert "ссылка" not in _reject(md)
        assert "Лимиты на снятие наличных: [ссылка](https://x/y)" in _apply(md)

    def test_black_in_the_middle(self):
        md = _critic(f'<p><span style="color: {GREEN};">до <span style="color: {BLACK};">середина</span> после</span></p>')
        # ведущий пробел цветного прогона — ПЕРЕД маркером: критик при apply снимает
        # всё между «ID:» и текстом, внутри маркера пробел пропал бы
        assert f"{{++{TASK}: до ++}}середина {{++{TASK}: после++}}" in md
        assert _reject(md).strip() == "середина"
        assert "до середина после" in _apply(md)

    def test_struck_colored_with_black_part_is_deletion(self):
        md = _critic(f'<p><span style="color: {GREEN};"><s><span style="color: {BLACK};">чёрное</span> цветное</s></span></p>')
        # зачёркнуто всё: чёрное зачёркнутое — ПРОМ-мусор (остаётся как есть),
        # цветное — удаление задачи
        assert f"{{--{TASK}: " in md and "{++" not in md
        assert "чёрное" in _reject(md) and "цветное" in _reject(md)
        assert "цветное" not in _apply(md)

    def test_full_override_unchanged(self):
        # НЕсрабатывание: весь текст перекрыт чёрным — маркера нет (правило 2026-08-06)
        md = _critic(f'<p><span style="color: {GREEN};"><span style="color: {BLACK};">всё чёрное</span></span></p>')
        assert "{++" not in md and "всё чёрное" in md

    def test_no_override_unchanged(self):
        md = _critic(f'<p><span style="color: {GREEN};">всё цветное <a href="x">ссылка</a></span></p>')
        assert f"{{++{TASK}: всё цветное [ссылка](x)++}}" in md

    def test_nested_mixed_child_split_recursively(self):
        md = _critic(f'<p><span style="color: {GREEN};">а <em>б <span style="color: {BLACK};">в</span> г</em> д</span></p>')
        r = _reject(md)
        assert "в" in r and "б" not in r and "г" not in r and "д" not in r


class TestHtmlIsland:
    def test_cell_paragraph_split(self):
        md = _critic(_island(FRAG))
        assert (f'<p>Лимиты на снятие наличных<span class="critic-ins" data-task="{TASK}">: '
                f'<a href="https://x/y">ссылка</a></span></p>') in md
        assert "Лимиты на снятие наличных" in _reject(md) and "ссылка" not in _reject(md)

    def test_list_item_split(self):
        md = _critic(_island(
            f'<ul><li><span style="color: {GREEN};">пункт <span style="color: {BLACK};">чёрный</span> цвет</span></li></ul>'))
        assert (f'<li><span class="critic-ins" data-task="{TASK}">пункт </span>чёрный'
                f'<span class="critic-ins" data-task="{TASK}"> цвет</span></li>') in md
        assert "<li>чёрный</li>" in _reject(md)

    def test_item_colored_as_whole_with_black_part(self):
        md = _critic(_island(
            f'<ul><li style="color: {GREEN};">цвет <span style="color: {BLACK};">чёрный</span></li></ul>'))
        assert f'<li><span class="critic-ins" data-task="{TASK}">цвет </span>чёрный</li>' in md

    def test_full_override_in_island_unchanged(self):
        md = _critic(_island(f'<p><span style="color: {GREEN};"><span style="color: {BLACK};">всё чёрное</span></span></p>'))
        assert "critic-" not in md and "всё чёрное" in md


class TestTableRow:
    def test_uniform_row_unchanged(self):
        # НЕсрабатывание: ячейка целиком цветная без чёрного — строка-вставка
        html = (f'<table><tbody><tr><th>А</th></tr>'
                f'<tr><td><span style="color: {GREEN};">весь текст</span></td></tr></tbody></table>')
        md = _critic(html)
        assert f"| весь текст | +{TASK} |" in md

    def test_row_with_black_part_is_not_a_row_insertion(self):
        # ячейка с чёрным текстом — не целостная правка строки, размечается inline
        html = (f'<table><tbody><tr><th>А</th></tr>'
                f'<tr><td><span style="color: {GREEN};"><span style="color: {BLACK};">ПРОМ</span> новое</span></td></tr></tbody></table>')
        md = _critic(html)
        assert f"| +{TASK} |" not in md
        assert "ПРОМ" in _reject(md) and "новое" not in _reject(md)
