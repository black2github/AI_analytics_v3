# -*- coding: utf-8 -*-
"""Гейт переноса и сторож каталога НФТ в двух раскладках (постановка «AI Factory» 2026-11-19,
часть Б). Б1 — сторож находит каталог в корне комплекта (целевая раскладка) и рядом с ним
(рабочая раскладка канона output/<service>/nfr); оба — ✗; ни одного — молчит. Б2 — гейт в полном
режиме кладёт каталог nfr/ рядом с docs/ в корень сборки (строка i с числом страниц), сторож на
сборке его видит, --out переносит; режим репозитория документации — сборка прежняя."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
from kitcheck.checks.nfr import _NFR_TYPE_BY_CODE, check_nfr_catalog  # noqa: E402
from tests.test_transfer_gate import (  # noqa: E402,F401 — platform_catalog: сервис X платформенный
    _target, _w, make_docs_repo, make_src, platform_catalog)

_HDR = "| ID | Параметр | Допустимое значение | Пояснение |\n|---|---|---|---|\n"


def _nfr(d: Path, readme: bool = True) -> Path:
    """Законный каталог НФТ: README-реестр и 18 страниц-скелетов с единой таблицей."""
    if readme:
        _w(d / "README.md", "---\nid: nfr\ntype: nfr\n---\n# Реестр НФТ\n")
    for code, name in _NFR_TYPE_BY_CODE.items():
        _w(d / f"nfr-{code}.md", f"---\nid: nfr-{code}\ntype: nfr\nnfr_type: {name}\n"
                                 f"ingress: reverse\nconfluence_page_ids: [2166860001]\n---\n# {name}\n\n{_HDR}")
    return d


def _registered(src: Path) -> Path:
    """Каталог в целевом корне — документы комплекта: строки «Реестра ID» (норма nfr.md: страница
    типа — из реестра матрицы) и тип nfr в легенде README."""
    from tests.test_transfer_gate import _MATRIX, _README
    rows = "| nfr | Реестр НФТ | `nfr/README.md` |\n" + "".join(
        f"| nfr-{c} | {n} | `nfr/nfr-{c}.md` |\n" for c, n in _NFR_TYPE_BY_CODE.items())
    _w(src / "docs/traceability-matrix.md", _MATRIX.replace("| VIS-001 |", rows + "| VIS-001 |"))
    _w(src / "docs/README.md", _README.replace("| **FUN** | Функция |",
                                               "| **FUN** | Функция |\n| `nfr` | Каталог НФТ |"))
    return src


def _run(src: Path, **kw):
    kw.setdefault("no_validator", True)
    return tg.run_gate(src, **kw)


def _has(lines, prefix):
    return any(l.startswith(prefix) for l in lines)


# ---------------------------------------------------------------- Б1: сторож

def test_catalog_in_kit_root_checked(tmp_path):
    root = tmp_path / "docs-x"
    _w(root / "README.md", "# К\n")
    _w(root / "traceability-matrix.md", "# М\n")
    _nfr(root / "nfr")
    report, ok = check_nfr_catalog(root)
    assert ok and report[0] == "i каталог НФТ: nfr/ в корне комплекта", report
    assert report[-1].startswith("✓ nfr: каталог НФТ"), report


def test_catalog_beside_kit_root_checked(tmp_path):
    docs = tmp_path / "output/svc/docs"
    _w(docs / "README.md", "# К\n")
    _w(docs / "traceability-matrix.md", "# М\n")
    _nfr(tmp_path / "output/svc/nfr", readme=False)
    report, ok = check_nfr_catalog(docs)
    assert not ok and report[0] == "i каталог НФТ: ../nfr/ рядом с корнем комплекта", report
    assert any(r.endswith("нет README.md реестра") for r in report), report


def test_defect_found_in_kit_root_catalog(tmp_path):
    # прежде каталог в корне комплекта не проверялся вовсе (замер 19.11: docs-file-storage-service)
    root = tmp_path / "docs-x"
    _w(root / "README.md", "# К\n")
    _nfr(root / "nfr", readme=False)
    report, ok = check_nfr_catalog(root)
    assert not ok and any(r.endswith("нет README.md реестра") for r in report), report


def test_two_catalogs_blocked(tmp_path):
    docs = tmp_path / "src-x/docs"
    _w(docs / "README.md", "# К\n")
    _nfr(docs / "nfr")
    _nfr(tmp_path / "src-x/nfr")
    report, ok = check_nfr_catalog(docs)
    assert not ok and report == ["✗ два каталога НФТ: nfr/ в корне комплекта и ../nfr/ рядом с ним — "
                                 "какой действует, прибор не решает; оставить один"], report


def test_no_catalog_silent(tmp_path):
    root = tmp_path / "docs-x"
    _w(root / "README.md", "# К\n")
    assert check_nfr_catalog(root) == ([], True)


# ---------------------------------------------------------------- Б2: гейт

def test_gate_stages_catalog_beside_docs(tmp_path):
    src = make_src(tmp_path)
    _nfr(src / "nfr")
    keep = tmp_path / "staged"
    lines, ready, _ = _run(src, keep=keep)
    assert _has(lines, "i [TRF-01] каталог НФТ: 19 страниц — в сборке, раздел nfr/ целевого корня"), \
        "\n".join(lines)
    assert (keep / "nfr/README.md").is_file() and (keep / "nfr/nfr-prf.md").is_file()
    assert len(list((keep / "nfr").glob("*.md"))) == 19


def test_gate_selfcheck_sees_staged_catalog(tmp_path):
    # сторож на сборке видит перенесённый каталог: дефект каталога — в вердикте прибора
    src = make_src(tmp_path)
    _nfr(src / "nfr", readme=False)
    lines, ready, _ = _run(src)
    assert not ready, "\n".join(lines)
    assert any("нет README.md реестра" in l for l in lines), "\n".join(lines)


def test_gate_out_copies_catalog(tmp_path):
    # сквозной сценарий: каталог НФТ рядом с docs/, строки реестра для страниц НФТ (ID иной
    # формы узнаются по id шапки — решение 19.11) — READY, --out переносит каталог
    from tests.test_transfer_gate import git_commit
    out = _target(tmp_path)
    src = _registered(make_src(tmp_path / "b"))
    _nfr(src / "nfr")
    lines, ready, _ = _run(git_commit(src), out=out)
    assert ready, "\n".join(lines)
    assert (out / "nfr/README.md").is_file() and (out / "nfr/nfr-mon.md").is_file()


def test_gate_without_catalog_unchanged(tmp_path):
    keep = tmp_path / "staged"
    lines, ready, _ = _run(make_src(tmp_path), keep=keep)
    assert not any("каталог НФТ" in l for l in lines)
    assert not (keep / "nfr").exists()


def test_gate_two_catalogs_blocked(tmp_path):
    src = make_src(tmp_path)
    _nfr(src / "nfr")
    _nfr(src / "docs/nfr")
    lines, ready, _ = _run(src)
    assert not ready and _has(lines, "✗ [TRF-01] два каталога НФТ: docs/nfr/ и nfr/ рядом с docs/"), \
        "\n".join(lines)


def test_docs_repo_catalog_checked_no_transfer_line(tmp_path):
    repo = make_docs_repo(tmp_path)
    _nfr(repo / "nfr", readme=False)
    lines, ready, data = _run(repo)
    assert data["docs_repo"] is True
    assert not any("в сборке, раздел nfr/" in l for l in lines), "\n".join(lines)
    assert not ready and any("нет README.md реестра" in l for l in lines), "\n".join(lines)


# ------------------------------------------- CORE-05: версия каталога НФТ, уходящего в --out

def _committed_with_nfr(tmp_path: Path) -> Path:
    from tests.test_transfer_gate import git_commit
    src = _registered(make_src(tmp_path / "b"))
    _nfr(src / "nfr")
    return git_commit(src)


def test_dirty_nfr_beside_docs_blocks_out(tmp_path):
    src = _committed_with_nfr(tmp_path)
    _w(src / "nfr/nfr-prf.md", (src / "nfr/nfr-prf.md").read_text(encoding="utf-8") + "\nправка\n")
    out = _target(tmp_path)
    lines, ready, _ = _run(src, out=out)
    assert not ready and _has(lines, "✗ [CORE-05] перенос из рабочего дерева: версию комплекта нельзя "
                                     "получить повторно — незакоммиченных изменений в каталоге "
                                     "комплекта и каталоге НФТ рядом с ним 1 (../nfr/nfr-prf.md)"), \
        "\n".join(lines)
    assert not (out / "nfr").exists()


def test_dirty_nfr_beside_docs_warns_without_out(tmp_path):
    src = _committed_with_nfr(tmp_path)
    _w(src / "nfr/nfr-new.md", "# x\n")
    lines, ready, _ = _run(src)
    assert _has(lines, "⚠ [CORE-05] незакоммиченные изменения в каталоге комплекта и каталоге НФТ "
                       "рядом с ним: 1 (../nfr/nfr-new.md)"), "\n".join(lines)


def test_clean_nfr_and_dirty_file_elsewhere_pass(tmp_path):
    # несрабатывание: чистый nfr/ — ✓; грязный файл вне docs/ и вне nfr/ не считается
    src = _committed_with_nfr(tmp_path)
    _w(src / "notes.md", "черновик\n")
    lines, ready, _ = _run(src, out=_target(tmp_path))
    assert ready and _has(lines, "✓ [CORE-05] каталог комплекта без незакоммиченных изменений "
                                 "(и каталог НФТ ../nfr/ рядом с ним)"), "\n".join(lines)


def test_without_nfr_core05_unchanged(tmp_path):
    from tests.test_transfer_gate import git_commit
    lines, ready, _ = _run(git_commit(make_src(tmp_path)))
    assert _has(lines, "✓ [CORE-05] каталог комплекта без незакоммиченных изменений")
    assert not any("../nfr/" in l for l in lines)
