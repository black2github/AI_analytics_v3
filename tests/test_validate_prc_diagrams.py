# tests/test_validate_prc_diagrams.py
"""validate_prc_diagrams: пустые if/else-развилки PlantUML activity в карточках процессов
(P0 stub_empty_if). Дом утилиты — analyzer, канон — копия (решение владельца 2026-11-01)."""
import sys

import pytest

from app.scripts.CI import validate_prc_diagrams as vpd


@pytest.mark.parametrize("name, body, want", [
    # PROC-032 КК (8fddecb8): развилка внутри repeat, endif с отступом, действие в else — не пустая
    ("repeat_indented_else_action",
     "repeat\n  :12 Обработать ошибку;\n  if (13) then (повторить выгрузку)\n"
     "  else (закрыть ДС вручную)\n    :7 Изменить статус;\n    stop\n  endif\n"
     "repeat while (повторить?) is (да)\n", []),
    # НЕсрабатывание правки (27): обе ветки пусты, с отступом — P0
    ("indented_both_empty",
     "repeat\n  if (13) then (да)\n  else (нет)\n  endif\nrepeat while (x?)\n",
     ["stub_empty_if: if (13)"]),
    # обе ветки пусты, без отступа — P0
    ("flat_both_empty", "if (1) then (да)\nelse (нет)\nendif\n", ["stub_empty_if: if (1)"]),
    # else только с комментарием — P0
    ("indented_else_comment_only",
     "repeat\n  if (2) then (да)\n  else (нет)\n    ' пусто\n  endif\nrepeat while (x?)\n",
     ["stub_empty_if: if (2)"]),
    # плоская развилка с действием в else — не пустая
    ("flat_else_action", "if (3) then (да)\nelse (нет)\n:действие;\nendif\n", []),
])
def test_find_stub_empty_ifs(name, body, want):
    assert vpd.find_stub_empty_ifs(body) == want, name


def _proc(body: str) -> str:
    return ("---\nid: PROC-001\ntitle: 'Процесс'\ntype: process\n---\n\n# PROC-001. Процесс\n\n"
            "```plantuml\n@startuml\nskinparam ActivityBackgroundColor #FFF\n"
            f"skinparam ActivityBorderColor #000\nstart\n{body}stop\n@enduml\n```\n")


def test_main_smoke(tmp_path, monkeypatch):
    # публичная точка входа: --docs/--out, отчёт и код выхода (2 — есть P0, 0 — нет)
    docs = tmp_path / "docs"
    good = docs / "srs" / "bc" / "process" / "proc-001-good.md"
    good.parent.mkdir(parents=True)
    good.write_text(_proc("repeat\n  if (13) then (повторить)\n  else (завершить)\n"
                          "    :Закрыть заявку;\n  endif\nrepeat while (повторить?)\n"),
                    encoding="utf-8")
    out = tmp_path / "rep.md"
    monkeypatch.setattr(sys, "argv", ["validate_prc_diagrams.py", "--docs", str(docs),
                                      "--out", str(out)])
    assert vpd.main() == 0
    text = out.read_text(encoding="utf-8")
    assert "| P0 | 0 |" in text and "| Вердикт | PASS |" in text, text

    (docs / "srs" / "bc" / "process" / "proc-002-bad.md").write_text(
        _proc("if (1) then (да)\nelse (нет)\nendif\n"), encoding="utf-8")
    assert vpd.main() == 2
    text = out.read_text(encoding="utf-8")
    assert "`stub_empty_if` | `srs/bc/process/proc-002-bad.md` | stub_empty_if: if (1)" in text, text
