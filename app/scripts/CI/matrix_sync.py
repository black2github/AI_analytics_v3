# app/scripts/CI/matrix_sync.py
"""Выводимые разделы матрицы трассировки (пакет 2 замечаний ОНБ-В, задача 10,
шаг 2; решения владельца канона 2026-10-16).

Матрица состоит из выводимых и ручных разделов. Выводимые — реестр ID,
покрытие функций, покрытие процессов, источники миграции — собираются из
тел документов (conventions §5.3 п.2: «матрица производна от тел»). Ручные —
покрытие API ↔ SRS, долги по ссылкам, бизнес-слой BRD — ведёт аналитик.

Режим `--check` (по умолчанию) печатает расхождения выводимых разделов с
документами и ничего не пишет. Код 0 — расхождений нет, 1 — есть ⚠.

Режим `--write` пересобирает таблицы выводимых разделов; текст разделов вне
таблиц, ручные разделы и ручные строки реестра переносятся байт в байт;
переносы строк и BOM сохраняются; запись атомарная (временный файл и
замена); неизменённый файл не перезаписывается; ячейка, где факт тот же
(название без учёта тега, тот же файл, тот же набор ID), не переписывается.
Отказ (код 2, файл не тронут) — всякий раз, когда пересборка потеряла бы
факт: структура не по шаблону; ID в ячейке, на который нет ссылки в
документах, которого нет в комплекте или у префикса которого нет колонки;
строка реестра без документа (документ удалён или сменил ID — снятие
оформляется вручную, conventions §5); снятый ID снова в документах.

Правила вывода:
- реестр ID: ID из шапок документов, ID в начале заголовков тел и ID в
  первой ячейке строки таблицы, записанный без ссылки (справочники EXT,
  группы CTL-GRP); локальные ID экранных форм и нотификаций (FLD, B, EV, FF,
  M, MSG, US) в реестр не входят; название документа — title (conventions §5:
  собственное наименование), без title — H1 без ID; строки с файлом «—» ручные — снятые
  (пометка «снят …») и плановые (conventions §5, §5.3 п.4–5);
- покрытие: связь — markdown-ссылка в любую сторону; ID связи — ID из текста
  ссылки, если он определён в целевом файле, иначе ID заголовка по якорю,
  иначе ID файла; голая ссылка на документ-контейнер (справочник, документ
  контролей) учитывается, только если конкретных ссылок в него нет; ссылки
  на README-реестры связей не дают; колонка — по префиксу ID; «Вызывает» —
  только по ссылке из тела процесса;
- источники: page_id из `confluence_page_ids` → ID документа; ID,
  определённые в файле, — когда файл — часть документа или у него одна
  страница; ID в матрице, определённый внутри документа этой страницы, —
  законное уточнение и сохраняется.

Запуск: python matrix_sync.py --docs <корень комплекта>
"""
import argparse
import os
import re
import sys
import tempfile
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


def yaml_scalar(v: str) -> str:
    """Значение поля шапки без одной парной внешней кавычки YAML: внутренние
    кавычки названия («ЭФ "Журнал"») сохраняются, '' в одинарных — апостроф."""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
        v = v.replace("''", "'") if v and "'" in v else v
    return v


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
        self.tables: List[Tuple[int, int]] = []   # [начало, конец) строк таблицы в файле

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
        tstart = None
        for j in range(i + 1, end + 1):
            ln = lines[j] if j < end else ""
            st = ln.strip()
            is_row = j < end and not in_code and st.startswith("|")
            if is_row and tstart is None:
                tstart = j
            if not is_row and tstart is not None:
                s.tables.append((tstart, j))
                tstart = None
            if j >= end:
                break
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
        if cols and len(s.tables) != 1:
            issues.append(f"в разделе «{s.title}» таблиц {len(s.tables)} — по шаблону одна")
    return issues


# ---------------------------------------------------------------- комплект

class Kit:
    """Индекс комплекта: определения ID и связи между ними."""

    def __init__(self, docs: Path, matrix: Path):
        self.docs = docs
        self.fm: Dict[str, Tuple[str, str, str]] = {}      # id → (rel, название, type)
        self.defs: Dict[str, Tuple[str, str]] = {}         # ID заголовка/таблицы → (rel, имя)
        self.defs_in: Dict[Path, Set[str]] = {}            # файл → определённые в нём ID
        self.table_defs: Set[str] = set()                  # ID, заданные строкой таблицы
        self.h1: Dict[str, str] = {}                       # id документа → H1 без ID
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
                # название — title («собственное наименование документа»,
                # conventions §5); без title (forward) — H1 без ID
                title = yaml_scalar(str(fms[p].get("title", "")))
                h1 = next((ln[2:].strip() for ln in texts[p].splitlines()
                           if ln.startswith("# ")), "")
                h1 = re.sub(r"^" + re.escape(fid) + r"\.?\s*", "", h1)
                self.h1[fid] = h1
                # часть документа (суб-ID «.N») несёт title главной страницы — различает
                # части только H1
                part = bool(re.search(r"\.\d+$", fid))
                self.fm[fid] = (p.relative_to(docs).as_posix(),
                                (h1 or title) if part else (title or h1),
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
                        if not local_doc and id_prefix(hid) not in LOCAL_PREFIXES:
                            self.table_defs.add(hid)
                if not hid or id_prefix(hid) in LOCAL_PREFIXES or hid == fid or local_doc:
                    continue
                here.add(hid)
                self.defs.setdefault(hid, (rel, name.strip(" .")))
            self.anchor_id[p.resolve()] = amap
            self.defs_in[p.resolve()] = here
            # страница → документ; ID, определённые в файле, — только когда файл —
            # часть документа (partOf) или у него одна страница: у многостраничного
            # файла (справочники) принадлежность ID странице из шапки не видна
            pids = scx.page_ids(fm)
            inner = here if (not fid or len(pids) == 1) else set()
            for pid in pids:
                if own or inner:
                    self.pages.setdefault(pid, set()).update(({own} if own else set()) | inner)
        self.text = "\n".join(texts.values())
        # ID определения → ID документа-контейнера, где он определён
        self.def_home: Dict[str, str] = {}
        for f, here in self.defs_in.items():
            cid = self.id_of_file.get(f, "")
            for i in here:
                if cid:
                    self.def_home[i] = cid
        for p, t in texts.items():
            src_file_id = self.id_of_file.get(p.resolve(), "")
            cur = src_file_id
            pend: List[Tuple[str, str, str]] = []
            spec: Set[Tuple[str, str]] = set()
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
                row_src = td.group(1) if td and td.group(1) in self.defs_in.get(p.resolve(), set()) \
                    else cur
                for m in scx._MD_LINK_RE.finditer(ln):
                    tid, bare = self._resolve(p, m.group(1), m.group(2).strip())
                    if not tid or tid in self.registry_ids:
                        continue
                    if bare:
                        pend.append((src_file_id, row_src, tid))
                        continue
                    self._link(src_file_id, row_src, tid)
                    if tid in self.def_home:
                        spec.add((src_file_id, self.def_home[tid]))
                        spec.add((row_src, self.def_home[tid]))
            # голая ссылка на документ-контейнер (справочник, документ контролей)
            # учитывается, только если конкретных ссылок в этот контейнер нет
            for src, row, tid in pend:
                if (src, tid) not in spec:
                    self._link(src, "", tid)
                if (row, tid) not in spec:
                    self._link("", row, tid)

    def _link(self, src_file_id: str, row_src: str, tid: str) -> None:
        if src_file_id and tid != src_file_id:
            self.out.setdefault(src_file_id, set()).add(tid)
        if row_src and tid != row_src and row_src not in self.registry_ids:
            self.inc.setdefault(tid, set()).add(row_src)

    def _resolve(self, md: Path, label: str, raw: str) -> Tuple[str, bool]:
        """(ID связи, голая ссылка на документ-контейнер)."""
        if "://" in raw or raw.startswith(("mailto:", "<")):
            return "", False
        path_part, _, anchor = unquote(raw).partition("#")
        path_part = path_part.replace("\\", "/")
        try:
            tgt = (md.parent / path_part).resolve() if path_part else md.resolve()
        except OSError:
            return "", False
        m = ID_RE.match(label.strip().strip("`*[]"))
        if m and m.group(1) in self.defs_in.get(tgt, set()):
            return m.group(1), False
        if anchor:
            hid = self.anchor_id.get(tgt, {}).get(anchor.lower())
            if hid:
                return hid, False
        fid = self.id_of_file.get(tgt, "")
        return fid, bool(fid and self.defs_in.get(tgt))

    def refines_page(self, i: str, pid: str) -> bool:
        """ID определён внутри документа, принадлежащего странице по шапке, —
        уточнение страницы в матрице (группа в README контролей и т. п.)."""
        return self.def_home.get(i, "") in self.pages.get(pid, set())

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
            gone = not (kit.docs / fcell).is_file()
            (mention if not gone and re.search(r"(?<![\w-])" + re.escape(i) + r"(?![\w.-])",
                                               kit.text) else stale).append(i)
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
    """(строки отчёта, блокеры записи). Блокер — ID ячейки, который пересборка
    потеряла бы: связи нет в документах, ID нет в комплекте, у префикса нет колонки."""
    lines: List[str] = []
    want_rows = kit.rows_of_type(row_types)
    colmap = [column_key(h) for h in sec.header]
    seen: Set[str] = set()
    missing_cells, only_matrix, misplaced, foreign_rows = [], [], [], []
    unknown, nocol = [], []
    all_prefixes = set().union(*(COL_PREFIXES[c] for c in cols))
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
            raw_ids = cell_ids(cell) - {rid}
            # неизвестный ID ловится до сведения суб-ID экрана к базовому:
            # снятый SCR-CL-01.0 иначе растворился бы в SCR-CL-01
            for i in sorted(raw_ids):
                if not kit.known(i):
                    unknown.append(f"{rid} «{COL_TITLE[ck]}»: {i}")
            m_ids = {scr_base(i) for i in raw_ids if kit.known(i)}
            if ck == "callproc":
                d_ids = {i for i in kit.related(rid, with_incoming=False)
                         if id_prefix(i) in COL_PREFIXES[ck]}
            else:
                d_ids = {i for i in rel_all if id_prefix(i) in COL_PREFIXES[ck]}
            for i in sorted(d_ids - m_ids):
                missing_cells.append(f"{rid} «{COL_TITLE[ck]}»: нет {i}")
            for i in sorted(m_ids - d_ids):
                tag = f"{rid} «{COL_TITLE[ck]}»: {i}"
                if not kit.known(i):
                    unknown.append(tag)
                elif id_prefix(i) not in all_prefixes:
                    nocol.append(tag)
                elif i in rel_all:
                    misplaced.append(tag)
                else:
                    only_matrix.append(tag)
    _emit(lines, "нет строки", sorted(want_rows - seen))
    _emit(lines, "строка не для документа этого типа", foreign_rows, 8)
    _emit(lines, "нет связи из документов", missing_cells, 8)
    _emit(lines, "связь есть, но ID не по префиксу колонки (--write перенесёт)", misplaced, 6)
    _emit(lines, "связь только в матрице — в документах ссылки нет "
                 "(--write не работает, пока перечень не пуст)", only_matrix, 8)
    _emit(lines, "ID не найден в комплекте (--write не работает, пока перечень не пуст)",
          unknown, 8)
    _emit(lines, "у префикса ID нет колонки в шаблоне (--write не работает, пока перечень "
                 "не пуст)", nocol, 8)
    return lines, only_matrix + unknown + nocol


def sources_only_matrix(sec: Section, kit: Kit) -> List[str]:
    """ID в ячейке страницы, не выводимые из шапок: известные комплекту (связь
    только в матрице) и не найденные в нём (снятые, опечатки) — блокеры записи."""
    tcol = sec.col(r"целев|артефакт", 1)
    out = []
    for r in sec.rows:
        m = re.search(r"\b(\d{6,})\b", r[0]) if r else None
        if m and tcol < len(r):
            extra = {i for i in cell_ids(r[tcol]) - kit.pages.get(m.group(1), set())
                     if not kit.refines_page(i, m.group(1))}
            out += [f"{m.group(1)}: {i}" for i in sorted(extra, key=id_sort_key)]
    return out


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
            lost = ids - have[p]
            if lost:
                diff.append(f"{p}: " + ", ".join(f"нет {x}" for x in sorted(lost)[:3]))
    lines: List[str] = []
    _emit(lines, "нет строки страницы", missing, 10)
    _emit(lines, "целевые артефакты расходятся", diff, 6)
    _emit(lines, "ID в ячейке не выводится из confluence_page_ids — связь только в матрице "
                 "или ID нет в комплекте (--write не работает, пока перечень не пуст)",
          sources_only_matrix(sec, kit), 8)
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


# ---------------------------------------------------------------- запись

def id_sort_key(i: str):
    return [(0, int(t)) if t.isdigit() else (1, t) for t in re.split(r"(\d+)", i) if t]


def _esc(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("|", "\\|")).strip() or "—"


def _row(cells: List[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(cols: List[str], rows: List[str]) -> List[str]:
    return [_row(cols), _row(["---"] * len(cols))] + rows


def _same_name(a: str, b: str) -> bool:
    """Названия совпадают без учёта тега источника «[XX_YY]», пробелов и ё/е."""
    def n(x: str) -> str:
        x = re.sub(r"^(?:\[[^\]]*\]\s*)+", "", x.replace("\\|", "|").strip())
        return re.sub(r"\s+", " ", x).lower().replace("ё", "е").strip(" .")
    return n(a) == n(b)


def _old_rows(sec: Section, lines: List[str]) -> Dict[str, List[str]]:
    t0, t1 = sec.tables[0]
    out: Dict[str, List[str]] = {}
    for ln in lines[t0 + 2:t1]:
        cells = _split_row(ln)
        i = _first_id(cells[0]) if cells else ""
        if i:
            out.setdefault(i, cells)
    return out


def build_registry(sec: Section, lines: List[str], kit: Kit) -> List[str]:
    derived = kit.derived_registry()
    manual: Dict[str, str] = {}
    old_name: Dict[str, str] = {}
    t0, t1 = sec.tables[0]
    for ln in lines[t0 + 2:t1]:
        cells = _split_row(ln)
        i = _first_id(cells[0]) if cells else ""
        if i and len(cells) > 1:
            old_name[i] = cells[1]
        if i and i not in derived and _file_cell(cells[-1]) in ("—", "-", ""):
            manual[i] = ln.rstrip()
    # Неизменённое не перезаписывается: ячейка остаётся, если факт тот же —
    # название совпадает без учёта тега, файл тот же (якорь допустим).
    # Название ID из строки таблицы выводится ненадёжно (вторая ячейка бывает
    # контуром «BE» или текстом со ссылками) — сохраняется название из реестра.
    old = _old_rows(sec, lines)
    rows = {}
    for i, (rel, name) in derived.items():
        o = old.get(i)
        nm = _esc(name)
        fl = f"`{rel}`"
        if o and len(o) == len(SECTION_COLS["registry"]):
            # существующее название остаётся, если это title или H1 документа;
            # у внутреннего ID (заголовок, строка таблицы) — всегда
            if i in kit.defs or _same_name(o[1], name) or _same_name(o[1], kit.h1.get(i, "")):
                nm = o[1]
            if _file_cell(o[2]) == rel:
                fl = o[2]
        elif i in kit.table_defs and i in old_name:
            nm = old_name[i]
        rows[i] = _row([i, nm, fl])
    rows.update(manual)
    return _table(SECTION_COLS["registry"], [rows[i] for i in sorted(rows, key=id_sort_key)])


def build_coverage(sec: Section, lines: List[str], kit: Kit, key: str) -> List[str]:
    types, cols = ({"function"}, FUN_COLS) if key == "fun" else ({"process"}, PROC_COLS)
    old = _old_rows(sec, lines)
    out = []
    for rid in sorted(kit.rows_of_type(types), key=id_sort_key):
        rel_all = kit.related(rid)
        o = old.get(rid) if rid in old and len(old[rid]) == len(cols) + 2 else None
        title = kit.fm[rid][1]
        cells = [rid, o[1] if o and _same_name(o[1], title) else _esc(title)]
        for n, ck in enumerate(cols, 2):
            src = kit.related(rid, with_incoming=False) if ck == "callproc" else rel_all
            ids = {i for i in src if id_prefix(i) in COL_PREFIXES[ck]}
            if o and {scr_base(i) for i in cell_ids(o[n])} == ids:
                cells.append(o[n])
            else:
                cells.append(", ".join(sorted(ids, key=id_sort_key)) or "—")
        out.append(_row(cells))
    return _table(SECTION_COLS[key], out)


def build_sources(sec: Section, lines: List[str], kit: Kit) -> List[str]:
    t0, t1 = sec.tables[0]
    old: Dict[str, List[str]] = {}
    for ln in lines[t0 + 2:t1]:
        cells = _split_row(ln)
        m = re.search(r"\b(\d{6,})\b", cells[0]) if cells else None
        if m:
            old[m.group(1)] = cells
    rows: Dict[str, str] = {}
    for pid, ids in kit.pages.items():
        reason = old[pid][2] if pid in old and len(old[pid]) > 2 else "—"
        if pid in old and len(old[pid]) > 1:
            ids = ids | {i for i in cell_ids(old[pid][1]) if kit.refines_page(i, pid)}
        same = pid in old and len(old[pid]) > 1 and cell_ids(old[pid][1]) == ids
        rows[pid] = _row([pid, old[pid][1] if same else ", ".join(sorted(ids, key=id_sort_key)),
                          reason or "—"])
    for pid, cells in old.items():
        # страница без артефакта с основанием — ручная строка, переносится как есть
        if pid not in rows and len(cells) > 2 and cells[2] not in ("—", "-", ""):
            rows[pid] = _row(cells)
    return _table(SECTION_COLS["sources"], [rows[k] for k in sorted(rows, key=int)])


def write(docs: Path, matrix: Optional[Path] = None) -> Tuple[List[str], int]:
    """(отчёт, код): 0 — записано или без изменений, 2 — отказ (файл не тронут)."""
    matrix = matrix or docs / MATRIX
    if not matrix.is_file():
        return [f"✗ матрицы нет: {matrix}"], 2
    raw = matrix.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    src = (raw[3:] if bom else raw).decode("utf-8")
    crlf = "\r\n" in src
    text = src.replace("\r\n", "\n")
    sections = parse_matrix(text)
    kit = Kit(docs, matrix)
    refuse: List[str] = []
    st = structure_issues(sections)
    if st:
        refuse.append(f"структура не по шаблону ×{len(st)}: " + "; ".join(st[:4])
                      + (" …" if len(st) > 4 else ""))
    by_key = {s.key: s for s in sections}
    if not st:
        for key, types, cols in (("fun", {"function"}, FUN_COLS),
                                 ("proc", {"process"}, PROC_COLS)):
            _l, only = check_coverage(by_key[key], kit, types, cols)
            if only:
                refuse.append(f"«{by_key[key].title}»: ID ячеек, которые пересборка потеряет, "
                              f"×{len(only)}: "
                              + "; ".join(only[:6]) + (" …" if len(only) > 6 else ""))
        only_src = sources_only_matrix(by_key["sources"], kit)
        if only_src:
            refuse.append(f"«{by_key['sources'].title}»: ID ячеек, которые пересборка потеряет, "
                          f"×{len(only_src)}: "
                          + "; ".join(only_src[:6]) + (" …" if len(only_src) > 6 else ""))
        reg = check_registry(by_key["registry"], kit)
        for ln in reg:
            if re.search(r"строка без документа|только упоминается|переиспользован", ln):
                refuse.append("«Реестр ID»: " + ln.strip())
    if refuse:
        return (["✗ --write отказывает, файл не тронут:"] + [f"   {x}" for x in refuse]
                + ["   сначала «--check», правка документов или ручных строк, затем повтор"]), 2
    lines = text.split("\n")
    new_tables = {
        "registry": build_registry(by_key["registry"], lines, kit),
        "fun": build_coverage(by_key["fun"], lines, kit, "fun"),
        "proc": build_coverage(by_key["proc"], lines, kit, "proc"),
        "sources": build_sources(by_key["sources"], lines, kit),
    }
    summary: List[str] = []
    for key in sorted(new_tables, key=lambda k: -by_key[k].tables[0][0]):
        t0, t1 = by_key[key].tables[0]
        old_rows, new_rows = lines[t0 + 2:t1], new_tables[key][2:]
        added = len(set(new_rows) - set(old_rows))
        removed = len(set(old_rows) - set(new_rows))
        if added or removed or lines[t0:t1] != new_tables[key]:
            summary.append(f"   «{by_key[key].title}»: строк новых или изменённых {added}, "
                           f"ушедших или изменённых {removed}")
        lines[t0:t1] = new_tables[key]
    out = "\n".join(lines)
    if out == text:
        return ["✓ выводимые разделы совпадают с документами — файл не перезаписан"], 0
    data = (b"\xef\xbb\xbf" if bom else b"") + (out.replace("\n", "\r\n") if crlf else out
                                                  ).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".matrix-", suffix=".tmp", dir=str(matrix.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, matrix)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return ["✓ выводимые разделы пересобраны (ручные разделы и строки не тронуты):"] \
        + summary[::-1], 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Выводимые разделы матрицы трассировки: "
                                 "сверка с телами документов (--check) и пересборка "
                                 "(--write).")
    ap.add_argument("--docs", type=Path, required=True, help="корень комплекта")
    ap.add_argument("--matrix", type=Path, default=None,
                    help="файл матрицы (по умолчанию <docs>/traceability-matrix.md)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="сверка (режим по умолчанию)")
    mode.add_argument("--write", action="store_true",
                      help="пересобрать выводимые разделы (ручные не трогаются)")
    args = ap.parse_args(argv)
    if args.write:
        report, code = write(args.docs, args.matrix)
        print("\n".join(report))
        return code
    report, warn = check(args.docs, args.matrix)
    print("\n".join(report))
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
