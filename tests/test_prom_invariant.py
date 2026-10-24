# tests/test_prom_invariant.py
#
# Сторож «ПРОМ не потерян» (--check-prom, 2026-10-23). Инвариант: слова reject-all
# совпадают с чёрным текстом источника (плюс всё зачёркнутое), слова apply содержат
# все вставки. Тесты парами: молчит на верной разметке всех трёх путей (проза,
# строка таблицы, HTML-остров) и срабатывает на трёх видах порчи markdown —
# потеря ПРОМ, не снятая вставка, потерянная вставка; границы слов — не нарушение;
# отброшенные пост-проходом удаления вычитаются; секция отчёта; хук экспортёра.

from collections import Counter

import pytest

import app.config as _cfg
from app.content_extractor import create_critic_extractor
from app.prom_invariant import PromCheck, check_prom_invariant, md_plain, words
from app.scripts.CI.critic import postpass_drop_contained_deletions
from app.scripts.migrate_colors import finalize, new_accumulator, render_report_md

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
BLACK = "rgb(0,51,102)"
CMAP = {"#008000": TASK}


def _extract(html):
    ext = create_critic_extractor(CMAP)
    md = ext.extract(html)
    md, dropped = postpass_drop_contained_deletions(md)
    return ext, md, dropped


def _check(html, md=None):
    ext, real_md, dropped = _extract(html)
    return check_prom_invariant(html, md if md is not None else real_md, ext,
                                [d["text"] for d in dropped])


def _island(cell):
    inner = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
    return f"<table><tbody><tr><td>внешняя</td><td>{inner}</td></tr></tbody></table>"


CLEAN_PROSE = (f'<p>Чёрный абзац с <a href="/x">ссылкой</a> и &lt;Номер заявки&gt;.</p>'
               f'<p><span style="color: {GREEN};">Новая вставка задачи</span></p>'
               f'<p>Было <s><span style="color: {GREEN};">удалено задачей</span></s> стало</p>'
               f'<p><span style="color: {GREEN};"><span style="color: {BLACK};">ПРОМ-часть</span>'
               f': <a href="/y">ссылка</a></span></p>'
               f'<p><span style="color: {GREEN};">В пол<s>е</s>ях</span></p>'
               f'<ul><li>пункт&nbsp;один</li><li><span style="color: {GREEN};">пункт два</span></li></ul>'
               f'<p><img src="/i.png" alt="картинка"/></p>')


class TestSilentOnCorrectMarkup:
    def test_prose(self):
        chk = _check(CLEAN_PROSE)
        assert chk.ok, chk.summary()
        assert chk.words_prom > 0 and chk.words_reject == chk.words_prom

    def test_table_rows(self):
        html = (f'<table><tbody><tr><th>А</th><th>Б</th></tr>'
                f'<tr><td>чёрная строка</td><td>текст</td></tr>'
                f'<tr><td><span style="color: {GREEN};">новая строка</span></td>'
                f'<td><span style="color: {GREEN};">целиком</span></td></tr>'
                f'<tr><td><s><span style="color: {GREEN};">удалённая строка</span></s></td>'
                f'<td><s><span style="color: {GREEN};">целиком</span></s></td></tr></tbody></table>')
        chk = _check(html)
        assert chk.ok, chk.summary()

    def test_html_island(self):
        html = _island(f'<p>чёрный <span style="color: {GREEN};">зелёный</span></p>'
                       f'<ul><li><span style="color: {GREEN};">пункт <span style="color: {BLACK};">чёрный</span> цвет</span></li></ul>'
                       f'<p>&lt;<span>accountNum&gt;</span> и <s><span style="color: {GREEN};">старое</span></s></p>')
        chk = _check(html)
        assert chk.ok, chk.summary()

    def test_plain_page_without_colors(self):
        chk = _check("<p>Только чёрный текст.</p><table><tr><td>ячейка</td></tr></table>")
        assert chk.ok and chk.words_prom == 4


class TestDetectsDamage:
    def test_prom_wrapped_into_insertion(self):
        _ext, md, _ = _extract(CLEAN_PROSE)
        damaged = md.replace("Чёрный абзац", f"{{++{TASK}: Чёрный абзац++}}")
        chk = _check(CLEAN_PROSE, damaged)
        assert not chk.ok
        assert chk.lost_reject == Counter({"чёрный": 1, "абзац": 1})
        assert not chk.leaked_reject and not chk.lost_apply

    def test_insertion_not_marked(self):
        _ext, md, _ = _extract(CLEAN_PROSE)
        damaged = md.replace(f"{{++{TASK}: Новая вставка задачи++}}", "Новая вставка задачи")
        chk = _check(CLEAN_PROSE, damaged)
        assert chk.leaked_reject == Counter({"новая": 1, "вставка": 1, "задачи": 1})
        assert not chk.lost_reject

    def test_insertion_dropped(self):
        _ext, md, _ = _extract(CLEAN_PROSE)
        damaged = md.replace(f"{{++{TASK}: Новая вставка задачи++}}", "")
        chk = _check(CLEAN_PROSE, damaged)
        assert chk.lost_apply == Counter({"новая": 1, "вставка": 1, "задачи": 1})
        assert not chk.lost_reject and not chk.leaked_reject

    def test_summary_text(self):
        chk = PromCheck(lost_reject=Counter({"лимиты": 2, "наличных": 1}))
        assert "потеряно из ПРОМ 3 слов (лимиты×2, наличных)" == chk.summary()
        assert PromCheck().summary() == "расхождений нет"


class TestModelExceptions:
    def test_word_boundary_is_not_a_loss(self):
        html = "<p>альфа бета гамма</p>"
        chk = _check(html, "альфабета гамма")
        assert chk.ok
        assert chk.boundary_reject == 3          # альфа, бета ↔ альфабета

    def test_dropped_deletions_excluded(self):
        html = f'<p>текст <s><span style="color: {GREEN};">отброшенное</span></s></p>'
        ext, md, _ = _extract(html)
        md_without = md.replace(f"{{--{TASK}: отброшенное--}}", "")
        assert not check_prom_invariant(html, md_without, ext).ok
        assert check_prom_invariant(html, md_without, ext, ["отброшенное"]).ok

    def test_md_plain_strips_markup_only(self):
        md = (f"| a | status |\n| б | +{TASK} |\n{{++{TASK}: в++}} ![x](i.png) [г](http://u) "
              f'<span class="critic-ins" data-task="{TASK}">д</span> &lt;Номер&gt;')
        # заголовок служебного столбца «status» md_plain не вырезает (1.9.13): в срезах
        # reject/apply его уже удалил критик, а столбец источника с таким именем — текст
        assert words(md_plain(md)) == Counter({"a": 1, "status": 1, "б": 1, "в": 1, "г": 1,
                                               "д": 1, "номер": 1})


class TestReportSection:
    def _report(self, entries):
        acc = new_accumulator()
        acc["prom_invariant"].extend(entries)
        _m, report = finalize(acc, service="KK", migrated_at="2026-10-23")
        return report

    def test_section_lists_pages_and_words(self):
        entry = {"page": "ЭФ Клиента", **PromCheck(
            lost_reject=Counter({"лимиты": 2}), lost_apply=Counter({"новое": 1})).as_report()}
        report = self._report([entry])
        assert report["stats"]["positions_manual_review"] == 1
        md = render_report_md(report)
        assert "## Инвариант ПРОМ нарушен (--check-prom)" in md
        assert "- «ЭФ Клиента»: потеряно из ПРОМ 2 слов (лимиты×2); потеряно при apply 1 слов (новое)" in md

    def test_empty_section(self):
        md = render_report_md(self._report([]))
        assert "нужен разбор (0)" in md
        assert "_нет_" in md.split("Инвариант ПРОМ")[1][:200]


class TestExporterHook:
    """_resolve_page_content: с CHECK_PROM страница проверяется, нарушение — в аккумулятор."""

    @pytest.fixture(autouse=True)
    def _flag(self, monkeypatch):
        monkeypatch.setattr(_cfg, "CHECK_PROM", True)
        monkeypatch.setattr(_cfg, "UNAPPROVED_JIRA_IDS", set())

    def _page(self, html):
        return {"raw_html": html, "full_content": "", "approved_content": ""}

    def test_clean_page_adds_nothing(self):
        from app.scripts.migrate_confluence_tree import _resolve_page_content
        acc = new_accumulator()
        _resolve_page_content(self._page(CLEAN_PROSE), False, True, acc, "страница")
        assert acc["prom_invariant"] == []

    def test_violation_recorded(self, monkeypatch):
        import app.prom_invariant as pi
        from app.scripts.migrate_confluence_tree import _resolve_page_content
        monkeypatch.setattr(pi, "check_prom_invariant",
                            lambda *a, **k: PromCheck(lost_reject=Counter({"лимиты": 1})))
        acc = new_accumulator()
        content = _resolve_page_content(self._page(CLEAN_PROSE), False, True, acc, "страница")
        assert content                                   # выгрузка не прерывается
        assert acc["prom_invariant"][0]["page"] == "страница"
        assert acc["prom_invariant"][0]["lost_reject"] == [("лимиты", 1)]

    def test_flag_off_skips_check(self, monkeypatch):
        import app.prom_invariant as pi
        from app.scripts.migrate_confluence_tree import _resolve_page_content
        monkeypatch.setattr(_cfg, "CHECK_PROM", False)
        called = []
        monkeypatch.setattr(pi, "check_prom_invariant", lambda *a, **k: called.append(1))
        acc = new_accumulator()
        _resolve_page_content(self._page(CLEAN_PROSE), False, True, acc, "страница")
        assert called == [] and acc["prom_invariant"] == []


class TestNormalization1911:
    """Нормализация 1.9.11: на выгрузке КК 1.9.10 из 76 сигналов 50 были ложными —
    нумерация списков (28) и «тегообразный» текст (<vpan>, <XS>, XML в коде — 22)."""

    def test_ordered_list_numbers_not_leaked(self):
        assert _check("<ol><li>первый</li><li>второй<ol><li>вложенный</li></ol></li></ol>").ok

    def test_latin_placeholders_in_prose(self):
        assert _check("<p>Поле &lt;vpan&gt; и &lt;XS&gt; обязательны</p>").ok

    def test_latin_placeholders_in_island(self):
        assert _check(_island("<p>Поле &lt;vpan&gt;, &lt;br&gt; и &lt;<span>id&gt;</span></p>")).ok

    def test_code_block_with_xml_and_html(self):
        html = ('<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA['
                '<client><messageId>1</messageId></client><div class="x">т</div>'
                ']]></ac:plain-text-body></ac:structured-macro>')
        assert _check(html).ok

    def test_literal_br_text(self):
        assert _check("<p>перенос через &lt;br&gt; в ячейке</p>").ok

    # --- НЕсрабатывание: настоящая потеря по-прежнему видна ---

    def test_lost_latin_placeholder_detected(self):
        html = "<p>Поле &lt;vpan&gt; обязательно</p>"
        chk = _check(html, "Поле обязательно")
        assert chk.lost_reject == Counter({"vpan": 1})

    def test_lost_list_item_detected(self):
        html = "<ol><li>первый</li><li>второй</li></ol>"
        chk = _check(html, "1. первый")
        assert chk.lost_reject == Counter({"второй": 1})

    def test_number_text_in_paragraph_kept(self):
        # «N. » в начале строки снимается только как нумерация; число внутри текста — слово
        assert _check("<p>Шаг 1. Проверка</p>").ok
        assert words(md_plain("Шаг 1. Проверка")) == Counter({"шаг": 1, "1": 1, "проверка": 1})

    def test_paragraph_starting_with_number(self):
        # чёрный и цветной абзац, начинающиеся с «1. », и такая же ячейка таблицы
        html = (f'<p>1. Чёрный пункт</p><p><span style="color: {GREEN};">2. Новый пункт</span></p>'
                f'<table><tbody><tr><th>А</th></tr><tr><td>3. Ячейка</td></tr></tbody></table>'
                + _island('<p>4. В острове</p>'))
        chk = _check(html)
        assert chk.ok, chk.summary()

    def test_link_target_with_parentheses(self):
        # адрес со скобками: (Copy) у figma, якорь с (2FAOperationStrategy)
        html = ('<p>Макет: <a href="https://f.com/d/X-(Copy)?node-id=19-278585&amp;t=Yh-4">ссылка</a>, '
                'смотри <a href="#id-Стратегия2(2FAOperationStrategy)-startOper">ниже</a></p>')
        assert _check(html).ok

    def test_negative_number_cell_is_text(self):
        html = '<table><tbody><tr><th>Сдвиг</th></tr><tr><td>-3</td></tr><tr><td>+6</td></tr></tbody></table>'
        assert _check(html).ok

    def test_status_cell_still_stripped(self):
        md = f"| a | status |\n| --- | --- |\n| б | +{TASK} |\n| в | -UNKNOWN-ff00ff |"
        # ячейки ±ID вырезаются; слово заголовка «status» — нет (1.9.13)
        assert words(md_plain(md)) == Counter({"a": 1, "status": 1, "б": 1, "в": 1})
