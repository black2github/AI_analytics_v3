# tests/test_glossary_guards.py
"""Глоссарий (решение владельца канона 2026-10-30, заход глоссария КК 29.10): к документу
type: glossary не применяются сторож полноты кавычечных литералов источника (документ
определений, не дословный перенос страницы — i-строка вместо ✗) и сторож выносок «>»
(выноску-делегирование предписывает шаблон glossary.md). Исключение — по type из
frontmatter, не по имени файла; обычная карточка с теми же признаками — прежние ✗."""
from pathlib import Path

from app.scripts.CI.normalize_tables import run_check

SRC = ("---\ntitle: '[X] Глоссарий'\nconfluence_page_id: '1'\n---\n\n"
       "Термин «Подсервис» — «Набор операций и функционала сервиса». "
       "Статус «Черновик заявки» и статус «Отправлена в банк».\n")

BODY = ("# Глоссарий\n\n"
        "| Термин | Определение |\n|---|---|\n"
        "| **Подсервис** | Набор операций сервиса. |\n\n"
        "> Полный справочник статусов заявки — в [process/](srs/process/README.md). "
        "Здесь — опорные доменные термины.\n")


def _card(tmp_path: Path, name: str, type_: str) -> Path:
    p = tmp_path / name
    (tmp_path / "srs/process").mkdir(parents=True, exist_ok=True)
    (tmp_path / "srs/process/README.md").write_text("# Процессы\n", encoding="utf-8")
    p.write_text(f"---\nid: GLO-001\ntitle: '[X] Глоссарий'\ntype: {type_}\n"
                 "confluence_page_ids: ['1']\n---\n\n" + BODY, encoding="utf-8")
    return p


def _src(tmp_path: Path) -> Path:
    s = tmp_path / "src.md"
    s.write_text(SRC, encoding="utf-8")
    return s


def test_glossary_with_delegation_and_partial_literals_passes(tmp_path):
    rep, ok = run_check([_card(tmp_path, "glossary.md", "glossary")], _src(tmp_path))
    text = "\n".join(rep)
    assert ok, text
    assert "i glossary.md: сторож литералов не применяется к глоссарию" in rep, text
    assert not any("blockquote" in r for r in rep), text
    assert not any("кавычечные литералы источника" in r for r in rep), text


def test_exemption_line_visible_in_selfcheck_when_green():
    # i-строка видна и при ✓ — «сторож не применялся», а не «прошёл»
    from app.scripts.CI.kitcheck.core import is_soft_signal
    assert is_soft_signal("i glossary.md: сторож литералов не применяется к глоссарию")
    assert is_soft_signal("[part.md] i glossary.md: сторож литералов не применяется к глоссарию")
    assert not is_soft_signal("i glossary.md: доп. страницы-источники (2) механически не сверяются")


def test_exemption_by_type_not_by_file_name(tmp_path):
    # глоссарий под другим именем файла — исключение действует
    rep, ok = run_check([_card(tmp_path, "terms.md", "glossary")], _src(tmp_path))
    assert ok, "\n".join(rep)
    assert "i terms.md: сторож литералов не применяется к глоссарию" in rep


def test_ordinary_card_same_features_still_flagged(tmp_path):
    # НЕсрабатывание исключения: файл glossary.md, но type не glossary — прежние ✗
    rep, ok = run_check([_card(tmp_path, "glossary.md", "function")], _src(tmp_path))
    text = "\n".join(rep)
    assert not ok, text
    assert any("blockquote «>» ×1" in r for r in rep), text
    assert any("кавычечные литералы источника: в карточке отсутствуют" in r for r in rep), text
    assert not any("сторож литералов не применяется" in r for r in rep), text


def test_glossary_indented_code_still_flagged(tmp_path):
    # НЕсрабатывание: у глоссария снят только сторож выносок, отступный код-блок — брак
    p = _card(tmp_path, "glossary.md", "glossary")
    p.write_text(p.read_text(encoding="utf-8")
                 + "\nАбзац перед блоком.\n\n      - ИЛИ \"Черновик\";\n", encoding="utf-8")
    rep, ok = run_check([p], _src(tmp_path))
    assert not ok and any("отступный код-блок" in r for r in rep), "\n".join(rep)


def test_glossary_other_checks_still_apply(tmp_path):
    # НЕсрабатывание: прочие проверки глоссария на месте — потеря title источника брак
    p = _card(tmp_path, "glossary.md", "glossary")
    p.write_text(p.read_text(encoding="utf-8").replace("'[X] Глоссарий'", "'Другое имя'"),
                 encoding="utf-8")
    rep, ok = run_check([p], _src(tmp_path))
    assert not ok, "\n".join(rep)
