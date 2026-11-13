# tests/test_call_contract_props.py
"""Сторож свойств контракта и кодов параметров в карточке вызова (шаблон contract-call.md, раздел B;
решения владельца канона 13.11.2026, постановка прибору 2026-11-13): колонки типа, обязательности,
кратности — ✗ у карточки с базовым контрактом, ⚠ без него; строки таблиц привязки без кода — ⚠ только
у карточки с базовым контрактом. Признак базового контракта — значение строки «Базовый контракт»
начинается со ссылки. Несрабатывание: таблица привязки в две колонки, строка данных «Тип…», таблица
«Процессы», документы других типов, код и путь в ячейке, блок кода."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.call_contract_props import (
    analyse, base_contract, check_call_contract_props, has_code)

OUT = "   · "
LF = chr(10)
WITH_BASE = "**Базовый контракт:** [EXTINT-X-001. Метод X](https://h/x/extint-x-001.md) — внешняя АС"
NO_BASE = "**Базовый контракт:** отсутствует — базовый контракт `X_Метод` в общем репозитории не создан"
NOT_SET = ("**Базовый контракт:** ссылка не ставится — описания метода у владельца нет: комплект "
           "`svc` не мигрирован; дословно [страница](https://conf/pages/1)")
PROPS = ("### Формат запроса\n\n| № | Код параметра | Наименование параметра | Тип | Обяз. | Кратность |\n"
         "|---|---|---|---|---|---|\n| 1 | `a` | А | Строка | Да | [1] |\n\n")
PROC = ("### Процессы\n\n| Процесс / функция | Шаг / место | Описание |\n|---|---|---|\n"
        "| [FUN-001](f.md) | Шаг 4 | Тип адреса |\n\n")
BIND = ("### Правила заполнения исходящего сообщения\n\n| Параметр контракта | Правило сервиса |\n"
        "|---|---|\n| `CLIENT_ID` (Идентификатор клиента) | = РНК |\n| data.cards[].id | = x |\n"
        "| Тип адреса | = \"01\" |\n\n")


def card(base: str = WITH_BASE, body: str = "", cid: str = "CALL-EXT-001", typ: str = "contract-call") -> str:
    return (f"---\nid: {cid}\ntitle: 'Вызов'\ntype: {typ}\nservice: x\n---\n\n# {cid}. Вызов\n\n"
            + base + "\n\n## Назначение\n\nСервис обращается к АС X.\n\n"
            "## Использование в сервисе «Сервис»\n\n" + PROC + body)


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _run(tmp_path: Path, files):
    docs = tmp_path / "docs"
    for rel, text in files.items():
        _w(docs / rel, text)
    return check_call_contract_props(docs)


# --- признак базового контракта ---

def test_base_contract_link_in_header_line():
    assert base_contract(WITH_BASE.splitlines()) == "EXTINT-X-001. Метод X"
    # вложенные скобки в метке ссылки
    nested = "**Базовый контракт:** [INTC-002 [Файловый сервис] Выгрузка](https://h/i.md) — сервис"
    assert base_contract([nested]) == "INTC-002 [Файловый сервис] Выгрузка"


def test_base_contract_absent_forms():
    # «ссылка не ставится — …» со ссылкой дальше в пояснении — базового контракта нет
    assert base_contract([NOT_SET]) is None
    assert base_contract([NO_BASE]) is None
    assert base_contract(["Текст без строки базового контракта"]) is None


# --- А. колонки свойств контракта ---

def test_props_with_base_contract_is_defect(tmp_path):
    rep, ok = _run(tmp_path, {"srs/contract-call/external/call-ext-001-x.md": card(body=PROPS)})
    assert ok is False
    assert len(rep) == 1 and rep[0].startswith(
        "✗ карточка вызова CALL-EXT-001 (srs/contract-call/external/call-ext-001-x.md): свойства "
        "контракта записаны второй раз — у карточки есть базовый контракт (EXTINT-X-001. Метод X); "
        "«Формат запроса» — «Тип», «Обяз.», «Кратность»")


def test_props_without_base_contract_is_warning(tmp_path):
    rep, ok = _run(tmp_path, {
        "srs/contract-call/external/call-ext-001-x.md": card(base=NO_BASE, body=PROPS),
        "srs/contract-call/external/call-ext-002-y.md": card(base=NOT_SET, body=PROPS, cid="CALL-EXT-002"),
    })
    assert ok is True
    heads = [l for l in rep if not l.startswith(OUT)]
    assert heads == ["⚠ свойства контракта временно живут в карточке вызова — до появления базового "
                     "контракта: 2 карточек (CALL-EXT-001, CALL-EXT-002) — признак базового контракта: "
                     "значение строки «Базовый контракт» начинается со ссылки"]
    assert [l for l in rep if l.startswith(OUT)] == [
        OUT + "srs/contract-call/external/call-ext-001-x.md:26 — «Формат запроса»: «Тип», «Обяз.», «Кратность»",
        OUT + "srs/contract-call/external/call-ext-002-y.md:26 — «Формат запроса»: «Тип», «Обяз.», «Кратность»"]


def test_props_column_variants_from_measurement():
    for head in ("Тип данных", "Тип параметра", "Тип поля", "Тип и формат данных", "**Обязательность**",
                 "Кратность"):
        t = card(body=f"### Т\n\n| Название параметра | {head} |\n|---|---|\n| a | b |\n")
        assert [c for _n, _s, c in analyse(t)["props"]] == [[head.strip("*")]], head


def test_bare_type_is_property_without_companions(tmp_path):
    # голое «Тип» — свойство контракта всегда, без обязательности и кратности рядом (решение владельца
    # 13.11): при базовом контракте — ✗
    body = "### Т\n\n| Параметр | Тип | Правило заполнения |\n|---|---|---|\n| a | b | c |\n"
    assert [c for _n, _s, c in analyse(card(body=body))["props"]] == [["Тип"]]
    rep, ok = _run(tmp_path, {"srs/contract-call/external/call-ext-001-x.md": card(body=body)})
    assert ok is False and rep[0].startswith("✗ карточка вызова CALL-EXT-001")
    # «№ | Тип | Процесс O2+ (шаг) | Действие» (пример CALL-EXT-003) — тоже срабатывание: колонку
    # другого смысла называют полностью («Тип сообщения»), правится карточка, не сторож
    t = card(body="### Обработка входящих ответов\n\n| № | Тип | Процесс O2+ (шаг) | Действие |\n"
                  "|---|---|---|---|\n| 1 | НОК | [PROC-005](p.md) | x |\n")
    assert [c for _n, _s, c in analyse(t)["props"]] == [["Тип"]]
    t = t.replace("| № | Тип |", "| № | Тип сообщения |")
    assert analyse(t)["props"] == []


def test_props_silent_cases():
    # таблица привязки в две колонки, строка данных «Тип…», «Процессы» с колонкой «Шаг / место»
    t = card(body=BIND + "### Т\n\n| Параметр | Значение |\n|---|---|\n| Тип процесса | Обяз. |\n")
    assert analyse(t)["props"] == []
    # шапки-данные из замера: не колонки свойств
    t = card(body="### Т\n\n| Тип документа | Досье |\n|---|---|\n| a | b |\n\n"
                  "### Ж\n\n| № | Тип сообщения (квитанции) | Тип контента |\n|---|---|---|\n| 1 | a | b |\n")
    assert analyse(t)["props"] == []
    # таблица в блоке кода и в HTML-комментарии — вне проверки
    t = card(body="```\n| Код | Тип | Обяз. |\n|---|---|---|\n| a | b | c |\n```\n\n"
                  "<!--\n| Код | Тип |\n|---|---|\n| a | b |\n-->\n")
    assert analyse(t)["props"] == []


def test_other_document_types_silent(tmp_path):
    # базовый контракт, функция, README реестра с теми же колонками — молчание
    rep, ok = _run(tmp_path, {
        "srs/internal-contract/intc-001-x.md": card(body=PROPS, typ="internal-contract", cid="INTC-001"),
        "ext/extint-x-001.md": card(body=PROPS, typ="external-integration", cid="EXTINT-X-001"),
        "srs/function/fun-001-x.md": card(body=PROPS, typ="function", cid="FUN-001"),
        "srs/contract-call/README.md": card(body=PROPS),
    })
    assert rep == [] and ok is True


# --- Б. строки привязки без кода ---

def test_has_code():
    assert has_code("`CLIENT_ID` (Идентификатор клиента)")
    assert has_code("data.cards[].id")
    assert has_code("Receipt/ErrorCode")
    assert has_code("**CLIENT_ID**")
    assert not has_code("Идентификатор клиента")
    assert not has_code("Тип адреса")
    assert not has_code("**Идентификация досье**")


def test_binding_without_code_with_base_contract(tmp_path):
    num = ("### Сопоставление входящего сообщения\n\n| № | Параметр контракта | Куда записывается в сервисе |\n"
           "|---|---|---|\n| 1 | Статус | [ENT-001](e.md).«Статус» |\n| 2 | — | — |\n")
    rep, ok = _run(tmp_path, {"srs/contract-call/external/call-ext-001-x.md": card(body=BIND + num)})
    assert ok is True
    heads = [l for l in rep if not l.startswith(OUT)]
    assert heads == ["⚠ строки привязки без кода параметра у карточек вызова с базовым контрактом: 2 строк "
                     "в 1 карточках (CALL-EXT-001 ×2) — параметр назвать кодом из базового контракта, "
                     "наименование — в скобках после кода (шаблон contract-call.md)"]
    assert [l for l in rep if l.startswith(OUT)] == [
        OUT + "srs/contract-call/external/call-ext-001-x.md:30 — Тип адреса",
        OUT + "srs/contract-call/external/call-ext-001-x.md:36 — Статус"]


def test_binding_without_code_no_base_contract_silent(tmp_path):
    rep, ok = _run(tmp_path, {
        "srs/contract-call/external/call-ext-001-x.md": card(base=NO_BASE, body=BIND),
        "srs/contract-call/external/call-ext-002-y.md": card(base=NOT_SET, body=BIND, cid="CALL-EXT-002"),
    })
    assert rep == [] and ok is True


def test_binding_only_template_columns():
    # таблица параметров не по шаблону («Параметр | Описание параметра | Заполнение») — не привязка
    t = card(body="### Т\n\n| Параметр | Описание параметра | Заполнение |\n|---|---|---|\n| Имя | a | b |\n\n"
                  "### П\n\n| Параметр | Значение |\n|---|---|\n| Протокол | REST |\n")
    assert analyse(t)["nocode"] == []


# --- реестр selfcheck ---

def test_selfcheck_registry_affects_verdict(tmp_path):
    from app.scripts.CI import selfcheck as sc
    chk = [c for c in sc.KIT_CHECKS if getattr(c, "id", None) == "call_contract_props"]
    assert len(chk) == 1 and chk[0].affects_verdict is True
    docs = tmp_path / "docs"
    _w(docs / "srs/contract-call/external/call-ext-001-x.md", card(body=PROPS))
    rep, ok = chk[0].run(type("Ctx", (), {"docs": docs})())
    assert ok is False and rep[0].startswith("✗ карточка вызова CALL-EXT-001")
    _w(docs / "srs/contract-call/external/call-ext-001-x.md", card(base=NO_BASE, body=PROPS))
    rep, ok = chk[0].run(type("Ctx", (), {"docs": docs})())
    assert ok is True and rep[0].startswith("⚠ свойства контракта временно живут")
