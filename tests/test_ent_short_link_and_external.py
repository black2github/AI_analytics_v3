# tests/test_ent_short_link_and_external.py
"""Постановка прибору 2026-11-10 («Точки расширения эталона»), пп. 1 и 4,
`check_named_entity_links`:

п. 1 — абсолютный адрес карточки чужого репозитория (`https://…/ent-001-….md`) вне
проверки: номер ENT там из чужого пространства ID (FUN-CL-46 КК).

п. 4 — норма владельца 10.11: короткая ссылка `[ENT-NNN]` (и запись атрибута
`[ENT-NNN](…).«Атрибут»`) требует более ранней полной ссылки `[ENT-NNN <название>]`;
дословное имя с тегом её не заменяет. Для ссылки-названия без ID имя с тегом по-прежнему
засчитывается."""
from pathlib import Path

from app.scripts.CI.kitcheck.checks.links import check_named_entity_links

ENT = "../data-model/ent-016-card-issue-request.md"
EXT = ("https://gitlab.gboteam.ru/EAN/docs-account-opening-request/-/blob/HEAD/"
       "srs/data-model/ent-001-request.md")


def card(tmp_path: Path, body: str) -> Path:
    docs = tmp_path / "docs"
    (docs / "function").mkdir(parents=True, exist_ok=True)
    (docs / "function" / "fun-cl-01-x.md").write_text(
        "---\nid: FUN-CL-01\ntitle: 'x'\ntype: function\nservice: business-cards\n---\n\n"
        "# FUN-CL-01. x\n\n" + body + "\n", encoding="utf-8")
    return docs


# --- п. 1: абсолютный адрес ---

def test_absolute_url_named_link_silent(tmp_path):
    docs = card(tmp_path, f"Создаётся [Заявка на открытие доп счета и заключение ДБС]({EXT}).")
    assert check_named_entity_links(docs) == []


def test_absolute_url_short_link_silent(tmp_path):
    docs = card(tmp_path, f"Значение = [ENT-001]({EXT}).«Номер».")
    assert check_named_entity_links(docs) == []


def test_relative_named_link_still_flagged(tmp_path):
    # НЕсрабатывание исключения: относительная ссылка-название без ID — ⚠ остаётся
    docs = card(tmp_path, f"В [Заявке на выпуск карты]({ENT}) заполняется ИНН.")
    rep = check_named_entity_links(docs)
    assert len(rep) == 1 and "ENT-016 названием без ID ×1" in rep[0]


# --- п. 4: короткая ссылка раньше полной ---

def test_short_before_full_flagged_with_count(tmp_path):
    docs = card(tmp_path,
                f"[ENT-016]({ENT}).«ИНН» и [ENT-016]({ENT}).«КПП». "
                f"Ниже: [ENT-016 Заявка на выпуск карты]({ENT}), затем [ENT-016]({ENT}).«ОГРН».")
    rep = check_named_entity_links(docs)
    assert len(rep) == 1
    assert "короткая ссылка на ENT-016 раньше полной" in rep[0]
    assert "×2" in rep[0] and "полная ссылка стоит ниже" in rep[0]


def test_short_after_full_silent(tmp_path):
    docs = card(tmp_path,
                f"Создаётся [ENT-016 Заявка на выпуск карты]({ENT}); [ENT-016]({ENT}).«ИНН».")
    assert check_named_entity_links(docs) == []


def test_tagged_name_does_not_justify_short(tmp_path):
    docs = card(tmp_path,
                f"Создаётся [[КК_ВК] Заявка на выпуск карты]({ENT}); [ENT-016]({ENT}).«ИНН».")
    rep = check_named_entity_links(docs)
    assert len(rep) == 1 and "короткая ссылка на ENT-016 раньше полной" in rep[0]
    assert "×1" in rep[0] and "полная ссылка стоит ниже" not in rep[0]


def test_tagged_name_still_justifies_named_link(tmp_path):
    # логика ссылки-названия без ID не меняется: имя с тегом её обосновывает
    docs = card(tmp_path,
                f"Создаётся [[КК_ВК] Заявка на выпуск карты]({ENT}); в [заявке]({ENT}) — ИНН.")
    assert check_named_entity_links(docs) == []


def test_short_link_in_code_and_readme_silent(tmp_path):
    docs = card(tmp_path, f"```markdown\n[ENT-016]({ENT}).«ИНН»\n```\n")
    (docs / "function" / "README.md").write_text(
        f"| ID | Файл |\n|---|---|\n| [ENT-016]({ENT}) | x |\n", encoding="utf-8")
    assert check_named_entity_links(docs) == []
