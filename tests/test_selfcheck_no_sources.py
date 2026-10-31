# tests/test_selfcheck_no_sources.py
"""Самопроверка комплекта без --sources (трек rules, срез 3): слой миграции выключен —
отчёт не говорит об источнике, которого нет, кроме одной сводной строки; ветвь с
--sources не меняется ни в одном пункте (срабатывание — прежние строки дословно)."""

import sys
from pathlib import Path

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.checks.card_run import check_file

SUFFIX = "без источника (page_ids нет — forward/реестр)"
SUMMARY = ("i карточек с происхождением из Confluence (confluence_page_ids): 1; выгрузки в "
           "репозитории нет — сверка с источником: selfcheck.py --sources <архив src-<service-id>>")
UNPARSED = ("confluence_page_ids задан, но id не распознаны — ключ сопоставления по странице не "
            "читается (сверка с источником и дельты по page id карточку не найдут); формат по "
            "шаблону: inline-список")


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid: str, title: str, pid_line: str = "", body: str = "текст\n") -> str:
    return (f"---\nid: {cid}\ntitle: '{title}'\ntype: function\n{pid_line}---\n\n# Т\n\n" + body)


def kit(tmp_path: Path, empty_pids: bool = False):
    """Комплект: карточка без page_ids, карточка с page_id, (по флагу) карточка с пустым
    полем; выгрузка — одна страница для карточки с page_id."""
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("X-01", "[X] Ф1"))
    make(docs / "srs/functions/f2.md", card("X-02", "[X] Ф2", "confluence_page_ids: [111222]\n"))
    ids = "| X-01 | function | Ф1 | f1.md |\n| X-02 | function | Ф2 | f2.md |\n"
    if empty_pids:
        make(docs / "srs/functions/f3.md", card("X-03", "[X] Ф3", "confluence_page_ids: []\n"))
        ids += "| X-03 | function | Ф3 | f3.md |\n"
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n" + ids)
    make(srcs / "стр2.md", "---\ntitle: '[X] Ф2'\nconfluence_page_id: '111222'\n---\n\nтекст\n")
    return docs, srcs


def run_main(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["selfcheck.py", *map(str, args)])
    rc = selfcheck.main()
    return rc, capsys.readouterr().out


# --- п. 1–2: суффикс и Р-2 (б) ---

def test_no_sources_no_suffix_no_unsourced_lines_one_summary(tmp_path, monkeypatch, capsys):
    docs, _srcs = kit(tmp_path)
    out = tmp_path / "rep.txt"
    rc, console = run_main(monkeypatch, capsys, "--docs", docs, "--out", out)
    rep = out.read_text(encoding="utf-8").splitlines()
    assert f"# ✓ {Path('srs/functions/f1.md')}" in rep
    assert f"# ✓ {Path('srs/functions/f2.md')}" in rep
    assert not any(SUFFIX in ln for ln in rep)
    assert not any("не сверялся" in ln for ln in rep)
    assert sum("с происхождением из Confluence" in ln for ln in rep) == 1
    assert f"# {SUMMARY}" in rep
    # перечень — только в --out (OUT_ONLY), в консоли одна сводная строка
    assert f"# {selfcheck.OUT_ONLY}srs/functions/f2.md: page_id 111222" in rep
    assert "page_id 111222" not in console and SUMMARY in console
    assert rc == 0


def test_no_sources_summary_silent_without_page_ids(tmp_path):
    # НЕсрабатывание: карточек с page_ids нет — сводной строки нет (эталон канона)
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("X-01", "[X] Ф1"))
    make(docs / "traceability-matrix.md", "# Матрица\n\n| ID | Тип | Наименование | Файл |\n"
         "|---|---|---|---|\n| X-01 | function | Ф1 | f1.md |\n")
    report, ok = selfcheck.run(docs, None)
    assert ok, report
    assert not any("с происхождением из Confluence" in ln for ln in report)


def test_with_sources_old_lines_verbatim(tmp_path):
    # срабатывание ветви с источником: суффикс у карточки без page_ids, группа по
    # странице, сводной строки нет
    docs, srcs = kit(tmp_path)
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report
    f1 = Path("srs/functions/f1.md")
    assert f"✓ {f1}: {SUFFIX}" in report
    assert any(ln.startswith("✓") and "f2.md ← стр2.md" in ln for ln in report)
    assert not any("с происхождением из Confluence" in ln for ln in report)


def test_with_sources_page_not_in_export_still_defect(tmp_path):
    # ветвь с источником не тронута: page_id вне выгрузки — ✗ как прежде
    docs, srcs = kit(tmp_path)
    (srcs / "стр2.md").unlink()
    make(srcs / "другая.md", "---\ntitle: 'Д'\nconfluence_page_id: '999'\n---\n\nтекст\n")
    report, ok = selfcheck.run(docs, srcs)
    assert not ok
    assert any("источник page_id 111222 НЕ НАЙДЕН" in ln for ln in report)


def test_solo_defect_line_without_and_with_sources(tmp_path):
    docs, srcs = kit(tmp_path)
    make(docs / "srs/functions/f1.md", card("X-01", "[X] Ф1", body="текст заявкаID\n"))
    bad = next(ln for ln in selfcheck.run(docs, None)[0] if "f1.md" in ln)
    assert bad == f"✗ {Path('srs/functions/f1.md')}: брак внутренних сторожей (причины ниже)"
    bad = next(ln for ln in selfcheck.run(docs, srcs)[0] if "f1.md" in ln)
    assert bad.endswith(f"брак внутренних сторожей (причины ниже); {SUFFIX}")


# --- п. 3: ключ задан, id не распознаны ---

def test_unparsed_page_ids_defect_neutral_text_both_modes(tmp_path, monkeypatch, capsys):
    docs, srcs = kit(tmp_path, empty_pids=True)
    for extra in ([], ["--sources", srcs]):
        rc, console = run_main(monkeypatch, capsys, "--docs", docs, *extra)
        line = next(ln for ln in console.splitlines() if "f3.md" in ln)
        assert line == f"# ✗ {Path('srs/functions/f3.md')}: {UNPARSED}"
        assert "выпала бы" not in console
        assert rc == 2
    # пустое поле — не карточка «из Confluence»: в сводную строку не входит
    report, _ok = selfcheck.run(docs, None)
    assert f"{SUMMARY}" in report


# --- п. 4: сверка сообщений карточек контролей ---

CTL = ("---\ntype: control\nentity: ENT-001\n---\n\n# К\n\n### CTL-001. Фамилия: Проверка\n\n"
       "| Параметр | Значение |\n|---|---|\n| Логика | Если указано, то пройдена |\n"
       "| Сообщение | «Укажите» |\n")


def test_control_messages_line_silent_without_sources(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/control/cards-a.md", CTL)
    ctx = selfcheck._KitCtx(docs=docs, sources=None, strict=False, catalog=None, card_ids={},
                            card_titles={}, fm_schema_issues=[], groups={}, idx={})
    assert selfcheck._kc_message_attribution_unchecked(ctx) == ([], True)


def test_control_messages_line_with_sources_page_not_given(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/control/cards-a.md", CTL)
    ctx = selfcheck._KitCtx(docs=docs, sources=tmp_path / "conf", strict=False, catalog=None,
                            card_ids={}, card_titles={}, fm_schema_issues=[], groups={}, idx={})
    rep, ok = selfcheck._kc_message_attribution_unchecked(ctx)
    assert ok and rep == ["i сверка сообщений карточек контролей с источником не выполнена: "
                          "1 файлов (страница не указана ×1)",
                          f"{selfcheck.OUT_ONLY}srs/control/cards-a.md: страница не указана"]


# --- п. 5: маркер сокращения ---

MARKER_OLD = ("предупреждение: маркер сокращения «и т.д.» ×1 — проверьте, что справочники и "
              "перечни источника перенесены целиком")
MARKER_NEW = "предупреждение: маркер сокращения «и т.д.» ×1 — проверьте, что перечень приведён целиком"


def test_shortening_marker_text_by_mode(tmp_path):
    docs, srcs = kit(tmp_path)
    make(docs / "srs/functions/f1.md", card("X-01", "[X] Ф1", body="коды: 01, 02 и т.д.\n"))
    no_src = selfcheck.run(docs, None)[0]
    with_src = selfcheck.run(docs, srcs)[0]
    assert any(MARKER_NEW in ln for ln in no_src)
    assert not any("перенесены целиком" in ln for ln in no_src)
    assert any(MARKER_OLD in ln for ln in with_src)
    assert not any("приведён целиком" in ln for ln in with_src)


def test_shortening_marker_check_cli_default_old_text(tmp_path):
    # режим --check (normalize_tables) без источника — прежняя формулировка: флаг
    # прогона без выгрузки выставляет только selfcheck
    p = tmp_path / "f.md"
    make(p, card("X-01", "[X] Ф1", body="коды: 01, 02 и т.д.\n"))
    rep, _ok = check_file(p, soft_markers=True)
    assert MARKER_OLD in rep
    rep, _ok = check_file(p, soft_markers=True, without_sources=True)
    assert MARKER_NEW in rep
