# app/scripts/CI/kitcheck/md.py
"""Примитивы разбора markdown комплекта: шапка документа, страницы-источники,
обход файлов комплекта, якоря GitLab, ссылки, строки таблиц, границы блоков
кода.

Функции перенесены из `selfcheck.py` дословно (этап 1б рефакторинга);
`selfcheck` реэкспортирует прежние имена. Новые примитивы — `table_cells`,
`is_fence` — повторяют поведение мест, которые их зовут, до символа:
- `table_cells` (и `split_cells`, `strip_row`, `count_cells`) режет строку по
  неэкранированным «|»: «\\|» внутри ячейки — часть текста (дефект Д-1
  исправлен 2026-10-17); на строках без «\\|» результат прежний;
- `is_fence` — правило ограждения блока кода общего кода бандла
  confluence-tree-exporter (`critic._FENCE_RE`), одно для всех мест прибора
  (решение владельца 2026-10-17, исследование «Прибор — распознавание блоков
  кода и ограждений»); `code_line_flags` и `blank_code` — границы блоков по
  тому же правилу для мест, где блоки вырезались регулярками.
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


# Ограждение блока кода — правило `critic._FENCE_RE` (общий код бандла
# confluence-tree-exporter, выбор миграции 2026-09-06): строка целиком —
# ``` или ~~~ (3+) с любым отступом; у ``` инфо-строка без «`» (CommonMark):
# строка ```"filter"``: { — склеенный инлайн-код выгрузки, а не ограждение
# (такие строки открывали мнимую код-зону, накрывавшую требования). Вид и
# длина не учитываются: любое ограждение и открывает, и закрывает блок;
# незакрытый блок — код до конца файла. Копия держится равной critic
# тестом (tests/test_kitcheck_core.py).
_FENCE_LINE_RE = re.compile(r"^[ \t]*(?:`{3,}[^`\n]*|~{3,}[^\n]*)\r?\n?$")


def is_fence(stripped_line: str, markers: Tuple[str, ...] = FENCE_BOTH) -> bool:
    """Строка открывает или закрывает блок кода (правило `_FENCE_LINE_RE`).
    Строку обрезает вызывающий (`strip()` или `lstrip()`); `markers` сужает
    набор маркеров (места прибора зовут с обоими)."""
    return (stripped_line.startswith(markers)
            and _FENCE_LINE_RE.match(stripped_line) is not None)


def code_line_flags(lines: List[str]) -> List[bool]:
    """По строке: True — ограждение или строка внутри блока кода."""
    out: List[bool] = []
    inside = False
    for ln in lines:
        if is_fence(ln.strip()):
            inside = not inside
            out.append(True)
        else:
            out.append(inside)
    return out


_INLINE_TRIPLE_RE = re.compile(r"```.*?```")


def blank_code(text: str, repl: str = " ", inline: bool = True) -> str:
    """Текст без блоков кода: каждый блок (от ограждения до ограждения
    включительно; незакрытый — до конца текста) заменяется одной строкой
    `repl`. inline=True — ещё и пары ``` в пределах одной строки (строчный
    кодовый спан GFM). Непарная ``` в строке остаётся текстом и не
    спаривается со следующим блоком: прежняя регулярка ```.*?``` по всему
    тексту вырезала всё между ними, и ссылки и теги там не проверялись."""
    lines = text.split("\n")
    flags = code_line_flags(lines)
    out: List[str] = []
    k = 0
    while k < len(lines):
        if flags[k]:
            j = k + 1
            while j < len(lines) and not is_fence(lines[j].strip()):
                j += 1
            out.append(repl)
            k = j + 1
            continue
        ln = lines[k]
        if inline and "```" in ln:
            ln = _INLINE_TRIPLE_RE.sub(" ", ln)
        out.append(ln)
        k += 1
    return "\n".join(out)


def code_blocks(text: str) -> List[str]:
    """Содержимое блоков кода (без строк-ограждений) по правилу `is_fence`;
    незакрытый блок — до конца текста."""
    lines = text.split("\n")
    out: List[str] = []
    k = 0
    while k < len(lines):
        if is_fence(lines[k].strip()):
            j = k + 1
            while j < len(lines) and not is_fence(lines[j].strip()):
                j += 1
            out.append("\n".join(lines[k + 1:j]))
            k = j + 1
            continue
        k += 1
    return out


def _escaped_at(s: str, i: int) -> bool:
    """Символ s[i] экранирован: перед ним нечётное число «\\»."""
    n = 0
    while i - n - 1 >= 0 and s[i - n - 1] == "\\":
        n += 1
    return n % 2 == 1


def split_cells(inner: str) -> List[str]:
    """Режет текст строки таблицы по неэкранированным «|» (GFM: «\\|» внутри
    ячейки — часть её текста, не граница; Д-1, исправлено 2026-10-17).
    Ячейки — как в тексте, с «\\|» и пробелами: перезапись строки (matrix_sync)
    сохраняет байты. Без «\\|» — ровно `inner.split("|")`."""
    if "\\|" not in inner:
        return inner.split("|")
    out: List[str] = []
    start = 0
    for i, ch in enumerate(inner):
        if ch == "|" and not _escaped_at(inner, i):
            out.append(inner[start:i])
            start = i + 1
    out.append(inner[start:])
    return out


def strip_row(line: str) -> str:
    """Текст строки таблицы без пробелов и крайних «|»; экранированная «\\|» в
    конце последней ячейки не срезается. Без «\\|» — `line.strip().strip("|")`."""
    s = line.strip()
    if "\\|" not in s:
        return s.strip("|")
    s = s.lstrip("|")
    while s.endswith("|") and not _escaped_at(s, len(s) - 1):
        s = s[:-1]
    return s


def count_cells(line: str) -> int:
    """Число ячеек строки таблицы (для сверки шапки с сепаратором)."""
    return len(split_cells(strip_row(line)))


def table_cells(line: str) -> List[str]:
    """Ячейки строки pipe-таблицы без пробелов по краям; «\\|» внутри ячейки —
    часть её текста (`split_cells`). Без «\\|» — прежнее
    `[c.strip() for c in line.strip().strip("|").split("|")]`."""
    return [c.strip() for c in split_cells(strip_row(line))]

_PID_RE = re.compile(r"\d{4,}")


def frontmatter_end(lines: List[str]) -> int:
    """Индекс первой строки тела после шапки; 0 — шапки нет или она не
    закрыта. Граница — правило `read_frontmatter`, одно для всех мест
    прибора (решение владельца 2026-10-17): BOM в начале снимается, шапка
    открывается строкой на «---» и закрывается ближайшей строкой «---»
    (без учёта пробелов) в пределах 200 строк; «---» внутри значения —
    не граница."""
    if not lines or not lines[0].lstrip("﻿").startswith("---"):
        return 0
    for k in range(1, min(len(lines), 200)):
        if lines[k].strip() == "---":
            return k + 1
    return 0


def frontmatter_split(text: str) -> Tuple[Optional[str], str]:
    """(текст шапки без строк «---», тело) по границе `frontmatter_end`.
    Шапки нет или она не закрыта — (None, весь текст без BOM): тело
    проверяется целиком, ничего не отрезается молча."""
    body = text.lstrip("﻿")
    lines = body.splitlines(keepends=True)
    end = frontmatter_end(lines)
    if not end:
        return None, body
    return "".join(lines[1:end - 1]), "".join(lines[end:])


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
        if is_fence(ln.strip()):
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
