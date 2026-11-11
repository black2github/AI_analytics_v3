# tests/test_step_assignments_moved.py
"""К-26: присваивания шага, вынесенные в карточку вызова (постановка прибору 2026-11-11, КК 2.17,
FUN-SYS-13 шаг 4 → CALL-INT-020; решение владельца 11.11: список присваиваний равноценен таблице
привязки). Извиняются только сами присваивания (определение — сторож карточек вызова,
call_algorithms.is_assignment); остаток шага сверяется прежней цепочкой; имена вынесенных
параметров ищутся в группе сверки и карточках вызова по ссылкам. Ссылка на карточку вызова со
слотом (CALL-BC-EXT-001 и CALL-EXT-BC-001 — позиция слота на решении владельца) узнаётся и
сторожем шагов, и подтягиванием карточек вызова для сторожа имён параметров."""
from pathlib import Path

import pytest

from app.scripts.CI.kitcheck.checks.card_run import _CALL_CARD_LINK_RE, _linked_call_cards
from app.scripts.CI.kitcheck.checks.card_steps import (_CALL_LINK_RE, _excused_assignment,
                                                       check_step_body_structure)

ASSIGNS = ("    * absClientId = Входящие параметры.<Сиблинг>.<Идентификатор клиента>\n"
           "    * cardGuid = Входящие параметры.<Сиблинг>.<Внешний идентификатор карты>\n"
           "    * limit = Входящие параметры.<Страница>.<Количество>\n")
COND = "**Если** в процессе обращения выявлены ошибки,<br>**то** формируется ошибка \"-3\".\n\n"
ELSE = "**Иначе** после получения ответа происходит переход на шаг 5.\n\n"
SRC = ("---\ntitle: X\n---\n\n"
       "**Шаг 4.** (запрос на получение данных)\n\n"
       "Происходит вызов метода с параметрами:\n\n"
       + ASSIGNS + "\n" + COND + ELSE +
       "**Шаг 5.** (ФЛК ответа)\n\n"
       "Ответ проходит ФЛК.\n")
CALL = "[CALL-INT-020 РКО Ф1](../contract-call/internal/call-int-020.md)"
CALL_TEXT = ("## Правила заполнения исходящего сообщения\n\n"
             "| Параметр | Значение |\n|---|---|\n"
             "| absClientId | Сиблинг.Идентификатор клиента |\n"
             "| cardGuid | Сиблинг.Внешний идентификатор карты |\n"
             "| limit | Страница.Количество |\n")


def card(step4: str) -> str:
    return ("- **Шаг 4.** (запрос на получение данных)\n\n" + step4 +
            "- **Шаг 5.** (ФЛК ответа)\n\n  Ответ проходит ФЛК.\n")


INTRO = f"  Происходит вызов {CALL} с параметрами по карточке вызова.\n\n"
CARD_OK = card(INTRO + "  " + COND + "  " + ELSE)
FORM_LINE = "предупреждение: структура тел шагов"


# ---------------------------------------------------------------- срабатывание

def test_assignments_moved_to_call_card_warn_not_fail():
    rep, ok = check_step_body_structure(CARD_OK, SRC, group_text=CALL_TEXT)
    assert ok, rep
    assert rep == [r for r in rep if "шага №4" in r] and len(rep) == 1, rep
    assert rep[0].startswith("предупреждение") and \
        "присваивания шага (3) вынесены в карточки вызова: CALL-INT-020" in rep[0], rep


@pytest.mark.parametrize("cid", ["CALL-BC-EXT-001", "CALL-EXT-BC-001", "CALL-KK-BC-INT-002",
                                 "CALL-INT-KK-BC-003"])
def test_slot_call_link_counts(cid):
    # позиция слота на решении владельца (2026-11-11): узнаются обе
    c = CARD_OK.replace("CALL-INT-020", cid)
    rep, ok = check_step_body_structure(c, SRC, group_text=CALL_TEXT)
    assert ok, rep
    assert any(f"вынесены в карточки вызова: {cid}" in r for r in rep), rep


def test_value_condition_counts_as_assignment():
    src = SRC.replace(ASSIGNS, ASSIGNS + "        + **Если** карта закрыта, **то** = 0\n")
    rep, ok = check_step_body_structure(CARD_OK, src, group_text=CALL_TEXT)
    assert ok, rep
    assert any("присваивания шага (4)" in r for r in rep), rep


def test_names_found_in_card_text_without_group_text():
    # без group_text имена ищутся в самом тексте карточки (вызов с объединением группы)
    rep, ok = check_step_body_structure(CARD_OK + "\n" + CALL_TEXT, SRC)
    assert ok, rep


def test_rest_matched_only_by_form_shows_form_line():
    # остаток шага сверяется прежней цепочкой: вводная строка стала пунктом списка — форма
    # экспорта; шаг виден и в строке формы, не только в строке выноса
    c = card(INTRO.replace("  Происходит", "  - Происходит") + "\n  " + COND + "  " + ELSE)
    rep, ok = check_step_body_structure(c, SRC, group_text=CALL_TEXT)
    assert ok, rep
    assert any("присваивания шага (3)" in r for r in rep), rep
    assert any(r.startswith(FORM_LINE) and "№4" in r for r in rep), rep


# ---------------------------------------------------------------- несрабатывание

def test_condition_line_lost_too_still_fails():
    rep, ok = check_step_body_structure(card(INTRO + "  " + ELSE), SRC, group_text=CALL_TEXT)
    assert not ok, rep
    assert any("шаги №4" in r and "✗" in r for r in rep), rep
    assert not any("присваивания шага (" in r for r in rep), rep


def test_no_call_link_still_fails():
    c = card("  Происходит вызов метода с параметрами по карточке вызова.\n\n  " + COND + "  " + ELSE)
    rep, ok = check_step_body_structure(c, SRC, group_text=CALL_TEXT)
    assert not ok, rep
    assert any("шаги №4" in r and "✗" in r for r in rep), rep


def test_names_missing_everywhere_fail_with_list():
    rep, ok = check_step_body_structure(CARD_OK, SRC, group_text="| absClientId | x |\n")
    assert not ok, rep
    assert any("параметров нет" in r and "cardGuid" in r and "limit" in r and "absClientId" not in r
               and "✗" in r for r in rep), rep
    assert not any(r.startswith("предупреждение") and "присваивания" in r for r in rep), rep


def test_condition_with_equals_is_not_excused():
    # «Если сумма = 0, то ошибка» — условие перехода, не присваивание параметра: в сверке остаётся
    src = SRC.replace(ASSIGNS, ASSIGNS + "\n**Если** сумма = 0, то формируется ошибка 400.\n")
    rep, ok = check_step_body_structure(CARD_OK, src, group_text=CALL_TEXT)
    assert not ok, rep


def test_step_label_with_equals_is_not_assignment():
    # ярлык шага со знаком «=» присваиванием не считается: строка остаётся в сверке
    assert _excused_assignment("    * Шаг 4.1 = повторный запрос") is None
    src = SRC.replace(ASSIGNS, ASSIGNS + "    * Шаг 4.1 = повторный запрос «Повтор»\n")
    rep, ok = check_step_body_structure(CARD_OK, src, group_text=CALL_TEXT)
    assert not ok, rep


def test_link_url_equals_is_not_parameter():
    # знак «=» в адресе ссылки источника — не присваивание параметра: строка в сверке, не в выносе
    assert _excused_assignment("См. [страницу](https://conf/x?pageId=1).") is None
    assert _excused_assignment("    * absClientId = Сиблинг.<Ид>") == "absClientId"
    assert _excused_assignment("**Если** карта закрыта, **то** = 0") == ""
    assert _excused_assignment("Если сумма = 0, то ошибка 400") is None
    src = SRC.replace(ASSIGNS, ASSIGNS + "\nСм. «Справочник» [страницы](https://conf/x?pageId=1).\n")
    rep, ok = check_step_body_structure(CARD_OK, src, group_text=CALL_TEXT)
    assert not ok, rep


def test_assignments_kept_in_card_no_new_line():
    # присваивания остались в карточке — выноса нет, отчёт прежний
    c = card(INTRO + "".join("  - " + ln.strip()[2:] + "\n" for ln in ASSIGNS.splitlines())
             + "\n  " + COND + "  " + ELSE)
    rep, _ok = check_step_body_structure(c, SRC, group_text=CALL_TEXT)
    assert not any("присваивания шага (" in r for r in rep), rep


def test_table_case_report_unchanged():
    # прежний случай (КК FUN-SYS-10): таблица с литералом, в карточке — ссылка на карточку вызова
    src = SRC.replace(ASSIGNS, "| Параметр | Значение |\n|---|---|\n| absClientId | «Ид клиента» |\n")
    c = card(INTRO.replace("  Происходит", "  - Происходит") + "\n  " + COND + "  " + ELSE)
    rep, ok = check_step_body_structure(c, src, group_text=CALL_TEXT)
    assert ok, rep
    assert any("таблица шага вынесена в карточки вызова: CALL-INT-020" in r for r in rep), rep
    assert not any("присваивания шага (" in r for r in rep), rep


# ---------------------------------------------------------------- ID со слотом

@pytest.mark.parametrize("cid", ["CALL-EXT-001", "CALL-MOD-004", "CALL-BC-EXT-001", "CALL-EXT-BC-001",
                                 "CALL-KK-BC-INT-002", "CALL-INT-KK-BC-002"])
def test_call_link_re_slot(cid):
    assert _CALL_LINK_RE.search(f"[{cid} Вызов](x.md)").group(1) == cid
    assert _CALL_CARD_LINK_RE.search(f"[{cid}. Вызов](../c/x.md)").group(1) == cid


@pytest.mark.parametrize("bad", ["CALL-BCDEF-EXT-001", "CALL-EXT-BCDEF-001", "CALL-AB-CD-EF-EXT-001",
                                 "CALL-X-EXT-001", "CALL-ABC-001"])
def test_call_link_re_rejects(bad):
    assert _CALL_LINK_RE.search(f"[{bad}](x.md)") is None


@pytest.mark.parametrize("cid", ["CALL-BC-EXT-001", "CALL-EXT-BC-001"])
def test_linked_call_card_with_slot_is_pulled(tmp_path: Path, cid):
    call = tmp_path / "contract-call" / "call.md"
    call.parent.mkdir(parents=True)
    call.write_text(f"---\nid: {cid}\ntype: contract-call\n---\n\n" + CALL_TEXT, encoding="utf-8")
    fun = tmp_path / "function" / "fun.md"
    fun.parent.mkdir(parents=True)
    got = _linked_call_cards(f"Вызов [{cid} Вызов](../contract-call/call.md).\n", fun)
    assert [i for i, _t in got] == [cid]
    assert "absClientId" in got[0][1]


# ---------------------------------------------------------------- правила параметров (б): признак по
# карточке вызова (постановка 2026-11-11, FUN-SYS-15 шаг 3 / FUN-SYS-35 шаг №4 → CALL-INT-023)

P_SRC_LINES = [
    "    * clientId == [Клиент Банка](https://conf/x?pageId=1).<РНК клиента>, для записи == Вход.<Ид>",
    "    * accountId = Вход.<Ид счёта>",
    "    * **Если** секция Вход.cardVirtualNums присутствует, **то**",
    "        + Если Вход.<Внешние ид карт> заполнен, то",
    "            - cardIds = Вход.<Внешние ид карт>",
    "            - isNotIds = false",
    "        + **Иначе**",
    "            - cardIds = Вход.<Кроме номеров>",
    "            - isNotIds = true",
    "    * page.limit = Вход.<Количество>",
    "    * stateAnsStatus заполняется согласно [Таблицы 2](https://conf/t2) — маппинг «всех» статусов",
]
P_RULES = ("## Использование\n\n### Правила заполнения исходящего сообщения\n\n"
           "| Параметр контракта | Правило сервиса |\n|---|---|\n"
           "| `data.clientId` | clientId == [Клиент Банка](../ext/c.md).«РНК клиента», для записи == Вход.«Ид» |\n"
           "| `data.accountId` | accountId = Вход.«Ид счёта» |\n"
           "| `data.cardIds` | **Если** секция присутствует: cardIds = … |\n"
           "| `data.isNotIds` | isNotIds = true / false |\n"
           "| `paging.limit` | page.limit = Вход.«Количество» |\n"
           "| `data.stateAndStatus` | stateAnsStatus заполняется согласно Таблицы 2 — маппинг «всех» статусов |\n"
           "\n### Сопоставление входящего сообщения\n\n| a | b |\n|---|---|\n| x | y |\n")
P_CALL = "[CALL-INT-023 Список карт](../contract-call/internal/call-int-023.md)"
P_TAIL = "Происходит переход на шаг 4\n\n"


def p_src(lines):
    return ("---\ntitle: X\n---\n\n**Шаг 3:** (Формирование параметров)\n\n" + "\n".join(lines) + "\n\n"
            + P_TAIL + "**Шаг 4:** (Выбор)\n\nВыбор варианта.\n")


def p_card(extra=""):
    return ("- **Шаг 3:** (Формирование параметров)\n\n"
            f"  Формируются параметры вызова {P_CALL} по карточке вызова.\n\n" + extra + "  " + P_TAIL
            + "- **Шаг 4:** (Выбор)\n\n  Выбор варианта.\n")


def p_check(src_lines, card=None, rules=P_RULES, cid="CALL-INT-023"):
    calls = {cid: "---\nid: " + cid + "\ntype: contract-call\n---\n\n" + rules}
    return check_step_body_structure(card or p_card(), p_src(src_lines), group_text=rules, call_cards=calls)


def test_param_rules_all_forms_warn():
    rep, ok = p_check(P_SRC_LINES)
    assert ok, rep
    # clientId(==), accountId, cardIds×2, isNotIds×2, page.limit, stateAnsStatus — 8 строк параметров
    assert any("присваивания шага (8) вынесены в карточки вызова: CALL-INT-023" in r for r in rep), rep


def test_param_line_without_equals_and_typo_name():
    rep, ok = p_check(["    * stateAnsStatus заполняется согласно [Таблицы 2](https://conf/t2) — маппинг «всех» статусов"])
    assert ok and any("присваивания шага (1)" in r for r in rep), rep


def test_param_line_text_not_in_rules_stays():
    # имя есть в карточке, текста строки в разделе нет — строка в сверке (ограничитель постановщика)
    rep, ok = p_check(["    * clientId пустой — формируется ошибка «Нет клиента»"])
    assert not ok, rep


def test_param_name_not_in_call_card_fails():
    rep, ok = p_check(P_SRC_LINES + ["    * extraParam == Вход.<Нечто>"])
    assert not ok, rep
    assert not any("присваивания шага (" in r for r in rep), rep


def test_name_mid_line_not_removed():
    rep, ok = p_check(P_SRC_LINES + ["    * Значение clientId == Вход.<Нечто> «пример»"])
    assert not ok, rep


def test_condition_block_with_jump_stays():
    lines = P_SRC_LINES[:2] + ["    * **Если** секция Вход.cardVirtualNums присутствует, **то**",
                               "        + cardIds = Вход.<Внешние ид карт>",
                               "        + переход на шаг 6"]
    rep, ok = p_check(lines)
    assert not ok, rep


def test_condition_block_with_error_stays():
    lines = P_SRC_LINES[:2] + ["    * **Если** секция Вход.cardVirtualNums присутствует, **то**",
                               "        + **Если** Вход.<Внешние ид карт> пуст, **то**",
                               "            - формируется ошибка «-3»",
                               "        + **Иначе**",
                               "            - cardIds = Вход.<Внешние ид карт>"]
    rep, ok = p_check(lines)
    assert not ok, rep


def test_no_call_cards_previous_behaviour():
    # без call_cards — только присваивания: строка «clientId == …» остаётся, ✗ как прежде
    rep, ok = check_step_body_structure(p_card(), p_src(P_SRC_LINES), group_text=P_RULES)
    assert not ok, rep


def test_step_without_call_link_fails():
    card = p_card().replace(P_CALL, "метода")
    rep, ok = p_check(P_SRC_LINES, card=card)
    assert not ok, rep


def test_call_card_not_linked_from_step_ignored():
    # карточка вызова группы, на которую шаг не ссылается, имён не даёт
    rep, ok = p_check(P_SRC_LINES, cid="CALL-INT-099")
    assert not ok, rep


def test_rules_as_list():
    rules = ("### Правила заполнения исходящего сообщения\n\n"
             "- clientId == [Клиент Банка](../ext/c.md).«РНК клиента», для записи == Вход.«Ид»\n"
             "- stateAnsStatus заполняется согласно Таблицы 2 — маппинг «всех» статусов\n")
    rep, ok = p_check([P_SRC_LINES[0], P_SRC_LINES[-1]], rules=rules)
    assert ok and any("присваивания шага (2)" in r for r in rep), rep


def test_param_rules_kept_in_card_no_line():
    # параметры остались и в шаге карточки — выноса нет
    extra = "".join("  " + ln.strip().replace("* ", "- ", 1) + "\n" for ln in (P_SRC_LINES[0], P_SRC_LINES[-1]))
    rep, _ok = p_check([P_SRC_LINES[0], P_SRC_LINES[-1]], card=p_card(extra + "\n"))
    assert not any("присваивания шага (" in r for r in rep), rep


def test_param_line_link_text_with_card_id_prefix():
    # карточка пишет ссылку «ID + дословный текст источника»: префикс ID — не различие (_cmp_text)
    rules = P_RULES.replace("[Клиент Банка](../ext/c.md)", "[EXT-002 Клиент Банка](../ext/c.md)")
    rep, ok = p_check([P_SRC_LINES[0]], rules=rules)
    assert ok and any("присваивания шага (1)" in r for r in rep), rep
