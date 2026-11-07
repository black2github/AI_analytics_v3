# tests/test_source_tables_extra_pages.py
"""Сверка таблиц и литералов по дополнительным страницам и по объединению карточек страницы.
Значение страницы перенесено, если оно есть в любой карточке с этой страницей в
confluence_page_ids; значение, которого нет нигде, остаётся потерей."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks.card_source import check_source_tables
from app.scripts.CI.kitcheck.core import is_soft_signal

P1, P2, P3 = "2000000111", "2000000222", "2000000333"
TABLE = "| Код | Значение |\n|---|---|\n| ALFA | Первое значение |\n| BETA | Второе значение |\n"
VALUES = "ALFA Первое значение BETA Второе значение\n"
LOST = "таблица источника «Код | Значение»"
FOUND = "i таблицы источника: значений"


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid: str, title: str, pids: str, body: str = "текст\n", typ: str = "data-model") -> str:
    return (f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\nconfluence_page_ids: [{pids}]\n---\n\n"
            f"# {title}\n\n{body}")


def page(pid: str, title: str, body: str = "текст\n") -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n{body}"


def kit(tmp_path: Path, cards: dict, pages: dict) -> Path:
    docs = tmp_path / "kit/docs"
    src = tmp_path / "kit/sources/confluence"
    make(docs / "traceability-matrix.md", "# М\n")
    for rel, text in cards.items():
        make(docs / rel, text)
    for pid, (title, body) in pages.items():
        make(src / f"{pid}.md", page(pid, title, body))
    return docs


def run(docs: Path):
    report, _ok = sc.run(docs, docs.parent / "sources/confluence")
    return report


def hits(report, needle):
    return [ln for ln in report if needle in ln]


# ---------------------------------------------------------------- сторож без комплекта

def test_unit_no_artifacts_as_before():
    rep, ok = check_source_tables("пусто", TABLE)
    assert not ok and any(LOST in l for l in rep) and not hits(rep, FOUND)


def test_unit_value_in_page_card_not_lost():
    rep, ok = check_source_tables("пусто", TABLE, page_artifacts=[("a/b.md", VALUES)])
    assert ok and not any(LOST in l for l in rep)
    line = hits(rep, FOUND)[0]
    assert "×4" in line and "a/b.md" in line and is_soft_signal(line)


def test_unit_value_absent_everywhere_stays_lost():
    rep, ok = check_source_tables("ALFA Первое значение", TABLE,
                                  page_artifacts=[("a/b.md", "BETA")])
    assert not ok and "отсутствуют 1 значений" in hits(rep, LOST)[0]
    assert "×1" in hits(rep, FOUND)[0]


def test_unit_only_files_with_hits_are_named():
    rep, _ok = check_source_tables("пусто", TABLE,
                                   page_artifacts=[("hit.md", VALUES), ("miss.md", "иное")])
    assert "hit.md" in hits(rep, FOUND)[0] and "miss.md" not in hits(rep, FOUND)[0]


def test_unit_html_param_names_use_union():
    src = ("<table><tr><th>Параметр</th><th>Описание</th></tr>"
           "<tr><td>file_id</td><td>Идентификатор файла</td></tr></table>\n")
    assert not check_source_tables("пусто", src)[1]
    rep, ok = check_source_tables("пусто", src,
                                  page_artifacts=[("a.md", "file_id Идентификатор файла Параметр Описание")])
    assert ok and hits(rep, FOUND)


def test_unit_thin_call_has_no_union_line():
    # тонкой карточке вызова имена параметров не требуются: сообщать о «найденных» нечего
    src = ("<table><tr><th>Параметр</th><th>Описание</th></tr>"
           "<tr><td>file_id</td><td>Идентификатор файла</td></tr></table>\n")
    rep, ok = check_source_tables("пусто", src, thin_call="базовый контракт",
                                  page_artifacts=[("a.md", "file_id")])
    assert ok and not hits(rep, FOUND) and hits(rep, "имён параметров HTML-таблиц не сверялось")


# ---------------------------------------------------------------- таблицы доп. страницы

def test_extra_page_table_loss_fires_with_page_tag(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}")},
               {P1: ("А", "текст\n"), P2: ("Б", TABLE)})
    line = hits(run(docs), LOST)
    assert line and f"(доп. страницы {P2} «Б»)" in line[0] and "✗" in line[0]


def test_extra_page_table_transferred_no_loss(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}", TABLE)},
               {P1: ("А", "текст\n"), P2: ("Б", TABLE)})
    assert not hits(run(docs), LOST)


def test_extra_page_outside_export_not_compared(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}")},
               {P1: ("А", "текст\n")})
    report = run(docs)
    assert not hits(report, LOST) and hits(report, f"вне выгрузки, без сверки: {P2}")


def test_extra_page_values_in_card_of_that_page(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}"),
                          "srs/function/f.md": card("FUN-1", "Б", P2, TABLE, typ="function")},
               {P1: ("А", "текст\n"), P2: ("Б", TABLE)})
    report = run(docs)
    assert not hits(report, LOST)
    assert any("srs/function/f.md" in l and f"(доп. страницы {P2} «Б»)" in l
               for l in hits(report, FOUND))


def test_main_page_values_in_card_having_it_as_extra(tmp_path):
    # сведение двух карточек в одну: страница стала дополнительной у сведённой, вторая карточка
    # той же страницы теряет её из группы, значения находятся по объединению
    docs = kit(tmp_path, {"srs/data-model/merged.md": card("DM-1", "А", f"{P1}, {P2}", TABLE),
                          "srs/function/f.md": card("FUN-1", "Б", P2, typ="function")},
               {P1: ("А", "текст\n"), P2: ("Б", TABLE)})
    report = run(docs)
    assert not hits(report, LOST)
    assert any("srs/data-model/merged.md" in l for l in hits(report, FOUND))


def test_same_directory_card_counts_for_tables(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}"),
                          "srs/data-model/b.md": card("DM-2", "Б", P2, TABLE)},
               {P1: ("А", "текст\n"), P2: ("Б", TABLE)})
    assert not hits(run(docs), LOST)


def test_card_of_other_page_does_not_count(tmp_path):
    # НЕсрабатывание снятия: значение лежит в карточке, у которой этой страницы нет
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}"),
                          "srs/function/c.md": card("FUN-3", "В", P3, TABLE, typ="function")},
               {P1: ("А", "текст\n"), P2: ("Б", TABLE), P3: ("В", TABLE)})
    report = run(docs)
    assert hits(report, f"(доп. страницы {P2} «Б»)") and any("✗" in l for l in hits(report, LOST))


def test_single_page_card_unchanged(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", P1),
                          "srs/function/c.md": card("FUN-3", "В", P3, TABLE, typ="function")},
               {P1: ("А", TABLE), P3: ("В", TABLE)})
    report = run(docs)
    assert hits(report, LOST) and not hits(report, FOUND) and not hits(report, "доп. страницы")


# ---------------------------------------------------------------- сводные типы

def test_vision_extra_pages_not_compared_and_counted(tmp_path):
    docs = kit(tmp_path, {"service-vision.md": card("VIS-001", "А", f"{P1}, {P2}", typ="vision")},
               {P1: ("А", "текст\n"), P2: ("Черновик", TABLE)})
    report = run(docs)
    assert not hits(report, LOST)
    line = hits(report, "i таблицы источника: доп. страниц ×1")
    assert line and "видению сервиса" in line[0] and is_soft_signal(line[0].strip())


def test_vision_main_page_still_compared(tmp_path):
    docs = kit(tmp_path, {"service-vision.md": card("VIS-001", "А", P1, typ="vision")},
               {P1: ("А", TABLE)})
    assert hits(run(docs), LOST)


# ---------------------------------------------------------------- литералы

LITERAL = 'Кнопка "Сохранить черновик" на форме.\n'


def test_extra_page_literal_in_card_of_that_page(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}"),
                          "srs/function/f.md": card("FUN-1", "Б", P2, LITERAL, typ="function")},
               {P1: ("А", "текст\n"), P2: ("Б", LITERAL)})
    report = run(docs)
    assert not hits(report, f"кавычечные литералы доп. страницы {P2} «Б»: в карточке отсутствуют")
    assert hits(report, "найдены в артефактах той же страницы")


def test_extra_page_literal_absent_everywhere_fires(tmp_path):
    docs = kit(tmp_path, {"srs/data-model/a.md": card("DM-1", "А", f"{P1}, {P2}"),
                          "srs/function/f.md": card("FUN-1", "Б", P2, typ="function")},
               {P1: ("А", "текст\n"), P2: ("Б", LITERAL)})
    assert hits(run(docs), f"кавычечные литералы доп. страницы {P2} «Б»")
