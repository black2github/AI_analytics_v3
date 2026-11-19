# -*- coding: utf-8 -*-
"""Гейт переноса: слой BRD (постановка «AI Factory» 2026-11-19, П6–П8; ответы 19.11).

П6 — платформенный сервис без brd/ — i; продуктовый, не найденный в каталоге или каталог
недоступен — ✗; --brd-deferred полный — ⚠ и текст в отчёте, без срока — ✗. П7 — секции BRD-1…5
по префиксу заголовка, гейты BRD-5 по ведущему числу («0 из 128: …» — ✓, «2 фичи (…)» — ✗, без
числа — ✗), пересчёт трёх счётчиков — ⚠. П8 — ссылка между слоями из тела документа — ✗; файлы
README.md (навигация) не рассматриваются. --after-step — новые строки ⚠; selfcheck — ⚠, вердикт
не меняется."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
import selfcheck as sc  # noqa: E402
from kitcheck.checks import brd  # noqa: E402
from tests.test_transfer_gate import (  # noqa: E402,F401 — platform_catalog: сервис X платформенный
    _MATRIX, _w, make_src, platform_catalog)

_FEATURE = ("---\nid: F-CL-01\ntitle: 'Фича'\ntype: feature\nservice: X\n---\n\n# Фича\n\n"
            "## US-01. История\n\nтекст\n")
_GATES = "| Функции без US | 0 из 1: все функции — в BRD-1 |\n| Сироты BRD | 0 |\n"


def _brd_sections(gates: str = _GATES, fun: str = "FUN-CL-01", drop: str = "") -> str:
    secs = {
        "1": ("## BRD-1. Покрытие: требования (BRD) → реализация (SRS)\n\n| Фича | US | Функции (FUN) |\n"
              f"|---|---|---|\n| F-CL-01 Фича | US-01 | {fun} |\n\n"),
        "2": "## BRD-2. Бизнес-правила → фича\n\n| Правило | Фича |\n|---|---|\n\n",
        "3": "## BRD-3. Use Case → фичи\n\n| UC | Фичи |\n|---|---|\n\n",
        "4": "## BRD-4. Печатные формы → фича\n\n| Печатная форма | Фича |\n|---|---|\n\n",
        "5": ("## BRD-5. Разрывы и сироты: гейты достаточности BRD\n\nСчётчики — по инвентарю.\n\n"
              "| Гейт | Значение |\n|---|---|\n" + gates),
    }
    return "\n" + "".join(v for k, v in secs.items() if k != drop)


def _catalog(tmp_path: Path, platform: bool = False, code: str = "X") -> Path:
    cat = tmp_path / "services.json"
    cat.write_text(f'[{{"code": "{code}", "key": "XX", "name": "X", "is_platform": '
                   f'{"true" if platform else "false"}}}]\n', encoding="utf-8")
    return cat


def _with_brd(tmp_path: Path, sections: str = None) -> Path:
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| F-CL-01 | Фича | `brd/features/f-cl-01.md` |\n| VIS-001 |")
        + (_brd_sections() if sections is None else sections))
    _w(src / "docs/brd/features/f-cl-01.md", _FEATURE)
    return src


def _run(src: Path, **kw):
    kw.setdefault("no_validator", True)
    return tg.run_gate(src, **kw)


def _has(lines, prefix):
    return any(l.startswith(prefix) for l in lines)


# ---------------------------------------------------------------- П6

def test_platform_service_without_brd_is_info(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path))
    assert ready and _has(lines, "i [SDLC-06] не применяется: платформенный сервис «X»"), lines


def test_product_service_without_brd_blocks(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path), catalog=_catalog(tmp_path))
    assert not ready and _has(lines, "✗ [SDLC-06] слой BRD обязателен для продуктового сервиса "
                                     "(conventions §5)"), "\n".join(lines)
    assert any("сервис «X» продуктовый" in l for l in lines)


def test_service_not_in_catalog_blocks(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path), catalog=_catalog(tmp_path, platform=True, code="Y"))
    assert not ready and any(l.startswith("✗ [SDLC-06]") and "не найден в каталоге" in l
                             for l in lines), "\n".join(lines)


def test_catalog_unavailable_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(tg.sc, "canon_catalog_path", lambda: None)
    lines, ready, _ = _run(make_src(tmp_path))
    assert not ready and any(l.startswith("✗ [SDLC-06]") and "каталог сервисов недоступен: "
                             "платформенный сервис определяется только по каталогу — задайте "
                             "--catalog" in l for l in lines), "\n".join(lines)


def test_catalog_unavailable_with_brd_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(tg.sc, "canon_catalog_path", lambda: None)
    lines, ready, _ = _run(_with_brd(tmp_path))
    assert _has(lines, "✓ [SDLC-06] слой BRD есть: документов brd/ с id 1"), "\n".join(lines)
    assert ready, "\n".join(lines)


_DEFERRED = "миграция идёт по частям; ответственный: Иванов И.; срок: 2026-12-20"


def test_brd_deferred_full_is_warning_in_report(tmp_path):
    src = make_src(tmp_path)
    lines, ready, data = _run(src, catalog=_catalog(tmp_path), brd_deferred=_DEFERRED,
                              fmt="table")
    assert ready, "\n".join(lines)
    assert any("⚠ предупреждение | SDLC-06 | слой BRD | слой BRD отложен (--brd-deferred): миграция "
               "идёт по частям; ответственный: Иванов И.; срок: 2026-12-20" in l for l in lines)
    rep = tmp_path / "r.md"
    tg.write_report(rep, src, lines, data)
    text = rep.read_text(encoding="utf-8")
    assert f"Слой BRD отложен (--brd-deferred): {_DEFERRED}." in text
    manual = text[text.index("## Ручная часть протокола"):]
    assert f"- **SDLC-06** — слой BRD отложен ключом --brd-deferred: {_DEFERRED}" in manual
    assert "verify-brd-vs-srs" in manual


def test_brd_deferred_without_term_blocks(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path), catalog=_catalog(tmp_path),
                           brd_deferred="миграция по частям; ответственный: Иванов И.")
    assert not ready and any(l.startswith("✗ [SDLC-06]") and "--brd-deferred без поля «срок»" in l
                             for l in lines), "\n".join(lines)


@pytest.mark.parametrize("value,missing", [
    (_DEFERRED, []),
    ("основание; срок: 2026-12-20", ["ответственный"]),
    ("основание; ответственный: А; срок: скоро", ["срок"]),
    ("ответственный: А; срок: 2026-12-20", ["основание"]),
])
def test_parse_deferred(value, missing):
    assert brd.parse_deferred(value)[1] == missing


def test_report_without_deferred_keeps_manual_sdlc06(tmp_path):
    src = make_src(tmp_path)
    lines, _r, data = _run(src, fmt="table")
    rep = tmp_path / "r.md"
    tg.write_report(rep, src, lines, data)
    text = rep.read_text(encoding="utf-8")
    assert "Слой BRD отложен" not in text
    assert "- **SDLC-06** — независимая сверка BRD с карточками (verify-brd-vs-srs) выполнена" in text


# ---------------------------------------------------------------- П7

def test_brd_sections_and_zero_gates_pass(tmp_path):
    lines, ready, _ = _run(_with_brd(tmp_path), catalog=_catalog(tmp_path))
    assert ready, "\n".join(lines)
    assert _has(lines, "✓ [SDLC-06] секции BRD-1…BRD-5 есть; гейты BRD-5 нулевые (2)")
    assert any("остальные гейты — по заявленному значению" in l for l in lines)
    assert not _has(lines, "⚠ [SDLC-06] пересчёт")


def test_missing_brd_section_blocks(tmp_path):
    lines, ready, _ = _run(_with_brd(tmp_path, _brd_sections(drop="3")), catalog=_catalog(tmp_path))
    assert not ready and _has(lines, "✗ [SDLC-06] в матрице нет секций бизнес-слоя: BRD-3"), \
        "\n".join(lines)


def test_nonzero_gate_blocks(tmp_path):
    gates = _GATES + "| Сироты BRD (F/US/FR/BR/UC без связи с SRS) | 2 фичи (F-CL-10, F-BNK-08) |\n"
    lines, ready, _ = _run(_with_brd(tmp_path, _brd_sections(gates)), catalog=_catalog(tmp_path))
    hit = [l for l in lines if l.startswith("✗ [SDLC-06] гейты достаточности BRD-5 не нулевые")]
    assert not ready and hit and "= «2 фичи (F-CL-10, F-BNK-08)»" in hit[0], "\n".join(lines)


def test_unreadable_gate_value_blocks(tmp_path):
    gates = _GATES + "| Печатные формы без связи | нет |\n"
    lines, ready, _ = _run(_with_brd(tmp_path, _brd_sections(gates)), catalog=_catalog(tmp_path))
    assert not ready and any("«Печатные формы без связи» — значение гейта не читается" in l
                             for l in lines), "\n".join(lines)


def test_section_title_variants_by_prefix(tmp_path):
    # название секции у комплектов разное — признак только префикс «## BRD-<N>»
    secs = _brd_sections().replace("## BRD-5. Разрывы и сироты: гейты достаточности BRD",
                                   "## BRD-5. Достаточность BRD: гейты покрытия")
    lines, ready, _ = _run(_with_brd(tmp_path, secs), catalog=_catalog(tmp_path))
    assert ready and _has(lines, "✓ [SDLC-06] секции BRD-1…BRD-5 есть"), "\n".join(lines)


def test_recount_function_without_us_is_warning(tmp_path):
    lines, ready, _ = _run(_with_brd(tmp_path, _brd_sections(fun="—")), catalog=_catalog(tmp_path))
    assert ready, "\n".join(lines)
    assert _has(lines, "⚠ [SDLC-06] пересчёт по комплекту расходится с заявленными нулями: функции "
                       "без US (нет в BRD-1): 1 (FUN-CL-01)"), "\n".join(lines)


def test_recount_orphan_and_inner_ids(tmp_path):
    src = _with_brd(tmp_path, _brd_sections().replace(
        "| Правило | Фича |\n|---|---|\n", "| Правило | Фича |\n|---|---|\n| BR-01 | F-CL-01 |\n"))
    # BR-000 связан через внутренний ID BR-01 — не сирота; F-CL-02 нигде — сирота
    _w(src / "docs/brd/business-rules.md",
       "---\nid: BR-000\ntitle: 'Правила'\ntype: business-rules\nservice: X\n---\n\n# Правила\n\n"
       "## BR-01. Правило\n\nтекст\n")
    _w(src / "docs/brd/features/f-cl-02.md",
       _FEATURE.replace("F-CL-01", "F-CL-02").replace("US-01", "US-02"))
    rc = brd.brd_recount(src / "docs", brd.brd_sections(
        (src / "docs/traceability-matrix.md").read_text(encoding="utf-8")))
    assert rc["сироты BRD (документ brd/ вне BRD-1…3)"] == ["F-CL-02"], rc


def test_print_forms_registry_readme_not_counted(tmp_path):
    src = _with_brd(tmp_path)
    _w(src / "docs/srs/print-form/README.md",
       "---\nid: PRN-000\ntitle: 'Реестр'\ntype: print-form\nservice: X\n---\n# Р\n")
    rc = brd.brd_recount(src / "docs", brd.brd_sections(
        (src / "docs/traceability-matrix.md").read_text(encoding="utf-8")))
    assert rc["печатные формы без связи (нет в BRD-4)"] == []


# ---------------------------------------------------------------- П8

def test_layer_link_from_document_blocks(tmp_path):
    src = _with_brd(tmp_path)
    _w(src / "docs/brd/features/f-cl-01.md",
       _FEATURE + "\nСм. [функцию](../../srs/function/client/fun-cl-01-f1.md).\n")
    lines, ready, _ = _run(src, catalog=_catalog(tmp_path))
    assert not ready and _has(lines, "✗ [SDLC-01] ссылки между слоями BRD и SRS в телах документов: "
                                     "1 (brd/features/f-cl-01.md → srs/function/client/"
                                     "fun-cl-01-f1.md)"), "\n".join(lines)


def test_layer_links_between_readme_not_considered(tmp_path):
    src = _with_brd(tmp_path)
    _w(src / "docs/brd/README.md", "# BRD\n\nСм. [SRS](../srs/README.md).\n")
    _w(src / "docs/srs/README.md", "# SRS\n\n[BRD](../brd/README.md)\n")
    lines, ready, _ = _run(src, catalog=_catalog(tmp_path))
    sdlc01 = [l for l in lines if "[SDLC-01]" in l and "между слоями" in l]
    assert sdlc01 == ["✓ [SDLC-01] ссылок между слоями BRD и SRS нет (conventions §5.4)"], \
        "\n".join(lines)
    assert not any("навигация" in l for l in lines)


def test_readme_as_link_source_or_target_not_considered(tmp_path):
    # README — навигация, не документ слоя: ни как источник ссылки на документ SRS, ни как цель
    src = _with_brd(tmp_path)
    _w(src / "docs/brd/README.md", "# BRD\n\n[функция](../srs/function/client/fun-cl-01-f1.md)\n")
    _w(src / "docs/srs/README.md", "# SRS\n")
    _w(src / "docs/brd/features/f-cl-01.md", _FEATURE + "\nСм. [оглавление SRS](../../srs/README.md).\n")
    lines, ready, _ = _run(src, catalog=_catalog(tmp_path))
    assert not _has(lines, "✗ [SDLC-01]") and not _has(lines, "⚠ [SDLC-01]"), "\n".join(lines)


def test_readme_excluded_body_link_still_blocks(tmp_path):
    # исключение README не прячет ссылку из тела документа рядом с ним
    src = _with_brd(tmp_path)
    _w(src / "docs/brd/README.md", "# BRD\n\nСм. [SRS](../srs/README.md).\n")
    _w(src / "docs/brd/features/f-cl-01.md",
       _FEATURE + "\nСм. [функцию](../../srs/function/client/fun-cl-01-f1.md).\n")
    lines, ready, _ = _run(src, catalog=_catalog(tmp_path))
    assert not ready and _has(lines, "✗ [SDLC-01] ссылки между слоями BRD и SRS в телах документов: "
                                     "1 (brd/features/f-cl-01.md"), "\n".join(lines)


def test_layer_link_in_code_block_and_external_ignored(tmp_path):
    src = _with_brd(tmp_path)
    _w(src / "docs/brd/features/f-cl-01.md",
       _FEATURE + "\n```\n[x](../../srs/function/client/fun-cl-01-f1.md)\n```\n"
                  "[внешняя](https://example.org/srs/a.md)\n")
    lines, ready, _ = _run(src, catalog=_catalog(tmp_path))
    assert _has(lines, "✓ [SDLC-01] ссылок между слоями BRD и SRS нет"), "\n".join(lines)


# ---------------------------------------------------------------- режимы

def test_after_step_brd_lines_are_warnings(tmp_path):
    src = _with_brd(tmp_path, _brd_sections(drop="3"))
    _w(src / "docs/brd/features/f-cl-01.md",
       _FEATURE + "\nСм. [функцию](../../srs/function/client/fun-cl-01-f1.md).\n")
    lines, ready, _ = _run(src, catalog=_catalog(tmp_path), after_step=True)
    assert _has(lines, "⚠ [SDLC-06] в матрице нет секций бизнес-слоя: BRD-3"), "\n".join(lines)
    assert _has(lines, "⚠ [SDLC-01] ссылки между слоями BRD и SRS в телах документов")
    lines, _r, _d = _run(make_src(tmp_path / "b"), catalog=_catalog(tmp_path), after_step=True)
    assert _has(lines, "⚠ [SDLC-06] слой BRD обязателен для продуктового сервиса")


def test_selfcheck_brd_lines_are_warnings_verdict_unchanged(tmp_path):
    src = _with_brd(tmp_path, _brd_sections(drop="3"))
    rep, ok = sc.run(src / "docs", None)
    assert any(l.startswith("⚠ слой BRD: в матрице нет секций бизнес-слоя: BRD-3") and
               l.endswith("(гейт переноса — ✗)") for l in rep), "\n".join(rep)
    rep0, ok0 = sc.run(_with_brd(tmp_path / "b") / "docs", None)
    assert ok == ok0 and not any(l.startswith("⚠ слой BRD") for l in rep0)


def test_selfcheck_product_without_brd_warns_platform_silent(tmp_path, monkeypatch):
    src = make_src(tmp_path)
    rep, _ok = sc.run(src / "docs", None, catalog=_catalog(tmp_path))
    assert any(l.startswith("⚠ слой BRD: слой BRD обязателен") for l in rep), "\n".join(rep)
    rep, _ok = sc.run(src / "docs", None)  # платформенный (фикстура) — молчит
    assert not any(l.startswith("⚠ слой BRD") for l in rep)
    monkeypatch.setattr(tg.sc, "canon_catalog_path", lambda: None)
    rep, _ok = sc.run(src / "docs", None)  # каталога нет — молчит
    assert not any(l.startswith("⚠ слой BRD") for l in rep)
