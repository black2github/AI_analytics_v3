# tests/test_repair_export.py
#
# Разовая починка уже выгруженных деревьев (app/scripts/repair_export.py):
#   • --unfold — склейка свёрнутых значений frontmatter (инцидент 2026-08-23:
#     PyYAML переносил длинный title на вторую строку, построчные читатели
#     видели обрезку с незакрытой кавычкой);
#   • --unapproved-jira — простановка страничного флага в старых выгрузках.
#
# Ключевые гарантии, которые здесь закрепляются: смысл frontmatter не меняется,
# тело файла не трогается, повторный прогон ничего не делает.

import json

import yaml

from app.scripts.repair_export import (
    load_unapproved_ids, main, marker_tasks, repair_file,
    set_page_flag, split_frontmatter, unfold_frontmatter,
)

LONG_TITLE = ("[РРКО_ИПВ] Система: Функция поиска документов по параметрам "
              "для формирования рассылки (обратная загрузка)")

# Ровно так это лежит в выгрузке: значение перенесено на вторую строку.
FOLDED = (
    "---\n"
    "doc_id: '{{SIGN: тест}}'\n"
    "title: '[РРКО_ИПВ] Система: Функция поиска документов по параметрам для формирования\n"
    "  рассылки (обратная загрузка)'\n"
    "status: draft\n"
    "---\n"
    "\n"
    "Тело страницы.\n"
)


def _write(tmp_path, text, name="страница.md"):
    path = tmp_path / name
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


class TestUnfold:
    def test_folded_value_joined_into_one_line(self, tmp_path):
        path = _write(tmp_path, FOLDED)
        rep = repair_file(path, unfold=True, unapproved=None)
        assert rep["changed"] and rep["unfolded"] == 1

        fm = rep["new_text"].split("---")[1]
        title_lines = [l for l in fm.splitlines() if l.startswith("title:")]
        assert len(title_lines) == 1
        assert LONG_TITLE in title_lines[0]
        assert title_lines[0].rstrip().endswith("'")

    def test_value_meaning_preserved(self, tmp_path):
        path = _write(tmp_path, FOLDED)
        rep = repair_file(path, unfold=True, unapproved=None)
        before = yaml.safe_load(FOLDED.split("---")[1])
        after = yaml.safe_load(rep["new_text"].split("---")[1])
        assert after == before
        assert after["title"] == LONG_TITLE

    def test_body_untouched(self, tmp_path):
        path = _write(tmp_path, FOLDED)
        rep = repair_file(path, unfold=True, unapproved=None)
        assert rep["new_text"].endswith("\nТело страницы.\n")

    def test_crlf_preserved(self, tmp_path):
        path = _write(tmp_path, FOLDED.replace("\n", "\r\n"))
        rep = repair_file(path, unfold=True, unapproved=None)
        text = rep["new_text"]
        assert "\r\n" in text
        assert text.replace("\r\n", "").count("\n") == 0   # одиночных LF нет

    def test_idempotent(self, tmp_path):
        path = _write(tmp_path, FOLDED)
        first = repair_file(path, unfold=True, unapproved=None)
        _write(tmp_path, first["new_text"])
        second = repair_file(path, unfold=True, unapproved=None)
        assert not second["changed"]

    def test_block_scalar_untouched(self):
        """Многострочность блочного скаляра осмысленная — не склеиваем."""
        fm = "description: |\n  первая строка\n  вторая строка\n"
        out, joined = unfold_frontmatter(fm)
        assert out == fm and joined == 0

    def test_list_untouched(self):
        fm = "reviewers:\n  - Иванов\n  - Петров\n"
        out, joined = unfold_frontmatter(fm)
        assert out == fm and joined == 0

    def test_nested_mapping_untouched(self):
        fm = "links:\n  parent: страница\n  child: другая\n"
        out, joined = unfold_frontmatter(fm)
        assert out == fm and joined == 0

    def test_short_values_untouched(self):
        fm = "title: Короткий\nstatus: active\n"
        out, joined = unfold_frontmatter(fm)
        assert out == fm and joined == 0


class TestPageFlag:
    FM = "---\ndoc_id: '{{SIGN: т}}'\nstatus: draft\n---\n"
    BODY = "\n{++TEAMECO-5486: Требование.++}\n\n```\nкод макроса\n```\n"

    def test_flag_set_for_listed_task(self, tmp_path):
        path = _write(tmp_path, self.FM + self.BODY)
        rep = repair_file(path, unfold=False, unapproved={"TEAMECO-5486"})
        assert rep["changed"] and rep["flagged"] == "TEAMECO-5486"
        assert "unapproved_jira: TEAMECO-5486" in rep["new_text"]
        # флаг встаёт сразу после status, тело не трогается
        assert rep["new_text"].endswith(self.BODY)

    def test_task_outside_list_ignored(self, tmp_path):
        path = _write(tmp_path, self.FM + self.BODY)
        rep = repair_file(path, unfold=False, unapproved={"GBO-777"})
        assert not rep["changed"] and rep["flagged"] is None

    def test_two_listed_tasks_are_conflict(self, tmp_path):
        body = "\n{++GBO-1: раз++}\n{++GBO-2: два++}\n"
        path = _write(tmp_path, self.FM + body)
        rep = repair_file(path, unfold=False, unapproved={"GBO-1", "GBO-2"})
        assert not rep["changed"]
        assert "несколько неутверждённых задач" in rep["skipped"]

    def test_existing_flag_not_duplicated(self):
        fm = "status: draft\nunapproved_jira: TEAMECO-5486\n"
        out, added = set_page_flag(fm, "TEAMECO-5486")
        assert out == fm and added is False

    def test_marker_tasks_reads_ids(self):
        assert marker_tasks("{++GBO-1: a++} и {++GBO-2: b++}") == {"GBO-1", "GBO-2"}


class TestGuards:
    def test_file_without_frontmatter_skipped(self, tmp_path):
        path = _write(tmp_path, "# Просто markdown\n\nбез frontmatter\n")
        rep = repair_file(path, unfold=True, unapproved={"GBO-1"})
        assert not rep["changed"] and rep["skipped"] == "нет frontmatter"

    def test_split_frontmatter_requires_closing(self):
        assert split_frontmatter("---\ntitle: без закрытия\n") is None

    def test_unapproved_ids_accept_both_shapes(self, tmp_path):
        plain = tmp_path / "a.json"
        plain.write_text(json.dumps(["GBO-1", "GBO-2"]), encoding="utf-8")
        wrapped = tmp_path / "b.json"
        wrapped.write_text(json.dumps({"unapproved_jira": ["GBO-1"]}), encoding="utf-8")
        assert load_unapproved_ids(plain) == {"GBO-1", "GBO-2"}
        assert load_unapproved_ids(wrapped) == {"GBO-1"}

    def test_unapproved_ids_reject_garbage(self, tmp_path):
        bad = tmp_path / "c.json"
        bad.write_text(json.dumps(["не-джира"]), encoding="utf-8")
        try:
            load_unapproved_ids(bad)
        except ValueError as e:
            assert "не похожи на Jira ID" in str(e)
        else:
            raise AssertionError("мусор в списке должен отвергаться")


class TestCli:
    def test_dry_run_writes_nothing(self, tmp_path, capsys):
        path = _write(tmp_path, FOLDED)
        before = _read(path)
        assert main([str(tmp_path), "--unfold", "--dry-run"]) == 0
        assert _read(path) == before
        assert "[dry-run]" in capsys.readouterr().out

    def test_run_rewrites_file(self, tmp_path):
        path = _write(tmp_path, FOLDED)
        assert main([str(tmp_path), "--unfold"]) == 0
        text = _read(path)
        assert LONG_TITLE in [l for l in text.splitlines() if l.startswith("title:")][0]

    def test_requires_a_repair_flag(self, tmp_path):
        try:
            main([str(tmp_path)])
        except SystemExit as e:
            assert e.code == 2
        else:
            raise AssertionError("без флагов починки запуск должен отвергаться")
