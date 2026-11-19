# app/scripts/CI/kitcheck/checks/call_ext_base.py
"""Внешний вызов ведёт к контракту (гейт переноса SDLC-02, постановка «AI Factory» 2026-11-19,
П11; ✗ включён по замеру 19.11: docs-business-cards 45 со ссылкой + 3 строки долга, эталон 12 + 1
срабатывание — CALL-EXT-013 без опубликованной базовой карточки и без строки долга, src-lk-mp 2;
ложных классов нет).

Карточка внешнего вызова — документ с ID формы `CALL-EXT-…` или `CALL-<часть>-EXT-…` (README-реестр
не считается). Она несёт ссылку на базовый контракт — markdown-ссылку на md-файл репозитория
`docs-external-contracts` (корень репозитория и каталог `examples/` не считаются), либо её ID —
FROM-ID строки раздела матрицы «Долги по ссылкам» (долг «у владельца» или иной: связь с контрактом
оформлена долгом). Иначе — отказ гейта с перечнем, в selfcheck — ⚠. Признаки — форма ID, адрес
ссылки, строка долга; слов источника нет. Слой — ядро.
"""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
import re
from pathlib import Path
from typing import List, Optional, Tuple
try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, read_frontmatter
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, read_frontmatter  # type: ignore

CALL_EXT_ID_RE = re.compile(r"^CALL-(?:[A-Z]+-)?EXT-\d")
BASE_CONTRACT_LINK_RE = re.compile(
    r"\]\(https?://[^)\s]*/docs-external-contracts/-/(?:blob|tree|raw)/(?![^)\s#?]*/examples/)"
    r"[^)\s#?]+\.md(?:[#?][^)\s]*)?\)")


def _debt_from_ids(matrix: Path) -> set:
    if not matrix.is_file():
        return set()
    try:
        import link_debts as ld  # noqa: E402 — разбор строк долга — один дом
    except ImportError:  # импорт пакетом app.scripts.CI (тесты)
        from ... import link_debts as ld  # type: ignore
    text = _fs.read_text(matrix, encoding="utf-8", errors="replace")
    return {x for d in ld.parse_matrix(text)[1] for x in d[0]}


def call_ext_without_contract(docs: Path) -> Optional[dict]:
    """{total: карточек внешнего вызова, linked, by_debt: [ID], missing: [ID]}; карточек нет —
    None."""
    cards: List[Tuple[str, Path]] = []
    for p in _kit_md(docs):
        if p.name.lower() == "readme.md":
            continue
        i = str((read_frontmatter(p) or {}).get("id", "") or "").strip().strip("'\"")
        if CALL_EXT_ID_RE.match(i):
            cards.append((i, p))
    if not cards:
        return None
    debts = _debt_from_ids(docs / "traceability-matrix.md")
    out = {"total": len(cards), "linked": 0, "by_debt": [], "missing": []}
    for i, p in sorted(cards):
        if BASE_CONTRACT_LINK_RE.search(_fs.read_text(p, encoding="utf-8", errors="replace")):
            out["linked"] += 1
        elif i in debts:
            out["by_debt"].append(i)
        else:
            out["missing"].append(i)
    return out


def call_ext_lines(res: Optional[dict]) -> List[Tuple[str, str]]:
    """(знак гейта полного режима, текст)."""
    if not res:
        return []
    m = res["missing"]
    tail = (f"; строкой долга — {len(res['by_debt'])} ({', '.join(res['by_debt'][:6])}"
            f"{'…' if len(res['by_debt']) > 6 else ''})" if res["by_debt"] else "")
    if m:
        return [("✗", f"карточки внешнего вызова без ссылки на базовый контракт: {len(m)} из "
                      f"{res['total']} ({', '.join(m[:8])}{'…' if len(m) > 8 else ''}) — добавить "
                      "ссылку на карточку контракта в docs-external-contracts либо строку долга "
                      "«у владельца» в матрице" + tail)]
    return [("✓", f"карточки внешнего вызова ведут к базовому контракту: ссылкой — "
                  f"{res['linked']} из {res['total']}" + tail)]
