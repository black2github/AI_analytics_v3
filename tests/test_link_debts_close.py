# tests/test_link_debts_close.py
"""Закрытие долга без цели режимом link_debts --close (постановка 2026-11-09, П-4) и ссылка на
карточку комплекта в поле «источник:»."""
import subprocess
import sys
from pathlib import Path

from app.scripts.CI.link_debts import check, close_debt, issue_closed, issue_fields

ROW_A = ("| FUN-SYS-37, FUN-SYS-38 | — | долг открытый вопрос: «страницы расходятся в типах» — причина: "
         "две страницы; ответственный: аналитик; ограничение: типы параметров; закрытие: решение "
         "аналитика; источник: OQ-380 |")
ROW_B = ("| CTL-417 | — | долг открытый вопрос: «длина реквизита не задана» — причина: нет длины; "
         "ответственный: аналитик; ограничение: контроль длины; закрытие: длина в модели; "
         "источник: OQ-381 |")
ROW_F1 = "| FUN-SYS-39 | — | нет целевого артефакта function «Иная функция» — требуется заход create-function |"
HEAD = "# М\r\n\r\n## 4. Долги по ссылкам\r\n\r\n| FROM-ID | Цель | Долг |\r\n|---|---|---|\r\n"


def matrix(tmp_path: Path, rows, bom: bool = False, eol: str = "\r\n") -> Path:
    text = (HEAD + "".join(r + "\r\n" for r in rows) + "\r\nабзац после таблицы\r\n").replace("\r\n", eol)
    p = tmp_path / "traceability-matrix.md"
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    return p


def test_close_appends_suffix_and_keeps_other_bytes(tmp_path):
    p = matrix(tmp_path, [ROW_A, ROW_B], bom=True)
    before = p.read_bytes()
    rep, ok = close_debt(p, "CTL-417", "src/TEAMTB-1", targets=["CTL-417"], day="2026-11-09")
    assert ok, rep
    after = p.read_bytes()
    assert after.startswith(b"\xef\xbb\xbf")
    new_row = ROW_B[:-2] + "; закрыт: 2026-11-09, src/TEAMTB-1, затронуто: CTL-417 |"
    assert after == before.replace(ROW_B.encode("utf-8"), new_row.encode("utf-8"))
    assert after.count(b"\r\n") == before.count(b"\r\n")
    assert issue_closed(new_row) == "2026-11-09, src/TEAMTB-1, затронуто: CTL-417"


def test_close_is_idempotent(tmp_path):
    p = matrix(tmp_path, [ROW_A])
    close_debt(p, "FUN-SYS-38", "abc1234", day="2026-11-09")
    once = p.read_bytes()
    rep, ok = close_debt(p, "FUN-SYS-38", "abc1234", day="2026-11-10")
    assert ok and "уже закрыт" in rep[0]
    assert p.read_bytes() == once


def test_statement_verbatim_checked(tmp_path):
    p = matrix(tmp_path, [ROW_A])
    before = p.read_bytes()
    rep, ok = close_debt(p, "FUN-SYS-37", "abc", statement="страницы расходятся в типе")
    assert not ok and "не совпадает дословно" in rep[0], rep
    assert "«страницы расходятся в типах»" in rep[1]
    assert p.read_bytes() == before
    rep, ok = close_debt(p, "FUN-SYS-37", "abc", statement="«страницы расходятся в типах»",
                         day="2026-11-09")
    assert ok, rep


def test_statement_with_nested_quotes(tmp_path):
    # разбор обрезает формулировку на первой «»», дословная сверка — по вхождению целиком
    row = ROW_A.replace("«страницы расходятся в типах»", "«кнопки B-1: после «==» код пуст»")
    p = matrix(tmp_path, [row])
    assert not close_debt(p, "FUN-SYS-37", "abc", statement="кнопки B-1: после «==» код")[1]
    rep, ok = close_debt(p, "FUN-SYS-37", "abc", statement="кнопки B-1: после «==» код пуст",
                         day="2026-11-09")
    assert ok, rep


def test_several_candidates_refused(tmp_path):
    row2 = ROW_B.replace("CTL-417", "FUN-SYS-37")
    p = matrix(tmp_path, [ROW_A, row2])
    rep, ok = close_debt(p, "FUN-SYS-37", "abc")
    assert not ok and "несколько (2)" in rep[0], rep
    rep, ok = close_debt(p, "FUN-SYS-37", "abc", line_no=8, day="2026-11-09")
    assert ok, rep
    assert "закрыт: 2026-11-09" in p.read_text(encoding="utf-8").splitlines()[7]


def test_form1_debt_not_closed_by_append(tmp_path):
    p = matrix(tmp_path, [ROW_F1])
    before = p.read_bytes()
    rep, ok = close_debt(p, "FUN-SYS-39", "abc")
    assert not ok and "ID цели во второй колонке" in rep[0], rep
    assert p.read_bytes() == before


def test_missing_row_and_pipe_refused(tmp_path):
    p = matrix(tmp_path, [ROW_A], eol="\n")
    before = p.read_bytes()
    assert not close_debt(p, "CTL-999", "abc")[1]
    assert not close_debt(p, "FUN-SYS-37", "a | b")[1]
    assert p.read_bytes() == before


def test_lf_file_stays_lf(tmp_path):
    p = matrix(tmp_path, [ROW_A], eol="\n")
    close_debt(p, "FUN-SYS-37", "abc", day="2026-11-09")
    assert b"\r\n" not in p.read_bytes()


def test_cli_close(tmp_path):
    p = matrix(tmp_path, [ROW_A])
    script = Path(__file__).resolve().parents[1] / "app/scripts/CI/link_debts.py"
    r = subprocess.run([sys.executable, str(script), "--matrix", str(p), "--docs", str(tmp_path),
                        "--close", "FUN-SYS-37", "--by", "src/X-1", "--date", "2026-11-09"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "закрыт: 2026-11-09, src/X-1" in p.read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(script), "--matrix", str(p), "--docs", str(tmp_path),
                        "--close", "CTL-999", "--by", "x"], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 2


# ---------------------------------------------------------------- «источник:» — ссылка на карточку

def test_source_card_link_accepted():
    for src in ("[RBAC-001 Ролевая модель](srs/rbac.md#2-ролевая-модель-банка)", "rbac.md#2",
                "srs/rbac.md"):
        row = ROW_A.replace("источник: OQ-380", f"источник: {src}")
        f = issue_fields(row)
        assert f["source"] and not f["missing"], (src, f)


def test_source_free_text_still_missing():
    # НЕсрабатывание: свободный текст источником не считается
    row = ROW_A.replace("источник: OQ-380", "источник: устно на встрече")
    f = issue_fields(row)
    assert f["source"] is None
    assert "источник OQ-NNN, T-<JIRA-ID> или ссылка на карточку" in f["missing"]


def test_source_card_link_passes_check(tmp_path):
    docs = tmp_path / "docs"
    (docs / "srs").mkdir(parents=True)
    (docs / "srs/rbac.md").write_text("---\nid: RBAC-001\ntitle: 'Р'\n---\n# Р\n", encoding="utf-8")
    (docs / "traceability-matrix.md").write_text(
        "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
        "| RBAC-001 | rbac | Р | srs/rbac.md |\n\n## 4. Долги по ссылкам\n\n| FROM | Цель | Долг |\n"
        "|---|---|---|\n" + ROW_A.replace("FUN-SYS-37, FUN-SYS-38", "RBAC-001")
        .replace("источник: OQ-380", "источник: [RBAC-001](srs/rbac.md#2)") + "\n", encoding="utf-8")
    report, ok = check(docs / "traceability-matrix.md", docs)
    assert ok and not any("НЕПОЛОН" in ln for ln in report), report
