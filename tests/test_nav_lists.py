# tests/test_nav_lists.py
"""Навигационный список страницы: связный список из ссылок и названий не считается уровнями К-24
и не требует кавычечных литералов. Один пункт иного вида — блок сверяется как прежде."""
import pytest

from app.scripts.CI.kitcheck.checks.card_source import check_quoted_literals, quoted_literals
from app.scripts.CI.kitcheck.checks.card_steps import check_nesting_depth
from app.scripts.CI.kitcheck.core import is_soft_signal
from app.scripts.CI.kitcheck.md import NAV_LINK_SHARE, blank_nav_lists, nav_list_blocks

TOC = ("- [\\[КК\\] Раздел]([КК]-Страница/[КК]-Раздел.md)\n"
       "    * [\\[КК\\] ЭФ \"Журнал заявок\"]([КК]-Страница/[КК]-ЭФ.md)\n"
       "        + [Функция \"Подпись\"](https://x/pages/viewpage.action?pageId=1)\n"
       "            - [Глубже (версия 2)](y.md)\n")


def _src(body: str) -> str:
    return f"---\ntitle: 'Т'\nconfluence_page_id: '1'\n---\n\n{body}"


def _deep_steps() -> str:
    return "- шаг один\n    * уточнение\n        + подробность\n            - деталь\n"


# ---------------------------------------------------------------- признак блока

def test_all_links_is_nav():
    assert nav_list_blocks(TOC) == [(0, 4)]


def test_blank_keeps_line_count_and_counts():
    text = "до\n" + TOC + "после"
    out, n, k = blank_nav_lists(text)
    assert (n, k) == (1, 4)
    assert out.count("\n") == text.count("\n") and "Журнал" not in out and "после" in out


def test_titles_within_share_stay_nav():
    text = "- [а](a.md)\n- [б](b.md)\n- [в](c.md)\n- DRAFT [КК] Название без адреса\n"
    assert nav_list_blocks(text) == [(0, 4)]


def test_share_below_threshold_not_nav():
    assert NAV_LINK_SHARE > 0.5
    assert nav_list_blocks("- [а](a.md)\n- Название\n") == []


def test_only_titles_not_nav():
    assert nav_list_blocks("- Первое название\n- Второе название\n") == []


@pytest.mark.parametrize("item", [
    "[а](a.md) — вызывается при ошибке",           # текст после ссылки
    "см. [а](a.md)",                               # текст перед ссылкой
    "**Если** статус новый",                       # условие нотации
    "Если статус новый, то показать",              # условие прозой
    "Статус = NEW",                                # присваивание
    "Срок 5 минут",                                # число с единицей
    "Показать сообщение.",                         # конец предложения
    "Сначала проверить. Затем сохранить",          # два предложения
    "Значение: ",                                  # подводка к значению
    "<b>Важно</b> название",                       # разметка
])
def test_one_other_item_breaks_block(item):
    text = f"- [а](a.md)\n- [б](b.md)\n- [в](c.md)\n- [г](d.md)\n- {item}\n"
    assert nav_list_blocks(text) == [], item


def test_block_breaks_on_non_list_line():
    text = "- [а](a.md)\n\nТекст абзаца\n\n- Шаг с условием, запятой\n- [б](b.md)\n"
    assert nav_list_blocks(text) == [(0, 1)]


def test_list_inside_code_block_not_nav():
    assert nav_list_blocks("```\n- [а](a.md)\n- [б](b.md)\n```\n") == []


def test_numbered_list_and_crlf():
    assert nav_list_blocks("1. [а](a.md)\r\n2) [б](b.md)\r\n") == [(0, 2)]


# ---------------------------------------------------------------- К-24

def test_k24_toc_levels_not_counted_in_source():
    # страница с плоским текстом и глубоким оглавлением: карточка без оглавления не уплощена
    rep, ok = check_nesting_depth("- шаг\n- шаг два\n", _src("- шаг\n- шаг два\n\nТекст\n\n" + TOC))
    assert ok and rep == []


def test_k24_real_depth_still_fires_next_to_toc():
    rep, ok = check_nesting_depth("- шаг\n- шаг два\n", _src(_deep_steps() + "\nОглавление\n\n" + TOC))
    assert not ok and "уплощена" in rep[0]


def test_k24_toc_in_card_does_not_hide_flattening():
    # оглавление в карточке не выдаёт себя за перенесённые уровни шагов
    card = "- шаг\n- шаг два\n\nОглавление\n\n" + TOC
    rep, ok = check_nesting_depth(card, _src(_deep_steps()))
    assert not ok and "карточка — 1" in rep[0]


def test_k24_steps_with_one_text_item_still_counted():
    src = ("- [а](a.md)\n    * [б](b.md)\n        + [в](c.md)\n"
           "            - [г](d.md) — вызов при ошибке\n")
    rep, ok = check_nesting_depth("- плоско\n", _src(src))
    assert not ok


# ---------------------------------------------------------------- литералы

def test_literals_from_nav_not_required():
    src = _src('Абзац.\n\n' + TOC)
    assert quoted_literals(src, skip_page_link_labels=True) == []


def test_literal_also_outside_nav_stays_required():
    src = _src('Кнопка "Журнал заявок" на форме.\n\n' + TOC)
    assert quoted_literals(src, skip_page_link_labels=True) == ["Журнал заявок"]
    rep, ok = check_quoted_literals("карточка без значения", src)
    assert not ok and any("в карточке отсутствуют 1 из 1" in l for l in rep)


def test_literals_of_non_nav_list_stay_required():
    src = _src('- [а](a.md)\n- [б](b.md)\n- [в](c.md)\n- Кнопка "Сохранить черновик", если заполнено\n')
    rep, ok = check_quoted_literals("карточка без значения", src)
    assert not ok


def test_spelling_call_without_skip_keeps_nav_literals():
    # сторож вариантов написания по чистовику зовёт без skip_page_link_labels: прежнее поведение
    assert "Журнал заявок" in quoted_literals(_src(TOC))


def test_info_line_counts_and_is_visible_on_green_card():
    rep, ok = check_quoted_literals("карточка", _src("Абзац.\n\n" + TOC))
    line = next(l for l in rep if l.startswith("i навигационных списков"))
    assert ok and line == "i навигационных списков не сверялось: 1 (пунктов 4)"
    assert is_soft_signal(line)


def test_no_info_line_without_nav():
    rep, ok = check_quoted_literals("Кнопка Сохранить", _src('Кнопка "Сохранить".\n'))
    assert ok and not any("навигационных" in l for l in rep)
