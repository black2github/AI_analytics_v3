# tests/test_raw_oracle.py
"""FB-32 КК (2026-10-24): raw-оракул снятий — del-фрагмент введённой задачи из архива raw не
должен дословно присутствовать в применённой копии той же страницы. Положительные случаи — по
каждой нотации; ограничители 1–7 — тесты на НЕсрабатывание; нормализация."""
from pathlib import Path

from app.scripts.CI import raw_oracle as ro
from app.scripts.CI import selfcheck as sc

T = "TEAMTB-1"
OTHER = "TEAMTB-2"
INTRO = {T}
LONG = "поле организация заполнено переход на следующий шаг"   # 7 слов, > 20 символов


def page(pid: str, body: str) -> str:
    return f"---\ntitle: 'Стр'\nconfluence_page_id: '{pid}'\n---\n\n{body}\n"


def findings(raw: str, copy: str, introduced=INTRO, nested=False):
    return ro.check_page(raw, copy, introduced, include_nested=nested)


# ---------------------------------------------------------------- положительные по нотациям

def test_wiki_del_left_in_copy_flags():
    raw = page("1", f"Начало. {{--{T}: Поле организация заполнено, переход на следующий шаг.--}} Конец.")
    rep = findings(raw, page("1", "Начало. Поле организация заполнено, переход на следующий шаг. Конец."))
    assert len(rep.findings) == 1 and rep.findings[0].kind == "wiki"
    assert rep.findings[0].line == 6
    # применённая копия без фрагмента — тишина
    assert not findings(raw, page("1", "Начало. Конец.")).findings


def test_sub_old_part_left_in_copy_flags():
    raw = page("1", f"{{~~{T}: Поле организация заполнено, переход на следующий шаг~>Новый текст требования здесь~~}}")
    rep = findings(raw, page("1", "Поле организация заполнено, переход на следующий шаг"))
    assert [f.kind for f in rep.findings] == ["sub"]
    assert not findings(raw, page("1", "Новый текст требования здесь")).findings


def test_html_span_del_left_in_copy_flags():
    raw = page("1", f'<table><tr><td><span class="critic-del" data-task="{T}"><strong>Е</strong>'
                    f'<strong>сли</strong> поле «Организация» заполнено, переход на шаг 32.1</span></td></tr></table>')
    copy = page("1", "<table><tr><td><strong>Если</strong> поле «Организация» заполнено, переход на шаг 32.1</td></tr></table>")
    rep = findings(raw, copy)
    assert [f.kind for f in rep.findings] == ["html-span"]
    assert not findings(raw, page("1", "<table><tr><td></td></tr></table>")).findings


def test_html_row_del_left_in_copy_flags():
    raw = page("1", f'<table><tr class="critic-row-del" data-task="{T}"><td>Номер договора клиента</td>'
                    f'<td>Строка обязательна для заполнения</td></tr><tr><td>Б</td><td>В</td></tr></table>')
    copy = page("1", "<table><tr><td>Номер договора клиента</td><td>Строка обязательна для заполнения</td></tr>"
                     "<tr><td>Б</td><td>В</td></tr></table>")
    assert [f.kind for f in findings(raw, copy).findings] == ["html-row"]


def test_md_status_row_del_left_in_copy_flags():
    raw = page("1", "| Поле | Описание | status |\n| --- | --- | --- |\n"
                    f"| Номер договора | Строка обязательна для заполнения клиентом | -{T} |\n| А | Б | |\n")
    copy = page("1", "| Поле | Описание |\n| --- | --- |\n| Номер договора | Строка обязательна для заполнения клиентом |\n| А | Б |\n")
    assert [f.kind for f in findings(raw, copy).findings] == ["md-row"]
    assert not findings(raw, page("1", "| Поле | Описание |\n| --- | --- |\n| А | Б |\n")).findings


def test_placeholder_in_angle_brackets_matches_escaped_copy():
    # парный к исправлению нормализации: плейсхолдер «<Признак …>» в raw как есть, в копии &lt;…&gt;
    raw = page("1", f'<table><tr><td><span class="critic-del" data-task="{T}">Отображается, если Заявка.'
                    f'<Признак открытия нового счета> = TRUE</span></td></tr></table>')
    copy = page("1", "<table><tr><td>Отображается, если Заявка.&lt;Признак открытия нового счета&gt; = TRUE</td></tr></table>")
    assert len(findings(raw, copy).findings) == 1


# ---------------------------------------------------------------- ограничители (НЕсрабатывание)

def test_1_task_not_introduced_silent():
    raw = page("1", f"{{--{OTHER}: Поле организация заполнено, переход на следующий шаг--}}")
    assert not findings(raw, page("1", "Поле организация заполнено, переход на следующий шаг")).findings


def test_2_text_reinserted_by_introduced_task_silent():
    raw = page("1", f"{{--{T}: Поле организация заполнено, переход на следующий шаг--}}\n\n"
                    f"{{++{T}: Поле организация заполнено, переход на следующий шаг ++}}")
    rep = findings(raw, page("1", "Поле организация заполнено, переход на следующий шаг"))
    assert not rep.findings and rep.reinserted == 1


def test_2_reinsert_by_not_introduced_task_does_not_excuse():
    # вставка невведённой задачи в применённой копии снята (reject-all) — не оправдание
    raw = page("1", f"{{--{T}: Поле организация заполнено, переход на следующий шаг--}}\n\n"
                    f"{{++{OTHER}: Поле организация заполнено, переход на следующий шаг ++}}")
    assert len(findings(raw, page("1", "Поле организация заполнено, переход на следующий шаг")).findings) == 1


def test_3_marker_inside_code_block_silent():
    raw = page("1", f"```\n{{--{T}: Поле организация заполнено, переход на следующий шаг--}}\n```")
    copy = page("1", f"```\n{{--{T}: Поле организация заполнено, переход на следующий шаг--}}\n```")
    rep = findings(raw, copy)
    assert not rep.findings and rep.checked == 0


def test_4_nested_table_cell_skipped_by_default():
    raw = page("1", f'<table><tr><td><table><tr><td><span class="critic-del" data-task="{T}">'
                    f'Поле организация заполнено переход на следующий шаг</span></td></tr></table></td></tr></table>')
    copy = page("1", "<table><tr><td><table><tr><td>Поле организация заполнено переход на следующий шаг"
                     "</td></tr></table></td></tr></table>")
    rep = findings(raw, copy)
    assert not rep.findings and rep.nested == 1
    assert len(findings(raw, copy, nested=True).findings) == 1   # ключ включает


def test_4_island_own_table_is_not_nested():
    raw = page("1", f'<table><tr><td><span class="critic-del" data-task="{T}">'
                    f'Поле организация заполнено переход на следующий шаг</span></td></tr></table>')
    rep = findings(raw, page("1", "<table><tr><td>Поле организация заполнено переход на следующий шаг</td></tr></table>"))
    assert rep.nested == 0 and len(rep.findings) == 1


def test_5_short_fragment_skipped():
    raw = page("1", f"Шаг {{--{T}: 2--}}. {{--{T}: Строка (100) да--}}")
    rep = findings(raw, page("1", "Шаг 2. Строка (100) да"))
    assert not rep.findings and rep.short == 2


def test_6_page_without_copy_counted(tmp_path):
    raw_root, conf = tmp_path / "raw", tmp_path / "confluence"
    (raw_root).mkdir()
    conf.mkdir()
    (raw_root / "a.md").write_text(page("1", f"{{--{T}: {LONG}--}}"), encoding="utf-8")
    lines, st = ro.check_tree(raw_root, conf, INTRO)
    assert lines == [] and st["no_copy"] == 1 and st["pages"] == 1


def test_7_repeats_one_finding_with_count():
    raw = page("1", f"{{--{T}: {LONG}--}}")
    rep = findings(raw, page("1", f"{LONG}\n\n{LONG}\n\n{LONG}"))
    assert len(rep.findings) == 1 and rep.findings[0].count == 3


def test_text_kept_elsewhere_on_page_silent():
    # удалено одно вхождение, второе законно остаётся на странице — в копии одно: тишина
    raw = page("1", f"{LONG}\n\n{{--{T}: {LONG}--}}")
    rep = findings(raw, page("1", LONG))
    assert not rep.findings and rep.kept_elsewhere == 1
    # а если в копии оба — второе недоснято
    assert len(findings(raw, page("1", f"{LONG}\n\n{LONG}")).findings) == 1


# ---------------------------------------------------------------- нормализация

def test_normalize():
    assert ro.normalize("<strong>Е</strong><strong>сли</strong> X") == "если x"
    assert ro.normalize("A&lt;B&gt;&amp;C") == "a<b>&c"
    assert ro.normalize("<td>Яч1</td><td>Яч2</td>") == "яч1 яч2"
    assert ro.normalize("| Яч1 | Яч2 |") == "яч1 яч2"
    assert ro.normalize("см. [\\[КК\\] Процедура](x.md).") == "см. [кк] процедура"
    assert ro.normalize(f"{{--{T}: Текст  с   пробелами--}}") == "текст с пробелами"
    assert ro.normalize("<Признак счета> и <cvv2>") == "<признак счета> и <cvv2>"


# ---------------------------------------------------------------- selfcheck

def _kit(tmp_path, copy_body: str):
    root = tmp_path / "src"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "traceability-matrix.md").write_text("# М\n", encoding="utf-8")
    raw, conf = root / "sources/raw", root / "sources/confluence"
    raw.mkdir(parents=True)
    conf.mkdir(parents=True)
    (raw / "p.md").write_text(page("1001", f"{{--{T}: {LONG}--}}"), encoding="utf-8")
    (conf / "p.md").write_text(page("1001", copy_body), encoding="utf-8")
    intro = root / "introduced.txt"
    intro.write_text(f"# введённые\n{T}\n", encoding="utf-8")
    return docs, root / "sources", raw, intro


def test_selfcheck_raw_flag_finding_and_counters(tmp_path):
    docs, sources, raw, intro = _kit(tmp_path, LONG)
    report, ok = sc.run(docs, sources, raw=raw, introduced=intro)
    hits = [ln for ln in report if ln.startswith("⚠ сверка по архиву raw:")]
    assert len(hits) == 1 and f"удалённое введённой задачей {T} осталось в применённой копии страницы 1001" in hits[0] and "p.md:6" in hits[0]
    assert any(ln.startswith("i сверка по архиву raw: введённые задачи TEAMTB-1; страниц с маркерами удаления 1") for ln in report)
    assert any(ln.startswith("i сверка по архиву raw: пропущено удалённых фрагментов в ячейках вложенных таблиц: 0")
               for ln in report)


def test_selfcheck_without_raw_flag_silent(tmp_path):
    docs, sources, raw, intro = _kit(tmp_path, LONG)
    report, _ok = sc.run(docs, sources)
    assert not any("сверка по архиву raw" in ln for ln in report)


def test_selfcheck_raw_no_introduced_info_line(tmp_path):
    docs, sources, raw, intro = _kit(tmp_path, LONG)
    intro.write_text("", encoding="utf-8")
    report, _ok = sc.run(docs, sources, raw=raw, introduced=intro)
    assert "i сверка по архиву raw: введённых задач не найдено (теги src/*), проверка пропущена" in report
    report, _ok = sc.run(docs, sources, raw=raw)   # нет git и нет файла — то же
    assert "i сверка по архиву raw: введённых задач не найдено (теги src/*), проверка пропущена" in report


def test_selfcheck_raw_does_not_change_verdict(tmp_path):
    docs, sources, raw, intro = _kit(tmp_path, LONG)
    _r1, ok1 = sc.run(docs, sources)
    _r2, ok2 = sc.run(docs, sources, raw=raw, introduced=intro)
    assert ok1 == ok2


def test_selfcheck_raw_bundle_not_found_warns(tmp_path):
    # путь бандла задан, а raw_oracle.py там нет — ⚠, не молчание и не падение
    docs, sources, raw, intro = _kit(tmp_path, LONG)
    report, _ok = sc.run(docs, sources, raw=raw, introduced=intro, bundle=tmp_path / "no-bundle")
    hits = [ln for ln in report if ln.startswith("⚠ сверка по архиву raw не выполнена: бандл не найден")]
    assert len(hits) == 1 and not any(ln.startswith("⚠ сверка по архиву raw: удалённое") for ln in report)


def test_selfcheck_raw_from_bundle_dir(tmp_path):
    # бандл экспортёра: raw_oracle.py рядом с critic.py (раскладка app/scripts/CI) — модуль оттуда
    import shutil
    ci = Path(ro.__file__).resolve().parent
    b = tmp_path / "bundle" / "app" / "scripts" / "CI"
    (b / "kitcheck").mkdir(parents=True)
    for f in ("raw_oracle.py", "critic.py", "kitcheck/__init__.py", "kitcheck/fence.py"):
        shutil.copy2(ci / f, b / f)
    docs, sources, raw, intro = _kit(tmp_path, LONG)
    report, _ok = sc.run(docs, sources, raw=raw, introduced=intro, bundle=tmp_path / "bundle")
    assert sum(1 for ln in report if ln.startswith("⚠ сверка по архиву raw: удалённое")) == 1, report



# ================================================================ режим карточек (срез 2)

def _cards_kit(tmp_path, card_body: str, pids: str = "'1001'"):
    raw = tmp_path / "sources/raw"
    docs = tmp_path / "docs"
    raw.mkdir(parents=True)
    (raw / "p.md").write_text(page("1001", f"{{--{T}: {LONG}--}}\n\nОстальной текст страницы"),
                              encoding="utf-8")
    (docs / "srs/function").mkdir(parents=True)
    (docs / "srs/function/fun-01.md").write_text(
        f"---\nid: FUN-01\ntitle: 'Ф'\ntype: function\nconfluence_page_ids: [{pids}]\n---\n\n# Ф\n\n{card_body}\n",
        encoding="utf-8")
    return raw, docs


def test_cards_fragment_in_card_flags(tmp_path):
    raw, docs = _cards_kit(tmp_path, f"## Поведение\n\n{LONG}")
    rows, st = ro.check_cards(raw, docs, INTRO)
    assert len(rows) == 1 and rows[0].card == "srs/function/fun-01.md" and rows[0].page == "1001"
    assert rows[0].task == T and rows[0].line == 12 and st["cards"] == 1


def test_cards_clean_card_silent_and_zero_line(tmp_path):
    raw, docs = _cards_kit(tmp_path, "## Поведение\n\nНовый текст требования без удалённого фрагмента")
    rows, st = ro.check_cards(raw, docs, INTRO)
    assert rows == [] and st["checked"] == 1
    rep = ro.cards_report(rows, st, INTRO, docs, raw)
    assert any(ln.startswith("**Находок нет**") for ln in rep)


def test_cards_card_of_other_page_not_checked(tmp_path):
    raw, docs = _cards_kit(tmp_path, LONG, pids="'2002'")
    rows, st = ro.check_cards(raw, docs, INTRO)
    assert rows == [] and st["pages_no_card"] == 1 and st["cards"] == 0


def test_cards_excluded_sections_silent(tmp_path):
    for heading in ("## Происхождение", "## 10. Долги и открытые вопросы (обязательный, если есть)",
                    "## Что не переносится из источника", "### Долги по ссылкам"):
        raw, docs = _cards_kit(tmp_path / heading[-8:].replace(" ", "_"), f"{heading}\n\n{LONG}")
        rows, st = ro.check_cards(raw, docs, INTRO)
        assert rows == [] and st["excluded"] == 1, heading


def test_cards_excluded_section_ends_at_next_heading(tmp_path):
    raw, docs = _cards_kit(tmp_path, f"## Происхождение\n\nстраница 1001\n\n## Поведение\n\n{LONG}")
    rows, _st = ro.check_cards(raw, docs, INTRO)
    assert len(rows) == 1


def test_cards_debt_and_oq_lines_silent(tmp_path):
    for line in (f"- {LONG} — см. OQ-12", f"Долг: {LONG}"):
        raw, docs = _cards_kit(tmp_path / str(abs(hash(line))), line)
        rows, st = ro.check_cards(raw, docs, INTRO)
        assert rows == [] and st["excluded"] == 1, line


def test_cards_not_introduced_task_silent(tmp_path):
    raw, docs = _cards_kit(tmp_path, LONG)
    rows, _st = ro.check_cards(raw, docs, {OTHER})
    assert rows == []


def test_cards_cli_report_with_introduced_file(tmp_path):
    raw, docs = _cards_kit(tmp_path, LONG)
    intro = tmp_path / "intro.txt"
    intro.write_text(f"{T}\n", encoding="utf-8")
    out = tmp_path / "report.md"
    assert ro.main(["--cards", str(docs), "--raw", str(raw), "--introduced", str(intro),
                    "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "| srs/function/fun-01.md | Ф | 1001 | TEAMTB-1 |" in text and "Время прогона:" in text
    assert "| TEAMTB-1 | 1 |" in text   # сводка по задачам



def test_cards_markdown_card_matches_html_raw():
    # карточка в markdown («**», «ёлочки»), архив в HTML и прямых кавычках — одна нормализация
    raw = page("1", f'<table><tr><td><span class="critic-del" data-task="{T}"><strong>Видимость:</strong> '
                    f'плашка "Не все продукты совместимы с картой"</span></td></tr></table>')
    card = "- **Видимость:** плашка «Не все продукты совместимы с картой»"
    assert len(ro.check_page(raw, card, INTRO).findings) == 1


def test_cards_nested_cells_checked_by_default(tmp_path):
    raw = tmp_path / "sources/raw"
    docs = tmp_path / "docs"
    raw.mkdir(parents=True)
    (raw / "p.md").write_text(page("1001", f'<table><tr><td><table><tr><td><span class="critic-del" '
                                           f'data-task="{T}">{LONG}</span></td></tr></table></td></tr></table>'),
                              encoding="utf-8")
    (docs / "srs").mkdir(parents=True)
    (docs / "srs/scr-1.md").write_text(f"---\nid: SCR-1\nconfluence_page_ids: ['1001']\n---\n\n{LONG}\n",
                                       encoding="utf-8")
    rows, st = ro.check_cards(raw, docs, INTRO)
    assert len(rows) == 1 and st["nested"] == 0
    rows, st = ro.check_cards(raw, docs, INTRO, include_nested=False)   # ключ --skip-nested-cells
    assert rows == [] and st["nested"] == 1


def test_cards_short_fragment_marked_check(tmp_path):
    raw = tmp_path / "sources/raw"
    docs = tmp_path / "docs"
    raw.mkdir(parents=True)
    short = "по умолчанию не отображается"            # 4 слова, 28 символов — порог проходит
    (raw / "p.md").write_text(page("1001", f"{{--{T}: {short}--}}\n\n{{--{T}: {LONG}--}}"), encoding="utf-8")
    (docs / "srs").mkdir(parents=True)
    (docs / "srs/scr-1.md").write_text(f"---\nid: SCR-1\nconfluence_page_ids: ['1001']\n---\n\n{short}\n\n{LONG}\n",
                                       encoding="utf-8")
    rows, _st = ro.check_cards(raw, docs, INTRO)
    marks = {r.fragment: r.check for r in rows}
    assert marks == {short: True, LONG: False}
