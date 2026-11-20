# tests/test_link_debts_prune.py
"""Закрытый долг снимается из матрицы (решение владельца 2026-11-20): режим чистки
link_debts --prune-closed, предупреждение «к удалению», ограничители (молчаливо удалить открытый
долг хуже, чем оставить закрытый) и неизменность вердиктов до и после чистки."""
import subprocess
import sys
from pathlib import Path

from app.scripts.CI import link_debts as ld
from app.scripts.CI import transfer_gate as tg

ISSUE = ("долг открытый вопрос: «{st}» — причина: две страницы; ответственный: аналитик; "
         "ограничение: типы параметров; закрытие: решение аналитика{tail}; источник: OQ-{oq}")
OPEN_FIELD = f"| FUN-001 | — | {ISSUE.format(st='типы расходятся', tail='', oq='001')} |"
OPEN_QUOTED = ("| FUN-002 | — | " + ISSUE.format(st="статус «закрыт: 2026-11-01, abc» на экране", tail="",
                                                 oq="002") + " |")
OPEN_PLAN = ("| FUN-001 | — | долг вне плана: «Виджет» — причина: подсервис bc-widget вне плана "
             "миграции (OQ-003); ответственный: владелец комплекта; ограничение: виджет; "
             "закрытие: включение подсервиса в план |")
OPEN_F1 = "| FUN-001 | — | нет целевого артефакта function «Иная функция» — требуется заход create-function |"
CLOSED_SUFFIX = ("| FUN-002 | — | " + ISSUE.format(st="длина не задана", tail="", oq="004")
                 + "; закрыт: 2026-11-05, abc1234 |")
CLOSED_BARE = "| FUN-001 | FUN-002 | Вторая функция |"
CLOSED_LINK = "| FUN-002 | [FUN-001](srs/f1.md) | Первая функция |"
CLOSED_DASH_LINKS = "| FUN-001 | — | [FUN-002](srs/f2.md) |"
CLOSED_ALIEN = "| FUN-001 | CALL-EXT-004 | CALL-EXT-004 — снят: перенесён во второй комплект |"
OPEN_ROWS = [OPEN_FIELD, OPEN_QUOTED, OPEN_PLAN, OPEN_F1]
PRUNABLE = [CLOSED_SUFFIX, CLOSED_BARE, CLOSED_LINK, CLOSED_DASH_LINKS]


def _docs(tmp_path: Path, rows, eol="\r\n", bom=True) -> Path:
    docs = tmp_path / "docs"
    (docs / "srs").mkdir(parents=True)
    (docs / "srs/f1.md").write_text("---\nid: FUN-001\ntitle: 'Первая функция'\n---\n# Ф1\n\n"
                                    "Вызов «Иная функция».\n", encoding="utf-8")
    (docs / "srs/f2.md").write_text("---\nid: FUN-002\ntitle: 'Вторая функция'\n---\n# Ф2\n\nшаг\n",
                                    encoding="utf-8")
    text = ("# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
            "| FUN-001 | function | Первая функция | srs/f1.md |\n"
            "| FUN-002 | function | Вторая функция | srs/f2.md |\n\n"
            "## 5. Долги по ссылкам\n\n| FROM-ID | Цель | Долг |\n|---|---|---|\n"
            + "".join(r + "\n" for r in rows) + "\nабзац после таблицы\n").replace("\n", eol)
    (docs / "traceability-matrix.md").write_bytes((b"\xef\xbb\xbf" if bom else b"")
                                                  + text.encode("utf-8"))
    return docs


ALL = [OPEN_FIELD, CLOSED_SUFFIX, OPEN_QUOTED, CLOSED_BARE, OPEN_PLAN, CLOSED_LINK, OPEN_F1,
       CLOSED_DASH_LINKS, CLOSED_ALIEN]


# ------------------------------------------------------------------ распознавание закрытых строк

def test_closed_rows_forms_and_limits(tmp_path):
    docs = _docs(tmp_path, ALL)
    rows = ld.closed_debt_rows((docs / "traceability-matrix.md").read_text(encoding="utf-8-sig"))
    got = {r["raw"]: (r["form"], r["prunable"]) for r in rows}
    assert got == {CLOSED_SUFFIX: ("приписка", True), CLOSED_BARE: ("цель", True),
                   CLOSED_LINK: ("цель", True), CLOSED_DASH_LINKS: ("цель", True),
                   CLOSED_ALIEN: ("цель", False)}, got
    alien = next(r for r in rows if r["raw"] == CLOSED_ALIEN)
    assert "CALL-EXT-004" in alien["why"]


def test_issue_closed_not_inside_quotes():
    # НЕсрабатывание: «закрыт: <дата>» внутри формулировки в кавычках; поле «закрытие:»
    assert ld.issue_closed(OPEN_QUOTED) is None
    assert ld.issue_closed(OPEN_FIELD) is None
    assert ld.issue_closed(CLOSED_SUFFIX) == "2026-11-05, abc1234"


# ------------------------------------------------------------------ режим чистки

def test_prune_list_only_does_not_write(tmp_path):
    docs = _docs(tmp_path, ALL)
    m = docs / "traceability-matrix.md"
    before = m.read_bytes()
    rep, ok = ld.prune_closed(m)
    assert ok and m.read_bytes() == before
    assert rep[-2] == ("к удалению 4 (ID цели во второй колонке — 3, приписка «закрыт:» — 1); "
                       "не трогается 1; строк раздела долгов было 9, останется 5"), rep
    assert any(r.startswith("не трогается: строка") and "CALL-EXT-004" in r for r in rep)
    assert rep[-1].startswith("файл не изменён")


def test_prune_write_removes_only_closed_and_keeps_bytes(tmp_path):
    docs = _docs(tmp_path, ALL)
    m = docs / "traceability-matrix.md"
    before = m.read_bytes()
    rep, _ = ld.prune_closed(m, write=True)
    after = m.read_bytes()
    want = before
    for r in PRUNABLE:
        want = want.replace(r.encode("utf-8") + b"\r\n", b"")
    assert after == want, rep
    text = after.decode("utf-8-sig")
    for r in OPEN_ROWS + [CLOSED_ALIEN]:
        assert r in text, r                       # открытые и неподтверждённая — на месте
    assert after.startswith(b"\xef\xbb\xbf") and b"\n" not in after.replace(b"\r\n", b"")
    # повторный прогон — снимать нечего, файл не меняется
    rep2, _ = ld.prune_closed(m, write=True)
    assert m.read_bytes() == after and rep2[-1].startswith("удалено 0")


def test_prune_lf_file_stays_lf(tmp_path):
    docs = _docs(tmp_path, ALL, eol="\n", bom=False)
    m = docs / "traceability-matrix.md"
    ld.prune_closed(m, write=True)
    assert b"\r\n" not in m.read_bytes()


def test_prune_unrecognized_row_untouched(tmp_path):
    # НЕсрабатывание: строка нераспознанной формы (вторая колонка — не ID) не трогается
    odd = "| FUN-001 | см. ниже | что-то без формы долга |"
    docs = _docs(tmp_path, [odd, CLOSED_BARE])
    m = docs / "traceability-matrix.md"
    ld.prune_closed(m, write=True)
    text = m.read_text(encoding="utf-8-sig")
    assert odd in text and CLOSED_BARE not in text


def test_cli_prune(tmp_path):
    docs = _docs(tmp_path, ALL)
    m = docs / "traceability-matrix.md"
    script = Path(__file__).resolve().parents[1] / "app/scripts/CI/link_debts.py"
    base = [sys.executable, str(script), "--matrix", str(m), "--docs", str(docs), "--prune-closed"]
    before = m.read_bytes()
    r = subprocess.run(base, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "к удалению 4" in r.stdout and m.read_bytes() == before, r.stdout
    r = subprocess.run(base + ["--write"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "удалено 4" in r.stdout and m.read_bytes() != before


# ------------------------------------------------------------------ проверка до и после чистки

def _open_count(report):
    return next(r for r in report if r.startswith("OK: долгов"))


def test_check_warns_to_delete_and_same_verdict_after_prune(tmp_path):
    docs = _docs(tmp_path, ALL)
    m = docs / "traceability-matrix.md"
    rep1, ok1 = ld.check(m, docs)
    assert any(r.startswith("⚠ закрытых строк долга к удалению: 4 (ID цели во второй колонке — 3, "
                            "приписка «закрыт:» — 1)") for r in rep1), rep1
    assert any(r.startswith("⚠ закрытых по форме строк долга без подтверждённой цели: 1")
               and "CALL-EXT-004" in r for r in rep1), rep1
    debts1 = ld.parse_matrix(m.read_text(encoding="utf-8-sig"))[1]
    ld.prune_closed(m, write=True)
    rep2, ok2 = ld.check(m, docs)
    debts2 = ld.parse_matrix(m.read_text(encoding="utf-8-sig"))[1]
    assert ok1 == ok2
    assert _open_count(rep1) == _open_count(rep2) == "OK: долгов 4, просроченных нет, все имена " \
                                                     "находятся в документах-ожидателях ✓"
    assert debts1 == debts2
    assert not any("к удалению" in r for r in rep2)


def test_closed_suffix_row_not_in_debt_parse(tmp_path):
    # приписка выводит строку из разбора долгов: её не видят гейт и другие потребители
    docs = _docs(tmp_path, [OPEN_FIELD, CLOSED_SUFFIX])
    debts = ld.parse_matrix((docs / "traceability-matrix.md").read_text(encoding="utf-8-sig"))[1]
    assert [d[4] for d in debts] == [OPEN_FIELD]


# ------------------------------------------------------------------ гейт: открытая запись без долга

def _gate_core20(tmp_path, rows):
    docs = _docs(tmp_path, rows, eol="\n", bom=False)
    (tmp_path / "open-questions.md").write_text(
        "# Журнал\n\n## OQ-004 — 2026-11-01 — длина\n\n- Статус: открыт\n", encoding="utf-8")
    g = tg.Gate()
    tg.check_transfer_conditions(g, tmp_path, docs, docs)
    return [(m, t) for m, c, _k, t in g.lines if c == "CORE-20" and "без долга" in t]


def test_gate_open_question_whose_debt_closed_is_blocker_before_and_after_prune(tmp_path):
    # долг закрыт припиской, запись журнала открыта: гейт показывает открытый вопрос без долга
    # и до чистки, и после неё — вердикт чистка не меняет
    before = _gate_core20(tmp_path / "a", [OPEN_FIELD, CLOSED_SUFFIX])
    assert before and before[0][0] == "✗" and "OQ-004" in before[0][1], before
    after = _gate_core20(tmp_path / "b", [OPEN_FIELD])
    assert after == before


# ------------------------------------------------------------------ ожидатель после чистки

def _awaiter_kit(tmp_path, rows):
    docs = _docs(tmp_path, rows, eol="\n", bom=False)
    (docs / "srs/f1.md").write_text(
        "---\nid: FUN-001\ntitle: 'Первая функция'\n---\n# Ф1\n\n"
        "Шаг: «Вторая функция» — нет целевого артефакта function «Вторая функция».\n",
        encoding="utf-8")
    m = docs / "traceability-matrix.md"
    return m, docs


def test_awaiter_named_before_and_after_prune(tmp_path):
    m, docs = _awaiter_kit(tmp_path, [CLOSED_BARE])
    rep1, _ = ld.check(m, docs)
    assert any("srs/f1.md:7" in r and "долг закрыт, формула осталась" in r for r in rep1), rep1
    ld.prune_closed(m, write=True)
    rep2, _ = ld.check(m, docs)
    # карточки больше нет ни в одном FROM — сторож ожидателя без строки долга называет
    # карточку и формулу
    assert any(r.startswith("⚠ ожидатель долга без строки долга: srs/f1.md (FUN-001)")
               and "«нет целевого артефакта» ×1" in r for r in rep2), rep2


def test_awaiter_named_by_pair_after_prune_when_card_in_other_row(tmp_path):
    m, docs = _awaiter_kit(tmp_path / "p", [CLOSED_BARE, OPEN_PLAN])
    ld.prune_closed(m, write=True)
    rep, _ = ld.check(m, docs)
    assert any("формула-ожидатель без пары" in r and "srs/f1.md:7" in r
               and "«нет целевого артефакта»" in r for r in rep), rep
