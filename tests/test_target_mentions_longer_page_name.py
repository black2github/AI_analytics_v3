# tests/test_target_mentions_longer_page_name.py
"""Титул карточки внутри более длинного названия страницы (постановка «Точек» 2026-11-18, приёмка
предложения 18.11). Сторож упоминаний целей, часть (а), находил титул карточки внутри названия
другой страницы — «[КК_ВК] Получить выписку по клиенту в КНОСИС (Этап 1)» читался как PROC-030 — и
требовал неверную ссылку. Правило без словаря: если текст в месте вхождения продолжается до более
длинного названия страницы выгрузки или описи, это упоминание той страницы; судьба — по номеру
страницы, в порядке:
а — страница проверяемой карточки → строка i «own»;
б — страница карточки короткого титула → как прежде;
в — страница другой карточки → «имя существующей карточки» с полным названием и путём той карточки;
г — карточки нет, страница снята с миграции по описи (класс source_coverage, и только он) →
    строка i «out-of-srs» с основанием (раньше следа матрицы);
д — карточки нет, след в матрице (полное название или номер страницы) → засчитано молча;
е — ничего из этого → предупреждение части (б) с полным названием.
Несрабатывание: «имя карточки (пояснение)» без такой страницы; без выгрузки и описи — как прежде.
Титул, оканчивающийся кавычкой: указатель титулов срезает её (правка кавычки отложена — она
меняет вычёркивание соседнего текста), длинным названием тогда служит полный титул страницы."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks import card_clean as cc
from app.scripts.CI.kitcheck.checks import source_profile as sp

SHORT = "[КК_ВК] Получить выписку по клиенту в КНОСИС"
LONG = SHORT + " (Этап 1)"
PID_SHORT, PID_LONG = "2166860100", "2166860154"
MATRIX = "# Матрица трассировки\n\n| FROM | TO |\n|---|---|\n"


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def card(cid: str, title: str, body: str, ids=(), typ: str = "process") -> str:
    head = f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\n"
    if ids:
        head += "confluence_page_ids: [" + ", ".join(f"'{i}'" for i in ids) + "]\n"
    return head + f"---\n\n# {cid}\n\n{body}\n"


def kit(tmp_path: Path, proc_ids=(PID_SHORT,), matrix: str = MATRIX) -> Path:
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", matrix)
    make(docs / "srs" / "process" / "proc-030.md", card("PROC-030", SHORT, "т", proc_ids))
    return docs


def export(pages=None):
    return sp.MentionExport(frozenset(), frozenset(), frozenset(), dict(pages or {}))


def run(docs: Path, body: str, exp=None, inv=None, ids=(), name="ntf-002.md"):
    md = make(docs / "srs" / name, card("NTF-002", "[КК_ВК] Нотификации", body, ids, "notification"))
    cc._TARGET_INDEX_CACHE.clear()
    cc._LONGER_CACHE.clear()
    labels, waived = [], []
    warns, ok = cc.check_target_mentions(md.read_text(encoding="utf-8"), md, docs, frozenset(),
                                         labels, exp, waived, inventory_rows=inv)
    assert ok is True
    return warns, waived


def existing(warns):
    return [w for w in warns if "имя существующей карточки" in w]


def target(warns):
    return [w for w in warns if "упоминание цели" in w]


BODY = f"Шаг №11 процесса {LONG}, затем выход."
PAGES = {PID_SHORT: SHORT, PID_LONG: LONG}


# ---------------------------------------------------------------- а: собственная страница
def test_a_own_page_is_info(tmp_path):
    docs = kit(tmp_path)
    warns, waived = run(docs, BODY, export(PAGES), ids=("2166860273", PID_LONG))
    assert not existing(warns) and not target(warns), warns
    assert ("own", LONG) in waived, waived


# ---------------------------------------------------------------- б: страница той же карточки
def test_b_page_of_same_card_as_before(tmp_path):
    # PROC-030 несёт страницу этапа 1 вторым номером шапки — ссылка на неё верна
    docs = kit(tmp_path, proc_ids=(PID_SHORT, PID_LONG))
    warns, waived = run(docs, BODY, export(PAGES))
    ex = existing(warns)
    assert len(ex) == 1 and f"«{SHORT}» ×1 → srs/process/proc-030.md" in ex[0], warns
    assert not waived, waived


def test_b_same_card_strikes_only_title_as_before(tmp_path):
    # «как прежде» целиком: вычёркивается только титул; соседний текст судится как до правки
    # (КК SCR-CL-07: «[DELETE] [КК_СК] ЭФ Клиента "Список карт, …" (Всплывающее окно)»)
    long_q = SHORT + '" (окно)'
    docs = kit(tmp_path, proc_ids=(PID_SHORT, PID_LONG))
    before, _ = run(docs, f"- `[DELETE] {long_q}`")
    after, waived = run(docs, f"- `[DELETE] {long_q}`", export({PID_SHORT: SHORT, PID_LONG: SHORT + '"'}))
    assert after == before and not waived, (before, after)


# ---------------------------------------------------------------- в: страница другой карточки
def test_c_page_of_other_card_warns_with_long_name(tmp_path):
    docs = kit(tmp_path)
    make(docs / "srs" / "process" / "proc-099.md", card("PROC-099", "[КК_ВК] Этап один", "т", (PID_LONG,)))
    warns, _ = run(docs, BODY, export(PAGES))
    ex = existing(warns)
    assert len(ex) == 1 and f"«{LONG}» ×1 → srs/process/proc-099.md" in ex[0], warns


# ---------------------------------------------------------------- г: снято с миграции по описи
INV_HEAD = ("| page_id | title | родитель | req_type | строк | целевой тип (гипотеза) | основание |\n"
            "|---|---|---|---|---|---|---|\n")


def inventory(tmp_path: Path, target: str, basis: str, head: str = INV_HEAD, row: str = "") -> dict:
    """Строки описи через selfcheck: колонки по заголовку, класс — классификатор покрытия."""
    row = row or f"| {PID_LONG} | {LONG} | [КК_ВК]-Процесс-(этап-1) | process | 104 | {target} | {basis} |\n"
    return sc._mention_inventory(make(tmp_path / "inventory.md", "# Опись\n\n" + head + row))


def test_d_withdrawn_by_inventory_is_info(tmp_path):
    docs = kit(tmp_path)
    inv = inventory(tmp_path, "вне SRS: снято с миграции", "решение владельца 18.11")
    warns, waived = run(docs, BODY, export(PAGES), inv)
    assert not existing(warns) and not target(warns), warns
    assert ("out-of-srs", f"{LONG} ← решение владельца 18.11") in waived, waived


def test_d_withdrawn_only_in_basis_is_info(tmp_path):
    # КК :57 — целевой тип archiv, «снято с миграции» только в основании: класс тот же
    docs = kit(tmp_path)
    inv = inventory(tmp_path, "archiv", "reference-only — снято с миграции: черновик-копия")
    warns, waived = run(docs, BODY, export(PAGES), inv)
    assert not existing(warns) and [k for k, _ in waived] == ["out-of-srs"], (warns, waived)


def test_d_base_contract_not_waived(tmp_path):
    # НЕсрабатывание: «вне SRS: базовый контракт EXTINT-X-001» — цель есть (контракт), судится дальше
    docs = kit(tmp_path)
    inv = inventory(tmp_path, "вне SRS: базовый контракт EXTINT-X-001", "страница метода владельца")
    warns, waived = run(docs, BODY, export(PAGES), inv)
    assert not waived and len(target(warns)) == 1, (warns, waived)


def test_d_frozen_not_waived(tmp_path):
    # НЕсрабатывание: заморожено — ждём строку долга frozen, не снятие
    docs = kit(tmp_path)
    inv = inventory(tmp_path, "вне SRS: заморожено GBO-1", "frozen (unapproved_jira)")
    warns, waived = run(docs, BODY, export(PAGES), inv)
    assert not waived and len(target(warns)) == 1, (warns, waived)


def test_d_negated_withdrawn_not_waived(tmp_path):
    # НЕсрабатывание: «не снято с миграции» — отрицание признака
    docs = kit(tmp_path)
    inv = inventory(tmp_path, "srs/bc-issue/process", "не снято с миграции: страница действует")
    warns, waived = run(docs, BODY, export(PAGES), inv)
    assert not waived and len(target(warns)) == 1, (warns, waived)


def test_d_inventory_other_column_order(tmp_path):
    head = "| основание | page_id | целевой тип (гипотеза) | title |\n|---|---|---|---|\n"
    row = f"| решение владельца | {PID_LONG} | вне SRS: снято с миграции | {LONG} |\n"
    inv = inventory(tmp_path, "", "", head, row)
    assert inv == {PID_LONG: (LONG, True, "решение владельца")}, inv
    docs = kit(tmp_path)
    warns, waived = run(docs, BODY, None, inv)
    assert not existing(warns) and [k for k, _ in waived] == ["out-of-srs"], (warns, waived)


def test_d_inventory_before_matrix_trace(tmp_path):
    # и снятие по описи, и строка матрицы — снятие видно строкой i (решение «Точек» 18.11)
    docs = kit(tmp_path, matrix=MATRIX + f"| PROC-022 | снят «{LONG}» |\n")
    inv = inventory(tmp_path, "вне SRS: снято с миграции", "")
    warns, waived = run(docs, BODY, export(PAGES), inv)
    assert not existing(warns) and [k for k, _ in waived] == ["out-of-srs"], (warns, waived)


def test_d_inventory_in_srs_not_waived(tmp_path):
    # НЕсрабатывание: опись относит страницу к srs/… — судится дальше (е)
    docs = kit(tmp_path)
    inv = inventory(tmp_path, "srs/bc-issue/process", "сигналы согласны")
    warns, waived = run(docs, BODY, export(PAGES), inv)
    assert not waived and len(target(warns)) == 1, (warns, waived)


# ---------------------------------------------------------------- д: след в матрице
def test_e_matrix_full_name_counts_silently(tmp_path):
    docs = kit(tmp_path, matrix=MATRIX + f"| DM-001 | — | нет целевого артефакта process «{LONG}» |\n")
    warns, waived = run(docs, BODY, export(PAGES))
    assert not existing(warns) and not target(warns) and not waived, (warns, waived)


def test_e_matrix_page_id_counts_silently(tmp_path):
    docs = kit(tmp_path, matrix=MATRIX + f"| DM-001 | — | долг: страница {PID_LONG} |\n")
    warns, waived = run(docs, BODY, export(PAGES))
    assert not existing(warns) and not target(warns) and not waived, (warns, waived)


def test_e_matrix_short_name_only_is_not_trace(tmp_path):
    # НЕсрабатывание: в матрице только имя короткой карточки — игла из трёх слов не засчитывает
    docs = kit(tmp_path, matrix=MATRIX + f"| PROC-030 | «{SHORT}» |\n")
    warns, _ = run(docs, BODY, export(PAGES))
    t = target(warns)
    assert len(t) == 1 and f"«{LONG}» ×1" in t[0], warns


# ---------------------------------------------------------------- е: ни описи, ни следа
def test_f_no_card_no_trace_warns_link_or_debt(tmp_path):
    docs = kit(tmp_path)
    warns, waived = run(docs, BODY, export(PAGES))
    assert not existing(warns) and not waived, (warns, waived)
    t = target(warns)
    assert len(t) == 1 and f"«{LONG}» ×1" in t[0] and "либо долг в матрице" in t[0], warns


# ---------------------------------------------------------------- несрабатывание
def test_bracket_note_without_such_page_stays_card_name(tmp_path):
    # «имя карточки (пояснение)»: названия «имя (пояснение)» нет ни в выгрузке, ни в описи
    docs = kit(tmp_path)
    inv = {PID_SHORT: (SHORT, False, "")}
    warns, waived = run(docs, f"Процесс {SHORT} (для ЮЛ), затем выход.", export(PAGES), inv)
    ex = existing(warns)
    assert len(ex) == 1 and f"«{SHORT}» ×1 → srs/process/proc-030.md" in ex[0], warns
    assert not waived and not target(warns), (warns, waived)


def test_without_export_and_inventory_as_before(tmp_path):
    docs = kit(tmp_path)
    warns, waived = run(docs, BODY)
    ex = existing(warns)
    assert len(ex) == 1 and f"«{SHORT}» ×1 → srs/process/proc-030.md" in ex[0], warns
    assert not waived, waived


def test_link_to_long_page_not_judged(tmp_path):
    # упоминание в markdown-ссылке сторожу не видно — как прежде
    docs = kit(tmp_path)
    warns, waived = run(docs, f"Шаг [{LONG}](process/proc-030.md).", export(PAGES))
    assert not existing(warns) and not target(warns) and not waived, (warns, waived)


# ---------------------------------------------------------------- титул с кавычкой в конце
def test_own_title_ending_with_quote_not_read_as_index_card(tmp_path):
    # SCR-CL-01 «[КК_СК] ЭФ Клиента "Список карт"» называет свою страницу; внутри — титул индекса ЭФ
    # «[КК_СК] ЭФ Клиента» (SCR-CL-07): прежде «имя существующей карточки → scr-cl-07», теперь own
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", MATRIX)
    make(docs / "srs" / "scr-cl-07.md", card("SCR-CL-07", "[КК_СК] ЭФ Клиента", "т", ("2166860400",)))
    full = '[КК_СК] ЭФ Клиента "Список карт"'
    md = make(docs / "srs" / "scr-cl-01.md", card("SCR-CL-01", full, f"Описание ЭФ {full}.", ("2166860498",)))
    cc._TARGET_INDEX_CACHE.clear()
    cc._LONGER_CACHE.clear()
    waived = []
    warns, _ = cc.check_target_mentions(md.read_text(encoding="utf-8"), md, docs, frozenset(), [],
                                        export({"2166860498": full, "2166860400": "[КК_СК] ЭФ Клиента"}),
                                        waived)
    assert not existing(warns) and not target(warns), warns
    assert ("own", full) in waived, waived


# ---------------------------------------------------------------- строка i в selfcheck
def test_selfcheck_waived_kind_out_of_srs_listed():
    kinds = dict(sc._WAIVED_KINDS)
    assert "out-of-srs" in kinds and kinds["out-of-srs"].startswith("упоминания страниц, снятых с миграции по описи")
