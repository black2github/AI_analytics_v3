# tests/test_structural_facts.py
"""Сторож реестра структурных фактов (решение владельца 2026-10-06):
сигнатуры факта ищутся по канону и сверяются со списком потребителей."""
from pathlib import Path

from app.scripts.CI import structural_facts as sf


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


REG = """# Реестр

## SF-01. Контракты API живут в репозитории кода

- Факт: контракты — в `api-specification/` репозитория кода.
- Дом: `_meta/migration/addressing.md` (§2, §5.2)

```сигнатуры
api-specification
docs/api/
```

```потребители
_meta/skills/create-docs-readme.md
_meta/templates/docs-readme.md
```

```вне-учёта
_meta/references/*
```
"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "canon"
    _write(repo / "_meta/structural-facts.md", REG)
    _write(repo / "_meta/migration/addressing.md",
           "Контракты живут в `api-specification/` репозитория кода.\n")
    _write(repo / "_meta/skills/create-docs-readme.md",
           "Каталог `api/` не ожидается; контракты — api-specification.\n")
    _write(repo / "_meta/templates/docs-readme.md",
           "Раньше было docs/api/, теперь нет.\n")
    _write(repo / "_meta/references/snapshot.md",
           "Снимок техбука: api-specification/ ...\n")
    _write(repo / "_meta/skills/create-function.md", "Ничего про контракты.\n")
    _write(repo / "output/svc/docs/api/README.md", "docs/api/ в комплекте\n")
    return repo


def test_parse_registry():
    facts = sf.parse_registry(REG)
    assert len(facts) == 1
    f = facts[0]
    assert f.sid == "SF-01" and f.title.startswith("Контракты API")
    assert f.homes == ["_meta/migration/addressing.md"]
    assert f.signatures == ["api-specification", "docs/api/"]
    assert f.consumers == ["_meta/skills/create-docs-readme.md",
                           "_meta/templates/docs-readme.md"]
    assert f.excluded == ["_meta/references/*"]


def test_all_listed_is_ok(tmp_path):
    repo = _repo(tmp_path)
    lines, ok = sf.check(repo)
    assert ok, lines
    assert lines == ["✓ SF-01 «Контракты API живут в репозитории кода»: сигнатуры в 3 "
                     "файлах, все в реестре (дом 1, потребителей 2)"]


def test_unlisted_file_with_signature_warned(tmp_path):
    # «тридцать первый файл»: новый скилл с сигнатурой вне реестра
    repo = _repo(tmp_path)
    _write(repo / "_meta/skills/create-process.md",
           "Контракты лежат в api-specification/ репозитория.\n")
    lines, ok = sf.check(repo)
    assert not ok
    assert any(ln.startswith("⚠ SF-01: сигнатура `api-specification` в файле "
                             "_meta/skills/create-process.md — файла нет в списке")
               for ln in lines), lines


def test_stale_consumer_warned(tmp_path):
    repo = _repo(tmp_path)
    _write(repo / "_meta/templates/docs-readme.md", "Без упоминаний.\n")
    lines, ok = sf.check(repo)
    assert not ok
    assert any("потребитель _meta/templates/docs-readme.md сигнатур больше не "
               "содержит" in ln for ln in lines), lines


def test_missing_listed_file_warned(tmp_path):
    repo = _repo(tmp_path)
    (repo / "_meta/skills/create-docs-readme.md").unlink()
    lines, ok = sf.check(repo)
    assert not ok
    assert any("назван файл _meta/skills/create-docs-readme.md, которого нет"
               in ln for ln in lines), lines


def test_excluded_and_outputs_not_scanned(tmp_path):
    # НЕсрабатывание: снимок в references (вне учёта) и комплект в output/
    # с сигнатурами не дают предупреждений
    repo = _repo(tmp_path)
    _write(repo / "_meta/references/other.md", "docs/api/ тоже тут\n")
    _write(repo / "output/x/docs/api/y.md", "api-specification\n")
    lines, ok = sf.check(repo)
    assert ok, lines


def test_no_registry(tmp_path):
    lines, ok = sf.check(tmp_path)
    assert not ok and "не найден" in lines[0]


def test_cli_strict_exit_code(tmp_path):
    repo = _repo(tmp_path)
    assert sf.main(["--repo", str(repo)]) == 0
    _write(repo / "_meta/skills/new.md", "docs/api/\n")
    assert sf.main(["--repo", str(repo)]) == 0
    assert sf.main(["--repo", str(repo), "--strict"]) == 1
