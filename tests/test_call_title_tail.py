"""title карточки вызова: дословный title страницы + « — <имя вызова>» (решение владельца
2026-11-07, замечание ОНБ-В 65). Прочие типы — без изменений."""
from app.scripts.CI.kitcheck.checks.card_source import check_title

SRC = "---\ntitle: 'Подтверждение номера телефона'\n---\nтело\n"


def _card(title, typ="contract-call", pids="[111]"):
    return (f"---\nid: CALL-EXT-001\ntitle: '{title}'\ntype: {typ}\n"
            f"confluence_page_ids: {pids}\n---\nтело\n")


def test_call_title_with_call_name_ok():
    rep, ok = check_title(_card("Подтверждение номера телефона — Отправка СМС-кода"), SRC)
    assert ok
    assert rep[0] == ("title: дословно перенесён ('Подтверждение номера телефона') ✓, "
                      "имя вызова: 'Отправка СМС-кода'")


def test_call_title_verbatim_still_ok():
    rep, ok = check_title(_card("Подтверждение номера телефона"), SRC)
    assert ok and rep[0] == "title: дословно перенесён ('Подтверждение номера телефона') ✓"


def test_call_title_only_call_name_flags():
    # НЕсрабатывание снятия: только имя вызова — ✗ как прежде
    rep, ok = check_title(_card("Отправка СМС-кода"), SRC)
    assert not ok and "расходится" in rep[0]


def test_call_title_empty_tail_flags():
    rep, ok = check_title(_card("Подтверждение номера телефона — "), SRC)
    assert not ok


def test_call_title_hyphen_not_dash_flags():
    # хвост только через « — » (пробел, тире, пробел)
    rep, ok = check_title(_card("Подтверждение номера телефона - Отправка СМС-кода"), SRC)
    assert not ok


def test_call_title_paraphrased_page_part_flags():
    rep, ok = check_title(_card("Подтверждение телефона — Отправка СМС-кода"), SRC)
    assert not ok


def test_page_title_with_dash_inside():
    # тире в самом title страницы: часть до первого « — » не обрезает сверку
    src = "---\ntitle: 'Клиент — Подтверждение номера'\n---\nтело\n"
    rep, ok = check_title(_card("Клиент — Подтверждение номера — Отправка СМС-кода"), src)
    assert ok and "имя вызова: 'Отправка СМС-кода'" in rep[0]
    rep, ok = check_title(_card("Клиент — Отправка СМС-кода"), src)
    assert not ok


def test_function_title_with_dash_compared_whole():
    # у типа function title с « — » сверяется целиком, как сейчас
    rep, ok = check_title(_card("Подтверждение номера телефона — Отправка СМС-кода",
                                typ="function"), SRC)
    assert not ok and "расходится" in rep[0]
