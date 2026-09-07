# tests/test_export_freeze_flag.py
#
# Сторож заморозки (решение владельца 2026-09-06, склейка с пилотом Doc-as-Code).
#
# Страничный флаг `unapproved_jira` — единственный канал, которым решение «этой
# страницы нет в ПРОМ» доезжает до миграции: опись выносит по нему `frozen:<ID>`,
# и промпт плана относит страницу в «вне SRS: заморожено до задачи». Пустая
# страница БЕЗ флага неотличима от штатного пустого контейнера, то есть потеря
# флага молчаливая.
#
# Раньше флаг писался только для страниц из списка --unapproved-jira. Забытая в
# списке задача давала преждевременный apply неутверждённого в ПРОМ — худший вид
# тихой порчи. Теперь экспортёр ставит флаг сам, когда ВЕСЬ состав страницы
# принадлежит одной задаче. Записывает именно экспортёр: флаг обязан лежать в
# архиве, а reject правит производную копию, которая пересоздаётся из архива на
# каждой задаче этапа 4 (исходное предложение писать флаг в reject-all отклонено).
#
# Ограничители здесь важнее самого срабатывания: цветовая семантика обязана
# защищать утверждённое от ложной заморозки.

from app.scripts.CI.critic import process_text
from app.scripts.migrate_confluence_tree import decide_page_flag as decide
from app.scripts.migrate_colors import finalize, new_accumulator, render_report_md


ONE_TASK = "{++GBO-52119: Требование целиком новой страницы.++}\n"


class TestFlagSet:
    def test_whole_page_of_one_task_gets_flag(self):
        flag, note = decide(ONE_TASK)
        assert flag == "GBO-52119" and note is None

    def test_html_notation_counts_too(self):
        content = ('<table><tbody>\n'
                   '<tr class="critic-row-ins" data-task="GBO-55269"><td>строка</td></tr>\n'
                   "</tbody></table>\n")
        flag, note = decide(content)
        assert flag == "GBO-55269" and note is None

    def test_flag_equals_the_task_that_reject_would_remove(self):
        """Инвариант: флаг называет ту задачу, чьим apply страница вернётся."""
        flag, _ = decide(ONE_TASK)
        restored, count = process_text(ONE_TASK, "apply", flag)
        assert count == 1 and "Требование целиком новой страницы." in restored


class TestFlagNotSet:
    """Пары на НЕсрабатывание — цветовая семантика защищает утверждённое."""

    def test_approved_new_page_without_markers(self):
        """Страница целиком новая, но ЧЁРНАЯ: утверждена, маркеров нет — флага нет."""
        content = "# Цели сервиса\n\nТребование, утверждённое на ПРОМ.\n"
        flag, note = decide(content)
        assert flag == "" and note is None

    def test_approved_text_next_to_a_marker(self):
        """Часть состава чёрная: reject опустошит страницу не целиком — флага нет."""
        content = "Утверждённый абзац.\n\n" + ONE_TASK
        flag, note = decide(content)
        assert flag == "" and note is None

    def test_empty_page_is_not_frozen(self):
        """Пустой контейнер — не заморозка: флаг превратил бы его в «нет в ПРОМ»."""
        flag, note = decide("\n\n")
        assert flag == "" and note is None

    def test_deletion_only_page_keeps_content(self):
        """Только удаления: reject их сохраняет, страница не пустеет — флага нет."""
        flag, note = decide("{--GBO-52119: удалённое требование--}\n")
        assert flag == "" and note is None


class TestGuards:
    def test_several_tasks_go_to_report_not_to_the_flag(self):
        content = "{++GBO-1: раз++}\n{++GBO-2: два++}\n"
        flag, note = decide(content)
        assert flag == ""                       # угадывать ID нельзя
        assert note["kind"] == "несколько задач" and note["tasks"] == ["GBO-1", "GBO-2"]

    def test_several_tasks_are_silent_when_the_list_already_decided(self):
        """Задача названа списком --unapproved-jira — вопрос уже решён владельцем."""
        content = "{++GBO-1: раз++}" + chr(10) + "{++GBO-2: два++}" + chr(10)
        flag, note = decide(content, forced="GBO-1")
        assert flag == "GBO-1" and note is None

    def test_manual_flag_not_overwritten(self):
        flag, note = decide(ONE_TASK, forced="GBO-99999")
        assert flag == "GBO-99999"
        assert note["kind"] == "расхождение" and note["tasks"] == ["GBO-99999", "GBO-52119"]

    def test_same_task_in_list_and_computed_is_silent(self):
        flag, note = decide(ONE_TASK, forced="GBO-52119")
        assert flag == "GBO-52119" and note is None


class TestReport:
    def _report(self, rows):
        acc = new_accumulator()
        acc["pages"] = 1
        acc["auto_page_flag"].extend(rows)
        _manifest, report = finalize(acc, service="KK", migrated_at="2026-09-06")
        return report

    def test_set_flags_listed(self):
        md = render_report_md(self._report(
            [{"page": "Страница", "kind": "поставлен", "tasks": ["GBO-52119"]}]))
        assert "## Страничный флаг заморозки проставлен автоматически" in md
        assert "GBO-52119" in md

    def test_ambiguous_case_is_a_manual_position(self):
        rows = [{"page": "Страница", "kind": "несколько задач", "tasks": ["GBO-1", "GBO-2"]}]
        with_case = self._report(rows)["stats"]["positions_manual_review"]
        assert with_case == self._report([])["stats"]["positions_manual_review"] + 1

    def test_set_flag_is_not_a_manual_position(self):
        """Успешная простановка — не работа для аналитика, а сведение."""
        rows = [{"page": "Страница", "kind": "поставлен", "tasks": ["GBO-52119"]}]
        assert (self._report(rows)["stats"]["positions_manual_review"]
                == self._report([])["stats"]["positions_manual_review"])

    def test_sections_present_when_clean(self):
        md = render_report_md(self._report([]))
        for heading in ("## Страничный флаг заморозки проставлен автоматически",
                        "## Флаг заморозки НЕ проставлен — нужен разбор"):
            start = md.find(heading)
            assert start >= 0 and "_нет_" in md[start:start + 200]
