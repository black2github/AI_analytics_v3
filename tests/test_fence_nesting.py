# tests/test_fence_nesting.py
"""Прибор на правиле kitcheck/fence.py (Р-1 (б), решение владельца 2026-10-17):
вложенный образец ````markdown с ``` внутри — код целиком; блок, не закрытый по
правилам GitLab, — ✗ в карточке и предупреждение в журнале."""

from pathlib import Path

from app.scripts.CI import link_debts as ld
from app.scripts.CI.kitcheck import md
from app.scripts.CI.kitcheck.checks import content
from app.scripts.CI.normalize_tables import check_file

SAMPLE = ("````markdown\n## Назначение\n\n```mermaid\nflowchart\n```\n\n"
          "## Поведение\n\n- шаг\n````\n")


def _make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_nested_sample_does_not_count_as_section():
    # заголовки образца — не разделы карточки
    assert content._h2_keys("# К\n\n" + SAMPLE + "\n## Назначение\n\nтекст\n") == ["назначение"]


def test_heading_inside_inner_block_not_a_section():
    # прежний переключатель закрывал внешний блок на внутреннем ограждении:
    # СОДЕРЖИМОЕ внутреннего блока выходило в текст карточки, и «## Поведение»
    # из образца засчитывался разделом (маскировка отсутствия раздела)
    text = ("# К\n\n````markdown\n```markdown\n## Поведение\n```\n````\n\n"
            "## Назначение\n\nтекст\n")
    assert content._h2_keys(text) == ["назначение"]


def test_helpers_on_nested_sample():
    text = "до\n" + SAMPLE + "после [ссылка](x.md)"
    out = md.blank_code(text)
    assert "Поведение" not in out and "flowchart" not in out
    assert out.startswith("до\n") and out.endswith("после [ссылка](x.md)")
    blocks = md.code_blocks(text)
    assert len(blocks) == 1 and "## Поведение" in blocks[0] and "```mermaid" in blocks[0]


def test_card_close_with_info_is_defect(tmp_path):
    p = _make(tmp_path / "c.md", "# К\n\n```text\nA - 1\n```text\n\n## Примеры\n\nтекст\n")
    rep, ok = check_file(p)
    assert not ok
    assert any("строка 3: блок кода закрыт ограждением с инфо-строкой (строка 5)" in ln
               for ln in rep), rep


def test_card_unclosed_block_is_defect(tmp_path):
    p = _make(tmp_path / "c.md", "# К\n\n```json\n{\"a\": 1}\n\nхвост карточки\n")
    rep, ok = check_file(p)
    assert not ok and any("строка 3: блок кода не закрыт до конца файла" in ln for ln in rep), rep


def test_card_nested_sample_and_lone_last_fence_silent(tmp_path):
    # НЕсрабатывание: корректная вложенность и голое ограждение последней строкой
    p = _make(tmp_path / "c.md", "# К\n\n" + SAMPLE + "\nтекст\n")
    rep, ok = check_file(p)
    assert not any("блок кода" in ln and "GitLab" in ln for ln in rep), rep
    p2 = _make(tmp_path / "d.md", "# К\n\nтекст\n```")
    rep2, ok2 = check_file(p2)
    assert not any("блок кода" in ln and "GitLab" in ln for ln in rep2), rep2


def test_journal_unclosed_block_is_warning(tmp_path):
    p = _make(tmp_path / "feedback.md",
              "# Замечания\n\n## FB-01 — 2026-10-01 — тема\n\n```powershell\ngit pull\n\n"
              "## FB-02 — 2026-10-02 — тема\n")
    rep, ok = ld.check_feedback_order(p)
    assert ok, rep
    assert any(ln.startswith("предупреждение: feedback: строка 5 — блок кода не закрыт")
               for ln in rep), rep


def test_journal_without_issues_unchanged(tmp_path):
    p = _make(tmp_path / "open-questions.md",
              "# Вопросы\n\n````markdown\n## OQ-09 — образец\n```\nx\n```\n````\n\n"
              "## OQ-01 — 2026-10-01 — тема\n")
    rep, ok = ld.check_oq_order(p)
    assert ok and rep == ["open-questions: порядок реестра append-only соблюдён (1 записей) ✓"], rep
