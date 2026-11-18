# -*- coding: utf-8 -*-
"""Сверка базового контракта с источником: три ложных брака (постановка «Точек» 2026-11-18, шаг 2.57
КК; приёмка предложения 18.11). Норма — шаблон contract-call.md, раздел A: в базовом контракте только
то, что задаёт владелец системы; содержимое потребителя — дословно в его карточке вызова (--call).

А — слова тегового упоминания без тега в контракте: имя параметра владельца целыми ячейками, упоминание
    с тегом — в карточке вызова (EXTINT-F1-064 / CALL-EXT-021, EXTINT-ESK-016 / CALL-EXT-031);
Б — тяжёлая ячейка паспорта, вынесенная в карточку вызова целиком («Привилегии» F1-064, «Где
    используется» ESK-016, EFR-001);
В — сегмент пути <item> (безымянный элемент массива), записанный в источнике текстом &lt;item&gt;
    (ESK-016, 45 путей из 177)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "scripts" / "CI"))

from kitcheck.checks.card_clean import check_source_tag_mentions  # noqa: E402
from kitcheck.checks.card_passport import check_heavy_pair_structure  # noqa: E402
from kitcheck.columns import validate_columns  # noqa: E402
from kitcheck.core import is_soft_signal  # noqa: E402

# ---------------------------------------------------------------- класс А
SRC_A = ("<table>\n<tr><th>Код параметра</th><th>Наименование</th><th>Описание</th></tr>\n"
         "<tr><td>Req/CardProduct</td>\n<td>Карточный продукт</td>\n<td></td></tr>\n"
         "<tr><td>Req/CardProduct/Code</td>\n<td>Код карточного продукта</td>\n"
         "<td>Согласно <a href=\"../m/[КК_ВК]-Карточный-продукт.md\">[КК_ВК] Карточный продукт</a>. "
         "Соответствует реквизиту \"Код карточного продукта\"</td></tr>\n</table>\n")
BASE_A = ("---\nid: EXTINT-F1-064\ntype: external-integration\n---\n\n"
          "| Код параметра | Наименование параметра | Тип |\n|---|---|---|\n"
          "| `Req/CardProduct` | Карточный продукт | CardProductType |\n"
          "| `Req/CardProduct/Code` | Код карточного продукта | string |\n")
CALL_A = ("---\nid: CALL-EXT-021\ntype: contract-call\n---\n\n"
          "| Параметр | Правило |\n|---|---|\n"
          "| Req/CardProduct/Code | Согласно «[КК_ВК] Карточный продукт». Соответствует реквизиту "
          "\"Код карточного продукта\" |\n")
CALLS_A = [("call-ext-021.md", CALL_A)]


def test_a_owner_name_cells_with_call_is_info():
    rep, ok = check_source_tag_mentions(BASE_A, SRC_A, call_texts=CALLS_A)
    assert ok, rep
    assert not any("дефейс" in r for r in rep), rep
    line = next(r for r in rep if r.startswith("i теговые упоминания потребителя"))
    assert "«[КК_ВК] Карточный продукт» (call-ext-021.md)" in line and ": 1 —" in line, line


def test_a_without_call_still_defeis():
    # НЕсрабатывание: без --call — дефейс как прежде
    rep, ok = check_source_tag_mentions(BASE_A, SRC_A)
    assert not ok and any("К-32 дефейс" in r for r in rep), rep


def test_a_call_card_without_tagged_mention_still_defeis():
    # НЕсрабатывание: в карточке вызова упоминания с тегом нет
    call = [("call-ext-021.md", CALL_A.replace("[КК_ВК] ", ""))]
    rep, ok = check_source_tag_mentions(BASE_A, SRC_A, call_texts=call)
    assert not ok and any("К-32 дефейс" in r for r in rep), rep


def test_a_bare_words_in_prose_still_defeis():
    # НЕсрабатывание (образец EXTINT-TESSA-009): тег снят из прозы контракта — не целая ячейка
    base = BASE_A + "\nJSON формируется на основе атрибутов сущности Карточный продукт.\n"
    rep, ok = check_source_tag_mentions(base, SRC_A, call_texts=CALLS_A)
    assert not ok and any("К-32 дефейс" in r for r in rep), rep
    assert not any(r.startswith("i теговые упоминания потребителя") for r in rep), rep


def test_a_no_bare_cell_in_source_still_defeis():
    # НЕсрабатывание: в источнике нет целой ячейки без тега с теми же словами
    src = SRC_A.replace("<td>Карточный продукт</td>", "<td>Продукт карты</td>")
    rep, ok = check_source_tag_mentions(BASE_A, src, call_texts=CALLS_A)
    assert not ok and any("К-32 дефейс" in r for r in rep), rep


def test_a_contract_cell_differs_from_source_cell_still_defeis():
    # НЕсрабатывание: ячейка контракта «Карточный продукт клиента» — в источнике такой ячейки нет
    base = BASE_A.replace("| Карточный продукт |", "| Карточный продукт клиента |")
    rep, ok = check_source_tag_mentions(base, SRC_A, call_texts=CALLS_A)
    assert not ok and any("К-32 дефейс" in r for r in rep), rep


# ---------------------------------------------------------------- класс Б
PRIV = ["Вызывающий метод пользователь должен иметь привилегию на просмотр счетов клиента",
        "Привилегия выдаётся администратором организации по заявке клиента банка",
        "Без привилегии метод возвращает ошибку доступа с кодом отказа в ответе"]
SRC_B = ("<table>\n<tr><th>Система</th><td>РКО Ф1</td></tr>\n"
         "<tr><th>Привилегии</th><td><ul>" + "".join(f"<li>{x}</li>" for x in PRIV) + "</ul></td></tr>\n"
         "</table>\n")
BASE_B = "---\nid: EXTINT-F1-064\ntype: external-integration\n---\n\n## 1. Паспорт\n\nСистема: РКО Ф1.\n"
CALL_B = ("---\nid: CALL-EXT-021\ntype: contract-call\n---\n\n## Привилегии\n\n"
          + "".join(f"- {x}\n" for x in PRIV))
CALLS_B = [("call-ext-021.md", CALL_B)]


def test_b_heavy_cell_in_call_card_is_info():
    rep, ok = check_heavy_pair_structure(BASE_B, SRC_B, call_texts=CALLS_B)
    assert ok, rep
    line = next(r for r in rep if r.startswith("i тяжёлая ячейка паспорта — в карточке вызова"))
    assert "«Привилегии» (call-ext-021.md)" in line and ": 1 —" in line, line


def test_b_without_call_still_flagged():
    # НЕсрабатывание: без --call — ✗ как прежде
    rep, ok = check_heavy_pair_structure(BASE_B, SRC_B)
    assert not ok and any("тяжёлых пар расходится" in r for r in rep), rep


def test_b_partial_in_call_card_still_flagged():
    # НЕсрабатывание: в карточке вызова только первый пункт — не все пробы
    call = [("call-ext-021.md", CALL_B.split("- " + PRIV[1])[0])]
    rep, ok = check_heavy_pair_structure(BASE_B, SRC_B, call_texts=call)
    assert not ok and any("тяжёлых пар расходится" in r for r in rep), rep
    assert not any(r.startswith("i тяжёлая ячейка паспорта — в карточке вызова") for r in rep), rep


def test_b_partly_in_contract_judged_as_before():
    # НЕсрабатывание: проба найдена в контракте — ячейка судится профилем, вынос не засчитывается
    base = BASE_B + "\n" + PRIV[0] + " " + PRIV[1] + "\n"
    rep, ok = check_heavy_pair_structure(base, SRC_B, call_texts=CALLS_B)
    assert not any(r.startswith("i тяжёлая ячейка паспорта — в карточке вызова") for r in rep), rep


# ---------------------------------------------------------------- класс В
HDR = ["Код параметра", "Наименование параметра"]
ROWS = [["Msg/PostAddr/<item>/Type", "Тип адреса"], ["Msg/PostAddr/<item>", "Адрес"], ["Msg/Id", "ID"]]


def _path_col(cols):
    return next(c for c in cols if c["role"] == "путь")


def test_c_angle_segment_from_source_valid():
    col = _path_col(validate_columns(HDR, ROWS, path_index=0, angle_segments={"item"}))
    assert col["valid_pct"] == 100.0 and col["angle_paths"] == 2 and col["angle_names"] == ["item"], col


def test_c_without_source_as_before():
    # НЕсрабатывание: без источника — <item> не путь
    col = _path_col(validate_columns(HDR, ROWS, path_index=0))
    assert col["bad"] == 2 and not col["angle_paths"], col


def test_c_segment_not_in_source_flagged():
    # НЕсрабатывание: сегмента нет в тексте источника
    col = _path_col(validate_columns(HDR, ROWS, path_index=0, angle_segments={"Result"}))
    assert col["bad"] == 2, col


def test_c_rest_of_path_still_validated():
    # НЕсрабатывание: остальной путь не проходит прежнюю форму (пробелы-слова — предложение)
    rows = [["Msg/<item>/это не путь вовсе", "Тип"]]
    col = _path_col(validate_columns(HDR, rows, path_index=0, angle_segments={"item"}))
    assert col["bad"] == 1, col


BASE_C = ("---\nid: EXTINT-ESK-016\ntitle: 'ЕСК Запрос'\ntype: external-integration\n---\n\n"
          "# EXTINT-ESK-016. ЕСК Запрос\n\n"
          "| Код параметра | Наименование параметра | Тип | Обяз. | Кратность |\n|---|---|---|---|---|\n"
          "| `Msg/PostAddr` | Адреса | object | Н | [0..1] |\n"
          "| `Msg/PostAddr/<item>` | Адрес | object | Н | [0..*] |\n"
          "| `Msg/PostAddr/<item>/Type` | Тип адреса | string | Н | [0..1] |\n")


def _run_c(tmp_path, src_body):
    card = tmp_path / "extint-esk-016.md"
    card.write_text(BASE_C, encoding="utf-8")
    src = tmp_path / "src.md"
    src.write_text("---\ntitle: 'ЕСК Запрос'\n---\n\n" + src_body, encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "app/scripts/CI/normalize_tables.py"), "--check", str(card),
                        "--source", str(src)], capture_output=True, cwd=str(ROOT),
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return (r.stdout + r.stderr).decode("utf-8")


def test_c_cli_escaped_item_in_source_is_info(tmp_path):
    out = _run_c(tmp_path, "<table><tr><td>PostAddr</td></tr><tr><td>&lt;item&gt;</td></tr>"
                           "<tr><td>Type</td></tr></table>\n<p>Указывается без имени.</p>\n")
    assert "i сегменты пути в угловых скобках дословно из источника (таблица 0, колонка «Код параметра»): " \
           "2 путей (<item>)" in out, out
    assert "(роль: путь): валидных 100.0%" in out, out


def test_c_cli_item_only_as_markup_flagged(tmp_path):
    # НЕсрабатывание: <item> в источнике — разметка, не текст
    out = _run_c(tmp_path, "<table><tr><td>PostAddr</td></tr></table>\n<item>x</item>\n")
    assert "сегменты пути в угловых скобках" not in out, out
    assert "(роль: путь): валидных 33.3% [1/3] ✗ НИЖЕ ПОРОГА" in out, out


# ---------------------------------------------------------------- видимость при ✓
def test_new_info_lines_visible_on_green_card():
    for line in ("i теговые упоминания потребителя — в карточке вызова, в контракте имя параметра "
                 "владельца целыми ячейками: 1 — «[X] Y» (call.md)",
                 "i тяжёлая ячейка паспорта — в карточке вызова: 1 — «Привилегии» (call.md)",
                 "i сегменты пути в угловых скобках дословно из источника (таблица 1, колонка «Код»): 2 путей "
                 "(<item>)"):
        assert is_soft_signal(line), line
