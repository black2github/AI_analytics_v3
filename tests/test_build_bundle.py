# tests/test_build_bundle.py
#
# Сборщик поставки (app/scripts/build_bundle.py). Причина появления: 2026-09-06
# сверка нашла в бандле нормализатор таблиц месячной давности — ручная копия
# молча разошлась с каноном, и ни один механизм об этом не сигналил. Отпечаток
# исходников этот класс не ловит: деревья канона и поставки разного состава.
#
# Здесь закрепляется главное свойство сборщика: он ругается на всё
# необъяснённое (лишний файл в поставке, пропавший файл манифеста,
# расхождение), но молчит там, где различие объявлено — отличия контура и
# справочники команд.

import pytest

from app.scripts.build_bundle import (
    BUNDLE_FILES, CONTOUR_PATCHES, SOFT_FILES,
    apply_patches, build_zip, compare, extra_bundle_files, main,
    read_stamp, render, stamp_source, strip_stamp, sync, zip_entries,
)

VERSION_PY = (
    'VERSION = "1.6.2"\n'
    "\n"
    'BUILD_FROM = ""\n'
    "\n"
    "def banner(tool):\n"
    "    return tool\n"
)

LOADER_PY = "conf = Confluence(\n    url=URL,\n    verify_ssl=True\n)\n"


def _make_pair(tmp_path, files):
    """Мини-канон и мини-поставка: только то, что нужно тесту."""
    canon, bundle = tmp_path / "canon", tmp_path / "bundle"
    for rel, text in files.items():
        p = canon / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
    (bundle / "app").mkdir(parents=True)
    return canon, bundle


BASE = {"app/version.py": VERSION_PY, "app/confluence_loader.py": LOADER_PY}


@pytest.fixture
def two_trees(tmp_path, monkeypatch):
    canon, bundle = _make_pair(tmp_path, BASE)
    monkeypatch.setattr("app.scripts.build_bundle.BUNDLE_FILES", tuple(BASE))
    monkeypatch.setattr("app.scripts.build_bundle.SOFT_FILES", ())
    return canon, bundle


class TestManifestMatchesCanon:
    """Манифест — не список пожеланий: каждый файл обязан существовать в каноне."""

    def test_every_listed_file_exists(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        missing = [rel for rel in BUNDLE_FILES if not (root / rel).is_file()]
        assert missing == [], f"манифест ссылается на несуществующие файлы: {missing}"

    def test_soft_files_are_data_references(self):
        assert SOFT_FILES and all(rel.startswith("app/data/") for rel in SOFT_FILES)

    def test_builder_itself_not_shipped(self):
        """Сборщик — инструмент канона, в поставку не уезжает."""
        assert "app/scripts/build_bundle.py" not in BUNDLE_FILES


class TestContourPatches:
    def test_patch_applied(self):
        out = apply_patches("app/confluence_loader.py", LOADER_PY)
        assert "verify_ssl=False" in out and "verify_ssl=True" not in out

    def test_missing_fragment_is_an_error(self):
        """Канон переписали, манифест устарел — молчать нельзя."""
        with pytest.raises(ValueError, match="манифест устарел"):
            apply_patches("app/confluence_loader.py", "conf = Confluence(url=URL)\n")

    def test_unlisted_file_untouched(self):
        assert apply_patches("app/color_map.py", LOADER_PY) == LOADER_PY

    def test_every_patch_carries_a_reason(self):
        for rel, patches in CONTOUR_PATCHES.items():
            for old, new, why in patches:
                assert why.strip(), f"{rel}: подстановка без причины"


class TestStamp:
    def test_stamp_written(self):
        out = stamp_source(VERSION_PY, "2ea768ad")
        assert 'BUILD_FROM = "2ea768ad"' in out
        assert read_stamp(out) == "2ea768ad"

    def test_stamp_stripped_for_comparison(self):
        assert strip_stamp(stamp_source(VERSION_PY, "abc123")) == VERSION_PY

    def test_crlf_file_stamped(self):
        """Канон живёт в CRLF: якорь конца строки тут не работает, нужен просмотр вперёд."""
        crlf = VERSION_PY.replace("\n", "\r\n")
        out = stamp_source(crlf, "2ea768ad")
        assert 'BUILD_FROM = "2ea768ad"\r\n' in out
        assert read_stamp(out) == "2ea768ad"
        assert strip_stamp(out) == crlf

    def test_absent_placeholder_is_an_error(self):
        with pytest.raises(ValueError, match="штамп ставить некуда"):
            stamp_source('VERSION = "1.0.0"\n', "abc123")

    def test_render_stamps_only_version(self):
        assert read_stamp(render("app/version.py", VERSION_PY, "aaa111")) == "aaa111"
        assert "BUILD_FROM" not in render("app/color_map.py", LOADER_PY, "aaa111")


class TestSync:
    def test_files_laid_out_with_patches(self, two_trees):
        canon, bundle = two_trees
        changed = sync(canon, bundle, "aaa111", sync_data=False)
        assert set(changed) == set(BASE)
        assert "verify_ssl=False" in (bundle / "app/confluence_loader.py").read_text(
            encoding="utf-8")
        assert read_stamp((bundle / "app/version.py").read_text(encoding="utf-8")) == "aaa111"

    def test_idempotent(self, two_trees):
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        assert sync(canon, bundle, "aaa111", sync_data=False) == []

    def test_new_commit_restamps_only_version(self, two_trees):
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        assert sync(canon, bundle, "bbb222", sync_data=False) == ["app/version.py"]

    def test_line_endings_alone_do_not_rewrite(self, two_trees):
        """Копии разъехались по CRLF/LF — смысла в этом нет, файл не трогаем."""
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        p = bundle / "app/confluence_loader.py"
        before = p.read_text(encoding="utf-8")
        p.write_text(before.replace("\n", "\r\n"), encoding="utf-8", newline="")
        assert sync(canon, bundle, "aaa111", sync_data=False) == []
        with open(p, "r", encoding="utf-8", newline="") as f:
            assert "\r\n" in f.read()                                # байты сохранены
        assert compare(canon, bundle, "aaa111")["расходится"] == []

    def test_missing_source_is_an_error(self, two_trees):
        canon, bundle = two_trees
        (canon / "app/version.py").unlink()
        with pytest.raises(FileNotFoundError, match="пропал из канона"):
            sync(canon, bundle, "aaa111", sync_data=False)


class TestCompare:
    def test_clean_after_sync(self, two_trees):
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        rep = compare(canon, bundle, "aaa111")
        assert rep["расходится"] == [] and rep["нет в поставке"] == []

    def test_hand_edit_in_bundle_detected(self, two_trees):
        """Ровно тот случай, ради которого сборщик и написан."""
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        p = bundle / "app/confluence_loader.py"
        p.write_text(p.read_text(encoding="utf-8") + "# правка на месте\n",
                     encoding="utf-8", newline="")
        assert compare(canon, bundle, "aaa111")["расходится"] == ["app/confluence_loader.py"]

    def test_old_stamp_is_not_a_divergence(self, two_trees):
        """Старая сборка — это возраст, а не расхождение кода."""
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        assert compare(canon, bundle, "bbb222")["расходится"] == []

    def test_extra_file_in_bundle_named(self, two_trees):
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        (bundle / "app/самодеятельность.py").write_text("x = 1\n", encoding="utf-8")
        assert compare(canon, bundle, "aaa111")["лишнее в поставке"] == [
            "app/самодеятельность.py"]

    def test_pycache_not_counted_as_extra(self, two_trees):
        canon, bundle = two_trees
        sync(canon, bundle, "aaa111", sync_data=False)
        cache = bundle / "app/__pycache__"
        cache.mkdir()
        (cache / "critic.cpython-312.pyc").write_bytes(b"\x00")
        assert extra_bundle_files(bundle) == []


class TestSoftDataFiles:
    """Справочники команд: различие называем, но молча не переписываем."""

    @pytest.fixture
    def trees(self, tmp_path, monkeypatch):
        files = dict(BASE, **{"app/data/services.json": '["канон"]\n'})
        canon, bundle = _make_pair(tmp_path, files)
        monkeypatch.setattr("app.scripts.build_bundle.BUNDLE_FILES", tuple(files))
        monkeypatch.setattr("app.scripts.build_bundle.SOFT_FILES", ("app/data/services.json",))
        return canon, bundle

    def test_not_overwritten_by_default(self, trees):
        canon, bundle = trees
        sync(canon, bundle, "aaa111", sync_data=False)
        target = bundle / "app/data/services.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('["команда"]\n', encoding="utf-8", newline="")
        assert sync(canon, bundle, "aaa111", sync_data=False) == []
        assert target.read_text(encoding="utf-8") == '["команда"]\n'

    def test_difference_reported(self, trees):
        canon, bundle = trees
        sync(canon, bundle, "aaa111", sync_data=True)
        (bundle / "app/data/services.json").write_text('["команда"]\n',
                                                       encoding="utf-8", newline="")
        rep = compare(canon, bundle, "aaa111")
        assert rep["справочники"] == ["app/data/services.json"]
        assert rep["расходится"] == []          # не ошибка, а предупреждение

    def test_sync_data_pulls_it(self, trees):
        canon, bundle = trees
        sync(canon, bundle, "aaa111", sync_data=True)
        assert (bundle / "app/data/services.json").read_text(encoding="utf-8") == '["канон"]\n'


class TestCanonCommit:
    """Штамп «+dirty» обязан означать «в пакет уехало неподтверждённое»."""

    def _repo(self, tmp_path, monkeypatch):
        import subprocess
        from app.scripts.build_bundle import canon_commit

        repo = tmp_path / "canon"
        (repo / "app").mkdir(parents=True)
        (repo / "app/version.py").write_text(VERSION_PY, encoding="utf-8")
        run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
        run("init", "-q")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        run("add", "app/version.py")
        run("commit", "-qm", "первый")
        monkeypatch.setattr("app.scripts.build_bundle.BUNDLE_FILES", ("app/version.py",))
        return repo, run, canon_commit

    def test_clean_tree_has_no_mark(self, tmp_path, monkeypatch):
        repo, _run, canon_commit = self._repo(tmp_path, monkeypatch)
        assert "+dirty" not in canon_commit(repo)

    def test_unrelated_junk_does_not_dirty_the_stamp(self, tmp_path, monkeypatch):
        """В каноне всегда лежит несвязанный мусор — он в пакет не уезжает."""
        repo, _run, canon_commit = self._repo(tmp_path, monkeypatch)
        (repo / "app/заметка.md").write_text("черновик\n", encoding="utf-8")
        assert "+dirty" not in canon_commit(repo)

    def test_edited_manifest_file_dirties_the_stamp(self, tmp_path, monkeypatch):
        repo, _run, canon_commit = self._repo(tmp_path, monkeypatch)
        (repo / "app/version.py").write_text(VERSION_PY + "# правка\n", encoding="utf-8")
        assert canon_commit(repo).endswith("+dirty")


class TestZip:
    def test_git_service_files_excluded(self):
        entries = zip_entries(["README.md", ".gitignore", ".gitattributes", "app/version.py"])
        assert entries == ["README.md", "app/version.py"]

    def test_archive_holds_tracked_files(self, tmp_path, monkeypatch):
        import zipfile
        bundle = tmp_path / "bundle"
        (bundle / "app").mkdir(parents=True)
        (bundle / "app/version.py").write_text(VERSION_PY, encoding="utf-8")
        (bundle / "README.md").write_text("# поставка\n", encoding="utf-8")
        monkeypatch.setattr("app.scripts.build_bundle._tracked_files",
                            lambda _b: ["README.md", "app/version.py", ".gitignore"])
        target, n = build_zip(bundle)
        assert n == 2
        names = zipfile.ZipFile(target).namelist()
        assert "app/version.py" in names and ".gitignore" not in names
        assert "app/" in names                  # каталоги как в прежних сборках


class TestCli:
    def test_check_reports_divergence_with_code_1(self, two_trees, capsys, monkeypatch):
        canon, bundle = two_trees
        monkeypatch.setattr("app.scripts.build_bundle.canon_commit", lambda _c: "aaa111")
        monkeypatch.setattr("app.scripts.build_bundle.Path.resolve", Path_resolve_stub(canon))
        code = main(["--bundle", str(bundle), "--check"])
        assert code == 1
        assert "нет в поставке" in capsys.readouterr().out

    def test_rejects_directory_that_is_not_a_bundle(self, tmp_path, capsys):
        assert main(["--bundle", str(tmp_path), "--check"]) == 2
        assert "не похож на поставку" in capsys.readouterr().err


def Path_resolve_stub(canon):
    """Подмена корня канона: сборщик считает его от собственного расположения."""
    from pathlib import Path

    real = Path.resolve

    def resolve(self, *a, **kw):
        if self.name == "build_bundle.py":
            return canon / "app" / "scripts" / "build_bundle.py"
        return real(self, *a, **kw)

    return resolve
