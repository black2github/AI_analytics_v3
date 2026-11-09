# tests/test_group_linked_calls.py
"""Сторож имён параметров HTML-таблиц: карточки вызова по ссылке ищутся от группы сверки, а не
от главного файла (КК FUN-SYS-10 + карточка вызова той же страницы, постановка 2026-11-09, П-1).
Таблица шага вынесена в карточки вызова (решение владельца канона 2026-11-02) — имена, найденные
в карточке вызова, на которую ссылается любой держатель шагов группы, на месте; не найденные нигде
остаются ✗."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks.card_run import run_check

P1 = "2000000111"
SRC = (f"---\ntitle: 'Функция проверки'\nconfluence_page_id: '{P1}'\n---\n\n"
       "<table><tr><th>Параметр</th><th>Описание</th></tr>"
       "<tr><td>GPB_CorpCardIssue_Auth_Check</td><td>вариант 10.1</td></tr>"
       "<tr><td>GPB_ProdCredentialsComb_Auth_Check</td><td>вариант 10.2</td></tr></table>\n")
NAMES = ("| ProcessName | GPB_CorpCardIssue_Auth_Check |\n"
         "| ProcessName | GPB_ProdCredentialsComb_Auth_Check |\n")
LOST = "отсутствуют 2 имён параметров"
FOUND = "найдено в карточках вызова по ссылке (CALL-EXT-011)"


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def card(cid, typ, body="текст\n", pids=P1, title="Функция проверки"):
    return (f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\nconfluence_page_ids: [{pids}]\n---\n\n"
            f"# {cid}. {title}\n\n{body}")


LINK = "Шаг 1: правила заполнения — в [CALL-EXT-011](../contract-call/call-ext-011.md).\n"


def call_ext(root: Path, names: str = NAMES) -> Path:
    return make(root / "contract-call/call-ext-011.md",
                card("CALL-EXT-011", "contract-call", names, pids="2000000222", title="Вызов ЕСК"))


def _src(tmp_path: Path) -> Path:
    return make(tmp_path / "src" / f"{P1}.md", SRC)


# ---------------------------------------------------------------- неглавный держатель шагов

def test_non_main_holder_links_searched(tmp_path):
    # главная — процесс без ссылки, неглавная функция ссылается на CALL-EXT с именами
    root = tmp_path / "srs"
    call_ext(root)
    proc = make(root / "process/proc-001.md", card("PROC-001", "process"))
    fun = make(root / "function/fun-001.md", card("FUN-001", "function", LINK))
    rep, _ok = run_check([proc, fun], _src(tmp_path))
    text = "\n".join(rep)
    assert LOST not in text, text
    assert FOUND in text, text


def test_name_nowhere_still_defect(tmp_path):
    # срабатывание: в связанной карточке вызова имён нет — ✗ как прежде
    root = tmp_path / "srs"
    call_ext(root, names="другое\n")
    proc = make(root / "process/proc-001.md", card("PROC-001", "process"))
    fun = make(root / "function/fun-001.md", card("FUN-001", "function", LINK))
    rep, ok = run_check([proc, fun], _src(tmp_path))
    assert not ok and LOST in "\n".join(rep), rep


def test_non_holder_non_main_links_ignored(tmp_path):
    # ограничитель: ссылка неглавной карточки не держателя шагов (data-model) не учитывается
    root = tmp_path / "srs"
    call_ext(root)
    proc = make(root / "process/proc-001.md", card("PROC-001", "process"))
    ent = make(root / "data-model/ent-001.md", card("ENT-001", "data-model", LINK))
    rep, ok = run_check([proc, ent], _src(tmp_path))
    assert not ok and LOST in "\n".join(rep), rep


# ---------------------------------------------------------------- главная — карточка вызова

def test_call_main_group_uses_own_links(tmp_path):
    # группа без держателя страницы: главная — карточка вызова со ссылкой на CALL-EXT
    root = tmp_path / "srs"
    call_ext(root)
    call = make(root / "contract-call/call-int-001.md", card("CALL-INT-001", "contract-call", LINK))
    ent = make(root / "data-model/ent-001.md", card("ENT-001", "data-model"))
    rep, _ok = run_check([call, ent], _src(tmp_path))
    text = "\n".join(rep)
    assert LOST not in text and FOUND in text, text


# ---------------------------------------------------------------- одиночные карточки — без изменений

def test_single_function_unchanged(tmp_path):
    root = tmp_path / "srs"
    call_ext(root)
    fun = make(root / "function/fun-001.md", card("FUN-001", "function", LINK))
    rep, _ok = run_check([fun], _src(tmp_path))
    text = "\n".join(rep)
    assert LOST not in text and FOUND in text, text


def test_single_call_card_unchanged(tmp_path):
    # одиночная карточка вызова ссылок не читала — и не читает
    root = tmp_path / "srs"
    call_ext(root)
    call = make(root / "contract-call/call-int-001.md", card("CALL-INT-001", "contract-call", LINK))
    rep, ok = run_check([call], _src(tmp_path))
    assert not ok and LOST in "\n".join(rep), rep


# ---------------------------------------------------------------- форма КК через selfcheck

def test_kk_form_call_and_function_group_passes(tmp_path):
    # КК FUN-SYS-10: карточка вызова и функция с одной главной страницей; имена — в CALL-EXT,
    # на который ссылается функция. Главная группы — функция (держатель), имена найдены
    docs = tmp_path / "kit/docs"
    make(docs / "traceability-matrix.md", "# М\n")
    root = docs / "srs/bc-component"
    call_ext(root)
    make(root / "contract-call/call-int-014.md", card("CALL-INT-014", "contract-call"))
    make(root / "function/fun-sys-10.md", card("FUN-SYS-10", "function", LINK))
    make(docs.parent / "sources/confluence" / f"{P1}.md", SRC)
    make(docs.parent / "sources/confluence/2000000222.md",
         "---\ntitle: 'Вызов ЕСК'\nconfluence_page_id: '2000000222'\n---\n\nтекст\n")
    report, _ok = sc.run(docs, docs.parent / "sources/confluence")
    group = [ln for ln in report if "fun-sys-10.md" in ln and "←" in ln]
    assert group and "call-int-014.md" in group[0], report
    assert not any(LOST in ln for ln in report), "\n".join(report)
