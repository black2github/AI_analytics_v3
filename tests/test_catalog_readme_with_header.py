# tests/test_catalog_readme_with_header.py
"""Пакет П3 ОНБ-В, срез 6 (ПР-26, решение владельца 09.11 — вариант А): README каталогов ЭФ и
функций шапки не несут — навигационный README, i. Исключение прибора «README-реестры каталогов
(README функций, ID ЭФ на -00/-000) не проверяются» снято в части ЭФ и функций: README с шапкой
`type: screen-form` / `function` — обычный документ своего типа, без разделов шаблона — ⚠ «нет
обязательного раздела». У README-реестров CTL-000 / PRN-000 исключение остаётся."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fm(i: str, t: str) -> str:
    return f"---\nid: {i}\ntype: {t}\nservice: x\ntitle: Реестр\n---\n\n# Реестр\n\n"


REGISTRY = "| ID | Название |\n|---|---|\n| SCR-CL-01 | Форма |\n"


def test_catalog_readme_without_header_is_navigational_info(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/screen-form/README.md", "# Экранные формы\n\n" + REGISTRY)
    w(docs / "srs/function/README.md", "# Функции\n\n" + REGISTRY)
    rep, _ok = sc.run(docs, None)
    for rel in ("srs/screen-form/README.md", "srs/function/README.md"):
        assert any(ln.startswith(f"i {Path(rel)}: навигационный README без frontmatter") for ln in rep), rep
    assert sc.check_required_sections(docs) == []


def test_screen_form_catalog_readme_with_header_checked(tmp_path):
    """README с шапкой SCR-000 — обычный документ screen-form: ⚠ «нет обязательного раздела»."""
    docs = tmp_path / "docs"
    w(docs / "srs/screen-form/README.md", fm("SCR-000", "screen-form") + REGISTRY)
    rep = sc.check_required_sections(docs)
    assert rep and "единиц 1" in rep[0], rep
    assert any("SCR-000" in ln and "«Назначение»" in ln for ln in rep[1:]), rep


def test_function_catalog_readme_with_header_checked(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/function/README.md", fm("FUN-000", "function") + REGISTRY)
    rep = sc.check_required_sections(docs)
    assert rep and any("srs/function/README.md [function]" in ln for ln in rep[1:]), rep


def test_function_group_readme_without_header_not_checked_as_function(tmp_path):
    """НЕсрабатывание: README группы без своей шапки берёт тип главной карточки, но документом
    функции не становится — разделы шаблона у него не ищутся (как прежде)."""
    docs = tmp_path / "docs"
    g = docs / "srs/function/fun-cl-01-x"
    w(g / "README.md", "# Группа\n\nНавигация.\n")
    w(g / "fun-cl-01-main.md", fm("FUN-CL-01", "function")
      + "## Назначение\n\nт\n\n## Доступность\n\nт\n\n## Вызов функции\n\nт\n\n## Поведение\n\nт\n")
    assert sc.check_required_sections(docs) == []


def test_control_and_print_form_registries_still_not_checked(tmp_path):
    """НЕсрабатывание: у CTL-000 и PRN-000 исключение остаётся."""
    docs = tmp_path / "docs"
    w(docs / "srs/print-form/README.md", fm("PRN-000", "print-form") + REGISTRY)
    w(docs / "srs/control/README.md", fm("CTL-000", "control") + "## Назначение\n\nт\n\n## Группы контролей\n\nт\n\n"
      "## Реестр контролей\n\nт\n\n## Карточки контролей\n\nт\n")
    assert sc.check_required_sections(docs) == []
