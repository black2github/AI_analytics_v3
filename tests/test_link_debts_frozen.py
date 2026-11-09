# tests/test_link_debts_frozen.py
"""Вид долга формы 1 на замороженную цель (постановка 2026-11-09, П-9; прецедент КК PRN-15):
«нет целевого артефакта <тип> «<имя>» — frozen (<задача>), вне SRS по профилю»."""
from pathlib import Path

from app.scripts.CI.link_debts import check

NAME = "[КК_B2B] Клиент: Функция экспорта списка заявок на B2B перевод"


def kit(tmp_path: Path, tail: str, body: str = f"Вызов {NAME}.\n") -> Path:
    docs = tmp_path / "docs"
    (docs / "srs/print-form").mkdir(parents=True)
    (docs / "srs/print-form/prn-15.md").write_text(f"---\nid: PRN-15\ntitle: 'П'\n---\n# П\n\n{body}",
                                                    encoding="utf-8")
    (docs / "traceability-matrix.md").write_text(
        "# М\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
        "| PRN-15 | print-form | П | srs/print-form/prn-15.md |\n\n## 4. Долги по ссылкам\n\n"
        "| FROM | Цель | Долг |\n|---|---|---|\n"
        f"| PRN-15 | — | нет целевого артефакта function «{NAME}» — {tail} |\n", encoding="utf-8")
    return docs


def _run(docs):
    return check(docs / "traceability-matrix.md", docs)


def test_frozen_debt_counted_without_warning(tmp_path):
    report, ok = _run(kit(tmp_path, "frozen (GBO-50272), вне SRS по профилю"))
    assert ok, report
    line = [ln for ln in report if ln.startswith("долгов на замороженную цель 1")]
    assert line and "GBO-50272" in line[0], report
    assert not any(ln.startswith("⚠") and "frozen" in ln for ln in report), report


def test_frozen_without_task_warned(tmp_path):
    report, ok = _run(kit(tmp_path, "frozen, вне SRS"))
    assert ok and any("«frozen» без задачи" in ln for ln in report), report


def test_frozen_with_visit_warned(tmp_path):
    report, _ok = _run(kit(tmp_path, "frozen (GBO-1), требуется заход create-function"))
    assert any("«frozen» и «требуется заход»" in ln for ln in report), report


def test_regular_debt_not_frozen(tmp_path):
    # НЕсрабатывание: обычный долг формы 1 к замороженным не относится
    report, _ok = _run(kit(tmp_path, "требуется заход create-function"))
    assert not any("замороженную цель" in ln or "frozen" in ln for ln in report), report


def test_frozen_debt_still_checked_for_verbatim_name(tmp_path):
    # исполнимость как у формы 1: имени в карточке нет — ✗
    report, ok = _run(kit(tmp_path, "frozen (GBO-50272)", body="Другой текст.\n"))
    assert not ok and any("НЕИСПОЛНИМ" in ln for ln in report), report
