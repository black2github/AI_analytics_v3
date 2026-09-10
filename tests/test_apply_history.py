# tests/test_apply_history.py
#
# Автоматизация этапа 4 (хронология): позадачное вливание истории (2026-08-10).
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

    def test_existing_tag_means_introduced(self, repo, tmp_path, monkeypatch):
        # тег на ветке = задача уже введена: пропуск, ввода нет; остаётся только
        # событие «выгрузка» (целевого каталога в init не было → коммит ПРОМ без тега)
        r, raw = repo
        monkeypatch.chdir(r)
        _git(r, "tag", "src/GBO-1")
        rc = main([str(raw), str(r), str(self._tasks_file(tmp_path, ["GBO-1"])),
                   "--target-subdir", "chron"])
        assert rc == 0
        assert _git(r, "log", "-1", "--format=%s").stdout.startswith("ПРОМ-срез")  # первый сбор
        assert _git(r, "tag").stdout.split() == ["src/GBO-1"]          # новых тегов нет
        # повтор без изменений архива: делать нечего — код 2, HEAD на месте
        head = _git(r, "rev-parse", "HEAD").stdout.strip()
        rc = main([str(raw), str(r), "--target-subdir", "chron"])        # без файла задач
        assert rc == 2 and _git(r, "rev-parse", "HEAD").stdout.strip() == head

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


class TestAccumulatedTree:
    """
    Накопительное дерево (2026-09-07): каждая задача применяется один раз в дерево
    «архив + принятые», срез — копия с reject-all. Главное свойство, которое здесь
    закрепляется: срезы ПОБАЙТНО совпадают с пересборкой из архива, где на каждой
    итерации заново применяются все принятые. Разница только в работе: линейно
    против квадратично (на 148 задачах — 148 проходов apply вместо 11 026).
    """

    def _repo_with_tasks(self, tmp_path, name):
        """Репозиторий и архив с тремя задачами, у которых правки на разных страницах."""
        r = tmp_path / name
        r.mkdir()
        _git(r, "init", "-q")
        _git(r, "config", "user.email", "t@t")
        _git(r, "config", "user.name", "t")
        raw = tmp_path / (name + "-raw")
        raw.mkdir()
        (raw / "а.md").write_text(
            "---\nstatus: draft\n---\n\nБаза.\n"
            "{++GBO-1: правка первой++}\n{--GBO-2: удалено второй--}\n",
            encoding="utf-8")
        (raw / "б.md").write_text(
            "---\nstatus: draft\nunapproved_jira: GBO-3\n---\n\n"
            "Страница целиком третьей задачи.\n",
            encoding="utf-8")
        (raw / "в.md").write_text(
            "| текст | status |\n| --- | --- |\n| строка второй | +GBO-2 |\n"
            "| строка первой | +GBO-1 |\n",
            encoding="utf-8")
        (r / "README.md").write_text("init\n", encoding="utf-8")
        _git(r, "add", "-A")
        _git(r, "commit", "-q", "-m", "init")
        return r, raw

    def _tasks(self, tmp_path, name):
        f = tmp_path / (name + "-tasks.txt")
        f.write_text("GBO-1\nGBO-2\nGBO-3\n", encoding="utf-8")
        return f

    def _slices(self, r):
        """Содержимое всех файлов среза по каждому тегу — для побайтного сравнения."""
        out = {}
        for tag in _git(r, "tag").stdout.split():
            files = _git(r, "ls-tree", "-r", "--name-only", tag).stdout.split("\n")
            out[tag] = {f: _git(r, "show", f"{tag}:{f}").stdout
                        for f in files if f.startswith("chron/")}
        return out

    def test_slices_identical_to_refill_method(self, tmp_path, monkeypatch):
        results = {}
        for name, extra in (("refill", ["--refill-each"]), ("accum", [])):
            r, raw = self._repo_with_tasks(tmp_path, name)
            monkeypatch.chdir(r)
            rc = main([str(raw), str(r), str(self._tasks(tmp_path, name)),
                       "--target-subdir", "chron", *extra])
            assert rc == 0, name
            results[name] = self._slices(r)
        assert set(results["accum"]) == {"src/GBO-1", "src/GBO-2", "src/GBO-3"}
        assert results["accum"] == results["refill"]       # побайтно, по каждому тегу

    def test_slice_semantics_hold(self, tmp_path, monkeypatch):
        r, raw = self._repo_with_tasks(tmp_path, "sem")
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, "sem")),
                     "--target-subdir", "chron"]) == 0
        s1 = _git(r, "show", "src/GBO-1:chron/а.md").stdout
        assert "правка первой" in s1 and "удалено второй" in s1     # удаление ещё не принято
        s2 = _git(r, "show", "src/GBO-2:chron/а.md").stdout
        assert "удалено второй" not in s2                            # принято — строки нет
        assert "{" not in s2
        assert "Страница целиком" not in _git(r, "show", "src/GBO-2:chron/б.md").stdout
        assert "Страница целиком" in _git(r, "show", "src/GBO-3:chron/б.md").stdout

    def test_working_tree_clean_between_slices(self, tmp_path, monkeypatch):
        """Накопительное дерево живёт вне репозитория — хронология не грязнит дерево."""
        r, raw = self._repo_with_tasks(tmp_path, "clean")
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, "clean")),
                     "--target-subdir", "chron"]) == 0
        assert _git(r, "status", "--porcelain").stdout.strip() == ""
        assert not any(p.name.startswith("base") for p in r.iterdir())

    def test_base_dir_used_and_cleaned(self, tmp_path, monkeypatch):
        """--base-dir: дерево кладётся туда, куда указано, и убирается после прогона."""
        r, raw = self._repo_with_tasks(tmp_path, "bd")
        base_dir = tmp_path / "fast-disk"
        base_dir.mkdir()
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, "bd")),
                     "--target-subdir", "chron", "--base-dir", str(base_dir)]) == 0
        assert not (base_dir / "onix-history-base").exists()          # прибрано
        assert _git(r, "tag").stdout.split() == ["src/GBO-1", "src/GBO-2", "src/GBO-3"]

    def test_base_dir_inside_repo_refused(self, tmp_path, monkeypatch, capsys):
        """Дерево внутри репозитория грязнило бы хронология — отказ до первого изменения."""
        r, raw = self._repo_with_tasks(tmp_path, "inside")
        monkeypatch.chdir(r)
        rc = main([str(raw), str(r), str(self._tasks(tmp_path, "inside")),
                   "--target-subdir", "chron", "--base-dir", str(r / "tmp")])
        assert rc == 2
        assert "внутри репозитория" in capsys.readouterr().err
        assert _git(r, "tag").stdout.strip() == ""


class TestServiceFilesAndCommitPrefix:
    """Модель «master = ПРОМ» (2026-09-10): служебные файлы экспортёра не
    попадают в целевой каталог; сообщение коммита — ввод, а не хронология."""

    def test_refill_target_skips_service_files(self, tmp_path):
        from app.scripts.apply_history import refill_target
        raw = tmp_path / "raw"; raw.mkdir()
        (raw / "стр.md").write_text("# страница\n", encoding="utf-8")
        (raw / "migration-manifest.yaml").write_text("x: 1\n", encoding="utf-8")
        (raw / "migration-apply-order.md").write_text("# порядок\n", encoding="utf-8")
        sub = raw / "Раздел"; sub.mkdir()
        (sub / "migration-colors-report.md").write_text("# отчёт\n", encoding="utf-8")
        (sub / "вложенная.md").write_text("# в\n", encoding="utf-8")
        target = tmp_path / "confluence"
        refill_target(raw, target)
        got = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
        assert got == ["Раздел/вложенная.md", "стр.md"]

    def test_refill_target_keeps_ordinary_files(self, tmp_path):
        # НЕсрабатывание: обычные файлы с похожими именами не режутся
        from app.scripts.apply_history import refill_target
        raw = tmp_path / "raw"; raw.mkdir()
        (raw / "миграция-карт.md").write_text("# ок\n", encoding="utf-8")
        (raw / "img").mkdir(); (raw / "img" / "a.png").write_bytes(b"x")
        target = tmp_path / "confluence"
        refill_target(raw, target)
        assert (target / "миграция-карт.md").exists()
        assert (target / "img" / "a.png").exists()

    def test_commit_message_default_is_intro(self):
        from app.scripts.apply_history import commit_message, DEFAULT_COMMIT_PREFIX
        m = commit_message(DEFAULT_COMMIT_PREFIX, "GBO-1", 3)
        assert m.startswith("Ввод в эксплуатацию: GBO-1")
        assert "3 ранее принятых" in m

    def test_commit_message_archive_prefix(self):
        from app.scripts.apply_history import commit_message
        assert commit_message("Срез хронологии", "GBO-2", 0).startswith("Срез хронологии: GBO-2")


class TestPriorFromTags:
    """Модель «master = ПРОМ» (2026-09-10): введённые ранее задачи скрипт берёт из
    тегов ветки, файл задач содержит только вводимые; порядок ввода произвольный."""

    def _tasks(self, tmp_path, ids, name="t"):
        f = tmp_path / f"{name}.txt"
        f.write_text("\n".join(ids) + "\n", encoding="utf-8")
        return f

    @pytest.mark.parametrize("extra", [[], ["--refill-each"]])
    def test_second_intro_builds_on_prior_tags(self, repo, tmp_path, monkeypatch, extra):
        r, raw = repo
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "a")),
                     "--target-subdir", "chron", *extra]) == 0
        # второй ввод: в файле только новая задача
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-2"], "b")),
                     "--target-subdir", "chron", *extra]) == 0
        s2 = _git(r, "show", "src/GBO-2:chron/стр.md").stdout
        assert "правка первой задачи" in s2 and "правка второй задачи" in s2
        assert "1 ранее принятых" in _git(r, "log", "-1", "--format=%s").stdout
        assert sorted(_git(r, "tag").stdout.split()) == ["src/GBO-1", "src/GBO-2"]

    def test_prior_order_is_branch_order_not_alphabetic(self, repo, tmp_path, monkeypatch):
        from app.scripts.apply_history import introduced_tasks
        r, raw = repo
        monkeypatch.chdir(r)
        _git(r, "tag", "src/PROM")                      # не задача — не считается
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-2"], "a")),
                     "--target-subdir", "chron"]) == 0
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "b")),
                     "--target-subdir", "chron"]) == 0
        assert introduced_tasks(r, "src/") == ["GBO-2", "GBO-1"]

    def test_already_introduced_in_list_skipped_with_warning(self, repo, tmp_path,
                                                             monkeypatch, capsys):
        r, raw = repo
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "a")),
                     "--target-subdir", "chron"]) == 0
        rc = main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1", "GBO-2"], "b")),
                   "--target-subdir", "chron"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "GBO-1 уже введена" in err
        assert "src/GBO-2" in _git(r, "tag").stdout
        # GBO-1 второй раз не коммитился: init + ПРОМ (выгрузка) + два ввода
        assert len(_git(r, "rev-list", "HEAD").stdout.split()) == 4

    def test_tag_outside_branch_is_error(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        _git(r, "checkout", "-q", "-b", "other")
        (r / "x.md").write_text("x\n", encoding="utf-8")
        _git(r, "add", "x.md"); _git(r, "commit", "-q", "-m", "other")
        _git(r, "tag", "src/GBO-1")
        _git(r, "checkout", "-q", "master") if _git(r, "rev-parse", "--verify", "-q", "master").returncode == 0 \
            else _git(r, "checkout", "-q", "main")
        head = _git(r, "rev-parse", "HEAD").stdout.strip()
        rc = main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"])),
                   "--target-subdir", "chron"])
        assert rc == 2                                   # тег занят, но не на ветке
        assert _git(r, "rev-parse", "HEAD").stdout.strip() == head

    def test_dry_run_runs_preflight_and_shows_prior(self, repo, tmp_path, monkeypatch, capsys):
        r, raw = repo
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "a")),
                     "--target-subdir", "chron"]) == 0
        rc = main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-2"], "b")),
                   "--target-subdir", "chron", "--dry-run"])
        err = capsys.readouterr().err
        assert rc == 0 and "введено ранее" in err and "GBO-1" in err
        assert "поверх ПРОМ + 1 ранее принятых" in err
        # грязное дерево: dry-run сообщает об ошибке preflight и возвращает 2
        (r / "README.md").write_text("dirty\n", encoding="utf-8")
        rc = main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-2"], "c")),
                   "--target-subdir", "chron", "--dry-run"])
        assert rc == 2 and "preflight" in capsys.readouterr().err
        assert "src/GBO-2" not in _git(r, "tag").stdout


class TestEventChain:
    """Цепочка событий (2026-09-10): новая выгрузка → коммит «Выгрузка» перед
    новыми задачами; хвост — по манифесту архива; пустой ввод — с причиной."""

    def _tasks(self, tmp_path, ids, name="t"):
        f = tmp_path / f"{name}.txt"
        f.write_text("\n".join(ids) + "\n", encoding="utf-8")
        return f

    @pytest.mark.parametrize("extra", [[], ["--refill-each"]])
    def test_new_export_gets_own_commit_before_new_task(self, repo, tmp_path,
                                                        monkeypatch, extra):
        r, raw = repo
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "a")),
                     "--target-subdir", "chron", *extra]) == 0
        # новая выгрузка: чёрный текст изменился и появилась задача GBO-3
        (raw / "стр.md").write_text(
            "База (уточнена выгрузкой).\n"
            "{++GBO-1: правка первой задачи++}\n"
            "{++GBO-2: правка второй задачи++}\n"
            "{++GBO-3: правка третьей++}\n", encoding="utf-8")
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-3"], "b")),
                     "--target-subdir", "chron", *extra]) == 0
        subjects = _git(r, "log", "--format=%s", "-3").stdout.strip().split("\n")
        assert subjects[0].startswith("Ввод в эксплуатацию: GBO-3")
        assert subjects[1].startswith("Выгрузка: архив обновлён")
        assert "ранее принятых: 1" in subjects[1]
        # дифф коммита задачи — только её строка; механика выгрузки — в своём коммите
        d = _git(r, "diff", "-U0", "src/GBO-3~1", "src/GBO-3", "--", "chron").stdout
        assert "правка третьей" in d and "уточнена выгрузкой" not in d
        d0 = _git(r, "diff", "-U0", "src/GBO-3~2", "src/GBO-3~1", "--", "chron").stdout
        assert "уточнена выгрузкой" in d0
        assert "src/" not in _git(r, "tag", "--points-at", "src/GBO-3~1").stdout  # без тега

    def test_unchanged_export_makes_no_refresh_commit(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "a")),
                     "--target-subdir", "chron"]) == 0
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-2"], "b")),
                     "--target-subdir", "chron"]) == 0
        subjects = _git(r, "log", "--format=%s").stdout.strip().split("\n")
        # ровно один коммит выгрузки — начальный ПРОМ (целевого каталога в init не
        # было); между вводами архив не менялся, второго нет
        assert [x.startswith("ПРОМ-срез") for x in subjects] == [False, False, True, False]
        assert not any(x.startswith("Выгрузка") for x in subjects)
        assert len(subjects) == 4

    def test_tail_from_manifest(self, repo, tmp_path, monkeypatch, capsys):
        r, raw = repo
        monkeypatch.chdir(r)
        (raw / "migration-manifest.yaml").write_text(
            "migrated_at: '2026-09-10'\nservice: x\ntasks:\n"
            "  GBO-1:\n    color: red\n  GBO-2:\n    color: blue\n  GBO-9:\n    color: g\n",
            encoding="utf-8")
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "a")),
                     "--target-subdir", "chron"]) == 0
        err = capsys.readouterr().err
        assert "не введено (по манифесту архива): 2 из 3" in err
        assert "GBO-2, GBO-9" in err
        assert not (r / "chron" / "migration-manifest.yaml").exists()   # служебный — не в срезе

    def test_empty_intro_explains_foreign_flag(self, tmp_path, monkeypatch, capsys):
        from app.scripts.apply_history import empty_reason
        r = tmp_path / "repo"; r.mkdir()
        _git(r, "init", "-q"); _git(r, "config", "user.email", "t@t"); _git(r, "config", "user.name", "t")
        raw = tmp_path / "raw"; raw.mkdir()
        (raw / "стр.md").write_text(
            "---\nstatus: draft\nunapproved_jira: GBO-76041\n---\n\n"
            "Страница задачи 76041.\n{++GBO-30312: правка поверх++}\n", encoding="utf-8")
        (r / "README.md").write_text("init\n", encoding="utf-8")
        _git(r, "add", "-A"); _git(r, "commit", "-q", "-m", "init")
        monkeypatch.chdir(r)
        assert "GBO-76041 (1 стр.)" in empty_reason(raw, "GBO-30312")
        assert empty_reason(raw, "GBO-76041") == ""                  # свой флаг — не причина
        f = tmp_path / "t.txt"; f.write_text("GBO-30312\n", encoding="utf-8")
        assert main([str(raw), str(r), str(f), "--target-subdir", "chron"]) == 0
        err = capsys.readouterr().err
        assert "пустой срез" in err and "GBO-76041" in err
        assert "src/GBO-30312" in _git(r, "tag").stdout

    def test_refresh_only_without_tasks_file(self, repo, tmp_path, monkeypatch):
        # выгрузка без вводов: файл задач не задан, архив изменился → один коммит «Выгрузка»
        r, raw = repo
        monkeypatch.chdir(r)
        assert main([str(raw), str(r), str(self._tasks(tmp_path, ["GBO-1"], "a")),
                     "--target-subdir", "chron"]) == 0
        (raw / "стр.md").write_text("База (новая выгрузка).\n{++GBO-1: правка первой задачи++}\n",
                                   encoding="utf-8")
        assert main([str(raw), str(r), "--target-subdir", "chron"]) == 0
        assert _git(r, "log", "-1", "--format=%s").stdout.startswith("Выгрузка")
        assert "ранее принятых: 1" in _git(r, "log", "-1", "--format=%s").stdout
        assert "новая выгрузка" in (r / "chron" / "стр.md").read_text(encoding="utf-8")
        assert "правка первой задачи" in (r / "chron" / "стр.md").read_text(encoding="utf-8")
        assert _git(r, "tag").stdout.split() == ["src/GBO-1"]


class TestReviewFixes:
    """Исправления по код-ревью 2026-09-10. Пары: срабатывание / НЕсрабатывание
    (асимметрия ошибок: молчаливая потеря ПРОМ хуже остановки)."""

    def _tasks(self, tmp_path, ids, name="t"):
        f = tmp_path / f"{name}.txt"
        f.write_text("\n".join(ids) + "\n", encoding="utf-8")
        return f

    def _intro(self, r, raw, tmp_path, ids, name, *extra):
        return main([str(raw), str(r), str(self._tasks(tmp_path, ids, name)),
                     "--target-subdir", "chron", *extra])

    # п.1 — аннотированный тег считается введённым (и ПРОМ не откатывается)
    def test_annotated_tag_counts_as_introduced(self, repo, tmp_path, monkeypatch):
        from app.scripts.apply_history import introduced_tasks
        r, raw = repo
        monkeypatch.chdir(r)
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a") == 0
        _git(r, "tag", "-d", "src/GBO-1")
        _git(r, "tag", "-a", "-m", "аннотированный", "src/GBO-1", "HEAD")
        assert introduced_tasks(r, "src/") == ["GBO-1"]
        assert self._intro(r, raw, tmp_path, ["GBO-2"], "b") == 0
        assert "Выгрузка" not in _git(r, "log", "--format=%s").stdout
        s2 = _git(r, "show", "src/GBO-2:chron/стр.md").stdout
        assert "правка первой задачи" in s2 and "правка второй задачи" in s2

    # п.2 — тег, достижимый через merge, введён; без файла задач — нет отката
    def test_tag_reachable_via_merge_is_introduced(self, repo, tmp_path, monkeypatch):
        from app.scripts.apply_history import introduced_tasks
        r, raw = repo
        monkeypatch.chdir(r)
        main_branch = _git(r, "branch", "--show-current").stdout.strip()
        _git(r, "checkout", "-q", "-b", "feat")
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a") == 0
        _git(r, "checkout", "-q", main_branch)
        _git(r, "merge", "-q", "--no-ff", "-m", "merge feat", "feat")
        assert introduced_tasks(r, "src/") == ["GBO-1"]
        head = _git(r, "rev-parse", "HEAD").stdout.strip()
        rc = main([str(raw), str(r), "--target-subdir", "chron"])   # только «выгрузка»
        assert rc == 2 and _git(r, "rev-parse", "HEAD").stdout.strip() == head
        assert "правка первой задачи" in (r / "chron" / "стр.md").read_text(encoding="utf-8")

    # п.3 — префикс без слэша
    def test_tag_prefix_without_slash(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a", "--tag-prefix", "src-") == 0
        assert self._intro(r, raw, tmp_path, ["GBO-2"], "b", "--tag-prefix", "src-") == 0
        assert "Выгрузка" not in _git(r, "log", "--format=%s").stdout
        assert sorted(_git(r, "tag").stdout.split()) == ["src-GBO-1", "src-GBO-2"]

    # п.4 — целевой каталог внутри .git запрещён
    def test_target_inside_git_dir_refused(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        rc = self._intro(r, raw, tmp_path, ["GBO-1"], "a", "--target-subdir", ".git/chron")
        assert rc == 2
        assert _git(r, "rev-parse", "--git-dir").returncode == 0      # репозиторий цел
        rc = self._intro(r, raw, tmp_path, ["GBO-1"], "b", "--target-subdir", "sources/../.git")
        assert rc == 2

    # п.10 — detached HEAD
    def test_detached_head_refused(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        _git(r, "checkout", "-q", "--detach")
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a") == 2
        assert "src/GBO-1" not in _git(r, "tag").stdout

    # п.8 — невалидное имя тега ловится до изменений
    def test_invalid_tag_name_refused_before_changes(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        head = _git(r, "rev-parse", "HEAD").stdout.strip()
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a", "--tag-prefix", "src:") == 2
        assert _git(r, "rev-parse", "HEAD").stdout.strip() == head
        assert not (r / "chron").exists()

    # п.7 — сверка с манифестом: опечатка — стоп; --allow-unlisted — обход; нет манифеста — как раньше
    def test_unknown_task_vs_manifest(self, repo, tmp_path, monkeypatch, capsys):
        r, raw = repo
        monkeypatch.chdir(r)
        (raw / "migration-manifest.yaml").write_text(
            "migrated_at: '2026-09-10'\ntasks:\n  GBO-1:\n    color: red\n  GBO-2:\n    color: b\n",
            encoding="utf-8")
        head = _git(r, "rev-parse", "HEAD").stdout.strip()
        assert self._intro(r, raw, tmp_path, ["GBO-10"], "a") == 2
        assert "нет в манифесте" in capsys.readouterr().err
        assert _git(r, "rev-parse", "HEAD").stdout.strip() == head
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "b") == 0            # известная — ок
        assert self._intro(r, raw, tmp_path, ["GBO-10"], "c", "--allow-unlisted") == 0
        assert "src/GBO-10" in _git(r, "tag").stdout

    # п.5 — сбой git add: без тега, без коммита, дерево возвращено к HEAD
    def test_git_add_failure_stops_without_tag(self, repo, tmp_path, monkeypatch):
        import app.scripts.apply_history as ah
        r, raw = repo
        monkeypatch.chdir(r)
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a") == 0
        real = ah._git
        def flaky(repo_, *args):
            if args and args[0] == "add":
                return subprocess.CompletedProcess(args, 128, "", "fatal: index.lock")
            return real(repo_, *args)
        monkeypatch.setattr(ah, "_git", flaky)
        rc = self._intro(r, raw, tmp_path, ["GBO-2"], "b")
        monkeypatch.setattr(ah, "_git", real)
        assert rc == 1
        assert "src/GBO-2" not in _git(r, "tag").stdout
        assert _git(r, "log", "-1", "--format=%s").stdout.startswith("Ввод в эксплуатацию: GBO-1")
        assert _git(r, "status", "--porcelain").stdout.strip() == ""      # откат

    # п.6 — файлы среза под .gitignore: стоп; без правила — вложение в дереве тега
    def test_ignored_slice_files_stop(self, repo, tmp_path, monkeypatch, capsys):
        r, raw = repo
        monkeypatch.chdir(r)
        (raw / "img").mkdir(); (raw / "img" / "a.png").write_bytes(b"png")
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a") == 0
        assert "chron/img/a.png" in _git(r, "ls-tree", "-r", "--name-only", "src/GBO-1").stdout
        # уже отслеживаемый a.png правило не задевает; НОВОЕ вложение под правилом
        # git add пропустил бы молча — это и есть стоп
        (r / ".gitignore").write_text("*.png\n", encoding="utf-8")
        _git(r, "add", ".gitignore"); _git(r, "commit", "-q", "-m", "ignore png")
        (raw / "img" / "b.png").write_bytes(b"png2")
        rc = self._intro(r, raw, tmp_path, ["GBO-2"], "b")
        err = capsys.readouterr().err
        assert rc == 1 and ".gitignore" in err and "b.png" in err
        assert "src/GBO-2" not in _git(r, "tag").stdout
        assert _git(r, "status", "--porcelain").stdout.strip() == ""

    # п.9/14 — ошибка critic после наполнения: каталог возвращён к HEAD, повтор проходит
    def test_failure_after_refill_rolls_back_and_resumes(self, repo, tmp_path, monkeypatch):
        import app.scripts.apply_history as ah
        r, raw = repo
        monkeypatch.chdir(r)
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a") == 0
        real = ah._critic
        def failing(repo_, *args):
            if args and args[0] == "reject-all":
                return subprocess.CompletedProcess(args, 3, "", "сломалось")
            return real(repo_, *args)
        monkeypatch.setattr(ah, "_critic", failing)
        assert self._intro(r, raw, tmp_path, ["GBO-2"], "b") == 1
        monkeypatch.setattr(ah, "_critic", real)
        assert _git(r, "status", "--porcelain").stdout.strip() == ""
        assert "src/GBO-2" not in _git(r, "tag").stdout
        assert self._intro(r, raw, tmp_path, ["GBO-2"], "c") == 0          # повтор с места останова
        assert "src/GBO-2" in _git(r, "tag").stdout

    # п.11 — --base-dir внутри архива
    def test_base_dir_inside_raw_refused(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a", "--base-dir", str(raw)) == 2
        assert not (raw / "onix-history-base").exists()

    # п.12 — BOM в файле задач
    def test_task_list_with_bom(self, tmp_path):
        f = tmp_path / "bom.txt"
        f.write_bytes("\ufeffREM run-critic.bat apply GBO-5 --path .\nGBO-1\n".encode("utf-8"))
        ids, _ = read_task_list(f)
        assert ids == ["GBO-1"]

    # п.13 — manifest: tasks: первой строкой
    def test_manifest_tasks_first_line(self, tmp_path):
        from app.scripts.apply_history import manifest_tasks
        raw = tmp_path / "raw"; raw.mkdir()
        (raw / "migration-manifest.yaml").write_text("tasks:\n  GBO-1:\n    x: 1\n  GBO-2:\n    x: 2\n",
                                                     encoding="utf-8")
        assert manifest_tasks(raw) == ["GBO-1", "GBO-2"]
        (raw / "migration-manifest.yaml").write_text("service: x\n", encoding="utf-8")
        assert manifest_tasks(raw) == []

    # п.14 — причина пустого ввода: ID не подстрока, флаг только во frontmatter
    def test_empty_reason_exact_id_and_frontmatter_only(self, tmp_path):
        from app.scripts.apply_history import empty_reason
        raw = tmp_path / "raw"; raw.mkdir()
        (raw / "a.md").write_text("---\nunapproved_jira: GBO-77\n---\n\n{++GBO-12: x++}\n",
                                  encoding="utf-8")
        (raw / "b.md").write_text("---\nstatus: draft\n---\n\nтело\nunapproved_jira: GBO-88\n{++GBO-1: y++}\n",
                                  encoding="utf-8")
        assert empty_reason(raw, "GBO-1") == ""                    # GBO-12 ≠ GBO-1; флаг в теле не считается
        assert "GBO-77 (1 стр.)" in empty_reason(raw, "GBO-12")

    # п.16 — --push отправляет ветку и только теги этого прогона
    def test_push_sends_only_run_tags(self, repo, tmp_path, monkeypatch):
        r, raw = repo
        monkeypatch.chdir(r)
        bare = tmp_path / "remote.git"
        _git(r, "init", "-q", "--bare", str(bare))
        branch = _git(r, "branch", "--show-current").stdout.strip()
        _git(r, "remote", "add", "origin", str(bare))
        _git(r, "push", "-q", "-u", "origin", branch)
        _git(r, "tag", "scratch")
        assert self._intro(r, raw, tmp_path, ["GBO-1"], "a", "--push") == 0
        remote_tags = _git(r, "ls-remote", "--tags", "origin").stdout
        assert "refs/tags/src/GBO-1" in remote_tags and "scratch" not in remote_tags
        assert _git(r, "rev-parse", f"origin/{branch}").stdout == _git(r, "rev-parse", "HEAD").stdout
