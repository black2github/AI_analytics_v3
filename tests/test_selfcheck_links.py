# tests/test_selfcheck_links.py
"""ПР-06 (разбор замечаний ОНБ-В): якоря ссылок по правилам GitLab и
упоминание конкретной карточки без ID — предупреждения."""
from pathlib import Path

from app.scripts.CI import selfcheck


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_gitlab_slug():
    assert selfcheck.gitlab_slug("EV-3. Ввод ФИО / 4 цифр") == "ev-3-ввод-фио-4-цифр"
    assert selfcheck.gitlab_slug("B-1. «Фильтры» (XS)") == "b-1-фильтры-xs"


def test_bad_anchor_warned_good_anchor_and_duplicate_heading_ok(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/scr.md", "# Э\n\n### EV-3. Ввод ФИО / 4 цифр\n\n### Итог\n\n### Итог\n\n"
      "[EV-3](#ev-3-ввод-фио-4-цифр) [итог-2](#итог-1) [плохо](#ev-3-ввод-фио--4-цифр)\n")
    rep = selfcheck.check_link_anchors_and_ids(docs)
    assert rep and rep[0].startswith("⚠ якоря ссылок: 1 не совпадают"), rep
    assert any("#ev-3-ввод-фио--4-цифр" in r for r in rep), rep


def test_card_mention_without_id_warned_navigation_not(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/contract-call/external/call-ext-001-x.md", "# В\n")
    w(docs / "srs/control/cards-a.md", "# К\n\n### CTL-001. Проверка ИНН\n")
    w(docs / "srs/platform-functions.md", "# П\n\n### PLT-002. Проверка ЭП\n")
    w(docs / "srs/function/fun-cl-01.md",
      "# Ф\n\n[Метод выпуска](../contract-call/external/call-ext-001-x.md); "
      "[CALL-EXT-001 Метод выпуска](../contract-call/external/call-ext-001-x.md); "
      "[Проверка ИНН](../control/cards-a.md#ctl-001-проверка-инн); "
      "[PLT-002 Проверка ЭП](../platform-functions.md#plt-002-проверка-эп); "
      "[платформенные функции](../platform-functions.md)\n")
    w(docs / "README.md", "# К\n\n[`srs/contract-call/external/call-ext-001-x.md`](srs/contract-call/external/call-ext-001-x.md)\n")
    rep = selfcheck.check_link_anchors_and_ids(docs)
    no_id = [r for r in rep if "без ID" in r]
    assert no_id and "без ID в тексте: 2" in no_id[0], rep
    assert not any("якоря ссылок" in r for r in rep), rep
