# tests/test_critic_island_nested_task.py
#
# Цвет другой задачи внутри цветного элемента в HTML-острове (FB-40 КК, 2026-10-28;
# страница 2166861010 «ЭКО_Получение отчета по карте из Ф1», ячейка кратности totalAmount):
#   <span cc99ff>[<span ff00ff>0..</span>1]</span>
# Было: внешний элемент получал critic-ins своей задачи, рекурсия шла с непустым стеком, и
# внутренний цвет маркера не получал — черновик поздней задачи уходил в ПРОМ с внешней, в
# отчёт конструкция не попадала. Уплощение ТЗ п. 4.5 (один маркер под ВНУТРЕННЕЙ задачей,
# зачёркнутый черновик отброшен, запись confidence=high) было только в прозе.
# Стало: то же в островах — ячейка, цветной потомок пункта и пункт, цветной целиком.
# Тесты парами: срабатывание / НЕсрабатывание; проза — без изменений.

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

OUTER, INNER = "DBOCORPESPLN-104756", "DBOCORPESPLN-118548"
CMAP = {"#cc99ff": OUTER, "#ff00ff": INNER}
VIOLET, MAGENTA, BLACK = "rgb(204,153,255)", "rgb(255,0,255)", "rgb(0,0,0)"
NESTED = (f'<span style="color: {VIOLET};">[<span style="color: {MAGENTA};">0..</span>1]</span>')


def _island(cell):
    inner = f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>"
    return f"<table><tbody><tr><td>totalAmount</td><td>{inner}</td></tr></tbody></table>"


def _run(html):
    ext = create_critic_extractor(CMAP)
    return ext.extract(html), ext._critic_report


def _ins(task, text):
    return f'<span class="critic-ins" data-task="{task}">{text}</span>'


# (а) вложенный цвет другой задачи в ячейке острова → один маркер внутренней, запись в отчёт

def test_a_island_cell_nested_task_flattened():
    md, report = _run(_island(NESTED))
    assert _ins(INNER, "[0..1]") in md
    assert f'data-task="{OUTER}"' not in md
    assert report and report[0]["confidence"] == "high"
    assert set(report[0]["tasks"]) == {OUTER, INNER}
    # ввод внутренней задачи без внешней — текст в ПРОМ; reject-all — ничего от обеих
    assert "[0..1]" in process_text_until_stable(md, "apply", INNER)[0]
    assert "0.." not in process_text_until_stable(md, "reject", None)[0]


# (б) внутренний цвет тот же, что внешний → один маркер внешней, отчёт пуст

def test_b_same_color_inside_not_flattened():
    same = (f'<span style="color: {VIOLET};">[<span style="color: {VIOLET};">0..</span>1]</span>')
    md, report = _run(_island(same))
    assert _ins(OUTER, "[0..1]") in md
    assert report == []


# (в) внутренний чёрный → частичное перекрытие, как прежде (чёрный текст без маркера)

def test_c_black_inside_partial_override_unchanged():
    black = (f'<span style="color: {VIOLET};">[<span style="color: {BLACK};">0..</span>1]</span>')
    md, report = _run(_island(black))
    assert f'{_ins(OUTER, "[")}0..{_ins(OUTER, "1]")}' in md
    assert report == []


# (г) внутренний цвет другой задачи зачёркнут → черновик отброшен, выживший текст — под внутренней

def test_d_struck_inner_draft_dropped():
    struck = (f'<span style="color: {VIOLET};">[<span style="color: {MAGENTA};"><s>0..</s></span>1]</span>')
    md, report = _run(_island(struck))
    assert _ins(INNER, "[1]") in md
    assert "0.." not in md
    assert report and report[0]["confidence"] == "high"


def test_d_struck_black_prom_text_kept():
    # зачёркнутый ЧЁРНЫЙ внутри — реальное удаление с ПРОМ, при уплощении не теряется (как в прозе)
    html = (f'<span style="color: {VIOLET};">[<s><span style="color: {BLACK};">0..</span></s>'
            f'<span style="color: {MAGENTA};">1</span>]</span>')
    md, _ = _run(_island(html))
    assert "0.." in md


# (д) пункт <li> острова: цветной потомок пункта и пункт, цветной целиком

def test_e_island_li_child_nested_task_flattened():
    md, report = _run(_island(f"<ul><li>кратность {NESTED}</li></ul>"))
    assert f"<li>кратность {_ins(INNER, '[0..1]')}</li>" in md
    assert report


def test_e_island_li_whole_colored_nested_task_flattened():
    li = f'<ul><li style="color: {VIOLET};">[<span style="color: {MAGENTA};">0..</span>1]</li></ul>'
    md, report = _run(_island(li))
    assert f"<li>{_ins(INNER, '[0..1]')}</li>" in md
    assert report


def test_e_island_li_single_color_not_flattened():
    md, report = _run(_island(f'<ul><li><span style="color: {VIOLET};">пункт</span></li></ul>'))
    assert f"<li>{_ins(OUTER, 'пункт')}</li>" in md
    assert report == []


# (е) проза — без изменений: та же конструкция даёт текстовый маркер внутренней задачи

def test_f_prose_unchanged():
    md, report = _run(f"<p>{NESTED}</p>")
    assert f"{{++{INNER}: [0..1]++}}" in md
    assert report and report[0]["confidence"] == "high"


def test_f_island_without_nesting_unchanged():
    md, report = _run(_island(f'<span style="color: {VIOLET};">[0..1]</span>'))
    assert _ins(OUTER, "[0..1]") in md
    assert report == []
