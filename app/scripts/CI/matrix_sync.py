# app/scripts/CI/matrix_sync.py
"""Выводимые разделы матрицы трассировки (пакет 2 замечаний ОНБ-В, задача 10,
шаг 2; решения владельца канона 2026-10-16).

Матрица состоит из выводимых и ручных разделов. Выводимые — реестр ID,
покрытие функций, покрытие процессов, источники миграции — собираются из
тел документов (conventions §5.3 п.2: «матрица производна от тел»). Ручные —
покрытие API ↔ SRS, долги по ссылкам, бизнес-слой BRD — ведёт аналитик.

Режим `--check` (по умолчанию) печатает расхождения выводимых разделов с
документами и ничего не пишет. Код 0 — расхождений нет, 1 — есть ⚠.

Правила вывода:
- реестр ID: ID из шапок документов, ID в начале заголовков тел и ID в
  первой ячейке строки таблицы, записанный без ссылки (справочники EXT,
  группы CTL-GRP); локальные ID экранных форм и нотификаций (FLD, B, EV, FF,
  M, MSG, US) в реестр не входят; строки с файлом «—» ручные — снятые
  (пометка «снят …») и плановые (conventions §5, §5.3 п.4–5);
- покрытие: связь — markdown-ссылка в любую сторону; ID связи — ID из текста
  ссылки, если он определён в целевом файле, иначе ID заголовка по якорю,
  иначе ID файла; ссылки на README-реестры связей не дают; колонка — по
  префиксу ID; «Вызывает» — только по ссылке из тела процесса;
- источники: page_id из `confluence_page_ids` → ID документов.

Запуск: python matrix_sync.py --docs <корень комплекта>
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import selfcheck as scx  # noqa: E402

MATRIX = "traceability-matrix.md"

# Шаблон канона: порядок разделов, имена, колонки выводимых разделов
TEMPLATE: List[Tuple[str, str, Optional[List[str]]]] = [
    ("registry", "Реестр ID", ["ID", "Название", "Файл"]),
    ("fun", "Покрытие: функции → артефакты",
     ["Функция", "Название", "Экраны", "Данные", "Контроли", "Печатные формы"]),
    ("proc", "Покрытие: процессы → артефакты",
     ["Процесс", "Название", "Вызывает", "Функции", "Вызовы", "Экраны",
      "Контроли", "Данные", "Печатные формы"]),
    ("api", "Покрытие: API ↔ SRS", None),
    ("sources", "Источники миграции", ["Page ID", "Целевые артефакты", "Основание"]),
    ("debts", "Долги по ссылкам", None),
]
SECTION_TITLE = {k: t for k, t, _ in TEMPLATE}
SECTION_COLS = {k: c for k, _, c in TEMPLATE}

# Колонки покрытия: ключ колонки → префиксы ID
COL_PREFIXES = {
    "scr": {"SCR"}, "data": {"ENT", "EXT", "DM"}, "ctl": {"CTL"},
    "prn": {"PRN"}, "fun": {"FUN"}, "ext": {"CALL", "PLT", "EXTINT"},
    "callproc": {"PROC", "PRC", "SM"},
}
COL_TITLE = {"scr": "Экраны", "data": "Данные", "ctl": "Контроли",
             "prn": "Печатные формы", "fun": "Функции", "ext": "Вызовы",
             "callproc": "Вызывает"}
FUN_COLS = ["scr", "data", "ctl", "prn"]
PROC_COLS = ["callproc", "fun", "ext", "scr", "ctl", "data", "prn"]

LOCAL_PREFIXES = {"FLD", "B", "EV", "FF", "M", "MSG", "US", "E"}
_TAIL = r"(?!\.?[A-Za-z0-9])(?![\w-])"
_ID = r"[A-Z]{2,}(?:-[A-Z0-9]+)*-\d+(?:\.\d+)*"
_ANY_ID = r"[A-Z]+(?:-[A-Z0-9]+)*-\d+(?:\.\d+)*"
ID_RE = re.compile(r"(?<![\w-])(" + _ID + r")" + _TAIL)
ANY_ID_RE = re.compile(r"(?<![\w-])(" + _ANY_ID + r")" + _TAIL)
RANGE_RE = re.compile(r"(?<![\w-])(" + _ID + r")\s*(?:…|\.\.\.|–|—)\s*(" + _ID + r")(?![\w-])")
HEAD_ID_RE = re.compile(
    r"^#{2,6}\s+(?:\d+(?:\.\d+)*\.?\s+)?[\[`*]*(" + _ANY_ID + r")" + _TAIL
    + r"[\]`*]*\.?\s*(.*)$")
TABLE_DEF_RE = re.compile(r"^\|\s*\**(" + _ANY_ID + r")" + _TAIL + r"\**\s*\|")


def id_prefix(i: str) -> str:
    return i.split("-", 1)[0]


def scr_base(i: str) -> str:
    return re.sub(r"(?:\.\d+)+$", "", i) if i.startswith("SCR-") else i


def _norm_name(h: str) -> str:
    h = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", h.strip())
    return h.lower().replace("ё", "е").strip()


def section_key(title: str) -> str:
    n = _norm_name(title)
    if n.startswith("реестр id") and "бизнес" not in n:
        return "registry"
    if re.match(r"покрытие\W+функци", n):
        return "fun"
    if re.match(r"покрытие\W+процесс", n):
        return "proc"
    if re.match(r"покрытие\W+api", n):
        return "api"
    if n.startswith("источники миграции") or n.startswith("покрытие страниц"):
        return "sources"
    if n.startswith("долги по ссылкам"):
        return "debts"
    if n.startswith("brd-"):
        return "brd"
    return "unknown"


def column_key(header: str) -> str:
    h = header.lower().replace("ё", "е")
    if re.search(r"вызыва|\bprc\b|^proc$", h):
        return "callproc"
    if re.search(r"вызов|интеграц|call|extint", h):
        return "ext"
    if re.search(r"экран|scr", h):
        return "scr"
    if re.search(r"данн|ent", h):
        return "data"
    if re.search(r"контрол|ctl", h):
        return "ctl"
    if re.search(r"печат|prn|пф", h):
        return "prn"
    if re.search(r"функци|fun", h):
        return "fun"
    return "other"


def cell_ids(cell: str) -> Set[str]:
    """ID ячейки; диапазон «A … B» одного префикса раскрывается."""
    out = set(ID_RE.findall(cell))
    for a, b in RANGE_RE.findall(cell):
        ma, mb = re.match(r"(.*-)(\d+)$", a), re.match(r"(.*-)(\d+)$", b)
        if ma and mb and ma.group(1) == mb.group(1) \
                and int(ma.group(2)) < int(mb.group(2)) <= int(ma.group(2)) + 200:
            w = len(ma.group(2))
            out |= {f"{ma.group(1)}{n:0{w}d}"
                    for n in range(int(ma.group(2)), int(mb.group(2)) + 1)}
    return out


def _is_registry_file(p: Path) -> bool:
    return p.name.lower() == "readme.md"


# ---------------------------------------------------------------- матрица

class Section:
    def __init__(self, title: str, key: str, start: int, end: int):
        self.title, self.key, self.start, self.end = title, key, start, end
        self.header: List[str] = []
        self.rows: List[List[str]] = []

    def col(self, pattern: str, default: int) -> int:
        for n, h in enumerate(self.header):
            if re.search(pattern, h, re.I):
                return n
        return default


def _split_row(ln: str) -> List[str]:
    return [c.strip() for c in ln.strip().strip("|").split("|")]


def parse_matrix(text: str) -> List[Section]:
    lines = text.split("\n")
    heads = [(i, ln[3:].strip()) for i, ln in enumerate(lines) if ln.startswith("## ")]
    out: List[Section] = []
    for n, (i, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        s = Section(title, section_key(title), i, end)
        in_code = False
        for ln in lines[i + 1:end]:
            st = ln.strip()
            if st.startswith(("```", "~~~")):
                in_code = not in_code
                continue
            if in_code or not st.startswith("|"):
                continue
            cells = _split_row(st)
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if not s.header:
                s.header = cells
            elif cells != s.header:
                s.rows.append(cells)
        out.append(s)
    return out


def structure_issues(sections: List[Section]) -> List[str]:
    """Отклонения от шаблона: состав, порядок, имена, колонки."""
    issues: List[str] = []
    keys = [s.key for s in sections]
    for s in sections:
        if s.key == "unknown":
            issues.append(f"раздел вне шаблона: «{s.title}»")
    for k, title, _ in TEMPLATE:
        if k not in keys:
            issues.append(f"нет раздела «{title}»")
        elif keys.count(k) > 1:
            issues.append(f"раздел «{title}» встречается {keys.count(k)} раза")
    order = [k for k in keys if k in SECTION_TITLE]
    want = [k for k, _, _ in TEMPLATE if k in order]
    if order != want:
        issues.append("порядок разделов не по шаблону: "
                      + " → ".join(SECTION_TITLE[k] for k in order))
    for s in sections:
        if s.key in SECTION_TITLE and _norm_name(s.title) != _norm_name(SECTION_TITLE[s.key]):
            issues.append(f"имя раздела «{s.title}» — по шаблону «{SECTION_TITLE[s.key]}»")
        cols = SECTION_COLS.get(s.key)
        if cols and s.header and s.header != cols:
            issues.append(f"колонки «{s.title}»: {' | '.join(s.header)} — по шаблону "
                          f"{' | '.join(cols)}")
    return issues


# ---------------------------------------------------------------- комплект

class Kit:
    """Индекс комплекта: определения ID и связи между ними."""

    def __init__(self, docs: Path, matrix: Path):
        self.docs = docs
        self.fm: Dict[str, Tuple[str, str, str]] = {}      # id → (rel, title, type)
        self.defs: Dict[str, Tuple[str, str]] = {}         # ID заголовка/таблицы → (rel, имя)
        self.defs_in: Dict[Path, Set[str]] = {}            # файл → определённые в нём ID
        self.id_of_file: Dict[Path, str] = {}
        self.registry_ids: Set[str] = set()                # ID README-реестров
        self.readme_rows: Set[str] = set()                 # ID документов-README
        self.anchor_id: Dict[Path, Dict[str, str]] = {}
        self.out: Dict[str, Set[str]] = {}                 # id → ID по ссылкам из тела
        self.inc: Dict[str, Set[str]] = {}                 # id → ID, ссылающиеся на него
        self.pages: Dict[str, Set[str]] = {}               # page_id → ID
        files = [p for p in scx._kit_md(docs) if p.resolve() != matrix.resolve()]
        texts: Dict[Path, str] = {}
        fms: Dict[Path, Dict[str, str]] = {}
        for p in files:
            try:
                texts[p] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fms[p] = scx.read_frontmatter(p) or {}
            fid = str(fms[p].get("id", "")).strip("'\"")
            if fid:
                self.fm[fid] = (p.relative_to(docs).as_posix(),
                                str(fms[p].get("title", "")).strip().strip("'\""),
                                str(fms[p].get("type", "")).strip("'\""))
                # README-реестр — навигация; README контролей (CTL-000) — документ
                if _is_registry_file(p) and self.fm[fid][2] != "control":
                    self.registry_ids.add(fid)
        for p, t in texts.items():
            fm = fms[p]
            rel = p.relative_to(docs).as_posix()
            fid = str(fm.get("id", "")).strip("'\"")
            own = fid or str(fm.get("partOf", "")).strip("'\"")
            if own:
                self.id_of_file[p.resolve()] = own
            for pid in scx.page_ids(fm):
                if own:
                    self.pages.setdefault(pid, set()).add(own)
            amap: Dict[str, str] = {}
            here: Set[str] = set()
            local_doc = str(fm.get("type", "")).strip("'\"") == "screen-form"
            in_code = False
            for ln in t.splitlines():
                if ln.strip().startswith(("```", "~~~")):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                hid, name = "", ""
                if ln.startswith("#"):
                    m = HEAD_ID_RE.match(ln)
                    if m:
                        hid, name = m.group(1), m.group(2)
                        amap[scx.gitlab_slug(ln.lstrip("#").strip())] = hid
                else:
                    m = TABLE_DEF_RE.match(ln)
                    if m and m.group(1) not in self.fm:
                        hid = m.group(1)
                        cells = _split_row(ln)
                        name = cells[1] if len(cells) > 1 else ""
                if not hid or id_prefix(hid) in LOCAL_PREFIXES or hid == fid or local_doc:
                    continue
                here.add(hid)
                self.defs.setdefault(hid, (rel, name.strip(" .")))
            self.anchor_id[p.resolve()] = amap
            self.defs_in[p.resolve()] = here
        self.text = "\n".join(texts.values())
        for p, t in texts.items():
            src_file_id = self.id_of_file.get(p.resolve(), "")
            cur = src_file_id
            in_code = False
            for ln in t.splitlines():
                if ln.strip().startswith(("```", "~~~")):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                if ln.startswith("#"):
                    m = HEAD_ID_RE.match(ln)
                    if m and id_prefix(m.group(1)) not in LOCAL_PREFIXES:
                        cur = m.group(1)
                    continue
                # строка таблицы, начинающаяся с определения ID, — источник своих ссылок
                td = TABLE_DEF_RE.match(ln)
                row_src = td.group(1) if td and td.group(1) in self.defs_in.get(p.resolve(), set())                     else cur
                for m in scx._MD_LINK_RE.finditer(ln):
                    tid = self._resolve(p, m.group(1), m.group(2).strip())
                    if not tid or tid in self.registry_ids:
                        continue
                    if src_file_id and tid != src_file_id:
                        self.out.setdefault(src_file_id, set()).add(tid)
                    if row_src and tid != row_src and row_src not in self.registry_ids:
                        self.inc.setdefault(tid, set()).add(row_src)

    def _resolve(self, md: Path, label: str, raw: str) -> str:
        if "://" in raw or raw.startswith(("mailto:", "<")):
            return ""
        path_part, _, anchor = unquote(raw).partition("#")
        path_part = path_part.replace("\\", "/")
        try:
            tgt = (md.parent / path_part).resolve() if path_part else md.resolve()
        except OSError:
            return ""
        m = ID_RE.match(label.strip().strip("`*[]"))
        if m and (m.group(1) in self.defs_in.get(tgt, set())
                  or m.group(1) == self.id_of_file.get(tgt)):
            return m.group(1)
        if anchor:
            hid = self.anchor_id.get(tgt, {}).get(anchor.lower())
            if hid:
                return hid
        return self.id_of_file.get(tgt, "")

    def known(self, i: str) -> bool:
        return i in self.fm or i in self.defs

    def derived_registry(self) -> Dict[str, Tuple[str, str]]:
        """ID → (файл, название) — выводимые строки реестра."""
        out = {i: (rel, t) for i, (rel, t, _ty) in self.fm.items()}
        for i, (rel, name) in self.defs.items():
            out.setdefault(i, (rel, name))
        return out

    def related(self, rid: str, with_incoming: bool = True) -> Set[str]:
        rel = set(self.out.get(rid, set()))
        if with_incoming:
            rel |= self.inc.get(rid, set())
        return {scr_base(i) for i in rel if scr_base(i) != rid}

    def rows_of_type(self, types: Set[str]) -> Set[str]:
        return {i for i, (rel, _t, typ) in self.fm.items()
                if typ in types and not rel.lower().endswith("readme.md")}


# ---------------------------------------------------------------- проверка

def _first_id(cell: str) -> str:
    m = ANY_ID_RE.search(re.sub(r"\]\([^)]*\)", "]", cell))
    return m.group(1) if m else ""


def _file_cell(cell: str) -> str:
    m = re.search(r"\]\(([^)]+)\)", cell) or re.search(r"`([^`]+)`", cell)
    v = (m.group(1) if m else cell).strip()
    return re.sub(r"^\./", "", v.split("#", 1)[0]).rstrip("/")


def _emit(lines: List[str], title: str, items: List[str], limit: int = 12) -> None:
    if items:
        lines.append(f"   {title} ×{len(items)}: " + "; ".join(items[:limit])
                     + (" …" if len(items) > limit else ""))


def check_registry(sec: Section, kit: Kit) -> List[str]:
    lines: List[str] = []
    fcol = sec.col(r"файл", len(sec.header) - 1 if sec.header else 2)
    have: Dict[str, List[str]] = {}
    for r in sec.rows:
        i = _first_id(r[0]) if r else ""
        if i:
            have.setdefault(i, r)
    derived = kit.derived_registry()
    missing = sorted(i for i in derived if i not in have)
    reused, stale, mention, wrong_file = [], [], [], []
    for i, r in have.items():
        fcell = _file_cell(r[fcol] if len(r) == len(sec.header) else r[-1]) if r else ""
        if fcell in ("—", "-", ""):
            if re.search(r"\bснят", " ".join(r), re.I) and i in derived:
                reused.append(i)
            continue
        if i not in derived:
            (mention if re.search(r"(?<![\w-])" + re.escape(i) + r"(?![\w.-])", kit.text)
             else stale).append(i)
        elif fcell != derived[i][0] and not derived[i][0].endswith("/" + fcell):
            wrong_file.append(f"{i}: {fcell} → {derived[i][0]}")
    _emit(lines, "нет строки для ID из документов", missing)
    _emit(lines, "снятый ID снова в документах (ID переиспользован)", reused)
    _emit(lines, "строка без документа (документ удалён или сменил ID — оформить снятие)", stale)
    _emit(lines, "ID только упоминается в тексте — нет ни в шапке, ни в заголовке, ни в "
                 "первой ячейке таблицы", mention)
    _emit(lines, "файл расходится", wrong_file, 6)
    return lines


def check_coverage(sec: Section, kit: Kit, row_types: Set[str], cols: List[str],
                   ) -> Tuple[List[str], List[str]]:
    """(строки отчёта, связи только в матрице)."""
    lines: List[str] = []
    want_rows = kit.rows_of_type(row_types)
    colmap = [column_key(h) for h in sec.header]
    seen: Set[str] = set()
    missing_cells, only_matrix, misplaced, foreign_rows = [], [], [], []
    for r in sec.rows:
        rid = _first_id(r[0]) if r else ""
        if not rid:
            continue
        seen.add(rid)
        if rid not in want_rows:
            foreign_rows.append(rid)
            continue
        rel_all = kit.related(rid)
        for n, cell in enumerate(r[1:], 1):
            ck = colmap[n] if n < len(colmap) else "other"
            if ck not in cols:
                continue
            m_ids = {scr_base(i) for i in cell_ids(cell)} - {rid}
            if ck == "callproc":
                d_ids = {i for i in kit.related(rid, with_incoming=False)
                         if id_prefix(i) in COL_PREFIXES[ck]}
            else:
                d_ids = {i for i in rel_all if id_prefix(i) in COL_PREFIXES[ck]}
            for i in sorted(d_ids - m_ids):
                missing_cells.append(f"{rid} «{COL_TITLE[ck]}»: нет {i}")
            for i in sorted(m_ids - d_ids):
                if i in rel_all:
                    misplaced.append(f"{rid} «{COL_TITLE[ck]}»: {i}")
                elif kit.known(i):
                    only_matrix.append(f"{rid} «{COL_TITLE[ck]}»: {i}")
    _emit(lines, "нет строки", sorted(want_rows - seen))
    _emit(lines, "строка не для документа этого типа", foreign_rows, 8)
    _emit(lines, "нет связи из документов", missing_cells, 8)
    _emit(lines, "связь есть, но ID не по префиксу колонки", misplaced, 6)
    _emit(lines, "связь только в матрице — в документах ссылки нет "
                 "(--write не работает, пока перечень не пуст)", only_matrix, 8)
    return lines, only_matrix


def check_sources(sec: Section, kit: Kit) -> List[str]:
    if not any(re.search(r"целев|артефакт", h, re.I) for h in sec.header):
        return ["   колонки не по шаблону — сверка содержимого пропущена"]
    tcol = sec.col(r"целев|артефакт", 1)
    have: Dict[str, Set[str]] = {}
    for r in sec.rows:
        m = re.search(r"\b(\d{6,})\b", r[0]) if r else None
        if m and tcol < len(r):
            have.setdefault(m.group(1), set()).update(cell_ids(r[tcol]))
    missing = sorted(p for p in kit.pages if p not in have)
    diff = []
    for p, ids in sorted(kit.pages.items()):
        if p in have:
            lost, extra = ids - have[p], have[p] - ids
            if lost or extra:
                diff.append(f"{p}: " + ", ".join(
                    [f"нет {x}" for x in sorted(lost)[:3]] + [f"лишний {x}" for x in sorted(extra)[:3]]))
    lines: List[str] = []
    _emit(lines, "нет строки страницы", missing, 10)
    _emit(lines, "целевые артефакты расходятся", diff, 6)
    return lines


def check(docs: Path, matrix: Optional[Path] = None) -> Tuple[List[str], bool]:
    """(отчёт, есть ⚠)."""
    matrix = matrix or docs / MATRIX
    if not matrix.is_file():
        return [f"i матрицы нет: {matrix.name}"], False
    text = matrix.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    sections = parse_matrix(text)
    kit = Kit(docs, matrix)
    report: List[str] = []
    st = structure_issues(sections)
    if st:
        report.append(f"⚠ структура матрицы не по шаблону ×{len(st)} (--write не работает):")
        report.extend(f"   {x}" for x in st)
    by_key: Dict[str, Section] = {}
    for s in sections:
        by_key.setdefault(s.key, s)
    checks = [
        ("registry", lambda s: check_registry(s, kit)),
        ("fun", lambda s: check_coverage(s, kit, {"function"}, FUN_COLS)[0]),
        ("proc", lambda s: check_coverage(s, kit, {"process"}, PROC_COLS)[0]),
        ("sources", lambda s: check_sources(s, kit)),
    ]
    for key, fn in checks:
        s = by_key.get(key)
        if s is None:
            continue
        lines = fn(s)
        if lines:
            mark = "⚠" if any("×" in ln for ln in lines) else "i"
            report.append(f"{mark} «{s.title}» расходится с документами:" if mark == "⚠"
                          else f"i «{s.title}»:")
            report.extend(lines)
    warn = any(ln.startswith("⚠") for ln in report)
    if not warn:
        report.append("✓ выводимые разделы матрицы совпадают с документами")
    return report, warn


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Выводимые разделы матрицы трассировки: "
                                 "сверка с телами документов (--check).")
    ap.add_argument("--docs", type=Path, required=True, help="корень комплекта")
    ap.add_argument("--matrix", type=Path, default=None,
                    help="файл матрицы (по умолчанию <docs>/traceability-matrix.md)")
    ap.add_argument("--check", action="store_true", help="сверка (режим по умолчанию)")
    args = ap.parse_args(argv)
    report, warn = check(args.docs, args.matrix)
    print("\n".join(report))
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
