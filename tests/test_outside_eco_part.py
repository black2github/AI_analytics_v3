# tests/test_outside_eco_part.py
"""Часть сервиса вне контура Экосистемы (решение владельца канона 2026-11-08): штатная часть
`docs/srs/<слаг>/`, признак — строка `вне Экосистемы <слаг>` таблицы «Разметка подсервисов»
профиля источников. Инварианты:

1. путь признака не несёт: файлы `docs/modules/…` — обычные документы комплекта, каталог
   `modules/` не штатный ни в корне репозитория, ни в целевой раскладке;
2. признак выключает ровно два сторожа — привилегии FUN-CL/BNK и авторизацию метода (у
   внутреннего контракта части вместо неё обязательны строки «Канал» и «Контур исполнения»);
   парные тесты: с признаком молчит / без признака срабатывает;
3. строка разметки без слага — ⚠, карточки по-прежнему сверяются;
4. паспорт границы `module-passport` — обязательные разделы шаблона; i-строка части и ⚠ без
   `boundary-passport.md`;
5. снятые типы `module-kit` / `module-interface` — ⚠-подсказка у карточки;
6. `extint_registry`: локальный ID потребителя не `CALL-…` — ⚠.
"""
from pathlib import Path

from app.scripts.CI import extint_registry as er
from app.scripts.CI import link_debts as ld
from app.scripts.CI import selfcheck as sc
from app.scripts.CI import source_coverage as cov
from app.scripts.CI.kitcheck.checks.card_clean import check_clean_document
from app.scripts.CI.kitcheck.checks.card_run import check_file
from app.scripts.CI.kitcheck.checks.card_source import check_title
from app.scripts.CI.kitcheck.checks.source_profile import (
    _load_subservice_map, in_outside_eco_part, outside_eco_lines, outside_eco_slugs, passport_slugs)
from app.scripts.CI.kitcheck.md import _kit_md


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def source(title: str, pid: str, body: str = "текст\n") -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n" + body


PROFILE = ("# Профиль\n\n## Разметка подсервисов\n\n| Матчер (тег или ветвь) | Зона |\n|---|---|\n"
           "| [Т_ЛК] | подсервис limits |\n| [Т_Виджет] | {zone} |\n")


def fun(fid: str, title: str, pid: str, access: str = "Общедоступна") -> str:
    return (f"---\nid: {fid}\ntitle: '{title}'\ntype: function\nconfluence_page_ids: [{pid}]\n---\n\n"
            f"# {fid}. Ф\n\n## 1. Назначение\n\nт\n\n## 2. Доступность\n\n{access}\n\n"
            "## 3. Вызов функции\n\nт\n\n## 4. Поведение\n\nт\n")


def kit(tmp_path: Path, zone: str = "вне Экосистемы widgets", part: str = "widgets",
        passport: bool = True):
    """Комплект с подсервисом limits и частью вне Экосистемы: функция FUN-CL-01 части без
    упоминания привилегий в «Доступности», функция FUN-CL-02 подсервиса — так же."""
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(tmp_path / "README.md", PROFILE.format(zone=zone))
    make(srcs / "w" / "w1.md", source("[Т_Виджет] Клиент: Скрипт", "333444"))
    make(srcs / "l" / "l1.md", source("[Т_ЛК] Клиент: Функция", "111222"))
    make(docs / f"srs/{part}/function/client/fun-cl-01.md",
         fun("FUN-CL-01", "[Т_Виджет] Клиент: Скрипт", "333444"))
    make(docs / "srs/limits/function/client/fun-cl-02.md",
         fun("FUN-CL-02", "[Т_ЛК] Клиент: Функция", "111222"))
    if passport:
        make(docs / f"srs/{part}/boundary-passport.md",
             "---\nid: BND-000\ntitle: 'Паспорт'\ntype: module-passport\n---\n\n# BND-000. П\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         f"| FUN-CL-01 | function | С | srs/{part}/function/client/fun-cl-01.md |\n"
         "| FUN-CL-02 | function | Ф | srs/limits/function/client/fun-cl-02.md |\n"
         f"| BND-000 | module-passport | П | srs/{part}/boundary-passport.md |\n")
    return docs, srcs


PRIV = "FUN-CL/BNK без упоминания привилегий"


def card_block(report, name):
    """Строки отчёта selfcheck карточки (строка файла и отступные строки под ней)."""
    out, on = [], False
    for ln in report:
        if not ln.startswith("   "):
            on = name in ln and ln[:1] in "✓✗⚠"
        if on:
            out.append(ln)
    return out


# ---------------------------------------------------------------- разметка: слаг и признак

def test_zone_row_slug_parsed_and_bare_row_kept(tmp_path):
    prof = make(tmp_path / "README.md", PROFILE.format(zone="вне Экосистемы widgets-rtl")
                + "| [Т_Старое] | вне Экосистемы |\n")
    rows = _load_subservice_map(prof)
    assert ("[Т_Виджет]", "widgets-rtl", "external", None) in rows
    assert ("[Т_Старое]", None, "external", None) in rows


def test_outside_eco_slugs_only_from_profile(tmp_path):
    docs, srcs = kit(tmp_path)
    assert outside_eco_slugs(srcs) == frozenset({"widgets"})
    assert outside_eco_slugs(None) == frozenset()
    p = docs / "srs/widgets/function/client/fun-cl-01.md"
    assert in_outside_eco_part(p, docs, frozenset({"widgets"}))
    assert not in_outside_eco_part(docs / "srs/limits/function/client/fun-cl-02.md", docs,
                                   frozenset({"widgets"}))
    # путь без признака в профиле — обычная часть
    assert not in_outside_eco_part(p, docs, frozenset())


def test_modules_path_does_not_carry_sign(tmp_path):
    # инвариант 1: файл docs/modules/… — обычный документ комплекта, обходы его видят
    docs = tmp_path / "docs"
    f = make(docs / "modules/widgets/interface/x.md", "---\nid: X-01\ntype: function\n---\n# X\n")
    assert f in _kit_md(docs)
    assert not in_outside_eco_part(f, docs, frozenset({"widgets"}))


# ---------------------------------------------------------------- сторож привилегий (пара)

def test_privileges_guard_silent_in_part_with_sign(tmp_path):
    docs, srcs = kit(tmp_path)
    report, _ok = sc.run(docs, srcs)
    assert not [ln for ln in card_block(report, "fun-cl-01.md") if PRIV in ln], report
    # та же форма карточки в части без признака — предупреждение есть
    assert [ln for ln in card_block(report, "fun-cl-02.md") if PRIV in ln], report


def test_privileges_guard_fires_without_sign_row(tmp_path):
    # строка разметки — «подсервис widgets», паспорта нет: признака нет, сторож работает
    docs, srcs = kit(tmp_path, zone="подсервис widgets", passport=False)
    report, _ok = sc.run(docs, srcs)
    assert [ln for ln in card_block(report, "fun-cl-01.md") if PRIV in ln], report


def test_privileges_guard_check_file_flag(tmp_path):
    f = make(tmp_path / "fun-cl-01.md", fun("FUN-CL-01", "[Т] Клиент: С", "1"))
    rep, _ = check_file(f)
    assert any(PRIV in ln for ln in rep), rep
    rep, _ = check_file(f, outside_eco=True)
    assert not any(PRIV in ln for ln in rep), rep


# ---------------------------------------------------------------- метод части: «Канал», «Контур исполнения»

INTC = ("---\nid: INTC-014\ntitle: 'Скрипт'\ntype: internal-contract\n---\n\n# INTC-014. Скрипт\n\n"
        "## 1. Краткое описание\n\n| Поле | Значение |\n|---|---|\n| Назначение | т |\n{rows}")
INTC_ROWS = ("| Авторизация | — (вне контура Экосистемы) |\n| Канал | js-api |\n"
             "| Контур исполнения | устройство пользователя |\n")
NO_CHANNEL = "без строк паспорта"


def test_intc_in_part_without_channel_rows_warned(tmp_path):
    f = make(tmp_path / "intc-014.md", INTC.format(rows="| Авторизация | — (вне контура Экосистемы) |\n"))
    rep, ok = check_file(f, outside_eco=True)
    hit = [ln for ln in rep if NO_CHANNEL in ln]
    assert ok and hit and "«Канал», «Контур исполнения»" in hit[0], rep


def test_intc_in_part_with_rows_silent_and_bold_form_accepted(tmp_path):
    f = make(tmp_path / "intc-014.md", INTC.format(rows=INTC_ROWS))
    rep, _ = check_file(f, outside_eco=True)
    assert not any(NO_CHANNEL in ln for ln in rep), rep
    g = make(tmp_path / "intc-015.md", INTC.format(
        rows="\n**Канал:** js-api\n\n**Контур исполнения:** устройство пользователя\n"))
    rep, _ = check_file(g, outside_eco=True)
    assert not any(NO_CHANNEL in ln for ln in rep), rep


def test_intc_outside_part_not_checked(tmp_path):
    # без признака части сторож молчит: у REST-метода свой паспорт с «Авторизацией»
    f = make(tmp_path / "intc-014.md", INTC.format(rows=""))
    rep, _ = check_file(f)
    assert not any(NO_CHANNEL in ln for ln in rep), rep


# ---------------------------------------------------------------- строки части в отчёте

def test_part_line_and_passport_present(tmp_path):
    docs, srcs = kit(tmp_path)
    report, _ok = sc.run(docs, srcs)
    assert "i часть вне Экосистемы widgets: карточек 2, паспорт BND есть" in report, report
    assert not any("нет boundary-passport.md" in ln for ln in report)


def test_part_without_passport_warned(tmp_path):
    docs, srcs = kit(tmp_path, passport=False)
    report, _ok = sc.run(docs, srcs)
    assert "i часть вне Экосистемы widgets: карточек 1, паспорт BND нет" in report, report
    assert any(ln.startswith("⚠ у части вне Экосистемы нет boundary-passport.md: srs/widgets/")
               for ln in report), report


def test_no_sign_row_no_part_lines(tmp_path):
    # НЕсрабатывание: та же раскладка без строки «вне Экосистемы» — обычная часть
    docs, srcs = kit(tmp_path, zone="подсервис widgets", passport=False)
    report, _ok = sc.run(docs, srcs)
    assert not any("вне Экосистемы" in ln for ln in report), report


def test_bare_zone_row_warns_cards_still_checked(tmp_path):
    docs, srcs = kit(tmp_path, zone="вне Экосистемы", part="legacy", passport=False)
    report, _ok = sc.run(docs, srcs)
    assert any(ln.startswith("⚠ разметка: зона «вне Экосистемы» без слага каталога части (матчер "
                             "[Т_Виджет])") for ln in report), report
    # карточка в сверке, признак не включён (слага нет) — сторож привилегий работает
    blk = card_block(report, "fun-cl-01.md")
    assert blk and [ln for ln in blk if PRIV in ln], report
    assert not any("✗ разметка" in ln for ln in report), report


def test_part_card_outside_its_dir_flagged(tmp_path):
    docs, srcs = kit(tmp_path, part="other")
    report, ok = sc.run(docs, srcs)
    assert not ok
    assert any("✗ разметка" in ln and "«вне Экосистемы widgets»" in ln for ln in report), report


def test_outside_eco_lines_unit(tmp_path):
    docs = tmp_path / "docs"
    smap = [("[A]", None, "external", None), ("[B]", "b", "external", None), ("[C]", "c", "slug", None)]
    out = outside_eco_lines(docs, smap)
    assert out[0].startswith("⚠ разметка: зона «вне Экосистемы» без слага каталога части (матчер [A])")
    assert out[1] == "i часть вне Экосистемы b: карточек 0, паспорт BND нет"
    assert out[2].startswith("⚠ у части вне Экосистемы нет boundary-passport.md: srs/b/")
    assert len(out) == 3


# ---------------------------------------------------------------- второй источник признака: паспорт границы

def test_passport_slugs_by_type_and_depth(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/widgets/boundary-passport.md", "---\nid: BND-000\ntype: module-passport\n---\n# П\n")
    make(docs / "srs/other/boundary-passport.md", "---\nid: X\ntype: function\n---\n# П\n")
    make(docs / "srs/a/b/boundary-passport.md", "---\nid: BND-000\ntype: module-passport\n---\n# П\n")
    make(docs / "srs/quoted/boundary-passport.md", "---\nid: BND-000\ntype: 'module-passport'\n---\n# П\n")
    assert passport_slugs(docs) == frozenset({"widgets", "quoted"})
    assert passport_slugs(tmp_path / "нет") == frozenset()


def test_no_profile_part_by_passport_guard_silent(tmp_path):
    # репозиторий документации без выгрузки: часть узнаётся по паспорту, сторож привилегий молчит
    docs, _srcs = kit(tmp_path)
    report, _ok = sc.run(docs, None)
    assert not [ln for ln in card_block(report, "fun-cl-01.md") if PRIV in ln], report
    assert [ln for ln in card_block(report, "fun-cl-02.md") if PRIV in ln], report
    assert ("i часть вне Экосистемы widgets: карточек 2, признак — по паспорту границы (профиль "
            "источников не читался)") in report, report


def test_no_profile_no_passport_guard_fires(tmp_path):
    # пара: без паспорта и без профиля признака нет — сторож работает, строки части нет
    docs, _srcs = kit(tmp_path, passport=False)
    report, _ok = sc.run(docs, None)
    assert [ln for ln in card_block(report, "fun-cl-01.md") if PRIV in ln], report
    assert not any("часть вне Экосистемы" in ln for ln in report), report


def test_no_profile_intc_in_passport_part_checked(tmp_path):
    docs, _srcs = kit(tmp_path)
    make(docs / "srs/widgets/internal-contract/client/intc-014.md",
         INTC.format(rows="| Авторизация | — (вне контура Экосистемы) |\n"))
    report, _ok = sc.run(docs, None)
    blk = card_block(report, "intc-014.md")
    assert any(NO_CHANNEL in ln for ln in blk), report


def test_passport_without_profile_row_warned(tmp_path):
    # профиль есть, строка части — «подсервис widgets»; паспорт в комплекте — ⚠ в обе стороны
    docs, srcs = kit(tmp_path, zone="подсервис widgets")
    report, _ok = sc.run(docs, srcs)
    assert "i часть вне Экосистемы widgets: карточек 2, паспорт BND есть" in report, report
    assert any(ln.startswith("⚠ паспорт границы srs/widgets/boundary-passport.md без строки "
                             "разметки «вне Экосистемы widgets»") for ln in report), report
    # признак по паспорту включён и с профилем
    assert not [ln for ln in card_block(report, "fun-cl-01.md") if PRIV in ln], report


def test_passport_without_profile_table_warned(tmp_path):
    # профиль без таблицы разметки: сторож разметки молчит, паспорт без строки — ⚠
    docs, srcs = kit(tmp_path)
    (tmp_path / "README.md").write_text("# Профиль\n", encoding="utf-8")
    report, _ok = sc.run(docs, srcs)
    assert any(ln.startswith("⚠ паспорт границы srs/widgets/boundary-passport.md без строки") for ln in report)
    assert not any("разметка подсервисов: соответствие" in ln for ln in report), report


def test_passport_with_profile_row_no_extra_warning(tmp_path):
    # НЕсрабатывание: оба источника согласны — ни ⚠ паспорта, ни строки «по паспорту»
    docs, srcs = kit(tmp_path)
    report, _ok = sc.run(docs, srcs)
    assert not any("без строки разметки" in ln or "по паспорту границы" in ln for ln in report), report


def test_wrong_type_passport_not_sign(tmp_path):
    # файл с другим типом шапки — не признак: сторож привилегий работает
    docs, _srcs = kit(tmp_path, passport=False)
    make(docs / "srs/widgets/boundary-passport.md", "---\nid: X\ntype: function\n---\n# П\n")
    report, _ok = sc.run(docs, None)
    assert [ln for ln in card_block(report, "fun-cl-01.md") if PRIV in ln], report


# ---------------------------------------------------------------- старое место docs/modules/

def test_old_place_files_are_kit_cards(tmp_path):
    # инвариант 1 на selfcheck: файл docs/modules/… входит в перепись и сверяется (без
    # исключения пути), снятый тип даёт подсказку
    docs = tmp_path / "docs"
    make(docs / "a.md", "---\nid: X-01\ntitle: 'А'\ntype: function\n---\n\n# А\n\nтекст\n")
    make(docs / "modules/widgets/interface/mod-001.md",
         "---\nid: MOD-WIDGETS-001\ntitle: 'Скрипт'\ntype: module-interface\n---\n\n# С\n\nтекст\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n| X-01 | function | А | a.md |\n")
    report, _ok = sc.run(docs, None)
    blk = card_block(report, "mod-001.md")
    assert blk, report
    assert any("тип module-interface снят" in ln for ln in blk), blk
    # ID вне реестра матрицы — как у любой карточки (фантомный id)
    assert any("mod-001.md: id MOD-WIDGETS-001 ✗" in ln for ln in report), report


def test_root_modules_dir_is_junk(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "a.md", "---\nid: X-01\ntitle: 'А'\ntype: function\n---\n\n# А\n\nтекст\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n| X-01 | function | А | a.md |\n")
    make(tmp_path / "modules/widgets-rtl/README.md", "# MOD-WIDGETS-RTL-000\n")
    report, ok = sc.run(docs, None)
    junk = [ln for ln in report if "посторонние файлы" in ln]
    assert not ok and junk and "modules" in junk[0], report


def test_clean_link_into_modules_beside_docs_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(tmp_path / "modules/widgets-rtl/interface/mod-001.md", "# M\n")
    f = make(docs / "srs/contract-call/call-int-001.md",
             "---\nid: CALL-INT-001\n---\n\n[MOD](../../../modules/widgets-rtl/interface/mod-001.md)\n")
    rep, ok = check_clean_document(f, docs)
    assert not ok and any("ВНЕ docs" in r for r in rep), rep


def test_check_title_two_pages_aggregator_for_any_card():
    # правило агрегатора действует для любой карточки, исключения по месту нет
    card = ("---\nid: INTC-014\ntitle: 'Клиент: Скрипт'\ntype: internal-contract\n"
            "confluence_page_ids: [2000000222, 2000000901]\n---\n\n# INTC-014. Скрипт\n\nтекст\n")
    src = source("[Т_Виджет] Клиент: Скрипт", "2000000222")
    rep, ok = check_title(card, src)
    assert not ok and rep[0].startswith("title: карточка-агрегатор 2 страниц"), rep


# ---------------------------------------------------------------- source_coverage, link_debts

INV_HEAD = ("| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
            "|---|---|---|---|---|---|---|\n")


def _cov_kit(tmp_path):
    root = tmp_path / "kit"
    src, docs = root / "sources/confluence", root / "docs"
    for pid, title in (("1", "[Т_Виджет] ЭФ Клиента"), ("2", "Функция А")):
        make(src / f"p{pid}.md", source(title, pid))
    make(docs / "srs/bc-a/function/fun-1.md",
         "---\nid: FUN-1\ntitle: 'Ф'\ntype: function\nconfluence_page_ids: ['2']\n---\n# Ф\n")
    make(root / "inventory.md", "# Опись\n\n" + INV_HEAD
         + "| 1 | [Т_Виджет] ЭФ Клиента | В | screenItemForm | 10 | вне Экосистемы (srs/widgets/) | р |\n"
         + "| 2 | Функция А | Р | function | 10 | srs/bc-a/function | сигналы согласны |\n")
    make(root / "migration-plan.md", "| [X_A] | подсервис bc-a | `srs/bc-a/` |\n| [Т_Виджет] | вне "
                                     "Экосистемы widgets | `srs/widgets/` |\n")
    return src, docs


def test_coverage_part_page_covered_by_card_in_part(tmp_path):
    src, docs = _cov_kit(tmp_path)
    make(docs / "srs/widgets/screen-form/scr-1.md",
         "---\nid: SCR-1\ntitle: 'ЭФ'\ntype: screen-form\nconfluence_page_ids: ['1']\n---\n# Э\n")
    lines, blocking = cov.coverage_report(src, docs)
    assert "НЕ покрыто: 0" in lines[0] and "вне Экосистемы" not in lines[0], lines[0]
    assert blocking == 0


def test_coverage_modules_beside_docs_not_read(tmp_path):
    # каталог modules/ рядом с docs/ — не корень покрытия: страница остаётся непокрытой
    src, docs = _cov_kit(tmp_path)
    make(docs.parent / "modules/widgets/scr-1.md",
         "---\nid: MOD-1\ntitle: 'ЭФ'\nconfluence_page_ids: ['1']\n---\n# Э\n")
    lines, _b = cov.coverage_report(src, docs)
    assert "НЕ покрыто: 1" in lines[0], lines[0]
    assert not any("мини-комплект" in ln for ln in lines), lines


def test_link_debts_no_zone_warning_on_part_target(tmp_path):
    root = tmp_path / "kit"
    docs = root / "docs"
    make(docs / "srs/function/fun-001.md", "---\nid: FUN-001\ntitle: 'Ф'\n---\n# Ф\n\nвызов\n")
    make(docs / "traceability-matrix.md",
         "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
         "| FUN-001 | function | Ф | srs/function/fun-001.md |\n\n"
         "## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n"
         "| FUN-001 | — | нет целевого артефакта screen-form «[Т_Виджет] ЭФ Клиента» — требуется заход "
         "create-screen-form |\n")
    make(root / "inventory.md", "# Опись\n\n" + INV_HEAD
         + "| 1 | [Т_Виджет] ЭФ Клиента | В | screenItemForm | 10 | вне Экосистемы (srs/widgets/) | р |\n")
    report, _ok = ld.check(docs / "traceability-matrix.md", docs)
    assert not any("вне Экосистемы" in r or "мини-комплект" in r for r in report), report


def test_title_match_rule_kept_for_gate():
    # правило сопоставления имени цели с титулом описи — общее (гейт, признак А)
    assert ld._title_match("[Т] ПИН-код установлен", ["[Т] ЭФ Клиента: ПИН-код установлен"])
    assert ld._title_match("Х", ["Y"]) is None


# ---------------------------------------------------------------- module-passport

def _w_sections(names):
    return "".join(f"## {i}. {n}\n\nт\n\n" for i, n in enumerate(names, 1))


PASSPORT_REQ = ["Назначение", "Контур исполнения и участники",
                "Граница: что не проходит через Экосистему", "Точки пересечения границы",
                "Границы ответственности", "Что не применяется из правил комплекта"]


def test_module_passport_required_sections(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/widgets/boundary-passport.md",
         "---\nid: BND-000\ntype: module-passport\n---\n\n# BND-000. П\n\n" + _w_sections(PASSPORT_REQ[:-1]))
    rep = sc.check_required_sections(docs)
    assert rep and "единиц 1" in rep[0], rep
    assert "srs/widgets/boundary-passport.md [module-passport]: «Что не применяется из правил комплекта»" \
        in rep[1], rep


def test_module_passport_full_and_conditional_section_silent(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/widgets/boundary-passport.md",
         "---\nid: BND-000\ntype: module-passport\n---\n\n# BND-000. П\n\n"
         + _w_sections(PASSPORT_REQ + ["Эндпоинты чужого контура"]))
    assert sc.check_required_sections(docs) == []


def test_removed_types_not_in_required_sections(tmp_path):
    # module-kit / module-interface сняты: сторож разделов их не знает (подсказку даёт card_form)
    docs = tmp_path / "docs"
    make(docs / "srs/x/kit.md", "---\nid: MOD-X\ntype: module-kit\n---\n\n## Назначение\n\nт\n")
    assert sc.check_required_sections(docs) == []


def test_removed_type_hint_and_silence_for_other_types(tmp_path):
    f = make(tmp_path / "a.md", "---\nid: MOD-1\ntype: module-kit\n---\n\n# А\n\nтекст\n")
    rep, _ = check_file(f)
    assert any("тип module-kit снят" in ln and "module-passport.md" in ln for ln in rep), rep
    g = make(tmp_path / "b.md", "---\nid: BND-000\ntype: module-passport\n---\n\n# Б\n\nтекст\n")
    rep, _ = check_file(g)
    assert not any("снят" in ln for ln in rep), rep


# ---------------------------------------------------------------- extint_registry: «Потребители»

def _consumers(tmp_path, rows: str):
    repo = tmp_path / "ext"
    body = ("## Потребители\n\n| Сервис (`code` каталога) | Локальный ID | Карточка вызова |\n|---|---|---|\n"
            + rows)
    f = make(repo / "systems/as/extint-as-001.md",
             "---\nid: EXTINT-AS-001\ntitle: 'К'\n---\n\n# EXTINT-AS-001. К\n\n" + body)
    card = er.Card(f, repo, f.parent)
    rep = er.Report()
    er.check_consumers([card], rep)
    return rep


def _report_text(rep) -> str:
    return "\n".join(rep.lines)


def test_consumer_local_id_not_call_warned(tmp_path):
    url = "https://gitlab.example/x/-/blob/HEAD/srs/a.md"
    rep = _consumers(tmp_path, f"| business-cards | MOD-WIDGETS-RTL-001 | [к]({url}) |\n")
    text = _report_text(rep)
    assert "локальный ID потребителя — не карточка вызова CALL-…" in text, text
    assert "MOD-WIDGETS-RTL-001" in text, text


def test_consumer_call_id_and_placeholder_silent(tmp_path):
    url = "https://gitlab.example/x/-/blob/HEAD/srs/a.md"
    rep = _consumers(tmp_path, f"| business-cards | CALL-EXT-011 | [к]({url}) |\n"
                               f"| lk | page_id:2166859911 (до регистрации) | — |\n")
    text = _report_text(rep)
    assert "не карточка вызова" not in text, text


def test_consumer_dash_with_id_in_note_silent(tmp_path):
    # НЕсрабатывание: «—» с пояснением (карточки вызова нет) — ID в пояснении не локальный ID
    url = "https://gitlab.example/x/-/blob/HEAD/srs/a.md"
    rep = _consumers(tmp_path, f"| svc | — (карточки вызова нет; вызов из FUN-SVC-01) | [ф]({url}) |\n")
    assert "не карточка вызова" not in _report_text(rep)
