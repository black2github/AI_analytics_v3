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


def test_auto_reason_from_canon_log(tmp_path):
    # --reason опционален: основание собирается из тем принимаемых
    # коммитов канона (git log old..new)
    canon = make_canon(tmp_path)
    old = _git(canon, "rev-parse", "--short", "HEAD")
    (canon / "f.txt").write_text("y", encoding="utf-8")
    _git(canon, "add", "-A")
    _git(canon, "commit", "-q", "-m", "П-99: тестовая калибровка")
    src = make_src(tmp_path, f"| **Срез канона** | `{old}` |\n")
    msg, ok = accept(src / "README.md", canon)
    assert ok, msg
    last = _git(src, "log", "-1", "--format=%s")
    assert "принято из канона" in last
    assert "П-99: тестовая калибровка" in last


def test_auto_reason_fallback_when_no_range(tmp_path):
    # строки не было → диапазона нет → фолбэк с датой коммита канона
    canon = make_canon(tmp_path)
    src = make_src(tmp_path)
    msg, ok = accept(src / "README.md", canon)
    assert ok, msg
    last = _git(src, "log", "-1", "--format=%s")
    assert "обновление канона до" in last


# ---------------------------------------------------------------- дельта норм при приёме среза

def _canon_with_norms(tmp_path: Path) -> Path:
    canon = tmp_path / "canon"
    make_repo(canon)
    (canon / "_meta/templates").mkdir(parents=True)
    (canon / "_meta/skills").mkdir(parents=True)
    (canon / "_meta/tools").mkdir(parents=True)
    (canon / "_meta/templates/controls.md").write_text(
        "# Шаблон\n\n## Поле «Сообщение об ошибке»\n\nтекст\n\n## Чек-лист\n\n7. со способом отображения\n",
        encoding="utf-8")
    (canon / "_meta/skills/create-artifact.md").write_text("# Скилл\n\n## Дерево метода\n\n1. пункт\n",
                                                           encoding="utf-8")
    (canon / "_meta/tools/selfcheck.py").write_text("x = 1\n", encoding="utf-8")
    (canon / "other.md").write_text("не норма\n", encoding="utf-8")
    _git(canon, "add", "-A")
    _git(canon, "commit", "-q", "-m", "init")
    return canon


def test_norm_delta_lists_files_sections_and_tools(tmp_path):
    from app.scripts.CI.accept_canon import norm_delta
    canon = _canon_with_norms(tmp_path)
    old = _git(canon, "rev-parse", "--short", "HEAD")
    p = canon / "_meta/templates/controls.md"
    p.write_text(p.read_text(encoding="utf-8").replace("7. со способом отображения", "7. без способа показа"),
                 encoding="utf-8")
    s = canon / "_meta/skills/create-artifact.md"
    s.write_text(s.read_text(encoding="utf-8") + "2. новый пункт\n", encoding="utf-8")
    (canon / "_meta/tools/selfcheck.py").write_text("x = 2\n", encoding="utf-8")
    (canon / "other.md").write_text("изменён, но не норма\n", encoding="utf-8")
    _git(canon, "add", "-A")
    _git(canon, "commit", "-q", "-m", "нормы")
    new = _git(canon, "rev-parse", "--short", "HEAD")
    out = norm_delta(canon, old, new)
    assert out[0].startswith(f"Дельта норм {old}→{new}")
    assert "  _meta/templates/controls.md — разделы: «Чек-лист»" in out
    assert "  _meta/skills/create-artifact.md — разделы: «Дерево метода»" in out
    assert "  прибор: 1 файлов" in out
    assert not any("other.md" in ln for ln in out)


def test_norm_delta_empty(tmp_path):
    from app.scripts.CI.accept_canon import norm_delta
    canon = _canon_with_norms(tmp_path)
    old = _git(canon, "rev-parse", "--short", "HEAD")
    (canon / "other.md").write_text("только не норма\n", encoding="utf-8")
    _git(canon, "add", "-A")
    _git(canon, "commit", "-q", "-m", "прочее")
    new = _git(canon, "rev-parse", "--short", "HEAD")
    assert norm_delta(canon, old, new) == [f"дельта норм {old}→{new} пуста"]


def test_accept_prints_norm_delta(tmp_path):
    canon = _canon_with_norms(tmp_path)
    old = _git(canon, "rev-parse", "--short", "HEAD")
    s = canon / "_meta/skills/create-artifact.md"
    s.write_text(s.read_text(encoding="utf-8") + "2. новый пункт\n", encoding="utf-8")
    _git(canon, "add", "-A")
    _git(canon, "commit", "-q", "-m", "скилл")
    src = make_src(tmp_path, f"| **Срез канона** | `{old}` |\n")
    msg, ok = accept(src / "README.md", canon)
    assert ok, msg
    lines = msg.splitlines()
    assert lines[0].startswith("✓ срез канона:") and lines[1].startswith("Дельта норм")
    assert "  _meta/skills/create-artifact.md — разделы: «Дерево метода»" in lines
