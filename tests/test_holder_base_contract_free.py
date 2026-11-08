# -*- coding: utf-8 -*-
"""Держатель шагов (функция, процесс) со строкой «**Базовый контракт:** [EXTINT-…](…)» получает
освобождение состава страницы метода, как тонкая карточка вызова: таблицы и имена параметров
страницы — в базовом контракте; литералы прозы и шаги сверяются как прежде (решение владельца
2026-11-08, КК FUN-SYS-41 ← страница метода SVFE)."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc

P1 = "2184432769"
SRC = (f"---\ntitle: 'Метод ПЦ: получение информации по карте'\nconfluence_page_id: '{P1}'\n---\n\n"
       "Шаг №1 Формируется запрос получения информации\n\n"
       "Шаг №2 Полученный ответ проходит ФЛК\n\n"
       "Шаг №3 Возвращаются код и описание ошибки «Сервис недоступен»\n\n"
       "| Код | Описание |\n|---|---|\n| 100 | Неверный формат запроса |\n| 200 | Карта не найдена |\n"
       "| 300 | Внутренняя ошибка ПЦ |\n\n"
       "<table><tbody><tr><th>Параметр</th><th>Тип</th><th>Описание</th></tr>"
       "<tr><td>virtualCardNumber</td><td>Строка</td><td>Номер карты</td></tr>"
       "<tr><td>requestState</td><td>Строка</td><td>Статус</td></tr></tbody></table>\n")
STEPS = ("## Поведение\n\n**Шаг 1.** Формируется запрос получения информации.\n\n"
         "**Шаг 2.** Полученный ответ проходит ФЛК.\n\n"
         "**Шаг 3.** Возвращаются код и описание ошибки «Сервис недоступен».\n")
BASE = "**Базовый контракт:** [EXTINT-SVFE-002. Получение информации по карте](https://x/-/blob/HEAD/svfe/a.md)\n\n"


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def run(tmp_path, body, typ="function"):
    docs = tmp_path / "kit/docs"
    src = tmp_path / "kit/sources/confluence"
    make(docs / "traceability-matrix.md", "# М\n")
    make(docs / "srs/function/fun-sys-41.md",
         f"---\nid: FUN-SYS-41\ntitle: 'Метод ПЦ: получение информации по карте'\ntype: {typ}\n"
         f"confluence_page_ids: [{P1}]\n---\n\n# FUN-SYS-41. Метод ПЦ: получение информации по карте\n\n{body}")
    make(src / f"{P1}.md", SRC)
    return sc.run(docs, src)


def _lines(report, needle):
    return [ln for ln in report if needle in ln]


def test_function_with_base_contract_line_table_composition_free(tmp_path):
    report, _ok = run(tmp_path, BASE + STEPS)
    assert _lines(report, "i паспорт и состав страницы метода — в базовом контракте EXTINT-SVFE-002"), report
    assert _lines(report, "i состав страницы метода: состав параметров"), report
    assert not _lines(report, "имён параметров ✗"), report
    assert not [ln for ln in report if "таблиц" in ln and "НИЖЕ ПОРОГА" in ln], report


def test_process_with_base_contract_line_free(tmp_path):
    report, _ok = run(tmp_path, BASE + STEPS, typ="process")
    assert _lines(report, "i паспорт и состав страницы метода — в базовом контракте EXTINT-SVFE-002"), report


def test_function_without_line_flagged_as_before(tmp_path):
    # НЕсрабатывание: без строки «Базовый контракт:» — состав страницы сверяется, ✗ как прежде
    report, ok = run(tmp_path, STEPS)
    assert not _lines(report, "состав страницы метода"), report
    assert [ln for ln in report if "НИЖЕ ПОРОГА" in ln], report
    assert not ok


def test_prose_literal_still_checked(tmp_path):
    # НЕсрабатывание: литерал прозы по-прежнему требуется
    report, ok = run(tmp_path, BASE + STEPS.replace("«Сервис недоступен»", "текст ошибки"))
    assert [ln for ln in report if "кавычечные литералы" in ln and "Сервис недоступен" in ln], report
    assert not ok


def test_base_line_inside_code_block_not_counted(tmp_path):
    body = "```text\n" + BASE + "```\n\n" + STEPS
    report, _ok = run(tmp_path, body)
    assert not _lines(report, "состав страницы метода"), report


def test_screen_form_not_freed(tmp_path):
    # тип вне держателей шагов функции/процесса — освобождения нет
    report, _ok = run(tmp_path, BASE + STEPS, typ="screen-form")
    assert not _lines(report, "состав страницы метода"), report


# ---------------------------------------------------------------- паспорт метода (К-34, К-25d)
# Страница метода с паспортом «лейбл → значение» и таблицами; группа {функция — держатель шагов,
# тонкая карточка вызова}: главная по типу — функция (замечание ОНБ-В 66), её строка «Базовый
# контракт:» снимает лейбл-секции паспорта с группы (КК FUN-SYS-43 + CALL-EXT-014, 2026-11-08).
P2 = "2184432771"
_PASSPORT_SRC = (
    f"---\ntitle: 'Метод ПЦ: установка лимита'\nconfluence_page_id: '{P2}'\n---\n\n"
    "<table><tbody>"
    "<tr><th>Название сервиса</th><td>SVFE cardLimitOper</td></tr>"
    "<tr><th>Система-поставщик сервиса</th><td>ПЦ SVFE</td></tr>"
    "<tr><th>Протокол взаимодействия</th><td><p>СИП: тестовая среда (T1) адрес sip-t08apl порт 8142 метод "
    "/api группа AD для доступа к сервису; промышленная среда (P) адрес sip-p05apl порт 8142 метод /api "
    "группа AD; авторизация Basic ТУЗ сервиса; формат обмена JSON в теле запроса по HTTPS.</p></td></tr>"
    "<tr><th>Где используется</th><td><ul><li>Функция установки лимита по карте клиента в ПЦ</li>"
    "<li>Функция изменения лимита по карте из заявки клиента на управление лимитами</li></ul></td></tr>"
    "</tbody></table>\n\n"
    "Шаг №1 Формируется запрос в ПЦ\n\nШаг №2 Полученный ответ проходит ФЛК\n\n"
    "Шаг №3 Возвращаются код и описание ошибки «Лимит не установлен»\n\n"
    "| Код | Описание |\n|---|---|\n| 100 | Неверный формат |\n| 200 | Карта не найдена |\n")
_FUN_STEPS = ("## Поведение\n\n**Протокол взаимодействия**\n\nСм. базовый контракт.\n\n"
              "**Где используется**\n\nСм. базовый контракт.\n\n"
              "**Шаг 1.** Формируется запрос в ПЦ.\n\n**Шаг 2.** Полученный ответ проходит ФЛК.\n\n"
              "**Шаг 3.** Возвращаются код и описание ошибки «Лимит не установлен».\n")
_BASE2 = "**Базовый контракт:** [EXTINT-SVFE-004. Установка лимита](https://x/-/blob/HEAD/svfe/b.md)\n\n"


def run_group(tmp_path, fun_body):
    docs = tmp_path / "kit/docs"
    src = tmp_path / "kit/sources/confluence"
    make(docs / "traceability-matrix.md", "# М\n")
    make(docs / "srs/function/fun-sys-43.md",
         f"---\nid: FUN-SYS-43\ntitle: 'Метод ПЦ: установка лимита'\ntype: function\n"
         f"confluence_page_ids: [{P2}]\n---\n\n# FUN-SYS-43. Метод ПЦ: установка лимита\n\n{fun_body}")
    make(docs / "srs/contract-call/external/call-ext-014.md",
         f"---\nid: CALL-EXT-014\ntitle: 'Метод ПЦ: установка лимита'\ntype: contract-call\n"
         f"confluence_page_ids: [{P2}]\n---\n\n# CALL-EXT-014. Метод ПЦ: установка лимита\n\n{_BASE2}"
         "## Использование\n\nВызов при установке лимита.\n")
    make(src / f"{P2}.md", _PASSPORT_SRC)
    return sc.run(docs, src)


def test_group_with_holder_line_passport_free(tmp_path):
    report, _ok = run_group(tmp_path, _BASE2 + _FUN_STEPS)
    assert _lines(report, "i паспорт и состав страницы метода — в базовом контракте EXTINT-SVFE-004"), report
    assert not _lines(report, "К-34 лейбл-секции паспорта"), report
    assert not _lines(report, "тяжёлых пар расходится"), report
    assert not [ln for ln in report if "таблиц" in ln and "НИЖЕ ПОРОГА" in ln], report


def test_group_holder_without_line_k34_as_before(tmp_path):
    # НЕсрабатывание: функция без строки «Базовый контракт:» на той же странице — ✗ К-34 как сегодня
    report, ok = run_group(tmp_path, _FUN_STEPS)
    assert _lines(report, "К-34 лейбл-секции паспорта"), report
    assert not ok
