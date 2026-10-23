# tests/test_critic_partial_override_nested.py
#
# Рекурсия частичного перекрытия (дефект 1.9.9, найден сторожем на 2166860176):
#   <span цвет><span чёрный><span цвет>Каждая </span>анкета может …</span> новое</span>
# Чёрный потомок, внутри которого снова есть цветной, разбирался рекурсивно, но его
# СОБСТВЕННЫЙ текст («анкета может…») и бесцветные потомки (ссылка) считались цветом
# внешнего элемента и уходили во вставку — reject-all терял ПРОМ-текст.
#
# Стало: прямой текст и бесцветные потомки наследуют цвет ближайшего окрашенного
# предка по рекурсии (_text_is_black, inherited_black). Три пути парами, с
# НЕсрабатыванием.

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
BLACK = "rgb(0,0,0)"
CMAP = {"#008000": TASK}

NESTED = (f'<span style="color: {GREEN};"><span style="color: {BLACK};">'
          f'<span style="color: {GREEN};">Каждая </span>анкета может <a href="/x">ссылка</a>'
          f'</span> новое</span>')


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _reject(md):
    return process_text_until_stable(md, "reject", None)[0]


def _apply(md):
    return process_text_until_stable(md, "apply", TASK)[0]


def _island(cell):
    inner = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
    return f"<table><tbody><tr><td>внешняя</td><td>{inner}</td></tr></tbody></table>"


def _semantics(md):
    r, a = _reject(md), _apply(md)
    assert "анкета может" in r and "ссылка" in r          # ПРОМ цел
    assert "Каждая" not in r and "новое" not in r         # вставки сняты
    assert "Каждая" in a and "анкета может" in a and "новое" in a


class TestProse:
    def test_black_text_of_mixed_child_outside_marker(self):
        md = _critic(f"<p>{NESTED}</p>")
        assert f"{{++{TASK}: Каждая ++}}анкета может [ссылка](/x) {{++{TASK}: новое++}}" in md
        _semantics(md)

    def test_colorless_child_inside_black_is_black(self):
        md = _critic(f'<p><span style="color: {GREEN};"><span style="color: {BLACK};">'
                     f'<em>курсив</em> <span style="color: {GREEN};">цвет</span></span> хвост</span></p>')
        r = _reject(md)
        assert "курсив" in r and "цвет" not in r and "хвост" not in r

    def test_plain_partial_override_unchanged(self):
        # НЕсрабатывание: случай 1.9.9 без вложенного цвета — как было
        md = _critic(f'<p><span style="color: {GREEN};"><span style="color: {BLACK};">ПРОМ</span>'
                     f': <a href="/y">ссылка</a></span></p>')
        assert f"ПРОМ{{++{TASK}: : [ссылка](/y)++}}" in md


class TestHtmlIsland:
    def test_cell(self):
        md = _critic(_island(f"<p>{NESTED}</p>"))
        assert (f'<span class="critic-ins" data-task="{TASK}">Каждая </span>анкета может '
                f'<a href="/x">ссылка</a><span class="critic-ins" data-task="{TASK}"> новое</span>') in md
        _semantics(md)

    def test_list_item(self):
        md = _critic(_island(f"<ul><li>{NESTED}</li></ul>"))
        assert f'data-task="{TASK}">анкета' not in md
        _semantics(md)

    def test_plain_partial_override_unchanged(self):
        md = _critic(_island(f'<p><span style="color: {GREEN};"><span style="color: {BLACK};">ПРОМ</span>'
                             f' новое</span></p>'))
        assert f'<p>ПРОМ<span class="critic-ins" data-task="{TASK}"> новое</span></p>' in md


class TestTableRow:
    def test_cell_not_row_edit(self):
        html = f'<table><tbody><tr><th>А</th></tr><tr><td>{NESTED}</td></tr></tbody></table>'
        md = _critic(html)
        assert f"| +{TASK} |" not in md
        _semantics(md)


# Та же ошибка наследования в разборе СМЕШАННОГО ЗАЧЁРКИВАНИЯ (страница 2166860176,
# нашёл сторож после первой правки): цветной пункт с зачёркнутым номером внутри, а в
# нём чёрный абзац — прямой текст абзаца и бесцветные потомки уходили во вставку.
STRUCK_NESTED = (f'<span style="color: {GREEN};">новое <span style="color: {BLACK};">'
                 f'Проверки группы <span style="color: {GREEN};">4<s>7</s></span> '
                 f'<a href="/f">Контроли</a></span></span>')


def _semantics_struck(md):
    r, a = _reject(md), _apply(md)
    assert "Проверки группы" in r and "Контроли" in r and "Проверки группы" in a
    assert "новое" not in r and "новое" in a
    assert "7" in r and "4" not in r.replace("4<", "")      # удаление и вставка задачи
    assert "4" in a


class TestMixedStrikeInheritance:
    def test_prose(self):
        md = _critic(f"<p>{STRUCK_NESTED}</p>")
        assert f"{TASK}: Проверки" not in md
        _semantics_struck(md)

    def test_island_cell(self):
        md = _critic(_island(f"<p>{STRUCK_NESTED}</p>"))
        assert f'data-task="{TASK}">Проверки' not in md
        _semantics_struck(md)

    def test_island_list_item_colored_as_whole(self):
        md = _critic(_island(
            f'<ul><li style="color: {GREEN};">новое <p><span style="color: {BLACK};">Проверки группы '
            f'<span style="color: {GREEN};">4<s>7</s></span> <a href="/f">Контроли</a></span></p></li></ul>'))
        assert f'data-task="{TASK}">Проверки' not in md
        _semantics_struck(md)

    def test_table_row(self):
        md = _critic(f'<table><tbody><tr><th>А</th></tr><tr><td>{STRUCK_NESTED}</td></tr></tbody></table>')
        assert f"| +{TASK} |" not in md and f"| -{TASK} |" not in md
        _semantics_struck(md)

    def test_colored_text_without_black_unchanged(self):
        # НЕсрабатывание: смешанное зачёркивание без чёрного — как в 1.9.2
        md = _critic(f'<p><span style="color: {GREEN};">В пол<s>е</s>ях</span></p>')
        assert f"{{--{TASK}: е--}}" in md and f"{{++{TASK}: ях++}}" in md
