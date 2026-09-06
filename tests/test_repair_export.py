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
    flatten_nested, strip_markers, unfence_html,
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


# Frontmatter без страничного флага — для проверок, где важен только текст.
FM_NO_FLAG = "---" + "\n" + "status: active" + "\n" + "---" + "\n"


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


class TestFlattenNested:
    """
    Уплощение литеральной вложенности (инцидент 2026-09-05): экспортёр обернул
    блочным маркером список, внутри которого были врезки других задач. Нотация
    вложенность запрещает, apply/reject падали жёстко и обрывали весь прогон.
    """

    def test_simple_nesting_flattened(self):
        src = "{++GBO-1: раз {++TEAMTB-2: два++} три++}"
        out, count = flatten_nested(src)
        assert count == 1
        assert out == "{++GBO-1: раз ++}{++TEAMTB-2: два++}{++GBO-1:  три++}"

    def test_text_is_never_touched(self):
        """Главный инвариант: переставляется только разметка."""
        src = "{++GBO-1: список\n- пункт {++TEAMTB-2: врезка++}\n- ещё++}"
        out, _ = flatten_nested(src)
        assert strip_markers(out) == strip_markers(src)

    def test_whitespace_chunk_not_wrapped(self):
        """Переводы строк и маркеры списка — структура, маркером не накрываем."""
        src = "{++GBO-1: текст {++TEAMTB-2: врезка++}\n++}"
        out, _ = flatten_nested(src)
        assert out.endswith("\n") and not out.endswith("{++GBO-1: \n++}")

    def test_clean_markup_untouched(self):
        for src in ("{++GBO-1: без вложенности++}", "обычный текст", ""):
            out, count = flatten_nested(src)
            assert count == 0 and out == src

    def test_unbalanced_markup_left_alone(self):
        """Разметка не сходится — не гадаем, отдаём линтеру как есть."""
        for src in ("{++GBO-1: незакрытый", "лишний закрыватель ++}",
                    "{++GBO-1: раз {++TEAMTB-2: два++}"):
            out, count = flatten_nested(src)
            assert count == 0 and out == src

    def test_substitution_not_split(self):
        """У подстановки два тела — безопасного дробления нет."""
        src = "{~~GBO-1: было {++TEAMTB-2: врезка++}~>стало~~}"
        out, count = flatten_nested(src)
        assert count == 0 and out == src

    def test_fenced_code_untouched(self):
        src = "```\n{++GBO-1: раз {++TEAMTB-2: два++} три++}\n```"
        out, count = flatten_nested(src)
        assert count == 0 and out == src

    def test_through_repair_file(self, tmp_path):
        body = "\n{++GBO-1: список\n- {++TEAMTB-2: врезка++} хвост++}\n"
        path = _write(tmp_path, FM_NO_FLAG + body)
        rep = repair_file(path, unfold=False, unapproved=None, flatten=True)
        assert rep["changed"] and rep["flattened"] == 1
        assert strip_markers(rep["new_text"]) == strip_markers(FM_NO_FLAG + body)

    def test_cli_flatten_writes_file(self, tmp_path):
        path = _write(tmp_path, FM_NO_FLAG + "\n{++GBO-1: раз {++TEAMTB-2: два++}++}\n")
        assert main([str(tmp_path), "--flatten-nested"]) == 0
        assert "{++GBO-1: раз ++}{++TEAMTB-2: два++}" in _read(path)


class TestUnfenceHtml:
    """
    Ограждения кода внутри HTML-таблицы (инцидент 2026-09-06). Экспортёр заворачивал
    JSON-подобный абзац в ```…``` прямо внутри ячейки, отданной сырым HTML: как код
    это не рендерится нигде, а содержимое между ограждениями считается кодом и
    переносится байт-в-байт — apply/reject не видят маркеры внутри, и неутверждённые
    требования молча остаются в «чистом ПРОМ». Замена ограничителей на <pre> вскрывает
    их, не трогая ни байта содержимого.
    """

    ISLAND = (
        "<table><tbody>\n"
        "<tr><td>\n"
        "```\n"
        "{++GBO-1: требование, спрятанное блоком++}\n"
        "```\n"
        "</td></tr>\n"
        "</tbody></table>\n"
    )

    def test_fences_become_pre(self):
        out, count = unfence_html(self.ISLAND)
        assert count == 1
        assert "<pre>" in out and "</pre>" in out and "```" not in out

    def test_content_untouched(self):
        out, _ = unfence_html(self.ISLAND)
        assert "{++GBO-1: требование, спрятанное блоком++}" in out

    def test_marker_becomes_visible_to_reject(self):
        """Смысл починки: маркер внутри бывшего блока теперь снимается."""
        from app.scripts.CI.critic import process_text
        assert process_text(self.ISLAND, "reject", None)[1] == 0     # до починки не виден
        out, _ = unfence_html(self.ISLAND)
        cleaned, count = process_text(out, "reject", None)
        assert count == 1 and "спрятанное блоком" not in cleaned

    def test_fence_outside_island_untouched(self):
        """Настоящий блок кода в тексте страницы — не наше дело."""
        text = "# Заголовок\n\n```\nprint(1)\n```\n"
        assert unfence_html(text) == (text, 0)

    def test_odd_number_of_fences_left_alone(self):
        """Пары не сходятся — не гадаем, отдаём линтеру."""
        text = "<table><tbody>\n<tr><td>\n```\nтекст\n</td></tr>\n</tbody></table>\n"
        assert unfence_html(text) == (text, 0)

    def test_glued_fence_handled(self):
        """Ограждение, приклеенное к содержимому — реальная форма из выгрузки."""
        text = "<table><tbody>\n<tr><td>x++}```\nтело\n```\n</td></tr></tbody></table>\n"
        out, count = unfence_html(text)
        assert count == 1 and "x++}<pre>" in out

    def test_idempotent(self):
        once, _ = unfence_html(self.ISLAND)
        assert unfence_html(once) == (once, 0)

    def test_only_delimiters_change(self):
        """Инвариант: между ограничителями не меняется ни байта."""
        import re
        text = ("<table><tbody><tr><td>\n```\nтело с `обратными` кавычками\n```\n"
                "</td></tr></tbody></table>\n\n```\nнастоящий блок\n```\n")
        out, count = unfence_html(text)
        assert count == 1
        drop = lambda s: re.sub(r"`{3,}|</?pre>", "", s)
        assert drop(out) == drop(text)
        assert "```\nнастоящий блок\n```" in out          # вне острова не тронуто

    def test_through_repair_file(self, tmp_path):
        path = _write(tmp_path, FM_NO_FLAG + "\n" + self.ISLAND)
        rep = repair_file(path, unfold=False, unapproved=None, unfence=True)
        assert rep["changed"] and rep["unfenced"] == 1
        assert "```" not in rep["new_text"]

    def test_cli_reports_and_writes(self, tmp_path, capsys):
        path = _write(tmp_path, FM_NO_FLAG + "\n" + self.ISLAND)
        assert main([str(tmp_path), "--unfence-html"]) == 0
        assert "<pre>" in _read(path)
        assert "ограждений распаковано" in capsys.readouterr().out

    def test_cli_dry_run_writes_nothing(self, tmp_path):
        path = _write(tmp_path, FM_NO_FLAG + "\n" + self.ISLAND)
        before = _read(path)
        assert main([str(tmp_path), "--unfence-html", "--dry-run"]) == 0
        assert _read(path) == before


class TestFlagPage:
    """
    Замороженное поддерево (2026-09-06): у страниц нет таблицы «История изменений»,
    значит нет карты «цвет → задача» и нет ни одного маркера — весь текст считается
    чёрным и переживает reject. При этом требования не исключены, а заморожены: их
    нужно держать в git и уметь вернуть, когда задача выйдет на ПРОМ.
    Ключ --unapproved-jira тут бессилен (он берёт задачу из маркеров в теле),
    поэтому флаг проставляется по пути напрямую.
    """

    FROZEN = "---\ntitle: Заморожено\nstatus: draft\n---\n\n# Цели\n\nТекст требований.\n"
    WITH_MARKER = "---\ntitle: Живая\nstatus: draft\n---\n\n{++GBO-52119: правка++}\n"

    def test_flag_set_on_page_without_markers(self, tmp_path):
        path = _write(tmp_path, self.FROZEN)
        rep = repair_file(path, unfold=False, unapproved=None, flag_page="GBO-52119")
        assert rep["changed"] and rep["flagged"] == "GBO-52119"
        assert "unapproved_jira: GBO-52119" in rep["new_text"]
        assert rep["new_text"].endswith("# Цели\n\nТекст требований.\n")   # тело не тронуто

    def test_idempotent(self, tmp_path):
        path = _write(tmp_path, self.FROZEN)
        first = repair_file(path, unfold=False, unapproved=None, flag_page="GBO-52119")
        _write(tmp_path, first["new_text"])
        second = repair_file(path, unfold=False, unapproved=None, flag_page="GBO-52119")
        assert not second["changed"]

    def test_foreign_flag_not_overwritten(self, tmp_path):
        text = self.FROZEN.replace("status: draft\n", "status: draft\nunapproved_jira: GBO-1\n")
        path = _write(tmp_path, text)
        rep = repair_file(path, unfold=False, unapproved=None, flag_page="GBO-52119")
        assert not rep["changed"]
        assert "уже стоит флаг другой задачи" in rep["skipped"]

    def test_reject_empties_flagged_page(self, tmp_path):
        """Ради чего всё: страница уходит из ПРОМ-среза, но остаётся в архиве."""
        from app.scripts.CI.critic import process_file
        path = _write(tmp_path, self.FROZEN)
        rep = repair_file(path, unfold=False, unapproved=None, flag_page="GBO-52119")
        _write(tmp_path, rep["new_text"])
        assert process_file(path, "reject", None) == 1
        assert "Текст требований" not in _read(path)

    def test_apply_returns_the_page(self, tmp_path):
        from app.scripts.CI.critic import process_file
        path = _write(tmp_path, self.FROZEN)
        rep = repair_file(path, unfold=False, unapproved=None, flag_page="GBO-52119")
        _write(tmp_path, rep["new_text"])
        assert process_file(path, "apply", "GBO-52119") == 1
        text = _read(path)
        assert "Текст требований" in text and "unapproved_jira" not in text


class TestFlagPageGuard:
    """Сторож: флаг задачи, которой нет в дереве, невидим для `critic list`."""

    def test_unknown_task_refused(self, tmp_path, capsys):
        _write(tmp_path, TestFlagPage.FROZEN)
        assert main([str(tmp_path), "--flag-page", "GBO-99999"]) == 2
        out = capsys.readouterr().out
        assert "не встречается" in out
        assert "unapproved_jira" not in _read(tmp_path / "страница.md")   # ничего не записано

    def test_task_present_as_marker_accepted(self, tmp_path):
        _write(tmp_path, TestFlagPage.FROZEN, name="заморожено.md")
        _write(tmp_path, TestFlagPage.WITH_MARKER, name="живая.md")
        assert main([str(tmp_path), "--flag-page", "GBO-52119"]) == 0
        assert "unapproved_jira: GBO-52119" in _read(tmp_path / "заморожено.md")

    def test_task_from_manifest_accepted(self, tmp_path):
        _write(tmp_path, TestFlagPage.FROZEN)
        (tmp_path / "migration-manifest.yaml").write_text(
            "tasks:\n  GBO-52119:\n    color: black\n", encoding="utf-8")
        assert main([str(tmp_path), "--flag-page", "GBO-52119"]) == 0
        assert "unapproved_jira: GBO-52119" in _read(tmp_path / "страница.md")

    def test_garbage_id_rejected(self, tmp_path):
        try:
            main([str(tmp_path), "--flag-page", "не-джира"])
        except SystemExit as e:
            assert e.code == 2
        else:
            raise AssertionError("мусорный идентификатор должен отвергаться")
