# tests/test_canon_delta.py
"""Дельта среза канона (canon_delta.py, решение владельца 2026-10-15):
удалённые файлы и заголовки разделов в _meta, правки утилит — для ревью
чужого вливания; заголовки внутри блоков кода не считаются."""
import subprocess
from pathlib import Path

import pytest

from app.scripts.CI import canon_delta as cd


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "canon"
    root.mkdir()
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "T T")
    _w(root / "_meta/templates/feature-spec.md",
       "# Шаблон\n\n## Истории\n\nтекст\n\n## Нефункциональные требования\n\nтекст\n")
    _w(root / "_meta/skills/old.md", "# Скилл\n")
    _w(root / "_meta/tools/link_debts.py", "a = 1\nb = 2\nc = 3\n")
    _w(root / "_meta/migration/guide.md", "# Гид\n\n```markdown\n## Образец\n```\n\n## Правила\n")
    _w(root / "output/x.md", "# не зона\n\n## Раздел\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "старый срез")
    return root


def test_clean_delta_reports_nothing_to_review(repo):
    _w(repo / "_meta/skills/new.md", "# Новый\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "добавление")
    rep, s = cd.delta(repo, "HEAD~1", "HEAD")
    assert s["attention"] == 0
    assert any("удалений и правок прибора нет" in l for l in rep), rep
    assert s["added"] == ["_meta/skills/new.md"]


def test_removed_heading_file_and_tool_change_are_reported(repo):
    _w(repo / "_meta/templates/feature-spec.md", "# Шаблон\n\n## Истории\n\nтекст\n")
    (repo / "_meta/skills/old.md").unlink()
    _w(repo / "_meta/tools/link_debts.py", "a = 1\n")
    _w(repo / "output/x.md", "# не зона\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "чужое слияние")
    rep, s = cd.delta(repo, "HEAD~1", "HEAD")
    assert s["removed_files"] == ["_meta/skills/old.md"]
    assert s["removed_headings"] == {
        "_meta/templates/feature-spec.md": ["## Нефункциональные требования"]}
    assert s["tools"] == {"_meta/tools/link_debts.py": (0, 2)}
    assert s["attention"] == 3
    joined = "\n".join(rep)
    assert "## Нефункциональные требования" in joined
    assert "_meta/tools/link_debts.py: +0 −2" in joined
    assert "есть что смотреть" in joined
    assert "output/x.md" not in joined  # вне зоны


def test_heading_inside_code_fence_counted_separately(repo):
    # образец в блоке кода убрали — это не раздел документа, но структура
    # шаблона: отдельная корзина и тоже «к ревью»
    _w(repo / "_meta/migration/guide.md", "# Гид\n\n## Правила\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "убран образец")
    rep, s = cd.delta(repo, "HEAD~1", "HEAD")
    assert s["removed_headings"] == {}, s
    assert s["removed_sample_headings"] == {"_meta/migration/guide.md": ["## Образец"]}
    assert s["attention"] == 1


def test_nested_fences_feature_spec_case(repo):
    # шаблон фичи 14.10: тело карточки в ````markdown с вложенным ```gherkin;
    # удалённый из образца раздел НФТ должен попасть в дельту
    body = ("# Шаблон\n\n## Шаблон файла фичи\n\n````markdown\n# Фича\n\n## US-NN\n\n"
            "```gherkin\nДано\n```\n\n## Нефункциональные требования\n\n## Ссылки\n````\n")
    _w(repo / "_meta/templates/feature-spec.md", body)
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "шаблон с образцом")
    _w(repo / "_meta/templates/feature-spec.md",
       body.replace("## Нефункциональные требования\n\n", ""))
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "раздел НФТ снят")
    rep, s = cd.delta(repo, "HEAD~1", "HEAD")
    assert s["removed_sample_headings"] == {
        "_meta/templates/feature-spec.md": ["## Нефункциональные требования"]}, s
    assert s["removed_headings"] == {}
    assert cd.headings(body)[0] == ["# Шаблон", "## Шаблон файла фичи"]


def test_rename_tracked_with_headings(repo):
    _git(repo, "mv", "_meta/skills/old.md", "_meta/skills/renamed.md")
    _git(repo, "commit", "-q", "-m", "переименование")
    rep, s = cd.delta(repo, "HEAD~1", "HEAD")
    assert s["renamed"] == [("_meta/skills/old.md", "_meta/skills/renamed.md")]
    assert s["removed_headings"] == {}
    assert s["attention"] == 1


def test_cli_strict_exit_code(repo, capsys):
    (repo / "_meta/skills/old.md").unlink()
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "удаление")
    import sys
    argv = sys.argv
    try:
        sys.argv = ["canon_delta.py", "--repo", str(repo), "--strict", "HEAD~1"]
        assert cd.main() == 1
        sys.argv = ["canon_delta.py", "--repo", str(repo), "HEAD~1", "HEAD"]
        assert cd.main() == 0
    finally:
        sys.argv = argv
    out = capsys.readouterr().out
    assert "удалено ×1" in out
