# tests/test_critic_fence.py
"""critic на общем правиле границ блоков кода kitcheck/fence.py (Р-1 (б), решение
владельца 2026-10-17): вложенность по виду и длине; W4 — закрытие с инфо-строкой;
E10 — незакрытый блок; E5 — маркер поперёк границы блока."""

from app.scripts.CI.critic import lint_text, process_text


def rules(text):
    return [(f.rule, f.line) for f in lint_text(text)]


def test_marker_inside_nested_sample_is_code():
    # ``` внутри ```` — содержимое: маркер в образце — E5, apply/reject его не трогают
    text = "a\n````markdown\n```\n{++ECO-1: x++}\n```\n````\nb\n"
    assert ("E5", 4) in rules(text)
    assert process_text(text, "reject", None) == (text, 0)


def test_markers_outside_nested_sample_processed():
    # НЕсрабатывание: вне образца маркеры обрабатываются как прежде
    text = "a {++ECO-1: x++}\n````markdown\n```\ncode\n```\n````\nb {--ECO-1: y--}\n"
    assert not any(r in ("E5", "E10", "W4") for r, _ in rules(text))
    out, n = process_text(text, "reject", None)
    assert "{++" not in out and "{--" not in out and "b y" in out and "a \n" in out


def test_close_with_info_is_warning_and_tail_processed():
    text = "п\n```text\nкод\n```text\n\n{++ECO-1: хвост++}\n"
    found = rules(text)
    assert ("W4", 2) in found and not any(r == "E10" for r, _ in found)
    assert "{++" not in process_text(text, "reject", None)[0]


def test_unclosed_block_is_error():
    text = "п\n```json\n{\"a\": 1}\n\n{++ECO-1: хвост++}\n"
    assert ("E10", 2) in rules(text)


def test_lone_last_fence_not_error():
    assert not any(r == "E10" for r, _ in rules("п\n```"))


def test_marker_across_block_boundary_is_error():
    text = "п {++ECO-1: начало\n```\nкод++}\n```\nтекст\n"
    assert ("E5", 1) in [(r, ln) for r, ln in rules(text)]


def test_crlf_same_as_lf():
    lf = "a\n````\n```\n{++ECO-1: x++}\n```\n````\nb\n"
    assert rules(lf) == rules(lf.replace("\n", "\r\n"))
