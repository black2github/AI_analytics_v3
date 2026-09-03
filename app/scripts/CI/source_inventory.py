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


def _full_title(head: str):
    """(титул, обрезан?). Длинный title экспортёр переносит по стандарту
    YAML (продолжение — строки с отступом); grep-подход видел только
    первую строку и ловил «обрезку» (уточнение аналитика 2026-08-26 —
    это легальный YAML, не дефект). Склеиваем перенос, как в
    link_debts/_doc_title; маркер обрезки остаётся только для титулов,
    у которых продолжение не нашлось (кавычка так и не закрылась)."""
    m = _TITLE_RE.search(head)
    if not m:
        return None, False
    v = m.group(1).strip()
    q = v[0] if v[:1] in "'\"" else None
    closed = (q is None
              or (len(v) >= 2 and v.endswith(q) and not v.endswith(q * 2)))
    if not closed:
        rest = head[m.end():].lstrip("\r\n").splitlines()
        for ln in rest:
            if not ln.startswith(" "):
                break
            v += " " + ln.strip()
            if v.endswith(q) and not v.endswith(q * 2):
                closed = True
                break
    if q and closed and len(v) >= 2:
        v = v[1:-1] if v.endswith(q) else v
        if q == "'":
            v = v.replace("''", "'")
        return v.strip(), False
    return v.strip("'\"").strip(), not closed

# колонки скелета (заполняет скрипт; правка = брак --check)
_SCRIPT_COLS = ("page_id", "title", "родитель", "req_type", "строк")
# колонки LLM (скелет оставляет пустыми)
_LLM_COLS = ("целевой тип (гипотеза)", "основание")
# колонки таблицы приложений (вся таблица скриптовая; правка = брак)
_ATT_COLS = ("файл", "страница-владелец (page_id)", "байт")


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
        rtype = _RTYPE_RE.search(head)
        title, truncated = _full_title(head)
        rows.append({
            "page_id": pid.group(1) if pid else "—",
            "title": ((title + (" ⋯" if truncated else ""))
                      if title else p.stem),
            "родитель": p.parent.name if p.parent != sources else "(корень)",
            "req_type": rtype.group(1) if rtype else "—",
            "строк": str(text.count("\n") + 1),
        })
    return rows, n_index


def _owner_pid(f: Path, sources: Path) -> str:
    """page_id страницы-владельца вложения: по конвенции экспортёра
    вложения лежат в каталогах страницы (files/, img/), а сама страница
    — md-сосед своего каталога уровнем выше. Поднимаемся от файла вверх
    до первого каталога, у которого есть md-сосед с page_id."""
    cur = f.parent
    while cur != sources and cur != cur.parent:
        md = cur.parent / (cur.name + ".md")
        if md.is_file():
            head = md.read_text(encoding="utf-8", errors="replace")[:4000]
            m = _PID_RE.search(head)
            return m.group(1) if m else "—"
        cur = cur.parent
    return "—"


def scan_attachments(sources: Path):
    """(строки приложений, число изображений). Приложение — любой
    не-markdown файл выгрузки вне каталогов img/ (изображения считаются
    числом: их перенос — существующая конвенция картинок карточек, в
    таблицу они не раздуваются). Файл без определимого владельца НЕ
    теряется — строка со страницей «—» (асимметрия: молчаливая потеря
    приложения хуже шума; мотив — приложенные XSD/JSON-схемы, которые
    опись страниц не видела вовсе)."""
    rows: List[Dict[str, str]] = []
    n_img = 0
    for p in sorted(sources.rglob("*")):
        if not p.is_file() or p.suffix.lower() == ".md":
            continue
        parts = p.relative_to(sources).parts
        if "img" in parts:
            n_img += 1
            continue
        rows.append({
            _ATT_COLS[0]: p.relative_to(sources).as_posix(),
            _ATT_COLS[1]: _owner_pid(p, sources),
            _ATT_COLS[2]: str(p.stat().st_size),
        })
    return rows, n_img


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
    att, n_img = scan_attachments(sources)
    out.append("")
    out.append("## Приложения (не-markdown файлы выгрузки)")
    out.append("")
    if att:
        out.append("| " + " | ".join(_ATT_COLS) + " |")
        out.append("|" + "---|" * len(_ATT_COLS))
        for r in att:
            out.append("| " + " | ".join(_cell(r[c]) for c in _ATT_COLS)
                       + " |")
        out.append("")
    no_owner = sum(1 for r in att if r[_ATT_COLS[1]] == "—")
    out.append(f"ИТОГО ПРИЛОЖЕНИЙ: файлов {len(att)}; изображений "
               f"{n_img} (каталоги img/ — конвенция картинок, в "
               "таблицу не входят)"
               + (f"; без страницы-владельца {no_owner}"
                  if no_owner else ""))
    return out


def refresh(sources: Path, inv_path: Path) -> List[str]:
    """--refresh: перегенерировать скриптовые колонки описи свежим
    сканом, СОХРАНИВ колонки LLM по ключу (page_id, для строк без него
    — title). Нужен, когда сканер улучшился после заполнения описи
    (прецедент 2026-08-26: фикс извлечения титулов с конечной кавычкой
    дал 72 ложных «правки скриптовых колонок» на честной описи)."""
    inv = _parse_inventory(
        inv_path.read_text(encoding="utf-8", errors="replace"))
    def key(r):
        pid = r.get("page_id", "—")
        return pid if pid != "—" else "t:" + r.get("title", "")
    old_llm = {key(r): [r.get(c, "") for c in _LLM_COLS] for r in inv}
    lines = build(sources)
    fresh, _ = scan(sources)
    kept = 0
    out: List[str] = []
    fi = iter(fresh)
    remaining = len(fresh)  # строки ПРИЛОЖЕНИЙ ниже таблицы страниц
    for ln in lines:        # LLM-колонок не имеют и не трогаются
        if remaining > 0 and ln.startswith("| ") \
                and not ln.startswith("| " + _SCRIPT_COLS[0]):
            r = next(fi)
            remaining -= 1
            llm = old_llm.get(key(r))
            if llm and any(v.strip() for v in llm):
                assert ln.rstrip().endswith("|  |  |")
                ln = (ln.rstrip()[:-len("|  |  |")]
                      + "| " + _cell(llm[0]) + " | " + _cell(llm[1]) + " |")
                kept += 1
        out.append(ln)
    out.append(f"ОБНОВЛЕНИЕ ОПИСИ: скриптовые колонки перегенерированы; "
               f"колонок LLM сохранено {kept}/{len(fresh)}")
    return out


def _parse_tables(text: str) -> List[Tuple[List[str], List[Dict[str, str]]]]:
    """Все pipe-таблицы файла: [(заголовки, строки)]. Опись стала
    многотабличной (страницы + приложения) — однотабличный парсер
    смешивал бы строки второй таблицы со строками первой."""
    tables: List[Tuple[List[str], List[Dict[str, str]]]] = []
    lines = text.splitlines()
    i = 0

    def _cells(s: str) -> List[str]:
        return [_uncell(c) for c in re.split(r"(?<!\\)\|", s.strip("|"))]

    def _is_sep(s: str) -> bool:
        return (s.startswith("|") and bool(s.strip("|").strip()) and
                all(re.fullmatch(r":?-+:?", c.strip())
                    for c in s.strip("|").split("|") if c.strip()))

    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("|") and i + 1 < len(lines) \
                and _is_sep(lines[i + 1].strip()):
            hdr = [c.strip() for c in _cells(s)]
            i += 2
            rows: List[Dict[str, str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _cells(lines[i].strip())
                if len(cells) < len(hdr):
                    cells += [""] * (len(hdr) - len(cells))
                rows.append({hdr[j]: cells[j].strip()
                             for j in range(len(hdr))})
                i += 1
            tables.append((hdr, rows))
            continue
        i += 1
    return tables


def _parse_inventory(text: str) -> List[Dict[str, str]]:
    """Строки таблицы СТРАНИЦ (первая таблица с колонкой page_id)."""
    for hdr, rows in _parse_tables(text):
        if "page_id" in hdr:
            return rows
    return []


def _parse_attachments(text: str) -> List[Dict[str, str]]:
    """Строки таблицы ПРИЛОЖЕНИЙ (таблица с первой колонкой «файл»);
    в старых описях таблицы нет — пустой список (совместимость)."""
    for hdr, rows in _parse_tables(text):
        if hdr and hdr[0] == _ATT_COLS[0]:
            return rows
    return []


def check(sources: Path, inv_path: Path) -> Tuple[List[str], bool]:
    fresh, _ = scan(sources)
    inv_text = inv_path.read_text(encoding="utf-8", errors="replace")
    inv = _parse_inventory(inv_text)
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
    # сравнение — в нормальной форме записи ячейки (пробелы жмутся):
    # титулы источника несут двойные пробелы, которые ячейка legitимно
    # сжала — это не правка (ложняк 38/162 на inkasso, 2026-08-26)
    def norm(v: str) -> str:
        return re.sub(r"\s+", " ", v).strip()
    for k in set(fresh_m) & set(inv_m):
        for c in _SCRIPT_COLS:
            if norm(_uncell(inv_m[k].get(c, ""))) != norm(fresh_m[k][c]):
                changed.append(f"{k}.{c}")
    if changed:
        ok = False
        report.append(f"ИЗМЕНЕНЫ скриптовые колонки ×{len(changed)} "
                      "(правке подлежат только колонки LLM): "
                      + ", ".join(sorted(changed)[:10]) + " ✗")
    # приложения (Д-24 по-самодостаточному: не-markdown файлы выгрузки
    # учитываются описью — потерянное приложение видимый брак, не тихая
    # дыра; вся таблица скриптовая, LLM-колонок нет)
    att_fresh, _n_img = scan_attachments(sources)
    att_inv = _parse_attachments(inv_text)
    af = {r[_ATT_COLS[0]]: r for r in att_fresh}
    ai = {r.get(_ATT_COLS[0], ""): r for r in att_inv}
    a_lost = sorted(set(af) - set(ai))
    a_extra = sorted(set(ai) - set(af))
    a_changed: List[str] = []
    for k in set(af) & set(ai):
        for c in _ATT_COLS[1:]:
            if norm(_uncell(ai[k].get(c, ""))) != norm(af[k][c]):
                a_changed.append(f"{k}.{c}")
    if a_lost:
        ok = False
        report.append(f"ПОТЕРЯНЫ приложения ×{len(a_lost)} — не-markdown "
                      "файлы выгрузки без строки описи (молчаливая "
                      "потеря): " + ", ".join(a_lost[:10]) + " ✗")
    if a_extra:
        ok = False
        report.append(f"ЛИШНИЕ строки приложений ×{len(a_extra)} (в "
                      "выгрузке таких файлов нет): "
                      + ", ".join(a_extra[:10]) + " ✗")
    if a_changed:
        ok = False
        report.append(f"ИЗМЕНЕНЫ колонки приложений ×{len(a_changed)} "
                      "(таблица приложений скриптовая целиком): "
                      + ", ".join(sorted(a_changed)[:10]) + " ✗")
    report.append(f"ПРОВЕРКА ПРИЛОЖЕНИЙ: файлов {len(att_fresh)}, строк "
                  f"{len(att_inv)}, потеряно {len(a_lost)}, лишних "
                  f"{len(a_extra)}, правок {len(a_changed)}")
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
    ap.add_argument("--refresh", type=Path, default=None,
                    help="перегенерировать скриптовые колонки описи "
                         "свежим сканом, сохранив колонки LLM (после "
                         "улучшений сканера)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if args.out is None and args.check is None and args.refresh is None:
        ap.error("нужен --out (скелет), --check (валидация) или "
                 "--refresh (обновление скелета с сохранением LLM)")
    if args.refresh is not None:
        lines = refresh(args.sources, args.refresh)
        args.refresh.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(lines[-1])
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
