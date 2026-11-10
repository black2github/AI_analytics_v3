# tests/test_link_debts_awaiters_by_pair.py
"""Ожидатель долга по паре «карточка, цель» (постановка 2026-11-10, п. 2; решение владельца 10.11
по трём развилкам): каждая формула AWAITER_FORMS в строке карточки сверяется с именами строк долга,
где эта карточка в FROM. Окно — строка карточки. Пары нет — одна ⚠ на формулу с классом лечения:
дописать в FROM / долг закрыт, формула осталась / строки долга нет / формула без дословного имени
цели. Прежняя строка по карточке (ID нет ни в одном FROM) сохраняется и здесь не повторяется."""
from pathlib import Path

from app.scripts.CI.link_debts import awaiters_by_pair, check

CRM = ("- Роли (см. «[ЦРМ] Ролевая модель клиента» (нет целевого артефакта platform-function — "
       "требуется заход create-platform-function)).\n")
ROW_OWN_OTHER = ("| FUN-001 | — | нет целевого артефакта function «Иная функция» — требуется заход "
                 "create-function |\n")
ROW_OWN_CRM = ("| FUN-001 | — | нет целевого артефакта platform-function «[ЦРМ] Ролевая модель "
               "клиента» — требуется заход create-platform-function |\n")
ROW_FUN2_CRM = ROW_OWN_CRM.replace("| FUN-001 |", "| FUN-002 |")
ROW_OWN_CLOSED_CRM = ("| FUN-001 | RBAC-001 | закрыт 2026-11-08: «[ЦРМ] Ролевая модель клиента» — "
                      "[RBAC-001](srs/rbac.md) |\n")


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def kit(tmp_path: Path, body: str, rows: str, readme: str = "") -> Path:
    docs = tmp_path / "docs"
    make(docs / "srs/function/fun-001.md", f"---\nid: FUN-001\ntitle: 'Ф1'\n---\n# Ф1\n\n{body}")
    make(docs / "srs/function/fun-002.md", "---\nid: FUN-002\ntitle: 'Ф2'\n---\n# Ф2\n\nтекст\n")
    reg = ("| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
           "| FUN-001 | function | Ф1 | srs/function/fun-001.md |\n"
           "| FUN-002 | function | Ф2 | srs/function/fun-002.md |\n")
    if readme:
        make(docs / "srs/function/README.md", readme)
        reg += "| FUN-000 | function | Реестр | srs/function/README.md |\n"
    make(docs / "traceability-matrix.md", "# М\n\n## 1. Реестр ID\n\n" + reg
         + "\n## 4. Долги по ссылкам\n\n| FROM-ID | Цель | Долг |\n|---|---|---|\n" + rows)
    return docs


def pair_lines(docs: Path):
    report, _ok = check(docs / "traceability-matrix.md", docs)
    return [ln for ln in report if ln.startswith("⚠ формула-ожидатель без пары")]


def test_warning_does_not_change_verdict(tmp_path):
    # те же строки долга: карточка с формулой без пары и без формулы — вердикт одинаков
    with_f = kit(tmp_path / "a", CRM, ROW_OWN_OTHER)
    without = kit(tmp_path / "b", "текст\n", ROW_OWN_OTHER)
    rep_a, ok_a = check(with_f / "traceability-matrix.md", with_f)
    rep_b, ok_b = check(without / "traceability-matrix.md", without)
    assert ok_a == ok_b
    assert any(ln.startswith("⚠ формула-ожидатель без пары") for ln in rep_a)
    assert not any(ln.startswith("⚠ формула-ожидатель без пары") for ln in rep_b)


def test_pair_in_line_silent(tmp_path):
    # НЕсрабатывание: в строке карточки имя открытой строки долга с этой карточкой в FROM
    docs = kit(tmp_path, CRM, ROW_OWN_CRM + ROW_OWN_OTHER)
    assert pair_lines(docs) == []


def test_class_add_to_from(tmp_path):
    # цель в открытой строке долга, где карточки нет в FROM (у карточки строка по иной цели)
    docs = kit(tmp_path, CRM, ROW_OWN_OTHER + ROW_FUN2_CRM)
    out = pair_lines(docs)
    assert len(out) == 1 and "srs/function/fun-001.md:7 (FUN-001)" in out[0]
    assert "дописать карточку в FROM строки долга" in out[0]


def test_class_closed_formula_left(tmp_path):
    docs = kit(tmp_path, CRM, ROW_OWN_CLOSED_CRM)
    out = pair_lines(docs)
    assert len(out) == 1 and "долг закрыт, формула осталась" in out[0] and "RBAC-001" in out[0]


def test_class_no_debt_row(tmp_path):
    docs = kit(tmp_path, CRM, ROW_OWN_OTHER)
    out = pair_lines(docs)
    assert len(out) == 1 and "строки долга по цели нет" in out[0]


def test_class_formula_without_name(tmp_path):
    body = ("Выполняется обращение к Сервису печати (нет целевого артефакта contract-call — "
            "требуется заход create-contract-call).\n")
    docs = kit(tmp_path, body, ROW_OWN_OTHER)
    out = pair_lines(docs)
    assert len(out) == 1 and "формула без дословного имени цели" in out[0]


def test_name_on_neighbour_line_is_not_a_pair(tmp_path):
    # окно — строка карточки: имя строки долга в соседней строке пары не даёт
    body = "Проверка «[ЦРМ] Ролевая модель клиента»:\n" + CRM.replace("«[ЦРМ] Ролевая модель клиента»", "роли")
    docs = kit(tmp_path, body, ROW_OWN_CRM)
    out = pair_lines(docs)
    assert len(out) == 1 and "формула без дословного имени цели" in out[0]


def test_short_own_name_pairs(tmp_path):
    # имя строки с этой карточкой в FROM — любой длины (КК FUN-CL-61 «ОТАР»)
    body = "ОТАР (нет целевого артефакта внешний документ «ОТАР» — внешняя ссылка в тело не переносится)\n"
    row = "| FUN-001 | — | нет целевого артефакта внешний документ «ОТАР» — внешняя ссылка |\n"
    docs = kit(tmp_path, body, row)
    assert pair_lines(docs) == []


def test_code_comment_and_readme_ignored(tmp_path):
    body = (f"```markdown\n{CRM}```\n\n<!-- {CRM.strip()} -->\n")
    readme = f"| ID | Файл |\n|---|---|\n| FUN-001 | {CRM.strip()} |\n"
    docs = kit(tmp_path, body, ROW_OWN_OTHER, readme=readme)
    assert pair_lines(docs) == []


def test_card_without_any_row_left_to_old_guard(tmp_path):
    # частный случай: ID карточки нет ни в одном FROM — строка прежнего сторожа, здесь тихо
    docs = kit(tmp_path, CRM, ROW_FUN2_CRM.replace("FUN-002", "FUN-009"))
    report, _ok = check(docs / "traceability-matrix.md", docs)
    assert any(ln.startswith("⚠ ожидатель долга без строки долга") for ln in report)
    assert not [ln for ln in report if ln.startswith("⚠ формула-ожидатель без пары")]


def test_summary_line_counts(tmp_path):
    body = CRM + ("Выполняется обращение к Сервису печати (нет целевого артефакта contract-call — "
                  "требуется заход create-contract-call).\n")
    docs = kit(tmp_path, body, ROW_OWN_OTHER + ROW_FUN2_CRM)
    out = awaiters_by_pair((docs / "traceability-matrix.md").read_text(encoding="utf-8"), docs,
                           {"FUN-001": ("function", "srs/function/fun-001.md"),
                            "FUN-002": ("function", "srs/function/fun-002.md")})
    assert out[-1].startswith("формул-ожидателей без пары «карточка, цель» 2 в 1 карточках")
    assert "дописать в FROM 1" in out[-1] and "без имени цели 1" in out[-1]
