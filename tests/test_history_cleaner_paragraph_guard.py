# tests/test_history_cleaner_paragraph_guard.py
"""Ограничитель ложного срабатывания чистильщика истории на абзацах.

Инцидент (2026-08-05, [БлокН2Н] «Процесс обработки сообщения о блокировке»):
содержательное требование «…выполняется создание записи в сущности История
изменений сообщения о блокировках Н2Н» содержало подстроку «история
изменений» — _remove_paragraph_history_sections принял абзац за заголовок
секции истории и удалил его ВМЕСТЕ со следующим div.table-wrap, где лежали
все 8 таблиц процесса (83 КБ → 2,8 КБ). Фикс: для абзацев — строгий детектор
(текст начинается с маркера И короткий), подстрочный поиск оставлен только
заголовочным конструкциям (expand, h1-h6, якоря).
"""

import pytest

from app.history_cleaner import remove_history_sections


INCIDENT_HTML = '''
<p class="auto-cursor-target"><strong>Важно</strong>: при любом изменении
значения атрибута <a href="/x">Сообщение о блокировках Н2Н</a>.&lt;Банковский
статус документа&gt; выполняется создание записи в сущности История изменений
сообщения о блокировках Н2Н.</p>
<div class="table-wrap"><table>
<thead><tr><th>Шаг</th><th>Название шага</th><th>Описание шага</th></tr></thead>
<tbody><tr><td>1.1</td><td>Начальное событие</td><td>Инициализация</td></tr></tbody>
</table></div>
'''

REAL_HISTORY_HTML = '''
<p><strong>История изменений:</strong></p>
<div class="table-wrap"><table>
<thead><tr><th>Дата</th><th>Описание</th><th>Автор</th><th>Задача в JIRA</th></tr></thead>
<tbody><tr><td>28.08.2024</td><td>Внесены изменения</td><td>Иванов</td><td>GBO-1</td></tr></tbody>
</table></div>
<p>Содержательный текст после истории.</p>
'''


class TestParagraphGuard:
    def test_requirement_mentioning_history_entity_survives(self):
        # Инцидентный паттерн: абзац-требование + следующие таблицы сохраняются
        result = remove_history_sections(INCIDENT_HTML, enabled=True)
        # фраза в литерале разбита переносом — сверяем по нормализованному тексту
        normalized = " ".join(result.split())
        assert "сущности История изменений сообщения о блокировках Н2Н" in normalized
        assert "Название шага" in result
        assert "Начальное событие" in result

    def test_real_history_paragraph_still_removed(self):
        # Ограничитель в обратную сторону: настоящий заголовок-абзац удаляется
        result = remove_history_sections(REAL_HISTORY_HTML, enabled=True)
        assert "История изменений" not in result
        assert "28.08.2024" not in result
        assert "Содержательный текст после истории." in result

    def test_long_paragraph_starting_with_marker_survives(self):
        # Длинный абзац, даже начинающийся с маркера, — требование, не заголовок
        html = ('<p>История изменений статусов сущности ведётся автоматически '
                'при каждом переходе; записи создаются функцией аудита и '
                'доступны в журнале операций банка.</p>'
                '<div class="table-wrap"><table><tbody><tr><td>Статус</td>'
                '<td>Переход</td></tr></tbody></table></div>')
        result = remove_history_sections(html, enabled=True)
        assert "функцией аудита" in result
        assert "Переход" in result

    def test_history_table_by_headers_still_removed(self):
        # Путь «таблица по колонкам Дата/Описание/Автор/Задача» не тронут фиксом
        html = ('<div class="table-wrap"><table>'
                '<thead><tr><th>Дата</th><th>Описание</th><th>Автор</th>'
                '<th>Задача в JIRA</th></tr></thead>'
                '<tbody><tr><td>01.01.2025</td><td>правка</td><td>Пётр</td>'
                '<td>GBO-2</td></tr></tbody></table></div>')
        result = remove_history_sections(html, enabled=True)
        assert "01.01.2025" not in result
