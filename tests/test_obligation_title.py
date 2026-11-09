# tests/test_obligation_title.py
"""Волна Д ОНБ-В, срез 2 (находка П2 п. 6): роль колонки «обязательность» — по совпадению
нормализованного заголовка с закрытым перечнем (`kitcheck/columns.py: obligation_title`), не по
подстроке «обяз». Подстрока отдавала роль колонке «Сообщение об ошибке» групп контролей ОНБ-В
(в шапке — пример текста «"обязательное поле"») и колонкам-условиям таблиц решений эталона.

Перечень: заголовки шаблонов канона («Обяз.», «Обязательность»), комбинированная шапка с
уникальностью и формы источников из реестра словарных эвристик README прибора (замер
2026-11-09)."""
import pytest

from app.scripts.CI import normalize_tables as nt
from app.scripts.CI.kitcheck.columns import (_OBL_SOURCE_TITLES, obligation_title,
                                             obligation_title_key, validate_columns)

# дословная шапка колонки групп контролей ОНБ-В (выгрузка src-onb-v eb4c8c8, «Группа контролей №1»)
ONBV_ERROR_HEAD = ("Сообщение об ошибке<br>На ЭФ сообщения об ошибке выводятся на конкретном поле, "
                   "поэтому <название реквизита> не указывается в тексте. Например, "
                   "\"Обязательное поле\".")


@pytest.mark.parametrize("title", [
    "Обяз.", "обяз", "Обязательность", "**Обязательность**", "**Обязате****льность**",
    "Обяз<br>ательность", "Обязательность (О/Н)", "Обяз.:", " Обязательность ",
])
def test_template_titles_get_role(title):
    assert obligation_title(title) == "obl"


@pytest.mark.parametrize("title", [
    "Обязательность / Уникальность", "Уникальность / Обязательность",
    "Уникальность/Обязательность", "Обязательность/ Уникальность",
    "**Обязательность / Уникальность**", "Обязательность /Уникальность",
])
def test_pair_titles(title):
    assert obligation_title(title) == "pair"


@pytest.mark.parametrize("title", [
    "Обязательность заполнения", "**Обязательность поля в реестре**", "Обязательность в блоке",
    "Обязательный", "Обяз-ть", "Обязатель-ность",
])
def test_source_forms_from_registry(title):
    assert obligation_title(title) == "obl"


@pytest.mark.parametrize("title", [
    "Сообщение об ошибке (обязательное)",
    ONBV_ERROR_HEAD,
    "Возможность отправлять обязательные к прочтению",
    "Обязателен скан контракта",
    "Обязательна вкладка «Реквизиты государственного контракта»",
    "Обязательно согласие о присоединении к правилам сопровождения",
    "Необязательность", "Описание", "Краткое описание", "Тип",
])
def test_not_obligation_column_silent(title):
    """НЕсрабатывание: заголовок со словом «обяз…» — не колонка обязательности."""
    assert obligation_title(title) is None


def test_key_normalization():
    assert obligation_title_key("**Обяз.** (О/Н)") == "обяз"
    assert obligation_title_key("Уникальность /  Обязательность") == "уникальность/обязательность"


def test_source_forms_are_lowercase_keys():
    """Перечень форм источников хранится ключами нормализации — иначе запись не сработает."""
    for k in _OBL_SOURCE_TITLES:
        assert obligation_title_key(k) == k


# ------------------------------------------------------------ потребители признака


def _roles(headers, rows):
    return {c["column"]: c["role"] for c in validate_columns(headers, rows, path_index=None,
                                                             source_mode=True)}


def test_validate_columns_error_message_no_role():
    rows = [["Поле обязательно для заполнения", "ИНН"], ["Неверный формат", "КПП"]]
    assert "Сообщение об ошибке (обязательное)" not in _roles(
        ["Сообщение об ошибке (обязательное)", "Поле"], rows)
    # у дословной шапки ОНБ-В роль «название» — по слову «<название реквизита>» в пояснении
    # (подстрока роли названия, вне среза 2); роли обязательности нет
    assert _roles([ONBV_ERROR_HEAD, "Поле"], rows).get(ONBV_ERROR_HEAD) != "обязат"


def test_validate_columns_obligation_role_kept():
    roles = _roles(["Наименование", "Обяз."], [["ИНН", "Да"], ["КПП", "Нет"]])
    assert roles.get("Обяз.") == "обязат"
    roles = _roles(["Наименование", "Обязательность / Уникальность"], [["ИНН", "Да / Нет"]])
    assert roles.get("Обязательность / Уникальность") == "обязат"


def test_block_roles_by_title():
    blocks = [(0, 0, "Параметр"), (1, 1, ONBV_ERROR_HEAD), (2, 2, "Обязательность"),
              (3, 3, "Сообщение об ошибке (обязательное)")]
    roles = nt._block_roles(blocks, 0)
    assert roles[0] == "path" and roles[2] == "obl" and roles[3] == "free"
    assert roles[1] != "obl"  # «name» по слову «название» в пояснении шапки — вне среза 2


def _table(head, rows):
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tbody><tr>{th}</tr>{tr}</tbody></table>\n"


def test_normalize_file_onbv_error_column_is_not_anchor(tmp_path):
    """Таблица групп контролей ОНБ-В без колонки обязательности — сетка без валидаторов,
    отказа колонки «Сообщение об ошибке» нет (прежде: роль по подстроке, колонка 0 %)."""
    p = tmp_path / "group.md"
    p.write_text(_table(["Наименование контроля", ONBV_ERROR_HEAD],
                        [["Проверка ИНН", "Неверный формат ИНН"],
                         ["Проверка КПП", "см. описание поля"]]), encoding="utf-8")
    _md, report, ok = nt.normalize_file(p, None, None)
    assert ok
    assert any("таблица без якорных ролей" in x for x in report)
    assert not any("роль: обязат" in x for x in report)


def test_normalize_file_obligation_column_validated(tmp_path):
    p = tmp_path / "form.md"
    p.write_text(_table(["Наименование", "Обязательность"], [["ИНН", "Да"], ["КПП", "Нет"]]),
                 encoding="utf-8")
    _md, report, ok = nt.normalize_file(p, None, None)
    assert ok
    assert any("роль: обязат" in x for x in report)
