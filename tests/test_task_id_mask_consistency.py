# tests/test_task_id_mask_consistency.py
#
# Инцидент 2026-09-02: apply-all падал с «незакрытый или некорректный маркер {++»
# на странице с ключом DBOCORPESPLN-61419. Причина — ДВЕ маски идентификатора
# задачи, разъехавшиеся по длине ключа проекта: color_map принимал до 20 символов
# и писал такие маркеры, critic принимал до 10 и их же не признавал. То есть
# миграция выдавала разметку, которую собственный критик читать отказывался.
#
# Здесь маски сверяются между собой: расхождение снова возможно (critic намеренно
# автономен и не импортирует app.color_map), поэтому нужен явный сторож.

import re

from app.color_map import TASK_ID_RE
from app.scripts.CI.critic import TASK_ID_PATTERN, process_text

_CRITIC_FULL = re.compile(r"^" + TASK_ID_PATTERN + r"$")

# Реальные ключи из выгрузок: длина проекта 12, 7 и 3 символа.
REAL_KEYS = ["DBOCORPESPLN-61419", "DBOCORPESPLN-59857", "TEAMECO-5354", "GBO-12345"]


class TestMasksAgree:
    def test_critic_accepts_every_key_color_map_extracts(self):
        for key in REAL_KEYS:
            assert TASK_ID_RE.fullmatch(key), f"color_map не извлёк бы {key}"
            assert _CRITIC_FULL.match(key), f"critic не признаёт {key} — маски разъехались"

    def test_long_project_key_accepted(self):
        """Ключ проекта в 12 символов — тот самый случай инцидента."""
        assert _CRITIC_FULL.match("DBOCORPESPLN-61419")

    def test_masks_agree_on_generated_lengths(self):
        """Совпадение по всей длине ключа проекта, а не только на примерах."""
        for length in range(2, 21):
            key = "A" + "B" * (length - 1) + "-1"
            assert bool(TASK_ID_RE.fullmatch(key)) == bool(_CRITIC_FULL.match(key)), (
                f"расхождение масок на ключе длиной {length}: {key}")

    def test_garbage_rejected_by_both(self):
        for bad in ("gbo-1", "GBO1", "GBO-", "-123", "ЗАДАЧА-1"):
            assert not TASK_ID_RE.fullmatch(bad)
            assert not _CRITIC_FULL.match(bad)


class TestMarkerWithLongKeyWorks:
    """Сквозная проверка: маркер с длинным ключом реально применяется."""

    LINE = ('| 12 |  | {++DBOCORPESPLN-61419: Подтвердите подписание в приложении '
            '"Моя подпись" ФНС России++} |  |')

    def test_apply_unwraps_long_key_marker(self):
        out, count = process_text(self.LINE, "apply", None)
        assert count == 1
        assert "{++" not in out
        assert "Подтвердите подписание" in out

    def test_reject_removes_long_key_marker(self):
        out, count = process_text(self.LINE, "reject", None)
        assert count == 1
        assert "Подтвердите подписание" not in out

    def test_targeted_apply_matches_long_key(self):
        out, count = process_text(self.LINE, "apply", "DBOCORPESPLN-61419")
        assert count == 1 and "{++" not in out

    def test_foreign_task_untouched(self):
        out, count = process_text(self.LINE, "apply", "TEAMECO-5354")
        assert count == 0 and out == self.LINE
