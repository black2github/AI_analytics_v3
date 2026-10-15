# tests/test_selfcheck_call_hint.py
"""ЗК-12 ОНБ-В: у карточки вызова с page_id вне выгрузки прибор подсказывает,
чьи страницы — источник карточки (первым — страница этого сервиса)."""
from pathlib import Path

from app.scripts.CI import selfcheck
from tests.test_selfcheck import card, make, make_matrix, source


def test_call_card_missing_source_gets_hint(tmp_path):
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/contract-call/internal/call-int-01.md",
         card("[X] Вызов", "999999").replace("type: function", "type: contract-call"))
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    report, _ok = selfcheck.run(docs, srcs)
    bad = [ln for ln in report if "НЕ НАЙДЕН" in ln]
    assert len(bad) == 1 and "call-int-01.md" in bad[0]
    assert "карточка вызова: первым — page_id страницы ЭТОГО сервиса" in bad[0], bad[0]
