# app/scripts/CI/source_inventory.py
#
# Механическая опись выгрузки Confluence для плана миграции (У-1,
# песочница точек расширения, 2026-08-25). Принцип: полноту описи
# гарантирует ГЕНЕРАЦИЯ, а не добросовестность LLM — скелет строит
# скрипт, LLM дополняет ТОЛЬКО свои колонки («целевой тип (гипотеза)»,
# «основание»); --check ловит потерю строк, лишние строки и правку
# скриптовых колонок (анти-подгонка). Потерянная страница — видимый
# брак, не тихая дыра.
#
# Сигналы классификации (титул, родитель-в-дереве, requirement_type
# экспортёра) — ПОДСКАЗКИ, не вердикт: тип назначает LLM/аналитик;
# рассогласование сигналов или unknown — кандидат на точечное чтение
# (эвристика аналитика 2026-08-25).
#
#   python source_inventory.py --sources <выгрузка> --out inventory.md
#   python source_inventory.py --sources <выгрузка> --check inventory.md
#
# Read-only по выгрузке; --out пишет только файл описи. Код 2 при
# браке --check.

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PID_RE = re.compile(r"^confluence_page_id:\s*['\"]?(\d+)['\"]?", re.M)
_TITLE_RE = re.compile(r"^title:\s*(.+)$", re.M)
_RTYPE_RE = re.compile(r"^requirement_type:\s*(\S+)", re.M)

# колонки скелета (заполняет скрипт; правка = брак --check)
_SCRIPT_COLS = ("page_id", "title", "родитель", "req_type", "строк")
# колонки LLM (скелет оставляет пустыми)
_LLM_COLS = ("целевой тип (гипотеза)", "основание")


def _cell(v: str) -> str:
    """Значение в ячейку pipe-таблицы: | экранируется, пробелы жмутся."""
    return re.sub(r"\s+", " ", str(v)).strip().replace("|", "\\|")


def _uncell(v: str) -> str:
    return v.replace("\\|", "|").strip()


def scan(sources: Path):
    """(строки описи, счётчики). Строка: dict по _SCRIPT_COLS.
    index.md — навигация экспортёра, в опись не входит (считается);
    файл без frontmatter/page_id НЕ теряется — строка с page_id "—"."""
    rows: List[Dict[str, str]] = []
    n_index = 0
    for p in sorted(sources.rglob("*.md")):
        if p.name.lower() == "index.md":
            n_index += 1
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        head = text[:4000]
        pid = _PID_RE.search(head)
        t_m = _TITLE_RE.search(head)
        rtype = _RTYPE_RE.search(head)
        # дефект экспортёра (выгрузка КК, 2026-08-25): title обрезается
        # по длине с НЕзакрытой кавычкой — хвосты титулов теряются и
        # порождают ложные «дубли» (v.2.1/v.2.2 съедены). Детект:
        # открывающая кавычка без парной закрывающей; маркер «⋯» в
        # описи, полный титул — в имени файла выгрузки.
        raw_t = t_m.group(1).strip() if t_m else None
        truncated = bool(raw_t) and raw_t[:1] in "'\"" and (
            len(raw_t) < 2 or raw_t[-1] != raw_t[0])
        rows.append({
            "page_id": pid.group(1) if pid else "—",
            "title": ((raw_t.strip("'\"").strip() + (" ⋯" if truncated
                                                     else ""))
                      if raw_t else p.stem),
            "родитель": p.parent.name if p.parent != sources else "(корень)",
            "req_type": rtype.group(1) if rtype else "—",
            "строк": str(text.count("\n") + 1),
        })
    return rows, n_index


def _dupes(rows: List[Dict[str, str]], col: str) -> List[str]:
    seen: Dict[str, int] = {}
    for r in rows:
        v = r[col]
        if v != "—":
            seen[v] = seen.get(v, 0) + 1
    return sorted(v for v, n in seen.items() if n > 1)


def build(sources: Path) -> List[str]:
    rows, n_index = scan(sources)
    out = [f"# Опись выгрузки: {sources}", ""]
    out.append("Скелет построен механически (source_inventory.py). "
               "Заполнению LLM подлежат ТОЛЬКО две последние колонки; "
               "остальные колонки и состав строк не изменяются — "
               "проверяется --check. Сигналы (титул/родитель/req_type) — "
               "подсказки, не вердикт: рассогласование или unknown — "
               "кандидат на точечное чтение, в «основание» пишется "
               "«сигналы согласны» / «прочитано: <вывод>» / «вопрос N».")
    out.append("")
    hdr = list(_SCRIPT_COLS) + list(_LLM_COLS)
    out.append("| " + " | ".join(hdr) + " |")
    out.append("|" + "---|" * len(hdr))
    for r in rows:
        out.append("| " + " | ".join(
            [_cell(r[c]) for c in _SCRIPT_COLS] + ["", ""]) + " |")
    out.append("")
    dup_pid = _dupes(rows, "page_id")
    dup_title = _dupes(rows, "title")
    no_pid = sum(1 for r in rows if r["page_id"] == "—")
    n_trunc = sum(1 for r in rows if r["title"].endswith("⋯"))
    out.append(f"ИТОГО: страниц {len(rows)}; навигационных index.md "
               f"{n_index} (в опись не входят); без page_id {no_pid}; "
               f"дублей page_id {len(dup_pid)}; дублей title "
               f"{len(dup_title)}; титулов обрезано экспортёром "
               f"{n_trunc} (маркер ⋯; полный титул — в имени файла "
               "выгрузки)")
    if dup_pid:
        out.append(f"⚠ дубли page_id: {', '.join(dup_pid[:10])}")
    if dup_title:
        out.append("⚠ дубли title (ключом быть не могут): "
                   + "; ".join(dup_title[:5]))
    return out


def _parse_inventory(text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    hdr: Optional[List[str]] = None
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [_uncell(c) for c in
                 re.split(r"(?<!\\)\|", s.strip("|"))]
        if hdr is None:
            hdr = [c.strip() for c in cells]
            continue
        if all(re.fullmatch(r":?-+:?", c.strip()) for c in cells if c.strip()):
            continue
        if len(cells) < len(hdr):
            cells += [""] * (len(hdr) - len(cells))
        rows.append({hdr[i].strip(): cells[i].strip()
                     for i in range(len(hdr))})
    return rows


def check(sources: Path, inv_path: Path) -> Tuple[List[str], bool]:
    fresh, _ = scan(sources)
    inv = _parse_inventory(
        inv_path.read_text(encoding="utf-8", errors="replace"))
    report: List[str] = []
    ok = True
    # ключ сравнения: page_id, для строк без него — title
    def key(r):
        return r.get("page_id", "—") if r.get("page_id", "—") != "—" \
            else "t:" + r.get("title", "")
    fresh_m = {key(r): r for r in fresh}
    inv_m = {key(r): r for r in inv}
    lost = sorted(set(fresh_m) - set(inv_m))
    extra = sorted(set(inv_m) - set(fresh_m))
    if lost:
        ok = False
        report.append(f"ПОТЕРЯНЫ строки описи ×{len(lost)} — страницы "
                      "выгрузки без строки (полнота нарушена): "
                      + ", ".join(lost[:10]) + " ✗")
    if extra:
        ok = False
        report.append(f"ЛИШНИЕ строки описи ×{len(extra)} (в выгрузке "
                      "таких страниц нет): " + ", ".join(extra[:10]) + " ✗")
    changed = []
    for k in set(fresh_m) & set(inv_m):
        for c in _SCRIPT_COLS:
            if _uncell(inv_m[k].get(c, "")) != fresh_m[k][c]:
                changed.append(f"{k}.{c}")
    if changed:
        ok = False
        report.append(f"ИЗМЕНЕНЫ скриптовые колонки ×{len(changed)} "
                      "(правке подлежат только колонки LLM): "
                      + ", ".join(sorted(changed)[:10]) + " ✗")
    empty = sum(1 for r in inv
                if not r.get(_LLM_COLS[0], "").strip())
    report.append(f"ПРОВЕРКА ОПИСИ: страниц {len(fresh)}, строк описи "
                  f"{len(inv)}, потеряно {len(lost)}, лишних "
                  f"{len(extra)}, правок скриптовых колонок "
                  f"{len(changed)}, без гипотезы {empty}; вердикт: "
                  + ("OK" if ok else "БРАК"))
    return report, ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Механическая опись выгрузки: скелет (--out) и "
                    "валидация полноты/неизменности (--check).")
    ap.add_argument("--sources", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--check", type=Path, default=None)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if args.out is None and args.check is None:
        ap.error("нужен --out (скелет) или --check (валидация)")
    if args.out is not None:
        lines = build(args.sources)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(lines[-1] if not lines[-1].startswith("⚠") else
              [l for l in lines if l.startswith("ИТОГО")][0])
        print(f"скелет: {args.out}")
    if args.check is not None:
        report, ok = check(args.sources, args.check)
        for ln in report:
            print(ln)
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
