# tests/test_critic_extractor.py
#
# Тесты Модуля 1, срез 1b-1 (ТЗ п. 4.4): режим CriticMarkup в content_extractor —
# обёртка цветных фрагментов прозы в маркеры {++/--}. Нумерация — по списку ТЗ п. 9
# (тесты 1-4, 13). Вложенность (4.5) и таблицы (4.6/4.7) — следующие срезы, здесь не тестируются.

from app.content_extractor import (
    create_critic_extractor,
    create_approved_fragments_extractor,
    create_all_fragments_extractor,
)
from app.scripts.CI.critic import process_text

CMAP = {"#9966ff": "GBO-12345"}  # rgb(153,102,255)


def _critic(html, cmap=CMAP):
    return create_critic_extractor(cmap).extract(html)


class TestInsertion:
    """1-3. Вставка слова / абзаца / раздела (ТЗ п. 9)."""

    def test_1_insert_word_mid_sentence(self):
        # ТЗ п. 1.2: хвостовой пробел должен попасть ВНУТРЬ маркера (п. 4.4).
        html = ('<p>Проверяется, что с пользователем связана хотя бы одна '
                '<span style="color: rgb(153,102,255);">действующая </span>организация.</p>')
        out = _critic(html)
        assert ("связана хотя бы одна {++GBO-12345: действующая ++}организация." in out)

    def test_2_insert_whole_paragraph(self):
        html = '<p style="color: rgb(153,102,255);">Целый абзац требования.</p>'
        out = _critic(html)
        assert "{++GBO-12345: Целый абзац требования.++}" in out
        # Блочный перенос строки остаётся снаружи маркера (не пересекаем границу блока).
        assert "требования.++}" in out and "\n\n++}" not in out

    def test_3_insert_section_with_heading(self):
        html = ('<div style="color: rgb(153,102,255);">'
                '<h2>Новый раздел</h2><p>Текст раздела.</p></div>')
        out = _critic(html)
        # Заголовок и абзац — в ОТДЕЛЬНЫХ маркерах, ни один не пересекает границу блока.
        assert "{++GBO-12345: ## Новый раздел++}" in out
        assert "{++GBO-12345: Текст раздела.++}" in out
        assert "\n\n++}" not in out


class TestDeletion:
    """4. Цветное зачёркивание бывшего чёрным текста → {--..--} (ТЗ п. 9)."""

    def test_4_colored_strikethrough_becomes_deletion(self):
        html = ('<p>Было <span style="color: rgb(153,102,255);"><s>старое условие</s></span> '
                'ново.</p>')
        out = _critic(html)
        assert "{--GBO-12345: старое условие--}" in out


class TestUnknownColor:
    """Цвет тела, отсутствующий в карте → плейсхолдер UNKNOWN-<hex> (ТЗ п. 4.2.ж)."""

    def test_unknown_color_placeholder(self):
        html = '<p>Тут <span style="color: rgb(255,102,0);">оранжевое</span> слово.</p>'
        out = _critic(html)  # #ff6600 нет в CMAP
        assert "{++UNKNOWN-ff6600: оранжевое++}" in out


class TestSyntaxProtection:
    """13. Смарт-ссылка, имена в скобках, угловые скобки и стрелки не ломаются (ТЗ п. 4.8)."""

    def test_13_special_syntax_preserved(self):
        html = ('<p>См. {{CC: [OTP] Запрос}} и &lt;атрибут&gt; и стрелки -&gt; ~&gt; '
                '<span style="color: rgb(153,102,255);">новое</span> тут.</p>')
        out = _critic(html)
        assert "{{CC: [OTP] Запрос}}" in out
        assert "<атрибут>" in out
        assert "-> ~>" in out
        assert "{++GBO-12345: новое++}" in out


class TestRoundTripOracle:
    """Оракул: reject-all(critic) == approved-экстракция (текущий ПРОМ) для инлайна."""

    def test_reject_all_equals_approved(self):
        html = ('<p>Чёрный текст с <span style="color: rgb(153,102,255);">вставкой</span> '
                'и ещё <span style="color: rgb(255,102,0);">другой</span> правкой.</p>')
        critic = _critic(html)
        rejected, _ = process_text(critic, "reject", None)
        approved = create_approved_fragments_extractor().extract(html)
        assert rejected == approved

    def test_apply_all_keeps_insertions(self):
        html = ('<p>Одна <span style="color: rgb(153,102,255);">две</span> три.</p>')
        critic = _critic(html)
        applied, _ = process_text(critic, "apply", None)
        assert "Одна две три." in applied
        assert "{++" not in applied


class TestNesting:
    """5. Вложенность двух цветов (пример ТЗ п. 4.5): уплощение под внутреннюю задачу + отчёт."""

    def test_nested_colors_flattened_under_inner_task(self):
        cmap = {"#ff99cc": "GBO-12345", "#99cc00": "GBO-67890"}  # розовый, зелёный
        html = ('<p><span style="color: rgb(255,153,204)">Организация должна быть '
                '<span style="color: rgb(153,204,0)"><s>головной</s>'
                'действующей и головной</span></span>.</p>')
        ext = create_critic_extractor(cmap)
        out = ext.extract(html)
        # Уплощено под внутреннюю (позднюю) задачу; зачёркнутый черновик отброшен.
        assert "{++GBO-67890: Организация должна быть действующей и головной++}" in out
        assert "головной++}" in out and "<s>" not in out

    def test_nesting_recorded_in_report(self):
        cmap = {"#ff99cc": "GBO-12345", "#99cc00": "GBO-67890"}
        html = ('<p><span style="color: rgb(255,153,204)">A '
                '<span style="color: rgb(153,204,0)">B</span></span></p>')
        ext = create_critic_extractor(cmap)
        ext.extract(html)
        assert len(ext._critic_report) == 1
        rec = ext._critic_report[0]
        assert set(rec["tasks"]) == {"GBO-12345", "GBO-67890"}
        assert "rgb(255,153,204)" in rec["html"]  # исходный HTML сохранён для аналитика


class TestNoRegressionWhenModeOff:
    """critic_mode выключен по умолчанию — существующие режимы не порождают маркеров."""

    def test_all_fragments_extractor_has_no_markers(self):
        html = '<p>Текст <span style="color: rgb(153,102,255);">цветной</span> тут.</p>'
        out = create_all_fragments_extractor().extract(html)
        assert "{++" not in out and "{--" not in out
        assert "цветной" in out  # include_colored сохраняет текст как есть

    def test_approved_extractor_drops_colored(self):
        html = '<p>Текст <span style="color: rgb(153,102,255);">цветной</span> тут.</p>'
        out = create_approved_fragments_extractor().extract(html)
        assert "цветной" not in out and "{++" not in out
