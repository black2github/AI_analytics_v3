# tests/test_critic_page_flag.py
#
# Страничный флаг неутверждённого состава (frontmatter `unapproved_jira`),
# инцидент 2026-08-23: reject-all оставлял на странице блоки кода из макросов
# Confluence — форс-обёртка не может пометить fenced-код (маркер «через забор»
# нотацией не читается). Флаг решает задачу страницей, а не фрагментами.

from app.scripts.CI.critic import (
    apply_page_flag, process_file, process_text, read_page_unapproved,
)
from app.unapproved_wrap import wrap_unapproved

T = "TEAMECO-5486"

FM = (
    "---\n"
    "doc_id: '{{SIGN: Тестовая страница}}'\n"
    "status: draft\n"
    "unapproved_jira: " + T + "\n"
    "---\n"
)

FM_NO_FLAG = "---\ndoc_id: '{{SIGN: Тестовая}}'\nstatus: active\n---\n"

# Тело как в инциденте: маркеры сняты reject-ом, остались блоки кода макроса.
CODE_LEFTOVER = "\n```\nwindow.postMessage({\"type\": \"REQ\"});\n```\n"


class TestReadFlag:
    def test_reads_task_from_frontmatter(self):
        assert read_page_unapproved(FM + CODE_LEFTOVER) == T

    def test_none_without_flag(self):
        assert read_page_unapproved(FM_NO_FLAG + "\nтекст\n") is None

    def test_none_without_frontmatter(self):
        assert read_page_unapproved("unapproved_jira: " + T + "\n\nтекст\n") is None


class TestReject:
    def test_empties_body_with_code_leftover(self):
        out, count = apply_page_flag(FM + CODE_LEFTOVER, "reject", T)
        assert count == 1
        assert out == FM + "\n"          # frontmatter цел, тела нет
        assert "postMessage" not in out

    def test_reject_all_matches_any_flag(self):
        out, count = apply_page_flag(FM + CODE_LEFTOVER, "reject", None)
        assert count == 1 and out == FM + "\n"

    def test_second_reject_is_noop(self):
        once, _ = apply_page_flag(FM + CODE_LEFTOVER, "reject", T)
        twice, count = apply_page_flag(once, "reject", T)
        assert count == 0 and twice == once

    def test_foreign_task_untouched(self):
        text = FM + CODE_LEFTOVER
        out, count = apply_page_flag(text, "reject", "GBO-777")
        assert count == 0 and out == text

    def test_page_without_flag_untouched(self):
        text = FM_NO_FLAG + CODE_LEFTOVER
        out, count = apply_page_flag(text, "reject", None)
        assert count == 0 and out == text

    def test_foreign_markers_protect_body(self):
        """Чужие вставки в теле — тело не опустошаем, решает оператор."""
        text = FM + "\n{++GBO-100: чужой состав++}\n" + CODE_LEFTOVER
        out, count = apply_page_flag(text, "reject", T)
        assert count == 0 and out == text

    def test_crlf_preserved(self):
        text = (FM + CODE_LEFTOVER).replace("\n", "\r\n")
        out, count = apply_page_flag(text, "reject", T)
        assert count == 1
        assert "\n" not in out.replace("\r\n", "")   # одиночных LF не осталось
        assert out.endswith("---\r\n\r\n")


class TestApply:
    def test_removes_flag_keeps_body(self):
        text = FM + "\nсостав страницы\n"
        out, count = apply_page_flag(text, "apply", T)
        assert count == 1
        assert "unapproved_jira" not in out
        assert "состав страницы" in out
        assert "status: draft" in out            # прочий frontmatter не тронут

    def test_apply_foreign_task_untouched(self):
        text = FM + "\nсостав\n"
        out, count = apply_page_flag(text, "apply", "GBO-777")
        assert count == 0 and out == text

    def test_second_apply_is_noop(self):
        once, _ = apply_page_flag(FM + "\nсостав\n", "apply", T)
        twice, count = apply_page_flag(once, "apply", T)
        assert count == 0 and twice == once


class TestThroughProcessFile:
    """Сквозной путь: как в конвейере — маркеры и флаг вместе."""

    def _page(self, tmp_path, body):
        path = tmp_path / "страница.md"
        path.write_text(FM + body, encoding="utf-8")
        return path

    def test_reject_all_clears_page_completely(self, tmp_path):
        wrapped, rep = wrap_unapproved(
            "# Заголовок\n\nТребование.\n\n```\nкод из макроса\n```\n", T
        )
        assert rep["code_blocks_skipped"] == 1        # нотация код не помечает
        path = self._page(tmp_path, "\n" + wrapped)

        count = process_file(path, "reject", None)
        result = path.read_text(encoding="utf-8")

        assert count >= 1
        assert "Требование" not in result
        assert "код из макроса" not in result         # ← ради этого всё и делалось
        assert "unapproved_jira: " + T in result      # флаг остаётся как объяснение

    def test_apply_keeps_content_and_drops_flag(self, tmp_path):
        wrapped, _ = wrap_unapproved("Требование.\n\n```\nкод\n```\n", T)
        path = self._page(tmp_path, "\n" + wrapped)

        process_file(path, "apply", T)
        result = path.read_text(encoding="utf-8")

        assert "Требование." in result and "код" in result
        assert "{++" not in result
        assert "unapproved_jira" not in result

    def test_untouched_page_not_rewritten(self, tmp_path):
        path = tmp_path / "чужая.md"
        text = FM_NO_FLAG + "\nОбычный состав.\n"
        path.write_text(text, encoding="utf-8")
        before = path.stat().st_mtime_ns

        assert process_file(path, "reject", None) == 0
        assert path.read_text(encoding="utf-8") == text
        assert path.stat().st_mtime_ns == before
