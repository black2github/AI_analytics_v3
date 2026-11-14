# tests/test_intc_algorithms.py
"""Сторож «в карточке внутреннего контракта нет алгоритма» (скилл create-internal-contracts, шаблон
internal-contracts.md; постановка прибору 2026-11-13, решения постановщика по замеру 13.11): шаги в
тексте карточки, раздел вне состава (второй уровень вне шаблона и первый уровень сверх заголовка),
карточка вне каталога internal-contract/ — по строке ⚠ уровня комплекта, вердикт не меняют.
Несрабатывание: раздел шаблона без шагов, слово «шаг» в середине описания, ссылка на функцию метода
строкой паспорта или под паспортом, js-api, блок кода, sidecar-пример, README реестра, другой тип."""
import sys
from pathlib import Path

from app.scripts.CI.kitcheck.checks.intc_algorithms import analyse, check_intc_algorithms, home_ok

OUT = "   · "
PASSPORT = ("## 1. Краткое описание\n\n| Поле | Значение |\n|---|---|\n| **Название метода** | М |\n"
            "| **Авторизация:** | Bearer token |\n\n")
PARAMS = ("## 2. Входные параметры\n\n| Код параметра | Наименование параметра | Тип | Обяз. | Кратность "
          "| Правила заполнения |\n|---|---|---|---|---|---|\n"
          "| `id` | Идентификатор, заполняется на шаге авторизации | Строка | Да | [1] | |\n\n"
          "## 3. Исходящие параметры и коды результата\n\n| Код параметра | Наименование параметра |\n"
          "|---|---|\n| `data` | Данные |\n\n")
ERRORS = ("## 4. Обработка ошибок и повторные вызовы\n\n| HTTP-код | Ошибка | Описание |\n|---|---|---|\n"
          "| 404 | Not Found | Повторный вызов не выполняется |\n\n")
TAIL = ("## 5. Примеры обмена\n\n| Сценарий | Файл |\n|---|---|\n"
        "| Пример запроса | [intc-001-request.json](examples/intc-001-request.json) |\n\n"
        "## Потребители\n\n| Сервис (`code` каталога) | Локальный ID | Карточка вызова |\n|---|---|---|\n")
ALGO = ("## 6. Алгоритм работы\n\n| № | Название шага | Описание шага |\n|---|---|---|\n"
        "| 1 | Найти клиента | Если найден — перейти на шаг №2, иначе перейти на шаг №3 |\n"
        "| 2 | Ответ | Сформировать ответ |\n\n")


def card(body: str = PASSPORT + PARAMS + ERRORS + TAIL, cid: str = "INTC-001",
         typ: str = "internal-contract") -> str:
    return f"---\nid: {cid}\ntitle: 'Метод'\ntype: {typ}\nservice: x\n---\n\n# {cid}. Метод\n\n" + body


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _run(tmp_path: Path, files):
    docs = tmp_path / "docs"
    for rel, text in files.items():
        _w(docs / rel, text)
    return check_intc_algorithms(docs)


def _heads(rep):
    return [l for l in rep if not l.startswith(OUT)]


# --- срабатывание ---

def test_steps_section_fires_both_signs(tmp_path):
    rep = _run(tmp_path, {"srs/internal-contract/system/intc-001-m.md": card(PASSPORT + PARAMS + ALGO + TAIL)})
    heads = _heads(rep)
    assert heads[0].startswith("⚠ карточка внутреннего контракта — шаги в тексте карточки («Шаг N», "
                               "«переход на шаг N» — объявленная эвристика): 1 карточек (INTC-001)")
    assert heads[1].startswith("⚠ карточка внутреннего контракта — раздел вне состава карточки: 1 "
                               "карточек (INTC-001); разделы: «Алгоритм работы» ×1")
    assert len(heads) == 2
    assert OUT + "srs/internal-contract/system/intc-001-m.md:29 — «Алгоритм работы» — раздел вне состава" in rep
    assert any(l.startswith(OUT + "srs/internal-contract/system/intc-001-m.md:33 — «перейти на шаг №2")
               for l in rep)


def test_steps_inside_template_section(tmp_path):
    # шаги в ячейке паспорта (раздел шаблона) — признак 1 без признака 2
    body = PASSPORT.replace("| **Авторизация:** |",
                            "| **Что делает метод** | **Шаг 1.** Проверить права<br>**Шаг 2.** Найти запись |\n"
                            "| **Авторизация:** |") + PARAMS + ERRORS + TAIL
    rep = _run(tmp_path, {"srs/internal-contract/client/intc-001-m.md": card(body)})
    heads = _heads(rep)
    assert len(heads) == 1 and heads[0].startswith("⚠ карточка внутреннего контракта — шаги в тексте")
    # заголовок «Шаг N» внутри раздела шаблона — тоже шаги
    t = card(PASSPORT + "### Шаг 1. Проверка\n\nтекст\n\n" + PARAMS + ERRORS + TAIL)
    assert [w for _n, w in analyse(t)["steps"]] == ["«Шаг 1. Проверка» — заголовок"]
    assert analyse(t)["sections"] == []


def test_h1_inside_body_is_section(tmp_path):
    t = card(PASSPORT + PARAMS + "## Описание вызова\n\n# Формат запроса\n\nтекст\n\n# Пример вызова\n\n" + TAIL)
    assert [s for _n, s in analyse(t)["sections"]] == ["Описание вызова", "Формат запроса", "Пример вызова"]


def test_section_names_counted_per_card(tmp_path):
    files = {f"srs/internal-contract/bank/intc-00{i}-m.md": card(PASSPORT + "## 2. Функция\n\n[FUN-BNK-01 Ф]"
                                                              "(../../function/bank/f.md)\n\n" + PARAMS + TAIL,
                                                              cid=f"INTC-00{i}") for i in range(1, 6)}
    files["srs/internal-contract/bank/intc-009-m.md"] = card(PASSPORT + "## Где используется\n\nx\n\n"
                                                             "## Где используется\n\ny\n\n" + TAIL, cid="INTC-009")
    heads = _heads(_run(tmp_path, files))
    assert heads == [heads[0]] and heads[0].startswith(
        "⚠ карточка внутреннего контракта — раздел вне состава карточки: 6 карточек (INTC-001, INTC-002, "
        "INTC-003, и ещё 3); разделы: «Функция» ×5, «Где используется» ×1 — ")


def test_home_outside_internal_contract_dir(tmp_path):
    rep = _run(tmp_path, {
        "srs/bc-pin/contract-call/internal/intc-008-otp.md": card(cid="INTC-008"),
        "srs/bc-pin/internal-contract/client/intc-009-otp.md": card(cid="INTC-009"),
        "srs/internal-contract/system/intc-010-x.md": card(cid="INTC-010"),
    })
    assert _heads(rep) == ["⚠ карточка внутреннего контракта — карточка вне каталога internal-contract/: "
                           "1 карточек (INTC-008); каталоги: «srs/bc-pin/contract-call/internal/» ×1 — "
                           "место карточки — srs/internal-contract/ комплекта или srs/<слаг>/internal-contract/ "
                           "части (шаблон internal-contracts.md, «Состав каталога»)"]
    assert rep[1] == OUT + "srs/bc-pin/contract-call/internal/intc-008-otp.md"


def test_home_ok():
    assert home_ok("srs/internal-contract/intc-001-x.md")
    assert home_ok("srs/internal-contract/client/intc-001-x.md")
    assert home_ok("srs/widgets-rtl/internal-contract/client/intc-014-pin.md")
    assert not home_ok("srs/bc-pin/contract-call/internal/intc-008-otp.md")
    assert not home_ok("srs/routing-contracts/to-consumer/message/intc-asc-001.md")
    assert not home_ok("internal-contract/intc-001-x.md")
    # каталог internal-contract глубже части — не дом
    assert not home_ok("srs/a/b/internal-contract/intc-001-x.md")


# --- несрабатывание ---

def test_template_card_silent(tmp_path):
    # раздел «Обработка ошибок и повторные вызовы» без шагов; «шаг» в середине описания параметра;
    # «Приложенные артефакты» и «Из источника, вне разделов шаблона» — в составе
    body = (PASSPORT + PARAMS + ERRORS + TAIL + "\n## Приложенные артефакты\n\nx\n\n"
            "## Из источника, вне разделов шаблона\n\nВызов повторяется на следующем шаге процесса.\n")
    assert _run(tmp_path, {"srs/internal-contract/system/intc-001-m.md": card(body)}) == []


def test_behavior_function_link_silent(tmp_path):
    # ссылка на функцию метода строкой паспорта и строкой «Поведение метода — …» под паспортом
    # (шаблон, правка канона 13.11) — не признак
    in_cell = PASSPORT.replace("| **Авторизация:** |", "| **Что делает метод** | см. раздел «Алгоритм» — "
                               "[FUN-SYS-07 Функция метода](../../function/system/fun-sys-07.md) |\n"
                               "| **Авторизация:** |")
    under = PASSPORT + "Поведение метода — [FUN-SYS-07 Функция метода](../../function/system/fun-sys-07.md)\n\n"
    rep = _run(tmp_path, {
        "srs/internal-contract/system/intc-001-m.md": card(in_cell + PARAMS + ERRORS + TAIL),
        "srs/internal-contract/system/intc-002-m.md": card(under + PARAMS + ERRORS + TAIL, cid="INTC-002"),
    })
    assert rep == []


def test_js_api_function_link_silent(tmp_path):
    body = ("## 1. Краткое описание\n\n| Поле | Значение |\n|---|---|\n| Канал | js-api |\n"
            "| Что делает | смотри раздел \"Процесс запроса ПИН\" — [FUN-CL-64 Клиент: Процесс запроса ПИН]"
            "(../../function/client/fun-cl-64-pin.md) |\n\n" + PARAMS + TAIL)
    assert _run(tmp_path, {"srs/widgets-rtl/internal-contract/client/intc-014-pin.md": card(body, cid="INTC-014")}) == []


def test_code_comment_and_sidecar_silent(tmp_path):
    body = (PASSPORT + "```\n**Шаг 1.** в примере\nперейти на шаг №2\n# Не заголовок\n## Не раздел\n```\n\n"
            "<!--\n## Алгоритм\n**Шаг 1.** x\n-->\n\n" + PARAMS + ERRORS + TAIL)
    rep = _run(tmp_path, {
        "srs/internal-contract/system/intc-001-m.md": card(body),
        "srs/internal-contract/examples/intc-001-request.json": '{"comment": "Шаг 1. перейти на шаг №2"}',
        "srs/internal-contract/examples/intc-001-note.txt": "**Шаг 1.** x\n## Раздел\n",
    })
    assert rep == []


def test_registry_readme_and_other_types_silent(tmp_path):
    algo = card(PASSPORT + ALGO)
    rep = _run(tmp_path, {
        "srs/internal-contract/README.md": algo.replace("INTC-001", "INTC-000"),
        "srs/function/system/fun-sys-01-m.md": card(PASSPORT + ALGO, cid="FUN-SYS-01", typ="function"),
        "srs/contract-call/internal/call-int-001-m.md": card(PASSPORT + ALGO, cid="CALL-INT-001",
                                                             typ="contract-call").replace("internal-contract", "x"),
    })
    assert not any("внутреннего контракта" in l for l in rep)


# --- реестр selfcheck и гейт переноса ---

def test_selfcheck_registry_warning_only(tmp_path):
    from app.scripts.CI import selfcheck as sc
    chk = [c for c in sc.KIT_CHECKS if getattr(c, "id", None) == "intc_algorithms"]
    assert len(chk) == 1 and chk[0].affects_verdict is False
    docs = tmp_path / "docs"
    _w(docs / "srs/bc-pin/contract-call/internal/intc-008-m.md", card(PASSPORT + ALGO, cid="INTC-008"))
    rep, ok = chk[0].run(type("Ctx", (), {"docs": docs})())
    assert ok is True and len(_heads(rep)) == 3


def test_transfer_gate_carries_warning(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_transfer_gate as ttg  # noqa: E402 — сборка комплекта и прогон гейта
    src = ttg.make_src(tmp_path)
    _w(src / "docs/srs/internal-contract/system/intc-001-m.md", card(PASSPORT + ALGO))
    lines, _ready, _ = ttg._run(src)
    got = [l for l in lines if "карточка внутреннего контракта — " in l]
    # готовность комплекта решают другие проверки (у фикстуры нет строки INTC в матрице); сторож
    # блокером не становится
    assert not any(l.startswith("✗") for l in got)
    assert any(l.startswith("⚠ [ПРИБОР] карточка внутреннего контракта — шаги в тексте карточки") for l in got)
    assert any(l.startswith("⚠ [ПРИБОР] карточка внутреннего контракта — раздел вне состава") for l in got)
