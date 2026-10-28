# tests/test_transfer_gate_after_step.py
"""Д-49 (2026-10-23): гейт переноса в лёгком режиме --after-step и дельта --baseline; строка
статуса OQ в двух формах; мини-комплект зоны modules/ в целевой раскладке. Каждое понижение —
пара тестов (полный режим — прежний знак, --after-step — пониженный); НЕ понижаемый критерий —
✗ в обоих режимах."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
from tests.test_transfer_gate import _CARD, _MATRIX, _OQ_OPEN, _target, _w, make_src  # noqa: E402


def _run(src: Path, **kw):
    kw.setdefault("no_validator", True)
    return tg.run_gate(src, **kw)


def _line(lines, prefix):
    return next((l for l in lines if l.startswith(prefix)), None)


# ---------------------------------------------------------------- режим и вердикт

def test_after_step_skips_selfcheck_and_prints_form_verdict(tmp_path):
    lines, ready, data = _run(make_src(tmp_path), after_step=True)
    assert ready, "\n".join(lines)
    assert any(l == "i [ПРИБОР] selfcheck не гонялся (режим --after-step), вердикт прибора — в сдаче"
               for l in lines)
    assert not any("[ПРИБОР]" in l and "файлов" in l for l in lines)  # сводки selfcheck нет
    # предупреждения базового комплекта: каталог srs/function без README, валидатор отключён
    assert lines[-1] == "ИТОГ: ФОРМА ПЕРЕНОСИМА (новых —), предупреждений 2"
    assert data["verdict"] == "ФОРМА ПЕРЕНОСИМА" and data["after_step"] is True
    assert not any("READY" in l for l in lines)


def test_full_mode_verdict_unchanged(tmp_path):
    lines, ready, data = _run(make_src(tmp_path))
    assert lines[-1] == "ИТОГ: READY — блокеров 0, предупреждений 3" and data["verdict"] == "READY"


def test_after_step_out_rejected(tmp_path):
    out = _target(tmp_path)
    lines, ready, data = _run(make_src(tmp_path), after_step=True, out=out)
    assert not ready and not (out / "traceability-matrix.md").exists()
    assert lines[0].startswith("✗ [TRF-01] --out не применим в режиме --after-step")
    assert lines[-1] == "ИТОГ: ФОРМА НЕ ПЕРЕНОСИМА" and data["verdict"] == "ФОРМА НЕ ПЕРЕНОСИМА"


# ---------------------------------------------------------------- понижения: пары

def test_core20_open_questions_blocker_full_info_after_step(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path, oq=_OQ_OPEN))
    assert not ready and _line(lines, "✗ [CORE-20] открытые вопросы без долга в матрице: 1")
    lines, ready, _ = _run(make_src(tmp_path / "b", oq=_OQ_OPEN), after_step=True)
    assert ready, "\n".join(lines)
    ln = _line(lines, "i [CORE-20] открытые вопросы без долга в матрице: 1")
    assert ln and ln.endswith("(проверяется полным гейтом перед переносом)")


def test_core20_debt_reading_rule_not_downgraded(tmp_path):
    # CORE-20 «перенесённые долги» (правило чтения в README) — форма матрицы, не журнал:
    # остаётся ✗ и в лёгком режиме (закрытый список понижений)
    row = ("\n## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n"
           "| FUN-CL-01 | — | нет целевого артефакта data-model «Карта» у владельца cards — "
           "требуется заход create-data-model |\n")
    src = make_src(tmp_path, matrix=_MATRIX + row)
    _w(src / "docs/srs/function/f1.md", _CARD.replace("см.", "использует «Карта»; см."))
    lines, ready, _ = _run(src, after_step=True)
    assert not ready and _line(lines, "✗ [CORE-20] перенесённые долги: 1")


def test_sdlc05_warn_full_info_after_step(tmp_path):
    src = make_src(tmp_path)
    (src / "docs/glossary.md").unlink()
    lines, _r, _d = _run(src)
    assert _line(lines, "⚠ [SDLC-05] glossary.md отсутствует")
    lines, _r, _d = _run(src, after_step=True)
    assert _line(lines, "i [SDLC-05] glossary.md отсутствует") and not _line(lines, "⚠ [SDLC-05]")


def test_sdlc04_missing_section_blocker_full_warn_after_step(tmp_path):
    m = _MATRIX.split("## 3.")[0]
    lines, ready, _ = _run(make_src(tmp_path, matrix=m))
    assert not ready and _line(lines, "✗ [SDLC-04] раздела нет")
    lines, ready, _ = _run(make_src(tmp_path / "b", matrix=m), after_step=True)
    assert ready and _line(lines, "⚠ [SDLC-04] раздела нет")


def test_broken_relative_link_not_downgraded(tmp_path):
    # НЕсрабатывание понижения: TRF-03 и README комплекта — ✗ в обоих режимах
    src = make_src(tmp_path)
    _w(src / "docs/api/x-openapi.yaml", "openapi: 3.0.1\n")
    (src / "docs/README.md").unlink()
    for kw in ({}, {"after_step": True}):
        lines, ready, _ = _run(src, **kw)
        assert not ready
        assert _line(lines, "✗ [TRF-03] контракты в комплекте")
        assert _line(lines, "✗ [SDLC-08] README.md комплекта отсутствует")
    assert lines[-1].startswith("ИТОГ: ФОРМА НЕ ПЕРЕНОСИМА: блокеров 2 (новых —)")


def test_downgrade_closed_list_keeps_validator_sdlc04(tmp_path):
    g = tg.Gate()
    g.add("✗", "SDLC-04", "srs/x.md: нет строки трассировки", check="валидатор E_TRACEABILITY_MISSING")
    g.add("✗", "SDLC-04", "раздела нет", check="матрица: раздел «Покрытие: API ↔ SRS»")
    g.downgrade(tg._AFTER_STEP_DOWNGRADE, tg._AFTER_STEP_NOTE)
    assert [m for m, *_ in g.lines] == ["✗", "⚠"] and g.blockers == 1


# ---------------------------------------------------------------- --baseline

def _report(tmp_path, src, name, **kw):
    lines, ready, data = _run(src, fmt="table", **kw)
    path = tmp_path / name
    tg.write_report(path, src, lines, data)
    return path, lines


def test_baseline_same_blockers_new_zero(tmp_path):
    src = make_src(tmp_path)
    (src / "docs/README.md").unlink()
    base, _ = _report(tmp_path, src, "r1.md", after_step=True)
    lines, ready, data = _run(src, after_step=True, baseline=base)
    assert lines[-3] == "ИТОГ: ФОРМА НЕ ПЕРЕНОСИМА: блокеров 1 (новых 0), предупреждений 2"
    assert lines[-2] == "новых блокеров 0" and lines[-1] == "ушло 0 (относительно r1.md)"
    assert data["new_blockers"] == 0


def test_baseline_new_and_gone(tmp_path):
    src = make_src(tmp_path)
    (src / "docs/README.md").unlink()
    base, _ = _report(tmp_path, src, "r1.md", after_step=True)
    _w(src / "docs/README.md", "# К\n\n## Разделы\n")
    _w(src / "docs/api/x-openapi.yaml", "openapi: 3.0.1\n")
    lines, _r, data = _run(src, after_step=True, baseline=base)
    itog = _line(lines, "ИТОГ:")
    assert itog.startswith("ИТОГ: ФОРМА НЕ ПЕРЕНОСИМА: блокеров 1 (новых 1)"), itog
    assert _line(lines, "новых блокеров 1: [TRF-03] контракты в комплекте (api/")
    assert _line(lines, "ушло 1 (относительно r1.md)")


def test_baseline_number_change_is_same_blocker(tmp_path):
    g1, g2 = tg.Gate(), tg.Gate()
    g1.add("✗", "CORE-06", "битые относительные ссылки: 30 из 7263")
    g2.add("✗", "CORE-06", "битые относительные ссылки: 31 из 7270")
    base = [tg._blocker_key(c, k, t) for _m, c, k, t in g1.lines]
    new, gone = tg.baseline_delta(g2, base)
    assert new == [] and gone == 0


def test_baseline_identifier_digits_distinguish_blockers(tmp_path):
    # НЕсрабатывание схлопывания: номер в имени файла — часть идентификатора, новый блокер
    # в соседнем файле не прячется за старым
    g1, g2 = tg.Gate(), tg.Gate()
    g1.add("✗", "CORE-06", "srs/process/proc-001.md:12: нет цели", check="валидатор E_LOCAL_LINK_MISSING")
    g2.add("✗", "CORE-06", "srs/process/proc-002.md:12: нет цели", check="валидатор E_LOCAL_LINK_MISSING")
    new, gone = tg.baseline_delta(g2, [tg._blocker_key(c, k, t) for _m, c, k, t in g1.lines])
    assert len(new) == 1 and gone == 1


def test_baseline_without_table(tmp_path):
    bad = tmp_path / "x.md"
    bad.write_text("# не отчёт\n", encoding="utf-8")
    lines, _r, _d = _run(make_src(tmp_path), after_step=True, baseline=bad)
    assert lines[-2] == "ИТОГ: ФОРМА ПЕРЕНОСИМА (новых —), предупреждений 2"
    assert lines[-1].startswith("✗ --baseline: в ") and "нет таблицы гейта" in lines[-1]


def test_report_header_mode_line(tmp_path):
    path, _ = _report(tmp_path, make_src(tmp_path), "r.md", after_step=True)
    text = path.read_text(encoding="utf-8")
    assert "Режим: после захода (--after-step)" in text and "ИТОГ: ФОРМА ПЕРЕНОСИМА" in text
    full, _ = _report(tmp_path, make_src(tmp_path / "b"), "f.md")
    assert "Режим: после захода" not in full.read_text(encoding="utf-8")


# ---------------------------------------------------------------- статус OQ (часть B)

def test_oq_status_both_forms(tmp_path):
    oq = ("# Открытые вопросы\n\n## OQ-001 — 2026-10-01. Вопрос\n- **Статус:** закрыт\n\n"
          "## OQ-002 — 2026-10-01. Второй\n- Статус: закрыт (вариант 1; переоткрыть при выкатке v2)\n\n"
          "## OQ-003 — 2026-10-01. Третий\n- Статус: открыт (аналитик)\n\n"
          "## OQ-004 — 2026-10-01. Четвёртый\n- Статус: частично закрыт (алгоритм перенесён)\n\n"
          "## OQ-005 — 2026-10-01. Пятый\n- **Статус:** открыт\n")
    src = make_src(tmp_path, oq=oq)
    path, opened = tg.open_questions(src, src / "docs")
    assert opened == ["OQ-003", "OQ-004", "OQ-005"]
    assert not any("без строки" in o for o in opened)


def test_oq_without_status_line_still_open(tmp_path):
    # НЕсрабатывание терпимости: запись без строки статуса — открыта (асимметрия)
    src = make_src(tmp_path, oq="# OQ\n\n## OQ-001. Вопрос\n- Решение: да\n")
    _p, opened = tg.open_questions(src, src / "docs")
    assert opened == ["OQ-001 (без строки «Статус»)"]


def test_oq_regex_single_home():
    # тот же объект модуля, что импортирует гейт (kitcheck — через sys.path прибора); сравнение с
    # app.scripts.CI.kitcheck.… — другим объектом модуля — держалось на кеше re.compile и падало
    # в полном прогоне, когда кеш вытеснялся (2026-10-28)
    from kitcheck.checks import review_guards as rg
    assert tg._OQ_STATUS_RE is rg.OQ_STATUS_RE is rg._OQ_STATUS_RE


# ---------------------------------------------------------------- зона modules/ (C7)

def _zone(src: Path) -> None:
    z = src / "docs/modules/widgets-rtl"
    _w(z / "README.md", "---\nid: MOD-WIDGETS-RTL-000\ntitle: 'Паспорт'\ntype: module-kit\n---\n# П\n")
    _w(z / "interface/mod-widgets-rtl-001.md",
       "---\nid: MOD-WIDGETS-RTL-001\ntitle: 'Скрипт'\ntype: module-interface\n---\n# С\n")
    _w(z / "spec/scr-01.md", "---\nid: MOD-WIDGETS-RTL-SCR-01\ntitle: 'ЭФ'\ntype: screen-form\n---\n# Э\n")


def test_zone_spec_without_readme_not_flagged_sdlc08(tmp_path):
    src = make_src(tmp_path)
    _zone(src)
    lines, _r, _d = _run(src, after_step=True)
    ln = _line(lines, "⚠ [SDLC-08] каталоги с карточками без README-реестра")
    # в перечне только каталог комплекта srs/function (у базового комплекта нет README), не зона
    assert ln and "modules" not in ln and ": 1 (srs/function)" in ln, "\n".join(lines)
    ln = _line(lines, "i [TRF-04] типы вне закрытого набора платформы")
    assert ln and "module-interface ×1" in ln and "module-kit ×1" in ln


def test_card_dir_without_readme_outside_zone_still_flagged(tmp_path):
    # НЕсрабатывание исключения: каталог карточек комплекта без README — ⚠ как прежде
    src = make_src(tmp_path)
    _zone(src)
    _w(src / "docs/srs/control/ctl-1.md", "---\nid: CTL-001\ntitle: 'К'\ntype: control\n---\n# К\n")
    lines, _r, _d = _run(src, after_step=True)
    ln = _line(lines, "⚠ [SDLC-08] каталоги с карточками без README-реестра: 2 (srs/control, srs/function)")
    assert ln, "\n".join(lines)


def test_docs_repo_modules_dir_is_standard(tmp_path):
    # режим репозитория документации: modules/ рядом с srs/ — штатный каталог (полный режим с
    # прибором: сторож корня не считает его посторонним); README-реестр spec/ не требуется
    from tests.test_transfer_gate import make_docs_repo
    repo = make_docs_repo(tmp_path)
    z = repo / "modules/widgets-rtl"
    _w(z / "README.md", "---\nid: MOD-WIDGETS-RTL-000\ntitle: 'Паспорт'\ntype: module-kit\n---\n# П\n")
    _w(z / "spec/scr-01.md", "---\nid: MOD-WIDGETS-RTL-SCR-01\ntitle: 'ЭФ'\ntype: screen-form\n---\n# Э\n")
    lines, ready, data = _run(repo)
    assert data["docs_repo"] is True
    assert not any("посторонние" in l for l in lines), "\n".join(lines)
    assert not any("каталоги с карточками без README-реестра" in l and "modules" in l for l in lines)


# ---------------------------------------------------------------- корень сборки (лёгкий режим)

def test_after_step_root_junk_dir_blocks(tmp_path):
    # docs/archive/ в целевой раскладке — каталог в корне репозитория документации (КК)
    src = make_src(tmp_path)
    _w(src / "docs/archive/srs/old.md", "# старое\n")
    _w(src / "docs/build.py", "print(1)\n")
    lines, ready, _ = _run(src, after_step=True)
    assert not ready
    ln = _line(lines, "✗ [TRF-01] в корне целевой раскладки посторонние каталоги и файлы: archive/, build.py")
    assert ln, "\n".join(lines)


def test_after_step_root_standard_dirs_pass(tmp_path):
    # НЕсрабатывание: разделы комплекта, зона, постановки, вложения, markdown — штатно
    src = make_src(tmp_path)
    _zone(src)
    for d in ("brd", "nfr", "tasks", "files"):
        _w(src / f"docs/{d}/x.md", "# x\n")
    lines, ready, _ = _run(src, after_step=True)
    assert ready, "\n".join(lines)
    assert _line(lines, "✓ [TRF-01] в корне целевой раскладки только разделы комплекта и markdown")


def test_after_step_root_api_not_doubled(tmp_path):
    # api/ — свой блокер TRF-03, в строке корня не повторяется
    src = make_src(tmp_path)
    _w(src / "docs/api/x-openapi.yaml", "openapi: 3.0.1\n")
    lines, _r, _d = _run(src, after_step=True)
    assert _line(lines, "✗ [TRF-03] контракты в комплекте")
    assert not any("корне целевой раскладки посторонние" in l for l in lines)


def test_full_mode_root_left_to_selfcheck(tmp_path):
    # полный режим: корень сборки проверяет сторож корня selfcheck (ПРИБОР), строки гейта нет
    src = make_src(tmp_path)
    _w(src / "docs/archive/srs/old.md", "# старое\n")
    lines, ready, _ = _run(src)
    assert not ready and not any("корне целевой раскладки" in l for l in lines)
    assert any("[ПРИБОР]" in l and "посторонние" in l and "archive" in l for l in lines), "\n".join(lines)
