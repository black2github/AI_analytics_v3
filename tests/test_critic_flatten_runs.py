"""Уплощение вложенных цветов по прогонам (ТЗ п. 4.5, версия 1.9.18).

Было: весь текст конструкции уходил под один маркер самой глубокой задачи, зачёркнутое
отбрасывалось. Когда внешняя задача введена, а внутренняя нет, её текст выпадал из среза
ПРОМ до ввода внутренней (КК, выгрузка 05.11: 11 записей из 35).
Стало: вид и задачу каждого узла определяет его эффективный цвет; зачёркнутое — удаление
задачи своего цвета (решение владельца 06.11), чёрное — без маркера.
"""
import pytest

from app.content_extractor import create_critic_extractor
from app.prom_invariant import check_prom_invariant
from app.scripts.CI.critic import find_literal_nesting, process_text_until_stable

X, Y, Z = "GBO-1", "GBO-2", "GBO-3"
CMAP = {"#ff6600": X, "#ff00ff": Y, "#00ff00": Z}
XC, YC, ZC = "rgb(255,102,0)", "rgb(255,0,255)", "rgb(0,255,0)"
RED, BLACK, NEAR_BLACK = "rgb(255,0,0)", "rgb(0,0,0)", "rgb(0,51,102)"


def span(color, inner):
    return f'<span style="color: {color};">{inner}</span>'


def run(body, cmap=None):
    ext = create_critic_extractor(CMAP if cmap is None else cmap)
    return ext.extract(body), ext._critic_report


def island(cell):
    nested = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
    return f"<table><tbody><tr><td>поле</td><td>{nested}</td></tr></tbody></table>"


def ins(task, text):
    return f'<span class="critic-ins" data-task="{task}">{text}</span>'


def dele(task, text):
    return f'<span class="critic-del" data-task="{task}">{text}</span>'


def slice_with_introduced(md, *introduced):
    """Срез ПРОМ: задачи introduced приняты, остальные отклонены."""
    for task in introduced:
        md = process_text_until_stable(md, "apply", task)[0]
    return process_text_until_stable(md, "reject", None)[0].strip()


class TestProse:
    def test_inner_color_splits_runs_and_spaces_survive(self):
        md, report = run(f'<p>{span(XC, "a " + span(YC, "b") + " c")}</p>')
        assert f"{{++{X}: a ++}}{{++{Y}: b++}} {{++{X}: c++}}" in md
        assert report[0]["parts"] == 3
        assert report[0]["tasks"] == [X, Y]
        assert report[0]["confidence"] == "high"

    def test_no_word_gluing_after_apply(self):
        md, _ = run(f'<p>{span(XC, "a " + span(YC, "b") + " c")}</p>')
        assert slice_with_introduced(md, X, Y) == "a b c"

    def test_struck_inner_is_deletion_of_inner_task(self):
        md, report = run(f'<p>{span(XC, "шаг №" + span(YC, "11<s>9</s>"))}</p>')
        assert f"{{++{X}: шаг №++}}{{++{Y}: 11++}}{{--{Y}: 9--}}" in md
        assert report[0]["parts"] == 3

    def test_struck_in_outer_color_is_deletion_of_outer_task(self):
        """Единое правило без исключения: цвет внешней задачи — её удаление."""
        md, _ = run(f'<p>{span(XC, "шаг №" + span(YC, "6") + "<s>4</s>,")}</p>')
        assert f"{{++{X}: шаг №++}}{{++{Y}: 6++}}{{--{X}: 4--}}{{++{X}: ,++}}" in md

    def test_three_levels_nearest_color(self):
        md, report = run(f'<p>{span(XC, "a" + span(YC, "b" + span(ZC, "c") + "d") + "e")}</p>')
        assert (f"{{++{X}: a++}}{{++{Y}: b++}}{{++{Z}: c++}}{{++{Y}: d++}}{{++{X}: e++}}") in md
        assert report[0]["tasks"] == [X, Y, Z]
        assert report[0]["parts"] == 5

    def test_struck_above_element_is_deletion(self):
        md, _ = run(f'<p><s>{span(XC, "a" + span(YC, "b"))}</s></p>')
        assert f"{{--{X}: a--}}{{--{Y}: b--}}" in md

    @pytest.mark.parametrize("color", [BLACK, NEAR_BLACK])
    def test_black_run_stays_without_marker(self, color):
        md, report = run(f'<p>{span(XC, "шаг №" + span(color, "6") + span(YC, "7") + ".")}</p>')
        assert f"{{++{X}: шаг №++}}6{{++{Y}: 7++}}{{++{X}: .++}}" in md
        assert report[0]["parts"] == 4

    def test_struck_black_stays_without_marker(self):
        md, _ = run(f'<p>{span(XC, "a <s>" + span(BLACK, "ПРОМ") + "</s> " + span(YC, "b"))}</p>')
        assert f"{{++{X}: a ++}}ПРОМ {{++{Y}: b++}}" in md

    def test_unknown_color_keeps_placeholder(self):
        md, report = run(f'<p>{span(XC, "a" + span(RED, "b"))}</p>')
        assert f"{{++{X}: a++}}{{++UNKNOWN-ff0000: b++}}" in md
        assert report[0]["tasks"] == [X, "UNKNOWN-ff0000"]

    def test_output_has_no_literal_nesting(self):
        md, _ = run(f'<p>{span(XC, "a" + span(YC, "b<s>c</s>" + span(ZC, "d")))}</p>')
        assert find_literal_nesting(md) == []


class TestWhitespaceNode:
    """Запись 13 выгрузки КК 05.11: красный спан вокруг пробела забрал весь текст."""

    PINK, PINK_C = "#ff99cc", "rgb(255,153,204)"
    CMAP_KK = {"#ff6600": X, "#ff99cc": Y}

    def test_colored_space_creates_no_marker_and_no_task(self):
        body = span(XC, span(self.PINK_C, span(RED, " ")) + span(self.PINK_C, "существует сущность ")
                    + "Лимит" + span(self.PINK_C, ", для которой"))
        md, report = run(f"<p>{body}</p>", self.CMAP_KK)
        assert "UNKNOWN" not in md
        assert f"{{++{Y}: существует сущность ++}}{{++{X}: Лимит++}}{{++{Y}: , для которой++}}" in md
        assert report[0]["tasks"] == [X, Y]

    def test_space_between_runs_goes_to_previous_run(self):
        md, _ = run(f'<p>{span(XC, "a" + span(RED, " ") + span(YC, "b"))}</p>')
        assert f"{{++{X}: a ++}}{{++{Y}: b++}}" in md
        assert "UNKNOWN" not in md


class TestOneColorUnchanged:
    """Один цвет внутри элемента — вывод 1.9.17 байт в байт."""

    def test_two_colors_of_one_task_give_single_marker(self):
        cmap = {"#ff6600": X, "#ff00ff": X}
        md, report = run(f'<p>{span(XC, " a  " + span(YC, "b") + " c ")}</p>', cmap)
        assert f"{{++{X}: a b c++}}" in md
        assert report[0]["parts"] == 1

    def test_same_color_inside_is_not_flattening(self):
        md, report = run(f'<p>{span(XC, "a " + span(XC, "b"))}</p>')
        assert f"{{++{X}: a b++}}" in md
        assert report == []


class TestIsland:
    def test_cell_runs(self):
        md, report = run(island(span(XC, "a " + span(YC, "b") + " c")))
        assert f'{ins(X, "a ")}{ins(Y, "b")} {ins(X, "c")}' in md
        assert report[0]["parts"] == 3

    def test_list_item_child_and_whole_item(self):
        child, _ = run(island(f'<ul><li>пункт {span(XC, "a" + span(YC, "b"))}</li></ul>'))
        assert f'<li>пункт {ins(X, "a")}{ins(Y, "b")}</li>' in child
        whole, _ = run(island(f'<ul><li style="color: {XC};">a{span(YC, "b")}</li></ul>'))
        assert f'<li>{ins(X, "a")}{ins(Y, "b")}</li>' in whole

    def test_struck_inner_is_deletion(self):
        md, _ = run(island(span(XC, "a" + span(YC, "<s>b</s>c"))))
        assert f'{ins(X, "a")}{dele(Y, "b")}{ins(Y, "c")}' in md

    def test_three_levels(self):
        md, report = run(island(span(XC, "a" + span(YC, "b" + span(ZC, "c")))))
        assert f'{ins(X, "a")}{ins(Y, "b")}{ins(Z, "c")}' in md
        assert report[0]["tasks"] == [X, Y, Z]

    def test_black_run_without_marker(self):
        md, _ = run(island(span(XC, "a" + span(BLACK, "b") + span(YC, "c"))))
        assert f'{ins(X, "a")}b{ins(Y, "c")}' in md

    def test_angle_bracket_escaped_in_every_run(self):
        md, _ = run(island(span(XC, "&lt;abc&gt;" + span(YC, "&lt;def&gt;"))))
        assert "&lt;abc" in md and "&lt;def" in md

    def test_one_task_gives_single_span(self):
        md, _ = run(island(span(XC, "a " + span(YC, "b"))), {"#ff6600": X, "#ff00ff": X})
        assert ins(X, "a b") in md


class TestSlices:
    """Ради этого и сделано: срез ПРОМ при разном составе введённых задач."""

    TZ = ('<p>' + span(XC, "Организация должна быть "
                       + span(YC, "<s>головной</s>действующей и головной")) + '.</p>')

    def test_outer_introduced_inner_not(self):
        md, _ = run(self.TZ)
        assert slice_with_introduced(md, X) == "Организация должна быть головной."

    def test_both_introduced(self):
        md, _ = run(self.TZ)
        assert slice_with_introduced(md, X, Y) == "Организация должна быть действующей и головной."

    def test_none_introduced_leaves_struck_as_accepted_noise(self):
        """Цена решения: лишний текст, а не потеря. Зафиксировано намеренно."""
        md, _ = run(self.TZ)
        assert slice_with_introduced(md) == "головной."

    def test_inner_introduced_outer_not_keeps_inner_text(self):
        md, _ = run(self.TZ)
        assert "действующей и головной" in slice_with_introduced(md, Y)

    def test_island_outer_introduced_inner_not(self):
        html = island(span(XC, "Организация " + span(YC, "<s>головная</s>новая")))
        md, _ = run(html)
        out = slice_with_introduced(md, X)
        assert "Организация" in out and "головная" in out and "новая" not in out


class TestPromInvariant:
    """Модель сторожа --check-prom: на ПРОМ чёрное и всё зачёркнутое. Уплощение ей верно."""

    @pytest.mark.parametrize("body", [
        span(XC, "шаг №" + span(YC, "11<s>9</s>") + " дальше"),
        span(XC, "шаг №" + span(YC, "6") + "<s>4</s>,"),
        span(XC, "начало " + span(BLACK, "ПРОМ текст") + " конец " + span(YC, "новое")),
        span(XC, "начало <s>" + span(BLACK, "удалено с ПРОМ") + "</s> " + span(YC, "новое")),
    ])
    def test_flatten_gives_no_signal(self, body):
        html = f"<p>Чёрный абзац {body}</p>"
        ext = create_critic_extractor(CMAP)
        md = ext.extract(html)
        assert ext._critic_report
        check = check_prom_invariant(html, md, ext)
        assert check.ok, check.summary()
