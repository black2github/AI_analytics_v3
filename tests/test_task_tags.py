# tests/test_task_tags.py
"""Сторож «задача объявлена введённой, тега src/<ID> нет» (2026-10-24): введена = тег
src/<ID> на текущей ветке. Только ⚠ и i; на каждый пункт — срабатывание и НЕсрабатывание."""
import shutil
import subprocess
from pathlib import Path

import pytest

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.checks import task_tags as tt

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="нужен git")


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def repo(tmp_path: Path, log: str, tags=(), state: str = "") -> Path:
    """Репозиторий сервиса: docs/, журнал координации, коммит и теги src/<ID>."""
    root = tmp_path / "svc"
    make(root / "docs/README.md", "# Комплект\n")
    make(root / "coordination-log.md", log)
    if state:
        make(root / "coordination-state.md", state)
    git(root, "init", "-q")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    for t in tags:
        git(root, "tag", f"src/{t}")
    return root


LOG = ("# Журнал\n\n"
       "- 2026-10-09 | решения владельца — TEAMTB-1 введена в промышленную эксплуатацию\n"
       "- 2026-10-10 | (6) РЕШЕНИЯ: TEAMTB-2 введена в эксплуатацию; GBO-5 размечает 3 стр.\n")


def test_declared_with_tag_silent(tmp_path):
    root = repo(tmp_path, LOG, tags=("TEAMTB-1", "TEAMTB-2"))
    assert tt.check_task_tags(root / "docs") == []


def test_declared_without_tag_flagged_with_line(tmp_path):
    root = repo(tmp_path, LOG, tags=("TEAMTB-1",))
    out = tt.check_task_tags(root / "docs")
    assert out == ["⚠ задача объявлена введённой, тега src/TEAMTB-2 нет: TEAMTB-2 "
                   "(журнал: coordination-log.md, строка 4) — ввод делается run-history "
                   "(гид, «Ветки и теги»)"]


def test_short_ids_and_state_list(tmp_path):
    log = "- TEAMTB-3716/-3846/-3969 введены в эксплуатацию (флаг не снят)\n"
    state = "| Введённые задачи | TEAMTB-7, TEAMTB-8 |\n"
    root = repo(tmp_path, log, tags=("TEAMTB-3716", "TEAMTB-7"), state=state)
    out = tt.check_task_tags(root / "docs")
    assert [ln.split(": ")[1].split(" ")[0] for ln in out] == [
        "TEAMTB-3846", "TEAMTB-3969", "TEAMTB-8"]
    assert "(состояние: coordination-state.md, строка 1)" in out[2]


def test_state_form_in_operation(tmp_path):
    root = repo(tmp_path, "- решение — TEAMTB-9 в эксплуатации, коммит\n")
    out = tt.check_task_tags(root / "docs")
    assert len(out) == 1 and "src/TEAMTB-9 нет" in out[0]


def test_not_introduced_and_planned_silent(tmp_path):
    log = ("- TEAMTB-3 НЕ введена в эксплуатацию\n"
           "- TEAMTB-4 планируется ввод в эксплуатацию 30.10\n"
           "- TEAMTB-5 — ввод в эксплуатацию 30.10\n"
           "- TEAMTB-6 ещё не в эксплуатации\n"
           "- страница введена GBO-95842, доработки на промконтуре\n"
           "- инциденты TEAMTB-10 введены и устранены\n")
    root = repo(tmp_path, log)
    assert tt.check_task_tags(root / "docs") == []


def test_unrelated_ids_in_long_record_not_declared(tmp_path):
    log = ("- 2026-10-10 | GBO-1 8->4, OQ-55 закрыт, сумма совпала. (6) РЕШЕНИЯ: обе "
           "страницы активные; TEAMTB-2 введена в эксплуатацию\n")
    root = repo(tmp_path, log, tags=("TEAMTB-2",))
    assert tt.declared_tasks(root) == {"TEAMTB-2": ("coordination-log.md", 1)}


def test_frozen_list_and_inventory_stale(tmp_path):
    root = repo(tmp_path, "# Журнал\n", tags=("TEAMTB-1",))
    make(root / "sandbox/confluence-unapproved-jira-pages.md",
         "| Page_id | title | status | unapproved_jira |\n| --- | --- | --- | --- |\n"
         "| 2166860176 | ЭФ Клиента | draft | TEAMTB-1 |\n"
         "| 2166860177 | Другая страница | draft | GBO-7 |\n")
    make(root / "inventory.md",
         "| page_id | title | папка | тип | байт | основание |\n|---|---|---|---|---|---|\n"
         "| 2166860176 | ЭФ Клиента | ЭФ | screen-form | 10 | вне SRS: заморожено TEAMTB-1 |\n"
         "| 2166861149 | Скроллер | Скр | function | 81 | вне SRS: заморожено GBO-91555 |\n")
    out = tt.check_task_tags(root / "docs")
    assert out == [
        "⚠ страница 2166860176 «ЭФ Клиента» числится замороженной по задаче TEAMTB-1, а "
        "задача введена тегом src/TEAMTB-1 — список устарел, пересчитать (run-history)",
        "⚠ опись: страница 2166860176 «ЭФ Клиента» — основание «заморожено TEAMTB-1», а "
        "задача введена тегом src/TEAMTB-1 — опись устарела, пересчитать (run-history)"]


def test_tag_on_other_branch_not_counted(tmp_path):
    root = repo(tmp_path, LOG, tags=("TEAMTB-1",))
    git(root, "checkout", "-q", "-b", "side")
    make(root / "x.md", "x\n")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "x.md")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "side")
    git(root, "tag", "src/TEAMTB-2")
    git(root, "checkout", "-q", "-")
    out = tt.check_task_tags(root / "docs")
    assert len(out) == 1 and "src/TEAMTB-2 нет" in out[0]


def test_no_git_info_line(tmp_path):
    root = tmp_path / "svc"
    make(root / "docs/README.md", "# Комплект\n")
    make(root / "coordination-log.md", LOG)
    assert tt.check_task_tags(root / "docs") == ["i теги задач не проверены (нет git)"]


def test_no_journal_silent(tmp_path):
    root = tmp_path / "svc"
    make(root / "docs/README.md", "# Комплект\n")
    assert tt.check_task_tags(root / "docs") == []


def test_registered_without_verdict():
    chk = [c for c in selfcheck.KIT_CHECKS if c.id == "task_tags"]
    assert len(chk) == 1 and chk[0].affects_verdict is False
