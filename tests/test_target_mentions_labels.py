# tests/test_target_mentions_labels.py
"""Сторож упоминаний целей: ярлык строки таблицы — не упоминание (постановка 15.11, решение
постановщика). Признак — оба условия сразу: тег стоит в первой ячейке строки таблицы И не
открывает ни одного титула карточек комплекта, а при выгрузке — и страниц выгрузки. Такие
вхождения не судятся, а сводятся в одну строку i на комплект со всеми тегами и числом
вхождений; перечень «файл:строка» — в --out.

Несрабатывание признака (⚠ как прежде): упоминание в ячейке значения; первая ячейка с тегом из
титулов комплекта; тег вне титулов в прозе; тег вне титулов комплекта, но из титулов выгрузки
(при --sources); вторая ячейка той же строки."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks import card_clean as cc
from app.scripts.CI.kitcheck.checks import source_profile as sp


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def card(cid: str, title: str, body: str) -> str:
    return (f"---\nid: {cid}\ntitle: '{title}'\ntype: internal-contract\n---\n\n"
            f"# {cid}. {title}\n\n{body}\n")


def kit(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", "# Матрица трассировки\n\n| FROM | TO |\n|---|---|\n")
    # титул с тегом [КК_БК] — тег комплекта
    make(docs / "srs" / "other.md", card("INTC-099", "[КК_БК] Другая карточка", "т"))
    cc._TARGET_INDEX_CACHE.clear()
    return docs


def run(docs: Path, body: str, source_tags=frozenset()):
    md = make(docs / "srs" / "intc-001.md", card("INTC-001", "Контракт", body))
    cc._TARGET_INDEX_CACHE.clear()
    labels = []
    warns, ok = cc.check_target_mentions(md.read_text(encoding="utf-8"), md, docs,
                                         source_tags, labels)
    assert ok is True
    return [w for w in warns if "упоминание цели" in w], labels


PASSPORT = "| Параметр | Значение |\n|---|---|\n| [DEV] Метод API | /business-cards/x |\n"


# --- признак срабатывает: ярлык не судится, складывается в labels ---

def test_dev_label_in_first_cell_not_judged(tmp_path):
    docs = kit(tmp_path)
    warns, labels = run(docs, PASSPORT)
    assert warns == []
    assert labels == [("[DEV]", 11, "[DEV] Метод API")]


def test_kit_title_tags_index(tmp_path):
    docs = kit(tmp_path)
    assert cc.kit_title_tags(docs) == frozenset({"[КК_БК]"})


# --- признак не срабатывает: ⚠ как прежде ---

def test_mention_in_value_cell_warns(tmp_path):
    docs = kit(tmp_path)
    warns, labels = run(docs, "| Параметр | Значение |\n|---|---|\n"
                              "| Описание | см. [ЦРМ] Ролевая модель клиента |\n")
    assert len(warns) == 1 and "«[ЦРМ] Ролевая модель клиента»" in warns[0]
    assert labels == []


def test_first_cell_with_kit_title_tag_warns(tmp_path):
    docs = kit(tmp_path)
    warns, labels = run(docs, "| Что это | Куда ведёт |\n|---|---|\n"
                              "| [КК_БК] Функции Клиента | экранные формы |\n")
    assert len(warns) == 1 and "«[КК_БК] Функции Клиента»" in warns[0]
    assert labels == []


def test_tag_outside_titles_in_prose_warns(tmp_path):
    docs = kit(tmp_path)
    warns, labels = run(docs, "Путь задан строкой [DEV] Метод API паспорта.\n")
    assert len(warns) == 1 and "«[DEV] Метод API паспорта»" in warns[0]
    assert labels == []


def test_tag_from_source_titles_in_first_cell_warns_with_sources(tmp_path):
    docs = kit(tmp_path)
    body = "| Параметр | Значение |\n|---|---|\n| [ЦРМ] Ролевая модель | роли |\n"
    warns, labels = run(docs, body, source_tags=frozenset({"[ЦРМ]"}))
    assert len(warns) == 1 and "«[ЦРМ] Ролевая модель»" in warns[0]
    assert labels == []
    # без выгрузки тег вне титулов комплекта — ярлык
    warns, labels = run(docs, body)
    assert warns == [] and [lb[0] for lb in labels] == ["[ЦРМ]"]


def test_second_cell_mention_in_same_row_warns(tmp_path):
    docs = kit(tmp_path)
    warns, labels = run(docs, "| Параметр | Значение |\n|---|---|\n"
                              "| [DEV] Метод API | см. [ЦРМ] Ролевая модель |\n")
    assert len(warns) == 1 and "«[ЦРМ] Ролевая модель»" in warns[0]
    assert [lb[0] for lb in labels] == ["[DEV]"]


def test_in_first_cell_positions():
    text = "| [DEV] A | [X] B |\nтекст [DEV] C\n  | [Y] D |"
    assert cc._in_first_cell(text, text.find("[DEV] A"))
    assert not cc._in_first_cell(text, text.find("[X] B"))
    assert not cc._in_first_cell(text, text.find("[DEV] C"))
    assert cc._in_first_cell(text, text.find("[Y] D"))


# --- selfcheck: строка i на комплект, перечень в --out ---

def _src(tmp_path: Path, titles) -> Path:
    conf = tmp_path / "src" / "sources" / "confluence"
    for i, t in enumerate(titles):
        make(conf / f"p{i}.md", f"---\ntitle: '{t}'\nconfluence_page_id: '90000{i}'\n---\n\nт\n")
    return conf


def test_source_title_tags(tmp_path):
    conf = _src(tmp_path, ["[ЦРМ] Ролевая модель", "Без тега", "[КК_БК] Функция"])
    assert sp.source_title_tags(conf) == frozenset({"[ЦРМ]", "[КК_БК]"})


def test_selfcheck_kit_line_without_sources(tmp_path):
    docs = kit(tmp_path)
    make(docs / "srs" / "intc-001.md", card("INTC-001", "Контракт", PASSPORT + "| [DEV] Транспорт | HTTPS |\n"))
    make(docs / "srs" / "intc-002.md", card("INTC-002", "Контракт 2", PASSPORT))
    report, _ok = sc.run(docs, None)
    line = [ln for ln in report if "ярлыки строк таблиц" in ln]
    assert line == ["i ярлыки строк таблиц с тегом вне титулов — не упоминания: [DEV] ×3 (тег в "
                    "первой ячейке строки таблицы не открывает ни одного титула карточек комплекта; "
                    "сторож упоминаний целей такие ярлыки не судит, перечень — в --out)"], report
    out = [ln for ln in report if ln.startswith(sc.OUT_ONLY)]
    assert sc.OUT_ONLY + "srs/intc-001.md:11 — [DEV] Метод API" in out, out
    assert sc.OUT_ONLY + "srs/intc-001.md:12 — [DEV] Транспорт" in out, out
    assert not any("упоминание цели «[DEV]" in ln for ln in report), report


def test_selfcheck_source_title_tag_keeps_warning(tmp_path):
    docs = kit(tmp_path)
    make(docs / "srs" / "intc-001.md", card("INTC-001", "Контракт", PASSPORT))
    conf = _src(tmp_path, ["[DEV] Метод API сервиса"])
    report, _ok = sc.run(docs, conf)
    assert any("упоминание цели «[DEV] Метод API»" in ln for ln in report), report
    assert not any("ярлыки строк таблиц" in ln for ln in report), report


def test_selfcheck_no_labels_no_line(tmp_path):
    docs = kit(tmp_path)
    make(docs / "srs" / "intc-001.md", card("INTC-001", "Контракт", "текст без таблиц"))
    report, _ok = sc.run(docs, None)
    assert not any("ярлыки строк таблиц" in ln for ln in report), report
