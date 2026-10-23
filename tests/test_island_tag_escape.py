# tests/test_island_tag_escape.py
#
# Плейсхолдеры в угловых скобках, разрезанные по текстовым узлам (2026-10-23,
# страницы «Детальная информация по карте» 2166860490 и «Запрос openApi» 2166865804):
#   &lt;<span style="color: rgb(23,43,77);">accountNum&gt;</span>
# _escape_stray_tag_openers работает на одном узле: «<» без буквы следом и
# «accountNum>» без «<» перед ним по отдельности на тег не похожи, а в склеенном
# острове получался живой <accountNum>: рендер его прячет, критик при reject
# дописывал </error_description></error_description>. В свежей выгрузке КК —
# 17 страниц из 544, 41 вхождение.
#
# Стало: пост-проход _escape_unknown_island_tags по готовому HTML острова —
# «<» перед именем, которого экспортёр не эмитит, экранируется. Тесты парами:
# срабатывание на трёх путях острова (ячейка, пункт списка, цветной потомок) и
# НЕсрабатывание (собственные теги, кириллица, сравнения, идемпотентность, проза).

from app.content_extractor import _escape_unknown_island_tags, create_critic_extractor
from app.filter_all_fragments import filter_all_fragments
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
BLACK = "rgb(0,51,102)"
CMAP = {"#008000": TASK}


def _island(cell):
    inner = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
    return f"<table><tbody><tr><td>внешняя</td><td>{inner}</td></tr></tbody></table>"


def _critic(html):
    return create_critic_extractor(CMAP).extract(html)


class TestHelper:
    def test_split_placeholder_escaped(self):
        s = "<p>= <a href=\"u\">Метод</a>.<accountNum><Исходящие параметры></p>"
        out = _escape_unknown_island_tags(s)
        assert "&lt;accountNum>" in out
        assert "<p>" in out and "</p>" in out and '<a href="u">' in out
        assert "<Исходящие параметры>" in out          # кириллица — текст, не трогаем

    def test_closing_unknown_tag_escaped(self):
        assert _escape_unknown_island_tags("</error_description>") == "&lt;/error_description>"

    # --- НЕсрабатывание ---

    def test_own_tags_untouched(self):
        s = ('<table><tr><td colspan="2"><p style="margin-left: 40.0px">'
             '<span class="critic-ins" data-task="X">a</span><a href="u">b</a><br/>'
             '<strong>c</strong><img src="i.png" alt="x"/></p></td></tr></table>')
        assert _escape_unknown_island_tags(s) == s

    def test_comparisons_digits_cyrillic_untouched(self):
        s = "<p>a < b, сумма <100, <Номер заявки></p>"
        assert _escape_unknown_island_tags(s) == s

    def test_idempotent(self):
        once = _escape_unknown_island_tags("<p><GUID></p>")
        assert once == "<p>&lt;GUID></p>"
        assert _escape_unknown_island_tags(once) == once


class TestIslandPaths:
    def test_cell_split_black_span(self):
        html = _island(f'<p>= <a href="/x">Метод</a>.&lt;<span style="color: {BLACK};">'
                       f'accountNum&gt;</span></p>')
        md = _critic(html)
        assert "&lt;accountNum" in md
        assert ".<accountNum" not in md

    def test_cell_split_plain_span(self):
        html = _island('<p>поле → &lt;<span>error_description&gt;</span> = пусто</p>')
        md = filter_all_fragments(html)
        assert "&lt;error_description" in md
        assert "<error_description" not in md

    def test_list_item_split(self):
        html = _island('<ul><li>идентификатор &lt;<span>GUID&gt;</span></li></ul>')
        md = _critic(html)
        assert "<li>идентификатор &lt;GUID" in md

    def test_colored_part_text_survives_reject_and_apply(self):
        html = _island(f'<p>&lt;<span style="color: {GREEN};">cardholderEmboss&gt;</span></p>')
        md = _critic(html)
        rej = process_text_until_stable(md, "reject", None)[0]
        app = process_text_until_stable(md, "apply", None)[0]
        assert "cardholderEmboss" in app
        assert "cardholderEmboss" not in rej
        assert "</cardholderEmboss" not in app and "</cardholderEmboss" not in rej

    def test_reject_adds_no_closing_tags(self):
        # до починки критик при reject парсил живой тег и дописывал закрывающие
        html = _island(f'<p>поле → &lt;<span>error_description&gt;</span> = пусто '
                       f'<span style="color: {GREEN};">новое</span></p>')
        md = _critic(html)
        rej = process_text_until_stable(md, "reject", None)[0]
        assert "</error_description>" not in rej
        assert "&lt;error_description" in rej
        assert "новое" not in rej

    # --- НЕсрабатывание ---

    def test_whole_placeholder_in_one_node_as_before(self):
        html = _island('<p>.&lt;accountNum&gt;</p>')
        md = _critic(html)
        assert "&lt;accountNum" in md and ".<accountNum" not in md

    def test_prose_unchanged(self):
        # проза — не остров, пост-проход её не касается: текст цел, байты как раньше
        html = '<p>= Метод.&lt;accountNum&gt; и <Номер заявки></p>'
        assert _critic(html) == filter_all_fragments(html)
        assert "accountNum" in _critic(html)

    def test_cyrillic_placeholder_in_island_untouched(self):
        html = _island('<p>.&lt;<span>Наименование продукта&gt;</span></p>')
        md = _critic(html)
        assert "<Наименование продукта>" in md
