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
        # «Да» → произвольный текст-предложение: якорная колонка переписана.
        # («обязателен» из теста убран: нотация эталона узаконила токен —
        # разбор ✗ эталона 2026-08-21, см. test_etalon_obligation_tokens)
        _report, ok = self._check(
            self.GOOD.replace("| Да |", "| заполняется всегда |"), tmp_path)
        assert not ok

    def test_etalon_obligation_tokens_ok(self, tmp_path):
        # нотация эталона docs-account-opening-request: «обязателен» /
        # «необязателен» / «Да (вход)» / «Нет (исход)» — валидные значения
        good = (
            "# Карточка\n\n"
            "| Параметр | Обязательность |\n"
            "|---|---|\n"
            "| Идентификатор организации | необязателен |\n"
            "| Валюта | обязателен |\n"
            "| «Заявка» | Да (вход) |\n"
            "| «Признак» | Нет (исход) |\n"
        )
        report, ok = self._check(good, tmp_path)
        assert ok, report

    def test_obligation_sentence_still_caught(self, tmp_path):
        # тест на НЕсрабатывание расширения: предложение — по-прежнему брак
        bad = (
            "# Карточка\n\n"
            "| Параметр | Обязательность |\n"
            "|---|---|\n"
            "| Валюта | при наличии блока параметры обязательны |\n"
        )
        _report, ok = self._check(bad, tmp_path)
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


class TestK35PassportLabelColumn:
    """К-35: двухколонная таблица-паспорт «лейбл → значение» (целиком
    жирный лейбл в заголовочной ячейке И в первой ячейке каждой строки) —
    лейблы в карточке не требуются: они носители структуры и
    раскладываются в слоты шаблона. Значения второй колонки сторожатся
    по-прежнему. Прецедент — эталон O2+ ent-005/007/008 (2026-08-20):
    гейт требовал лейбл и агент гасил его жирной строкой-дублем рядом со
    слотом шаблона («Таблица БД» + «**Название физической таблицы БД**»)."""

    SOURCE = (
        "# Описание\n\n"
        "| **Назначение** | Хранение сведений о счетах по заявке. |\n"
        "| --- | --- |\n"
        "| **Когда создается запись сущности** | **TBD** |\n"
        "| **Когда изменяется запись сущности** | **TBD** |\n"
        "| **Название физической таблицы БД** | Заполняется разработкой |\n"
    )

    CARD = (
        "# ENT-005. Сведения о счетах\n\n"
        "Хранение сведений о счетах по заявке.\n\n"
        "### Когда создается запись сущности\n\n**TBD**\n\n"
        "### Когда изменяется запись сущности\n\n**TBD**\n\n"
        "| Параметр | Значение |\n|---|---|\n"
        "| Таблица БД | Заполняется разработкой |\n"
    )

    def test_labels_not_required(self):
        _report, ok = check_source_tables(self.CARD, self.SOURCE)
        assert ok

    def test_value_loss_still_caught(self):
        # тест на НЕсрабатывание послабления: потеря ЗНАЧЕНИЯ пары — брак
        card = self.CARD.replace(
            "| Таблица БД | Заполняется разработкой |\n", "")
        _report, ok = check_source_tables(card, self.SOURCE)
        assert not ok

    def test_plain_first_column_still_required(self):
        # двухколонный справочник с НЕжирной первой колонкой — данные:
        # первая колонка сторожится по-прежнему
        source = (
            "| Код | Описание |\n| --- | --- |\n"
            "| ACC_DU | Счёт доверительного управления |\n"
            "| ACC_STS | Специальный транзитный счёт |\n"
        )
        card = ("Счёт доверительного управления; "
                "Специальный транзитный счёт")
        _report, ok = check_source_tables(card, source)
        assert not ok

    def test_partial_bold_first_column_still_required(self):
        # жирные не ВСЕ первые ячейки — не паспорт: колонка сторожится
        source = (
            "| **Признак** | Значение |\n| --- | --- |\n"
            "| **Онлайн** | Да |\n"
            "| Офлайн-код | 7 |\n"
        )
        card = "Да 7 Признак Онлайн"
        _report, ok = check_source_tables(card, source)
        assert not ok


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


class TestCombinedObligationUniqueness:
    """Блокер COM-01 Корпкарт (2026-08-27): комбинированная колонка
    «Обязательность / Уникальность» («Да / Да») и строки-разделы
    (<td colspan=5>Реквизиты операции) давали 0% валидности и отказ."""

    def test_pair_values_valid(self):
        headers = ["Атрибут", "Тип", "Обязательность / Уникальность"]
        rows = [["code", "Строка", "Да / Да"],
                ["name", "Строка", "Да / Нет"],
                ["ref", "Строка", "Нет/Да"],
                ["opt", "Строка", "—"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] == 100.0

    def test_reversed_header_order(self):
        # источники пишут и «Уникальность/Обязательность»
        headers = ["Атрибут", "Уникальность/Обязательность"]
        rows = [["a", "Да / Нет"], ["b", "Нет/Да"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] == 100.0

    def test_plain_obligation_column_still_strict(self):
        # НЕсрабатывание: в ОБЫЧНОЙ колонке «Обязательность» пара — брак
        # (защита от съехавших ролей не ослаблена)
        headers = ["Атрибут", "Обязательность"]
        rows = [["a", "Да / Да"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] < 100

    def test_section_rows_excluded_from_validation(self):
        # заголовок группы протянут colspan'ом на всю ширину — не данные
        headers = ["Атрибут", "Тип", "Обязательность / Уникальность"]
        rows = [["Реквизиты операции", "Реквизиты операции",
                 "Реквизиты операции"],
                ["code", "Строка", "Да / Да"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] == 100.0
        assert report["обязат"]["total"] == 1

    def test_data_row_not_treated_as_section(self):
        # НЕсрабатывание: строка с РАЗНЫМИ значениями остаётся данными,
        # и брак в ней по-прежнему виден
        headers = ["Атрибут", "Тип", "Обязательность / Уникальность"]
        rows = [["code", "Строка", "текст вместо обязательности"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] < 100

    def test_narrow_table_not_section(self):
        # НЕсрабатывание: в узкой таблице (2 колонки) повтор значения —
        # не строка-раздел (порог ширины ≥3)
        headers = ["Название", "Обязательность"]
        rows = [["Да", "Да"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["total"] == 1

    def test_pair_with_parenthetical_tail(self):
        # «Набор фильтров» КК: автор дописал состав ключа уникальности
        # скобками со второй строки ячейки — валидность не ломается
        headers = ["Атрибут", "Тип", "Обязательность / Уникальность"]
        rows = [["a", "Строка",
                 "Да / Да<br>(код экранной формы + Наименование)"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] == 100.0

    def test_section_row_with_empty_edges(self):
        # 2FA КК: секция colspan=5 при 7 колонках сетки — крайние пустые;
        # повтор ≥3 раз распознаётся как раздел
        headers = ["№", "Тех", "Рус", "Уникальность/Обязательность",
                   "Тип", "Формат", "Прим"]
        rows = [["", "Реквизиты операции", "Реквизиты операции",
                 "Реквизиты операции", "Реквизиты операции",
                 "Реквизиты операции", ""],
                ["1", "code", "Код", "Да / Нет", "Строка", "", ""]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] == 100.0
        assert report["обязат"]["total"] == 1

    def test_section_row_with_section_number(self):
        # 2FA КК фактическая форма: номер раздела в первой колонке +
        # протяжка ×5 — тоже раздел
        headers = ["№", "Тех", "Рус", "Уникальность/Обязательность",
                   "Тип", "Формат", "Прим"]
        rows = [["1", "Реквизиты операции", "Реквизиты операции",
                 "Реквизиты операции", "Реквизиты операции",
                 "Реквизиты операции", ""],
                ["1.1", "code", "Код", "Да / Нет", "Строка", "", ""]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] == 100.0
        assert report["обязат"]["total"] == 1

    def test_boolean_repeats_stay_data(self):
        # НЕсрабатывание: повтор «Нет» в булевых колонках — данные,
        # не раздел (токены обязательности исключены из признака)
        headers = ["Атрибут", "Видимость", "Редактируемость",
                   "Обязательность"]
        rows = [["a", "Нет", "Нет", "Нет"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["total"] == 1

    def test_single_filled_cell_row_stays_data(self):
        # НЕсрабатывание (гейт качества): строка с одним заполненным
        # значением и пустым хвостом — данные, съехавший профиль виден
        headers = ["Путь", "Название", "Обязательность"]
        rows = [["все поля внутри блока передаются строкой", "", ""]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=0)}
        assert report["путь"]["valid_pct"] < 100


class TestSourceModeValidators:
    """Калибровка ISS-01 (КК_ВК, 2026-08-27): жирная обязательность,
    голая логическая кратность источника, колонка физимён БД."""

    def test_bold_obligation_valid(self):
        headers = ["Путь", "Обязательность"]
        rows = [["A/B", "**Да**"], ["A/C", "**Нет**"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=0)}
        assert report["обязат"]["valid_pct"] == 100.0

    def test_bare_cardinality_valid_in_source_mode(self):
        headers = ["Путь", "Кратность"]
        rows = [["A/B", "1"], ["A/C", "0..1"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=0,
                                   source_mode=True)}
        assert report["кратн"]["valid_pct"] == 100.0

    def test_bare_cardinality_still_defect_in_card_check(self):
        # НЕсрабатывание ослабления: защита от раскавычивания [1] → 1
        # в проверке КАРТОЧКИ не тронута
        headers = ["Путь", "Кратность"]
        rows = [["A/B", "1"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=0)}
        assert report["кратн"]["valid_pct"] < 100

    def test_db_field_column_gets_no_name_role(self):
        # «[DEV] Название поля в таблице БД» — физимена, не названия
        headers = ["Путь", "[DEV] Название поля в таблице БД"]
        rows = [["A/B", "eco_card_request.user_id"]]
        report = validate_columns(headers, rows, path_index=0)
        assert all(c["role"] != "название" for c in report)

    def test_bold_cardinality_valid(self):
        # КК_ВК пишет кратность жирной: «**1**», «**0..1**»
        headers = ["Путь", "Кратность"]
        rows = [["A/B", "**1**"], ["A/C", "**0..1**"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=0,
                                   source_mode=True)}
        assert report["кратн"]["valid_pct"] == 100.0

    def test_conditional_obligation_valid(self):
        # условная обязательность авторским текстом
        headers = ["Путь", "Обязательность"]
        rows = [["A/B", "Да, если не заполнен Адрес пребывания"]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=0)}
        assert report["обязат"]["valid_pct"] == 100.0

    def test_short_description_not_cardinality(self):
        # «Краткое описание» — не роль кратность (ложный префикс-матч)
        headers = ["Код", "Краткое описание"]
        rows = [["X1", "Бесплатный выпуск за 5 минут"]]
        report = validate_columns(headers, rows, path_index=None)
        assert all(c["role"] != "кратн" for c in report)

    def test_table_without_anchor_roles_not_validated(self, tmp_path):
        # мета-таблица свойств страницы («Назначение | …») не валидируется
        # и не блокирует sidecar; сетка отдана как есть
        from app.scripts.CI.normalize_tables import normalize_file
        f = tmp_path / "page.md"
        f.write_text(
            "<table><tr><th>Назначение</th><th>Описание</th></tr>"
            "<tr><td>Когда создается запись</td>"
            "<td>Запись может быть создана</td></tr></table>\n",
            encoding="utf-8")
        out, report, ok = normalize_file(f, None, None)
        assert ok, "\n".join(report)
        assert any("без якорных ролей" in ln for ln in report)
        assert "Когда создается запись" in out


class TestCellCoverage:
    """Сторож полноты ячеек (COM-01 Корпкарт 2026-08-27): хвосты ячеек
    Тип/Описание источника обязаны быть покрыты текстом комплекта в
    нормальной форме; иерархия и разметка при переносе свободны."""

    SOURCE = (
        "# Постановка\n\n"
        "<table>\n"
        "<tr><th>№</th><th>Наименование поля</th><th>Тип</th>"
        "<th>Обязательность / Уникальность</th><th>Описание</th></tr>\n"
        "<tr><td>1</td><td>Идентификатор операции</td>"
        "<td>Строка (36)<br>допустимый алфавит: цифры, английские буквы"
        "</td><td>Да / Нет</td>"
        "<td>Уникальный идентификатор операции. Совместно с \"Каналом\" "
        "входит в составной ключ.</td></tr>\n"
        "<tr><td>2</td><td>Канал</td>"
        "<td>Строка с одним из значений: OMNI</td><td>Да / Нет</td>"
        "<td>Код системы. OMNI - универсальный сервис \"Реквизиты карты\""
        "</td></tr>\n"
        "<tr><td>3</td><td>Тип адреса</td>"
        "<td>Строка с одним из значений: SMS PUSH EMAIL</td>"
        "<td>Нет / Нет</td><td>Канал доставки кода</td></tr>\n"
        "</table>\n"
    )

    FULL_CORPUS = (
        "| Идентификатор операции | | Строка (36), допустимый алфавит: "
        "цифры, английские буквы | Да | Нет | Уникальный идентификатор "
        "операции. Совместно с «Каналом» входит в составной ключ |\n"
        "| Канал | | Строка с одним из значений | Да | Нет | Код системы. "
        "Допустимые значения — справочник |\n"
        "| Тип адреса | | Строка с одним из значений | Нет | Нет | "
        "Канал доставки кода |\n"
        "### Каналы\n| Код | Название |\n|---|---|\n"
        "| `OMNI` | Универсальный сервис «Реквизиты карты» |\n"
        "### Типы адреса\n| Код |\n|---|\n| `SMS` |\n| `PUSH` |\n"
        "| `EMAIL` |\n"
    )

    def test_full_transfer_covered(self):
        # НЕсрабатывание: канонные трансформации — enum в справочник
        # (пары «код - расшифровка» строками таблицы, латинский перечень
        # по строкам), типографские кавычки, ссылка вместо перечня
        from app.scripts.CI.normalize_tables import check_cell_coverage
        report, ok = check_cell_coverage(self.SOURCE, self.FULL_CORPUS)
        assert ok, "\n".join(report)
        assert any("потерь 0" in ln for ln in report)

    def test_lost_tail_caught(self):
        # срабатывание: потеряны алфавит (Тип), составной ключ (Описание)
        from app.scripts.CI.normalize_tables import check_cell_coverage
        corpus = (self.FULL_CORPUS
                  .replace(", допустимый алфавит: цифры, английские буквы",
                           "")
                  .replace(" Совместно с «Каналом» входит в составной "
                           "ключ", ""))
        report, ok = check_cell_coverage(self.SOURCE, corpus)
        assert not ok
        text = "\n".join(report)
        assert "алфавит" in text and "составной ключ" in text

    def test_lost_enum_meaning_caught(self):
        # срабатывание: расшифровка значения выброшена из справочника
        from app.scripts.CI.normalize_tables import check_cell_coverage
        corpus = self.FULL_CORPUS.replace(
            "| `OMNI` | Универсальный сервис «Реквизиты карты» |",
            "| `OMNI` |  |")
        report, ok = check_cell_coverage(self.SOURCE, corpus)
        assert not ok
        assert any("универсальный сервис" in ln for ln in report)

    def test_example_tail_not_required(self):
        # НЕсрабатывание: «Пример: …» удаляется из карточек ПО ШАБЛОНУ —
        # его отсутствие в комплекте не потеря
        from app.scripts.CI.normalize_tables import check_cell_coverage
        src = ("<table><tr><th>Поле</th><th>Тип</th><th>Описание</th></tr>"
               "<tr><td>Код</td><td>Строка</td>"
               "<td>Код колонки.<br>Пример: CC_ORG_NAME</td></tr>"
               "</table>")
        report, ok = check_cell_coverage(
            src, "| Код | Строка | Код колонки |")
        assert ok, "\n".join(report)

    def test_reference_construction_pardoned(self):
        # НЕсрабатывание: «Ссылка на идентификатор записи справочника
        # "Пользователь"» в карточке легально становится EXT-ссылкой
        from app.scripts.CI.normalize_tables import check_cell_coverage
        src = ("<table><tr><th>Поле</th><th>Описание</th></tr>"
               "<tr><td>Логин</td><td>Ссылка на идентификатор записи "
               "справочника \"Пользователь\"</td></tr></table>")
        report, ok = check_cell_coverage(
            src, "| Логин | [EXT-001 Пользователь](dictionaries.md) |")
        assert ok, "\n".join(report)

    def test_inserted_service_words_pardoned(self):
        # НЕсрабатывание: вставка служебных слов переносом («в
        # соответствии СО СТАТУСНОЙ МОДЕЛЬЮ „X“») — слова фрагмента по
        # порядку в одном окне корпуса
        from app.scripts.CI.normalize_tables import check_cell_coverage
        src = ("<table><tr><th>Поле</th><th>Описание</th></tr>"
               "<tr><td>Статус</td><td>Текущий статус в соответствии с "
               "[КК] Статусы операции</td></tr></table>")
        report, ok = check_cell_coverage(
            src, "| Статус | Текущий статус запроса в соответствии со "
                 "статусной моделью «[КК] Статусы операции» |")
        assert ok, "\n".join(report)

    def test_scattered_words_still_lost(self):
        # срабатывание: слова фрагмента есть в корпусе РОССЫПЬЮ по разным
        # местам — окно не милует, потеря видна
        from app.scripts.CI.normalize_tables import check_cell_coverage
        src = ("<table><tr><th>Поле</th><th>Описание</th></tr>"
               "<tr><td>Тип</td><td>Тип операции для которой выполняется "
               "подтверждение</td></tr></table>")
        corpus = ("| Тип операции | значения из справочника |\n"
                  "| Другое | для карты которой выполняется операция |\n"
                  "| Третье | требует подтверждение |")
        report, ok = check_cell_coverage(src, corpus)
        assert not ok

    def test_markdown_link_with_colon_not_split(self):
        # блокер ISS-01: ссылка с «:» в тексте резалась пополам ДО
        # снятия markdown — правая половина требовала сырой URL
        from app.scripts.CI.normalize_tables import check_cell_coverage
        src = ("<table><tr><th>Поле</th><th>Описание</th></tr>"
               "<tr><td>Валюта</td><td>Справочник "
               "[[СпрВал] Модель данных: Валюта]"
               "(https://confluence.x/pages/123)</td></tr></table>")
        report, ok = check_cell_coverage(
            src, "| Валюта | Справочник [СпрВал] Модель данных: Валюта |")
        assert ok, "\n".join(report)
        assert not any("https" in ln for ln in report)

    def test_section_rows_and_alien_tables_skipped(self):
        # НЕсрабатывание: секционные строки и таблицы без целевых
        # колонок (перечни кодов) не проверяются
        from app.scripts.CI.normalize_tables import check_cell_coverage
        src = (
            "<table>\n"
            "<tr><th>№</th><th>Поле</th><th>Тип</th><th>Описание</th></tr>\n"
            "<tr><td>1</td><td colspan=\"3\"><strong>Реквизиты операции"
            "</strong></td></tr>\n"
            "<tr><td>2</td><td>Код</td><td>Строка</td><td>Код записи"
            "</td></tr>\n"
            "</table>\n"
            "<table>\n<tr><th>Код отказа</th><th>Причина</th></tr>\n"
            "<tr><td>E01</td><td>Совсем непереносимый текст</td></tr>\n"
            "</table>\n"
        )
        report, ok = check_cell_coverage(
            src, "| Код | | Строка | Код записи |")
        assert ok, "\n".join(report)


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


class TestTuzFormulaAndTargetMentions:
    """Сторожа триады по решениям 2026-08-19: формула ТУЗ обычным
    шрифтом (шаблон function §2) и теговые упоминания целей
    (ссылка на карточку или долг в матрице)."""

    def _docs(self, tmp_path):
        docs = tmp_path / "docs"
        (docs / "srs").mkdir(parents=True)
        (docs / "srs" / "ent-001.md").write_text(
            "---\nid: ENT-001\n"
            "title: '[РРКО_ИПИ] Инкассовое поручение исходящее'\n"
            "type: data-model\n---\n\n# ENT-001\n", encoding="utf-8")
        (docs / "traceability-matrix.md").write_text(
            "# Матрица\n\n| Источник | Долг |\n|---|---|\n"
            "| FUN-SYS-03 | Страница «Методы» — требуется заход "
            "create-function |\n", encoding="utf-8")
        return docs

    def test_tuz_bold_flagged(self):
        from app.scripts.CI.normalize_tables import check_tuz_formula
        rep, ok = check_tuz_formula(
            "- **Системная функция; вызов с ТУЗ; роли и привилегии "
            "не применяются.**\n")
        assert not ok and "формула ТУЗ" in rep[0]

    def test_tuz_plain_ok(self):
        # НЕсрабатывание: обычный шрифт легитимен
        from app.scripts.CI.normalize_tables import check_tuz_formula
        rep, ok = check_tuz_formula(
            "- Системная функция; вызов с ТУЗ; роли и привилегии "
            "не применяются.\n")
        assert ok and rep == []

    def test_existing_title_without_link_warned(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_target_mentions
        docs = self._docs(tmp_path)
        card = docs / "srs" / "fun-sys-03.md"
        card.write_text(
            "---\nid: FUN-SYS-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "| ID \"[РРКО_ИПИ] Инкассовое поручение исходящее\" | GUID |\n",
            encoding="utf-8")
        warns, ok = check_target_mentions(
            card.read_text(encoding="utf-8"), card, docs)
        assert ok  # софт: вердикт не трогает
        assert any("имя существующей карточки без ссылки" in w
                   and "ent-001.md" in w for w in warns)

    def test_linked_title_not_warned(self, tmp_path):
        # НЕсрабатывание: оформленная ссылка сторожу не видна
        from app.scripts.CI.normalize_tables import check_target_mentions
        docs = self._docs(tmp_path)
        card = docs / "srs" / "fun-sys-03.md"
        card.write_text(
            "---\nid: FUN-SYS-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "см. [[РРКО_ИПИ] Инкассовое поручение исходящее]"
            "(ent-001.md)\n", encoding="utf-8")
        warns, _ = check_target_mentions(
            card.read_text(encoding="utf-8"), card, docs)
        assert warns == []

    def test_unknown_target_without_debt_warned(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_target_mentions
        docs = self._docs(tmp_path)
        card = docs / "srs" / "fun-sys-03.md"
        card.write_text(
            "---\nid: FUN-SYS-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "вызов функции [РРКО_ИПИ] Система: Функция сохранения "
            "статуса, вызываемой при работе.\n", encoding="utf-8")
        warns, _ = check_target_mentions(
            card.read_text(encoding="utf-8"), card, docs)
        assert any("упоминание цели" in w and "следа в матрице" in w
                   for w in warns)

    def test_debt_in_matrix_not_warned(self, tmp_path):
        # НЕсрабатывание: игла (без тега, ≤3 слова) находит долг
        from app.scripts.CI.normalize_tables import check_target_mentions
        docs = self._docs(tmp_path)
        card = docs / "srs" / "fun-sys-03.md"
        card.write_text(
            "---\nid: FUN-SYS-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "проверки см. в [РРКО_ИПИ] Методы.\n",
            encoding="utf-8")
        warns, _ = check_target_mentions(
            card.read_text(encoding="utf-8"), card, docs)
        assert warns == []

    def test_cardinality_brackets_not_mentions(self, tmp_path):
        # НЕсрабатывание: [1], [0..1], [x] — не теговые упоминания
        from app.scripts.CI.normalize_tables import check_target_mentions
        docs = self._docs(tmp_path)
        card = docs / "srs" / "fun-sys-03.md"
        card.write_text(
            "---\nid: FUN-SYS-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "| Кратность [1] | Массив [0..1] Да |\n", encoding="utf-8")
        warns, _ = check_target_mentions(
            card.read_text(encoding="utf-8"), card, docs)
        assert warns == []


class TestK31Homoglyphs:
    """К-31: латиница внутри кириллического слова (и наоборот) = брак
    (пилот-2: «Kратность» с латинской K выключила роль колонки)."""

    def test_latin_k_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-SYS-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "| Обяз. | Kратность |\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("гомоглифы" in r and "Kратность" in r
                              for r in rep)

    def test_plantuml_escape_not_flagged(self, tmp_path):
        # НЕсрабатывание: «\nИПИ» в метке PlantUML — эскейп, не гомоглиф
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: PRC-01\ntitle: 'П'\ntype: process\n---\n\n"
            "```plantuml\n:1.1 Начальное событие:\\nИнициировано "
            "создание ИПИ;\n```\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert ok and not any("гомоглифы" in r for r in rep)

    def test_clean_scripts_not_flagged(self, tmp_path):
        # НЕсрабатывание: чистые слова, коды, дефисные пары, Ф1
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-SYS-03\ntitle: 'Ф'\ntype: function\n---\n\n"
            "Кратность и DELETED, md-файл, АБС Ф1, `q_eco_d_inks`, "
            "ISO20022.01, ЭФ Клиента.\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert ok and not any("гомоглифы" in r for r in rep)


class TestK32SourceTagMentions:
    """К-32: теговое упоминание источника сохраняется в карточке —
    тег на месте или ссылка; слова без тега вне ссылки = дефейс."""

    _SRC = ("<h1>[РРКО_ИПИ] Система: Функция удаления документа</h1>"
            "<table><tr><td>Что делает функция:</td><td>Проверки см в "
            "[РРКО_ИПИ] Методы для конкретной функции; далее работа "
            "</td></tr></table>")

    def _card(self, poведение):
        return ("---\nid: FUN-SYS-03\n"
                "title: '[РРКО_ИПИ] Система: Функция удаления документа'\n"
                "type: function\n---\n\n## Поведение\n\n" + poведение)

    def test_defaced_tag_flagged(self):
        from app.scripts.CI.normalize_tables import check_source_tag_mentions
        rep, ok = check_source_tag_mentions(
            self._card("Проверки см в Методы для конкретной функции\n"),
            self._SRC)
        assert not ok and any("дефейс" in r and "Методы" in r for r in rep)

    def test_tag_intact_ok(self):
        # НЕсрабатывание: тег на месте
        from app.scripts.CI.normalize_tables import check_source_tag_mentions
        rep, ok = check_source_tag_mentions(
            self._card("Проверки см в [РРКО_ИПИ] Методы для конкретной "
                       "функции\n"), self._SRC)
        assert ok and not any("дефейс" in r for r in rep)

    def test_linked_mention_ok(self):
        # НЕсрабатывание: оформлено ссылкой, тег в ссылке заменён на ID
        from app.scripts.CI.normalize_tables import check_source_tag_mentions
        rep, ok = check_source_tag_mentions(
            self._card("Проверки см в [FUN-SYS-99 Методы для конкретной "
                       "функции](../fun-sys-99.md)\n"), self._SRC)
        assert ok and not any("дефейс" in r for r in rep)

    def test_registry_style_name_with_link_exempt(self, tmp_path):
        # НЕсрабатывание: имя существующей карточки без тега + ссылка
        # на её файл (реестровая конвенция README/матрицы; дисплей
        # ссылки с ID-переименованием иглу не несёт)
        from app.scripts.CI.normalize_tables import check_source_tag_mentions
        docs = tmp_path / "docs"
        (docs / "client").mkdir(parents=True)
        (docs / "client" / "fun-cl-99-methods.md").write_text(
            "---\nid: FUN-CL-99\n"
            "title: '[РРКО_ИПИ] Методы для конкретной функции'\n"
            "type: function\n---\n", encoding="utf-8")
        card = self._card(
            "| FUN-CL-99 | Методы для конкретной функции | "
            "[client/fun-cl-99-methods.md](client/fun-cl-99-methods.md) |\n")
        rep, ok = check_source_tag_mentions(card, self._SRC, docs)
        assert ok and not any("Методы" in r for r in rep)

    def test_absent_mention_warns_not_flags(self):
        # отсутствие целиком — предупреждение, не брак
        from app.scripts.CI.normalize_tables import check_source_tag_mentions
        rep, ok = check_source_tag_mentions(
            self._card("Совсем другой текст.\n"), self._SRC)
        assert ok and any(r.startswith("предупреждение") and "Методы" in r
                          for r in rep)


class TestK34LabelSections:
    """К-34: лейблы двухъячеечных пар источника не переносятся в
    карточку функции ни жирной строкой, ни парой-таблицей; жирный
    текст внутри значения ячейки («ПРИМЕЧАНИЯ!») — контент."""

    _SRC = ("---\ntitle: X\n---\n\n<table><tbody>"
            "<tr><td><strong>Что делает функция:</strong></td>"
            "<td><p>Проверки при вызове метода выполняются штатно.</p>"
            "<p><strong>ПРИМЕЧАНИЯ!</strong></p>"
            "<p>исходим из одного документа</p></td></tr>"
            "<tr><td>Доступность функции</td>"
            "<td>Доступ к функции не ограничен (ТУЗ)</td></tr>"
            "</tbody></table>\n")

    def test_bold_label_line_flagged(self):
        from app.scripts.CI.normalize_tables import check_label_sections
        rep, ok = check_label_sections(
            "## Назначение\n\n**Что делает функция:**\n\nПроверки при "
            "вызове метода выполняются штатно.\n", self._SRC)
        assert not ok and "К-34" in rep[0] and "Что делает функция" in rep[0]

    def test_passport_pair_table_flagged(self):
        from app.scripts.CI.normalize_tables import check_label_sections
        rep, ok = check_label_sections(
            "| **Доступность функции** | Доступ к функции не ограничен "
            "(ТУЗ) |\n| --- | --- |\n", self._SRC)
        assert not ok and "Доступность функции" in rep[0]

    def test_bold_content_not_flagged(self):
        # НЕсрабатывание: «ПРИМЕЧАНИЯ!» — жирный текст ВНУТРИ значения
        # ячейки, не лейбл пары — переносится как есть
        from app.scripts.CI.normalize_tables import check_label_sections
        rep, ok = check_label_sections(
            "## Поведение\n\nПроверки при вызове метода выполняются "
            "штатно.\n\n**ПРИМЕЧАНИЯ!**\n\nисходим из одного "
            "документа\n", self._SRC)
        assert ok and rep == []

    def test_data_model_passport_not_flagged(self, tmp_path):
        # НЕсрабатывание: у data-model паспорт-таблица — слот шаблона;
        # гейт по type в run_check
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "s.md"
        src.write_text("---\nconfluence_page_id: 1\ntitle: '[Т] С'\n"
                       "---\n\n<h1>[Т] С</h1>" + self._SRC.split(
                           "---\n\n", 1)[1], encoding="utf-8")
        card = tmp_path / "ent.md"
        card.write_text(
            "---\nid: ENT-001\ntitle: '[Т] С'\ntype: data-model\n---\n\n"
            "# ENT-001\n\n| **Доступность функции** | Доступ к функции "
            "не ограничен (ТУЗ) |\n|---|---|\n", encoding="utf-8")
        rep, _ = run_check([card], src)
        assert not any("К-34" in r for r in rep)


class TestK33NestedLinks:
    """К-33: ссылка внутри текста другой ссылки / обёртка ссылки в
    скобки = брак (след генераторной правки 5.5; двойная обёртка
    проходила все сторожа)."""

    def _card(self, body, title="'Ф'"):
        return (f"---\nid: FUN-SYS-02\ntitle: {title}\n"
                f"type: function\n---\n\n{body}\n")

    def test_double_wrap_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(self._card(
            "- При выполнении [[[[РРКО_ИПИ] Клиент: Функция снятия "
            "подписи](../client/fun-cl-08.md)]](../client/fun-cl-08.md)"),
            encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("К-33" in r for r in rep)

    def test_link_inside_title_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(self._card(
            "текст",
            title="'[[[РРКО_ИПИ] Клиент: Функция создания документа]"
                  "(fun-cl-02.md)] из шаблона'"), encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("К-33" in r for r in rep)

    def test_tagged_display_legit(self, tmp_path):
        # НЕсрабатывание: скобочный тег в дисплее — скобка самой ссылки
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(self._card(
            'ID "[[РРКО_ИПИ] Инкассовое поручение исходящее]'
            '(../../data-model/ent-001.md)" и кратность [1] (пояснение)'),
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok and not any("К-33" in r for r in rep)


class TestK30InvisibleChars:
    """К-30: zero-width/BOM в чистовике = брак (обход границы секций
    дозаходом 5.3)."""

    def test_zwsp_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-CL-08\ntitle: 'Ф'\ntype: function\n---\n\n"
            "**ИНАЧЕ​**\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("невидимые символы" in r for r in rep)

    def test_bold_content_line_not_section_boundary(self):
        # фикс границы: «**ИНАЧЕ**» внутри секции не рвёт профиль
        from app.scripts.CI.normalize_tables import (
            check_heavy_pair_structure, html_fragment_to_markdown)
        cell = ("<p>Функция проверяет возможность отклонения документа "
                "администратором банка по статусной модели заявки.</p>"
                "<p><strong>ИНАЧЕ</strong></p>"
                "<p><strong>завершение процесса.</strong></p>")
        src = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
               "<td><strong>Что делает функция:</strong></td>"
               "<td>" + cell + "</td></tr></tbody></table>\n")
        card = ("**Что делает функция:**\n\n"
                + html_fragment_to_markdown(cell) + "\n")
        rep, ok = check_heavy_pair_structure(card, src)
        assert ok, rep


class TestProbeAcrossBlockBoundary:
    """Проба, пересекающая границу абзацев эталона («Функция
    вызывается:» + список), находится в правильно разложенной карточке
    (фикс 5.5-фикс: построчный поиск требовал склейки строк и
    противоречил профилю — исполнитель подгонял текст под прибор)."""

    _CELL = ("<p>Функция вызывается:</p><ul>"
             "<li>При выполнении Клиент: Функция отправки документа "
             "на обработку в банк по клиентскому сценарию</li>"
             "<li>Автоматически при переходе документа в статус SIGNED "
             "по статусной модели сервиса обработки</li></ul>")
    _SRC = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
            "<td><strong>Что делает функция:</strong></td>"
            "<td>" + _CELL + "</td></tr></tbody></table>\n")

    def test_correct_layout_not_flagged(self):
        from app.scripts.CI.normalize_tables import (
            check_heavy_pair_structure, html_fragment_to_markdown)
        card = ("## Вызов функции\n\n"
                + html_fragment_to_markdown(self._CELL) + "\n")
        rep, ok = check_heavy_pair_structure(card, self._SRC)
        assert ok, rep

    def test_loss_still_flagged(self):
        # НЕсрабатывание наоборот: содержимого нет — потеря видна
        from app.scripts.CI.normalize_tables import (
            check_heavy_pair_structure)
        card = "## Вызов функции\n\nСовсем другой текст.\n"
        rep, ok = check_heavy_pair_structure(card, self._SRC)
        assert not ok


class TestK25dPairSectionProfiles:
    """К-25d: p-абзацная секция сверяется профилем (склейка шести
    абзацев в один — усечение профиля); корректная секция чиста."""

    _CELL = ("<p>Функция вызывается в рамках метода обработки заявки "
             "клиента банка на удаление платёжного документа.</p>"
             "<p>При вызове осуществляется проверка возможности смены "
             "статуса для текущего документа по модели статусов.</p>"
             "<p>Сохранение нового статуса выполняется функцией "
             "сохранения статуса при работе стейт-машины сервиса.</p>")
    _SRC = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
            "<td><strong>Что делает функция:</strong></td>"
            "<td>" + _CELL + "</td></tr></tbody></table>\n")

    def test_glued_paragraphs_flagged(self):
        from app.scripts.CI.normalize_tables import (
            check_heavy_pair_structure, html_fragment_to_markdown)
        glued = html_fragment_to_markdown(self._CELL).replace("\n\n", " ")
        card = "**Что делает функция:**\n\n" + glued + "\n"
        rep, ok = check_heavy_pair_structure(card, self._SRC)
        assert not ok and any("расходится с эталоном" in r for r in rep)

    def test_etalon_section_clean(self):
        from app.scripts.CI.normalize_tables import (
            check_heavy_pair_structure, html_fragment_to_markdown)
        card = ("**Что делает функция:**\n\n"
                + html_fragment_to_markdown(self._CELL) + "\n")
        rep, ok = check_heavy_pair_structure(card, self._SRC)
        assert ok, rep

    def test_list_layout_is_signal_not_defect(self):
        # решение 2026-08-29 (README SCR-CL-01): раскладка тяжёлой пары
        # markdown-СПИСКОМ легальна — профиль эталона (quote-абзацы
        # конвертера) не требуется, i-сигнал вместо ✗
        from app.scripts.CI.normalize_tables import (
            check_heavy_pair_structure, html_fragment_to_markdown)
        md = html_fragment_to_markdown(self._CELL)
        as_list = "\n".join("- " + p for p in md.split("\n\n") if p.strip())
        card = "**Что делает функция:**\n\n" + as_list + "\n"
        rep, ok = check_heavy_pair_structure(card, self._SRC)
        assert ok, rep
        assert any(r.startswith("i тяжёлая пара разложена") for r in rep)

    def test_naznachenie_duplicate_head_not_flagged(self):
        # дубль начала ячейки в «Назначении» (первые предложения
        # дословно) легитимен: сверка идёт с ЛУЧШИМ вхождением
        from app.scripts.CI.normalize_tables import (
            check_heavy_pair_structure, html_fragment_to_markdown)
        md = html_fragment_to_markdown(self._CELL)
        first_para = md.split("\n\n")[0]
        card = ("## Назначение\n\n" + first_para + "\n\n"
                "## Поведение\n\n" + md + "\n")
        rep, ok = check_heavy_pair_structure(card, self._SRC)
        assert ok, rep


class TestK29HeavyCellInvariant:
    """К-29: тяжёлая ячейка (в т.ч. p-абзацами без ul) не коллапсирует
    в |-строку карточки; короткие правило-ячейки в таблицах легальны."""

    _CELL = ("<p>Функция публикует в очереди сервиса сообщение об "
             "удалении документа и связанных с ним сущностей учёта.</p>"
             "<p>При вызове функции выполняется проверка возможности "
             "удаления по статусной модели документа и организации.</p>"
             "<p>После успешного удаления формируется запись истории "
             "операций и уведомление администратору системы банка.</p>")
    _SRC = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
            "<td><strong>Описание работы:</strong></td>"
            "<td>" + _CELL + "</td></tr></tbody></table>\n")

    def test_collapsed_heavy_cell_flagged(self):
        from app.scripts.CI.normalize_tables import (
            check_heavy_cells, html_fragment_to_markdown)
        flat = html_fragment_to_markdown(self._CELL).replace("\n", " ")
        card = f"| **Описание работы:** | {flat} |\n"
        rep, ok = check_heavy_cells(card, self._SRC)
        assert not ok and any("расплющена" in r for r in rep)

    def test_label_section_clean(self):
        # тест на НЕсрабатывание: содержимое вынесено секцией
        from app.scripts.CI.normalize_tables import (
            check_heavy_cells, html_fragment_to_markdown)
        card = ("| Поле | Значение |\n|---|---|\n| **Alias** | /x |\n\n"
                "**Описание работы:**\n\n"
                + html_fragment_to_markdown(self._CELL) + "\n")
        rep, ok = check_heavy_cells(card, self._SRC)
        assert ok, rep

    def test_short_rule_cell_in_table_legal(self):
        # тест на НЕсрабатывание: короткая правило-ячейка в таблице
        from app.scripts.CI.normalize_tables import check_heavy_cells
        src = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
               "<td>Источник вызова</td>"
               "<td><p>Если пусто, то = 0 (Создание), иначе = 1 "
               "(Редактирование).</p></td></tr></tbody></table>\n")
        card = ("| Источник вызова | Если пусто, то = 0 (Создание), "
                "иначе = 1 (Редактирование). |\n")
        rep, ok = check_heavy_cells(card, src)
        assert ok, rep


class TestK26TableBodiesExcluded:
    """z06-fix ISS-03 (FUN-CL-01): строки таблиц не входят в ранговый
    профиль тел шагов — md-таблица карточки против HTML-таблицы
    источника несопоставима по числу строк по построению."""

    def test_md_table_in_step_body_ok(self):
        from app.scripts.CI.normalize_tables import (
            check_step_body_structure)
        src = ("---\ntitle: X\n---\n\n"
               "**Шаг 1.** Маппинг полей:\n\n"
               "<table><tr><td>Поле</td><td>Атрибут</td></tr>"
               "<tr><td>Организация</td><td>Ссылка</td></tr></table>\n\n"
               "**Шаг 2.** Отправка слепка заявки в очередь.\n")
        card = ("# Ф\n\n**Шаг 1.** Маппинг полей:\n\n"
                "| Поле | Атрибут |\n|---|---|\n"
                "| Организация | Ссылка |\n\n"
                "**Шаг 2.** Отправка слепка заявки в очередь.\n")
        rep, ok = check_step_body_structure(card, src)
        assert ok, rep

    def test_flattened_lists_still_caught(self):
        # НЕсрабатывание послабления: уплощение СПИСКОВ тела ловится
        from app.scripts.CI.normalize_tables import (
            check_step_body_structure)
        src = ("---\ntitle: X\n---\n\n"
               "**Шаг 1.** Проверки:\n\n- правило один\n  - подусловие\n\n"
               "**Шаг 2.** Конец.\n")
        card = ("# Ф\n\n**Шаг 1.** Проверки:\n\n"
                "- правило один\n- подусловие\n\n"
                "**Шаг 2.** Конец.\n")
        rep, ok = check_step_body_structure(card, src)
        assert not ok
        assert any("структура тел шагов" in r for r in rep)


class TestK26StepBodyStructure:
    """К-26: ранговый профиль тела каждого шага сверяется с источником;
    HTML-тела без md-разметки — честный skip."""

    _SRC = ("---\ntitle: X\n---\n\n"
            "#### Шаг №10. Печать\n\n"
            "    * Выполняется печать по правилам:\n"
            "        + правило раз\n"
            "        + правило два\n\n"
            "#### Шаг №11. Завершение\n\n"
            "    * Процесс завершён\n")

    def test_flattened_body_flagged(self):
        from app.scripts.CI.normalize_tables import check_step_body_structure
        card = ("- **Шаг №10.** Печать\n"
                "- Выполняется печать по правилам:\n"
                "- правило раз\n"
                "- правило два\n"
                "- **Шаг №11.** Завершение\n"
                "- Процесс завершён\n")
        rep, ok = check_step_body_structure(card, self._SRC)
        assert not ok and any("№10" in r for r in rep)

    def test_ranked_levels_clean(self):
        # тест на НЕсрабатывание: ранги совпадают при другом шаге отступа
        from app.scripts.CI.normalize_tables import check_step_body_structure
        card = ("- **Шаг №10.** Печать\n"
                "  - Выполняется печать по правилам:\n"
                "    - правило раз\n"
                "    - правило два\n"
                "- **Шаг №11.** Завершение\n"
                "  - Процесс завершён\n")
        rep, ok = check_step_body_structure(card, self._SRC)
        assert ok, rep

    def test_html_source_skipped(self):
        # тест на НЕсрабатывание: HTML-тела без md-маркеров — skip
        from app.scripts.CI.normalize_tables import check_step_body_structure
        src = ("---\ntitle: X\n---\n\n<td><strong>Шаг №1.</strong> "
               "текст</td><td><strong>Шаг №2.</strong> текст</td>\n")
        rep, ok = check_step_body_structure("текст", src)
        assert ok, rep


class TestK28UiArtifacts:
    """К-28: элементы UI Confluence из выгрузки в чистовике = брак."""

    def test_expand_source_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-BNK-07\ntitle: 'Ф'\ntype: function\n---\n\n"
            "Пример запроса Развернуть исходный код ``` {} ```\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("артефакт интерфейса" in r for r in rep)

    def test_clean_card_ok(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-BNK-07\ntitle: 'Ф'\ntype: function\n---\n\n"
            "Пример запроса:\n\n```\n{}\n```\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep


class TestK27StubGuard:
    """К-27: карточка-заглушка чужого типа = брак; слово «заглушка» в
    прозе и заглушки ЭФ — легальны."""

    def test_stub_card_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "rbac.md"
        p.write_text(
            "---\nid: RBAC-001\ntitle: 'Р'\ntype: rbac\n---\n\n"
            "# Ролевая модель\n\nЗаглушка комплекта: полное описание "
            "требует целевого захода create-rbac.\n", encoding="utf-8")
        rep, ok = check_file(p)
        assert not ok and any("заглушка вне правил" in r for r in rep)

    def test_word_in_prose_clean(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "f.md"
        p.write_text(
            "---\nid: FUN-CL-01\ntitle: 'Ф'\ntype: function\n---\n\n"
            "при отсутствии данных отображается заглушка экрана\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep

    def test_screen_form_stub_legal(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "scr.md"
        p.write_text(
            "---\nid: SCR-CL-09\ntitle: 'Э'\ntype: screen-form\n---\n\n"
            "## Назначение\n\nДокумент-заглушка: страница вне партии.\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep

    def test_contract_call_stub_legal(self, tmp_path):
        # модель CALL (2026-08-20): заглушка карточки вызова чужого
        # контракта — легальна, как прежний тип external-integration
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "call.md"
        p.write_text(
            "---\nid: CALL-003\ntitle: 'В'\ntype: contract-call\n---\n\n"
            "## Назначение\n\nЗаглушка: страница метода вне выгрузки.\n",
            encoding="utf-8")
        rep, ok = check_file(p)
        assert ok, rep


class TestK25CellConverterAndStructure:
    """К-25: детерминированная конвертация ячейки (чередование абзацев и
    уровней) + сверка секции со структурным профилем эталона."""

    _CELL = ("<p>Инициируется процесс.</p>"
             "<p>Создается Задача с атрибутами:</p>"
             "<ul><li><ul><li>Идентификатор задачи</li>"
             "<li>Статус = \"NEW\"</li></ul></li></ul>"
             "<p>Документы отбираются:</p>"
             "<ul><li>по условиям фильтрации</li></ul>")
    _SRC = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
            "<th>Что делает функция</th><td>" + _CELL + "</td>"
            "</tr></tbody></table>\n")

    def test_margin_left_paragraph_level(self):
        # вложенность абзацев инлайн-стилем Confluence (margin-left)
        # переносится blockquote-уровнем; профиль различает уровни
        from app.scripts.CI.normalize_tables import (
            html_fragment_to_markdown, _md_profile)
        cell = ('<p><strong>ТОГДА</strong></p>'
                '<p style="margin-left: 40.0px"><strong>Выполнение '
                'функции возможно</strong> новый статус "DELETED"</p>'
                '<p><strong>ИНАЧЕ</strong></p>')
        md = html_fragment_to_markdown(cell)
        lines = [ln for ln in md.splitlines() if ln.strip()]
        assert lines[1].startswith("> **Выполнение функции возможно**")
        assert _md_profile(lines) == ["p", "q1", "p"]

    def test_converter_keeps_alternation(self):
        from app.scripts.CI.normalize_tables import html_fragment_to_markdown
        md = html_fragment_to_markdown(self._CELL)
        lines = [ln for ln in md.splitlines() if ln.strip()]
        assert lines[0] == "Инициируется процесс."
        assert lines[1] == "Создается Задача с атрибутами:"
        assert lines[2].startswith("  - Идентификатор")
        assert lines[4] == "Документы отбираются:"  # абзац ВЕРНУЛСЯ наверх
        assert lines[5] == "- по условиям фильтрации"

    def test_inline_strong_inside_word_glued(self):
        # имена файлов с жирным куском внутри слова остаются слитными
        from app.scripts.CI.normalize_tables import html_fragment_to_markdown
        md = html_fragment_to_markdown(
            "<ul><li>767_610412_<strong>13_9</strong>_1.xml</li></ul>")
        assert "767_610412_**13_9**_1.xml" in md

    def test_section_matching_profile_clean(self, tmp_path):
        from app.scripts.CI.normalize_tables import (
            check_passport_cell_structure, html_fragment_to_markdown)
        card = ("**Что делает функция**\n\n"
                + html_fragment_to_markdown(self._CELL) + "\n")
        rep, ok = check_passport_cell_structure(card, self._SRC)
        assert ok, rep

    def test_section_broken_profile_flagged(self):
        # всё уехало под список — принадлежность уровней сломана
        from app.scripts.CI.normalize_tables import (
            check_passport_cell_structure)
        card = ("**Что делает функция**\n\n"
                "Инициируется процесс.\n\n"
                "- Создается Задача с атрибутами:\n"
                "  - Идентификатор задачи\n"
                "  - Статус = \"NEW\"\n"
                "  - Документы отбираются:\n"
                "  - по условиям фильтрации\n")
        rep, ok = check_passport_cell_structure(card, self._SRC)
        assert not ok and any("расходится" in r for r in rep)

    def test_link_replacement_does_not_flag(self, tmp_path):
        # тест на НЕсрабатывание: замена текста ссылки (правило трёх
        # случаев) не меняет структурный профиль
        from app.scripts.CI.normalize_tables import (
            check_passport_cell_structure)
        card = ("**Что делает функция**\n\n"
                "Инициируется процесс.\n\n"
                "Создается Задача с атрибутами "
                "[ENT-009 Задача](../ent-009.md):\n\n"
                "  - Идентификатор задачи\n"
                "  - Статус = \"NEW\"\n\n"
                "Документы отбираются:\n\n"
                "- по условиям фильтрации\n")
        rep, ok = check_passport_cell_structure(card, self._SRC)
        assert ok, rep


class TestK24bPassportCellFormat:
    """К-24b: структурная ячейка «Что делает функция» (вложенные списки
    в источнике) не заталкивается в строку md-таблицы — лейбл-секцией."""

    _SRC = ("---\ntitle: X\n---\n\n<table><tbody><tr>"
            "<th>Что делает функция</th>"
            "<td><p>Инициируется синхронный процесс формирования "
            "реестра документов по фильтрам запроса клиента.</p>"
            "<ul><li>Создаётся задача выгрузки с атрибутами запуска"
            "<ul><li>Идентификатор задачи и пользователя сервиса"
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
            "| **Что делает функция** | Инициируется синхронный процесс "
            "формирования реестра документов по фильтрам запроса клиента. "
            "Создаётся задача выгрузки с атрибутами запуска Идентификатор "
            "задачи и пользователя сервиса |\n")
        assert any("расплющена" in r for r in rep)

    def test_td_strong_colon_variant_detected(self, tmp_path):
        # К-25c: лейбл в <td><strong>…:</strong> (макет системных
        # функций) детектится так же, как <th> — теперь инвариантом К-29
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text(
            "---\ntitle: X\n---\n\n<table><tbody><tr>"
            "<td><strong>Что делает функция:</strong></td>"
            "<td><p>Инициируется синхронный процесс формирования "
            "реестра документов по фильтрам запроса клиента банка.</p>"
            "<ul><li>Создаётся задача выгрузки с атрибутами запуска "
            "и идентификатором пользователя сервиса</li></ul></td>"
            "</tr></tbody></table>\n", encoding="utf-8")
        card = tmp_path / "card.md"
        card.write_text(
            "---\nid: FUN-SYS-01\ntitle: 'X'\ntype: function\n---\n\n"
            "| **Что делает функция:** | Инициируется синхронный процесс "
            "формирования реестра документов по фильтрам запроса клиента "
            "банка. Создаётся задача выгрузки с атрибутами запуска и "
            "идентификатором пользователя сервиса |\n", encoding="utf-8")
        rep, ok = run_check([card], src)
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
            docs, "[макет](https://zeplin.io/project/XYZ)\n")
        assert ok
        assert any(r.startswith("предупреждение") for r in rep)

    def test_figma_whitelisted(self, tmp_path):
        # решение 2026-08-29: URL макетов Figma легальны и обязательны
        docs = self._docs(tmp_path)
        rep, ok = self._check(
            docs, "[макет](https://www.figma.com/design/XYZ/page)\n")
        assert ok
        assert not any(r.startswith("предупреждение") for r in rep)

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


class TestFencedBlocksOutOfTornCellGuard:
    """Fenced-блоки — вне зоны сторожа «разорванная ячейка»: PlantUML
    activity несёт свимлейны «|Система|» и шаги «:6 …;» — сторож видел
    таблицу с зажатым голым текстом (4 ложняка process-файлов эталона,
    разбор ✗ 2026-08-21)."""

    def _check(self, text, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = tmp_path / "card.md"
        p.write_text(text, encoding="utf-8")
        return check_file(p)

    def test_plantuml_swimlanes_not_flagged(self, tmp_path):
        md = (
            "# Процесс\n\n"
            "```plantuml\n"
            "@startuml\n"
            "|Система|\n"
            "  :5 Информировать пользователей банка;\n"
            "|Пользователь Банка|\n"
            "  :6 Обработать ошибку;\n"
            "|Система|\n"
            "@enduml\n"
            "```\n"
        )
        report, ok = self._check(md, tmp_path)
        assert ok, report
        assert not any("разорванная ячейка" in l for l in report)

    def test_real_torn_cell_still_caught(self, tmp_path):
        # тест на НЕсрабатывание фильтра: разрыв ВНЕ fenced-блока ловится
        md = (
            "# Карточка\n\n"
            "| Параметр | Описание |\n"
            "|---|---|\n"
            "| A | начало описания |\n"
            "хвост разорванной ячейки\n"
            "| B | следующая строка |\n"
        )
        report, ok = self._check(md, tmp_path)
        assert any("разорванная ячейка" in l for l in report)


class TestEscapedBracketsInLinks:
    """Блокер z01-fix ISS-03: экранированные \[ \] в тексте ссылки —
    текст, не скобки баланса; кривая конструкция выгрузки
    «[КК_ВК\] Банк: …](url)» должна терять URL при нормализации."""

    def test_escaped_bracket_link_stripped(self):
        from app.scripts.CI.normalize_tables import _norm_cell
        v = ("[КК_ВК\] Банк: Функция изменения статуса]"
             "(../../[КК_ВК]-Функции/файл.md)")
        n = _norm_cell(v)
        assert "функции/файл" not in n and "../" not in n
        assert "[кк_вк] банк: функция изменения статуса" in n

    def test_wellformed_escaped_label_still_stripped(self):
        # НЕсрабатывание: корректная ссылка с \[тегом\] в ярлыке
        from app.scripts.CI.normalize_tables import _norm_cell
        v = ("[\[КК_ВК\] Банк: Функция]"
             "(../../[КК_ВК]-Функции/файл.md)")
        n = _norm_cell(v)
        assert "../" not in n
        assert "[кк_вк] банк: функция" in n


class TestStructRowsAndHomoglyphPardon:
    """Калибровки z01/z03 ISS-03: структурные ряды ЭФ-таблиц в колонке
    обязательности (source_mode) и помилование гомоглифов, дословно
    пришедших из кавычечных литералов источника."""

    def test_struct_label_valid_in_source_mode(self):
        headers = ["Название поля", "Обязательность"]
        rows = [["Поле А", "Да"],
                ["**Раздел \"Основная информация\"**",
                 "**Раздел \"Основная информация\"**"],
                ["Вкладка \"Параметры заявки\"",
                 "Вкладка \"Параметры заявки\""]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None,
                                   source_mode=True)}
        assert report["обязат"]["valid_pct"] == 100.0

    def test_struct_label_still_defect_in_card_check(self):
        # НЕсрабатывание: в --check карточек послабления нет
        headers = ["Название поля", "Обязательность"]
        rows = [["Поле", "Раздел \"Х\""]]
        report = {c["role"]: c for c in
                  validate_columns(headers, rows, path_index=None)}
        assert report["обязат"]["valid_pct"] < 100

    def test_homoglyph_from_source_literal_pardoned(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        src = 'Кнопка "ОK" закрывает сообщение.'  # кириллическая О
        card = tmp_path / "c.md"
        card.write_text('# К\n\nКнопка "ОK" — закрыть.\n',
                        encoding="utf-8")
        rep, ok = check_file(card, source_text=src)
        assert ok, "\n".join(rep)
        assert any("помилованы" in ln for ln in rep)

    def test_homoglyph_not_in_source_still_defect(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text('# К\n\nСтатус "Aктивен" установлен.\n',
                        encoding="utf-8")  # латинская A
        rep, ok = check_file(card, source_text='Литералы: "другое".')
        assert not ok
        assert any("К-30" in ln for ln in rep)

    def test_run_check_pardon_source_channel(self, tmp_path):
        # z03 ISS-03 (scr-cl-01.4): источник группы доезжает до
        # НЕглавной карточки каналом помилований — гомоглиф «ОK»
        # милуется, а сверочные блоки (литералы, title) НЕ включаются
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text('# Другой title\n\nКнопка "ОK" закрывает. '
                       'Литерал "Иной".\n', encoding="utf-8")
        part = tmp_path / "part.md"
        part.write_text('# Часть\n\nКнопка "ОK" — закрыть.\n',
                        encoding="utf-8")
        rep, ok = run_check([part], None, pardon_source=src)
        assert ok, "\n".join(rep)
        assert any("помилованы" in ln for ln in rep)
        # «Иной» в части отсутствует — при полной сверке был бы брак
        assert not any("отсутств" in ln for ln in rep)

    def test_flattened_attr_logic_defect(self, tmp_path):
        # z04 ISS-03 (FLD-29): ≥2 «если» в однострочном значении
        # атрибута — вложенное ветвление источника выпрямлено
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### FLD-1. «Поле»\n\n"
            "- **Логика установки значения:**<br>Если держатель из "
            "справочника, то: если атрибут не пустой, то поле "
            "заполняется, иначе не заполняется. Если реестр загружен, "
            "то поле не заполняется.\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("сплющенный атрибут" in ln
                   and "Логика установки значения" in ln for ln in rep)

    def test_flattened_attr_not_fired_on_list_or_single(self, tmp_path):
        # НЕсрабатывание: одно «если» одной строкой; значение,
        # разложенное подсписком; «если» в кавычках и скобках
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### FLD-1. «Поле»\n\n"
            "- **Видимость:** **Если** переключатель == \"А\", **то** "
            "показывается, **иначе** скрывается.\n"
            "- **Логика установки значения:**\n"
            "  - **Если** держатель из справочника, **то**:\n"
            "    - **если** атрибут не пустой, **то** заполняется,\n"
            "    - **иначе** не заполняется.\n"
            "  - **Если** реестр загружен, **то** не заполняется.\n"
            "- **По умолчанию:** пусто (если очищено, если сброшено — "
            "текст в скобках) с подсказкой \"если адрес не найден, "
            "если пусто\"\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("сплющенный атрибут" in ln for ln in rep)

    def test_separator_column_mismatch_defect(self, tmp_path):
        # находка владельца 2026-08-29 (реестр контролей после d10):
        # сепаратор с числом колонок ≠ заголовку — GFM таблицу не рендерит
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text("# К\n\n| A | B |\n|---|---|---|\n| 1 | 2 |\n",
                        encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("сепаратор таблицы" in ln for ln in rep)

    def test_separator_match_clean(self, tmp_path):
        # НЕсрабатывание: колонки совпадают
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text("# К\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
                        encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("сепаратор таблицы" in ln for ln in rep)

    def test_glued_steps_in_button_action_defect(self, tmp_path):
        # замечание владельца (дозаход z01-z04): «При нажатии» со
        # склеенными шагами одной строкой
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### B-1. «Удалить все анкеты»\n\n"
            "- **При нажатии:** **Шаг 1.** Модальное окно MSG-1. "
            "**Шаг 2.** Удаление всех блоков. **Шаг 3.** Snackbar.\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("склеены одной строкой" in ln for ln in rep)

    def test_steps_on_own_lines_not_fired(self, tmp_path):
        # НЕсрабатывание: шаги разложены по строкам списка
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### B-1. «Кнопка»\n\n"
            "- **При нажатии:**\n"
            "  - **Шаг 1.** Модальное окно MSG-1.\n"
            "  - **Шаг 2.** Удаление всех блоков.\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("сплющенный" in ln for ln in rep)

    def test_long_flat_value_defect(self, tmp_path):
        # замечание владельца: «Формат» FLD-13 — простыня одной строкой
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### FLD-13. «Офис получения»\n\n"
            "- **Формат:** " + "Очень длинное описание формата. " * 12
            + "\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("видимой длиной" in ln for ln in rep)

    def test_links_dont_inflate_length(self, tmp_path):
        # НЕсрабатывание: длина считается по видимому тексту — URL
        # markdown-ссылок строку не раздувают
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        link = "[EXT-004](../../../../data-model/dictionaries.md#реестр)"
        card.write_text(
            "# К\n\n### FLD-1. «Поле»\n\n"
            f"- **Формат:** {link}.<Населенный пункт> + {link}.<Адрес> "
            f"+ {link}.<Номер>\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("видимой длиной" in ln for ln in rep)

    def test_flattened_list_item_defect(self, tmp_path):
        # замечание владельца: разложен только первый блок — элемент
        # списка с ветвлением (в т.ч. в ДЛИННОЙ скобке) остался строкой
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### FLD-29. «Поле»\n\n"
            "- **Логика установки значения:**\n"
            "  - **Если** поле ЕСК заполнено, **то** заполняются "
            "атрибуты: A, B, C (список из справочника; **Если** номер "
            "дома заполнен, **то** FALSE, **иначе** TRUE — вложенное "
            "условие внутри длинной скобки).\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("сплющенная строка" in ln for ln in rep)

    def test_lazy_continuation_paragraph_defect(self, tmp_path):
        # закон обходов (z05, B-1 scr-bnk-02): пустой ярлык + абзац-
        # продолжение с ≥2 «если» — та же простыня вне маркера списка
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### B-1. Кнопка \"Применить\"\n\n"
            "- **При нажатии:**\n"
            "  После нажатия ЭФ закрывается. **Если** статус выпущен, "
            "**то** открывается форма, **иначе** изменение статуса. "
            "**Если** заполнены поля, **то** они сохраняются.\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("сплющенная строка" in ln for ln in rep)

    def test_norm_cell_ignores_list_markers(self):
        # разложение ячейки списком не рвёт нормализованную сверку —
        # маркеры «- » вычищаются (снят конфликт сторож↔дословность)
        from app.scripts.CI.normalize_tables import _norm_cell
        src_cell = "После нажатия ЭФ закрывается. **Если** статус, **то** форма"
        card = ("- **При нажатии:**\n"
                "  - После нажатия ЭФ закрывается.\n"
                "  - **Если** статус, **то** форма\n")
        assert _norm_cell(src_cell) in _norm_cell(card)

    def test_short_paren_insert_in_item_not_fired(self, tmp_path):
        # НЕсрабатывание: короткая скобочная оговорка «(если было
        # заполнено)» — не второе условие
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### EV-3. «Переключение»\n\n"
            "- **Если** выбран режим, **то** поле очищается (если было "
            "заполнено) и скрывается.\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("сплющенный элемент" in ln for ln in rep)

    def test_long_body_line_defect(self, tmp_path):
        # решение 2026-08-29 (README SCR-CL-01 «Части»): перечень одной
        # строкой вне таблицы длиннее 500 видимых символов
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text("# К\n\nОбщие для экрана: "
                        + "; ".join(f"элемент номер {i}" for i in range(40))
                        + ".\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("видимой длиной" in ln and "вне таблицы" in ln
                   for ln in rep)

    def test_long_table_row_and_quote_not_flagged(self, tmp_path):
        # НЕсрабатывание: строка таблицы и длинная дословная цитата
        from app.scripts.CI.normalize_tables import check_file
        long_quote = '"' + "текст сообщения пользователю " * 25 + '"'
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n| ID | Содержание |\n|---|---|\n| MSG-1 | "
            + "содержимое ячейки " * 40 + " |\n\n"
            f"Текст информера: {long_quote} дословно.\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("вне таблицы" in ln for ln in rep)

    def test_content_readme_of_ef_group_warns(self, tmp_path):
        # решение 2026-08-30: README группы ЭФ с предметными секциями —
        # старая структура, содержимое уровня страницы уходит в frame
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "README.md"
        card.write_text(
            "---\ntype: screen-form\n---\n\n# Ф\n\n### FLD-1. «Выход»\n\n"
            "- **Видимость:** всегда\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert any("чистое оглавление" in ln and "main" in ln for ln in rep)

    def test_nav_readme_and_frame_card_not_warned(self, tmp_path):
        # НЕсрабатывание: README без frontmatter (навигация) и frame-
        # карточка с секциями — целевая структура
        from app.scripts.CI.normalize_tables import check_file
        nav = tmp_path / "README.md"
        nav.write_text("# Форма\n\nЧасти: [SCR-X-01.0](x.md)\n",
                       encoding="utf-8")
        frame = tmp_path / "scr-x-01.0-frame.md"
        frame.write_text(
            "---\ntype: screen-form\n---\n\n# Ф\n\n### FLD-1. «Выход»\n\n"
            "- **Видимость:** всегда\n", encoding="utf-8")
        for f in (nav, frame):
            rep, ok = check_file(f)
            assert not any("чистое оглавление" in ln for ln in rep), f.name

    def test_pseudo_screen_form_warns(self, tmp_path):
        # z06 (SCR-CL-05): все поля «не отображается» — операционная
        # функция в шаблоне формы, кандидат на смену типа
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "---\ntype: screen-form\n---\n\n# Ф\n\n### FLD-1. «Алгоритм»\n\n"
            "- **Тип:** Текст\n"
            "- **Видимость:** не отображается (серверная процедура)\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert any("кандидат на смену типа" in ln for ln in rep)

    def test_real_screen_form_not_warned(self, tmp_path):
        # НЕсрабатывание: есть отображаемые поля
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "---\ntype: screen-form\n---\n\n# Ф\n\n### FLD-1. «Поле»\n\n"
            "- **Видимость:** всегда\n\n### FLD-2. «Скрытое»\n\n"
            "- **Видимость:** не отображается\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("кандидат на смену типа" in ln for ln in rep)

    def test_screen_form_without_figma_warns(self, tmp_path):
        # решение 2026-08-29: URL макетов Figma обязаны переноситься
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "---\ntype: screen-form\n---\n\n# Ф\n\n### Макеты ЭФ\n\n"
            "Размер XL - ссылка\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert any("Figma" in ln and ln.startswith("предупреждение")
                   for ln in rep)

    def test_screen_form_with_figma_silent(self, tmp_path):
        # НЕсрабатывание: ссылка на макет есть
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "---\ntype: screen-form\n---\n\n# Ф\n\n### Макеты ЭФ\n\n"
            "[Размер XL](https://www.figma.com/file/abc)\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("Figma" in ln and "предупреждение" in ln
                       for ln in rep)

    def test_bare_html_tagish_placeholder_defect(self, tmp_path):
        # z04 ISS-03 (B-5): <S>/<XS> — HTML-теги в рендере
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n- **Видимость:** **Если** Метод определения "
            "размерности экрана.<S> = true или <XS> = true.\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("HTML-теговидные" in ln and "<S>" in ln
                   for ln in rep)

    def test_tagish_pardons_br_backticks_cyrillic(self, tmp_path):
        # НЕсрабатывание: <br> легален, `<S>` в бэктиках, кириллический
        # <Атрибут> тегом не парсится
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n- **Логика:**<br>значение `<S>` = true, атрибут "
            "<Адрес одной строкой> для <Тип адреса> == LEGAL\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("HTML-теговидные" in ln for ln in rep)

    def test_condition_notation_warning(self, tmp_path):
        # голое «если» в секции FLD — предупреждение, вердикт не валит
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n### FLD-1. «Поле»\n\n"
            "- **Видимость:** Если экран узкий, скрывается.\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert any(ln.startswith("предупреждение: нотация условий")
                   for ln in rep)

    def test_condition_notation_not_fired(self, tmp_path):
        # НЕсрабатывание: жирная нотация; «если» в кавычках/скобках/
        # обязательности; «если» вне зон FLD/EV/B/MSG
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\nТекст: если применимо — вне зоны.\n\n"
            "### FLD-1. «Поле»\n\n"
            "- **Видимость:** **Если** А, **то** Б, **иначе** В.\n"
            "- **Обязательность:** Да, если не заполнено поле \"Х\"\n"
            "- **Логика:** очищается (если было заполнено), подсказка "
            "\"если адрес не найден\"\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("нотация условий" in ln for ln in rep)

    def test_quote_parity_survives_html_attributes(self):
        # z04 ISS-03: кавычки href=«…» сбивали рамки _QUOTED_RE — маска
        # "+7 (ХXX) XXX-XX-XX" после атрибутного тега не распознавалась
        # литералом вовсе (терялись и сверка, и К-30-помилование)
        from app.scripts.CI.normalize_tables import quoted_literals
        src = ('<p>Алфавит: <a href="../Стандартные-наборы.md">Цифры</a>'
               '</p><p>Отображение по маске: "+7 (ХXX) XXX-XX-XX", '
               'где X - цифра</p>')
        lits = quoted_literals(src)
        assert "+7 (ХXX) XXX-XX-XX" in lits
        # НЕсрабатывание: значение href литералом не становится
        assert not any("Стандартные" in l for l in lits)

    def test_quote_parity_keeps_example_boundaries(self):
        # НЕсрабатывание К-18: </p> (тег без кавычек) сохраняется как
        # граница — литерал ПОСЛЕ закрытого примера по-прежнему требуется
        from app.scripts.CI.normalize_tables import quoted_literals
        src = ('<p>Пример: значение примера</p>'
               '<p>Кнопка "Продолжить" доступна.</p>')
        assert "Продолжить" in quoted_literals(src)

    def test_mixed_img_cell_skipped_with_warning(self, tmp_path):
        # z04 ISS-03 («Выход с ЭФ» view): ячейка с <img> внутри текста —
        # дословная сверка пропущена, сигнал приёмке вместо ✗
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("| № | Поле | Логика |\n|---|---|---|\n"
               '| 1 | Выход | **Если** экран узкий, **то** иконка '
               '<img src="img/a.png" width="20" alt="x.png"> **Иначе** '
               "текст |\n"
               "| 2 | Заголовок | Наименование экранной формы заявки |\n")
        card = ("# К\n\n1. Перенос с перефразированной подписью иконки. "
                "Выход. 2. Заголовок. Наименование экранной формы "
                "заявки.\n")
        rep, ok = check_source_tables(card, src)
        assert ok, "\n".join(rep)
        assert any("смешанным текстом и изображениями" in ln
                   for ln in rep)

    def test_textonly_cell_still_guarded(self, tmp_path):
        # НЕсрабатывание послабления: ячейка БЕЗ img сверяется как раньше
        from app.scripts.CI.normalize_tables import check_source_tables
        src = ("| № | Поле | Логика |\n|---|---|---|\n"
               "| 1 | Выход | Дословный текст ячейки без картинок |\n"
               "| 2 | Заголовок | Наименование экранной формы заявки |\n")
        rep, ok = check_source_tables("# К\n\nдругое\n", src)
        assert not ok
        assert any("отсутствуют" in ln for ln in rep)

    def test_literal_relocated_to_sibling_is_signal_not_defect(self):
        # z04 ISS-03: точка применения «Подписать и отправить» живёт в
        # README реестра, не в cards-файле группы — i-сигнал, не ✗
        from app.scripts.CI.normalize_tables import check_quoted_literals
        src = 'При нажатии кнопки "Подписать и отправить" на ЭФ.'
        rep, ok = check_quoted_literals(
            "# Карточка\n\nбез кнопки\n", src,
            sibling_text='README: группа «При нажатии "Подписать и '
                         'отправить"»')
        assert ok, "\n".join(rep)
        assert any(ln.startswith("i кавычечные литералы") for ln in rep)

    def test_literal_missing_everywhere_still_defect(self):
        # НЕсрабатывание фолбэка: литерала нет и у соседей — ✗ как раньше
        from app.scripts.CI.normalize_tables import check_quoted_literals
        rep, ok = check_quoted_literals(
            "# К\n\nтекст\n", 'Кнопка "Продолжить" доступна.',
            sibling_text="соседи без кнопки")
        assert not ok
        assert any("отсутствуют" in ln for ln in rep)

    def test_run_check_pardon_does_not_mute_alien_homoglyph(self, tmp_path):
        # НЕсрабатывание: гомоглиф НЕ из литералов источника группы —
        # брак части остаётся
        from app.scripts.CI.normalize_tables import run_check
        src = tmp_path / "src.md"
        src.write_text('# С\n\nКнопка "ОК" закрывает.\n',
                       encoding="utf-8")  # чистая кириллица
        part = tmp_path / "part.md"
        part.write_text('# Часть\n\nСтатус "Aктивен".\n',
                        encoding="utf-8")  # латинская A
        rep, ok = run_check([part], None, pardon_source=src)
        assert not ok
        assert any("К-30" in ln for ln in rep)


class TestLayoutCellExcludedFromHeavyPairs:
    """2026-08-31 (модель README/main): ячейка макетов не входит в
    сверку тяжёлых пар — её ссылки живут в несверяемом README."""

    def test_layout_cell_skipped(self):
        from app.scripts.CI.normalize_tables import heavy_source_cells
        src = ('<table><tr><td>Макеты ЭФ</td><td>'
               '<p>Моментальная карта - <a href="https://www.figma.com/'
               'design/a">макеты</a></p><p>Размер XL - <a href='
               '"https://www.figma.com/design/b">ссылка</a></p>'
               '<p>Размер L, M - ссылка</p><p>Размер S, XS - ссылка</p>'
               '</td></tr></table>')
        assert heavy_source_cells(src) == []

    def test_ordinary_heavy_cell_still_collected(self):
        # НЕсрабатывание послабления: обычная тяжёлая пара собирается
        from app.scripts.CI.normalize_tables import heavy_source_cells
        src = ('<table><tr><td>Что делает функция</td><td>'
               '<p>Первый абзац текста подлиннее про поведение.</p>'
               '<ul><li>шаг один</li><li>шаг два</li></ul>'
               '<p>Третий абзац с завершением описания.</p>'
               '</td></tr></table>')
        assert len(heavy_source_cells(src)) == 1


class TestBlockquoteAndIndentedCode:
    """Рецидив CALL-INT-001 (2026-08-31): цитаты «>» и отступные
    код-блоки конвертера в чистовике — «заметки» и код в рендере."""

    def test_blockquote_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n**Шаг 1.**\n\n> **Если** статус равен:\n\n"
            "> > **то,** отправляется в очередь.\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("blockquote" in ln for ln in rep)

    def test_indented_code_with_text_flagged(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\nАбзац перед блоком.\n\n"
            "      - ИЛИ \"Черновик\";\n"
            "      - ИЛИ \"Новый\";\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert not ok
        assert any("отступный код-блок" in ln for ln in rep)

    def test_nested_list_after_parent_li_not_flagged(self, tmp_path):
        # НЕсрабатывание: вложенный список после родительского li —
        # легальная вложенность, не код-блок
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\n- **Если** статус равен:\n\n"
            "    - «Черновик»;\n"
            "    - «Новый».\n", encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("отступный код-блок" in ln or "blockquote" in ln
                       for ln in rep)

    def test_mermaid_fenced_block_not_flagged(self, tmp_path):
        # НЕсрабатывание: отступные строки ВНУТРИ fenced-блока (mermaid
        # статусной модели: «[*] --> NONE : создание через ЭФ») — код
        from app.scripts.CI.normalize_tables import check_file
        card = tmp_path / "c.md"
        card.write_text(
            "# К\n\nДиаграмма.\n\n```mermaid\nstateDiagram-v2\n"
            "    [*] --> NONE : создание через ЭФ\n"
            "    NONE --> DRAFT : сохранить черновик\n```\n",
            encoding="utf-8")
        rep, ok = check_file(card)
        assert ok, "\n".join(rep)
        assert not any("отступный код-блок" in ln for ln in rep)


class TestControlsEntitySlicing:
    """Нарезка карточных файлов контролей по сущности (2026-08-31):
    frontmatter entity + сверка «Проверяемого атрибута» карточек."""

    def _card(self, tmp_path, name, fm_extra, body):
        p = tmp_path / name
        p.write_text("---\npartOf: CTL-000\ntype: control\n"
                     + fm_extra + "---\n\n# Контроли\n\n" + body,
                     encoding="utf-8")
        return p

    def test_no_entity_warned_once(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = self._card(tmp_path, "cards-request-main-1.md", "",
                       "### CTL-001. Проверка\n\n"
                       "- **Проверяемый атрибут:** [ENT-016](x.md).«А».\n")
        rep, ok = check_file(p)
        assert ok, "\n".join(rep)
        assert sum(1 for ln in rep if "без entity" in ln) == 1

    def test_alien_card_warned(self, tmp_path):
        from app.scripts.CI.normalize_tables import check_file
        p = self._card(
            tmp_path, "cards-ent-016-request.md", "entity: ENT-016\n",
            "### CTL-001. Своя\n\n"
            "- **Проверяемый атрибут:** [ENT-016](x.md).«А».\n\n"
            "### CTL-002. Чужая\n\n"
            "- **Проверяемый атрибут:** [ENT-012](y.md).«Б».\n")
        rep, ok = check_file(p)
        assert ok, "\n".join(rep)
        assert any("чужой сущности" in ln and "CTL-002" in ln
                   for ln in rep)

    def test_homogeneous_file_silent(self, tmp_path):
        # НЕсрабатывание: все карточки своей сущности
        from app.scripts.CI.normalize_tables import check_file
        p = self._card(
            tmp_path, "cards-ent-016-request.md", "entity: ENT-016\n",
            "### CTL-001. Своя\n\n"
            "- **Проверяемый атрибут:** [ENT-016](x.md).«А».\n")
        rep, ok = check_file(p)
        assert ok, "\n".join(rep)
        assert not any("чужой сущности" in ln or "без entity" in ln
                       for ln in rep)
