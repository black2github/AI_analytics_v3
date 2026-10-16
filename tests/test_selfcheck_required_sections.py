# tests/test_selfcheck_required_sections.py
"""Пакет 2, задача 7 (ПР-05, ЗК-23): обязательные разделы шаблона — ⚠ «нет раздела»,
разделы вне шаблона — i."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fm(i: str, t: str, extra: str = "") -> str:
    return f"---\nid: {i}\ntype: {t}\nservice: x\n{extra}---\n\n# Заголовок\n\n"


def test_missing_required_section_warned_numbering_and_id_ignored(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/f/fun-cl-01.md", fm("FUN-CL-01", "function")
      + "## 1. Назначение\n\nт\n\n## 2. ДОСТУПНОСТЬ\n\nт\n\n## 3. Вызов функции\n\nт\n")
    w(docs / "srs/ntf-notification.md", fm("NTF-AGR-000", "notification")
      + "## Каналы и адреса доставки\n\nт\n\n## NTF-AGR-01. Сообщения нотификации\n\nт\n")
    rep = sc.check_required_sections(docs)
    assert rep and "единиц 1" in rep[0], rep
    assert "fun-cl-01.md [function]: «Поведение»" in rep[1], rep


def test_screen_form_group_union_parts_registry_and_stub_silent(tmp_path):
    docs = tmp_path / "docs"
    g = docs / "srs/screen-form/client/scr-cl-02-edit"
    w(g / "README.md", "# ЭФ Клиента «Ред.»\n\n## Части\n\nт\n\n## Макеты ЭФ\n\nт\n")
    w(g / "scr-cl-02-main.md", fm("SCR-CL-02", "screen-form")
      + "## 1. Назначение\n\nт\n\n## 2. Как перейти на ЭФ\n\nт\n\n## 3. Структура экрана\n\nт\n")
    w(g / "scr-cl-02.1-data.md", fm("SCR-CL-02.1", "screen-form")
      + "## 1. Реестр полей\n\nт\n\n## 2. Правила полей\n\nт\n")
    w(docs / "srs/screen-form/client/README.md", fm("SCR-CL-00", "screen-form") + "| ID | Форма |\n")
    w(docs / "srs/screen-form/client/scr-cl-03-stub.md", fm("SCR-CL-03", "screen-form")
      + "## Назначение\n\nДокумент-заглушка: форма будет описана позже.\n")
    assert sc.check_required_sections(docs) == []


def test_section_with_only_silent_formula_and_control_readme_cards_silent(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/control/README.md", fm("CTL-000", "control")
      + "## 1. Назначение\n\nв постановке не задано\n\n## 2. Группы контролей\n\nт\n\n"
        "## 3. Реестр контролей\n\nт\n")
    w(docs / "srs/control/cards-01.md", fm("CTL-001", "control", "partOf: CTL-000\n")
      + "## 4. Карточки контролей\n\nт\n")
    w(docs / "srs/agents/agent-01.md", fm("AGT-01", "agent")
      + "## Описание агента\n\nв постановке не задано\n\n## Описание процесса\n\nт\n")
    w(docs / "srs/process/status-model.md", fm("SM-01", "process") + "## Статусы\n")
    assert sc.check_required_sections(docs) == []


def test_out_of_template_section_is_info_not_warning(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/f/fun-cl-02.md", fm("FUN-CL-02", "function")
      + "## Назначение\n\n## Доступность\n\n## Вызов функции\n\n## Поведение\n\n"
        "## Параметры вызова функции подписи\n")
    w(docs / "srs/scr/scr-bnk-10.md", fm("SCR-BNK-10", "screen-form")
      + "## Назначение\n\n## Реестр полей\n\n## Правила полей\n\n## Описание кнопок ЭФ\n")
    rep = sc.check_required_sections(docs)
    assert len(rep) == 1 and rep[0].startswith("i разделы вне шаблона"), rep
    assert "«описание кнопок эф» ×1" in rep[0] and "параметры" not in rep[0], rep
