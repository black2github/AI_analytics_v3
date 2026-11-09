# tests/test_gate_oq_close_form.py
"""Пакет П2 ОНБ-В, п. 4 (замечание 77): CORE-20 гейта переноса — строка ⚠ о записях
журнала, закрытых с даты нормы без коммита, тега или «без изменений». Признак — сторож
формы закрытия review_guards (один дом); вердикт гейта не меняется."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
from kitcheck.checks import review_guards as rg  # noqa: E402

from tests.test_transfer_gate import _OQ_CLOSED, make_src  # noqa: E402

AFTER = date.fromordinal(rg.OQ_CLOSE_FORM_SINCE.toordinal() + 2).isoformat()


def _oq(status: str) -> str:
    return _OQ_CLOSED + f"\n## OQ-002. Ещё\n- **Статус:** {status}\n"


def _run(src: Path):
    return tg.run_gate(src, no_validator=True)


def test_closed_without_channel_blocks(tmp_path):
    """Пакет П3 ОНБ-В (решение владельца 2026-11-09): закрытие без канала — ✗ CORE-20, блокер."""
    lines, ready, _ = _run(make_src(tmp_path, oq=_oq(f"закрыт: {AFTER}")))
    assert not ready, "\n".join(lines)
    hit = [ln for ln in lines if ln.startswith("✗ [CORE-20]") and "OQ закрыт без коммита" in ln]
    assert hit and hit[0].endswith(": 1 — OQ-002"), "\n".join(lines)
    assert lines[-1].startswith("ИТОГ: NOT READY")


def test_closed_with_commit_tag_or_no_change_silent(tmp_path):
    for i, st in enumerate((f"закрыт: {AFTER}, a1b2c3d4", f"закрыт: {AFTER}, тег src/OQ-2",
                            f"закрыт: {AFTER}, без изменений: аналитик")):
        lines, ready, _ = _run(make_src(tmp_path / str(i), oq=_oq(st)))
        assert ready and not any("OQ закрыт без коммита" in ln for ln in lines), st


def test_closed_before_norm_date_silent(tmp_path):
    # НЕсрабатывание: прежняя форма закрытия (до даты нормы) не трогается
    lines, _r, _ = _run(make_src(tmp_path, oq=_oq("закрыт 2026-09-17 — решение")))
    assert not any("OQ закрыт без коммита" in ln for ln in lines)


def test_one_home_of_feature(tmp_path):
    # строка гейта — текст сторожа review_guards без маркера, второго признака нет
    src = make_src(tmp_path, oq=_oq(f"закрыт: {AFTER}"))
    expect = rg.check_oq_close_form(src / "open-questions.md")[0][2:]
    lines, _r, _ = _run(src)
    assert f"✗ [CORE-20] {expect}" in lines, "\n".join(lines)
