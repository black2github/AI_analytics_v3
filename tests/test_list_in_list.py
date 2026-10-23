# tests/test_list_in_list.py
#
# Список прямо внутри списка, без обёртки <li> (2026-10-24, страница 2166860358
# «[Виджет_Карты] Очередь для виджета "Карты к выдаче"», нашёл сторож --check-prom):
#   <ul><ul><li><a>[Виджет_Карты] Метод обработки сообщения о статусе карты</a></li></ul></ul>
# Так редактор Confluence сохраняет список, у которого отступ сделан первому пункту.
# Оба пути списков (проза _process_list и HTML-остров _list_to_html) брали только
# <li> и теряли такой список целиком вместе с текстом — во всех режимах.
#
# Стало: <ul>/<ol> среди детей списка обрабатывается как вложенный список. Тесты
# парами: срабатывание (проза, остров, нумерованный, критик-разметка) и
# НЕсрабатывание (обычный вложенный список через <li> — байты как раньше).

from app.content_extractor import create_critic_extractor
from app.filter_all_fragments import filter_all_fragments
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
CMAP = {"#008000": TASK}

LOST = '<ul><ul><li><a href="/x">Метод обработки</a></li></ul><li>обычный</li><ul><li>под обычным</li></ul></ul>'


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


def _cell(html):
    return f"<table><tbody><tr><td>{html}</td></tr></tbody></table>"


def _island(html):
    return (f"<table><tbody><tr><td>внешняя</td><td><table><tr><td>{html}</td></tr></table>"
            f"</td></tr></tbody></table>")


class TestProse:
    def test_list_without_li_kept(self):
        md = filter_all_fragments(LOST)
        assert md.strip() == "- [Метод обработки](/x)\n- обычный\n    * под обычным"

    def test_ordered(self):
        md = filter_all_fragments("<ol><li>один</li><ol><li>вложенный</li></ol><li>два</li></ol>")
        assert md.strip() == "1. один\n    1. вложенный\n2. два"

    def test_critic_marker_inside(self):
        md = _critic(f'<ul><ul><li><span style="color: {GREEN};">новое</span></li></ul><li>старое</li></ul>')
        assert f"{{++{TASK}: новое++}}" in md
        r = process_text_until_stable(md, "reject", None)[0]
        assert "старое" in r and "новое" not in r

    # --- НЕсрабатывание ---

    def test_regular_nested_list_unchanged(self):
        md = filter_all_fragments("<ul><li>а<ul><li>б</li></ul></li><li>в</li></ul>")
        assert md.strip() == "- а\n    * б\n- в"


class TestHtmlIsland:
    def test_cell_list_without_li_kept(self):
        md = filter_all_fragments(_cell(LOST))
        assert ('<ul><ul><li><a href="/x">Метод обработки</a></li></ul><li>обычный</li>'
                '<ul><li>под обычным</li></ul></ul>') in md

    def test_nested_island_critic(self):
        md = _critic(_island(f'<ul><ul><li><span style="color: {GREEN};">новое</span></li></ul></ul>'))
        assert f'<ul><ul><li><span class="critic-ins" data-task="{TASK}">новое</span></li></ul></ul>' in md

    # --- НЕсрабатывание ---

    def test_regular_nested_list_unchanged(self):
        md = filter_all_fragments(_cell("<ul><li>а<ul><li>б</li></ul></li><li>в</li></ul>"))
        assert "<ul><li>а<ul><li>б</li></ul></li><li>в</li></ul>" in md

    def test_empty_inner_list_adds_nothing(self):
        md = filter_all_fragments(_cell("<ul><ul></ul><li>а</li></ul>"))
        assert "<ul><li>а</li></ul>" in md
