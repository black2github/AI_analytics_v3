# -*- coding: utf-8 -*-
"""Гейт переноса: типы, README, внешние вызовы, версия комплекта (постановка «AI Factory»
2026-11-19, П9–П12; ответы 19.11).

П9 — тип вне набора платформы, не описанный в «Условных обозначениях» README (токен типа либо
ID-префикс его документов, выведенный из комплекта), — ✗; описанный — i; тип из набора, не
описанный, — ⚠. П10 — README без ссылки на матрицу — ⚠. П11 — карточка CALL-EXT без ссылки на md
базового контракта в docs-external-contracts и не FROM-ID строки долга — ✗. П12 — --out при
незакоммиченных изменениях в каталоге комплекта — ✗, без --out — ⚠; служебные файлы не считаются."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
import selfcheck as sc  # noqa: E402
from kitcheck.checks.ids_domain import doc_types  # noqa: E402
from tests.test_transfer_gate import (  # noqa: E402,F401 — platform_catalog: сервис X платформенный
    _MATRIX, _MATRIX_BASE, _README, _target, _w, git_commit, make_src, platform_catalog)

_CALL_REL = "srs/contract-call/external/call-ext-001.md"
_BASE = ("**Базовый контракт:** [EXTINT-ESK-001](https://gitlab.gboteam.ru/EAN/docs-external-contracts"
         "/-/blob/HEAD/esk/extint-esk-001-request.md)\n")


def _run(src: Path, **kw):
    kw.setdefault("no_validator", True)
    return tg.run_gate(src, **kw)


def _has(lines, prefix):
    return any(l.startswith(prefix) for l in lines)


# ---------------------------------------------------------------- П9

def _with_flag(tmp_path: Path, readme: str = _README) -> Path:
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| FF-001 | Флаг | `srs/feature-flag/ff-001.md` |\n| VIS-001 |"))
    _w(src / "docs/srs/feature-flag/ff-001.md",
       "---\nid: FF-001\ntitle: 'Флаг'\ntype: feature-flag\nservice: X\n---\n# Флаг\n")
    _w(src / "docs/README.md", readme)
    return src


def test_outside_type_not_described_blocks(tmp_path):
    lines, ready, _ = _run(_with_flag(tmp_path))
    assert not ready and _has(lines, "✗ [TRF-04] типы вне закрытого набора платформы не описаны в "
                                     "README комплекта: feature-flag ×1 (FF)"), "\n".join(lines)


def test_outside_type_described_by_kit_prefix_is_info(tmp_path):
    readme = _README.replace("| **FUN** | Функция |", "| **FUN** | Функция |\n| **FF** | Фича-флаг |")
    lines, ready, _ = _run(_with_flag(tmp_path, readme))
    assert _has(lines, "i [TRF-04] типы вне закрытого набора платформы: feature-flag ×1 — объявлены"), \
        "\n".join(lines)
    assert not _has(lines, "✗ [TRF-04]")


def test_outside_type_described_by_token_is_info(tmp_path):
    readme = _README.replace("### Поля frontmatter", "Тип `feature-flag` — фича-флаг.\n\n### Поля frontmatter")
    lines, _r, _d = _run(_with_flag(tmp_path, readme))
    assert _has(lines, "i [TRF-04] типы вне закрытого набора платформы: feature-flag ×1 — объявлены")


def test_description_outside_legend_not_counted(tmp_path):
    readme = _README + "\n| **FF** | Фича-флаг |\n"  # в разделе «Разделы», не в «Условных обозначениях»
    lines, _r, _d = _run(_with_flag(tmp_path, readme))
    assert _has(lines, "✗ [TRF-04] типы вне закрытого набора платформы не описаны")


def test_platform_type_not_described_warns(tmp_path):
    readme = _README.replace("| **FUN** | Функция |\n", "")
    lines, ready, _ = _run(make_src(tmp_path), fmt="log")
    assert _has(lines, "✓ [TRF-04] все типы комплекта в закрытом наборе платформы и описаны в README")
    src = make_src(tmp_path / "b")
    _w(src / "docs/README.md", readme)
    lines, ready, _ = _run(src)
    assert _has(lines, "⚠ [TRF-04] типы из набора платформы не описаны в README комплекта: function ×1 "
                       "(FUN)"), "\n".join(lines)


def test_prefix_derived_from_kit_not_dictionary(tmp_path):
    # префикс выводится из документов типа: тот же тип с другим префиксом ID — описание по нему
    src = make_src(tmp_path)
    _w(src / "docs/srs/x/a.md", "---\nid: QQ-001\ntype: agent\n---\n# A\n")
    types = doc_types([src / "docs/srs/x/a.md"], _README.replace("| **FUN** | Функция |",
                                                                 "| **QQ** | Агент |"))
    assert types["agent"]["described"] and types["agent"]["prefixes"] == {"QQ"}
    types = doc_types([src / "docs/srs/x/a.md"], _README.replace("| **FUN** | Функция |",
                                                                 "| **CHD** | Агент |"))
    assert not types["agent"]["described"]


# ---------------------------------------------------------------- П10

def test_readme_matrix_link(tmp_path):
    lines, _r, _d = _run(make_src(tmp_path))
    assert _has(lines, "✓ [SDLC-08] README ссылается на traceability-matrix.md")
    src = make_src(tmp_path / "b")
    _w(src / "docs/README.md", _README.replace("- [Матрица трассировки](traceability-matrix.md)\n", ""))
    lines, ready, _ = _run(src)
    assert ready and _has(lines, "⚠ [SDLC-08] README не ссылается на traceability-matrix.md")


# ---------------------------------------------------------------- П11

def _with_call(tmp_path: Path, body: str, matrix: str = None, rel: str = _CALL_REL,
               cid: str = "CALL-EXT-001") -> Path:
    m = matrix if matrix is not None else _MATRIX
    src = make_src(tmp_path, matrix=m.replace("| VIS-001 |", f"| {cid} | Вызов | `{rel}` |\n| VIS-001 |"))
    _w(src / "docs" / rel, f"---\nid: {cid}\ntitle: 'Вызов'\ntype: contract-call\nservice: X\n---\n\n"
                           f"# {cid}. Вызов\n\n{body}")
    return src


def test_call_ext_with_base_contract_link_passes(tmp_path):
    lines, ready, _ = _run(_with_call(tmp_path, _BASE))
    assert ready and _has(lines, "✓ [SDLC-02] карточки внешнего вызова ведут к базовому контракту: "
                                 "ссылкой — 1 из 1"), "\n".join(lines)


def test_call_ext_without_link_blocks(tmp_path):
    lines, ready, _ = _run(_with_call(tmp_path, "**Базовый контракт:** опубликованной карточки нет.\n"))
    assert not ready and _has(lines, "✗ [SDLC-02] карточки внешнего вызова без ссылки на базовый "
                                     "контракт: 1 из 1 (CALL-EXT-001)"), "\n".join(lines)
    assert any("строку долга «у владельца»" in l for l in lines)


def test_call_ext_repo_root_or_examples_link_not_counted(tmp_path):
    body = ("[репозиторий](https://gitlab.gboteam.ru/EAN/docs-external-contracts) и "
            "[примеры](https://gitlab.gboteam.ru/EAN/docs-external-contracts/-/tree/HEAD/esk/examples)\n")
    lines, ready, _ = _run(_with_call(tmp_path, body))
    assert not ready and _has(lines, "✗ [SDLC-02] карточки внешнего вызова без ссылки")


def test_call_ext_examples_md_link_not_counted(tmp_path):
    body = ("[пример](https://gitlab.gboteam.ru/EAN/docs-external-contracts/-/blob/HEAD/esk/examples/"
            "request.md)\n")
    lines, ready, _ = _run(_with_call(tmp_path, body))
    assert not ready and _has(lines, "✗ [SDLC-02] карточки внешнего вызова без ссылки"), "\n".join(lines)


def test_call_ext_debt_row_counts(tmp_path):
    debts = ("\n## Долги по ссылкам\n\n| FROM-ID | Цель | Долг |\n|---|---|---|\n"
             "| CALL-EXT-001 | — | нет базового контракта «ЕСК: запрос» у владельца esk |\n")
    readme = _README.replace("## Разделы\n", "### Долги по ссылкам\n\nправило\n\n## Разделы\n")
    src = _with_call(tmp_path, "без ссылки\n", matrix=_MATRIX_BASE + debts)
    _w(src / "docs/README.md", readme)
    lines, _r, _d = _run(src)
    assert _has(lines, "✓ [SDLC-02] карточки внешнего вызова ведут к базовому контракту: ссылкой — 0 "
                       "из 1; строкой долга — 1 (CALL-EXT-001)"), "\n".join(lines)


def test_call_ext_part_form_and_internal_ignored(tmp_path):
    src = _with_call(tmp_path, "без ссылки\n", rel="srs/agr/contract-call/call-agr-ext-01.md",
                     cid="CALL-AGR-EXT-01")
    lines, _r, _d = _run(src)
    assert _has(lines, "✗ [SDLC-02] карточки внешнего вызова без ссылки на базовый контракт: 1 из 1 "
                       "(CALL-AGR-EXT-01)"), "\n".join(lines)
    src = _with_call(tmp_path / "b", "без ссылки\n", rel="srs/contract-call/internal/call-int-001.md",
                     cid="CALL-INT-001")
    lines, _r, _d = _run(src)
    assert not any("[SDLC-02]" in l for l in lines)


def test_call_ext_after_step_and_selfcheck_warn(tmp_path):
    src = _with_call(tmp_path, "без ссылки\n")
    lines, _r, _d = _run(src, after_step=True)
    assert _has(lines, "⚠ [SDLC-02] карточки внешнего вызова без ссылки")
    rep, ok = sc.run(src / "docs", None)
    assert any(l.startswith("⚠ внешний вызов: карточки внешнего вызова без ссылки") for l in rep)
    rep0, ok0 = sc.run(_with_call(tmp_path / "c", _BASE) / "docs", None)
    assert ok == ok0 and not any(l.startswith("⚠ внешний вызов") for l in rep0)


# ---------------------------------------------------------------- П12

def test_out_from_dirty_kit_blocks(tmp_path):
    src = git_commit(make_src(tmp_path))
    _w(src / "docs/glossary.md", "---\nid: GLO-001\ntype: glossary\n---\n# Г правка\n")
    out = _target(tmp_path)
    lines, ready, _ = _run(src, out=out)
    assert not ready and _has(lines, "✗ [CORE-05] перенос из рабочего дерева: версию комплекта нельзя "
                                     "получить повторно — незакоммиченных изменений в каталоге "
                                     "комплекта 1 (glossary.md)"), "\n".join(lines)
    assert not (out / "traceability-matrix.md").exists()


def test_dirty_without_out_warns(tmp_path):
    src = git_commit(make_src(tmp_path))
    _w(src / "docs/srs/new.md", "# новый\n")
    lines, ready, _ = _run(src)
    assert _has(lines, "⚠ [CORE-05] незакоммиченные изменения в каталоге комплекта: 1 (srs/new.md)")


def test_service_files_and_outside_kit_changes_ignored(tmp_path):
    src = git_commit(make_src(tmp_path))
    _w(src / "docs/feedback.md", "# FB правка\n")       # служебный файл — не переносится
    _w(src / "open-questions.md", "# OQ\n")             # вне каталога комплекта
    out = _target(tmp_path)
    lines, ready, _ = _run(src, out=out)
    assert ready and _has(lines, "✓ [CORE-05] каталог комплекта без незакоммиченных изменений"), \
        "\n".join(lines)


def test_not_git_kit(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path))
    assert ready and _has(lines, "i [CORE-05] каталог комплекта не под git — версия не фиксируется")
    lines, ready, _ = _run(make_src(tmp_path / "b"), out=_target(tmp_path))
    assert not ready and _has(lines, "✗ [CORE-05] каталог комплекта не под git")
