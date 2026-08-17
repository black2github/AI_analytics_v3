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


_OQ_NUM_RE = re.compile(r"^##\s+OQ-(\d+)\b", re.M)

# Настраиваемые параметры: упоминание «[Настраиваемые параметры]
# <сервис>.<ключ>» в документах комплекта требует строки с этим ключом в
# разделе параметров data-model/dictionaries.md (conventions §5.2 —
# параметры фиксируются вместе со значениями; инцидент src-locks
# 2026-08-15: h2h_in_path/h2h_path_polling_time упоминались агентом и
# процессом, в справочнике отсутствовали, долг не заводился).
# пробелы вокруг точки допускаются: «БлокН2Н .h2h_out_path» — дефект
# набора источника прятал третий параметр от сторожа (src-locks)
_PARAM_MENTION_RE = re.compile(
    r"Настраиваемые параметры\W{0,4}\s+[\w-]+(?:\.[\w-]+)*\s*\.\s*(\w+)")


def check_config_params(docs_root: Path) -> Tuple[List[str], bool]:
    dicts = docs_root / "srs" / "data-model" / "dictionaries.md"
    dict_text = (dicts.read_text(encoding="utf-8", errors="replace")
                 if dicts.is_file() else "")
    missing: Dict[str, List[str]] = {}
    for p in docs_root.rglob("*.md"):
        if "data-model" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in _PARAM_MENTION_RE.finditer(text):
            key = m.group(1)
            if key not in dict_text:
                missing.setdefault(key, []).append(p.name)
    if missing:
        return [f"настраиваемые параметры без строки в dictionaries "
                f"(conventions §5.2): "
                + "; ".join(f"{k} ({', '.join(sorted(set(v))[:2])})"
                            for k, v in sorted(missing.items()))
                + " ✗ — требуется дозаход create-data-model"], False
    return [], True


_FB_NUM_RE = re.compile(r"^##\s+FB-(\d+)\b", re.M)


def _check_register_order(path: Path, num_re, prefix: str,
                          name: str) -> Tuple[List[str], bool]:
    """Общий сторож append-only реестров записей «## <PREFIX>-NN»:
    номера монотонно возрастают по позиции в файле; вставка в середину
    и перемещение записей при правке — брак."""
    if not path.is_file():
        return [], True
    nums = [int(m.group(1)) for m in num_re.finditer(
        path.read_text(encoding="utf-8", errors="replace"))]
    bad = [(a, b) for a, b in zip(nums, nums[1:]) if b < a]
    if bad:
        return [f"{name}: порядок реестра нарушен (append-only): "
                + ", ".join(f"{prefix}-{b:03d} стоит после {prefix}-{a:03d}"
                            for a, b in bad[:3]) + " ✗"], False
    return [f"{name}: порядок реестра append-only соблюдён "
            f"({len(nums)} записей) ✓"], True


def check_oq_order(oq_path: Path) -> Tuple[List[str], bool]:
    """Реестр open-questions — append-only (трёхкратный инцидент,
    третий — src-locks 2026-08-15: закрытая запись переехала в конец)."""
    return _check_register_order(oq_path, _OQ_NUM_RE, "OQ",
                                 "open-questions")


def check_feedback_order(fb_path: Path) -> Tuple[List[str], bool]:
    """Реестр замечаний команды feedback.md (цикл обратной связи,
    модель принята 2026-08-17) — та же дисциплина, что у OQ: записи
    FB-NN append-only, статусы правятся на месте."""
    return _check_register_order(fb_path, _FB_NUM_RE, "FB", "feedback")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Сторож долгов ссылок: просрочка (цель существует, "
                    "ссылки нет) и исполнимость (имя находится дословно); "
                    "плюс порядок реестра open-questions (append-only).")
    ap.add_argument("--matrix", type=Path, required=True)
    ap.add_argument("--docs", type=Path, required=True,
                    help="корень docs/ комплекта")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    report, ok = check(args.matrix, args.docs)
    oq = args.docs / "open-questions.md"
    if not oq.is_file():
        oq = args.docs.parent / "open-questions.md"
    oq_report, oq_ok = check_oq_order(oq)
    report.extend(oq_report)
    ok = ok and oq_ok
    # feedback.md живёт в корне репозитория (уровень сервиса, вне docs/)
    fb_report, fb_ok = check_feedback_order(
        args.docs.parent / "feedback.md")
    report.extend(fb_report)
    ok = ok and fb_ok
    cp_report, cp_ok = check_config_params(args.docs)
    report.extend(cp_report)
    ok = ok and cp_ok
    for ln in report:
        print(f"# {ln}")
    return 0 if ok or not args.strict else 2


if __name__ == "__main__":
    sys.exit(main())
