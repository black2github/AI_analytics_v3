# tests/test_critic_task_prefilter.py
#
# Отбор файлов перед разбором (2026-09-06). Адресная правка `apply <ID>` /
# `reject <ID>` не может изменить файл, где идентификатора нет вовсе, — значит,
# разбирать его незачем. Замер на дереве [КК] (614 страниц): разбор всех файлов
# 1,39 с против 0,04 с при отборе.
#
# Повод — этап 4 роадмапа: хронология для каждой задачи заново применяет ВСЕ ранее
# принятые, то есть делает 11 026 проходов по дереву при 148 задачах. Разница
# между «часы» и «минуты» здесь целиком в этом отборе.
#
# Главное, что здесь закрепляется: отбор ничего не меняет в результате. Он грубый
# намеренно — подстрока, а не разбор: пропустить файл можно только когда
# упоминания нет совсем.

from app.scripts.CI.critic import file_mentions_task, main

PAGE_A = "---\nstatus: draft\n---\n\n{++GBO-1: правка первой задачи++}\n"
PAGE_B = "---\nstatus: draft\n---\n\n{++GBO-2: правка второй задачи++}\n"
PAGE_FLAG = "---\nstatus: draft\nunapproved_jira: GBO-3\n---\n\nТекст замороженной страницы.\n"
PAGE_HTML = ('---\nstatus: draft\n---\n\n<table><tbody>\n'
             '<tr class="critic-row-ins" data-task="GBO-4"><td>строка</td></tr>\n'
             "</tbody></table>\n")
PAGE_TABLE = ("---\nstatus: draft\n---\n\n"
              "| текст | status |\n| --- | --- |\n| требование | +GBO-5 |\n")


def _tree(tmp_path):
    for name, text in (("a.md", PAGE_A), ("b.md", PAGE_B), ("flag.md", PAGE_FLAG),
                       ("html.md", PAGE_HTML), ("table.md", PAGE_TABLE)):
        with open(tmp_path / name, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return tmp_path


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


class TestDetector:
    def test_sees_inline_marker(self, tmp_path):
        p = _tree(tmp_path) / "a.md"
        assert file_mentions_task(p, "GBO-1")
        assert not file_mentions_task(p, "GBO-2")

    def test_sees_page_flag(self, tmp_path):
        """Страничный флаг — тоже упоминание: по нему reject опустошает страницу."""
        assert file_mentions_task(_tree(tmp_path) / "flag.md", "GBO-3")

    def test_sees_html_notation(self, tmp_path):
        assert file_mentions_task(_tree(tmp_path) / "html.md", "GBO-4")

    def test_sees_status_column(self, tmp_path):
        assert file_mentions_task(_tree(tmp_path) / "table.md", "GBO-5")


class TestResultUnchanged:
    """Отбор — оптимизация: дерево после правки обязано быть тем же."""

    def test_targeted_apply_touches_only_its_page(self, tmp_path):
        root = _tree(tmp_path)
        assert main(["apply", "GBO-1", "--path", str(root)]) == 0
        assert "{++" not in _read(root / "a.md")
        assert _read(root / "b.md") == PAGE_B          # чужая задача не тронута
        assert _read(root / "flag.md") == PAGE_FLAG

    def test_page_flag_still_works_through_the_filter(self, tmp_path):
        root = _tree(tmp_path)
        assert main(["reject", "GBO-3", "--path", str(root)]) == 0
        assert "Текст замороженной страницы" not in _read(root / "flag.md")

    def test_html_and_table_notations_still_work(self, tmp_path):
        root = _tree(tmp_path)
        assert main(["reject", "GBO-4", "--path", str(root)]) == 0
        assert main(["reject", "GBO-5", "--path", str(root)]) == 0
        assert "строка" not in _read(root / "html.md")
        assert "требование" not in _read(root / "table.md")

    def test_all_modes_untouched_by_the_filter(self, tmp_path):
        """apply-all/reject-all идут без задачи — отбор к ним не применяется."""
        root = _tree(tmp_path)
        assert main(["apply-all", "--path", str(root)]) == 0
        for name in ("a.md", "b.md", "html.md", "table.md"):
            assert "{++" not in _read(root / name) and "critic-row" not in _read(root / name)

    def test_unknown_task_changes_nothing(self, tmp_path):
        root = _tree(tmp_path)
        before = {n: _read(root / n) for n in ("a.md", "b.md", "flag.md")}
        assert main(["apply", "GBO-99999", "--path", str(root)]) == 0
        assert {n: _read(root / n) for n in before} == before


class TestReport:
    def test_skipped_files_are_reported(self, tmp_path, capsys):
        root = _tree(tmp_path)
        main(["apply", "GBO-1", "--path", str(root)])
        out = capsys.readouterr().out
        assert "пропущено без упоминания задачи: 4" in out

    def test_nothing_reported_for_all_modes(self, tmp_path, capsys):
        main(["reject-all", "--path", str(_tree(tmp_path))])
        assert "пропущено без упоминания" not in capsys.readouterr().out
