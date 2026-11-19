# app/scripts/CI/kitcheck/checks/brd.py
"""Слой BRD комплекта (постановка «AI Factory» 2026-11-19, П6–П8; решения владельца 19.11).

Стандарт требует `brd/` у продуктовых сервисов и нулевые гейты достаточности (conventions §5
«инварианты», §5.3 п. 8–9); слои BRD и SRS друг на друга не ссылаются (conventions §5.4: вся
связь — в матрице трассировки). Проверки:

- П6, слой BRD: сервис комплекта — по полю `service` шапок; запись в каталоге сервисов
  `_meta/services.json`, признак `is_platform`. Платформенный сервис — i «не применяется»
  (роль слоя выполняет `service-vision.md`). Продуктовый, не найденный в каталоге или каталог
  недоступен (сомнение — в сторону отказа) и нет каталога `brd/` с документами, имеющими `id`, —
  отказ гейта; отсрочка — ключ гейта `--brd-deferred "<основание>; ответственный: <кто>; срок:
  <ГГГГ-ММ-ДД>"` (⚠ с текстом ключа), значение без ответственного или срока — отказ с названием
  поля. `brd/` есть — каталог не нужен.
- П7, секции и гейты BRD (только при слое `brd/`): секции `## BRD-1` … `## BRD-5` матрицы — по
  префиксу заголовка, не по названию; в `BRD-5` таблица «Гейт | Значение», ведущее целое число
  ячейки «Значение» каждой строки равно 0, нет числа — «значение не читается». Пересчёт трёх
  счётчиков по комплекту — функции без US (функции, которых нет в `BRD-1`), печатные формы без
  связи (формы, которых нет в `BRD-4`), сироты BRD (документ `brd/`, ни `id` которого, ни ID,
  определённые в нём, не встречаются в `BRD-1…3`); README-реестры не считаются. Расхождение
  пересчёта с заявленным нулём — ⚠ (повышение до ✗ — отдельным словом владельца). Счётчики
  «сценарные процессы без UC» и «доменные политики без BR» механически не выводятся — по
  заявленному значению. Секция `BRD-6` (НФТ) — за проверкой `nfr_catalog`.
- П8, слои не ссылаются друг на друга: markdown-ссылка из файла `brd/**` на файл `srs/**` или
  обратно — отказ гейта. Файлы README.md — навигация, ни к слою BRD, ни к слою SRS не относятся:
  проверка их не рассматривает ни как источник ссылки, ни как цель (решение владельца канона 19.11).

Признаки — по форме и структуре: поле шапки, каталог, префикс заголовка, ведущее число ячейки,
markdown-ссылка. Слов источника нет; имена строк таблицы гейтов — термины нормы. Слой — ядро
(работает без выгрузки). В selfcheck — ⚠ (вердикт не меняется), отказ — у гейта переноса.
"""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote
try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, code_line_flags, read_frontmatter, table_cells
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, code_line_flags, read_frontmatter, table_cells  # type: ignore

Mark = Tuple[str, str]  # (знак гейта полного режима, текст)

_BRD_HEAD_RE = re.compile(r"^##\s+BRD-(\d+)\b", re.M)
_LEAD_INT_RE = re.compile(r"^[\s*_`]*(\d+)")
_LINK_RE = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_REQUIRED_SECTIONS = ("1", "2", "3", "4", "5")


def _ms():
    try:
        import matrix_sync as m  # noqa: E402 — ID ячеек и диапазоны — один дом
    except ImportError:  # импорт пакетом app.scripts.CI (тесты)
        from ... import matrix_sync as m  # type: ignore
    return m


def _val(fm: dict, key: str) -> str:
    return str(fm.get(key, "") or "").strip().strip("'\"")


def _ids_in(text: str) -> Set[str]:
    """ID текста секции: любой формы (F-CL-01 — однобуквенный префикс) и диапазоны."""
    m = _ms()
    return set(m.ANY_ID_RE.findall(text)) | m.cell_ids(text)


# ---------------------------------------------------------------- П6

def kit_service(docs: Path) -> Tuple[str, Dict[str, int]]:
    """(код сервиса комплекта — самое частое поле `service` шапок, все значения со счётом)."""
    cnt: Counter = Counter()
    for p in _kit_md(docs):
        s = _val(read_frontmatter(p) or {}, "service")
        if s:
            cnt[s] += 1
    return (cnt.most_common(1)[0][0] if cnt else ""), dict(cnt)


def brd_docs(docs: Path) -> List[Path]:
    """Документы `brd/` с `id` (README-реестры — тоже документы слоя)."""
    d = docs / "brd"
    if not d.is_dir():
        return []
    return [p for p in _kit_md(docs) if d in p.parents and _val(read_frontmatter(p) or {}, "id")]


def load_catalog(catalog: Optional[Path]) -> Optional[List[dict]]:
    if catalog is None or not catalog.is_file():
        return None
    try:
        data = json.loads(_fs.read_text(catalog, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else None


def parse_deferred(value: str) -> Tuple[Dict[str, str], List[str]]:
    """Значение --brd-deferred: ({основание, ответственный, срок}, недостающие поля)."""
    parts = [x.strip() for x in value.split(";")]
    out = {"основание": "", "ответственный": "", "срок": ""}
    for x in parts:
        k, sep, v = x.partition(":")
        key = k.strip().lower()
        if sep and key in ("ответственный", "срок"):
            out[key] = v.strip()
        elif x and not out["основание"]:
            out["основание"] = x
    if out["срок"] and not _DATE_RE.search(out["срок"]):
        out["срок"] = ""
    return out, [k for k, v in out.items() if not v]


def brd_layer(docs: Path, catalog: Optional[Path]) -> dict:
    """Сведения для П6: service, services (счёт значений), catalog (доступен ли), entry (запись
    каталога или None), platform (bool|None), brd (число документов brd/ с id)."""
    svc, svcs = kit_service(docs)
    cat = load_catalog(catalog)
    entry = next((s for s in cat or [] if s.get("code") == svc), None) if svc else None
    return {"service": svc, "services": svcs, "catalog": cat is not None, "entry": entry,
            "platform": (bool(entry.get("is_platform")) if entry is not None else None),
            "brd": len(brd_docs(docs))}


def brd_layer_lines(info: dict, deferred: Optional[str] = None) -> List[Mark]:
    svc = info["service"] or "не указан в шапках"
    if info["brd"]:
        out = [("✓", f"слой BRD есть: документов brd/ с id {info['brd']}")]
        if deferred:
            out.append(("i", "ключ --brd-deferred не применяется: слой BRD есть"))
        return out
    if info["platform"]:
        return [("i", f"не применяется: платформенный сервис «{svc}» (каталог сервисов, "
                      "is_platform), роль слоя выполняет service-vision.md")]
    if not info["catalog"]:
        why = ("каталог сервисов недоступен: платформенный сервис определяется только по каталогу "
               "— задайте --catalog")
    elif info["entry"] is None:
        why = (f"сервис «{svc}» не найден в каталоге сервисов — сомнение трактуется в сторону "
               "продуктового")
    else:
        why = f"сервис «{svc}» продуктовый (каталог сервисов)"
    base = (f"слой BRD обязателен для продуктового сервиса (conventions §5): каталога brd/ с "
            f"документами нет; {why}")
    if deferred is None:
        return [("✗", base + " — либо отсрочка ключом --brd-deferred \"<основание>; "
                             "ответственный: <кто>; срок: <ГГГГ-ММ-ДД>\"")]
    fields, missing = parse_deferred(deferred)
    if missing:
        return [("✗", base + f"; --brd-deferred без поля {', '.join(f'«{m}»' for m in missing)}"
                      f" — отсрочка не принята: «{deferred}»")]
    return [("⚠", f"слой BRD отложен (--brd-deferred): {fields['основание']}; ответственный: "
                  f"{fields['ответственный']}; срок: {fields['срок']} — {why}")]


# ---------------------------------------------------------------- П7

def brd_sections(matrix_text: str) -> Dict[str, str]:
    """Секции бизнес-слоя матрицы по префиксу заголовка `## BRD-<N>`: {N: текст секции}."""
    out: Dict[str, str] = {}
    heads = [(m.start(), m.end(), m.group(1)) for m in _BRD_HEAD_RE.finditer(matrix_text)]
    for s, e, n in heads:
        nxt = re.search(r"^#{1,2}\s", matrix_text[e:], re.M)
        out.setdefault(n, matrix_text[e:e + nxt.start()] if nxt else matrix_text[e:])
    return out


def _gate_table(section: str) -> Optional[List[List[str]]]:
    """Строки таблицы «Гейт | Значение» секции (без шапки и разделителя); None — таблицы нет."""
    lines = section.splitlines()
    flags = code_line_flags(lines)
    rows: Optional[List[List[str]]] = None
    for ln, code in zip(lines, flags):
        s = ln.strip()
        if code or not s.startswith("|"):
            if rows is not None:
                return rows
            continue
        cells = table_cells(s)
        if rows is None:
            low = [c.lower().strip("* ") for c in cells]
            if len(low) >= 2 and low[0] == "гейт" and low[1] == "значение":
                rows = []
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def _inner_ids(p: Path) -> Set[str]:
    m = _ms()
    out: Set[str] = set()
    lines = _fs.read_text(p, encoding="utf-8", errors="replace").splitlines()
    for ln, code in zip(lines, code_line_flags(lines)):
        if code:
            continue
        hm = m.HEAD_ID_RE.match(ln) or m.TABLE_DEF_RE.match(ln)
        if hm:
            out.add(hm.group(1))
    return out


def brd_recount(docs: Path, sections: Dict[str, str]) -> Dict[str, List[str]]:
    """Пересчёт трёх счётчиков BRD-5 по комплекту (README-реестры не считаются)."""
    ids1 = _ids_in(sections.get("1", ""))
    ids4 = _ids_in(sections.get("4", ""))
    ids13 = _ids_in("\n".join(sections.get(n, "") for n in ("1", "2", "3")))
    funs, prns = [], []
    for p in _kit_md(docs):
        if p.name.lower() == "readme.md":
            continue
        fm = read_frontmatter(p) or {}
        i, t = _val(fm, "id"), _val(fm, "type")
        if not i:
            continue
        if t == "function" and i not in ids1:
            funs.append(i)
        elif t == "print-form" and i not in ids4:
            prns.append(i)
    orphans = []
    for p in brd_docs(docs):
        if p.name.lower() == "readme.md":
            continue
        i = _val(read_frontmatter(p) or {}, "id")
        if i not in ids13 and not (_inner_ids(p) & ids13):
            orphans.append(i)
    key = _ms().id_sort_key
    return {"функции без US (нет в BRD-1)": sorted(funs, key=key),
            "печатные формы без связи (нет в BRD-4)": sorted(prns, key=key),
            "сироты BRD (документ brd/ вне BRD-1…3)": sorted(orphans, key=key)}


def brd_gates_lines(docs: Path) -> List[Tuple[str, str, str]]:
    """(знак, проверка, текст) по П7; слоя brd/ или матрицы нет — пусто."""
    matrix = docs / "traceability-matrix.md"
    if not brd_docs(docs) or not matrix.is_file():
        return []
    text = _fs.read_text(matrix, encoding="utf-8", errors="replace").replace("\r\n", "\n")
    secs = brd_sections(text)
    out: List[Tuple[str, str, str]] = []
    chk = "секции и гейты BRD"
    missing = [f"BRD-{n}" for n in _REQUIRED_SECTIONS if n not in secs]
    if missing:
        out.append(("✗", chk, f"в матрице нет секций бизнес-слоя: {', '.join(missing)} — секции "
                              "BRD-1…BRD-5 обязательны при слое brd/ (conventions §5.3 п. 8–9; "
                              "секция узнаётся по префиксу заголовка «## BRD-<N>»)"))
    if "5" in secs:
        rows = _gate_table(secs["5"])
        if rows is None:
            out.append(("✗", chk, "в секции BRD-5 нет таблицы «Гейт | Значение» — гейты "
                                  "достаточности BRD не читаются"))
        else:
            bad = []
            for r in rows:
                name = r[0].strip() if r else "?"
                val = r[1].strip() if len(r) > 1 else ""
                m = _LEAD_INT_RE.match(val)
                if not m:
                    bad.append(f"«{name}» — значение гейта не читается: «{val[:40]}»")
                elif int(m.group(1)) != 0:
                    bad.append(f"«{name}» = «{val[:60]}{'…' if len(val) > 60 else ''}»")
            if bad:
                out.append(("✗", chk, "гейты достаточности BRD-5 не нулевые: " + "; ".join(bad)
                            + " — слой достаточен, когда все счётчики равны 0 (conventions §5.3 "
                              "п. 9)"))
            elif rows:
                out.append(("✓", chk, f"секции BRD-1…BRD-5 есть; гейты BRD-5 нулевые ({len(rows)}); "
                                      "пересчитаны по комплекту: функции без US, печатные формы без "
                                      "связи, сироты BRD; остальные гейты — по заявленному значению"))
            else:
                out.append(("✗", chk, "таблица «Гейт | Значение» секции BRD-5 пуста"))
    rc = brd_recount(docs, secs)
    diffs = [f"{k}: {len(v)} ({', '.join(v[:8])}{'…' if len(v) > 8 else ''})"
             for k, v in rc.items() if v]
    if diffs:
        out.append(("⚠", "пересчёт гейтов BRD", "пересчёт по комплекту расходится с заявленными "
                    "нулями: " + "; ".join(diffs) + " — дополнить секции BRD-1…BRD-4 или "
                    "таблицу гейтов BRD-5"))
    return out


# ---------------------------------------------------------------- П8

def layer_links(docs: Path) -> List[Tuple[str, str]]:
    """Markdown-ссылки между слоями: (файл-источник, цель) — из brd/** в srs/** и обратно.
    Файлы README.md — навигация, не документы слоя: не источник и не цель."""
    root = docs.resolve()
    out: List[Tuple[str, str]] = []
    for p in _kit_md(docs):
        try:
            rel = p.resolve().relative_to(root).parts
        except ValueError:
            continue
        if not rel or rel[0] not in ("brd", "srs") or rel[-1].lower() == "readme.md":
            continue
        lines = _fs.read_text(p, encoding="utf-8", errors="replace").splitlines()
        for ln, code in zip(lines, code_line_flags(lines)):
            if code:
                continue
            for u in _LINK_RE.findall(ln):
                if "://" in u or u.startswith(("#", "mailto:", "<")):
                    continue
                path = unquote(u.split("#", 1)[0]).replace("\\", "/")
                if not path:
                    continue
                try:
                    tgt = (p.parent / path).resolve().relative_to(root).parts
                except (ValueError, OSError):
                    continue
                if (tgt and tgt[0] in ("brd", "srs") and tgt[0] != rel[0]
                        and tgt[-1].lower() != "readme.md"):
                    out.append(("/".join(rel), "/".join(tgt)))
    return out


def layer_links_lines(links: List[Tuple[str, str]]) -> List[Mark]:
    if not links:
        return []
    shown = ", ".join(f"{s} → {t}" for s, t in links[:4]) + ("…" if len(links) > 4 else "")
    return [("✗", f"ссылки между слоями BRD и SRS в телах документов: {len(links)} ({shown})"
                  " — слои не ссылаются друг на друга, связь — в матрице трассировки "
                  "(conventions §5.4)")]
