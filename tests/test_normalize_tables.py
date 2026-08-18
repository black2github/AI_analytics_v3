# tests/test_normalize_tables.py
"""Нормализатор сырых HTML-таблиц (Д-21, проход 1): сетка, протяжка,
иерархия по профилю, счётный инвариант нулевых потерь."""

import pytest
from bs4 import BeautifulSoup

from app.scripts.CI.normalize_tables import (
    Profile, _title_key, assert_invariant, blocks_profile_applies, build_flat,
    check_file, expand_grid, find_top_tables, header_blocks, normalize_file,
    check_behavior_nesting, check_behavior_numbering,
    check_source_tables, check_title, html_param_names, render_sample,
    source_role_literals, validate_columns,
)


def grid_of(html: str):
    table = BeautifulSoup(html, "html.parser").find("table")
    return expand_grid(table)


ROWSPAN_HTML = """
<table>
<tr><th>Узел</th><th>Параметр</th><th>Тип</th></tr>
<tr><td rowspan="2">RelPerson</td><td>Name</td><td>Строка</td></tr>
<tr><td>INN</td><td>Число</td></tr>
</table>
"""


class TestGrid:
    def test_rowspan_stretched(self):
        g = grid_of(ROWSPAN_HTML)
        assert g[1][0] == "RelPerson" and g[2][0] == "RelPerson"
        assert g[2][1] == "INN"  # колонка не съехала

    def test_colspan_expanded(self):
        g = grid_of('<table><tr><td colspan="3">Шапка</td><td>X</td></tr>'
                    '<tr><td>a</td><td>b</td><td>c</td><td>d</td></tr></table>')
        assert g[0] == ["Шапка", "Шапка", "Шапка", "X"]
        assert g[1] == ["a", "b", "c", "d"]

    def test_links_become_markdown(self):
        g = grid_of('<table><tr><td><a href="/x">Заявка</a> текст</td></tr></table>')
        assert g[0][0] == "[Заявка](/x) текст"

    def test_bold_and_nested_indent_preserved(self):
        # Замечание пользователя (итерация 5): «Правила заполнения» теряли
        # форматирование — жирные Если/то/иначе и NBSP-отступы вложенности.
        # Проход 1 отвечает за структуру, включая отступы условий.
        html = ('<table><tr><td>'
                '<p><strong>Если</strong> A = "X", <strong>то</strong>:</p>'
                '<p>    <strong>Если</strong> B, <strong>то</strong> C</p>'
                '<p>    <strong>иначе</strong> D</p>'
                '</td></tr></table>')
        g = grid_of(html)
        assert g[0][0] == ('**Если** A = "X", **то**:<br>'
                           '&nbsp;&nbsp;&nbsp;&nbsp;**Если** B, **то** C<br>'
                           '&nbsp;&nbsp;&nbsp;&nbsp;**иначе** D')

    def test_em_preserved(self):
        g = grid_of('<table><tr><td>обычный <em>курсив</em> текст</td></tr></table>')
        assert g[0][0] == "обычный *курсив* текст"

    def test_pipe_escaped_and_br(self):
        g = grid_of('<table><tr><td><p>a|b</p><p>вторая</p></td></tr></table>')
        assert g[0][0] == "a\\|b<br>вторая"

    def test_ragged_rows_padded(self):
        g = grid_of('<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>')
        assert g[1] == ["c", ""]


class TestProfileBuild:
    def test_hierarchy_path_joined_without_adjacent_dups(self):
        g = grid_of(ROWSPAN_HTML)
        p = Profile(name="t", header_rows=1, hierarchy_cols=[0, 1],
                    path_title="XML-элемент", keep_cols=[(2, "Тип")])
        headers, rows = build_flat(g, p)
        assert headers == ["XML-элемент", "Тип"]
        assert rows[0] == ["RelPerson/Name", "Строка"]
        assert rows[1] == ["RelPerson/INN", "Число"]

    def test_invariant_counts(self):
        g = grid_of(ROWSPAN_HTML)
        p = Profile(header_rows=1, hierarchy_cols=[0, 1], keep_cols=[(2, "Тип")])
        _, rows = build_flat(g, p)
        assert "✓" in assert_invariant(g, p, rows)

    def test_passthrough_without_profile(self):
        g = grid_of(ROWSPAN_HTML)
        headers, rows = build_flat(g, Profile())
        assert headers == ["Узел", "Параметр", "Тип"]
        assert len(rows) == 2 and rows[1][0] == "RelPerson"


LADDER_HTML = """
<table>
<tr><th colspan="3">XML структура</th><th>Тип</th></tr>
<tr><td colspan="3">Message</td><td>контейнер</td></tr>
<tr><td></td><td colspan="2">MessageHeader</td><td>контейнер</td></tr>
<tr><td></td><td></td><td>MessageId</td><td>GUID</td></tr>
<tr><td></td><td colspan="2">MessageBody</td><td>контейнер</td></tr>
<tr><td></td><td></td><td>ObjectID</td><td>string</td></tr>
</table>
"""


class TestLadder:
    def test_prefix_inherited_and_cut(self):
        g = grid_of(LADDER_HTML)
        p = Profile(name="ladder", header_rows=1, hierarchy_cols=[0, 1, 2],
                    ladder=True, keep_cols=[(3, "Тип")])
        _, rows = build_flat(g, p)
        paths = [r[0] for r in rows]
        assert paths == [
            "Message",
            "Message/MessageHeader",
            "Message/MessageHeader/MessageId",
            "Message/MessageBody",              # префикс обрезан до уровня
            "Message/MessageBody/ObjectID",
        ]

    def test_ladder_invariant_holds(self):
        g = grid_of(LADDER_HTML)
        p = Profile(header_rows=1, hierarchy_cols=[0, 1, 2], ladder=True,
                    keep_cols=[(3, "Тип")])
        _, rows = build_flat(g, p)
        assert "✓" in assert_invariant(g, p, rows)


# Реальная геометрия страниц ЕСК: шапка нарезана colspan-блоками, глубина
# элемента задаётся стартовой колонкой, роли — блоками, а не индексами.
# Именно на этой форме режим индексов давал ~30 % брака (разжалование
# итерации 3, 2026-08-06): текст названий утекал в путь, пути — в «Название».
BLOCKS_HTML = """
<table>
<tr>
  <th colspan="4">XML структура</th><th colspan="2">Название параметра</th>
  <th colspan="2">Тип данных</th><th colspan="2">Обязате<br>льность</th>
  <th colspan="2">Крат<br>ность</th><th colspan="2">Комментарий</th>
</tr>
<tr>
  <td colspan="4">ObjectBody/*</td><td colspan="2">Блок с телом запроса</td>
  <td colspan="2"></td><td colspan="2">О</td><td colspan="2">[1]</td><td colspan="2"></td>
</tr>
<tr>
  <td></td><td colspan="3">/Context/*</td><td colspan="2">Блок: Содержимое</td>
  <td colspan="2"></td><td colspan="2">О</td><td colspan="2">[0-1]</td><td colspan="2"></td>
</tr>
<tr>
  <td></td><td></td><td colspan="2">/ProcessGUID</td><td colspan="2">GUID процесса</td>
  <td colspan="2">GUID</td><td colspan="2">Н</td><td colspan="2">[0..1]</td>
  <td colspan="2">уникальный идентификатор.</td>
</tr>
<tr>
  <td></td><td></td><td colspan="2">все поля внутри блока передаются в формате p_in</td>
  <td colspan="2"></td><td colspan="2"></td><td colspan="2"></td><td colspan="2"></td>
  <td colspan="2"></td>
</tr>
</table>
"""

BLOCKS_PROFILE = Profile(name="t", header_rows=1, blocks=True, path_block=0,
                         ladder=True, path_title="XML-элемент", path_join="/")


class TestHeaderBlocks:
    def test_blocks_detected_from_header_runs(self):
        blocks = header_blocks(grid_of(BLOCKS_HTML))
        titles = [t for _s, _e, t in blocks]
        assert titles[0] == "XML структура" and titles[1] == "Название параметра"
        assert blocks[0][0] == 0 and blocks[1][0] == 4      # границы по colspan

    def test_title_key_strips_br_inside_word(self):
        # «Крат<br>ность» — роль не находилась, роли колонок съезжали
        assert _title_key("Крат<br>ность") == "кратность"
        assert _title_key("Обязате<br>льность") == "обязательность"


class TestAnchoredAssignment:
    def _rows(self):
        return build_flat(grid_of(BLOCKS_HTML), BLOCKS_PROFILE)

    def test_roles_land_in_own_columns(self):
        headers, rows = self._rows()
        assert headers[0] == "XML-элемент"
        # строка-лист: путь, название, тип, обязательность, кратность, комментарий
        leaf = rows[2]
        assert leaf[0] == "ObjectBody/Context/ProcessGUID"  # «*» контейнеров чистится по умолчанию
        assert leaf[1] == "GUID процесса"
        assert leaf[2] == "GUID"
        assert leaf[3] == "Н"
        assert leaf[4] == "[0..1]"
        assert "уникальный идентификатор." in leaf[5]

    def test_container_row_without_type(self):
        # У контейнера тип пуст — описание не должно занять колонку типа
        _headers, rows = self._rows()
        assert rows[0][0] == "ObjectBody"
        assert rows[0][1] == "Блок с телом запроса"
        assert rows[0][2] == ""          # тип пуст
        assert rows[0][3] == "О" and rows[0][4] == "[1]"

    def test_cardinality_dash_form_is_anchor(self):
        # «[0-1]» — легальная форма; без неё якорь не срабатывал и хвост уезжал в путь
        _headers, rows = self._rows()
        assert rows[1][4] == "[0-1]"
        assert rows[1][0] == "ObjectBody/Context"

    def test_prose_inside_path_block_not_in_path(self):
        # «все поля внутри блока…» — пояснение, а не уровень иерархии:
        # в путь не идёт (иначе станет префиксом потомков) и не теряется
        _headers, rows = self._rows()
        prose_row = rows[3]
        assert "все поля" not in prose_row[0]
        assert any("все поля" in c for c in prose_row[1:])

    def test_ladder_prefix_not_polluted_by_prose(self):
        _headers, rows = self._rows()
        assert all(not r[0].startswith("все поля") for r in rows)

    def test_bold_anchors_still_recognized(self):
        # Брак итерации 6-бис (2026-08-07): после сохранения форматирования
        # в cell_text жирные «**О**»/«**[1]**» переставали распознаваться
        # якорями, и название с обязательностью утекали в путь. Разметка
        # снимается в путях и якорных колонках, но ОСТАЁТСЯ в свободных.
        html = """
<table>
<tr>
  <th colspan="4">XML структура</th><th colspan="2">Название параметра</th>
  <th colspan="2">Тип данных</th><th colspan="2">Обязате<br>льность</th>
  <th colspan="2">Крат<br>ность</th><th colspan="2">Комментарий</th>
</tr>
<tr>
  <td colspan="4"><strong>ObjectBody/*</strong></td>
  <td colspan="2"><strong>Блок с телом запроса</strong></td>
  <td colspan="2"></td><td colspan="2"><strong>О</strong></td>
  <td colspan="2"><strong>[1]</strong></td>
  <td colspan="2"><strong>Если</strong> запрос — заполнить</td>
</tr>
</table>
"""
        _headers, rows = build_flat(grid_of(html), BLOCKS_PROFILE)
        row = rows[0]
        assert row[0] == "ObjectBody"            # путь чист от «**» и «*»-хвоста
        assert row[1] == "Блок с телом запроса"  # название чисто
        assert row[3] == "О" and row[4] == "[1]" # якоря распознаны и чисты
        assert "**Если**" in row[5]              # свободная колонка хранит жирный


# Таблица другой природы в том же файле: перечень кодов отказов —
# без кратности/обязательности в шапке, с rowspan-примечанием.
# Применение к ней XML-профиля склеивало «№ п/п» и «Код отказа» в
# псевдо-путь «1/EIO1» (брак итерации 6-тер, 2026-08-07).
CODES_HTML = """
<table>
<tr><th>№ п/п</th><th>Код отказа</th><th>Текст отказа</th><th>Примечание</th></tr>
<tr><td>1</td><td>EIO1</td><td>Физ лицо не связано с клиентом</td>
    <td rowspan="2">Коды не анализируются</td></tr>
<tr><td>2</td><td>EIO2</td><td>Физ лицо имеет недействительный ДУЛ</td></tr>
</table>
"""


class TestTokenAndMarkupClasses:
    """Классы содержимого, а не перечисление случаев: незнакомый «тег» —
    это токен-данные (словарь HTML замкнут); s/u/img — классы разметки."""

    def test_token_tag_survives(self):
        # <GUID> — токен-имя из источника; парсер HTML съедал его молча.
        # Путь честный — через find_top_tables (там живёт защита токенов).
        html = ('<table><tr><th>Поле</th></tr>'
                '<tr><td>значение <GUID> из ЕСК</td></tr></table>')
        table = find_top_tables(html)[0]
        _h, rows = build_flat(expand_grid(table), Profile())
        assert "<GUID>" in rows[0][0]

    def test_real_html_tags_not_escaped(self):
        # тест на НЕсрабатывание: настоящий HTML разбирается как разметка
        html = ('<table><tr><th>Поле</th></tr>'
                '<tr><td><strong>жирный</strong> и <s>снятый</s></td></tr></table>')
        _h, rows = build_flat(grid_of(html), Profile())
        assert rows[0][0] == "**жирный** и ~~снятый~~"

    def test_underline_and_img_preserved(self):
        html = ('<table><tr><th>Поле</th></tr>'
                '<tr><td><u>важно</u> <img src="pic.png" alt="схема"/></td></tr></table>')
        _h, rows = build_flat(grid_of(html), Profile())
        assert "<u>важно</u>" in rows[0][0]
        assert "![схема](pic.png)" in rows[0][0]


class TestCheckMode:
    """--check: колонные валидаторы поверх готовой карточки — ловит класс
    «якорная колонка переписана при перекладке» (кратность [1] → 1,
    регресс итерации 6-кватер, 2026-08-07)."""

    GOOD = (
        "# Карточка\n\n"
        "| XML-элемент | Название | Тип | Обяз. | Кратность | Правила |\n"
        "|---|---|---|---|---|---|\n"
        "| `ObjectBody/*` | Блок с телом запроса |  | Да | [1] |  |\n"
        "| `ObjectBody/ProcessGUID` | GUID процесса | GUID | Нет | [0..1] | = GUID |\n"
    )

    def _check(self, text, tmp_path):
        p = tmp_path / "card.md"
        p.write_text(text, encoding="utf-8")
        return check_file(p)

    def test_clean_card_passes(self, tmp_path):
        _report, ok = self._check(self.GOOD, tmp_path)
        assert ok

    def test_unbracketed_cardinality_caught(self, tmp_path):
        _report, ok = self._check(self.GOOD.replace("[1]", "1").replace("[0..1]", "0..1"),
                                  tmp_path)
        assert not ok

    def test_rewritten_obligation_caught(self, tmp_path):
        # «Да» → произвольный текст: якорная колонка переписана
        _report, ok = self._check(self.GOOD.replace("| Да |", "| обязателен |"),
                                  tmp_path)
        assert not ok

    def test_roleless_table_skipped(self, tmp_path):
        # тест на НЕсрабатывание (Д-22): таблица кодов без ролей — не брак
        codes = (
            "| Код отказа | Текст отказа | Примечание |\n"
            "|---|---|---|\n"
            "| EIO1 | Физ лицо не связано с клиентом | не анализируются |\n"
        )
        report, ok = self._check(codes, tmp_path)
        assert ok
        assert any("пропущена" in l for l in report)

    def test_bold_in_rules_not_flagged(self, tmp_path):
        # форматирование свободных колонок — не брак
        _report, ok = self._check(
            self.GOOD.replace("| = GUID |", "| **Если** запрос — **то** GUID |"),
            tmp_path)
        assert ok


class TestLinkUrlNotLiteral:
    """Сверка markdown-ссылок — по тексту-названию, URL не литерал: замена
    живого URL Confluence относительной ссылкой на карточку не должна
    валить сверку паспорта (конфликт правила и гейта, OQ-029)."""

    SOURCE = (
        "# Общая информация о методе\n\n"
        "| **Название метода** | Загрузка файла |\n"
        "| --- | --- |\n"
        "| **Где используется** | На шаге [Функция просмотра](https://confluence.int.example/pages/1) |\n"
        "| **Alias** | /upload |\n"
    )

    def test_replaced_link_passes(self):
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Название метода** | Загрузка файла |\n"
                "| **Где используется** | На шаге Функция просмотра |\n"
                "| **Alias** | /upload |\n")
        _report, ok = check_source_tables(card, self.SOURCE)
        assert ok

    def test_lost_link_text_still_caught(self):
        # тест на НЕсрабатывание послабления: потеря ТЕКСТА ссылки — брак
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Название метода** | Загрузка файла |\n"
                "| **Где используется** | На шаге |\n"
                "| **Alias** | /upload |\n")
        _report, ok = check_source_tables(card, self.SOURCE)
        assert not ok

    def test_link_with_bracketed_text_near_unpaired_bracket(self):
        # правило трёх случаев требует относительную ссылку; текст ссылки
        # содержит «[Файловый сервис]», а раньше по карточке есть непарный
        # «[1]» (кратность) — поиск первого «](» склеивал чужой текст
        # и валил правильную карточку (инцидент intc-014)
        source = (
            "# Общая информация о методе\n\n"
            "| **Название метода** | Создание архива |\n"
            "| --- | --- |\n"
            "| **При вызове метода** | Инициирование подпроцесса [\\[Файловый сервис\\] Клиент: Выгрузка архива (асинхрон)](https://confluence.int.example/pages/5) (шаг №3) |\n"
            "| **Alias** | /archive |\n"
        )
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Кратность** | [1] |\n"
                "| **Название метода** | Создание архива |\n"
                "| **При вызове метода** | Инициирование подпроцесса [[Файловый сервис] Клиент: Выгрузка архива (асинхрон)](../process/prc-004-client-download-archive-async.md) (шаг №3) |\n"
                "| **Alias** | /archive |\n")
        _report, ok = check_source_tables(card, source)
        assert ok

    def test_escaped_brackets_normalized(self):
        # HTML→MD-конвертер выгрузки экранирует скобки в тексте ссылки
        # (\[ДСФ_ЭКО\]); карточка пишет чистый текст — не брак
        source = (
            "# Общая информация о методе\n\n"
            "| **Название метода** | Загрузка файла |\n"
            "| --- | --- |\n"
            "| **Где используется** | На шаге 5 [\\[ДСФ_ЭКО\\] Клиент: Функция скачивания](https://confluence.int.example/pages/9) |\n"
            "| **Alias** | /upload |\n"
        )
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Название метода** | Загрузка файла |\n"
                "| **Где используется** | На шаге 5 [ДСФ_ЭКО] Клиент: Функция скачивания |\n"
                "| **Alias** | /upload |\n")
        _report, ok = check_source_tables(card, source)
        assert ok

    def test_escaped_brackets_loss_still_caught(self):
        # тест на НЕсрабатывание послабления: значение с \[..\] всё равно
        # обязано присутствовать — потеря остаётся браком
        source = (
            "# Общая информация о методе\n\n"
            "| **Название метода** | Загрузка файла |\n"
            "| --- | --- |\n"
            "| **Где используется** | На шаге 5 [\\[ДСФ_ЭКО\\] Клиент: Функция скачивания](https://confluence.int.example/pages/9) |\n"
            "| **Alias** | /upload |\n"
        )
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Название метода** | Загрузка файла |\n"
                "| **Где используется** | На шаге 5 |\n"
                "| **Alias** | /upload |\n")
        _report, ok = check_source_tables(card, source)
        assert not ok

    def test_bracket_inside_link_text(self):
        # названия Confluence бывают с «]» внутри текста ссылки — regex
        # [^\]]* на таком обрезал значение, посимвольный разбор — нет
        source = (
            "# Общая информация о методе\n\n"
            "| **Название метода** | Загрузка файла |\n"
            "| --- | --- |\n"
            "| **Где используется** | См. [Метод [v2] выгрузки](https://confluence.int.example/pages/7) |\n"
        )
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Название метода** | Загрузка файла |\n"
                "| **Где используется** | См. Метод [v2] выгрузки |\n")
        _report, ok = check_source_tables(card, source)
        assert ok


class TestBehaviorNesting:
    """Профиль вложенности «Поведения»: маркеры дословно, уровень — из
    разметки источника (margin-left/списки), нормализация рангами."""

    SRC = (
        "# Ф\n\n<table><tr><th>Что делает функция</th><td>"
        '<p><strong>1)</strong> Если критично, то:</p>'
        '<p style="margin-left: 40.0px"><strong>1.1)</strong> Найти номер</p>'
        '<p style="margin-left: 40.0px"><strong>1.2)</strong> Разместить</p>'
        "<p>иначе:</p>"
        '<p style="margin-left: 40.0px"><strong>1.3)</strong> Отказ</p>'
        "<p><strong>2)</strong> Завершение</p>"
        "</td></tr></table>\n"
    )

    def test_matching_profile_ok(self):
        card = ("## Поведение\n\n"
                "1. **Если** критично, **то:**\n"
                "   1.1. Найти номер\n"
                "   1.2. Разместить\n"
                "   **иначе:**\n"
                "   1.3. Отказ\n"
                "2. Завершение\n")
        report, ok = check_behavior_nesting(card, self.SRC)
        assert ok and "совпадает" in report[0]

    def test_flattened_card_caught(self):
        card = ("## Поведение\n\n"
                "1. **Если** критично, **то:**\n"
                "2. Найти номер\n"          # 1.1 потерян, плоско
                "3. Разместить\n")
        _report, ok = check_behavior_nesting(card, self.SRC)
        assert not ok

    def test_lost_step_caught(self):
        card = ("## Поведение\n\n"
                "1. **Если** критично, **то:**\n"
                "   1.1. Найти номер\n"
                "   1.3. Отказ\n"
                "2. Завершение\n")           # 1.2 потерян
        report, ok = check_behavior_nesting(card, self.SRC)
        assert not ok and any("1.2" in r for r in report)

    def test_flat_behavior_no_noise(self):
        # тест на НЕсрабатывание: плоское поведение без вложенности
        src = ("# Ф\n\n<table><tr><th>Что делает функция</th><td>"
               "<p><strong>1)</strong> Сделать</p>"
               "<p><strong>2)</strong> Завершить</p></td></tr></table>\n")
        card = "## Поведение\n\n1. Сделать\n2. Завершить\n"
        _report, ok = check_behavior_nesting(card, src)
        assert ok

    def test_source_without_behavior_cell_skipped(self):
        # тест на НЕсрабатывание: у контрактов ячейки «Что делает» нет
        src = "# Метод\n\n<table><tr><th>Параметр</th><td>x</td></tr></table>\n"
        report, ok = check_behavior_nesting("## Поведение\n\n1. Шаг\n", src)
        assert ok and not report

    def test_letter_markers_with_margin(self):
        # маркеры не обязаны быть числовыми: A) / B) с отступом
        src = ("# Ф\n\n<table><tr><th>Что делает функция</th><td>"
               "<p><strong>1)</strong> Цикл:</p>"
               '<p style="margin-left: 40.0px"><strong>A)</strong> Взять</p>'
               '<p style="margin-left: 40.0px"><strong>B)</strong> Положить</p>'
               "</td></tr></table>\n")
        good = ("## Поведение\n\n1. Цикл:\n   A) Взять\n   B) Положить\n")
        flat = ("## Поведение\n\n1. Цикл:\nA) Взять\nB) Положить\n")
        assert check_behavior_nesting(good, src)[1]
        assert not check_behavior_nesting(flat, src)[1]


class TestBehaviorNumbering:
    """Самосогласованность карточки: глубина точечного номера ↔ отступ."""

    def test_consistent_ok(self):
        card = ("## Поведение\n\n- **1.** Шаг\n  - **1.1.** Вложенный\n"
                "- **2.** Конец\n")
        _report, ok = check_behavior_numbering(card)
        assert ok

    def test_flattened_dotted_caught(self):
        card = "## Поведение\n\n1. Шаг\n1.1. Вложенный без отступа\n"
        report, ok = check_behavior_numbering(card)
        assert not ok and "1.1" in report[0]

    def test_non_dotted_markers_no_noise(self):
        # «Шаг №1/№2» голым текстом — глубина в номере не закодирована, но
        # строки не являются элементами списка → рендер склеит: брак
        card = "## Поведение\n\nШаг №1: Сделать\nШаг №2: Завершить\n"
        report, ok = check_behavior_numbering(card)
        assert not ok and "склеит" in report[0]

    def test_paragraph_steps_with_blank_lines_ok(self):
        # тест на НЕсрабатывание: шаги-абзацы, отделённые пустыми строками,
        # рендерятся самостоятельно (стиль «Шаг № N.» file-storage)
        card = ("## Поведение\n\n"
                "Шаг № 1. Вызвать метод генерации токена.\n\n"
                "- `<action>` = \"\"\n\n"
                "Шаг № 2. Инициировать процесс выгрузки.\n")
        report, ok = check_behavior_numbering(card)
        assert ok and not report

    def test_dash_wrapped_verbatim_markers_ok(self):
        # канонный стиль: пункт создаёт «-», дословный маркер — текстом
        card = ("## Поведение\n\n"
                "- **1)** **Если** критично, **то:**\n"
                "  - **1.1)** Найти номер\n"
                "  - **1.2)** Разместить\n"
                "  - **иначе:**\n"
                "  - **1.3)** Отказ\n"
                "- **2)** Завершение\n")
        report, ok = check_behavior_numbering(card)
        assert ok and not report

    def test_composite_marker_without_list_item_caught(self):
        # составной маркер с отступом без «-» — рендер склеит в абзац
        card = ("## Поведение\n\n"
                "1) **Если** критично, **то:**\n"
                "   1.1) Найти номер\n"
                "   1.2) Разместить\n")
        report, ok = check_behavior_numbering(card)
        assert not ok and any("склеит" in r for r in report)


class TestMethodBehaviorCell:
    """Алгоритм из ячейки «Что делает метод»: сверяется с карточкой,
    несущей раздел «Поведение» (функция метода FUN-SYS); карточка
    контракта INTC без раздела — законный skip."""

    SRC = ("# Метод\n\n<table><tr><td><strong>Что делает метод</strong></td>"
           "<td><p><strong>1)</strong> Взять клиента</p>"
           '<p style="margin-left: 40.0px"><strong>1.1)</strong> Выбрать блокировки</p>'
           "<p><strong>2)</strong> Вернуть массив</p></td></tr></table>\n")

    def test_intc_card_without_behavior_skipped(self):
        card = "---\nid: INTC-001\n---\n## 1. Краткое описание\n\nКонтракт.\n"
        report, ok = check_behavior_nesting(card, self.SRC)
        assert ok and not report

    def test_fun_sys_card_checked(self):
        good = ("## Поведение\n\n- **1)** Взять клиента\n"
                "  - **1.1)** Выбрать блокировки\n- **2)** Вернуть массив\n")
        flat = ("## Поведение\n\n- **1)** Взять клиента\n"
                "- **2)** Вернуть массив\n")   # 1.1 потерян
        assert check_behavior_nesting(good, self.SRC)[1]
        assert not check_behavior_nesting(flat, self.SRC)[1]


class TestQuotedLiterals:
    """Кавычечные литералы источника (сообщения, кнопки, значения) обязаны
    присутствовать в карточке дословно — механизируемая часть класса
    «свободный текст не сторожится»."""

    def test_lost_message_caught(self):
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = ('---\ntitle: x\n---\nЕсли записей нет, отображается сообщение '
               '"Записей пока нет" (см. макет ЭФ)\n')
        report, ok = check_quoted_literals("# карточка без сообщения\n", src)
        assert not ok and "Записей пока нет" in report[0]

    def test_paraphrase_caught(self):
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = '---\nt: x\n---\nКатегория «Ошибка обработки» выбрана всегда\n'
        card = "Категория «Ошибки обработки» выбрана всегда\n"  # пересказ
        _report, ok = check_quoted_literals(card, src)
        assert not ok

    def test_all_present_ok(self):
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = ('---\nt: x\n---\nКнопка "Сохранить"; статус «Исполнен»\n')
        card = 'Кнопка «Сохранить» переводит в статус "Исполнен".\n'
        report, ok = check_quoted_literals(card, src)
        assert ok and "все 2" in report[0]

    def test_url_literals_not_required(self):
        # тест на НЕсрабатывание: литералы с URL/figma не требуются
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = '---\nt: x\n---\nсм. "https://figma.com/x" и «страницу confluence»\n'
        report, ok = check_quoted_literals("# пусто\n", src)
        assert ok and not report


class TestLayoutTableNotRequired:
    """Таблица макетов ЭФ (Figma/размерности) — служебная: её значения в
    карточке не требуются (шаблон запрещает Figma/Confluence-URL)."""

    def test_figma_layout_table_skipped(self):
        src = ("# ЭФ\n\n"
               "| Размерность экрана | Cсылки на Figma |\n|---|---|\n"
               "| XL - Web | https://figma.com/x |\n"
               "| M - Tablet | https://figma.com/y |\n")
        card = "# карточка без макетов\n"
        _report, ok = check_source_tables(card, src)
        assert ok

    def test_see_below_pointer_row_skipped(self):
        # строка-указатель «Логика работы | …см. ниже» — навигация,
        # дублирующая целевой раздел: значение в карточке не требуется
        src = ("# Агент\n\n"
               "| **Назначение:** | Повторная выгрузка заявок |\n"
               "|---|---|\n"
               "| **Логика работы:** | Схему и описание процесса работы агента см. ниже. |\n"
               "| **Расписание:** | раз в 5 минут |\n")
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Назначение:** | Повторная выгрузка заявок |\n"
                "| **Расписание:** | раз в 5 минут |\n")
        _report, ok = check_source_tables(card, src)
        assert ok

    def test_layout_row_in_passport_skipped(self):
        # макеты — СТРОКОЙ паспортной таблицы (вложенный HTML со ссылками)
        src = ("# ЭФ\n\n"
               "| **Зачем нужна ЭФ** | Ручное изменение статуса |\n"
               "|---|---|\n"
               '| **Макеты ЭФ:** | <table><tr><th>Размерность экрана</th><th>Cсылки на Figma</th></tr><tr><td>XL - Web</td><td>https://www.figma.com/design/x</td></tr></table> |\n'
               "| **Кому доступна** | Пользователь Банка |\n")
        card = ("| Поле | Значение |\n|---|---|\n"
                "| **Зачем нужна ЭФ** | Ручное изменение статуса |\n"
                "| **Кому доступна** | Пользователь Банка |\n")
        _report, ok = check_source_tables(card, src)
        assert ok

    def test_ordinary_table_still_required(self):
        # тест на НЕсрабатывание: обычная таблица сторожится по-прежнему
        src = ("# ЭФ\n\n| Колонка | Формат |\n|---|---|\n"
               "| Дата статуса | ДД.ММ.ГГГГ |\n| Номер | Строка |\n")
        _report, ok = check_source_tables("# пусто\n", src)
        assert not ok


class TestStepMarkers:
    """Полнота маркеров шагов: номера — литералы; перенумерация и слияние
    шагов — потеря (29 → 22 своих при зелёном гейте, src-locks)."""

    SRC = ("# Процесс\n\n<table><tr><th>№</th><th>Шаг</th></tr>"
           "<tr><td><strong>1.1</strong></td><td>Принять файл</td></tr>"
           "<tr><td><strong>1.2</strong></td><td>Проверить</td></tr>"
           "<tr><td><strong>1.22</strong></td><td>Сохранить</td></tr>"
           "</table>\n")

    def test_all_markers_present_ok(self):
        from app.scripts.CI.normalize_tables import check_step_markers
        card = "| 1.1 | Принять файл |\n| 1.2 | Проверить |\n| 1.22 | Сохранить |\n"
        report, ok = check_step_markers(card, self.SRC)
        assert ok and "все 3" in report[0]

    def test_renumbering_caught(self):
        from app.scripts.CI.normalize_tables import check_step_markers
        card = "| 1 | Принять файл |\n| 2 | Проверить |\n| 3 | Сохранить |\n"
        report, ok = check_step_markers(card, self.SRC)
        assert not ok and "перенумерация" in report[0]

    def test_marker_boundary_not_substring(self):
        # «1.2» не должен «находиться» внутри «1.22»
        from app.scripts.CI.normalize_tables import check_step_markers
        card = "| 1.1 | x |\n| 1.22 | y |\n"
        _report, ok = check_step_markers(card, self.SRC)
        assert not ok  # 1.2 действительно отсутствует

    def test_source_without_composite_markers_skipped(self):
        # тест на НЕсрабатывание: голый текст без нумерации — сверять нечего
        from app.scripts.CI.normalize_tables import check_step_markers
        src = "# Ф\n\n<table><tr><th>Параметр</th><td>x</td></tr></table>\n"
        report, ok = check_step_markers("текст", src)
        assert ok and not report


class TestTitleTransfer:
    """Дословный перенос title источника во frontmatter карточки —
    постоянный атрибут, потеря наименования = брак."""

    SRC = ("---\ntitle: '[Файловый сервис] Клиент: Функция загрузки файла'\n"
           "confluence_page_id: '1'\n---\n# стр\n")

    def test_verbatim_title_ok(self):
        card = ("---\nid: FUN-CL-01\n"
                "title: '[Файловый сервис] Клиент: Функция загрузки файла'\n"
                "---\n# док\n")
        _report, ok = check_title(card, self.SRC)
        assert ok

    def test_missing_title_is_loss(self):
        card = "---\nid: FUN-CL-01\n---\n# док\n"
        _report, ok = check_title(card, self.SRC)
        assert not ok

    def test_paraphrased_title_caught(self):
        card = ("---\nid: FUN-CL-01\n"
                "title: 'Функция загрузки файла (клиент)'\n---\n# док\n")
        _report, ok = check_title(card, self.SRC)
        assert not ok

    def test_source_without_title_skipped(self):
        # тест на НЕсрабатывание: источник без title сверке не подлежит
        src = "---\nconfluence_page_id: '1'\n---\n# стр\n"
        card = "---\nid: FUN-CL-01\n---\n# док\n"
        _report, ok = check_title(card, src)
        assert ok and not _report

    def test_multiline_yaml_title_joined(self):
        # экспортёр переносит длинный title на следующую строку (YAML
        # flow scalar) — значение склеивается, сверка по ПОЛНОМУ имени
        src = ("---\ntitle: '[БлокН2Н] Банк: Функция повторного запуска обработки сообщения о блокировках\n"
               "  Н2Н'\nconfluence_page_id: '1'\n---\n# стр\n")
        full = ("---\nid: FUN-BNK-02\n"
                "title: '[БлокН2Н] Банк: Функция повторного запуска обработки сообщения о блокировках Н2Н'\n"
                "---\n# док\n")
        _report, ok = check_title(full, src)
        assert ok

    def test_multiline_title_truncated_card_caught(self):
        # тест на НЕсрабатывание слепоты: карточка только с первой строкой
        # значения — раньше сверка «совпадала» по обрезку, теперь брак
        src = ("---\ntitle: '[БлокН2Н] Банк: Функция повторного запуска обработки сообщения о блокировках\n"
               "  Н2Н'\nconfluence_page_id: '1'\n---\n# стр\n")
        cut = ("---\nid: FUN-BNK-02\n"
               "title: '[БлокН2Н] Банк: Функция повторного запуска обработки сообщения о блокировках'\n"
               "---\n# док\n")
        _report, ok = check_title(cut, src)
        assert not ok

    def test_title_in_body_not_frontmatter(self):
        # 'title:' в теле карточки — не frontmatter, не считается
        card = "---\nid: FUN-CL-01\n---\n# док\n\ntitle: подделка\n"
        _report, ok = check_title(card, self.SRC)
        assert not ok


class TestLogicalCardinality:
    """Логическая кратность связей МД («1 : N») — расширение словаря роли
    кратн; строгий якорь раскроя HTML не затронут."""

    def test_logical_forms_accepted_in_links(self):
        from app.scripts.CI.normalize_tables import _looks_like_cardinality_logical
        for v in ["1 : N", "1 : 1", "0..1", "N : M", "1 : 0..N", "[1..N]", "[1]"]:
            assert _looks_like_cardinality_logical(v), v

    def test_param_tables_still_strict(self):
        # тест на НЕсрабатывание: в таблицах параметров раскавычивание
        # [1] -> 1 остаётся браком (защита литералов якорных колонок)
        from app.scripts.CI.normalize_tables import _looks_like_cardinality
        assert not _looks_like_cardinality("1 : N")
        assert not _looks_like_cardinality("1")

    def test_garbage_still_rejected(self):
        from app.scripts.CI.normalize_tables import _looks_like_cardinality_logical
        for v in ["много", "1 или 2", "N шт.", "см. ниже"]:
            assert not _looks_like_cardinality_logical(v), v

    def test_links_table_signature(self):
        # сигнатура «Связь|Сущность|Кратность» включает логическую нотацию
        from app.scripts.CI.normalize_tables import validate_columns
        rep = validate_columns(["Связь", "Сущность", "Кратность"],
                               [["A → B", "ENT-002", "1 : N"]], path_index=None)
        kr = [r for r in rep if r.get("role") == "кратн"]
        assert kr and not kr[0].get("bad")

    def test_strict_anchor_untouched(self):
        # строгий якорь разбора HTML по-прежнему только скобочный
        from app.scripts.CI.normalize_tables import _looks_like_cardinality_strict
        assert _looks_like_cardinality_strict("[1..N]")
        assert not _looks_like_cardinality_strict("1 : N")


class TestLogicFieldTableNotRequired:
    """Вложенная таблица «поле | значение» из «Логики работы метода»
    (заполнение полей БД-записи) — не сетка параметров контракта: её
    имена в карточке не требуются (OQ-033, intc-035)."""

    def test_pole_znachenie_table_skipped(self):
        source = (
            "# Метод\n\n"
            '<table><tr><th>поле</th><th>значение</th></tr>'
            '<tr><td>storage_type</td><td>= "S3"</td></tr></table>\n'
        )
        assert "storage_type" not in html_param_names(source)

    def test_param_grid_still_required(self):
        # тест на НЕсрабатывание: обычная сетка параметров сторожится
        source = (
            "# Метод\n\n"
            "<table><tr><th>Параметр</th><th>Описание</th></tr>"
            "<tr><td>file_id</td><td>Идентификатор файла</td></tr></table>\n"
        )
        assert "file_id" in html_param_names(source)

    def test_nested_table_rows_not_mixed(self):
        # таблица полей внутри ячейки шаговой таблицы «Логики» (intc-035):
        # её строки не подмешиваются в сетку внешней и имена не требуются;
        # соседняя настоящая сетка параметров — сторожится
        source = (
            "# Метод\n\n"
            "<table><tr><th>№</th><th>Шаг</th><th>Описание</th></tr>"
            "<tr><td>3</td><td>Создать запись</td><td>поля — см. таблицу:"
            "<table><tr><th>поле</th><th>значение</th></tr>"
            '<tr><td>storage_type</td><td>= "S3"</td></tr></table>'
            "</td></tr></table>\n"
            "<table><tr><th>Параметр</th><th>Описание</th></tr>"
            "<tr><td>file_id</td><td>Идентификатор</td></tr></table>\n"
        )
        names = html_param_names(source)
        assert "storage_type" not in names and "file_id" in names


class TestHtmlSourceCompleteness:
    """--check --source: полнота HTML-таблиц источника — каждое имя параметра
    из раскрытой сетки обязано присутствовать в карточке (инцидент
    2026-08-12: file_id/upload_token потеряны при зелёном гейте)."""

    SOURCE = (
        "# Формат запроса\n\n"
        "<table>\n"
        "<tr><th>Структура запроса</th><th>Название параметра</th>"
        "<th>Тип</th></tr>\n"
        "<tr><td><strong>Тело запроса</strong></td><td></td><td></td></tr>\n"
        "<tr><td>file_id</td><td>Идентификатор файла</td><td>UUID</td></tr>\n"
        "<tr><td>upload_token</td><td>Токен загрузки</td><td>Строка</td></tr>\n"
        "<tr><td>Content-Type</td><td>Заголовок</td><td>Строка</td></tr>\n"
        "</table>\n"
    )

    def test_names_extracted(self):
        names = html_param_names(self.SOURCE)
        assert {"file_id", "upload_token", "Content-Type"} <= names
        # секционная строка и типы именами не считаются
        assert "UUID" not in names and "Строка" not in names

    def test_missing_param_is_brak(self):
        card = "| Код параметра | Наименование параметра |\n|---|---|\n| `file_id` | Идентификатор файла |\n"
        _report, ok = check_source_tables(card, self.SOURCE)
        assert not ok

    def test_full_card_passes(self):
        # тест на НЕсрабатывание: все имена на месте — OK
        card = ("| Код параметра | Наименование параметра |\n|---|---|\n"
                "| `file_id` | Идентификатор файла |\n"
                "| `upload_token` | Токен загрузки |\n"
                "| `Content-Type` | Заголовок |\n")
        _report, ok = check_source_tables(card, self.SOURCE)
        assert ok

    def test_kod_parametra_is_path_role(self):
        # каноническая шапка: «Код параметра» — роль путь; JSON-пути с точками валидны
        headers = ["Код параметра", "Наименование параметра", "Тип", "Обяз.", "Кратность", "Правила"]
        rows = [["body.file_id", "Идентификатор файла", "UUID", "Да", "[1]", ""],
                ["body.parts[]", "Части", "Массив", "Нет", "[0..N]", ""]]
        report = validate_columns(headers, rows, path_index=0)
        path_col = [c for c in report if c["role"] == "путь"][0]
        assert path_col["valid_pct"] == 100.0


class TestSourceLiteralPardon:
    """--check --source: дословный литерал источника вне словаря роли — не брак
    (ложный БРАК жанра 3 file-storage, 2026-08-10: автор постановки написал
    «[1]» в колонке обязательности; дословность переноса сильнее словаря)."""

    # Источник в форме сырого HTML (как выгрузка Confluence): в колонке
    # обязательности авторский литерал [1] у строки-контейнера.
    SOURCE_HTML = (
        "# Постановка\n\n"
        "<table>\n"
        "<tr><th colspan=\"2\">Структура ответа</th><th>Название параметра</th>"
        "<th>Тип данных</th><th>Кратность</th><th>Обязательность</th></tr>\n"
        "<tr><td colspan=\"2\">Тело ответа</td><td colspan=\"2\">Объект</td>"
        "<td>[1]</td><td>[1]</td></tr>\n"
        "<tr><td></td><td colspan=\"2\">addresses</td><td>Массив</td>"
        "<td>[1]</td><td>Да</td></tr>\n"
        "</table>\n"
    )

    CARD = (
        "# Карточка\n\n"
        "| JSON-элемент | Название | Тип | Обяз. | Кратность | Правила |\n"
        "|---|---|---|---|---|---|\n"
        "| Тело ответа | Объект | Объект | [1] | [1] |  |\n"
        "| Тело ответа/addresses | Массив адресов | Массив | Да | [1] |  |\n"
    )

    def _check(self, card, tmp_path, source=None):
        p = tmp_path / "card.md"
        p.write_text(card, encoding="utf-8")
        return check_file(p, source_text=source)

    def test_source_literals_collected_per_role(self):
        lits = source_role_literals(self.SOURCE_HTML)
        assert "[1]" in lits["обязат"]
        assert "да" in lits["обязат"]
        assert "[1]" in lits["кратн"]

    def test_verbatim_source_literal_pardoned(self, tmp_path):
        # тест на НЕсрабатывание: [1] в Обяз. дословно из источника — OK
        report, ok = self._check(self.CARD, tmp_path, source=self.SOURCE_HTML)
        assert ok, "\n".join(report)
        assert any("дословно из источника" in l for l in report)

    def test_without_source_still_caught(self, tmp_path):
        # без --source поведение прежнее: [1] в обязательности — брак
        _report, ok = self._check(self.CARD, tmp_path)
        assert not ok

    def test_real_rewrite_not_pardoned(self, tmp_path):
        # настоящий регресс ([1] → 1 в кратности) источником не оправдан:
        # литерала «1» в колонке кратности источника нет
        card = self.CARD.replace("| Да | [1] |", "| Да | 1 |")
        _report, ok = self._check(card, tmp_path, source=self.SOURCE_HTML)
        assert not ok

    def test_literal_from_other_role_not_pardoned(self, tmp_path):
        # совпадение ищется в колонке ТОЙ ЖЕ роли: «Объект» есть в источнике
        # (название/тип), но обязательность «Объект» это не оправдывает
        card = self.CARD.replace("| [1] | [1] |", "| Объект | [1] |")
        _report, ok = self._check(card, tmp_path, source=self.SOURCE_HTML)
        assert not ok


class TestProfileApplicability:
    def test_table_without_anchor_roles_kept_as_grid(self):
        # фолбэк: колонки на местах, путей нет, rowspan протянут
        headers, rows = build_flat(grid_of(CODES_HTML), BLOCKS_PROFILE)
        assert headers == ["№ п/п", "Код отказа", "Текст отказа", "Примечание"]
        assert rows[0][:3] == ["1", "EIO1", "Физ лицо не связано с клиентом"]
        assert rows[1][:3] == ["2", "EIO2", "Физ лицо имеет недействительный ДУЛ"]
        assert rows[0][3] == rows[1][3] == "Коды не анализируются"

    def test_xml_table_still_assembled(self):
        # тест на НЕсрабатывание (Д-22): у таблицы с якорными ролями
        # фолбэк не отнимает сборку путей
        assert blocks_profile_applies(grid_of(BLOCKS_HTML), BLOCKS_PROFILE)
        assert not blocks_profile_applies(grid_of(CODES_HTML), BLOCKS_PROFILE)
        _h, rows = build_flat(grid_of(BLOCKS_HTML), BLOCKS_PROFILE)
        assert rows[2][0] == "ObjectBody/Context/ProcessGUID"


class TestColumnValidators:
    def test_clean_table_passes(self):
        headers, rows = build_flat(grid_of(BLOCKS_HTML), BLOCKS_PROFILE)
        report = validate_columns(headers, rows, path_index=0)
        assert report and all(c["valid_pct"] == 100.0 for c in report)

    def test_shifted_roles_are_caught(self):
        # Смоделированный брак итерации 3: путь съехал в «Название»
        headers = ["XML-элемент", "Название параметра", "Обязательность", "Кратность"]
        rows = [["Message/*/Body/Текст пояснения тут", "Message/*/Body", "текст", "1"]]
        report = {c["role"]: c for c in validate_columns(headers, rows, path_index=0)}
        assert report["путь"]["valid_pct"] < 100
        assert report["название"]["valid_pct"] < 100
        assert report["обязательность" if "обязательность" in report else "обязат"]["valid_pct"] < 100

    def test_legit_name_with_slash_not_flagged(self):
        # «ОГРН/ОГРНИП» — законное имя со слэшем, не XML-путь
        headers = ["Путь", "Название параметра"]
        rows = [["A/B", "ОГРН/ОГРНИП"], ["A/C", "Адрес рег./факт."]]
        report = {c["role"]: c for c in validate_columns(headers, rows, path_index=0)}
        assert report["название"]["valid_pct"] == 100.0

    def test_path_with_attribute_segment_not_flagged(self):
        # Vars Code="SKIP_CONTROL_DUL" — элемент с атрибутом, законный путь
        headers = ["Путь"]
        rows = [['ObjectBody/Vars Code="SKIP_CONTROL_DUL"']]
        report = validate_columns(headers, rows, path_index=0)
        assert report[0]["valid_pct"] == 100.0


class TestQualityGate:
    def test_refuses_below_threshold(self, tmp_path):
        # Профиль по индексам на блочной таблице — заведомо съедет
        f = tmp_path / "page.md"
        f.write_text(BLOCKS_HTML, encoding="utf-8")
        bad = Profile(name="idx", header_rows=1, hierarchy_cols=[0, 1, 2, 3],
                      path_title="XML-элемент",
                      keep_cols=[(4, "Название параметра"), (8, "Обязательность")])
        _out, report, ok = normalize_file(f, bad, None, min_valid_pct=95.0)
        assert ok is False
        assert any("НИЖЕ ПОРОГА" in line for line in report)

    def test_passes_with_good_profile(self, tmp_path):
        f = tmp_path / "page.md"
        f.write_text(BLOCKS_HTML, encoding="utf-8")
        _out, _report, ok = normalize_file(f, BLOCKS_PROFILE, None, min_valid_pct=95.0)
        assert ok is True


class TestDiscovery:
    def test_top_level_only(self):
        md = ("текст\n<table><tr><td>внешняя"
              "<table><tr><td>вложенная</td></tr></table></td></tr></table>\n")
        tables = find_top_tables(md)
        assert len(tables) == 1

    def test_sample_lists_columns(self):
        g = grid_of(ROWSPAN_HTML)
        s = render_sample(g)
        assert "[0] Узел" in s and "строка 1" in s


class TestAnchorlessRowAssignment:
    """Замечание итерации 6-секст (2026-08-09): строка БЕЗ якорей — текст правил
    уезжал в «Название», а название — в путь."""

    HTML = """
<table>
<tr>
  <th colspan="4">XML структура</th><th colspan="2">Название параметра</th>
  <th colspan="2">Тип данных</th><th colspan="2">Обязате<br>льность</th>
  <th colspan="2">Крат<br>ность</th><th colspan="2">Комментарий</th>
</tr>
<tr>
  <td></td><td colspan="3">/Description</td><td colspan="2">Описание документа</td>
  <td colspan="2"></td><td colspan="2"></td><td colspan="2"></td>
  <td colspan="2">Если Организация найдена в ЕСК: текст сообщения</td>
</tr>
</table>
"""

    def test_rules_stay_in_rules_name_in_name(self):
        _h, rows = build_flat(grid_of(self.HTML), BLOCKS_PROFILE)
        row = rows[0]
        assert row[0] == "/Description"              # путь без названия
        assert row[1] == "Описание документа"        # название на месте
        assert "Если Организация" in row[5]          # правила — в правилах
        assert "Если Организация" not in row[1]

    def test_anchored_rows_not_affected(self):
        # тест на НЕсрабатывание (Д-22): строки с якорями разбираются как раньше
        _h, rows = build_flat(grid_of(BLOCKS_HTML), BLOCKS_PROFILE)
        assert rows[2][1] == "GUID процесса" and rows[2][4] == "[0..1]"


class TestNestedListSeparator:
    def test_bold_before_nested_list_not_glued(self):
        # «**иначе:**Если» без разделителя — CommonMark не закрывал жирный
        html = ('<table><tr><th>Поле</th></tr>'
                '<tr><td><ul><li><strong>иначе:</strong>'
                '<ul><li>Если условие — действие</li></ul></li></ul></td></tr></table>')
        _h, rows = build_flat(grid_of(html), Profile())
        assert "**иначе:**<br>Если условие" in rows[0][0]


class TestStripPathWildcards:
    P_ON = Profile(name="t", header_rows=1, blocks=True, path_block=0, ladder=True,
                   path_title="XML-элемент", path_join="/", strip_path_wildcards=True)

    def test_wildcard_segments_removed(self):
        _h, rows = build_flat(grid_of(BLOCKS_HTML), self.P_ON)
        assert rows[2][0] == "ObjectBody/Context/ProcessGUID"
        assert rows[0][0] == "ObjectBody"

    def test_on_by_default_and_opt_out(self):
        # чистка «*» включена по умолчанию; выключение — опцией профиля
        import dataclasses
        _h, rows = build_flat(grid_of(BLOCKS_HTML), BLOCKS_PROFILE)
        assert rows[2][0] == "ObjectBody/Context/ProcessGUID"
        raw = dataclasses.replace(BLOCKS_PROFILE, strip_path_wildcards=False)
        _h, rows = build_flat(grid_of(BLOCKS_HTML), raw)
        assert rows[2][0] == "ObjectBody/*/Context/*/ProcessGUID"


class TestFlatTableWithoutCardinality:
    """Генерализационный тест (2026-08-09, «Метод-запроса-QR-кода»): таблица
    БЕЗ колонки кратности — правила на хвосте ослепляли якорь обязательности,
    и все значения склеивались в псевдо-путь при 100 % «валидности»."""

    HTML = """
<table>
<tr><th>№</th><th>Параметр</th><th>Тип</th><th>Обязательность</th><th>Правила заполнения</th></tr>
<tr><td>1</td><td>traceID</td><td>Строка(20)</td><td>Да</td>
    <td>Формируется уникальное значение запроса</td></tr>
<tr><td>2</td><td>ecoServiceCode</td><td>Строка(20)</td><td>Да</td><td>= "O2PLUS"</td></tr>
</table>
"""

    def test_columns_not_glued_into_path(self):
        p = Profile(name="t", header_rows=1, blocks=True, path_block=0,
                    ladder=True, path_title="XML-элемент", path_join="/")
        _h, rows = build_flat(grid_of(self.HTML), p)
        assert rows[0][0] == "1"                     # путь = только первая колонка
        assert rows[0][1] == "traceID"               # параметр в названии
        assert rows[0][2] == "Строка(20)"            # тип распознан
        assert rows[0][3] == "Да"                    # обязательность распознана
        assert "Формируется" in rows[0][4]           # правила в правилах
        assert rows[1][1] == "ecoServiceCode"


class TestCheckTruncationMarkers:
    """Маркеры сокращения в --check (2026-08-09): агент трижды ужимал
    справочник с пометкой «фрагмент» — текст не доехал, ловим инструментом."""

    BASE = ("| XML-элемент | Название | Тип | Обяз. | Кратность | Правила |\n"
            "|---|---|---|---|---|---|\n"
            "| `A/B` | Поле | string | Да | [1] | правило |\n")

    def _check(self, text, tmp_path):
        p = tmp_path / "card.md"
        p.write_text(text, encoding="utf-8")
        return check_file(p)

    def test_fragment_marker_fails(self, tmp_path):
        rep, ok = self._check(self.BASE + "\n### 2.2. Коды (фрагмент из источника)\n",
                              tmp_path)
        assert not ok
        assert any("фрагмент" in l for l in rep)

    def test_etc_marker_fails(self, tmp_path):
        _rep, ok = self._check(self.BASE + "\n| X | 1 | и т.д. |\n", tmp_path)
        assert not ok

    def test_clean_card_passes(self, tmp_path):
        # тест на НЕсрабатывание: честная карточка без маркеров — OK
        _rep, ok = self._check(self.BASE, tmp_path)
        assert ok


class TestNoteRowsGoToRules:
    """Замечания по 6-окт (2026-08-09): строка-пояснение без пути (проза в
    зоне пути + пример в зоне названия) — контент читался как «Название».
    Место пояснений и примеров — «Правила заполнения»."""

    HTML = """
<table>
<tr>
  <th colspan="4">XML структура</th><th colspan="2">Название параметра</th>
  <th colspan="2">Тип данных</th><th colspan="2">Обязате<br>льность</th>
  <th colspan="2">Крат<br>ность</th><th colspan="2">Комментарий</th>
</tr>
<tr>
  <td colspan="4">Body/Text</td><td colspan="2">Текст ответа</td>
  <td colspan="2">string</td><td colspan="2">О</td><td colspan="2">[1]</td>
  <td colspan="2">Результат в формате JSON</td>
</tr>
<tr>
  <td colspan="6">1 Вариант - Успешный. Синтаксис выглядит следующим образом</td>
  <td colspan="4">{ "CL_ORG": "GUID", "Is_Success": "1" }</td>
  <td colspan="4"></td>
</tr>
</table>
"""

    def test_note_row_content_lands_in_rules(self):
        _h, rows = build_flat(grid_of(self.HTML), BLOCKS_PROFILE)
        note = rows[1]
        assert note[0] == ""                          # путь пуст (не унаследован)
        assert note[1] == ""                          # название пусто
        assert "1 Вариант - Успешный" in note[5]      # пояснение в правилах
        assert '"Is_Success"' in note[5].replace("\\", "")  # пример там же
        # исходный порядок: проза раньше примера
        assert note[5].index("Вариант") < note[5].index("Is_Success")

    def test_normal_rows_unaffected(self):
        # тест на НЕсрабатывание: обычная строка с якорями — как раньше
        _h, rows = build_flat(grid_of(self.HTML), BLOCKS_PROFILE)
        assert rows[0][0] == "Body/Text" and rows[0][1] == "Текст ответа"
        assert rows[0][4] == "[1]"


class TestCheckSourceTables:
    """Сверка --check --source (2026-08-09): агент четырежды ужимал справочник,
    в т.ч. обойдя словесный гейт — сторожим содержимое."""

    SRC = ("текст\n\n### Коды\n\n"
           "| **Наименование** | **Код** |\n| --- | --- |\n"
           "| Корпоративные карты | CORP_CARDS |\n"
           "| Брокеридж и лицензии | BROKERAGE |\n")

    def test_missing_table_caught(self):
        from app.scripts.CI.normalize_tables import check_source_tables
        card = "| Код |\n|---|\n| `CORP_CARDS` |\n"          # ужато до колонки
        rep, ok = check_source_tables(card, self.SRC)
        assert not ok
        assert any("BROKERAGE" in l or "отсутствуют" in l for l in rep)

    def test_full_transfer_passes(self):
        # НЕсрабатывание: перенос целиком (пусть и с бэктиками/жирным) — OK
        from app.scripts.CI.normalize_tables import check_source_tables
        card = ("| Наименование | Код |\n|---|---|\n"
                "| Корпоративные карты | `CORP_CARDS` |\n"
                "| Брокеридж и лицензии | `BROKERAGE` |\n")
        _rep, ok = check_source_tables(card, self.SRC)
        assert ok

    def test_single_column_source_tables_ignored(self):
        # НЕсрабатывание: одноколоночные/короткие таблицы источника не сверяются
        from app.scripts.CI.normalize_tables import check_source_tables
        src = "| Код |\n|---|\n| X1 |\n| X2 |\n"
        _rep, ok = check_source_tables("пустая карточка", src)
        assert ok


class TestTypeWithSpaceAnchor:
    def test_type_with_space_before_parens_recognized(self):
        # «string (30)» с пробелом — тип уезжал в «Название» (замечание 6-нон)
        html = ('<table><tr>'
                '<th colspan="4">XML структура</th><th colspan="2">Название параметра</th>'
                '<th colspan="2">Тип данных</th><th colspan="2">Обязате<br>льность</th>'
                '<th colspan="2">Крат<br>ность</th><th colspan="2">Комментарий</th></tr>'
                '<tr><td colspan="4">/RelType</td><td colspan="2">=Код должности</td>'
                '<td colspan="2">string (30)</td><td colspan="2">О</td>'
                '<td colspan="2">[1]</td><td colspan="2">значения ниже</td></tr></table>')
        _h, rows = build_flat(grid_of(html), BLOCKS_PROFILE)
        assert rows[0][1] == "=Код должности"
        assert rows[0][2] == "string (30)"


class TestSuspiciousTitleDetector:
    """Детектор «в названии не только название» (2026-08-09): скрипт находит,
    проход 2 разносит; в --check готовой карточки — брак."""

    def _card(self, name_cell):
        return ("| XML-элемент | Название | Тип | Обяз. | Кратность | Правила |\n"
                "|---|---|---|---|---|---|\n"
                f"| `A/B` | {name_cell} | array | Нет | [1] | правило |\n")

    def test_markers_caught_in_check(self, tmp_path):
        for bad in ("Перечень – обязателен на момент перевода технологии",
                    "Операция (допустимые значения: \"OR\"/\"AND\")",
                    "string (30)"):
            p = tmp_path / "c.md"; p.write_text(self._card(bad), encoding="utf-8")
            _rep, ok = check_file(p)
            assert not ok, bad

    def test_honest_long_title_not_flagged(self, tmp_path):
        # НЕсрабатывание: длинное, но честное название — не брак
        good = "Перечень характеров отношений с Клиентом по данным справочника ЕСК"
        p = tmp_path / "c.md"; p.write_text(self._card(good), encoding="utf-8")
        _rep, ok = check_file(p)
        assert ok


class TestTornTableRows:
    """Разорванные строки таблиц (инцидент 6-дец, 2026-08-09): агент при
    разнесении названия вставил перенос строки внутрь ячейки — строка
    таблицы оборвалась, хвост выпал голым текстом."""

    def _check(self, text, tmp_path):
        p = tmp_path / "card.md"
        p.write_text(text, encoding="utf-8")
        return check_file(p)

    def test_short_row_caught(self, tmp_path):
        card = ("| XML-элемент | Название | Тип | Обяз. | Кратность | Правила |\n"
                "|---|---|---|---|---|---|\n"
                "| `A/B` | Поле | array | Н \n"
                "вывалившийся текст правил\n"
                "| `A/C` | Поле2 | string | Да | [1] | правило |\n")
        rep, ok = self._check(card, tmp_path)
        assert not ok
        assert any("разорванная строка" in l or "строкой данных" in l for l in rep)

    def test_intact_table_passes(self, tmp_path):
        # НЕсрабатывание: целая таблица с <br> внутри ячейки — OK
        card = ("| XML-элемент | Название | Тип | Обяз. | Кратность | Правила |\n"
                "|---|---|---|---|---|---|\n"
                "| `A/B` | Поле | array | Н | [1] | строка один<br>строка два |\n")
        _rep, ok = self._check(card, tmp_path)
        assert ok


class TestTitleDetectorExtended:
    """Расширение детектора по замечаниям 6-дец (2026-08-09): <br>-абзацы,
    =присвоения, глагольные описания."""

    def test_new_markers_caught(self):
        from app.scripts.CI.normalize_tables import _title_suspicious
        for bad in ("=Код должности представителя",
                    "Признак заявителя<br>(допускается передача только одной персоны)",
                    "Перечень наборов<br>Проверка ЕИО выполняется всегда",
                    "Время последнего изменения. Время должно быть указано с точностью"):
            assert _title_suspicious(bad), bad

    def test_honest_names_not_flagged(self):
        from app.scripts.CI.normalize_tables import _title_suspicious
        for good in ("Перечень характеров отношений с Клиентом",
                     "GUID организации в ЕСК",
                     "Признак ответа в «расширенном» формате"):
            assert not _title_suspicious(good), good


class TestTitleDetectorPurposeMarkers:
    def test_purpose_descriptions_caught(self):
        # замечание 5 по 6-ундец: описания назначения — не имена
        from app.scripts.CI.normalize_tables import _title_suspicious
        assert _title_suspicious("Секция для связи блока Segment представителя")
        assert _title_suspicious("ссылка на блок Segment с информацией по организации")

    def test_names_with_similar_words_not_flagged(self):
        from app.scripts.CI.normalize_tables import _title_suspicious
        assert not _title_suspicious("Ссылки документа")     # не «ссылка на»
        assert not _title_suspicious("Секция подписи")       # не «секция для»


class TestNotificationStructure:
    """Сторож карточки нотификаций (NTF): ключ «канал, получатели» события
    обязан иметь карточку канала (инцидент [КК_ВК]: «Уведомление в
    Экосистеме» использовался событиями, в разделе каналов отсутствовал);
    упомянутый общий шаблон M-NN существует; E-номера монотонны."""

    def make(self, channels, events, tail=""):
        return ("---\nid: NTF-01\ntype: notification\n---\n\n"
                "## Каналы и адреса доставки\n\n" + channels +
                "\n## Сообщения нотификации\n\n" + events + tail)

    def test_missing_channel_card_caught(self):
        from app.scripts.CI.normalize_tables import check_notification_structure
        text = self.make(
            "### Канал и получатели: E-mail, Пользователи Клиента\n\nправила\n",
            "### NTF-01.E01. Событие А\n\n"
            "#### Канал и получатели: Уведомление в Экосистеме, Пользователи Клиента\n\nтекст\n")
        report, ok = check_notification_structure(text)
        assert not ok and "Уведомление в Экосистеме" in report[0]

    def test_consistent_card_clean(self):
        # тест на НЕсрабатывание: ключи, шаблон и порядок согласованы
        from app.scripts.CI.normalize_tables import check_notification_structure
        text = self.make(
            "### Канал и получатели: E-mail, Пользователи Банка\n\nправила\n",
            "### NTF-01.E01. Событие А\n\n"
            "#### Канал и получатели: E-mail, Пользователи Банка\n\n"
            "- **Сообщение:** общий шаблон M-01\n\n"
            "### NTF-01.E02. Событие Б\n\n"
            "#### Канал и получатели: E-mail, Пользователи Банка\n\nтекст\n",
            "\n## Общие шаблоны сообщений\n\n### M-01. E-mail — ошибки\n")
        report, ok = check_notification_structure(text)
        assert ok and "согласованы ✓" in report[0]

    def test_missing_template_caught(self):
        from app.scripts.CI.normalize_tables import check_notification_structure
        text = self.make(
            "### Канал и получатели: E-mail, Пользователи Банка\n\nправила\n",
            "### NTF-01.E01. Событие А\n\n"
            "#### Канал и получатели: E-mail, Пользователи Банка\n\n"
            "- **Сообщение:** общий шаблон M-02\n")
        report, ok = check_notification_structure(text)
        assert not ok and any("M-02" in r for r in report)

    def test_non_monotonic_events_caught(self):
        from app.scripts.CI.normalize_tables import check_notification_structure
        text = self.make(
            "### Канал и получатели: SMS, Пользователи Клиента\n\nправила\n",
            "### NTF-01.E03. Событие В\n\n"
            "#### Канал и получатели: SMS, Пользователи Клиента\n\nтекст\n\n"
            "### NTF-01.E02. Событие Б\n\n"
            "#### Канал и получатели: SMS, Пользователи Клиента\n\nтекст\n")
        report, ok = check_notification_structure(text)
        assert not ok and any("E02 после E03" in r for r in report)

    def test_other_card_types_untouched(self):
        # тест на НЕсрабатывание: не-нотификация (нет обоих разделов)
        from app.scripts.CI.normalize_tables import check_notification_structure
        report, ok = check_notification_structure(
            "---\nid: FUN-BNK-01\n---\n\n## Поведение\n\n#### Подраздел\n")
        assert ok and not report

    def test_single_digit_event_number_flagged(self):
        # формат E-номера: минимум две цифры (прогон B выдал E1/E2)
        from app.scripts.CI.normalize_tables import check_notification_structure
        text = self.make(
            "### Канал и получатели: SMS, Пользователи Клиента\n\nправила\n",
            "### NTF-01.E1. Событие А\n\n"
            "#### Канал и получатели: SMS, Пользователи Клиента\n\nтекст\n")
        report, ok = check_notification_structure(text)
        assert not ok and any("минимум две цифры" in r for r in report)

    def test_br_flat_message_flagged_table_allowed(self):
        # <br>-простыня в абзаце сообщения — брак; <br> в ячейке
        # реестра (строка на «|») — легален
        from app.scripts.CI.normalize_tables import check_notification_structure
        text = self.make(
            "### Канал и получатели: SMS, Пользователи Клиента\n\nправила\n",
            "| ID | Событие | Каналы, получатели |\n|---|---|---|\n"
            "| NTF-01.E01 | Событие А | SMS,<br>Пользователи Клиента |\n\n"
            "### NTF-01.E01. Событие А\n\n"
            "#### Канал и получатели: SMS, Пользователи Клиента\n\n"
            "**Сообщение:**\n\nТема:<br>\"X\"<br>Текст:<br>\"Y\"\n")
        report, ok = check_notification_structure(text)
        assert not ok and any("<br> вне таблиц" in r for r in report)
        unrolled = text.replace(
            "Тема:<br>\"X\"<br>Текст:<br>\"Y\"",
            "Тема:\n\n\"X\"\n\nТекст:\n\n\"Y\"")
        report2, ok2 = check_notification_structure(unrolled)
        assert ok2, report2


class TestHistoryTableNotRequired:
    """История изменений страницы («Дата | Описание | Автор») по канону не
    переносится — гейт значений не должен требовать её в карточке
    (ретро-перегон [КК_ВК] 2026-08-15, конфликт гейт↔шаблон)."""

    SRC = ("# История изменений\n\n"
           "| Дата | Описание | Автор | Задача в JIRA |\n|---|---|---|---|\n"
           "| 2024-02-14 | Разделение нотификаций | Иванов | GBO-1 |\n"
           "| 2023-09-14 | Добавлены нотификации | Петров | GBO-2 |\n\n"
           "| Код | Значение |\n|---|---|\n"
           "| A1 | Боевой код |\n| B2 | Второй код |\n")

    def test_history_not_required(self):
        from app.scripts.CI.normalize_tables import check_source_tables
        card = "| Код | Значение |\n|---|---|\n| A1 | Боевой код |\n| B2 | Второй код |\n"
        rep, ok = check_source_tables(card, self.SRC)
        assert ok, rep

    def test_real_table_still_guarded(self):
        # тест на НЕсрабатывание фильтра: потеря обычной таблицы ловится
        from app.scripts.CI.normalize_tables import check_source_tables
        rep, ok = check_source_tables("# пустая карточка\n", self.SRC)
        assert not ok and any("Код" in r or "A1" in r for r in rep)

    def test_unprefixed_key_heading_flagged(self):
        # заголовок-ключ без префикса «Канал и получатели: » — брак
        from app.scripts.CI.normalize_tables import check_notification_structure
        text = ("---\nid: NTF-01\ntype: notification\n---\n\n"
                "## Каналы и адреса доставки\n\n"
                "### SMS, Пользователи Клиента\n\nправила\n"
                "\n## Сообщения нотификации\n\n"
                "### NTF-01.E01. Событие А\n\n"
                "#### Канал и получатели: SMS, Пользователи Клиента\n\nтекст\n")
        report, ok = check_notification_structure(text)
        assert not ok and any("без префикса" in r for r in report)


class TestCriticAttrsNotLiterals:
    """Значения HTML-атрибутов внутри тега (CriticMarkup: class="critic-del",
    data-task="GBO-…") — разметка, не кавычечные литералы источника;
    присваивание в тексте (= "O2PLUS") — литерал (финальный прогон locks)."""

    SRC = ('---\ntitle: x\n---\n'
           'Ячейка: <span class="critic-del" data-task="GBO-104711">старый'
           '</span> <span class="critic-ins" data-task="GBO-104711">новый'
           '</span>\n\nТема: "Сообщение о блокировке Н2Н"\n'
           'Параметр {Код} = "O2PLUS" обязателен.\n')

    def test_attr_values_skipped_content_kept(self):
        from app.scripts.CI.normalize_tables import quoted_literals
        lits = quoted_literals(self.SRC)
        assert "critic-del" not in lits and "critic-ins" not in lits
        assert "GBO-104711" not in lits
        assert "Сообщение о блокировке Н2Н" in lits
        assert "O2PLUS" in lits  # тест на НЕсрабатывание фильтра


class TestPlaceholderLinkFlagged:
    """Ссылка-заглушка [текст](#) в карточке NTF — суррогат вместо правила
    трёх случаев (финальный прогон locks 2026-08-15)."""

    BASE = ("---\nid: NTF-01\ntype: notification\n---\n\n"
            "## Каналы и адреса доставки\n\n"
            "### Канал и получатели: E-mail, Пользователи Банка\n\nправила\n"
            "\n## Сообщения нотификации\n\n"
            "### NTF-01.E01. Событие А\n\n"
            "#### Канал и получатели: E-mail, Пользователи Банка\n\n")

    def test_stub_link_flagged(self):
        from app.scripts.CI.normalize_tables import check_notification_structure
        report, ok = check_notification_structure(
            self.BASE + "Статус: [Сущность](../e.md)[.<Статус>](#)\n")
        assert not ok and any("](#)" in r for r in report)

    def test_real_links_clean(self):
        # тест на НЕсрабатывание: обычные относительные ссылки легальны
        from app.scripts.CI.normalize_tables import check_notification_structure
        report, ok = check_notification_structure(
            self.BASE + "Статус: [Сущность](../e.md).<Статус>\n")
        assert ok, report


class TestReadmeRegistryTitle:
    """README-реестры: title дословный из главной страницы-оглавления,
    как у всех документов с источником (решение 2026-08-16 v2 —
    «собственный title» только у файлов БЕЗ страницы-источника;
    расширенное наименование реестра — в H1)."""

    SRC = "---\ntitle: '[X] Методы сервиса'\n---\n\nтекст\n"

    def test_readme_title_checked_like_any_card(self, tmp_path):
        from app.scripts.CI.normalize_tables import run_check
        readme = tmp_path / "README.md"
        readme.write_text(
            "---\ntitle: '[X] Методы и файловые контракты сервиса'\n---\n\n# Р\n",
            encoding="utf-8")
        src = tmp_path / "src.md"
        src.write_text(self.SRC, encoding="utf-8")
        rep, ok = run_check([readme], src)
        assert not ok and any("расходится" in r for r in rep)

    def test_readme_verbatim_title_ok(self, tmp_path):
        # тест на НЕсрабатывание: дословный title реестра проходит
        from app.scripts.CI.normalize_tables import run_check
        readme = tmp_path / "README.md"
        readme.write_text("---\ntitle: '[X] Методы сервиса'\n---\n\n"
                          "# Методы и файловые контракты сервиса\n",
                          encoding="utf-8")
        src = tmp_path / "src.md"
        src.write_text(self.SRC, encoding="utf-8")
        rep, ok = run_check([readme], src)
        assert ok, rep

    def test_regular_card_title_still_checked(self, tmp_path):
        from app.scripts.CI.normalize_tables import run_check
        cardf = tmp_path / "card.md"
        cardf.write_text("---\ntitle: 'Другое имя'\n---\n\n# К\n",
                         encoding="utf-8")
        src = tmp_path / "src.md"
        src.write_text(self.SRC, encoding="utf-8")
        rep, ok = run_check([cardf], src)
        assert not ok and any("расходится" in r for r in rep)


class TestStepMarkersTypeScoped:
    """Сторож маркеров шагов — только для типов с таблицей шагов;
    на data-model составные номера — нумерация секций, не шаги
    (экзамен inkasso 2026-08-16: ложные «отсутствуют 72 из 72»)."""

    SRC = ("---\ntitle: 'С'\n---\n\n<table><tr><th>№</th><th>Атрибут</th>"
           "</tr><tr><td><strong>1.1</strong></td><td>Поле А</td></tr>"
           "<tr><td><strong>1.2</strong></td><td>Поле Б</td></tr>"
           "<tr><td><strong>1.3</strong></td><td>Поле В</td></tr></table>\n")

    def test_data_model_sections_not_steps(self, tmp_path):
        from app.scripts.CI.normalize_tables import run_check
        cardf = tmp_path / "ent-001.md"
        cardf.write_text("---\nid: ENT-001\ntitle: 'С'\ntype: data-model\n"
                         "---\n\nПоле А, Поле Б, Поле В\n", encoding="utf-8")
        src = tmp_path / "src.md"
        src.write_text(self.SRC, encoding="utf-8")
        rep, ok = run_check([cardf], src)
        assert ok, rep

    def test_process_type_still_guarded(self, tmp_path):
        # тест на НЕсрабатывание фильтра: у процессов маркеры сторожатся
        from app.scripts.CI.normalize_tables import run_check
        cardf = tmp_path / "prc-001.md"
        cardf.write_text("---\nid: PRC-001\ntitle: 'С'\ntype: process\n"
                         "---\n\nшаги потеряны\n", encoding="utf-8")
        src = tmp_path / "src.md"
        src.write_text(self.SRC, encoding="utf-8")
        rep, ok = run_check([cardf], src)
        assert not ok and any("маркеры шагов" in r for r in rep)


class TestExamCalibrations:
    """К-2/К-3 экзамена inkasso: обрезки текстового CriticMarkup — не
    значения источника; одиночный латинский идентификатор — легитимное
    имя параметра, не «тип»."""

    def test_latin_identifier_name_not_suspicious(self):
        from app.scripts.CI.normalize_tables import _title_suspicious
        assert not _title_suspicious("TraceID")
        assert not _title_suspicious("SessionID")

    def test_dictionary_types_still_suspicious(self):
        # тест на НЕсрабатывание послабления: словарные типы — брак
        from app.scripts.CI.normalize_tables import _title_suspicious
        assert _title_suspicious("GUID")
        assert _title_suspicious("Строка(20)")

    def test_critic_scraps_not_required_values(self):
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("| Доступность функции | Условие |\n|---|---|\n"
               "| Роль Банка | СТАТУС |\n| ++} | {++ |\n")
        card = "Роль Банка и СТАТУС перенесены\n"
        rep, ok = check_source_tables(card, src)
        assert ok, rep

    def test_content_inside_critic_still_required(self):
        # тест на НЕсрабатывание: содержимое правок остаётся значением
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("| Доступность функции | Условие |\n|---|---|\n"
               "| Роль Банка | {++Новое условие++} |\n"
               "| Вторая строка | Ещё значение |\n")
        rep, ok = check_source_tables("Роль Банка, Вторая строка, Ещё значение\n", src)
        assert not ok and any("Новое условие" in r for r in rep)

    TBL = ("| Краткое название формы (элемент) | Действие |\n|---|---|\n"
           "| Журнал/Список | х |\n| Панель записи шаблонов | х |\n"
           "| Форма ввода названия | х |\n| А/Б | х |\n")

    def test_k4_readme_column_roles_skipped(self, tmp_path):
        # К-4: README-реестр — колонные роли не применяются
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "README.md"
        p.write_text("---\ntitle: 'Р'\n---\n\n" + self.TBL, encoding="utf-8")
        rep, ok = check_file(p, column_roles=False)
        assert ok and any("колонные роли" in r for r in rep)

    def test_k4_regular_card_roles_still_apply(self, tmp_path):
        # тест на НЕсрабатывание: у обычной карточки роли работают
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "card.md"
        p.write_text("---\ntitle: 'К'\n---\n\n" + self.TBL, encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok


class TestApplyCritic:
    """К-5: гейты сверяют ЦЕЛЕВОЙ текст источника — правки применены,
    разметка не требуется в карточке (инцидент fun-sys-08: «markup
    сохранён для прохождения гейта»)."""

    def test_textual_forms_applied(self):
        from app.scripts.CI.normalize_tables import apply_critic
        s = ("до {++GBO-118742: добавлено++} середина {--удалено--} "
             "конец {~~старое~>новое~~}")
        assert apply_critic(s) == "до добавлено середина  конец новое"

    def test_unknown_task_prefix_stripped(self):
        # К-15: экспортёрский префикс правки без номера задачи
        # (UNKNOWN-<hex-цвет>:) — тоже разметка, не текст
        from app.scripts.CI.normalize_tables import apply_critic
        s = "{++UNKNOWN-ff0000: Статус документа. Ссылка++}"
        assert apply_critic(s) == "Статус документа. Ссылка"

    def test_unknown_like_content_not_stripped(self):
        # тест на НЕсрабатывание: UNKNOWN вне разметки — содержимое
        from app.scripts.CI.normalize_tables import apply_critic
        s = "плейсхолдер UNKNOWN-ff0000: остаётся текстом"
        assert apply_critic(s) == s

    def test_html_forms_applied(self):
        from app.scripts.CI.normalize_tables import apply_critic
        s = ('a <span class="critic-del" data-task="GBO-1">старый</span>'
             '<span class="critic-ins" data-task="GBO-1">новый</span> b')
        assert apply_critic(s) == "a новый b"

    def test_gate_requires_target_not_markup(self):
        from app.scripts.CI.normalize_tables import run_check
        import pathlib, tempfile
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            src = p / "src.md"
            src.write_text(
                "---\ntitle: 'С'\n---\n\n| Реквизит | Правило |\n|---|---|\n"
                "| Поле А | {++GBO-118742: **Если** согласие есть++} |\n"
                "| Поле Б | {--устаревшее правило--} обычный текст |\n",
                encoding="utf-8")
            card = p / "card.md"
            card.write_text(
                "---\ntitle: 'С'\ntype: function\n---\n\n"
                "Поле А: **Если** согласие есть. Поле Б: обычный текст\n",
                encoding="utf-8")
            rep, ok = run_check([card], src)
            assert ok, rep

    def test_missing_target_content_still_caught(self):
        # тест на НЕсрабатывание: целевое содержимое добавления обязано
        # присутствовать — К-5 не превращается в дыру
        from app.scripts.CI.normalize_tables import run_check
        import pathlib, tempfile
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            src = p / "src.md"
            src.write_text(
                "---\ntitle: 'С'\n---\n\n| Реквизит | Правило |\n|---|---|\n"
                "| Поле А | {++GBO-118742: важное новое правило++} |\n"
                "| Поле Б | второе значение строки |\n",
                encoding="utf-8")
            card = p / "card.md"
            card.write_text("---\ntitle: 'С'\ntype: function\n---\n\n"
                            "Поле А и Поле Б: второе значение строки\n",
                            encoding="utf-8")
            rep, ok = run_check([card], src)
            assert not ok and any("важное новое правило" in r for r in rep)


class TestExamCalibrationsK6K7:
    """К-6: ячейки-изображения не требуются гейтом значений (шаблоны
    запрещают перенос скриншотов); К-7: отсылки к страницам источника
    в теле карточки — брак (отсылка вместо переноса, инцидент ×40)."""

    def test_k6_img_cells_not_required(self):
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("| № | Desktop (S-XL) | Наименование блока |\n|---|---|---|\n"
               '| 1 | <img src="img/a.png" width="473"> | Общие элементы |\n'
               '| 2 | <img src="img/b.png"><img src="img/c.png"> | Фильтры |\n')
        card = ("| № | Desktop (S-XL) | Наименование блока |\n|---|---|---|\n"
                "| 1 | Desktop (S-XL) | Общие элементы |\n"
                "| 2 | 2 варианта | Фильтры |\n")
        rep, ok = check_source_tables(card, src)
        assert ok, rep

    def test_k6_text_cells_still_required(self):
        # тест на НЕсрабатывание: текстовые ячейки обязаны переноситься
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("| № | Desktop (S-XL) | Наименование блока |\n|---|---|---|\n"
               '| 1 | <img src="img/a.png"> | Уникальный блок настроек |\n'
               "| 2 | текстовая ячейка | Второй блок |\n")
        rep, ok = check_source_tables("Второй блок, текстовая ячейка\n", src)
        assert not ok and any("Уникальный блок" in r for r in rep)

    def test_k7_page_refs_in_body_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "card.md"
        p.write_text("---\ntitle: 'К'\nconfluence_page_ids: [2169849859]\n"
                     "---\n\nСтатика и источники — по таблице полей "
                     "источника page 2169849859;\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("отсылки к страницам источника" in r
                              for r in rep)

    def test_k7_frontmatter_only_is_clean(self, tmp_path):
        # тест на НЕсрабатывание: page_ids во frontmatter легальны
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "card.md"
        p.write_text("---\ntitle: 'К'\nconfluence_page_ids: [2169849859]\n"
                     "---\n\nОбычное содержимое карточки без отсылок.\n",
                     encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep


class TestStripHistory:
    """К-9: история изменений источника вырезается до всех сверок —
    её кавычечные литералы не требуются в карточках."""

    def test_history_literals_not_required(self, tmp_path):
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text(
            '---\ntitle: "С"\n---\n\n'
            "<table><tr><th>Дата</th><th>Описание</th><th>Автор</th></tr>"
            '<tr><td>2024-01-01</td><td>исключен реквизит "Наименование '
            'клиента"</td><td>И.</td></tr></table>\n\n'
            'Контроль: значение "Сумма документа" обязательно.\n',
            encoding="utf-8")
        card = tmp_path / "card.md"
        card.write_text('---\ntitle: "С"\ntype: control\n---\n\n'
                        'Контроль: значение "Сумма документа" обязательно.\n',
                        encoding="utf-8")
        rep, ok = run_check([card], src)
        assert ok, rep

    def test_content_literals_still_required(self, tmp_path):
        # тест на НЕсрабатывание: литералы вне истории требуются
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text('---\ntitle: "С"\n---\n\n'
                       'Контроль: значение "Сумма документа" обязательно.\n',
                       encoding="utf-8")
        card = tmp_path / "card.md"
        card.write_text('---\ntitle: "С"\ntype: control\n---\n\nпусто\n',
                        encoding="utf-8")
        rep, ok = run_check([card], src)
        assert not ok and any("Сумма документа" in r for r in rep)


class TestK11LinkUrlParens:
    """К-11: скобки внутри URL ссылки («(исходящее)», «(2).xsd») — URL
    закрывается балансом, хвосты путей не остаются в тексте ячейки
    (OQ-033 экзамена: EXTINT-001, «Применение»/«Форматы»)."""

    def test_parens_in_url_no_tails(self):
        from app.scripts.CI.normalize_tables import _strip_markdown_links
        v = ('см. [Функция выгрузки](../[РРКО_ИПИ]-Инкассовое-поручение-'
             '(исходящее)/функция.md) и файл '
             '[схема](xsd/pain.013.001.08(2).xsd) конец')
        assert _strip_markdown_links(v) == \
            "см. Функция выгрузки и файл схема конец"

    def test_plain_links_and_cardinality_unchanged(self):
        # тест на НЕсрабатывание: обычные ссылки и кратность [1] как раньше
        from app.scripts.CI.normalize_tables import _strip_markdown_links
        assert _strip_markdown_links("[текст](a.md) и [1] рядом") == \
            "текст и [1] рядом"


class TestPrivilegeWarning:
    """Волна A (Э-12): FUN-CL/BNK без привилегий в «Доступности» —
    ПРЕДУПРЕЖДЕНИЕ (не брак); SYS-формула и карточки с привилегиями —
    чисто."""

    def _card(self, fid, dostup):
        return (f"---\nid: {fid}\ntitle: 'Ф'\ntype: function\n---\n\n"
                f"## Доступность\n\n{dostup}\n\n## Поведение\n\nтекст\n")

    def test_cl_without_privileges_warned_not_failed(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(self._card("FUN-CL-01", "Доступна всегда."),
                     encoding="utf-8")
        rep, ok = check_file(p)
        assert ok
        assert any(r.startswith("предупреждение") for r in rep)

    def test_bnk_with_privilege_clean(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(self._card(
            "FUN-BNK-02",
            "- **Роль и привилегия.** Код привилегии `X.VIEW`."),
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok and not any(r.startswith("предупреждение") for r in rep)

    def test_sys_not_warned(self, tmp_path):
        # тест на НЕсрабатывание: FUN-SYS сторож не трогает
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(self._card(
            "FUN-SYS-01",
            "Системная функция; вызов с ТУЗ; роли и привилегии не "
            "применяются."), encoding="utf-8")
        rep, ok = check_file(p)
        assert ok and not any(r.startswith("предупреждение") for r in rep)


class TestK24bPassportCellFormat:
    """К-24b: структурная ячейка «Что делает функция» (вложенные списки
    в источнике) не заталкивается в строку md-таблицы — лейбл-секцией."""

    _SRC = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
            "<th>Что делает функция</th>"
            "<td><p>Процесс.</p><ul><li>Задача<ul><li>Идентификатор"
            "</li></ul></li></ul></td>"
            "</tr></tbody></table>\n")

    def _run(self, tmp_path, card_body):
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text(self._SRC, encoding="utf-8")
        card = tmp_path / "card.md"
        card.write_text(
            "---\nid: FUN-BNK-08\ntitle: 'X'\ntype: function\n---\n\n"
            + card_body, encoding="utf-8")
        return run_check([card], src)

    def test_cell_in_table_row_flagged(self, tmp_path):
        rep, ok = self._run(
            tmp_path,
            "| **Что делает функция** | Процесс. Задача Идентификатор |\n")
        assert any("расплющена" in r for r in rep)

    def test_label_section_clean(self, tmp_path):
        # тест на НЕсрабатывание: лейбл-секция с полноценным markdown
        rep, ok = self._run(
            tmp_path,
            "**Что делает функция**\n\nПроцесс.\n\n- Задача\n"
            "  - Идентификатор\n")
        assert not any("расплющена" in r for r in rep), rep


class TestK24NestingDepth:
    """К-24: уплощение многоуровневых списков источника = брак;
    маловложенный источник (HTML-ul без md-отступов) — skip."""

    _SRC = ("---\ntitle: X\n---\n\n"
            "* Выполняется процесс:\n"
            "    + Содержимое файла формируется по правилу\n"
            "        - NNN - номер АС\n"
            "            - уточнение поля\n")

    def test_flattened_card_flagged(self):
        from app.scripts.CI.normalize_tables import check_nesting_depth
        card = ("- Выполняется процесс:\n- Содержимое файла формируется "
                "по правилу\n- NNN - номер АС\n- уточнение поля\n")
        rep, ok = check_nesting_depth(card, self._SRC)
        assert not ok and any("уплощена" in r for r in rep)

    def test_structured_card_clean(self):
        # тест на НЕсрабатывание: уровни перенесены отступами
        from app.scripts.CI.normalize_tables import check_nesting_depth
        card = ("- Выполняется процесс:\n"
                "  + Содержимое файла формируется по правилу\n"
                "    - NNN - номер АС\n"
                "      - уточнение поля\n")
        rep, ok = check_nesting_depth(card, self._SRC)
        assert ok, rep

    def test_shallow_source_skipped(self):
        # тест на НЕсрабатывание: источник без глубокой вложенности
        from app.scripts.CI.normalize_tables import check_nesting_depth
        src = "---\ntitle: X\n---\n\n- один\n- два\n"
        rep, ok = check_nesting_depth("- один\n- два\n", src)
        assert ok, rep


class TestK23StepHeadings:
    """К-23: шаги, объявленные md-заголовками «#### Шаг №N.», обязаны
    присутствовать в карточке — полная потеря поведения (мешок литералов
    вместо шагов) больше не проходит зелёной."""

    _SRC = ("---\ntitle: X\n---\n\n"
            "#### Шаг №1. Валидация запроса\n\nтекст\n\n"
            "#### Шаг №2. Создание задачи\n\nтекст\n\n"
            "##### Шаг №2.1. Подшаг\n\nтекст\n")

    def test_lost_steps_flagged(self):
        from app.scripts.CI.normalize_tables import check_step_markers
        card = "- Выгрузить в xml\n- NEW\n- FAILED\n- SEQ\n"
        rep, ok = check_step_markers(card, self._SRC)
        assert not ok and any("маркеры шагов" in r for r in rep)

    def test_steps_present_clean(self):
        # тест на НЕсрабатывание: шаги перенесены
        from app.scripts.CI.normalize_tables import check_step_markers
        card = ("- **Шаг №1.** Валидация запроса …\n"
                "- **Шаг №2.** Создание задачи …\n"
                "- **Шаг №2.1.** Подшаг …\n")
        rep, ok = check_step_markers(card, self._SRC)
        assert ok, rep

    def test_strong_declared_steps_collected(self):
        # объявления «**Шаг №N.**» (markdown-strong) тоже собираются
        from app.scripts.CI.normalize_tables import check_step_markers
        src = ("---\ntitle: X\n---\n\n**Шаг №1.** Проверка\n\n"
               "**Шаг №2.** Изменение статуса\n")
        rep, ok = check_step_markers("текст без шагов вовсе", src)
        assert not ok and any("маркеры шагов" in r for r in rep)

    def test_single_step_source_skipped(self):
        # тест на НЕсрабатывание: <2 шагов — сверять нечего
        from app.scripts.CI.normalize_tables import check_step_markers
        src = "---\ntitle: X\n---\n\n#### Шаг №1. Единственный\n"
        rep, ok = check_step_markers("текст без шагов", src)
        assert ok, rep


class TestK21OqRefsInCard:
    """К-21: отсылка к OQ в теле карточки = брак; слово
    «open-questions» без номера — легально."""

    def test_oq_ref_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: RBAC-001\ntitle: 'Р'\ntype: rbac\n---\n\n"
            "Заглушка: полное описание — см. OQ-014.\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("открытым вопросам" in r for r in rep)

    def test_no_numbered_ref_clean(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-CL-01\ntitle: 'Ф'\ntype: function\n---\n\n"
            "нерешённое фиксируется в open-questions комплекта\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep


class TestK19ExampleValuesAbsent:
    """К-19 (data-model): значения примеров источника НЕ должны попадать
    в карточку — ловится и частичный вырез (хвост примера); в function
    примеры легитимны, сторож не применяется."""

    _SRC = ('---\ntitle: X\n---\n\n'
            '<td><p>Назначение платежа с указанием ФЗ</p>'
            '<p>Пример: Оплата просроченного лизингового платежа по '
            'договору лизинга № 1122р/2л от 10.03.2022</p>'
            '<p>Реквизит №24 в 762-П.</p></td>\n')

    def test_example_tail_in_card_flagged(self):
        from app.scripts.CI.normalize_tables import (
            check_example_values_absent)
        card = ("Назначение платежа с указанием ФЗ лизингового платежа "
                "по договору лизинга № 1122р/2л Реквизит №24 в 762-П.")
        rep, ok = check_example_values_absent(card, self._SRC)
        assert not ok and any("значения примеров" in r for r in rep)

    def test_clean_card_ok(self):
        # тест на НЕсрабатывание: пример вырезан целиком
        from app.scripts.CI.normalize_tables import (
            check_example_values_absent)
        card = "Назначение платежа с указанием ФЗ Реквизит №24 в 762-П."
        rep, ok = check_example_values_absent(card, self._SRC)
        assert ok, rep

    def test_function_type_not_guarded(self, tmp_path):
        # тест на НЕсрабатывание: у function примеры переносятся легитимно
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text(self._SRC, encoding="utf-8")
        card = tmp_path / "card.md"
        card.write_text(
            "---\nid: FUN-CL-01\ntitle: 'X'\ntype: function\n---\n\n"
            "Назначение платежа с указанием ФЗ\n"
            "Пример: Оплата просроченного лизингового платежа по "
            "договору лизинга № 1122р/2л от 10.03.2022\n"
            "Реквизит №24 в 762-П.\n", encoding="utf-8")
        rep, ok = run_check([card], src)
        assert not any("значения примеров" in r for r in rep), rep


class TestK18FlkAndExamples:
    """К-18 (Э-3): колонки ФЛК/«Пример» и значения внутри «Пример: …»
    гейтами не требуются (их судьба — долг create-controls / шаблонное
    обезличивание ПД); прочие колонки и литералы — требуются."""

    def test_flk_column_not_required_md(self):
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("---\ntitle: X\n---\n\n"
               "| Атрибут | Тип | ФЛК |\n|---|---|---|\n"
               "| Номер | Число | не более 6 знаков |\n"
               "| Дата | Дата | только рабочие дни |\n")
        card = "| Номер | Число |\n| Дата | Дата |\n"
        rep, ok = check_source_tables(card, src)
        assert ok, rep

    def test_other_columns_still_required(self):
        # тест на НЕсрабатывание фильтра: потеря типа — брак по-прежнему
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("---\ntitle: X\n---\n\n"
               "| Атрибут | Тип | ФЛК |\n|---|---|---|\n"
               "| Номер | Число | не более 6 знаков |\n"
               "| Дата | Дата и время | — |\n")
        card = "| Номер | Число |\n| Дата |  |\n"
        rep, ok = check_source_tables(card, src)
        assert not ok and any("отсутствуют" in r for r in rep)

    def test_literal_inside_example_not_required(self):
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = ('---\ntitle: X\n---\n\n'
               '<td><p>Запрос</p><p><strong>Пример:</strong> '
               '{"userFio":"Выпискин О. О."}</p></td>\n'
               'кнопка "Сохранить" обязательна\n')
        card = "перенесено: кнопка Сохранить\n"
        rep, ok = check_quoted_literals(card, src)
        assert ok, rep

    def test_literal_in_next_cell_after_example_required(self):
        # тест на НЕсрабатывание: граница ячейки после «Пример:» —
        # следующий литерал снова требуется
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = ('---\ntitle: X\n---\n\n'
               '<td><strong>Пример:</strong> просто текст примера</td>\n'
               '<td>статус "Отклонено банком" обязателен</td>\n')
        card = "карточка без статуса\n"
        rep, ok = check_quoted_literals(card, src)
        assert not ok and any("отсутствуют" in r for r in rep)

    def test_flk_cell_quotes_not_required_html(self):
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = ('---\ntitle: X\n---\n\n'
               '<table><tbody>'
               '<tr><th>Атрибут</th><th>ФЛК</th></tr>'
               '<tr><td>Номер</td><td>Формат "000001" по правилам '
               'УФЭБС</td></tr>'
               '</tbody></table>\n')
        card = "Номер\n"
        rep, ok = check_quoted_literals(card, src)
        assert ok, rep


class TestK17OqPageRefs:
    """К-17: page_id/отсылки к Confluence в текстах open-questions —
    предупреждение (носители page_id — frontmatter и матрица)."""

    def test_page_id_and_bare_number_warned(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_oq_page_refs
        p = tmp_path / "open-questions.md"
        p.write_text(
            "## OQ-001\n\n**Вопрос:** страница confluence_page_id "
            "2169849344 не перенесена.\n\n- 2169849965 — Функция X\n",
            encoding="utf-8")
        rep, ok = check_oq_page_refs(p)
        assert ok  # софт-сигнал, вердикт не меняет
        assert len(rep) == 2
        assert all(r.startswith("предупреждение") for r in rep)

    def test_task_ids_dates_titles_clean(self, tmp_path):
        # тест на НЕсрабатывание: GBO-номера, даты, title + файл выгрузки
        from app.scripts.CI.normalize_tables import check_oq_page_refs
        p = tmp_path / "open-questions.md"
        p.write_text(
            "## OQ-002\n\n**Вопрос:** задача GBO-79044 от 2026-08-17; "
            "страница «[X] Функция импорта» "
            "(sources/выгрузка/страница.md) не покрыта.\n",
            encoding="utf-8")
        rep, ok = check_oq_page_refs(p)
        assert ok and not rep, rep


class TestK16BlankLineBreaksTable:
    """К-16: пустая строка внутри pipe-таблицы = разрыв (хвост рендерится
    плоско); пустая строка между СОСЕДНИМИ таблицами легальна."""

    def test_blank_after_separator_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: ENT-002\ntitle: 'С'\ntype: entity\n---\n\n"
            "| Параметр | Значение |\n|---|---|\n\n"
            "| Таблица БД | `x` |\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("разрывает таблицу" in r for r in rep)

    def test_blank_between_data_rows_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: ENT-002\ntitle: 'С'\ntype: entity\n---\n\n"
            "| А | Б |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("разрывает таблицу" in r for r in rep)

    def test_adjacent_tables_legal(self, tmp_path):
        # тест на НЕсрабатывание: две таблицы подряд через пустую строку
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: ENT-002\ntitle: 'С'\ntype: entity\n---\n\n"
            "| А | Б |\n|---|---|\n| 1 | 2 |\n\n"
            "| В | Г |\n|---|---|\n| 3 | 4 |\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep


class TestCleanDocumentGuard:
    """Сторож чистовика (волна D, Э-6): битые ссылки, цели вне docs/,
    изображения, critic-маркеры — брак; внешние http вне белого списка —
    предупреждение (софт-сигнал)."""

    def _docs(self, tmp_path):
        docs = tmp_path / "docs"
        (docs / "srs").mkdir(parents=True)
        (docs / "srs" / "target.md").write_text("# Цель\n", encoding="utf-8")
        return docs

    def _check(self, docs, body):
        from app.scripts.CI.normalize_tables import check_clean_document
        p = docs / "srs" / "card.md"
        p.write_text("---\nid: X-01\ntitle: 'К'\ntype: function\n---\n\n"
                     + body, encoding="utf-8")
        return check_clean_document(p, docs)

    def test_valid_relative_link_clean(self, tmp_path):
        # тест на НЕсрабатывание: живая ссылка внутрь docs + якорь
        docs = self._docs(tmp_path)
        rep, ok = self._check(
            docs, "см. [цель](target.md) и [якорь](target.md#раздел) "
                  "и [внутрифайловый](#ff-1-сохранить)\n")
        assert ok and not rep, rep

    def test_broken_link_flagged(self, tmp_path):
        docs = self._docs(tmp_path)
        rep, ok = self._check(docs, "[нет цели](missing.md)\n")
        assert not ok and any("битая" in r for r in rep)

    def test_link_outside_docs_flagged(self, tmp_path):
        docs = self._docs(tmp_path)
        (tmp_path / "sources").mkdir()
        (tmp_path / "sources" / "стр.md").write_text("x", encoding="utf-8")
        rep, ok = self._check(docs, "[выгрузка](../../sources/стр.md)\n")
        assert not ok and any("ВНЕ docs" in r for r in rep)

    def test_grey_http_is_warning_not_failure(self, tmp_path):
        docs = self._docs(tmp_path)
        rep, ok = self._check(
            docs, "[макет](https://www.figma.com/file/XYZ)\n")
        assert ok
        assert any(r.startswith("предупреждение") for r in rep)

    def test_whitelist_http_clean(self, tmp_path):
        # тест на НЕсрабатывание: конвенции eco-techbook легальны
        docs = self._docs(tmp_path)
        rep, ok = self._check(
            docs, "[conventions](https://gitlab.gboteam.ru/ED/eco-techbook"
                  "/-/blob/master/standards/analytics/conventions.md)\n")
        assert ok and not rep, rep

    def test_img_and_critic_and_stub_flagged(self, tmp_path):
        docs = self._docs(tmp_path)
        rep, ok = self._check(
            docs, '<img src="img/x.png"> и {++вставка++} и [заглушка](#)\n')
        assert not ok
        assert any("изображение" in r for r in rep)
        assert any("critic-маркер" in r for r in rep)
        assert any("заглушка" in r for r in rep)


class TestK14AnchorQuotesNotLiterals:
    """К-14: кавычки внутри адреса markdown-ссылки (якоря Confluence) —
    навигация, не литерал; тот же текст вне ссылки — литерал."""

    def test_quote_inside_anchor_not_required(self):
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = ('---\ntitle: X\n---\n\n'
               'см. [Дополнительные действия]'
               '(#id-[РРКО_ИПИ]ЭФКлиента"Журналдокументов"-Действия);\n'
               'и текст с литералом "Боевой код" в предложении.\n')
        card = "карточка несёт Боевой код и больше ничего\n"
        rep, ok = check_quoted_literals(card, src)
        assert ok, rep

    def test_same_quote_outside_link_required(self):
        # тест на НЕсрабатывание фильтра: литерал вне ссылки обязателен
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = ('---\ntitle: X\n---\n\n'
               'кнопка "Журнал документов" отображается всегда.\n')
        card = "карточка без текста кнопки\n"
        rep, ok = check_quoted_literals(card, src)
        assert not ok and any("отсутствуют" in r for r in rep)


class TestK13HtmlCommentGuard:
    """К-13 (анти-маскировка): HTML-коммент в чистовике = брак; значения
    внутри комментов сверкой значений не «находятся» (контрольный
    дозаход: обход гейта через <!-- selfcheck-coverage: … -->)."""

    def test_comment_in_card_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: SCR-CL-02\ntitle: 'Э'\ntype: screen-form\n---\n\n"
            "текст\n\n<!-- selfcheck-coverage: Назад · WEB · PDF -->\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("HTML-коммент" in r for r in rep)

    def test_no_comment_clean(self, tmp_path):
        # тест на НЕсрабатывание
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: SCR-CL-02\ntitle: 'Э'\ntype: screen-form\n---\n\n"
            "обычный текст без комментов\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep

    def test_value_only_in_comment_is_loss(self, tmp_path):
        # интеграция: значение источника, спрятанное в коммент, потерей
        # и остаётся — сверка значений комменты не видит
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text(
            "---\ntitle: 'Э'\nconfluence_page_id: '111'\n---\n\n"
            "| Код | Значение |\n|---|---|\n"
            "| A1 | Боевой код |\n| B2 | Второй код |\n",
            encoding="utf-8")
        card = tmp_path / "card.md"
        card.write_text(
            "---\nid: X-01\ntitle: 'Э'\ntype: screen-form\n---\n\n"
            "A1 Боевой код упомянут честно\n\n"
            "<!-- coverage: B2 · Второй код -->\n", encoding="utf-8")
        rep, ok = run_check([card], src)
        assert not ok
        assert any("отсутствуют" in r for r in rep), rep


class TestK12SurrogateParamCode:
    """К-12: номера строк в колонке «Код параметра» — суррогат (правило
    волны B: без технических имён источника код ПУСТОЙ)."""

    def test_numeric_codes_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-CL-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "| Код параметра | Наименование параметра | Тип |\n"
            "|---|---|---|\n"
            "| 1 | ID \"Пользователь\" | GUID |\n"
            "| 2.1 | Идентификатор объекта | GUID |\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("номера строк" in r for r in rep)

    def test_paths_and_empty_clean(self, tmp_path):
        # тест на НЕсрабатывание: пути и пустые коды легальны
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-CL-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "| Код параметра | Наименование параметра | Тип |\n"
            "|---|---|---|\n"
            "| `body.filter.date_from` | Дата с | Дата |\n"
            "|  | ID \"Пользователь\" | GUID |\n"
            "| `Тело запроса.file_id` | Файл | Строка |\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep

    def test_registry_number_column_untouched(self, tmp_path):
        # тест на НЕсрабатывание: «№» реестра полей — не «Код параметра»
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: SCR-CL-02.1\ntitle: 'Э'\ntype: screen-form\n---\n\n"
            "| № | Блок | Поле | Тип | Обяз. |\n|---|---|---|---|---|\n"
            "| 1 | — | FLD-1 «Заголовок» | Текст | — |\n"
            "| 2.1 | Счёт | FLD-2 «Счёт» | Список | Да |\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep


class TestStruckMarkerGuard:
    """Н-7 (волна C): «%зачёркнуто%» — постфиксный маркер выгрузки, в
    чистовике ему не место (инцидент scr-cl-02: инверсия смысла шага)."""

    def test_marker_in_card_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: SCR-CL-02\ntitle: 'Э'\ntype: screen-form\n---\n\n"
            "Шаг № 3 исключается %зачёркнуто%\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("%зачёркнуто%" in r for r in rep)

    def test_tilde_strike_legal(self, tmp_path):
        # тест на НЕсрабатывание: перенесённая семантика (~~…~~) — не брак
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: SCR-CL-02\ntitle: 'Э'\ntype: screen-form\n---\n\n"
            "~~Шаг № 3 исключается~~ (зачёркнуто источником — "
            "неактуально).\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep


class TestK10DuplicateHeaders:
    """К-10 (волна B): повторяющийся непустой заголовок шапки — сетка
    нормализатора как формат, брак; протяжки в данных легальны."""

    def test_duplicate_headers_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-CL-20\ntitle: 'Ф'\ntype: function\n---\n\n"
            "| № | Название параметра | Название параметра | Тип |\n"
            "|---|---|---|---|\n| 1 | Секция | Секция | Структура |\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("повторяющиеся заголовки" in r for r in rep)

    def test_data_row_spans_legal(self, tmp_path):
        # тест на НЕсрабатывание: протяжка в данных — не брак
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-CL-20\ntitle: 'Ф'\ntype: function\n---\n\n"
            "| № | Наименование параметра | Тип |\n|---|---|---|\n"
            "| 1 | Секция | Секция |\n| 1.1 | Поле | GUID |\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep

    def test_readme_registry_not_checked(self, tmp_path):
        # README-реестры — вне колонных проверок (К-4), дубли не флагуются
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "README.md"
        p.write_text("---\ntitle: 'Р'\n---\n\n"
                     "| Ա | X | X |\n|---|---|---|\n| 1 | а | б |\n",
                     encoding="utf-8")
        rep, ok = check_file(p, column_roles=False)
        assert ok, rep
