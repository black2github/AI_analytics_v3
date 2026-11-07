# tests/test_scr_links_without_id.py
"""Пакет П2 ОНБ-В, п. 5 (остаток замечания 22): ссылка на экранную форму без ID в
тексте — в той же строке ⚠, что CTL/CALL/PLT."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.links import check_link_anchors_and_ids

FM = "---\nid: FUN-CL-01\ntype: function\nservice: x\n---\n\n# Ф\n\n"


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def kit(tmp_path: Path, body: str) -> Path:
    docs = tmp_path / "docs"
    sf = docs / "srs/screen-form/client"
    w(sf / "scr-cl-02-filter.md", "---\nid: SCR-CL-02\ntype: screen-form\nservice: x\n---\n\n"
      "# ЭФ\n\n## FLD-1 Счёт\n\nт\n")
    w(sf / "scr-cl-13-edit/README.md", "# Группа\n")
    w(sf / "scr-cl-13-edit/scr-cl-13-main.md", "---\nid: SCR-CL-13\ntype: screen-form\nservice: x\n---\n\n"
      "# ЭФ\n\n## FLD-17 Доп\n\nт\n")
    w(docs / "srs/function/client/fun-cl-01.md", FM + body)
    return docs


def _noid(rep):
    head = next((ln for ln in rep if ln.startswith("⚠ ссылки на карточку")), None)
    return head, [ln.strip() for ln in rep if ln.startswith("   srs/")]


def test_screen_link_without_id_warned(tmp_path):
    docs = kit(tmp_path, "Открывается [ЭФ Клиента «Фильтр»](../../screen-form/client/scr-cl-02-filter.md).\n")
    head, items = _noid(check_link_anchors_and_ids(docs))
    assert head and "экранной формы без ID в тексте: 1" in head, head
    assert items == ["srs/function/client/fun-cl-01.md: [ЭФ Клиента «Фильтр»]"]


def test_screen_link_with_id_silent(tmp_path):
    docs = kit(tmp_path, "Открывается [SCR-CL-02 ЭФ Клиента «Фильтр»](../../screen-form/client/"
               "scr-cl-02-filter.md) и [SCR-CL-13.1](../../screen-form/client/scr-cl-13-edit/scr-cl-13-main.md).\n")
    assert _noid(check_link_anchors_and_ids(docs))[0] is None


def test_source_tag_labels_silent_three_forms(tmp_path):
    # вариант А: дословное наименование источника с тегом — полноценное упоминание
    p = "../../screen-form/client/scr-cl-02-filter.md"
    docs = kit(tmp_path, f"[[КК_ВК] ЭФ Клиента «Фильтр»]({p}), [\\[КК_ВК\\] ЭФ Клиента]({p}), "
               f"[«[КК_ЛК] ЭФ Клиента: „Фильтр“» (SCR-CL-02)]({p}).\n")
    assert _noid(check_link_anchors_and_ids(docs))[0] is None


def test_element_anchor_group_readme_self_nav_list_silent(tmp_path):
    # НЕсрабатывание: якорь на элемент части, README группы, ссылка на себя, навигационный список
    p13 = "../../screen-form/client/scr-cl-13-edit"
    body = (f"Поле [FLD-17]({p13}/scr-cl-13-main.md#fld-17-доп), группа [README]({p13}/README.md).\n\n"
            "Ссылка на себя: [эта функция](fun-cl-01.md).\n\n"
            "- [Фильтр](../../screen-form/client/scr-cl-02-filter.md)\n"
            "- [Редактирование](../../screen-form/client/scr-cl-13-edit/scr-cl-13-main.md)\n")
    assert _noid(check_link_anchors_and_ids(docs := kit(tmp_path, body)))[0] is None, docs


def test_readme_and_matrix_sources_not_checked(tmp_path):
    docs = kit(tmp_path, "т\n")
    w(docs / "srs/README.md", "Экраны: [фильтр](screen-form/client/scr-cl-02-filter.md).\n")
    assert _noid(check_link_anchors_and_ids(docs))[0] is None


def test_non_screen_scr_named_file_outside_screen_form_silent(tmp_path):
    # признак — каталог screen-form цели, а не только имя файла
    docs = kit(tmp_path, "См. [заметку](../../notes/scr-notes.md).\n")
    w(docs / "srs/notes/scr-notes.md", "# Заметка\n")
    assert _noid(check_link_anchors_and_ids(docs))[0] is None
