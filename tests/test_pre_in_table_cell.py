# tests/test_pre_in_table_cell.py
"""Блок кода в ячейке pipe-таблицы источника (2026-11-06): экспортёр 1.9.13 отдавал его как
``` … ```, 1.9.17 — как <pre>…</pre>; вердикт сверки от версии экспортёра не зависит.
Закрытые <pre>/<code> — тот же литерал, что в обратных кавычках; незакрытый тег — как прежде."""
from app.scripts.CI.kitcheck.checks.card_source import (
    check_quoted_literals, check_source_tables, html_param_names,
)
from app.scripts.CI.kitcheck.html import _norm_cell

VALUE = '{ "filter": { "reqDateFrom": { "ge":"2023-07-20" } } }'
CARD_HEAD = "---\nid: SCR-BNK-06.1\n---\n\n# Примеры\n\n"
CARD_WITH = (CARD_HEAD + "| Поле | Тип | Фильтр |\n|---|---|---|\n"
             f"| reqDateFrom | LocalDate | **DateFrom** `{VALUE}` |\n"
             "| reqDateTo | LocalDate | **DateTo** |\n")
CARD_WITHOUT = (CARD_HEAD + "| Поле | Тип | Фильтр |\n|---|---|---|\n"
                "| reqDateFrom | LocalDate | **DateFrom** |\n"
                "| reqDateTo | LocalDate | **DateTo** |\n")


def source(cell: str) -> str:
    return ("---\ntitle: Примеры\n---\n\n| Поле | Тип | Фильтр |\n|---|---|---|\n"
            f"| reqDateFrom | LocalDate | {cell} |\n"
            "| reqDateTo | LocalDate | **DateTo** |\n")


SRC_PRE = source(f"**DateFrom** <pre>{VALUE}</pre>")
SRC_FENCE = source(f"**DateFrom** ``` {VALUE} ```")


def test_norm_pre_equals_backticks():
    assert _norm_cell(f"**DateFrom** <pre>{VALUE}</pre>") == _norm_cell(f"**DateFrom** `{VALUE}`")
    assert _norm_cell(f"**DateFrom** <pre>{VALUE}</pre>") == _norm_cell(f"**DateFrom** ``` {VALUE} ```")


def test_norm_pre_variants():
    assert _norm_cell('<PRE class="x">{ "a": 1 }</PRE>') == _norm_cell('`{ "a": 1 }`')
    # блок отделён от соседнего текста, пробелы внутри и на границах схлопываются
    assert _norm_cell("Фильтр<pre>  x  y </pre>хвост") == "фильтр x y хвост"
    assert _norm_cell("a <pre>x<br>y</pre>") == "a x y"


def test_norm_code_is_inline():
    assert _norm_cell("имя<code>_id</code>") == _norm_cell("имя`_id`") == "имя_id"
    assert _norm_cell('<code class="x">a</code> b') == "a b"


def test_norm_unclosed_and_other_tags_unchanged():
    assert _norm_cell("a <pre>x") == "a <pre>x"
    assert _norm_cell("a </pre> x") == "a </pre> x"
    assert _norm_cell("a <code>x") == "a <code>x"
    # имя тега целиком: <prefix> — не <pre>
    assert _norm_cell("<prefix>x</prefix>") == "<prefix>x</prefix>"
    assert _norm_cell("без тегов `x`") == "без тегов x"


def test_table_pre_value_found_in_backticks():
    rep, ok = check_source_tables(CARD_WITH, SRC_PRE)
    assert ok, rep
    assert rep == check_source_tables(CARD_WITH, SRC_FENCE)[0]


def test_table_pre_value_lost_still_fires():
    # НЕсрабатывание послабления: значения в карточке нет — потеря, как и при ``` в ячейке
    rep, ok = check_source_tables(CARD_WITHOUT, SRC_PRE)
    assert not ok and any("отсутствуют 1 значений ✗" in r for r in rep), rep
    assert not check_source_tables(CARD_WITHOUT, SRC_FENCE)[1]


def test_table_unclosed_pre_still_fires():
    rep, ok = check_source_tables(CARD_WITH, source(f"**DateFrom** <pre>{VALUE}"))
    assert not ok and any("отсутствуют 1 значений ✗" in r for r in rep), rep


def test_table_code_tag():
    rep, ok = check_source_tables(CARD_WITH, source(f"**DateFrom** <code>{VALUE}</code>"))
    assert ok, rep


def test_literal_in_cell_pre_is_value_not_example():
    # литерал ячейки — значение и при <pre>, и при ```: потеря ✗, а не ⚠ класса «примеры»
    for src in (SRC_PRE, SRC_FENCE):
        rep, ok = check_quoted_literals(CARD_WITHOUT, src)
        assert not ok and any("✗" in r and "'filter'" in r for r in rep), rep
        assert not any(r.startswith("⚠ примеры:") for r in rep), rep


def test_literal_in_cell_pre_found():
    rep, ok = check_quoted_literals(CARD_WITH, SRC_PRE)
    assert ok, rep
    assert rep == check_quoted_literals(CARD_WITH, SRC_FENCE)[0]


def test_literal_in_block_pre_outside_table_stays_example():
    # блок вне таблицы и <pre> в HTML-ячейке — по-прежнему класс «примеры»
    for block in (f"<p>Пример:</p><pre>{VALUE}</pre>\n",
                  f"<table><tr><td>a</td><td><pre>{VALUE}</pre></td></tr></table>\n"):
        rep, ok = check_quoted_literals(CARD_HEAD + "текст\n", "---\ntitle: П\n---\n\n" + block)
        assert ok, rep
        assert any(r.startswith("⚠ примеры:") for r in rep), rep


def test_literal_in_unclosed_pre_in_cell_is_value():
    rep, ok = check_quoted_literals(CARD_WITHOUT, source(f"**DateFrom** <pre>{VALUE}"))
    assert not ok and not any(r.startswith("⚠ примеры:") for r in rep), rep


def test_html_param_names_parser_strips_pre():
    # HTML-таблицы проходят через разбор тегов: <pre> в ячейке не меняет имени параметра
    table = "<table><tr><th>Имя</th><th>Тип</th></tr><tr><td>{}</td><td>string</td></tr></table>"
    assert ("file_id" in html_param_names(table.format("<pre>file_id</pre>"))
            and "file_id" in html_param_names(table.format("<code>file_id</code>"))
            and "file_id" in html_param_names(table.format("file_id")))
