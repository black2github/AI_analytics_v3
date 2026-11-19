# -*- coding: utf-8 -*-
"""Гейт переноса: матрица трассировки (постановка «AI Factory» 2026-11-19, П1–П5).

П1 — структура: порядок шести разделов при верном составе — ⚠ и сверка выполнена, прочие
отклонения — ✗; matrix_sync --write при отклонении только порядка работает и порядок сохраняет.
П2 — реестр ID: расхождение — ✗, «ID только упоминается» — ⚠. П3 — покрытия функций и процессов:
расхождение (в том числе недостающая колонка шаблона) — ✗ с командой пересборки; «Источники
миграции» — ⚠. П4–П5 — раздел API: пуст без карточек методов — ✓, с карточками — ✗, с причиной в
шапке — ✓; карточка метода не названа в разделе — ✗; карточка части вне контура Экосистемы и
README-реестр не считаются. --after-step — новые строки ⚠."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
import matrix_sync as ms  # noqa: E402
import selfcheck as sc  # noqa: E402
from tests.test_transfer_gate import (  # noqa: E402,F401 — platform_catalog: сервис X платформенный
    _API_SEC, _MATRIX, _w, make_src, platform_catalog)

_REG_SEC = _MATRIX[_MATRIX.index("## Реестр ID"):_MATRIX.index("## Покрытие: функции")]
_INTC = "---\nid: INTC-001\ntitle: 'М'\ntype: internal-contract\nservice: X\n---\n\n# М\n"
_INTC_ROW = "| INTC-001 | М | `srs/internal-contract/intc-001.md` |\n| VIS-001 |"


def _run(src: Path, **kw):
    kw.setdefault("no_validator", True)
    return tg.run_gate(src, **kw)


def _has(lines, prefix):
    return any(l.startswith(prefix) for l in lines)


def _matrix(src: Path, text: str) -> None:
    _w(src / "docs/traceability-matrix.md", text)


# ---------------------------------------------------------------- П1

def test_order_only_is_warning_and_ready(tmp_path):
    src = make_src(tmp_path, matrix=_MATRIX.replace(_REG_SEC, "").replace(
        "## Покрытие: API", _REG_SEC + "## Покрытие: API"))
    lines, ready, _ = _run(src)
    assert ready, "\n".join(lines)
    assert _has(lines, "⚠ [SDLC-04] порядок разделов не по шаблону: Покрытие: функции")
    assert _has(lines, "✓ [SDLC-09] «Реестр ID» совпадает с документами")
    assert _has(lines, "✓ [SDLC-04] «Покрытие: функции → артефакты» совпадает")


def test_order_only_still_compares_sections(tmp_path):
    # порядок иной — сверка разделов всё равно выполняется: строки нет — ✗ реестра
    m = _MATRIX.replace(_REG_SEC, "").replace("## Покрытие: API", _REG_SEC + "## Покрытие: API")
    src = make_src(tmp_path, matrix=m.replace("| GLO-001 | Г | `glossary.md` |\n", ""))
    lines, ready, _ = _run(src)
    assert not ready
    assert _has(lines, "✗ [SDLC-09] «Реестр ID» расходится с документами: нет строки для ID из "
                       "документов ×1 (GLO-001)"), "\n".join(lines)


def test_section_outside_template_blocks(tmp_path):
    src = make_src(tmp_path, matrix=_MATRIX.replace("## Источники миграции",
                                                    "## Фича-флаги\n\nтекст\n\n## Источники миграции"))
    lines, ready, _ = _run(src)
    assert not ready
    hit = [l for l in lines if l.startswith("✗ [SDLC-04] структура матрицы не по шаблону ×1")]
    assert hit and "раздел вне шаблона: «Фича-флаги»" in hit[0] and "## Приложение" in hit[0], lines


def test_missing_section_blocks(tmp_path):
    m = _MATRIX[:_MATRIX.index("\n## Долги по ссылкам")]
    lines, ready, _ = _run(make_src(tmp_path, matrix=m))
    assert not ready and _has(lines, "✗ [SDLC-04] структура матрицы не по шаблону ×1: нет раздела "
                                     "«Долги по ссылкам»")


def test_structure_classes():
    m = _MATRIX.replace(_REG_SEC, "").replace("## Покрытие: API", _REG_SEC + "## Покрытие: API")
    found = ms.structure_findings(ms.parse_matrix(m))
    assert [c for c, _ in found] == [ms.ORDER]
    assert ms.blocking_structure(ms.parse_matrix(m)) == []
    assert ms.structure_issues(ms.parse_matrix(m)) == [t for _, t in found]


def _sync_kit(tmp_path: Path) -> Path:
    from tests.test_matrix_sync import kit
    return kit(tmp_path)


def test_matrix_sync_write_keeps_order(tmp_path):
    from tests.test_matrix_sync import w, fm
    docs = _sync_kit(tmp_path)
    mx = docs / "traceability-matrix.md"
    text = mx.read_text(encoding="utf-8")
    reg = text[text.index("## Реестр ID"):text.index("## Покрытие: функции")]
    moved = text.replace(reg, "").replace("## Покрытие: API", reg + "## Покрытие: API")
    mx.write_text(moved, encoding="utf-8")
    report, warn = ms.check(docs)
    assert warn and report[0].startswith("⚠ порядок разделов не по шаблону"), report
    assert "структура матрицы не по шаблону" not in "\n".join(report)
    w(docs / "srs/data-model/ent-002.md", fm("ENT-002", "data-model", "Адрес"))
    rep, code = ms.write(docs)
    assert code == 0, rep
    out = mx.read_text(encoding="utf-8")
    heads = [ln for ln in out.splitlines() if ln.startswith("## ")]
    assert heads.index("## Реестр ID") > heads.index("## Покрытие: процессы → артефакты"), heads
    assert "| ENT-002 | Адрес | `srs/data-model/ent-002.md` |" in out


def test_matrix_sync_write_refuses_blocking(tmp_path):
    docs = _sync_kit(tmp_path)
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace("## Долги по ссылкам", "## Долги"),
                  encoding="utf-8")
    before = mx.read_bytes()
    report, code = ms.write(docs)
    assert code == 2 and "структура не по шаблону" in "\n".join(report)
    assert mx.read_bytes() == before


# ---------------------------------------------------------------- П2

def test_registry_mention_only_is_warning(tmp_path):
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| FUN-CL-09 | Упомянутая | `srs/function/client/fun-cl-01-f1.md` |\n| VIS-001 |"))
    _w(src / "docs/srs/function/client/fun-cl-01-f1.md",
       (src / "docs/srs/function/client/fun-cl-01-f1.md").read_text(encoding="utf-8")
       + "\nСм. также FUN-CL-09 в тексте\n")
    lines, ready, _ = _run(src)
    assert _has(lines, "⚠ [SDLC-09] «Реестр ID»: ID только упоминается в тексте"), "\n".join(lines)
    assert not _has(lines, "✗ [SDLC-09] «Реестр ID»")


def test_registry_stale_row_blocks(tmp_path):
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| FUN-CL-09 | Удалённая | `srs/function/client/fun-cl-09.md` |\n| VIS-001 |"))
    lines, ready, _ = _run(src)
    assert not ready and _has(lines, "✗ [SDLC-09] «Реестр ID» расходится с документами: строка без "
                                     "документа"), "\n".join(lines)


def test_registry_row_of_migration_journal_is_warning(tmp_path):
    # журнал вопросов внутри комплекта в целевую раскладку не переносится; его строка в
    # реестре — ⚠ «--write снимет», не «строка без документа»
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| OQ-001 | Вопрос | `srs/open-questions.md` |\n| VIS-001 |"))
    _w(src / "docs/srs/open-questions.md", "# Открытые вопросы\n\n## OQ-001. Вопрос\n\nТекст.\n")
    lines, ready, _ = _run(src)
    assert _has(lines, "⚠ [SDLC-09] «Реестр ID»: строка служебного файла миграции — --write "
                       "снимет ×1 (OQ-001)"), "\n".join(lines)
    assert not _has(lines, "✗ [SDLC-09]"), "\n".join(lines)


def test_migration_journal_ids_not_required_in_registry(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/srs/open-questions.md", "# Открытые вопросы\n\n## OQ-001. Вопрос\n\nТекст.\n")
    lines, ready, _ = _run(src)
    assert not _has(lines, "✗ [SDLC-09]") and not _has(lines, "⚠ [SDLC-09]"), "\n".join(lines)


# ---------------------------------------------------------------- П3

def test_coverage_missing_link_blocks_with_write_command(tmp_path):
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| ENT-001 | С | `srs/data-model/e1.md` |\n| VIS-001 |"))
    _w(src / "docs/srs/data-model/e1.md", "---\nid: ENT-001\ntitle: 'С'\ntype: data-model\n---\n# С\n")
    _w(src / "docs/srs/function/client/fun-cl-01-f1.md",
       (src / "docs/srs/function/client/fun-cl-01-f1.md").read_text(encoding="utf-8")
       + "\nПишет [ENT-001](../../data-model/e1.md).\n")
    lines, ready, _ = _run(src)
    hit = [l for l in lines if l.startswith("✗ [SDLC-04] «Покрытие: функции → артефакты» расходится")]
    assert not ready and hit, "\n".join(lines)
    assert "нет связи из документов ×1 (FUN-CL-01 «Данные»: нет ENT-001)" in hit[0], hit
    assert "matrix_sync.py --docs" in hit[0] and "--write" in hit[0]


def test_coverage_missing_template_column_blocks(tmp_path):
    m = (_MATRIX.replace("| Функция | Название | Вызовы | Экраны | Данные | Контроли | Уведомления | "
                         "Печатные формы |\n| --- | --- | --- | --- | --- | --- | --- | --- |",
                         "| Функция | Название | Вызовы | Экраны | Данные | Контроли | Печатные формы |\n"
                         "| --- | --- | --- | --- | --- | --- | --- |")
         .replace("| FUN-CL-01 | Ф | — | — | — | — | — | — |", "| FUN-CL-01 | Ф | — | — | — | — | — |"))
    lines, ready, _ = _run(make_src(tmp_path, matrix=m))
    assert not ready
    assert not _has(lines, "✗ [SDLC-04] структура матрицы"), "\n".join(lines)
    assert _has(lines, "✗ [SDLC-04] «Покрытие: функции → артефакты» расходится с документами: нет "
                       "колонки «Уведомления»"), "\n".join(lines)


def test_sources_discrepancy_is_warning(tmp_path):
    src = make_src(tmp_path)
    p = src / "docs/srs/function/client/fun-cl-01-f1.md"
    p.write_text(p.read_text(encoding="utf-8").replace("service: X\n",
                                                       "service: X\nconfluence_page_ids: ['2166860001']\n"),
                 encoding="utf-8")
    lines, ready, _ = _run(src)
    assert ready, "\n".join(lines)
    assert _has(lines, "⚠ [SDLC-04] «Источники миграции» расходится с документами: нет строки "
                       "страницы ×1 (2166860001)"), "\n".join(lines)


def test_after_step_matrix_lines_are_warnings(tmp_path):
    m = _MATRIX.replace("## Источники миграции", "## Фича-флаги\n\nтекст\n\n## Источники миграции")
    src = make_src(tmp_path, matrix=m.replace("| GLO-001 | Г | `glossary.md` |\n", ""))
    lines, ready, _ = _run(src, after_step=True)
    assert _has(lines, "⚠ [SDLC-04] структура матрицы не по шаблону"), "\n".join(lines)
    assert _has(lines, "⚠ [SDLC-09] «Реестр ID» расходится")
    assert not any(l.startswith("✗ [SDLC-0") for l in lines), "\n".join(lines)


# ---------------------------------------------------------------- П4–П5

def _with_intc(tmp_path: Path, api: str = _API_SEC) -> Path:
    src = make_src(tmp_path, matrix=_MATRIX.replace("| VIS-001 |", _INTC_ROW).replace(_API_SEC, api))
    _w(src / "docs/srs/internal-contract/intc-001.md", _INTC)
    return src


def test_empty_api_without_methods_passes(tmp_path):
    lines, _r, _d = _run(make_src(tmp_path))
    assert _has(lines, "✓ [SDLC-04] раздел пуст — собственных методов нет")


def test_empty_api_with_methods_blocks(tmp_path):
    lines, ready, _ = _run(_with_intc(tmp_path))
    assert not ready and _has(lines, "✗ [SDLC-04] раздел пуст, а в комплекте карточек собственных "
                                     "методов (internal-contract) 1: INTC-001")


def test_empty_api_with_reason_in_header_passes(tmp_path):
    api = _API_SEC.replace("\n\n|", "\n\nОпераций нет: методы описаны карточками до API First.\n\n|", 1)
    lines, ready, _ = _run(_with_intc(tmp_path, api))
    assert _has(lines, "✓ [SDLC-04] раздел пуст, причина записана в шапке раздела: «Операций нет: "
                       "методы описаны карточками до API First.»"), "\n".join(lines)


def test_unnamed_method_card_blocks(tmp_path):
    api = _API_SEC.replace("| --- | --- |\n", "| --- | --- |\n| POST /x | FUN-CL-01 |\n")
    lines, ready, _ = _run(_with_intc(tmp_path, api))
    assert not ready and _has(lines, "✗ [SDLC-04] операций 1; карточки собственных методов не "
                                     "названы в разделе: 1 из 1 (INTC-001)"), "\n".join(lines)


def test_named_method_card_in_srs_column_passes(tmp_path):
    api = _API_SEC.replace("| --- | --- |\n", "| --- | --- |\n| POST /x | INTC-001, FUN-CL-01 |\n")
    lines, ready, _ = _run(_with_intc(tmp_path, api))
    assert _has(lines, "✓ [SDLC-04] раздел есть, операций 1; все карточки собственных методов "
                       "названы (1)"), "\n".join(lines)


def test_outside_eco_part_card_not_required(tmp_path):
    # карточка части вне контура Экосистемы (паспорт границы srs/<слаг>/boundary-passport.md) в
    # раздел не вносится; README-реестр методов не считается
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| BND-001 | П | `srs/rtl/boundary-passport.md` |\n"
                       "| INTC-002 | М2 | `srs/rtl/internal-contract/intc-002.md` |\n"
                       "| INTC-000 | Р | `srs/rtl/internal-contract/README.md` |\n| VIS-001 |"))
    _w(src / "docs/srs/rtl/boundary-passport.md",
       "---\nid: BND-001\ntitle: 'П'\ntype: module-passport\n---\n# П\n")
    _w(src / "docs/srs/rtl/internal-contract/intc-002.md", _INTC.replace("INTC-001", "INTC-002")
       .replace("'М'", "'М2'"))
    _w(src / "docs/srs/rtl/internal-contract/README.md",
       "---\nid: INTC-000\ntitle: 'Р'\ntype: internal-contract\n---\n# Р\n")
    lines, _r, _d = _run(src)
    assert _has(lines, "✓ [SDLC-04] раздел пуст — собственных методов нет; карточек части вне "
                       "контура Экосистемы 1 — в раздел не вносятся"), "\n".join(lines)


def test_after_step_api_line_is_warning(tmp_path):
    lines, _r, _d = _run(_with_intc(tmp_path), after_step=True)
    assert _has(lines, "⚠ [SDLC-04] раздел пуст, а в комплекте карточек собственных методов")


def test_selfcheck_api_line_is_warning_verdict_unchanged(tmp_path):
    src = _with_intc(tmp_path)
    rep, ok = sc.run(src / "docs", None)
    hit = [l for l in rep if l.startswith("⚠ матрица «Покрытие: API ↔ SRS»: раздел пуст")]
    assert hit and "(гейт переноса — ✗)" in hit[0], "\n".join(rep)
    rep0, ok0 = sc.run(make_src(tmp_path / "b") / "docs", None)
    assert ok == ok0
    assert not any(l.startswith("⚠ матрица «Покрытие: API ↔ SRS»") for l in rep0)
