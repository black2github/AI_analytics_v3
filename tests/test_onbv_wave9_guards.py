# tests/test_onbv_wave9_guards.py
"""Волна 9 ОНБ-В (ответы команды, 2026-10-19): сторожа прибора — только ⚠ / i, вердикт не
меняют; на каждый — срабатывание и НЕсрабатывание на законном случае."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.matrix import check_registry_name_duplicates


def w(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------- T4: названия по «Реестру ID»

def matrix(tmp_path: Path, rows: str) -> Path:
    return w(tmp_path / "traceability-matrix.md",
             "# Матрица\n\n## Реестр ID\n\n| ID | Название | Файл |\n| --- | --- | --- |\n" + rows
             + "\n## Покрытие: функции → артефакты\n")


def test_t4_same_name_different_ids_of_one_type_warned(tmp_path):
    m = matrix(tmp_path, "| CTL-015 | Проверка ИНН | srs/control/cards-org.md |\n"
                         "| CTL-034 | проверка  инн | srs/control/cards-applicant.md |\n")
    assert check_registry_name_duplicates(m, []) == ["CTL-015, CTL-034 — «Проверка ИНН»"]


def test_t4_lawful_cases_silent(tmp_path):
    m = matrix(tmp_path,
               "| SCR-CL-01.1 | Форма заявки | a.md |\n| SCR-CL-01.2 | Форма заявки | b.md |\n"  # части группы
               "| CTL-000 | Контроли | README.md |\n| ENT-000 | Контроли | README.md |\n"     # реестры
               "| SCR-CL-05 | снят 2026-08-30: дубль, преемник SCR-CL-01 | — |\n"
               "| SCR-CL-06 | снят 2026-08-30: дубль, преемник SCR-CL-01 | — |\n"               # снятые
               "| FUN-CL-01 | Сохранение | f.md |\n| PRN-01 | Сохранение | p.md |\n")          # разные типы
    assert check_registry_name_duplicates(m, []) == []


def test_t4_pair_already_named_by_title_not_repeated(tmp_path):
    m = matrix(tmp_path, "| CTL-015 | Проверка ИНН | a.md |\n| CTL-034 | Проверка ИНН | b.md |\n")
    assert check_registry_name_duplicates(m, [{"CTL-015", "CTL-034"}]) == []


# ---------------------------------------------------------------- T5: долг с признаком чужой цели

from app.scripts.CI import link_debts as ld  # noqa: E402

CATALOG = [
    {"code": "onboarding", "key": "ON", "name": "[ОНБ] Онбординг юридических лиц"},
    {"code": "branchDirectory", "key": "BD", "name": "[СФП] Справочник филиалов и подразделений"},
    {"code": "errorDictionary", "key": "ED", "name": "[СпрОшибок] Справочник текстов ошибок"},
    {"code": "my-service", "key": "MS", "name": "[МС] Мой сервис заявок"},
    {"code": "payments", "key": "PA", "name": "[ПП] Платёжные поручения клиента Банка"},
    {"code": "cards", "key": "CC", "name": "[КК] Корпоративные карты клиента Банка"},
    # общее слово встречается в названиях трёх и более сервисов — не признак (как в каталоге канона)
    {"code": "deposits", "key": "DP", "name": "[ДЕП] Депозиты клиента"},
]


def debts_kit(tmp_path: Path, rows: str) -> tuple:
    docs = tmp_path / "docs"
    w(docs / "srs/data-model/ent-001.md", "---\nid: ENT-001\ntype: data-model\nservice: my-service\n"
      "title: 'Заявка'\n---\n\n# Заявка\n\nСвязь: ОНБ_2021, Справочник городов, [СпрОшибок] Метод текста "
      "ошибки, АС ППБ_СИП выгрузка, Заявка клиента, Банк-партнёр, Онбординг ЮЛ, Моя заявка.\n")
    m = w(docs / "traceability-matrix.md",
          "# М\n\n## Реестр ID\n\n| ID | Название | Файл |\n|---|---|---|\n"
          "| ENT-001 | Заявка | srs/data-model/ent-001.md |\n\n"
          "## Долги по ссылкам\n\n| Артефакт | Цель | Причина |\n|---|---|---|\n" + rows)
    return m, docs


def foreign_lines(tmp_path, rows, catalog=CATALOG):
    m, docs = debts_kit(tmp_path, rows)
    rep, ok = ld.check(m, docs, {s["code"] for s in catalog}, catalog)
    return [ln for ln in rep if "похоже на чужую цель" in ln], ok


def row(name, skill="create-data-model", typ="data-model"):
    return f"| ENT-001 | — | нет целевого артефакта {typ} «{name}» — требуется заход {skill} |\n"


def test_t5_foreign_signs_warned(tmp_path):
    rows = (row("ОНБ_2021") + row("Справочник городов")
            + row("[СпрОшибок] Метод текста ошибки", "create-internal-contracts", "internal-contract")
            + row("АС ППБ_СИП выгрузка") + row("Онбординг ЮЛ"))
    lines, ok = foreign_lines(tmp_path, rows)
    assert len(lines) == 5, lines
    assert any("ОНБ_2021" in ln and "тег сервиса [ОНБ]" in ln for ln in lines), lines
    assert any("Справочник городов" in ln for ln in lines)
    assert any("СпрОшибок" in ln and "тег сервиса" in ln for ln in lines), lines
    assert any("АС ППБ_СИП" in ln and "внешняя система" in ln for ln in lines), lines
    assert any("Онбординг" in ln and "слово «Онбординг»" in ln for ln in lines), lines
    assert ok  # только ⚠


def test_t5_lawful_debts_silent(tmp_path):
    rows = ("| ENT-001 | — | нет целевого артефакта data-model «ОНБ_2021» у владельца onboarding "
            "— требуется заход create-data-model у владельца |\n"   # формула «у владельца»
            + row("Заявка клиента")                                    # «клиента», «Заявка» — общие слова
            + row("Банк-партнёр")                                      # «банк» — общее
            + row("Моя заявка"))                                       # свой сервис
    lines, _ok = foreign_lines(tmp_path, rows)
    assert lines == [], lines


def test_t5_without_catalog_only_data_model_words(tmp_path):
    m, docs = debts_kit(tmp_path, row("ОНБ_2021") + row("Справочник городов"))
    rep, _ok = ld.check(m, docs)
    lines = [ln for ln in rep if "похоже на чужую цель" in ln]
    assert len(lines) == 1 and "Справочник городов" in lines[0], lines


def test_t5_own_subservice_tag_silent(tmp_path):
    # тег своего сервиса или его подсервиса («[МС]», «[МС_ЛК] …») — своя цель
    lines, _ok = foreign_lines(tmp_path, row("[МС_ЛК] Онбординг пакета") + row("[МС] Онбординг"))
    assert lines == [], lines


# ---------------------------------------------------------------- T1–T3: сверка с источником

from app.scripts.CI.kitcheck.core import is_soft_signal  # noqa: E402
from app.scripts.CI.kitcheck.checks.card_source import (
    check_image_trace,
    check_unchecked_tables,
    source_tables_summary,
)  # noqa: E402

SRC_LAYOUT = ("---\ntitle: X\n---\n\n## Макеты ЭФ\n\n| Размерность экрана | Макет |\n| --- | --- |\n"
              "| xl | [Макет xl](https://www.figma.com/file/a) |\n| m | [Макет m](https://www.figma.com/file/b) |\n"
              "| xs | [Макет xs](https://www.figma.com/file/c) |\n")


def test_t1_links_only_table_not_found_warned():
    rep = check_unchecked_tables("# Форма\n\nПоля формы.\n", SRC_LAYOUT, "")
    assert len(rep) == 1 and rep[0].startswith("предупреждение: таблица источника «Размерность экрана | Макет»"), rep
    assert is_soft_signal(rep[0])


def test_t1_headers_in_group_readme_silent():
    readme = "# Группа\n\n| Размерность экрана | Макет |\n|---|---|\n| xl | макет в src |\n| m | — |\n| xs | — |\n"
    rep = check_unchecked_tables("# Форма\n", SRC_LAYOUT, readme)
    assert not any(r.startswith("предупреждение") for r in rep), rep


def test_t1_partly_found_gives_info_line():
    rep = check_unchecked_tables("# Форма\n\nМакеты: размерность экрана xl.\n", SRC_LAYOUT, "")
    assert len(rep) == 1 and rep[0].startswith("i таблица без дословных значений"), rep
    assert is_soft_signal(rep[0])


def test_t1_table_with_plain_values_not_concerned():
    src = "| Поле | Тип |\n| --- | --- |\n| Номер | Строка |\n| Дата | Дата |\n"
    assert check_unchecked_tables("# К\n", src, "") == []


IMG_SRC = "# Стр\n\nСхема: <img src=\"a.png\"> и ![x](b.png), смайлик <img class=\"emoticon\" src=\"e.png\">\n"


def test_t2_images_without_trace_warned():
    rep = check_image_trace("# Карточка\n\nТекст.\n", IMG_SRC, "", ["FUN-CL-01"])
    assert rep and rep[0].startswith("предупреждение: изображения источника ×2"), rep


def test_t2_trace_or_no_images_silent():
    assert check_image_trace("# К\n", "# без картинок\n", "", ["FUN-CL-01"]) == []
    assert check_image_trace("# К\n\n## Приложенные артефакты\n\n| Файл |\n", IMG_SRC, "", []) == []
    assert check_image_trace("# К\n\nСм. [схема](files/flow.vsdx).\n", IMG_SRC, "", []) == []
    debts = "| FUN-CL-01 | — | долг правило на изображении: «схема» — ответственный: А |\n"
    assert check_image_trace("# К\n", IMG_SRC, debts, ["FUN-CL-01"]) == []


def test_t3_tables_listed_and_silent_without_tables():
    src = ("| Кнопка | Действие |\n| --- | --- |\n| Обновить | обновляет |\n| Назад | возврат |\n\n"
           "| Поле | Тип |\n| --- | --- |\n| Номер | Строка |\n")
    rep = source_tables_summary(src)
    assert rep == ["i таблицы источника: 2 — «Кнопка | Действие» (2); «Поле | Тип» (1)"], rep
    assert is_soft_signal(rep[0])
    assert source_tables_summary("# Страница без таблиц\n\nТекст.\n") == []


# ---------------------------------------------------------------- T7: сводка написаний

from app.scripts.CI import selfcheck as sc  # noqa: E402


def test_t7_close_pairs_found(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/screen-form/scr-cl-01.md", "# Ф\n\n### B-1. «Подтвердить»\n\nТекст «Валюта счёта», «e-mail».\n")
    w(docs / "srs/screen-form/scr-cl-03.md", "# Ф\n\nКнопка B-2 «подтвердить», «Валюта счета», «e‑mail».\n")
    pairs = sc.spelling_pairs(sc._kit_md(docs), docs)
    got = {frozenset((a, b)) for a, b, _fa, _fb in pairs}
    assert frozenset(("Подтвердить", "подтвердить")) in got, pairs
    assert frozenset(("Валюта счёта", "Валюта счета")) in got, pairs
    assert frozenset(("e-mail", "e‑mail")) in got, pairs


def test_t7_identical_and_morphology_silent(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "a.md", "# А\n\n«Подтвердить», «Счёт».\n")
    w(docs / "b.md", "# Б\n\n«Подтвердить», «Счета».\n")
    assert sc.spelling_pairs(sc._kit_md(docs), docs) == []
