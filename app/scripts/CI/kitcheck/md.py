# app/scripts/CI/kitcheck/md.py
"""Примитивы разбора markdown комплекта: шапка документа, страницы-источники,
обход файлов комплекта, якоря GitLab, ссылки, строки таблиц, границы блоков
кода.

Функции перенесены из `selfcheck.py` дословно (этап 1б рефакторинга);
`selfcheck` реэкспортирует прежние имена. Новые примитивы — `table_cells`,
`is_fence` — повторяют поведение мест, которые их зовут, до символа:
- `table_cells` режет строку по «|» как раньше, в том числе экранированную
  «\\|» внутри ячейки (подозрение на дефект Д-1, REFACTOR_STATUS.md) —
  поведение сохранено;
- `is_fence` принимает набор маркеров явно: часть мест прибора распознаёт
  только ```` ``` ````, часть — и `~~~`; расхождение сохранено и видно в
  вызове (`FENCE_BACKTICK` против `FENCE_BOTH`).
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from kitcheck import fs as _fs
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from . import fs as _fs  # type: ignore

FENCE_BOTH: Tuple[str, ...] = ("```", "~~~")
FENCE_BACKTICK: Tuple[str, ...] = ("```",)


def is_fence(stripped_line: str, markers: Tuple[str, ...] = FENCE_BOTH) -> bool:
    """Строка открывает или закрывает блок кода. Строку обрезает вызывающий —
    как в прежнем месте (`strip()` или `lstrip()`)."""
    return stripped_line.startswith(markers)


def table_cells(line: str) -> List[str]:
    """Ячейки строки pipe-таблицы без пробелов по краям:
    `[c.strip() for c in line.strip().strip("|").split("|")]`."""
    return [c.strip() for c in line.strip().strip("|").split("|")]

_PID_RE = re.compile(r"\d{4,}")

def read_frontmatter(path: Path) -> Optional[Dict[str, str]]:
    """Плоский frontmatter файла; None — блок не закрыт (битый),
    {} — блока нет вовсе."""
    try:
        text = _fs.read_text(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return {}
    fm: Dict[str, str] = {}
    last = None
    for ln in body.splitlines()[1:200]:
        if ln.strip() == "---":
            return fm
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip()
            last = m.group(1)
        elif last and re.match(r"^\s+-\s+\S", ln):
            # многострочный YAML-список (COM-01 Корпкарт, 2026-08-27):
            # шаблон предписывает inline, но данные ВАЖНЕЕ формата —
            # элементы подклеиваются к значению ключа, чтобы карточка
            # не выпадала из сверки с источником молча; факт помечается
            # служебным ключом для ⚠ в отчёте
            fm[last] = (fm[last] + " "
                        + ln.strip().lstrip("-").strip()).strip()
            fm["__multiline-" + last] = "1"
    return None

def page_ids(fm: Dict[str, str]) -> List[str]:
    raw = fm.get("confluence_page_ids", "") + " " + \
        fm.get("confluence_page_id", "")
    return _PID_RE.findall(raw)

def is_task_file(p: Path, docs: Path) -> bool:
    """Постановка задачи forward-режима: `tasks/<JIRA-ID>.md` в корне комплекта
    (решение 2026-10-15, режим «изменение по постановке»). Текст аналитика
    хранится дословно и источником правок является сам — сверке как
    карточка не подлежит (ни внутренние сторожа, ни ссылки, ни структурные
    файлы); в матрицу не входит, карточного id не несёт."""
    try:
        rel = p.relative_to(docs)
    except ValueError:
        return False
    return len(rel.parts) >= 2 and rel.parts[0] == "tasks" and p.suffix == ".md"

def in_dot_dir(p: Path, docs: Path) -> bool:
    """Файл внутри точечного каталога (.cursor, .claude, .vscode…) — локальная
    обёртка IDE, к комплекту не относится (решение 2026-10-15, шаблон cursor/)."""
    try:
        rel = p.relative_to(docs)
    except ValueError:
        return False
    return any(part.startswith(".") for part in rel.parts[:-1])

def _kit_md(docs: Path):
    """Документы комплекта для обходов сторожей — без постановок `tasks/`."""
    return [p for p in sorted(docs.rglob("*.md"))
            if not is_task_file(p, docs) and not in_dot_dir(p, docs)]

def gitlab_slug(heading: str) -> str:
    """Якорь заголовка, как его строит GitLab: нижний регистр, без
    разметки ссылок и HTML, всё, кроме букв, цифр, «_», «-» и пробела,
    удаляется, пробел → «-», повторные дефисы схлопываются."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading.strip())
    t = re.sub(r"<[^>]+>", "", t).lower()
    t = re.sub(r"[^\w\- ]", "", t).replace(" ", "-")
    return re.sub(r"-{2,}", "-", t)

def _anchors_of(path: Path, cache: Dict[Path, set]) -> set:
    if path in cache:
        return cache[path]
    out: set = set()
    seen: Dict[str, int] = {}
    in_code = False
    try:
        lines = _fs.read_text(path, encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for ln in lines:
        if ln.strip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", ln)
        if m:
            sl = gitlab_slug(m.group(1))
            n = seen.get(sl, 0)
            seen[sl] = n + 1
            out.add(sl if n == 0 else f"{sl}-{n}")
        out.update(a.lower() for a in re.findall(r'<a\s+(?:id|name)="([^"]+)"', ln))
        out.update(a.lower() for a in re.findall(r"\{#([\w-]+)\}", ln))
    cache[path] = out
    return out

_MD_LINK_RE = re.compile(
    r"\[((?:[^\[\]\n]|\[[^\[\]\n]*\])+)\]"       # текст, один уровень [..]
    r"\(\s*([^)\s]+)(?:\s+\"[^\"\n]*\")?\s*\)")       # адрес и подсказка
