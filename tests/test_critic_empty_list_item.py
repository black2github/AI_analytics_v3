# tests/test_critic_empty_list_item.py
#
# Пункт списка, опустевший после reject/apply (FB-40 КК, 2026-10-28): пункт целиком из
# вставки невведённой задачи после reject-all оставлял строку «    * » без текста (срез КК:
# 92 строки на 23 страницах), карточка FUN-SYS-13 унаследовала 8. Симметрично — пункт
# целиком из удаления после apply. Снимается только строка, где стоял снятый маркер и
# остался один маркер списка; пустые пункты источника, пункты с чёрным остатком и
# родители с непустыми детьми остаются. Тесты парами: срабатывание / НЕсрабатывание.

from app.scripts.CI.critic import process_text, process_text_until_stable

T = "GBO-1"
INS = f'<span class="critic-ins" data-task="{T}">'


def _reject(md):
    return process_text_until_stable(md, "reject", None)[:2]


def _apply(md):
    return process_text_until_stable(md, "apply", T)[:2]


# (а) пункт целиком из вставки: reject удаляет строку, apply оставляет текст

def test_a_insert_item_reject_drops_line():
    out, n = _reject(f"- раз\n    * {{++{T}: вставка++}}\n- два\n")
    assert out == "- раз\n- два\n" and n == 2      # маркер + удалённый пункт


def test_a_insert_item_apply_keeps_text():
    out, _ = _apply(f"- раз\n    * {{++{T}: вставка++}}\n- два\n")
    assert out == "- раз\n    * вставка\n- два\n"


# (б) пункт целиком из удаления: apply удаляет, reject оставляет

def test_b_delete_item_apply_drops_line():
    out, n = _apply(f"* {{--{T}: старое--}}\n* живое\n")
    assert out == "* живое\n" and n == 2


def test_b_delete_item_reject_keeps_text():
    assert _reject(f"* {{--{T}: старое--}}\n* живое\n")[0] == "* старое\n* живое\n"


# (в) пункт с чёрным остатком остаётся

def test_c_black_remainder_kept():
    assert _reject(f"* до {{++{T}: х++}}\n")[0] == "* до \n"


def test_c_inline_code_and_link_remainder_kept():
    assert _reject(f"* `x`{{++{T}: х++}}\n* [с](a.md){{++{T}: у++}}\n")[0] == "* `x`\n* [с](a.md)\n"


# (г) пустой пункт без маркера в источнике остаётся (свойство источника)

def test_d_preexisting_empty_item_kept():
    md = f"* \n    * \n* {{++{T}: вставка++}}\n"
    assert _reject(md)[0] == "* \n    * \n"


def test_d_no_markers_no_changes():
    assert process_text("* \n- \n1. \n", "reject", None) == ("* \n- \n1. \n", 0)


# (д) вложенность: родитель из вставки с чёрным ребёнком остаётся; без детей — снимается

def test_e_parent_with_black_child_kept():
    md = f"* {{++{T}: родитель++}}\n    * ребёнок\n"
    assert _reject(md)[0] == "* \n    * ребёнок\n"


def test_e_parent_and_child_both_inserted_dropped():
    md = f"* {{++{T}: родитель++}}\n    * {{++{T}: ребёнок++}}\n* сосед\n"
    assert _reject(md)[0] == "* сосед\n"


def test_e_child_dropped_parent_with_text_kept():
    md = f"* родитель\n    * {{++{T}: ребёнок++}}\n"
    assert _reject(md)[0] == "* родитель\n"


# (е) нумерованные пункты «1.» и «1)»; маркер другой задачи не трогается

def test_f_numbered_items():
    md = f"1. {{++{T}: а++}}\n2) {{++{T}: б++}}\n3. в\n"
    assert _reject(md)[0] == "3. в\n"


def test_f_other_task_item_untouched():
    md = f"* {{++{T}: моё++}}\n* {{++GBO-2: чужое++}}\n"
    assert process_text_until_stable(md, "reject", T)[0] == "* {++GBO-2: чужое++}\n"


# (ж) HTML-остров: пустой <li> снимается, опустевший список — тоже; чужие пустые <ul> — нет

def _island(cell):
    return f"<table><tbody><tr><td>{cell}</td></tr></tbody></table>\n"


def test_g_island_li_dropped_and_empty_list_dropped():
    md = _island(f"<p>текст</p><ul><li>{INS}вставка</span></li></ul>")
    out, n = _reject(md)
    assert out == _island("<p>текст</p>") and n == 2


def test_g_island_li_with_black_remainder_kept():
    md = _island(f"<ul><li>чёрное {INS}вставка</span></li><li>{INS}вся</span></li></ul>")
    assert _reject(md)[0] == _island("<ul><li>чёрное </li></ul>")


def test_g_island_preexisting_empty_list_kept():
    md = _island(f"<ul></ul><ul><li></li></ul><p>{INS}вставка</span></p>")
    assert _reject(md)[0] == _island("<ul></ul><ul><li></li></ul><p></p>")


def test_g_island_parent_li_with_child_kept():
    md = _island(f"<ul><li>{INS}родитель</span><ul><li>ребёнок</li></ul></li></ul>")
    assert _reject(md)[0] == _island("<ul><li><ul><li>ребёнок</li></ul></li></ul>")


# (з) идемпотентность: повторный прогон — 0 правок

def test_h_idempotent():
    md = f"* {{++{T}: а++}}\n* \n* б\n" + _island(f"<ul><li>{INS}в</span></li></ul>")
    once, _ = _reject(md)
    assert process_text(once, "reject", None) == (once, 0)


# (и) CRLF сохраняется; fenced-код — байт в байт

def test_i_crlf_preserved():
    md = f"- раз\r\n    * {{++{T}: вставка++}}\r\n- два\r\n"
    assert _reject(md)[0] == "- раз\r\n- два\r\n"


def test_i_fenced_code_untouched():
    md = f"```\n* {{++{T}: в коде++}}\n```\n* {{++{T}: вне++}}\n"
    assert _reject(md)[0] == f"```\n* {{++{T}: в коде++}}\n```\n"
