# tests/test_critic_list.py
#
# Тесты команды critic.py list (Модуль 3, ТЗ п. 5.4): сбор незавершённых задач из всех
# нотаций (inline-маркеры / столбец status / HTML-нотация), группировка по задаче,
# разделение мигрировавших и новых по манифесту и остаток переходного периода (тест 23 ТЗ).

import json

from app.scripts.CI.critic import collect_task_occurrences, main


class TestCollect:
    """Сбор идентификаторов задач из всех нотаций одного файла."""

    def test_collects_from_all_notations(self):
        text = (
            "текст {++GBO-1: вставка++} и {--GBO-2: удаление--}\n"
            "| C-1 | V | +GBO-3 |\n"
            '<table><tr class="critic-row-ins" data-task="GBO-4"><td>x</td></tr></table>\n'
        )
        occ = collect_task_occurrences(text)
        assert set(occ) == {"GBO-1", "GBO-2", "GBO-3", "GBO-4"}

    def test_ignores_markers_in_fenced_code(self):
        text = "```\n{++GBO-9: в коде++}\n```\nснаружи {++GBO-1: x++}\n"
        occ = collect_task_occurrences(text)
        assert "GBO-1" in occ and "GBO-9" not in occ

    def test_lines_deduplicated_and_sorted(self):
        text = "{++GBO-1: a++} и ещё {++GBO-1: b++}\nвторая строка {++GBO-1: c++}\n"
        occ = collect_task_occurrences(text)
        assert occ["GBO-1"] == [1, 2]


class TestListCli:
    """CLI list: text и json, разделение по манифесту."""

    def _write(self, tmp_path):
        (tmp_path / "a.md").write_bytes(
            "требование {++GBO-1: x++} и {++TEAMTB-5: y++}\n".encode("utf-8"))
        (tmp_path / "b.md").write_bytes(
            "| C-1 | V | -GBO-1 |\n".encode("utf-8"))

    def test_list_text_runs(self, tmp_path):
        self._write(tmp_path)
        assert main(["list", "--path", str(tmp_path)]) == 0

    def test_list_json_groups_by_task(self, tmp_path, capsys):
        self._write(tmp_path)
        rc = main(["list", "--path", str(tmp_path), "--format", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert set(payload["tasks"]) == {"GBO-1", "TEAMTB-5"}
        # GBO-1 встречается в двух файлах
        assert len({p["file"] for p in payload["tasks"]["GBO-1"]}) == 2

    def test_list_manifest_splits_migrated_and_new(self, tmp_path, capsys):
        self._write(tmp_path)
        (tmp_path / "migration-manifest.yaml").write_bytes(
            ("migrated_at: '2026-08-15'\nservice: КК\ntasks:\n"
             "  GBO-1:\n    color: '#9966ff'\n"
             "  GBO-99:\n    color: '#00ff00'\n").encode("utf-8"))
        rc = main(["list", "--path", str(tmp_path), "--format", "json",
                   "--manifest", str(tmp_path / "migration-manifest.yaml")])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["migrated_with_markers"] == ["GBO-1"]   # в манифесте и есть маркеры
        assert payload["new_tasks"] == ["TEAMTB-5"]            # не из манифеста
        assert payload["transition_remaining"] == 1
        assert payload["migrated_cleared"] == ["GBO-99"]       # в манифесте, маркеров нет → на ПРОМ
