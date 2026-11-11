# tests/test_card_deviation.py
"""Заметка о санкционированном отклонении снимает названные шаг, раздел и строку таблицы
источника из сверки (решение владельца 2026-11-11, card_deviation). Вырезка — из текста
источника группы до всех сверок; абзац заметки — из текстов карточек; всё снятое печатается;
группа без ✗ — ⚠ (вердикт прежний), гейт переносит строку предупреждением."""
import sys
from pathlib import Path

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.checks.card_deviation import (
    DEVIATION_PREFIX, apply_notes, blank_notes, find_notes, parse_note)

LIT = "Недостаточно полномочий для использования сервиса."
SRC = ("---\ntitle: 'Метод'\nconfluence_page_id: '555000'\n---\n\n"
       "# Описание\n\n"
       "<table>\n<tbody>\n<tr>\n<td><strong>Назначение</strong></td>\n<td>Получение списка</td>\n</tr>\n"
       "<tr>\n<td><p><strong>Привилегии</strong></p></td>\n"
       "<td><p>Нужна привилегия [КК_ВК] Клиент: Функция выпуска «Выпуск»</p></td>\n</tr>\n"
       "</tbody>\n</table>\n\n"
       "# Права\n\nТекст раздела «Право доступа».\n\n"
       "# Процесс\n\n"
       f"**Шаг 0:** (проверка прав)\n\nЕсли прав нет, то ошибка \"{LIT}\" и переход на шаг 3.\n\n"
       "**Шаг 1:** Запрос «Список».\n\n"
       "**Шаг 2:** Ответ «Готово».\n\n"
       "**Шаг 3.** Возврат ошибки.\n")
NOTE = ("Не перенесено как санкционированное отклонение, решение владельца канона 2026-11-11: "
        "шаг 0. Шаг проверки прав относится к другому методу.")


def _apply(note: str, card_steps=None):
    return apply_notes(SRC, [("fun.md", "# Т\n\n" + note + "\n")], card_steps)


# ---------------------------------------------------------------- разбор заметки

def test_parse_forms_and_dates():
    assert parse_note(NOTE) == ("2026-11-11", [("шаг", "0", "шаг 0")])
    d, els = parse_note("Не перенесено как санкционированное отклонение, решение владельца "
                        "11.11.2026: шаги 0, 2; раздел «Права»; строка «Привилегии». Почему: …")
    assert d == "11.11.2026"
    assert els == [("шаг", "0", "шаги 0, 2"), ("шаг", "2", "шаги 0, 2"),
                   ("раздел", "Права", "раздел «Права»"), ("строка", "Привилегии", "строка «Привилегии»")]
    assert parse_note("Не перенесено как санкционированное отклонение, решение 2026-11-11: шаг №1.2.")[1] \
        == [("шаг", "1.2", "шаг №1.2")]


def test_note_without_list_date_or_decision_removes_nothing():
    for bad in ("Не перенесено как санкционированное отклонение, решение владельца 2026-11-11. Почему: …",
                "Не перенесено как санкционированное отклонение, решение владельца: шаг 0.",
                "Не перенесено как санкционированное отклонение владельца 2026-11-11: шаг 0.",
                "Не перенесено как санкционированное отклонение, решение 2026-11-11: шаг 0; что-то ещё."):
        src, rep, cut = _apply(bad)
        assert src == SRC and not cut, bad
        assert len(rep) == 1 and "заметка об отклонении без перечня — из сверки ничего не снято" in rep[0], rep


def test_corrected_note_not_read():
    note = ("Колонка «Тип»: пробел между «string» и «Строка» — исправлено как санкционированное "
            "отклонение, решение владельца канона 2026-11-11.")
    assert find_notes([("c.md", note)]) == ([], [])
    assert blank_notes(note) == note


def test_note_in_code_block_ignored():
    assert find_notes([("c.md", "```\n" + NOTE + "\n```\n")]) == ([], [])


# ---------------------------------------------------------------- вырезка

def test_step_removed_lines_kept_and_counted():
    src, rep, cut = _apply(NOTE)
    assert cut and src.count("\n") == SRC.count("\n")
    assert "Шаг 0" not in src and LIT not in src and "**Шаг 1:**" in src
    assert rep == [f"{DEVIATION_PREFIX} (решение 2026-11-11, fun.md): снято из сверки — шаг 0 "
                   "(строк источника 2); исключено литералов 1, теговых упоминаний 0"], rep


def test_section_and_row_removed():
    note = ("Не перенесено как санкционированное отклонение, решение владельца 11.11.2026: "
            "раздел «Права»; строка «Привилегии». Почему: другой метод.")
    src, rep, cut = _apply(note)
    assert cut and src.count("\n") == SRC.count("\n")
    assert "Право доступа" not in src and "# Права" not in src and "# Процесс" in src
    assert "Привилегии" not in src and "Назначение" in src and "<table>" in src
    assert "раздел «Права» (строк источника 2); строка «Привилегии» (строк источника 4)" in rep[0], rep
    assert "исключено литералов 2, теговых упоминаний 1" in rep[0], rep


def test_literal_also_outside_removed_stays():
    src0 = SRC.replace("Ответ «Готово».", f"Ответ «Готово», иначе \"{LIT}\".")
    src, rep, _cut = apply_notes(src0, [("fun.md", NOTE)], None)
    assert LIT in src
    assert "исключено литералов 0" in rep[0], rep


def test_missing_element_warns_nothing_cut():
    note = NOTE.replace("шаг 0.", "шаг 7; раздел «Нет такого».")
    src, rep, cut = _apply(note)
    assert src == SRC and not cut
    assert len(rep) == 2 and all("в источнике не найдено" in r for r in rep), rep


def test_step_present_in_card_stale_note():
    src, rep, cut = _apply(NOTE, card_steps={"0", "1"})
    assert src == SRC and not cut
    assert "шаг 0 есть в карточке — заметка устарела" in rep[0], rep


def test_blank_notes_keeps_lines():
    text = "# Т\n\n- **Шаг 1:** x\n\n" + NOTE + "\n\nхвост\n"
    out = blank_notes(text)
    assert out.count("\n") == text.count("\n") and "санкционированное" not in out and "хвост" in out


# ---------------------------------------------------------------- selfcheck: знак группы, ИТОГО, вердикт

def _make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


CARD = ("---\nid: X-01\ntitle: 'Метод'\ntype: function\nconfluence_page_ids: [555000]\n---\n\n"
        "# X-01. Метод\n\n## Поведение\n\n"
        "- **Шаг 1:** Запрос «Список».\n"
        "- **Шаг 2:** Ответ «Готово».\n"
        "- **Шаг 3.** Возврат ошибки.\n\n"
        "Привилегии и разделы паспорта — в README.\n\n{note}\n")
SRC_KIT = SRC.replace("<td><p>Нужна привилегия [КК_ВК] Клиент: Функция выпуска «Выпуск»</p></td>",
                      "<td><p>Нужна привилегия</p></td>").replace(
    "# Права\n\nТекст раздела «Право доступа».\n\n", "")


def _kit(tmp_path: Path, note: str, src: str = None):
    src = SRC_KIT if src is None else src
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    _make(docs / "srs/function/f.md", CARD.replace("{note}", note))
    _make(docs / "traceability-matrix.md", "# Матрица\n\n| ID | Тип | Наименование | Файл |\n"
          "|---|---|---|---|\n| X-01 | function | Метод | f.md |\n")
    _make(srcs / "метод.md", src)
    return selfcheck.run(docs, srcs)


def test_selfcheck_group_with_removal_is_warning_verdict_ok(tmp_path):
    report, ok = _kit(tmp_path, NOTE)
    grp = [ln for ln in report if "srs" in ln and "← метод.md" in ln]
    assert grp and grp[0].startswith("⚠ "), report
    assert any(ln.strip().startswith(DEVIATION_PREFIX) and "шаг 0" in ln for ln in report), report
    total = next(ln for ln in report if ln.startswith("ИТОГО"))
    # двойник без снятия (шага 0 в источнике нет, заметки нет): группа ✓ — разница ровно в ⚠ группы
    step0 = f"**Шаг 0:** (проверка прав)\n\nЕсли прав нет, то ошибка \"{LIT}\" и переход на шаг 3.\n\n"
    assert step0 in SRC_KIT
    twin, twin_ok = _kit(tmp_path / "twin", "", SRC_KIT.replace(step0, ""))
    t_total = next(ln for ln in twin if ln.startswith("ИТОГО"))
    assert twin_ok and any(ln.startswith("✓ ") and "← метод.md" in ln for ln in twin), twin
    assert "✓ 1, ✗ 0, ⚠ 1" in t_total and "✓ 0, ✗ 0, ⚠ 2" in total and "вердикт: OK" in total, (t_total, total)
    assert ok


def test_selfcheck_without_note_fails_and_note_text_does_not_rescue(tmp_path):
    # заметка без перечня: ничего не снято, а её «шаг 0» и цитата не закрывают потерю
    note = NOTE.replace("2026-11-11: шаг 0.", "2026-11-11. шаг 0") + f" Литерал «{LIT}»."
    report, ok = _kit(tmp_path, note)
    assert not ok, report
    assert any(ln.startswith("✗ ") and "← метод.md" in ln for ln in report), report


def test_selfcheck_step_mention_outside_note_keeps_defect_by_literal(tmp_path):
    # заметки нет, «переход на шаг 0» в карточке есть (К-23 его засчитывает) — ✗ держит литерал
    report, ok = _kit(tmp_path, "Переход на шаг 0 — в другом методе.")
    assert not ok
    assert any("кавычечные литералы" in ln and "✗" in ln for ln in report), report


# ---------------------------------------------------------------- гейт

def test_gate_carries_removal_as_warning(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
    import transfer_gate as tg

    line = f"{DEVIATION_PREFIX} (решение 2026-11-11, f.md): снято из сверки — шаг 0 (строк источника 2)"

    def fake_run(staged, sources, **kw):
        return [f"⚠ srs/function/f.md ← метод.md", f"   {line}",
                "✗ srs/function/g.md ← другой.md", f"   {line}", "   причина ✗",
                "ИТОГО: файлов 2 — ✓ 0, ✗ 1, ⚠ 1; вердикт: БРАК"], False

    monkeypatch.setattr(tg.sc, "run", fake_run)
    gate = tg.Gate()
    tg.run_selfcheck(gate, Path("."), None, strict=False)
    dev = [x for x in gate.lines if x[2] == "санкционированное отклонение"]
    assert len(dev) == 2 and all(x[0] == "⚠" and x[3] == line for x in dev), gate.lines
    assert gate.blockers == 2   # ✗ группы и вердикт прибора; ⚠ блокером не считается
