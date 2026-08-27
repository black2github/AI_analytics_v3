# tests/test_accept_canon.py
"""Утилита владельца accept_canon: принять срез канона одной командой —
правка строки профиля + точечный коммит; ограничители против грязной
вехи и угадывания."""

import subprocess
from pathlib import Path

from app.scripts.CI.accept_canon import accept


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def make_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "t@t")


def make_canon(tmp_path: Path) -> Path:
    canon = tmp_path / "canon"
    make_repo(canon)
    (canon / "f.txt").write_text("x", encoding="utf-8")
    _git(canon, "add", "-A")
    _git(canon, "commit", "-q", "-m", "init")
    return canon


def make_src(tmp_path: Path, cut_line: str = "") -> Path:
    src = tmp_path / "src"
    make_repo(src)
    (src / "README.md").write_text(
        "# Профиль\n\n| Поле | Значение |\n|---|---|\n"
        "| **service-id** | `CC` |\n" + cut_line,
        encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "init")
    return src


def test_updates_line_and_commits(tmp_path):
    canon = make_canon(tmp_path)
    src = make_src(tmp_path, "| **Срез канона** | `0000000` |\n")
    msg, ok = accept(src / "README.md", canon, "тест")
    assert ok, msg
    head = _git(canon, "rev-parse", "--short", "HEAD")
    assert head in (src / "README.md").read_text(encoding="utf-8")
    last = _git(src, "log", "-1", "--format=%s")
    assert last.startswith(f"Срез канона обновлён на {head}: тест")


def test_idempotent_no_empty_commit(tmp_path):
    canon = make_canon(tmp_path)
    head = _git(canon, "rev-parse", "--short", "HEAD")
    src = make_src(tmp_path, f"| **Срез канона** | `{head}` |\n")
    n_before = _git(src, "rev-list", "--count", "HEAD")
    msg, ok = accept(src / "README.md", canon, "тест")
    assert ok and "уже актуально" in msg
    assert _git(src, "rev-list", "--count", "HEAD") == n_before


def test_inserts_row_when_missing(tmp_path):
    canon = make_canon(tmp_path)
    src = make_src(tmp_path)
    msg, ok = accept(src / "README.md", canon, "первичная фиксация")
    assert ok, msg
    text = (src / "README.md").read_text(encoding="utf-8")
    assert "Срез канона" in text
    # строка вставлена сразу после service-id
    assert text.index("service-id") < text.index("Срез канона")


def test_dirty_profile_refused(tmp_path):
    # ограничитель: незакоммиченные правки профиля — отказ, чужое
    # в веху не захватывается
    canon = make_canon(tmp_path)
    src = make_src(tmp_path, "| **Срез канона** | `0000000` |\n")
    p = src / "README.md"
    p.write_text(p.read_text(encoding="utf-8") + "\nправка\n",
                 encoding="utf-8")
    _msg, ok = accept(p, canon, "тест")
    assert not ok


def test_non_repo_canon_refused(tmp_path):
    src = make_src(tmp_path, "| **Срез канона** | `0000000` |\n")
    msg, ok = accept(src / "README.md", tmp_path / "nowhere", "тест")
    assert not ok and "HEAD канона" in msg
