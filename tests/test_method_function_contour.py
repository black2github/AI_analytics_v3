# tests/test_method_function_contour.py
"""Сторож «контур функции метода не совпадает с контуром контракта» (шаблоны internal-contracts.md и
function.md, норма канона 14.11.2026; решение постановщика 14.11): пара «функция ↔ контракт» по
ссылке «по контракту» или общей странице, контур функции — префикс ID, контракта — подкаталог
internal-contract/<client|bank|system>/, «Авторизация» — вторым источником без подкаталога.
Несрабатывание: совпадающие контуры, общая страница без контракта, js-api, слот части в ID,
расхождение подкаталога с «Авторизацией» (отдельный класс)."""
import sys
from pathlib import Path

from app.scripts.CI.kitcheck.checks.method_function_contour import (
    auth_contours, check_method_function_contour, contract_contours, find_pairs, fun_contour)

OUT = "   · "


def intc(cid: str, page: str = "1000001", auth: str = "Bearer token") -> str:
    return (f"---\nid: {cid}\ntitle: 'Метод'\ntype: internal-contract\nservice: x\n"
            f"confluence_page_ids: ['{page}']\n---\n\n# {cid}. Метод\n\n## 1. Краткое описание\n\n"
            f"| Поле | Значение |\n|---|---|\n| **Авторизация:** | {auth} |\n")


def fun(fid: str, page: str = "1000001", link: str = "") -> str:
    body = f"Входные и исходящие параметры — по контракту [INTC]({link}).\n" if link else "Текст.\n"
    return (f"---\nid: {fid}\ntitle: 'Функция'\ntype: function\nservice: x\n"
            f"confluence_page_ids: ['{page}']\n---\n\n# {fid}. Функция\n\n## 4. Параметры\n\n" + body)


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _run(tmp_path: Path, files):
    docs = tmp_path / "docs"
    for rel, text in files.items():
        _w(docs / rel, text)
    return check_method_function_contour(docs)


C = "srs/internal-contract"
F = "srs/function"


# --- части признака ---

def test_fun_contour_by_id_prefix():
    assert fun_contour("FUN-SYS-13") == "SYS"
    assert fun_contour("FUN-CL-64") == "CL"
    assert fun_contour("FUN-BNK-04") == "BNK"
    assert fun_contour("FUN-BC-SYS-01") == "SYS"  # слот части
    assert fun_contour("FUN-MB-SYS-01") == "SYS"
    assert fun_contour("FUN-001") is None
    assert fun_contour("FUN-GRP-01") is None


def test_contract_contours_subdir_then_auth():
    bearer = ["| **Авторизация:** | Bearer token |"]
    assert contract_contours("srs/internal-contract/client/intc-001.md", []) == {"CL"}
    assert contract_contours("srs/bc/internal-contract/bank/intc-001.md", []) == {"BNK"}
    # подкаталог главнее «Авторизации»: расхождение — отдельный класс
    assert contract_contours("srs/internal-contract/system/intc-001.md", bearer) == {"SYS"}
    # без подкаталога — однозначная «Авторизация»
    assert contract_contours("srs/internal-contract/intc-001.md", bearer) == {"CL", "BNK"}
    assert contract_contours("srs/internal-contract/intc-001.md", ["**Авторизация:** Basic authorization"]) == {"SYS"}
    assert contract_contours("srs/internal-contract/intc-001.md", ["| **Авторизация** | ТУЗ, Bearer token |"]) is None
    assert contract_contours("srs/internal-contract/intc-001.md", ["| **Авторизация:** | — |"]) is None
    assert contract_contours("srs/internal-contract/intc-001.md", []) is None
    assert auth_contours(["Код авторизации в тексте"]) is None


# --- срабатывание ---

def test_system_function_for_client_contract_by_link(tmp_path):
    rep = _run(tmp_path, {
        f"{C}/client/intc-001-x.md": intc("INTC-001"),
        f"{F}/system/fun-sys-13-x.md": fun("FUN-SYS-13", page="2000002",
                                            link="../../internal-contract/client/intc-001-x.md"),
    })
    assert rep[0].startswith("⚠ функция метода — контур функции не совпадает с контуром контракта: 1 пар "
                             "(FUN-SYS-13 ↔ INTC-001) — контур функции метода — по подкаталогу контракта")
    assert rep[1:] == [OUT + "srs/function/system/fun-sys-13-x.md (FUN-SYS-13) ↔ srs/internal-contract/client/"
                       "intc-001-x.md (INTC-001), пара по ссылке — функция системная (FUN-SYS), по контракту — "
                       "клиентская (FUN-CL)"]


def test_pair_by_shared_page(tmp_path):
    rep = _run(tmp_path, {
        f"{C}/bank/intc-001-x.md": intc("INTC-001"),
        f"{F}/system/fun-sys-01-x.md": fun("FUN-SYS-01"),
    })
    assert len(rep) == 2 and rep[1].endswith("пара по странице — функция системная (FUN-SYS), по контракту — "
                                             "банковская (FUN-BNK)")


def test_auth_without_subdir(tmp_path):
    rep = _run(tmp_path, {f"{C}/intc-001-x.md": intc("INTC-001", auth="Basic authorization"),
                          f"{F}/client/fun-cl-01-x.md": fun("FUN-CL-01")})
    assert len(rep) == 2 and "по контракту — системная (FUN-SYS)" in rep[1]
    rep = _run(tmp_path / "b", {f"{C}/intc-001-x.md": intc("INTC-001"),
                                f"{F}/bank/fun-bnk-01-x.md": fun("FUN-BNK-01")})
    assert rep == []  # Bearer: клиентская или банковская


def test_link_pair_overrides_page_pair(tmp_path):
    # функция ссылается на контракт client/ и делит страницу с контрактом system/: верим ссылке
    files = {
        f"{C}/client/intc-001-x.md": intc("INTC-001", page="3000003"),
        f"{C}/system/intc-002-y.md": intc("INTC-002", page="1000001"),
        f"{F}/client/fun-cl-05-x.md": fun("FUN-CL-05", link="../../internal-contract/client/intc-001-x.md"),
    }
    assert _run(tmp_path, files) == []
    pairs = [(fid, cid, how) for _f, fid, _c, cid, how in find_pairs(tmp_path / "docs")]
    assert pairs == [("FUN-CL-05", "INTC-001", "ссылка")]


# --- несрабатывание ---

def test_matching_contours_silent(tmp_path):
    rep = _run(tmp_path, {
        f"{C}/system/intc-001-x.md": intc("INTC-001", page="1000001", auth="Basic authorization"),
        f"{F}/system/fun-sys-01-x.md": fun("FUN-SYS-01", page="1000001"),
        f"{C}/client/intc-002-x.md": intc("INTC-002", page="1000002"),
        f"{F}/client/fun-cl-02-x.md": fun("FUN-CL-02", page="1000002"),
        f"{C}/bank/intc-003-x.md": intc("INTC-003", page="1000003"),
        f"{F}/bank/fun-bnk-03-x.md": fun("FUN-BNK-03", page="1000003",
                                          link="../../internal-contract/bank/intc-003-x.md"),
    })
    assert rep == []


def test_shared_page_without_contract_silent(tmp_path):
    rep = _run(tmp_path, {
        f"{F}/system/fun-sys-01-x.md": fun("FUN-SYS-01", page="1000001"),
        "srs/process/proc-001-x.md": fun("PROC-001", page="1000001").replace("type: function", "type: process"),
        f"{C}/client/intc-001-x.md": intc("INTC-001", page="9000009"),
    })
    assert rep == []


def test_empty_page_lists_do_not_pair(tmp_path):
    # пустой confluence_page_ids у обеих карточек — не общая страница
    rep = _run(tmp_path, {
        f"{C}/client/intc-004-x.md": intc("INTC-004").replace("['1000001']", "[]"),
        f"{F}/bank/fun-bnk-04-x.md": fun("FUN-BNK-04").replace("['1000001']", "[]"),
    })
    assert rep == []


def test_js_api_part_silent(tmp_path):
    rep = _run(tmp_path, {
        "srs/widgets-rtl/internal-contract/client/intc-014-pin.md":
            intc("INTC-014", page="2211206719", auth="— (вне контура Экосистемы)"),
        "srs/widgets-rtl/function/client/fun-cl-64-pin.md": fun("FUN-CL-64", page="2211206719"),
    })
    assert rep == []


def test_part_slot_in_id_silent(tmp_path):
    rep = _run(tmp_path, {
        "srs/internal-contract/system/intc-bc-001-x.md": intc("INTC-BC-001", auth="Basic authorization"),
        "srs/function/system/fun-bc-sys-01-x.md": fun("FUN-BC-SYS-01",
                                                      link="../../internal-contract/system/intc-bc-001-x.md"),
    })
    assert rep == []


def test_subdir_vs_auth_mismatch_not_mixed(tmp_path):
    # контракт в system/ с Bearer — отдельный класс; FUN-SYS по подкаталогу — совпадение
    rep = _run(tmp_path, {f"{C}/system/intc-mb-002-x.md": intc("INTC-MB-002"),
                          f"{F}/system/fun-mb-sys-02-x.md": fun("FUN-MB-SYS-02")})
    assert rep == []


def test_link_in_code_block_and_other_line_ignored(tmp_path):
    body = ("```\nпо контракту [INTC](../../internal-contract/client/intc-001-x.md)\n```\n\n"
            "Вызов на эндпоинт контракта [INTC](../../internal-contract/client/intc-001-x.md).\n")
    f = fun("FUN-SYS-01", page="5000005").replace("Текст.\n", body)
    rep = _run(tmp_path, {f"{C}/client/intc-001-x.md": intc("INTC-001"), f"{F}/system/fun-sys-01-x.md": f})
    assert rep == []


# --- реестр selfcheck и гейт переноса ---

def test_selfcheck_registry_warning_only(tmp_path):
    from app.scripts.CI import selfcheck as sc
    chk = [c for c in sc.KIT_CHECKS if getattr(c, "id", None) == "method_function_contour"]
    assert len(chk) == 1 and chk[0].affects_verdict is False
    docs = tmp_path / "docs"
    _w(docs / f"{C}/client/intc-001-x.md", intc("INTC-001"))
    _w(docs / f"{F}/system/fun-sys-01-x.md", fun("FUN-SYS-01"))
    rep, ok = chk[0].run(type("Ctx", (), {"docs": docs})())
    assert ok is True and rep[0].startswith("⚠ функция метода — контур функции не совпадает")


def test_transfer_gate_carries_warning(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_transfer_gate as ttg  # noqa: E402 — сборка комплекта и прогон гейта
    src = ttg.make_src(tmp_path)
    _w(src / f"docs/{C}/client/intc-001-x.md", intc("INTC-001"))
    _w(src / f"docs/{F}/system/fun-sys-01-x.md", fun("FUN-SYS-01"))
    lines, _ready, _ = ttg._run(src)
    got = [l for l in lines if "функция метода — " in l]
    assert any(l.startswith("⚠ [ПРИБОР] функция метода — контур функции не совпадает") for l in got)
    assert not any(l.startswith("✗") for l in got)
