# tests/test_mention_guards_false_positives.py
"""Ложные срабатывания сторожей упоминаний и ссылок (постановка «Точек» 2026-11-17, замер шага 2.12
КК; ответ на замер 18.11). На каждый класс — тест на срабатывание правки (ложной строки нет) и на
несрабатывание (настоящее упоминание судится как прежде).

1. тег-подпись: тег встречается в выгрузке, но не открывает ни титула, ни текста ссылки;
2. собственная страница карточки (confluence_page_ids шапки);
3. граница имени: имя в ссылке, продолжение за ней; пробел перед знаком; хвост ячейки; путь
   атрибута; долг матрицы «[тег] имя» по префиксу ядра — со строкой i;
4. обратный апостроф — только граница имени (текст в апострофах остаётся упоминанием);
5. непарная «[» не гасит разбор подписей ссылок до конца файла;
6. строка долга матрицы — формальная запись пробела, сторож неформальных пометок её не читает;
7. копия общей страницы метода: чужие места зоны «Где используется» в карточке вызова."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks import card_clean as cc
from app.scripts.CI.kitcheck.checks import source_profile as sp


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def card(cid: str, title: str, body: str, typ: str = "function", ids: str = "") -> str:
    head = f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\n"
    if ids:
        head += f"confluence_page_ids: [{ids}]\n"
    return head + f"---\n\n# {cid}. {title}\n\n{body}\n"


MATRIX = "# Матрица трассировки\n\n| FROM | TO |\n|---|---|\n"


def kit(tmp_path: Path, matrix: str = MATRIX) -> Path:
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", matrix)
    # тег [КК_ВК] открывает титул карточки комплекта
    make(docs / "srs" / "other.md", card("FUN-CL-99", "[КК_ВК] Другая функция", "т"))
    cc._TARGET_INDEX_CACHE.clear()
    return docs


def export(link=(), seen=(), titles=(), pages=None):
    return sp.MentionExport(frozenset(titles), frozenset(link), frozenset(seen), pages or {})


def targets(docs: Path, body: str, exp=None, ids: str = "", source_tags=frozenset()):
    md = make(docs / "srs" / "fun-cl-01.md", card("FUN-CL-01", "Функция", body, ids=ids))
    cc._TARGET_INDEX_CACHE.clear()
    labels, waived = [], []
    warns, ok = cc.check_target_mentions(md.read_text(encoding="utf-8"), md, docs,
                                         source_tags, labels, exp, waived)
    assert ok is True
    return [w for w in warns if "упоминание цели" in w], labels, waived


def sources(card_text: str, src: str, docs=None, exp=None):
    waived = []
    rep, ok = cc.check_source_tag_mentions(card_text, src, docs, exp, waived)
    return [r for r in rep if "теговое упоминание источника" in r], ok, waived


# --- класс 5: непарная «[» ---

def test_c5_unpaired_bracket_does_not_hide_later_links():
    text = "атрибуты сущности [, **кроме** …\n\nсм. [FUN-CL-55 [КК_ВК] Маппинга реквизитов](f.md)"
    assert "FUN-CL-55 [КК_ВК] Маппинга реквизитов" in cc._md_link_texts(text)


def test_c5_bracket_text_without_address_is_not_link():
    assert cc._md_link_texts("[DELETE] текст [ещё] без адреса") == ""


def test_c5_source_mention_found_after_unpaired_bracket():
    body = card("FUN-CL-54", "Ф", "атрибуты сущности [, кроме …\n\n"
                "по [FUN-CL-55 [КК_ВК] Маппинга реквизитов для импорта](f.md)")
    src = "<p>см. [КК_ВК] Маппинга реквизитов для импорта реестра</p>"
    warns, ok, _w = sources(body, src)
    assert warns == [] and ok


# --- класс 3: граница имени ---

def test_c3_name_in_link_continuation_after_link_found():
    body = card("FUN-CL-56", "Ф", "Если [ENT-010 [КК_ВК] Выпускаемая карта](e.md) выполняется:")
    warns, ok, _w = sources(body, "<p>Если [КК_ВК] Выпускаемая карта выполняется:</p>")
    assert warns == [] and ok


def test_c3_space_before_punctuation_at_link_boundary():
    body = card("PROC-034", "П", "[ENT-010 [КК_ВК] Выпускаемая карта](e.md): Атрибут заполняется")
    warns, ok, _w = sources(body, "<p>[КК_ВК] Выпускаемая карта : Атрибут заполняется</p>")
    assert warns == [] and ok


def test_c3_cell_markup_between_link_and_text():
    body = card("PROC-034", "П",
                "| 1 | [ENT-010 [КК_ВК] Выпускаемая карта](e.md):<br>&nbsp;&nbsp;• Атрибут <К> |")
    warns, ok, _w = sources(body, "<p>[КК_ВК] Выпускаемая карта : Атрибут <К> заполняется</p>")
    assert warns == [] and ok


def test_c3_other_tag_in_link_still_warned():
    # [АО_З1] в названии ссылки — другая страница, упоминание [АО_З2] не найдено
    body = card("SCR-CL-04", "Э", "после [PROC-1 [АО_З1] ЖЦ заявки](p.md) на шаг 2.5")
    warns, ok, _w = sources(body, "<p>после [АО_З2] ЖЦ заявки на шаг 2.5</p>")
    assert len(warns) == 1 and "[АО_З2] ЖЦ заявки" in warns[0]


def test_c3_absent_mention_still_warned():
    body = card("FUN-CL-56", "Ф", "Если [ENT-010 [КК_ВК] Заявка](e.md) выполняется:")
    warns, _ok, _w = sources(body, "<p>Если [КК_ВК] Выпускаемая карта выполняется:</p>")
    assert len(warns) == 1


def test_c3_core_boundaries_html_tag_attribute_path():
    assert cc._mention_core("Функции Банка.<br> далее") == "Функции Банка"
    assert cc._mention_core("Функции Банка<br>") == "Функции Банка"
    assert cc._mention_core("Метод отправки ОТР-кода.<Исходящие параметры>.<Код>") == \
        "Метод отправки ОТР-кода"


def test_c3_source_needle_without_space_before_sign():
    m = cc.source_tag_mentions("<p>[КК_ВК] Адрес держателя карты > = значение</p>")
    assert "адрес держателя карты" in m


DEBT = ("# Матрица\n\n## Долги по ссылкам\n\n| FROM | — | Долг |\n|---|---|---|\n"
        "| CALL-EXT-026 | — | нет целевого артефакта external «[ДПП] Классификатор продуктов» "
        "— страница 1 вне выгрузки |\n")


def test_c3_debt_by_prefix_counted_with_i_line(tmp_path):
    docs = kit(tmp_path, DEBT)
    warns, _l, waived = targets(docs, "на странице [ДПП] Классификатор продуктов в столбце Код")
    assert warns == []
    assert waived and waived[0][0] == "debt-prefix" and "[ДПП] Классификатор продуктов" in waived[0][1]


def test_c3_registry_row_without_quotes_not_counted(tmp_path):
    docs = kit(tmp_path, MATRIX + "| PROC-1 | [ДПП] Классификатор продуктов |\n")
    warns, _l, waived = targets(docs, "на странице [ДПП] Классификатор продуктов в столбце Код")
    assert len(warns) == 1 and waived == []


def test_c3_one_word_prefix_not_counted(tmp_path):
    docs = kit(tmp_path, DEBT.replace("Классификатор продуктов»", "Классификатор»"))
    warns, _l, waived = targets(docs, "на странице [ДПП] Классификатор продуктов в столбце Код")
    assert len(warns) == 1 and waived == []


# --- класс 4: обратный апостроф — только граница имени ---

def test_c4_backtick_ends_name():
    assert cc._mention_core("Текст Согласия №2` (перенос — заход z04)") == "Текст Согласия №2"


def test_c4_mention_in_backticks_still_judged(tmp_path):
    docs = kit(tmp_path)
    warns, _l, _w = targets(docs, "Поле `[ДПП] Классификатор статусов`.`<Код>` заполняется")
    assert len(warns) == 1 and "[ДПП] Классификатор статусов»" in warns[0]


# --- класс 6: строки долгов матрицы ---

def test_c6_debt_row_not_read_as_gap_mark(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", DEBT)
    rep = sc.check_source_silent(docs)
    assert not any("не по формуле" in r for r in rep), rep


def test_c6_debt_of_other_kind_not_read(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", DEBT.replace(
        "нет целевого артефакта external «[ДПП] Классификатор продуктов» — страница 1 вне выгрузки",
        "долг источник недоступен: «таблица ЦРМ» — причина: таблица вне выгрузки"))
    rep = sc.check_source_silent(docs)
    assert not any("не по формуле" in r for r in rep), rep


def test_c6_unrecognized_row_and_other_section_still_warned(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n## Покрытие\n\n| A | B |\n|---|---|\n| X | страница вне выгрузки |\n\n"
         "## Долги по ссылкам\n\n| FROM | — | Долг |\n|---|---|---|\n"
         "| Y | — | что-то вне выгрузки |\n")
    rep = sc.check_source_silent(docs)
    assert rep and rep[0].startswith("⚠ пометка о пробеле не по формуле ×2"), rep


def test_c6_card_text_still_warned(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs" / "c.md", "# К\n\nнет целевого артефакта — страница 1 вне выгрузки\n")
    rep = sc.check_source_silent(docs)
    assert rep and rep[0].startswith("⚠ пометка о пробеле не по формуле ×1"), rep


# --- класс 2: собственная страница ---

OWN = {"2166860131": "[КК_ВК] Сквозной процесс (Этап 1)",
       "2535842300": '[КК_СК] Первичное наполнение сущности "Карты клиентов"'}


def test_c2_own_additional_page_title(tmp_path):
    docs = kit(tmp_path)
    warns, _l, waived = targets(docs, "### [КК_ВК] Сквозной процесс (Этап 1)\n\nтекст",
                                export(pages=OWN), ids="'2166860040', '2166860131'")
    assert warns == [] and waived == [("own", "[КК_ВК] Сквозной процесс (Этап 1)")]


def test_c2_own_title_cut_by_boundary(tmp_path):
    docs = kit(tmp_path)
    warns, _l, waived = targets(docs, '## [КК_СК] Первичное наполнение сущности "Карты клиентов"',
                                export(pages=OWN), ids="'2535842300'")
    assert warns == [] and waived and waived[0][0] == "own"


def test_c2_other_card_page_still_warned(tmp_path):
    docs = kit(tmp_path)
    warns, _l, waived = targets(docs, "### [КК_ВК] Сквозной процесс (Этап 1)",
                                export(pages=OWN), ids="'2166860040'")
    assert len(warns) == 1 and waived == []


def test_c2_without_export_still_warned(tmp_path):
    docs = kit(tmp_path)
    warns, _l, _w = targets(docs, "### [КК_ВК] Сквозной процесс (Этап 1)", None, ids="'2166860131'")
    assert len(warns) == 1


# --- класс 1: тег-подпись ---

def test_c1_label_tag_in_prose_not_judged(tmp_path):
    docs = kit(tmp_path)
    warns, labels, _w = targets(docs, "Колонка [DEV] Код колонки задаёт код",
                                export(seen={"[DEV]", "[ДПП]"}, link={"[ДПП]"}))
    assert warns == [] and labels and labels[0][0] == "[DEV]"


def test_c1_tag_opening_link_text_still_warned(tmp_path):
    docs = kit(tmp_path)
    warns, labels, _w = targets(docs, "см. [ДПП] Классификатор статусов здесь",
                                export(seen={"[DEV]", "[ДПП]"}, link={"[ДПП]"}))
    assert len(warns) == 1 and labels == []


def test_c1_tag_absent_from_export_still_warned(tmp_path):
    docs = kit(tmp_path)
    warns, labels, _w = targets(docs, "сервис [ЭП] Сервис по работе с подписью вызывается",
                                export(seen={"[DEV]"}))
    assert len(warns) == 1 and labels == []


def test_c1_no_export_prose_still_warned(tmp_path):
    docs = kit(tmp_path)
    warns, labels, _w = targets(docs, "Колонка [DEV] Код колонки задаёт код", None)
    assert len(warns) == 1 and labels == []


def test_c1_source_label_not_required(tmp_path):
    docs = kit(tmp_path)
    body = card("FUN-CL-66", "Ф", "Код привилегии: BC.CLIENT")
    warns, ok, waived = sources(body, "<p>[DEV] Англоязычное наименование (код привилегии)</p>",
                                docs, export(seen={"[DEV]"}))
    assert warns == [] and ok and waived[0][0] == "src-label"


def test_c1_source_linked_tag_still_required(tmp_path):
    docs = kit(tmp_path)
    body = card("FUN-CL-66", "Ф", "текст")
    warns, _ok, waived = sources(body, "<p>[ДПП] Классификатор статусов</p>", docs,
                                 export(seen={"[ДПП]"}, link={"[ДПП]"}))
    assert len(warns) == 1 and waived == []


# --- класс 7: копия общей страницы метода ---

WHERE = ('<table><tr><td><strong>Где используется:</strong></td>\n<td><ul>'
         '<li>Процесс <a href="https://c/x?pageId=1">[РЭП] Зарегистрировать КЭП/НЭП</a> (Шаг №4)</li>'
         '<li>Процесс <a href="p.md">[КК_ВК] Получить выписку по клиенту</a> (Шаг №3)</li>'
         '</ul></td></tr></table>\n')


def test_c7_foreign_place_of_where_used_not_required(tmp_path):
    docs = kit(tmp_path)
    body = card("CALL-EXT-025", "Копия", "## Процессы\n\nнет", typ="contract-call")
    warns, _ok, waived = sources(body, WHERE, docs)
    assert len(warns) == 1 and "[КК_ВК] Получить выписку" in warns[0]  # своё место требуется
    assert [k for k, _t in waived] == ["foreign-place"] and "[РЭП]" in waived[0][1]


def test_c7_foreign_mention_outside_zone_still_required(tmp_path):
    docs = kit(tmp_path)
    body = card("CALL-EXT-025", "Копия", "нет", typ="contract-call")
    warns, _ok, waived = sources(body, "<p>см. [РЭП] Зарегистрировать КЭП/НЭП</p>", docs)
    assert len(warns) == 1 and waived == []


def test_c7_not_contract_call_still_required(tmp_path):
    docs = kit(tmp_path)
    body = card("FUN-CL-01", "Функция", "нет", typ="function")
    warns, _ok, waived = sources(body, WHERE, docs)
    assert len(warns) == 2 and waived == []


def test_c7_prose_phrase_does_not_open_zone(tmp_path):
    # «где используется» в прозе — не подпись: чужое упоминание после неё требуется
    docs = kit(tmp_path)
    body = card("CALL-EXT-025", "Копия", "нет", typ="contract-call")
    src = ("<p>Параметр передаётся в функциях, где используется метод: см. "
           "[РЭП] Зарегистрировать КЭП/НЭП.</p>\n<table><tr><td>a</td></tr></table>\n")
    warns, _ok, waived = sources(body, src, docs)
    assert len(warns) == 1 and "[РЭП]" in warns[0] and waived == []


def test_c7_capitalised_phrase_in_prose_does_not_open_zone(tmp_path):
    docs = kit(tmp_path)
    body = card("CALL-EXT-025", "Копия", "нет", typ="contract-call")
    src = "<p>Где используется метод, см. [РЭП] Зарегистрировать КЭП/НЭП.</p>\n"
    warns, _ok, waived = sources(body, src, docs)
    assert len(warns) == 1 and waived == []


def test_c7_own_place_in_zone_still_required(tmp_path):
    # своё место зоны (тег открывает титул карточки комплекта) требуется по-прежнему
    docs = kit(tmp_path)
    body = card("CALL-EXT-025", "Копия", "нет", typ="contract-call")
    src = ('<table><tr><td><strong>Где используется:</strong></td><td>Процесс '
           '<a href="p.md">[КК_ВК] Получить выписку по клиенту</a></td></tr></table>\n')
    warns, _ok, waived = sources(body, src, docs)
    assert len(warns) == 1 and "[КК_ВК] Получить выписку" in warns[0] and waived == []


def test_c7_zone_by_pipe_cell_and_heading(tmp_path):
    docs = kit(tmp_path)
    body = card("CALL-EXT-025", "Копия", "нет", typ="contract-call")
    for src in ("| **Где используется:** | Процесс [РЭП] Зарегистрировать КЭП/НЭП |\n",
                "## Где используется\n\nПроцесс [РЭП] Зарегистрировать КЭП/НЭП\n\n## Далее\n"):
        warns, _ok, waived = sources(body, src, docs)
        assert warns == [] and [k for k, _t in waived] == ["foreign-place"], src


# --- строки i снятого ---

def test_waived_i_lines(tmp_path):
    ctx = sc._KitCtx(docs=tmp_path, sources=None, strict=False, catalog=None, card_ids={},
                     card_titles={}, fm_schema_issues=[], groups={}, idx={},
                     mention_waived=[("debt-prefix", "a.md", "x ← долг «y»"),
                                     ("foreign-place", "b.md", "[РЭП] Z")])
    rep, ok = sc._kc_mention_waived(ctx)
    assert ok is True
    heads = [r for r in rep if r.startswith("i ")]
    assert len(heads) == 2 and ": 1; первые: a.md: «x ← долг «y»»" in heads[0]
    assert any(r.endswith("b.md — [РЭП] Z") for r in rep)


def test_waived_i_lines_empty(tmp_path):
    ctx = sc._KitCtx(docs=tmp_path, sources=None, strict=False, catalog=None, card_ids={},
                     card_titles={}, fm_schema_issues=[], groups={}, idx={})
    assert sc._kc_mention_waived(ctx) == ([], True)


def test_source_mention_index(tmp_path):
    src = tmp_path / "confluence"
    make(src / "a.md", "---\nconfluence_page_id: 101\ntitle: '[КК_ВК] Страница'\n---\n"
                       "| [DEV] Код колонки | x |\nсм. <a href=\"b.md\">[ДПП] Баннер</a> и "
                       "[[СУВ] Процесс](https://c/x)\n")
    idx = sp.source_mention_index(src)
    assert idx.page_titles == {"101": "[КК_ВК] Страница"}
    assert {"[ДПП]", "[СУВ]"} <= idx.link_tags and "[DEV]" not in idx.link_tags
    assert "[DEV]" in idx.seen_tags and "[КК_ВК]" in idx.title_tags
