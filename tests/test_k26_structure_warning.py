# tests/test_k26_structure_warning.py
"""К-26 по решению владельца канона (FB-16 КК, 2026-10-19): расхождение рангов тела шага с
источником — предупреждение, когда содержание шага на месте (литералы источника) и
вложенность не уменьшилась (глубина каждого условия, наибольшая глубина списка); брак — при
сплющивании условия, потере литерала, другом числе условий; пропуск шага — К-23."""
from pathlib import Path

import pytest

from app.scripts.CI.kitcheck.checks.card_steps import check_step_body_structure, check_step_markers

SRC = ("---\ntitle: X\n---\n\n"
       "#### Шаг №1. Формирование\n\n"
       "    * clientId = Клиент.<РНК клиента>\n"
       "    * **Если** секция присутствует, **то**\n"
       "        + Если B заполнен, то\n"
       "            - c = 1\n"
       "        + **Иначе**\n"
       "            - c = 2\n"
       "    * d = 3\n\n"
       "Формируется ответ согласно разделу \"[Формат ответа](#id-X-ResponseFormat)\".\n\n"
       "- в фильтре присутствует только данный статус\n\n"
       "#### Шаг №2. Завершение\n\n"
       "    * Процесс завершён\n")

CARD_FORM = ("- **Шаг №1.** Формирование\n"
             "  Формируются параметры вызова:\n"
             "  - clientId = [EXT-002 Клиент](d.md).«РНК клиента»\n"
             "  - **Если** секция присутствует, **то:**\n"
             "    - Если B заполнен, то\n"
             "      - c = 1\n"
             "    - **Иначе**\n"
             "      - c = 2\n"
             "  - d = 3\n"
             "  Формируется ответ согласно разделу «Формат ответа» контракта [INTC-005](i.md).\n"
             "  - в фильтре присутствует только данный статус\n"
             "- **Шаг №2.** Завершение\n"
             "  - Процесс завершён\n")


# ---------------------------------------------------------------- несрабатывание (⚠, не ✗)

def test_export_ranks_same_content_and_nesting_warns_not_fails():
    rep, ok = check_step_body_structure(CARD_FORM, SRC)
    assert ok, rep
    assert any(r.startswith("предупреждение: структура тел шагов") and "№1" in r for r in rep), rep


def test_literal_with_link_and_attribute_notation_count_as_kept():
    # «[Формат ответа](#…)» источника — текстом ссылки; <РНК клиента> — как «РНК клиента»
    rep, ok = check_step_body_structure(CARD_FORM, SRC)
    assert ok and not any("✗" in r for r in rep), rep


KK = Path("C:/doc-as-code/EAS/src-business-cards")
KK_SRC = KK / "sources/confluence/[КК]-Корпоративные-Карты/[КК]-Общая-часть-сервиса-КК/[КК]-Интеграции/ЭКО_Корпоративные-карты"


@pytest.mark.skipif(not KK.exists(), reason="клон КК недоступен")
@pytest.mark.parametrize("card, src", [
    ("docs/srs/bc-component/function/system/fun-sys-15-corp-cards-list.md",
     "ЭКО_Получение-списка-корпоративных-карт.md"),
    ("docs/srs/bc-component/function/system/fun-sys-17-account-export-report.md",
     "ЭКО_Экспорт-отчета-по-счету-карты.md"),
])
def test_kk_pairs_warn_not_fail(card, src):
    rep, ok = check_step_body_structure((KK / card).read_text(encoding="utf-8"),
                                        (KK_SRC / src).read_text(encoding="utf-8"))
    assert ok, rep
    assert any(r.startswith("предупреждение: структура тел шагов") for r in rep), rep


# ---------------------------------------------------------------- срабатывание (✗)

def test_flattened_condition_fails():
    card = CARD_FORM.replace(
        "  - **Если** секция присутствует, **то:**\n    - Если B заполнен, то\n      - c = 1\n"
        "    - **Иначе**\n      - c = 2\n",
        "  - **Если** секция присутствует, **то:** если B заполнен, то c = 1, **иначе** c = 2\n")
    rep, ok = check_step_body_structure(card, SRC)
    assert not ok and any("№1" in r and "✗" in r for r in rep), rep


def test_lost_literal_fails():
    card = CARD_FORM.replace("«Формат ответа»", "ответа")
    rep, ok = check_step_body_structure(card, SRC)
    assert not ok, rep


def test_missing_step_is_k23_failure():
    card = CARD_FORM.split("- **Шаг №2.**")[0]
    rep, ok = check_step_markers(card, SRC)
    assert not ok, rep


# ---------------------------------------------------------------- FB-24: <br> — не HTML-разметка

SRC_BR = ("---\ntitle: X\n---\n\n"
          "#### Шаг №1. Проверка\n\n"
          "Проверка полномочий.\n\n"
          "**Если** полномочий недостаточно, **то** ошибка 403 и переход на шаг 2.\n\n"
          "**Если** полномочия есть, **то** переход на шаг 2.\n\n"
          "#### Шаг №2. Завершение\n\n"
          "Процесс завершён.\n")


def test_br_line_stays_in_profile():
    # --branch-form вставил <br> в абзацы шага: профиль тот же (абзацы), ни ✗, ни ⚠
    card = ("- **Шаг №1.** Проверка\n\n  Проверка полномочий.\n\n"
            "  **Если** полномочий недостаточно,<br>**то** ошибка 403 и переход на шаг 2.\n\n"
            "  **Если** полномочия есть,<br>**то** переход на шаг 2.\n\n"
            "- **Шаг №2.** Завершение\n\n  Процесс завершён.\n")
    rep, ok = check_step_body_structure(card, SRC_BR)
    assert ok and rep == [], rep


def test_real_html_line_still_out_of_profile():
    # строка с настоящей HTML-разметкой по-прежнему вне профиля — расхождение ловится
    card = ("- **Шаг №1.** Проверка\n\n  Проверка полномочий.\n\n"
            "  <strong>Если</strong> полномочий недостаточно, то ошибка 403 и переход на шаг 2.\n\n"
            "  **Если** полномочия есть,<br>**то** переход на шаг 2.\n\n"
            "- **Шаг №2.** Завершение\n\n  Процесс завершён.\n")
    rep, ok = check_step_body_structure(card, SRC_BR)
    assert rep, rep
