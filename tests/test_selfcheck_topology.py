# tests/test_selfcheck_topology.py
#
# Корень стенда по каталогу выгрузки (FB-03, 2026-09-11): пилотный стенд
# <root>/confluence против репозитория источника линии 2.x
# <src>/sources/confluence (track-manual, гид «Файлы репозитория»).
#
# Прежний признак «родитель выгрузки» на второй раскладке давал <src>/sources:
# гейт требовал журнал sources/sandbox/journal.txt, искал профиль в
# sources/README.md и молча пропускал сверку среза канона. Первый исполнитель
# PRE-01 создал sources/sandbox/ по подсказке прибора, координатор велел
# удалить — круг замкнулся. Класс дефекта тот же, что FB-01: прибор молчаливо
# предполагает топологию пилота. Каждый сторож — парой на обе раскладки.

from pathlib import Path

from app.scripts.CI import selfcheck


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


PROFILE = ("# Профиль\n\n| Поле | Значение |\n|---|---|\n"
           "| **service-id** | `CC` |\n"
           "| **Срез канона** | `abc1234` |\n"
           "| **План миграции** | `plan.md` |\n")

PLAN = ("# План\n\n| Этап | Тип |\n|---|---|\n"
        "| `PRE-01` | инфраструктура |\n"
        "| `COM-01` | data-model |\n")


def pilot(tmp_path):
    """<root>/confluence, профиль в корне."""
    srcs = tmp_path / "confluence"
    srcs.mkdir()
    make(tmp_path / "README.md", PROFILE)
    return tmp_path, srcs


def src_line2(tmp_path, git=True):
    """<src>/sources/confluence, профиль в корне, .git в корне."""
    srcs = tmp_path / "sources" / "confluence"
    srcs.mkdir(parents=True)
    if git:
        (tmp_path / ".git").mkdir()
    make(tmp_path / "README.md", PROFILE)
    return tmp_path, srcs


class TestStandRoot:
    def test_pilot(self, tmp_path):
        root, srcs = pilot(tmp_path)
        assert selfcheck._stand_root(srcs) == root.resolve()

    def test_src_line2(self, tmp_path):
        root, srcs = src_line2(tmp_path)
        assert selfcheck._stand_root(srcs) == root.resolve()

    def test_src_line2_without_git(self, tmp_path):
        # стенд вне git (тесты): признак по имени контейнера sources
        root, srcs = src_line2(tmp_path, git=False)
        assert selfcheck._stand_root(srcs) == root.resolve()

    def test_sources_is_repo_itself(self, tmp_path):
        # НЕсрабатывание: каталог с именем sources сам является
        # репозиторием — выше него не поднимаемся
        repo = tmp_path / "sources"
        srcs = repo / "confluence"
        srcs.mkdir(parents=True)
        (repo / ".git").mkdir()
        assert selfcheck._stand_root(srcs) == repo.resolve()


class TestJournalName:
    """Протокол §4: единый sandbox/journal.txt в корне стенда."""

    def test_pilot(self, tmp_path):
        root, srcs = pilot(tmp_path)
        assert selfcheck.check_journal_name(
            root / "sandbox" / "journal.txt", srcs) is None

    def test_src_line2(self, tmp_path):
        root, srcs = src_line2(tmp_path)
        assert selfcheck.check_journal_name(
            root / "sandbox" / "journal.txt", srcs) is None

    def test_src_line2_old_demand_is_defect(self, tmp_path):
        # то, что прибор требовал раньше, — теперь брак
        root, srcs = src_line2(tmp_path)
        w = selfcheck.check_journal_name(
            root / "sources" / "sandbox" / "journal.txt", srcs)
        assert w and "§4" in w


class TestCanonCut:
    def test_pilot(self, tmp_path):
        _, srcs = pilot(tmp_path)
        rep, ok = selfcheck.check_canon_cut(srcs, "deadbee")
        assert not ok and any("✗ срез канона" in ln for ln in rep)

    def test_src_line2(self, tmp_path):
        # раньше профиль не находился и сверка молча пропускалась
        _, srcs = src_line2(tmp_path)
        rep, ok = selfcheck.check_canon_cut(srcs, "deadbee")
        assert not ok and any("✗ срез канона" in ln for ln in rep)
        rep, ok = selfcheck.check_canon_cut(srcs, "abc1234")
        assert ok and any("✓ срез канона" in ln for ln in rep)


class TestProtocolDiscipline:
    """Протокол §3: посторонний скрипт в sandbox/ корня стенда."""

    def test_pilot(self, tmp_path):
        root, srcs = pilot(tmp_path)
        make(root / "sandbox" / "build_controls.py", "print(1)")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert not ok and any("build_controls.py" in ln for ln in rep)

    def test_src_line2(self, tmp_path):
        root, srcs = src_line2(tmp_path)
        make(root / "sandbox" / "build_controls.py", "print(1)")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert not ok and any("build_controls.py" in ln for ln in rep)


class TestStagePrompts:
    """prompts/ и sandbox/ читаются от корня стенда."""

    def _check(self, root, srcs):
        make(root / "plan.md", PLAN)
        make(root / "prompts" / "PRE-01.md", "промпт")
        rep, _ = selfcheck.check_stage_prompts(srcs)
        line = next(ln for ln in rep if ln.startswith("⚠ промпты"))
        assert "COM-01" in line and "PRE-01" not in line

    def test_pilot(self, tmp_path):
        self._check(*pilot(tmp_path))

    def test_src_line2(self, tmp_path):
        self._check(*src_line2(tmp_path))
