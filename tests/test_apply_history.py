# tests/test_apply_history.py
#
# Автоматизация этапа 4 (летопись): позадачное вливание истории (2026-08-10).
# Сквозной сценарий на настоящем временном git-репозитории.

import subprocess
import sys
from pathlib import Path

import pytest

from app.scripts.apply_history import main, read_task_list


def _git(repo: Path, *args):
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path):
    """git-репозиторий с raw-архивом: один файл с правками двух задач."""
    r = tmp_path / "src-repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "стр.md").write_text(
        "База.\n"
        "{++GBO-1: правка первой задачи++}\n"
        "{++GBO-2: правка второй задачи++}\n",
        encoding="utf-8")
    (r / "README.md").write_text("init\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r, raw


class TestReadTaskList:
    def test_bare_ids_and_command_lines(self, tmp_path):
        f = tmp_path / "tasks.txt"
        f.write_text("GBO-1\n\n# комментарий\n"
                     "run-critic.bat apply GBO-2 --path .\n"
                     "REM порядок уточните: run-critic.bat apply GBO-9 --path .\n"
                     "GBO-1\n", encoding="utf-8")
        ids, warnings = read_task_list(f)
        assert ids == ["GBO-1", "GBO-2"]          # REM пропущен, дубль отброшен
        assert any("дубль" in w for w in warnings)


class TestEndToEnd:
    def _tasks_file(self, tmp_path, ids):
        f = tmp_path / "tasks.txt"
        f.write_text("\n".join(ids) + "\n", encoding="utf-8")
        return f

    def test_two_slices_commits_tags_and_content(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)                      # critic запускается из репо
        rc = main([str(raw), str(r), str(self._tasks_file(tmp_path, ["GBO-1", "GBO-2"])),
                   "--target-subdir", "chron"])
        assert rc == 0
        # два коммита срезов + init
        log = _git(r, "log", "--oneline").stdout
        assert "GBO-1" in log and "GBO-2" in log
        # теги
        tags = _git(r, "tag").stdout.split()
        assert "src/GBO-1" in tags and "src/GBO-2" in tags
        # срез 1: только первая задача принята, вторая отброшена
        s1 = _git(r, "show", "src/GBO-1:chron/стр.md").stdout
        assert "правка первой задачи" in s1
        assert "правка второй задачи" not in s1
        assert "{++" not in s1                    # маркеров не осталось
        # срез 2: обе приняты
        s2 = _git(r, "show", "src/GBO-2:chron/стр.md").stdout
        assert "правка первой задачи" in s2 and "правка второй задачи" in s2

    def test_existing_tag_stops_before_changes(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        _git(r, "tag", "src/GBO-1")
        head = _git(r, "rev-parse", "HEAD").stdout.strip()
        rc = main([str(raw), str(r), str(self._tasks_file(tmp_path, ["GBO-1"])),
                   "--target-subdir", "chron"])
        assert rc == 2                            # preflight: тег существует
        assert _git(r, "rev-parse", "HEAD").stdout.strip() == head   # ничего не внесено

    def test_dirty_tree_stops(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        (r / "README.md").write_text("dirty\n", encoding="utf-8")
        rc = main([str(raw), str(r), str(self._tasks_file(tmp_path, ["GBO-1"])),
                   "--target-subdir", "chron"])
        assert rc == 2

    def test_dry_run_changes_nothing(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        rc = main([str(raw), str(r), str(self._tasks_file(tmp_path, ["GBO-1"])),
                   "--target-subdir", "chron", "--dry-run"])
        assert rc == 0
        assert not (r / "chron").exists()
        assert "src/GBO-1" not in _git(r, "tag").stdout

    def test_empty_slice_allowed_with_tag(self, repo, tmp_path, monkeypatch):
        # задача без правок в архиве: срез пуст, но коммит и тег существуют
        r, raw = repo
        monkeypatch.chdir(r)
        rc = main([str(raw), str(r),
                   str(self._tasks_file(tmp_path, ["GBO-1", "GBO-7", "GBO-2"])),
                   "--target-subdir", "chron"])
        assert rc == 0
        assert "src/GBO-7" in _git(r, "tag").stdout
        # содержимое среза GBO-7 совпадает со срезом GBO-1 (задача пустая)
        a = _git(r, "show", "src/GBO-1:chron/стр.md").stdout
        b = _git(r, "show", "src/GBO-7:chron/стр.md").stdout
        assert a == b
