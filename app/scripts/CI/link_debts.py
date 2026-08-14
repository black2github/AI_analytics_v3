# app/scripts/CI/link_debts.py
#
# Сторож долгов ссылок: URL несёт два смысла — семантический (связь) и
# навигационный (переход). Семантику держит матрица трассировки; навигацию
# восстанавливает заход-создатель цели (правило create-artifact «закрытие
# входящих долгов»). Утилита проверяет, что механизм не молчит:
#
#   1) ПРОСРОЧКА: долг, чья цель уже существует в комплекте, — брак
#      (заход-создатель не закрыл входящие долги: ссылка не проставлена).
#   2) ИСПОЛНИМОСТЬ: дословное имя долга находится в документе-ожидателе
#      (иначе долг нельзя закрыть механической заменой «имя → ссылка» —
#      нарушена дословность упоминания, чинить в документе).
#
# Формат строки долга в матрице (create-artifact, шаг 6):
#   | <FROM-ID[, FROM-ID…]> | — | нет целевого артефакта <тип> «<дословное имя>» — требуется заход <скилл> |
# Имя опционально для однофайловых типов (rbac): существование проверяется
# по типу в реестре ID. Диапазоны FROM («FUN-BNK-01…05») разворачиваются.
#
# Стадии запуска (одна утилита, три рубежа): самопроверка агента в заходе →
# приёмка эксперта → CI docs-репо (после переезда комплекта).
#
# Мягкий гейт: код 0 и отчёт; --strict — код 2 при нарушениях.

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_DEBT_RE = re.compile(
    r"нет целевого артефакта\s+([\w./-]+)(?:\s+«([^»]+)»)?", re.IGNORECASE)
_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_RANGE_RE = re.compile(r"^(.*?)(\d+)\s*(?:…|\.\.\.)\s*(\d+)$")
_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$")


def _norm(s: str) -> str:
    s = re.sub(r"[«»\"'`]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _expand_from(cell: str) -> List[str]:
    ids: List[str] = []
    for tok in re.split(r"[,;]\s*", cell.strip()):
        tok = tok.strip().strip("*").strip()
        if not tok or tok in "—-":
            continue
        m = _RANGE_RE.match(tok)
        if m:
            prefix, a, b = m.group(1), m.group(2), m.group(3)
            width = len(a)
            ids.extend(f"{prefix}{i:0{width}d}"
                       for i in range(int(a), int(b) + 1))
        else:
            ids.append(tok)
    return ids


def _doc_title(path: Path) -> Optional[str]:
    """title из frontmatter; YAML-перенос длинного значения склеивается."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return None
    lines = body.splitlines()
    for i, ln in enumerate(lines[1:60], start=1):
        if ln.strip() == "---":
            return None
        m = _TITLE_RE.match(ln)
        if not m:
            continue
        v = m.group(1)
        q = v[0] if v and v[0] in "'\"" else None
        closed = (q is None or (len(v) >= 2 and v.endswith(q)
                                and not v.endswith(q * 2)))
        j = i + 1
        while not closed and j < len(lines) and lines[j].startswith(" "):
            v += " " + lines[j].strip()
            closed = v.endswith(q) and not v.endswith(q * 2)
            j += 1
        if q and len(v) >= 2 and v.endswith(q):
            v = v[1:-1]
            if q == "'":
                v = v.replace("''", "'")
        return v
    return None


def parse_matrix(matrix_text: str):
    """(реестр: ID -> (тип, файл), долги: [(from_ids, тип, имя|None, строка)])."""
    registry: Dict[str, Tuple[str, str]] = {}
    debts: List[Tuple[List[str], str, Optional[str], str]] = []
    for ln in matrix_text.splitlines():
        row = _ROW_RE.match(ln)
        if not row:
            continue
        cells = [c.strip() for c in row.group(1).split("|")]
        joined = " ".join(cells)
        m = _DEBT_RE.search(joined)
        if m:
            debts.append((_expand_from(cells[0]), m.group(1),
                          m.group(2), ln.strip()))
            continue
        # реестр ID: | ID | Тип | Наименование | Файл |
        if (len(cells) >= 4 and re.match(r"^[A-ZА-Я]{2,}[-\w]*-?\d*$", cells[0])
                and cells[3].endswith(".md")):
            registry[cells[0]] = (cells[1], cells[3])
    return registry, debts


def check(matrix_path: Path, docs_root: Path):
    registry, debts = parse_matrix(
        matrix_path.read_text(encoding="utf-8", errors="replace"))
    # титулы и типы существующих артефактов комплекта
    titles: Dict[Path, str] = {}
    for p in docs_root.rglob("*.md"):
        t = _doc_title(p)
        if t:
            titles[p] = _norm(t)
    types_present = {t for t, _f in registry.values()}
    report: List[str] = []
    ok = True
    for from_ids, typ, name, raw in debts:
        # 1) просрочка: цель существует?
        target = None
        if name and len(_norm(name)) >= 10:
            nname = _norm(name)
            target = next((p for p, t in titles.items() if nname in t), None)
        elif not name:
            target = typ if typ.lower() in {t.lower() for t in types_present} \
                else None
        if target:
            report.append(f"ПРОСРОЧЕН долг: цель существует "
                          f"({target if isinstance(target, str) else target.name}), "
                          f"ссылка не проставлена ✗ — {raw[:100]}")
            ok = False
        # 2) исполнимость: имя находится в документах-ожидателях
        if not name:
            continue
        nname = _norm(name)
        for fid in from_ids:
            reg = registry.get(fid)
            if not reg:
                report.append(f"долг от {fid}: ID отсутствует в реестре "
                              f"матрицы ✗ — {raw[:80]}")
                ok = False
                continue
            doc = docs_root / reg[1]
            if not doc.is_file():
                report.append(f"долг от {fid}: файл реестра не найден "
                              f"({reg[1]}) ✗")
                ok = False
                continue
            body = _norm(doc.read_text(encoding="utf-8", errors="replace"))
            if nname not in body:
                report.append(
                    f"долг НЕИСПОЛНИМ: имя «{name}» не найдено дословно в "
                    f"{reg[1]} ✗ (замена «имя → ссылка» невозможна — "
                    "дословность упоминания нарушена)")
                ok = False
    if ok:
        report.append(f"OK: долгов {len(debts)}, просроченных нет, "
                      "все имена находятся в документах-ожидателях ✓")
    return report, ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Сторож долгов ссылок: просрочка (цель существует, "
                    "ссылки нет) и исполнимость (имя находится дословно).")
    ap.add_argument("--matrix", type=Path, required=True)
    ap.add_argument("--docs", type=Path, required=True,
                    help="корень docs/ комплекта")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    report, ok = check(args.matrix, args.docs)
    for ln in report:
        print(f"# {ln}")
    return 0 if ok or not args.strict else 2


if __name__ == "__main__":
    sys.exit(main())
