# app/scripts/CI/kitcheck/checks/task_tags.py
"""Сторож «задача объявлена введённой, тега src/<ID> нет» (2026-10-24): введена = тег
`src/<ID>` на текущей ветке репозитория сервиса (гид, «Ветки и теги»). Повод — КК,
TEAMTB-3633: журнал и состояние координации две недели называли задачу введённой, а ввода
утилитой run-history (коммит + тег) не было. Только ⚠ и i, вердикт не меняют."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
try:
    from kitcheck import fs as _fs
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore

_COORD_FILES = ("coordination-state.md", "coordination-log.md")
_UNAPPROVED = "sandbox/confluence-unapproved-jira-pages.md"
_INVENTORY = "inventory.md"
_LIMIT = 30

_ID = r"[A-Z][A-Z0-9]*-\d+"
# группа ID подряд: «TEAMTB-1, TEAMTB-2», «TEAMTB-3716/-3846/-3969» (сокращённые номера
# наследуют префикс предыдущего полного ID)
_ID_GROUP = rf"{_ID}(?:\s*(?:,|/|\bи\b)\s*(?:{_ID}|-\d+))*"
_ID_RE = re.compile(_ID)
_SHORT_RE = re.compile(rf"({_ID})|(?<![A-Z0-9])-(\d+)")
# «<ID> введена в (промышленную) эксплуатацию» (глагол обязателен: «ввод в эксплуатацию
# 30.10» — план, не факт), «<ID> в (промышленной) эксплуатации»; между группой ID и
# глаголом — не больше трёх слов без ID (тире допускается)
_GAP_WORD = r"(?![A-Z][A-Z0-9]*-\d)[^\s|;]+"
_DECL_RE = re.compile(
    rf"(?P<ids>{_ID_GROUP})(?P<gap>(?:\s+{_GAP_WORD}){{0,3}}?)\s+"
    r"(?:(?:введен[аоы]?|введён[аоы]?)\s+в\s+(?:промышленную\s+)?эксплуатацию"
    r"|в\s+(?:промышленной\s+)?эксплуатации)",
    re.I)
# «введённые задачи …: X, Y» (и в ячейке таблицы состояния через «|»)
_LIST_RE = re.compile(
    rf"введ[её]нн\w*\s+(?:в\s+\S+\s+)?задач\w*[^:|\n]{{0,40}}[:|]\s*(?P<ids>{_ID_GROUP})",
    re.I)
_NEG_RE = re.compile(r"(?:^|\s)(?:не|ещё не|еще не)(?:\s|$)|планир|будет|ожида", re.I)
_FROZEN_RE = re.compile(rf"заморожено\s+({_ID})", re.I)
_PID_RE = re.compile(r"\d{4,}")


def _text(p: Path) -> str:
    try:
        return _fs.read_text(p, encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _expand(group: str) -> List[str]:
    """Группа ID → полные ID; «-3846» после «TEAMTB-3716» → «TEAMTB-3846»."""
    out: List[str] = []
    prefix = ""
    for m in _SHORT_RE.finditer(group):
        if m.group(1):
            out.append(m.group(1))
            prefix = m.group(1).rsplit("-", 1)[0]
        elif prefix:
            out.append(f"{prefix}-{m.group(2)}")
    return out


def declared_tasks(root: Path) -> Dict[str, Tuple[str, int]]:
    """Множество A: задача → (файл, строка) первого объявления «введена/в эксплуатации».
    Отрицание или будущее время в просвете между ID и глаголом («НЕ введена»,
    «планируется ввод») — не объявление."""
    found: Dict[str, Tuple[str, int]] = {}
    for name in _COORD_FILES:
        for n, line in enumerate(_text(root / name).splitlines(), 1):
            for m in _DECL_RE.finditer(line):
                if _NEG_RE.search(m.group("gap") or ""):
                    continue
                for tid in _expand(m.group("ids")):
                    found.setdefault(tid, (name, n))
            for m in _LIST_RE.finditer(line):
                for tid in _expand(m.group("ids")):
                    found.setdefault(tid, (name, n))
    return found


def task_tags(root: Path) -> Optional[Set[str]]:
    """Множество B: ID из тегов src/<ID>, достижимых из HEAD; None — нет git."""
    if not (root / ".git").exists():
        return None
    try:
        r = subprocess.run(["git", "-C", str(root), "tag", "--merged", "HEAD", "--list", "src/*"],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {t.strip()[4:] for t in r.stdout.splitlines() if t.strip().startswith("src/")}


def _cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _frozen_rows(path: Path, tagged: Set[str], by_column: bool) -> List[Tuple[str, str, str]]:
    """(page_id, title, ID) строк таблицы, где страница числится замороженной по задаче
    из `tagged`: список замороженных — по колонке unapproved_jira (без шапки — по всей
    строке), опись — по основанию «заморожено <ID>»."""
    out: List[Tuple[str, str, str]] = []
    col: Optional[int] = None
    for line in _text(path).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        low = [c.lower() for c in cells]
        if by_column and "unapproved_jira" in low:
            col = low.index("unapproved_jira")
            continue
        if not cells or not _PID_RE.fullmatch(cells[0]):
            continue
        title = cells[1] if len(cells) > 1 else ""
        if by_column:
            src = cells[col] if col is not None and col < len(cells) else line
            ids = _ID_RE.findall(src)
        else:
            ids = _FROZEN_RE.findall(line)
        for tid in dict.fromkeys(ids):
            if tid in tagged:
                out.append((cells[0], title, tid))
    return out


def _capped(rows: List[str]) -> List[str]:
    if len(rows) <= _LIMIT:
        return rows
    return rows[:_LIMIT] + [f"   … и ещё {len(rows) - _LIMIT}"]


def check_task_tags(docs: Path) -> List[str]:
    """Корень репозитория сервиса — родитель `docs` (в репозитории документации, где
    комплект в корне, — сам `docs`). Нет журнала, состояния и списка замороженных —
    молчание; есть, но нет git — одна i-строка."""
    names = _COORD_FILES + (_UNAPPROVED,)
    root = next((r for r in (docs.parent, docs) if any((r / f).is_file() for f in names)), None)
    if root is None:
        return []
    tagged = task_tags(root)
    if tagged is None:
        return ["i теги задач не проверены (нет git)"]
    rep: List[str] = []
    for tid, (name, n) in sorted(declared_tasks(root).items()):
        if tid not in tagged:
            label = "журнал" if name == "coordination-log.md" else "состояние"
            rep.append(f"⚠ задача объявлена введённой, тега src/{tid} нет: {tid} "
                       f"({label}: {name}, строка {n}) — ввод делается run-history "
                       "(гид, «Ветки и теги»)")
    frozen: List[str] = []
    for pid, title, tid in _frozen_rows(root / _UNAPPROVED, tagged, by_column=True):
        frozen.append(f"⚠ страница {pid} «{title}» числится замороженной по задаче {tid}, "
                      f"а задача введена тегом src/{tid} — список устарел, пересчитать "
                      "(run-history)")
    for pid, title, tid in _frozen_rows(root / _INVENTORY, tagged, by_column=False):
        frozen.append(f"⚠ опись: страница {pid} «{title}» — основание «заморожено {tid}», "
                      f"а задача введена тегом src/{tid} — опись устарела, пересчитать "
                      "(run-history)")
    return rep + _capped(frozen)
