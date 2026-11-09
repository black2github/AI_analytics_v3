# tests/test_registry_label_names.py
"""Пакет П3 ОНБ-В, п. 3 (решение владельца 2026-11-09): строка «одинаковые названия разных ID
одного типа (реестр матрицы)» понижена до i — замер волны Д: на КК 8 из 10 групп — форма
источника (однотипные проверки полей в разных блоках). Истинный класс выделен по форме в
отдельную ⚠: название — метка вместо названия (латинский код без слов «BE»; значение `type`
документов комплекта «internal-contract»)."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_label_name_forms():
    types = {"internal-contract", "function"}
    assert sc.registry_label_name("CTL-GRP-26, CTL-GRP-27 — «BE»", types)
    assert sc.registry_label_name("INTC-001, INTC-002 — «internal-contract»", types)


def test_ordinary_names_not_labels():
    """НЕсрабатывание: дословные названия проверок и короткие кириллические — не метки."""
    types = {"internal-contract"}
    assert not sc.registry_label_name("CTL-214, CTL-249 — «Адрес одной строкой: Проверка длины»", types)
    assert not sc.registry_label_name("EXT-AGR-001, EXT-USR-001 — «Пользователь»", types)
    assert not sc.registry_label_name("CTL-1, CTL-2 — «ИНН»", types)
    assert not sc.registry_label_name("CTL-1, CTL-2 — «Be careful»", types)


MATRIX = ("# Матрица\n\n## Реестр ID\n\n| ID | Название | Файл |\n|---|---|---|\n"
          "| CTL-001 | Имя: Проверка заполненности | a.md |\n"
          "| CTL-002 | Имя: Проверка заполненности | b.md |\n"
          "| CTL-GRP-1 | BE | a.md |\n| CTL-GRP-2 | BE | b.md |\n")


def test_kit_lines_levels(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", MATRIX)
    report, _ok = sc.run(docs, None)
    i_line = [x for x in report if "одинаковые названия разных ID одного типа" in x]
    w_line = [x for x in report if x.startswith("⚠ название-метка вместо названия")]
    assert i_line and i_line[0].startswith("i ") and "групп 1" in i_line[0]
    assert w_line and "групп 1" in w_line[0]
    joined = "\n".join(report)
    assert "CTL-GRP-1, CTL-GRP-2 — «BE»" in joined
    assert "CTL-001, CTL-002 — «Имя: Проверка заполненности»" in joined
    assert not [x for x in report if x.startswith("⚠ одинаковые названия разных ID")]
