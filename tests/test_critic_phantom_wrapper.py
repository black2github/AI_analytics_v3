# tests/test_critic_phantom_wrapper.py
"""Фантомные цветные обёртки над ПРОМ-текстом не превращаются в маркеры.

Инцидент 2026-08-06, «[КК_ВК] Получить выписку по клиенту в КНОСИС»: в
исходнике Confluence остались спаны-обёртки редактирования

    <span color:#ff0000>                       ← фантом (не виден)
      <span color:#003366>ссылка.</span>       ← ПРОМ (тёмно-синий = чёрный)
      <span color:#ff6600>                     ← фантом (не виден)
        <span color:#003366>&lt;Комментарий&gt; =</span>   ← ПРОМ
      </span>
    </span>

Экстрактор оборачивал это в {++UNKNOWN-ff6600: …++}, то есть помечал как
ВСТАВКУ текст, который на экране чёрный (уже на ПРОМ). Последствие —
критическое: `reject`/`reject-all` удаляет вставки, значит ПРОМ-требование
исчезало бы из среза молча.

Корень: защита `_element_effectively_colored` («внутренний цвет перекрывает
внешний», CSS) стояла ПОСЛЕ ветки уплощения вложенных цветов — до неё
исполнение не доходило. Фикс: проверка видимости цвета выполняется первой,
а вложенность считается только по ВИДИМЫМ цветам.

Асимметрия: неразмеченная правка — шум в ПРОМ-срезе; удалённое ПРОМ-требование
невосстановимо. Поэтому тесты-ограничители («правки по-прежнему размечаются»)
обязательны и идут ниже.
"""

import pytest

from app.color_map import build_color_task_map
from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text


HIST = (
    '<h1>История изменений</h1><table><thead><tr><th>Дата</th><th>Описание</th>'
    '<th>Автор</th><th>Задача в JIRA</th></tr></thead><tbody>'
    '<tr><td>01.01.2025</td><td><span style="color: rgb(255,102,0)">п1</span></td>'
    '<td>И</td><td>GBO-1</td></tr>'
    '<tr><td>02.01.2025</td><td><span style="color: rgb(0,128,0)">п2</span></td>'
    '<td>И</td><td>GBO-2</td></tr></tbody></table>'
)

INCIDENT = (
    '<p><span style="color: rgb(255,0,0);">'
    '<span style="color: rgb(0,51,102);">ссылка.</span>'
    '<span style="color: rgb(255,102,0);">'
    '<span style="color: rgb(0,51,102);">&lt;Комментарий для Банка&gt; =</span>'
    '</span></span>'
    '<span style="color: rgb(0,51,102);"> "текст ошибки"</span></p>'
)


def _extract(html: str) -> str:
    result = build_color_task_map(html)
    return create_critic_extractor(result.color_to_task).extract(html)


class TestPhantomWrapper:
    def test_prom_text_under_phantom_wrappers_not_marked(self):
        out = _extract(INCIDENT)
        assert "UNKNOWN" not in out and "{++" not in out
        assert "<Комментарий для Банка> =" in out

    def test_prom_text_survives_reject_all(self):
        # Главное следствие: ПРОМ-срез сохраняет требование
        out = _extract(INCIDENT)
        rejected, _ = process_text(out, "reject-all", None)
        assert "<Комментарий для Банка> =" in rejected
        assert "ссылка." in rejected

    def test_single_phantom_wrapper_over_black(self):
        html = ('<p><span style="color: rgb(255,102,0);">'
                '<span style="color: rgb(0,51,102);">текст ПРОМ</span></span></p>')
        out = _extract(html)
        assert "{++" not in out and "текст ПРОМ" in out


class TestRealEditsStillMarked:
    """Ограничители: фикс не должен глушить настоящие правки."""

    def test_visible_task_color_marked(self):
        out = _extract(HIST + '<p><span style="color: rgb(255,102,0)">новое требование</span></p>')
        assert "{++GBO-1: новое требование++}" in out

    def test_visible_nested_colors_flattened_to_inner(self):
        out = _extract(HIST + '<p><span style="color: rgb(255,102,0)">правка-1 '
                              '<span style="color: rgb(0,128,0)">правка-2</span></span></p>')
        assert "{++GBO-2:" in out and "правка-1" in out and "правка-2" in out

    def test_phantom_wrapper_over_visible_task_color(self):
        # Внешняя обёртка-фантом, внутри — видимый цвет задачи: правка сохраняется
        out = _extract(HIST + '<p><span style="color: rgb(255,0,0)">'
                              '<span style="color: rgb(0,128,0)">правка задачи 2</span></span></p>')
        assert "{++GBO-2: правка задачи 2++}" in out

    def test_unknown_marker_still_emitted_for_visible_unmapped_color(self):
        # Видимый цвет, которого нет в истории → UNKNOWN остаётся (это сигнал аналитику)
        out = _extract('<p><span style="color: rgb(0,128,0)">видимый цветной фрагмент</span></p>')
        assert "{++UNKNOWN-008000: видимый цветной фрагмент++}" in out


EDIT = '<span style="color: rgb(255,102,0)">%s</span>'
PHANTOM = ('<span style="color: rgb(255,102,0)">'
           '<span style="color: rgb(0,51,102)">%s</span></span>')


class TestBothRenderingPathsIntact:
    """Проверка видимости живёт в ОБЩЕМ узле решения (_critic_marker_for), а формы
    разметки у путей разные и обязаны такими остаться (ТЗ п. 4.4/4.6/4.7):
      • чистый markdown  — текстовый маркер {++ID: …++};
      • сырой HTML-остров — <span class="critic-ins" data-task="ID">;
      • цельно-цветная строка — служебный столбец `status` (markdown) или
        <tr class="critic-row-ins" data-task="ID"> (HTML).
    Общий узел решает ЧТО есть правка, путь решает КАК её записать."""

    def test_markdown_inline_form(self):
        out = _extract(HIST + f'<p>{EDIT % "настоящая правка"}</p>')
        assert "{++GBO-1: настоящая правка++}" in out

    def test_html_island_inline_form(self):
        # colspan форсирует рендер таблицы сырым HTML
        out = _extract(HIST + f'<h2>Р</h2><table><tbody><tr><td colspan="2">{EDIT % "правка"}</td>'
                              f'<td>обычный</td></tr></tbody></table>')
        assert '<span class="critic-ins" data-task="GBO-1">правка</span>' in out

    def test_markdown_row_level_status_column(self):
        out = _extract(HIST + '<h2>Р</h2><table><tbody>'
                              '<tr><td>обычная</td><td>строка</td></tr>'
                              f'<tr><td>{EDIT % "новая"}</td><td>{EDIT % "строка"}</td></tr>'
                              '</tbody></table>')
        assert "| +GBO-1 |" in out

    def test_html_row_level_tr_attribute(self):
        out = _extract(HIST + '<h2>Р</h2><table><tbody>'
                              '<tr><td colspan="2">шапка</td><td>x</td></tr>'
                              f'<tr><td>{EDIT % "новая"}</td><td>{EDIT % "строка"}</td>'
                              f'<td>{EDIT % "ещё"}</td></tr></tbody></table>')
        assert '<tr class="critic-row-ins" data-task="GBO-1">' in out

    # --- фантом игнорируется во ВСЕХ трёх механизмах ---

    def test_phantom_ignored_in_markdown_table(self):
        out = _extract(HIST + f'<h2>Р</h2><table><tbody><tr><td>{PHANTOM % "ПРОМ"}</td>'
                              '<td>обычный</td></tr></tbody></table>')
        assert "{++" not in out.split("Р\n")[-1] and "ПРОМ" in out

    def test_phantom_ignored_in_html_island(self):
        out = _extract(HIST + f'<h2>Р</h2><table><tbody><tr><td colspan="2">{PHANTOM % "ПРОМ"}</td>'
                              '<td>обычный</td></tr></tbody></table>')
        assert "critic-ins" not in out and "ПРОМ" in out

    def test_phantom_row_not_marked_as_row_insert(self):
        out = _extract(HIST + '<h2>Р</h2><table><tbody>'
                              '<tr><td colspan="2">шапка</td><td>x</td></tr>'
                              f'<tr><td>{PHANTOM % "ПРОМ-1"}</td><td>{PHANTOM % "ПРОМ-2"}</td>'
                              f'<td>{PHANTOM % "ПРОМ-3"}</td></tr></tbody></table>')
        assert "critic-row-ins" not in out
        assert all(f"ПРОМ-{i}" in out for i in (1, 2, 3))
