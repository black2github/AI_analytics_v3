# tests/test_kitcheck_core.py
"""Ядро прибора kitcheck (рефакторинг 2026-10-17): реестр проверок, находки,
файловый кэш прогона, кэш результатов, примитивы markdown."""
import pytest

from app.scripts.CI.kitcheck import core, fs, md


# ---------------------------------------------------------------- core

def test_run_checks_order_and_verdict_only_from_affecting_checks():
    seen = []

    def mk(name, ok):
        def run(ctx):
            seen.append(name)
            return [f"{name}"], ok
        return run

    checks = [core.Check("a", mk("a", True)),
              core.Check("b", mk("b", False), affects_verdict=False),
              core.Check("c", mk("c", True))]
    lines, ok = core.run_checks(checks, ctx=None)
    assert lines == ["a", "b", "c"] and seen == ["a", "b", "c"]
    assert ok is True                       # «b» вердикт не трогает
    lines, ok = core.run_checks(checks + [core.Check("d", mk("d", False))], None)
    assert ok is False and lines[-1] == "d"


def test_run_checks_skips_not_applicable_and_propagates_exceptions():
    def boom(ctx):
        raise RuntimeError("сбой")
    skipped = core.Check("x", boom, applies=lambda ctx: False)
    assert core.run_checks([skipped], None) == ([], True)
    with pytest.raises(RuntimeError):       # изоляцию сбоя делает сама проверка (_safe)
        core.run_checks([core.Check("y", boom)], None)


def test_finding_render_levels():
    f = [core.Finding(core.WARN, "предупреждение", ("деталь",)), core.Finding(core.INFO, "сведение")]
    lines, ok = core.render(f)
    assert lines == ["⚠ предупреждение", "   деталь", "i сведение"] and ok is True
    assert core.render([core.Finding(core.FAIL, "брак")]) == (["✗ брак"], False)


# ---------------------------------------------------------------- fs

def test_read_text_in_session_equals_path_read_text(tmp_path):
    p = tmp_path / "a.md"
    p.write_bytes("﻿строка 1\r\nстрока 2\rстрока 3\n".encode("utf-8"))
    direct = p.read_text(encoding="utf-8")
    with fs.session():
        assert fs.read_text(p, encoding="utf-8") == direct
        assert fs.read_text(p, encoding="utf-8") == direct      # из кэша
        assert fs.read_bytes(p) == p.read_bytes()


def test_cache_lives_only_inside_session(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("один", encoding="utf-8")
    with fs.session():
        assert fs.read_text(p, encoding="utf-8") == "один"
        p.write_text("два", encoding="utf-8")
        assert fs.read_text(p, encoding="utf-8") == "один"      # прогон read-only: кэш
    assert fs.read_text(p, encoding="utf-8") == "два"           # вне сессии — диск
    assert not fs.active()


def test_strict_decode_error_and_missing_file_same_as_path(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe\xfa")
    with pytest.raises(UnicodeDecodeError):
        bad.read_text(encoding="utf-8")
    with fs.session():
        with pytest.raises(UnicodeDecodeError):
            fs.read_text(bad, encoding="utf-8")
        assert fs.read_text(bad, encoding="utf-8", errors="replace") == \
            bad.read_text(encoding="utf-8", errors="replace")
        with pytest.raises(FileNotFoundError):
            fs.read_text(tmp_path / "нет.md", encoding="utf-8")


def test_memoize_copy_and_exceptions_not_cached():
    calls = []

    @fs.memoize(copy=list)
    def f(x):
        calls.append(x)
        if x == "boom":
            raise ValueError(x)
        return [x]

    assert f("a") == ["a"] and len(calls) == 1       # вне сессии — прямой вызов
    assert f("a") == ["a"] and len(calls) == 2
    with fs.session():
        r1 = f("a"); r1.append("испорчено")
        assert f("a") == ["a"] and len(calls) == 3   # кэш + копия
        for _ in range(2):
            with pytest.raises(ValueError):
                f("boom")
        assert calls.count("boom") == 2              # исключение не кэшируется


# ---------------------------------------------------------------- md

def test_table_cells_and_fences():
    assert md.table_cells("  | a | b |  ") == ["a", "b"]
    assert md.table_cells("| a |") == ["a"]
    assert md.is_fence("```python") and md.is_fence("~~~")
    assert not md.is_fence("~~~", md.FENCE_BACKTICK)


def test_soft_signal_contract():
    """Контракт начала строки: какие строки проверок карточки видны при ✓."""
    for ln in ("предупреждение: нотация …", "[scr-cl-01.2.md] предупреждение: …",
               "полнота ячеек источника: 12/12", "маркер «и т.д.» помилован"):
        assert core.is_soft_signal(ln), ln
    for ln in ("✗ брак", "проверка карточки: x.md", "Предупреждение с большой буквы"):
        assert not core.is_soft_signal(ln), ln
