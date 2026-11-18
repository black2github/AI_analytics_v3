# -*- coding: utf-8 -*-
"""FB-03 сервиса «Обновление сведений» (2026-11-18): строка макетов ЭФ узнаётся и по ярлыку
«Макеты» / «Макеты ЭФ» (ссылки Zeplin, пустая ячейка) — в сверку не входит, как строка Figma;
снятое только ярлыком видно i-строкой. Признак по хосту Figma остаётся."""
import pytest

from app.scripts.CI.kitcheck.checks.card_common import (
    is_layout_label, layout_label_rows, layout_row)
from app.scripts.CI.kitcheck.checks.card_passport import heavy_source_pairs
from app.scripts.CI.kitcheck.checks.card_source import check_source_tables
from app.scripts.CI.kitcheck.core import is_soft_signal

SRC = ("---\ntitle: X\n---\n\n"
       "| **Зачем нужна ЭФ:** | Просмотр списка требований |\n|---|---|\n"
       "| **Как перейти на ЭФ:** | Через боковое меню |\n"
       "| **Макеты ЭФ:** | [Скроллер (записи скрыты)](https://zpl.io/VkMeKv5)<br>"
       "[Фильтр требований](https://zpl.io/V139MdZ) |\n")
CARD = "| Поле | Значение |\n|---|---|\n| Зачем | Просмотр списка требований |\n| Как | Через боковое меню |\n"
NOTE = "i строки макетов ЭФ по ярлыку «Макеты» без ссылок Figma не сверялись: "


@pytest.mark.parametrize("cell", ["Макеты", "Макеты ЭФ", "**Макеты ЭФ:**", "Макеты:",
                                  "<td><strong>Макеты ЭФ:</strong></td>", "<p>макеты&nbsp;эф</p>"])
def test_layout_label_recognized(cell):
    assert is_layout_label(cell)


@pytest.mark.parametrize("cell", ["Макет анкеты клиента ЮЛ", "№ на макете", "Макеты ЭФ клиента",
                                  "Ссылка на макеты", "Макет", ""])
def test_layout_label_not_recognized(cell):
    # НЕсрабатывание: ярлык — ячейка целиком «Макеты» / «Макеты ЭФ», не слово внутри
    assert not is_layout_label(cell)


def test_zeplin_row_by_label_not_required():
    rep, ok = check_source_tables(CARD, SRC)
    assert ok, rep
    assert NOTE + "1 (макеты живут в src, шаблон screen-form)" in rep, rep
    assert is_soft_signal(NOTE + "1"), "строка видна приёмке и при ✓"


def test_empty_layout_row_counted():
    src = SRC.replace("[Скроллер (записи скрыты)](https://zpl.io/VkMeKv5)<br>"
                      "[Фильтр требований](https://zpl.io/V139MdZ)", "-")
    rep, ok = check_source_tables(CARD, src)
    assert ok and NOTE + "1 (макеты живут в src, шаблон screen-form)" in rep, rep


def test_figma_row_by_host_no_note():
    # строка Figma снята по хосту, как прежде — i-строки «по ярлыку» нет
    src = SRC.replace("https://zpl.io/VkMeKv5", "https://www.figma.com/file/abc")
    rep, ok = check_source_tables(CARD, src)
    assert ok and not any(r.startswith(NOTE) for r in rep), rep
    assert layout_row(["Макеты ЭФ", "https://www.figma.com/file/abc"]) == "host"


def test_zeplin_under_other_label_required():
    # НЕсрабатывание: ссылка Zeplin в другой строке паспорта — значение требуется (потеря)
    src = SRC.replace("| **Как перейти на ЭФ:** | Через боковое меню |",
                      "| **Как перейти на ЭФ:** | [Через боковое меню](https://zpl.io/abc) |")
    card = CARD.replace("| Как | Через боковое меню |\n", "")
    rep, ok = check_source_tables(card, src)
    assert not ok and any("в карточке отсутствуют 1 значений" in r for r in rep), rep
    assert NOTE + "1 (макеты живут в src, шаблон screen-form)" in rep, rep


def test_maket_anketa_row_required():
    # НЕсрабатывание: «Макет анкеты» — не строка макетов ЭФ (печатная форма)
    src = SRC.replace("**Макеты ЭФ:**", "**Макет анкеты клиента:**")
    rep, ok = check_source_tables(CARD, src)
    assert not ok and not any(r.startswith(NOTE) for r in rep), rep


def test_layout_word_in_multi_column_data_required():
    # НЕсрабатывание: «№ на макете» — колонка таблицы данных, значения требуются
    src = ("---\ntitle: X\n---\n\n| № на макете | Поле | Описание |\n|---|---|---|\n"
           "| 1 | ИНН | Номер налогоплательщика |\n| 2 | КПП | Код причины постановки |\n")
    rep, ok = check_source_tables("| 1 | ИНН | Номер налогоплательщика |\n", src)
    assert not ok, rep
    assert layout_label_rows(src) == 0


HTML_SRC = ("<table><tbody>\n<tr>\n<td><strong>Как перейти на ЭФ:</strong></td>\n"
            "<td><ul><li>Через меню «Заявки»</li><li>Через уведомление</li></ul></td>\n</tr>\n"
            "<tr>\n<td><strong>Макеты ЭФ:</strong></td>\n"
            "<td><ul><li><a href=\"https://app.zeplin.io/project/1/screen/2\">01. Меню – Заявки</a>"
            "боковое меню</li><li><a href=\"https://app.zeplin.io/project/1/screen/3\">02. Журнал</a></li>"
            "</ul></td>\n</tr>\n</tbody></table>\n")


def test_heavy_pairs_skip_zeplin_layout_row():
    labels = [lb for lb, _c in heavy_source_pairs(HTML_SRC)]
    assert len(labels) == 1 and "Как перейти" in labels[0], labels
    assert layout_label_rows(HTML_SRC) == 1


def test_heavy_pairs_keep_zeplin_under_other_label():
    # НЕсрабатывание: та же тяжёлая ячейка Zeplin под другим ярлыком — тяжёлая пара сверяется
    src = HTML_SRC.replace("<strong>Макеты ЭФ:</strong>", "<strong>Описание ЭФ:</strong>")
    assert len(heavy_source_pairs(src)) == 2
    assert layout_label_rows(src) == 0
