# tests/test_function_placement.py
"""Сторож «контур функции: префикс идентификатора, каталог и имя файла» (шаблон function.md,
«Идентификация и размещение»; постановка прибору 2026-11-15, решение постановщика 15.11): ✗ строкой
на карточку. Несрабатывание: согласованные карточки трёх контуров, слот сервиса и части в
идентификаторе, суб-идентификатор «.N», старая раскладка functions/, часть вне контура Экосистемы,
README каталога, карточка другого типа в каталоге функций, идентификатор без контура."""
import sys
from pathlib import Path

from app.scripts.CI.kitcheck.checks.function_placement import (
    check_function_placement, id_contour, placement_defects)


def fun(fid: str, typ: str = "function") -> str:
    return f"---\nid: {fid}\ntitle: 'Функция'\ntype: {typ}\nservice: x\n---\n\n# {fid}. Функция\n"


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _run(tmp_path: Path, files):
    docs = tmp_path / "docs"
    for rel, text in files.items():
        _w(docs / rel, text)
    return check_function_placement(docs)


def test_id_contour():
    assert id_contour("FUN-CL-01") == "CL"
    assert id_contour("FUN-BNK-12") == "BNK"
    assert id_contour("FUN-SYS-07") == "SYS"
    assert id_contour("FUN-MB-SYS-01") == "SYS"  # слот части
    assert id_contour("FUN-DS-SYS-01.1") == "SYS"  # суб-идентификатор
    assert id_contour("FUN-001") is None
    assert id_contour("FUN-SYS-07-x") is None


# --- срабатывание ---

def test_prefix_vs_subdir_is_defect(tmp_path):
    rep, ok = _run(tmp_path, {"srs/multi-bank/function/bank/fun-mb-sys-01-add-cert.md": fun("FUN-MB-SYS-01")})
    assert ok is False
    assert rep == ["✗ функция FUN-MB-SYS-01 (srs/multi-bank/function/bank/fun-mb-sys-01-add-cert.md): префикс "
                   "идентификатора — контур system/, а карточка лежит в function/bank/ — контур, каталог и имя "
                   "файла согласуются: переложить карточку или исправить идентификатор по контуру функции "
                   "вместе со ссылками на неё (шаблон function.md, «Идентификация и размещение»)"]


def test_file_name_vs_id_is_defect(tmp_path):
    rep, ok = _run(tmp_path, {"srs/function/client/fun-cl-02-view.md": fun("FUN-CL-12")})
    assert ok is False and len(rep) == 1
    assert "имя файла не начинается с идентификатора строчными («fun-cl-12-…»)" in rep[0]
    assert "префикс идентификатора" not in rep[0]


def test_both_defects_one_line_and_root_dir(tmp_path):
    rep, ok = _run(tmp_path, {"srs/function/fun-x.md": fun("FUN-SYS-03")})
    assert ok is False and len(rep) == 1
    assert "контур system/, а карточка лежит в корне function/; имя файла не начинается" in rep[0]


def test_placement_defects_shapes():
    assert placement_defects("FUN-CL-01", "srs/function/client/fun-cl-01-x.md") == []
    assert placement_defects("FUN-CL-01", "srs/function/client/fun-cl-01.md") == []
    # «fun-cl-010» — не «fun-cl-01-…»: номер другой
    assert placement_defects("FUN-CL-01", "srs/function/client/fun-cl-010-x.md") == [
        "имя файла не начинается с идентификатора строчными («fun-cl-01-…»)"]


# --- несрабатывание ---

def test_consistent_cards_silent(tmp_path):
    rep, ok = _run(tmp_path, {
        "srs/function/client/fun-cl-01-a.md": fun("FUN-CL-01"),
        "srs/function/bank/fun-bnk-02-b.md": fun("FUN-BNK-02"),
        "srs/function/system/fun-sys-03-c.md": fun("FUN-SYS-03"),
        # слот сервиса и части
        "srs/bc-component/function/system/fun-bc-sys-01-d.md": fun("FUN-BC-SYS-01"),
        "srs/multi-bank/function/bank/fun-mb-bnk-01-e.md": fun("FUN-MB-BNK-01"),
        # суб-идентификатор
        "srs/document-signing/function/system/fun-ds-sys-01.1-error-summary.md": fun("FUN-DS-SYS-01.1"),
        # часть вне контура Экосистемы — то же размещение
        "srs/widgets-rtl/function/client/fun-cl-64-pin.md": fun("FUN-CL-64"),
    })
    assert rep == [] and ok is True


def test_legacy_functions_layout_checked_not_judged(tmp_path):
    rep, ok = _run(tmp_path, {
        "srs/functions/bank/fun-bnk-01-view.md": fun("FUN-BNK-01"),
        "srs/functions/client/fun-cl-01-x.md": fun("FUN-CL-01"),
    })
    assert rep == [] and ok is True
    # в старой раскладке подкаталог сверяется так же
    rep, ok = _run(tmp_path / "b", {"srs/functions/bank/fun-sys-01-x.md": fun("FUN-SYS-01")})
    assert ok is False and "лежит в functions/bank/" in rep[0]


def test_readme_other_type_and_no_contour_silent(tmp_path):
    rep, ok = _run(tmp_path, {
        "srs/function/README.md": fun("FUN-000"),
        "srs/function/client/README.md": fun("FUN-SYS-01"),
        # карточка другого типа в каталоге функций
        "srs/function/system/proc-001-x.md": fun("FUN-CL-01", typ="process"),
        # идентификатор без контура и карточка вне каталога функций
        "srs/function/client/fun-001-x.md": fun("FUN-001"),
        "srs/process/fun-sys-09-x.md": fun("FUN-SYS-09"),
    })
    assert rep == [] and ok is True


# --- реестр selfcheck и гейт переноса ---

def test_selfcheck_registry_affects_verdict(tmp_path):
    from app.scripts.CI import selfcheck as sc
    chk = [c for c in sc.KIT_CHECKS if getattr(c, "id", None) == "function_placement"]
    assert len(chk) == 1 and chk[0].affects_verdict is True
    docs = tmp_path / "docs"
    _w(docs / "srs/function/bank/fun-sys-01-x.md", fun("FUN-SYS-01"))
    rep, ok = chk[0].run(type("Ctx", (), {"docs": docs})())
    assert ok is False and rep[0].startswith("✗ функция FUN-SYS-01")


def test_transfer_gate_blocks(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_transfer_gate as ttg  # noqa: E402 — сборка комплекта и прогон гейта
    src = ttg.make_src(tmp_path)
    _w(src / "docs/srs/function/bank/fun-sys-01-x.md", fun("FUN-SYS-01"))
    lines, ready, _ = ttg._run(src)
    assert not ready
    assert any(l.startswith("✗ [ПРИБОР] функция FUN-SYS-01 (srs/function/bank/fun-sys-01-x.md): префикс")
               for l in lines)
