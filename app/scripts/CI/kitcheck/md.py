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
- границы блоков кода — правило `kitcheck/fence.py`, одно для прибора и для
  разметки CriticMarkup (`critic.py`, бандл confluence-tree-exporter):
  вложенность по виду и длине ограждения (решение владельца 2026-10-17);
  `is_fence` — строка-ограждение, `code_line_flags` — разметка строк,
  `blank_code` и `code_blocks` — для мест, где блоки вырезались регулярками.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from kitcheck import fence as _fence
    from kitcheck import fs as _fs
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from . import fence as _fence  # type: ignore
    from . import fs as _fs  # type: ignore

FENCE_BOTH: Tuple[str, ...] = ("```", "~~~")
FENCE_BACKTICK: Tuple[str, ...] = ("```",)

# формула пробела источника: единственная допустимая пометка в чистовике (conventions §6 п.5);
# один дом — здесь, её импортируют перечень формулы (checks/content.py) и сторож колонок (columns.py)
SILENT_FORMULA = "в постановке не задано"


def is_fence(stripped_line: str, markers: Tuple[str, ...] = FENCE_BOTH) -> bool:
    """Строка — ограждение блока кода (правило `fence.fence_of`). Открывает
    она блок или закрывает, решает разметка строк (`code_line_flags`), а не
    эта функция. Строку обрезает вызывающий; `markers` сужает набор."""
    return (stripped_line.startswith(markers)
            and _fence.fence_of(stripped_line) is not None)


def code_line_flags(lines: List[str]) -> List[bool]:
    """По строке: True — ограждение или строка внутри блока кода. Вложенность
    по виду и длине: ``` внутри ```` — содержимое (`fence.code_flags`)."""
    return _fence.code_flags(lines)


# Навигационный список: оглавление страницы, дом такого перечня в комплекте — README каталога.
# Признаки только по разметке. Блок — связный список, включая вложенные уровни. Пункт — одна
# ссылка целиком либо название: текст без ссылок, жирных слов нотации, тегов, запятых, «=», цифр и
# знаков конца предложения. Один пункт иного вида (условие, присваивание, число с единицей, текст
# после ссылки) — блок не навигация и сверяется как прежде.
# Порог доли ссылок — замер 2026-11-07: в выгрузках всех сервисов у 422 блоков из 422 доля 1,0, в
# карточках у оглавлений от 0,75 (PROC-048 КК: часть ссылок заменена названиями без адреса),
# у списков из двух пунктов встречается 0,5 — они навигацией не считаются.
NAV_LINK_SHARE = 0.7
_NAV_ITEM_RE = re.compile(r"^ *(?:[-+*]|\d+[.)])\s+(.*\S)\s*$")
_NAV_LINK_RE = re.compile(r"^\[(?:\\.|[^\]\\\[]|\[[^\]]*\])*\]\((?:[^()]|\([^()]*\))*\)$")
_NAV_NOT_TITLE_RE = re.compile(r"\]\(|\*\*|__|<|=|,|\d|[.!?;:]\s*$|[.!?;]\s")


def nav_list_blocks(text: str) -> List[Tuple[int, int]]:
    """Навигационные списки текста: (первая строка, строка за последней), нумерация от нуля.
    Строки блоков кода списком не считаются."""
    lines = text.split("\n")
    code = code_line_flags(lines)
    out: List[Tuple[int, int]] = []

    def close(start: Optional[int], end: int, links: int, titles: int, other: bool) -> None:
        if start is not None and links and not other and links / (links + titles) >= NAV_LINK_SHARE:
            out.append((start, end))

    start: Optional[int] = None
    links = titles = 0
    other = False
    for i, ln in enumerate(lines):
        m = None if code[i] else _NAV_ITEM_RE.match(ln.rstrip("\r"))
        if m is None:
            close(start, i, links, titles, other)
            start, links, titles, other = None, 0, 0, False
            continue
        if start is None:
            start = i
        item = m.group(1)
        if _NAV_LINK_RE.match(item):
            links += 1
        elif _NAV_NOT_TITLE_RE.search(item):
            other = True
        else:
            titles += 1
    close(start, len(lines), links, titles, other)
    return out


def blank_nav_lists(text: str) -> Tuple[str, int, int]:
    """(текст без навигационных списков, блоков, пунктов). Число строк сохраняется."""
    blocks = nav_list_blocks(text)
    if not blocks:
        return text, 0, 0
    lines = text.split("\n")
    for start, end in blocks:
        lines[start:end] = [""] * (end - start)
    return "\n".join(lines), len(blocks), sum(end - start for start, end in blocks)


_INLINE_TRIPLE_RE = re.compile(r"```.*?```")


def blank_code(text: str, repl: str = " ", inline: bool = True) -> str:
    """Текст без блоков кода: каждый блок (от ограждения до ограждения
    включительно; незакрытый — до конца текста) заменяется одной строкой
    `repl`. inline=True — ещё и пары ``` в пределах одной строки (строчный
    кодовый спан GFM). Непарная ``` в строке остаётся текстом и не
    спаривается со следующим блоком: прежняя регулярка ```.*?``` по всему
    тексту вырезала всё между ними, и ссылки и теги там не проверялись."""
    lines = text.split("\n")
    end_of = {b.start: b.end for b in _fence.blocks(lines)}
    out: List[str] = []
    k = 0
    while k < len(lines):
        if k in end_of:
            out.append(repl)
            k = end_of[k] + 1
            continue
        ln = lines[k]
        if inline and "```" in ln:
            ln = _INLINE_TRIPLE_RE.sub(" ", ln)
        out.append(ln)
        k += 1
    return "\n".join(out)


def code_blocks(text: str) -> List[str]:
    """Содержимое блоков кода (без строк-ограждений) по правилу
    `kitcheck/fence.py`; незакрытый блок — до конца текста."""
    lines = text.split("\n")
    return ["\n".join(lines[b.start + 1:b.end if b.closed else len(lines)])
            for b in _fence.blocks(lines)]


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _code_chunks(text: str) -> List[Tuple[bool, str]]:
    """Текст кусками (в блоке кода?, кусок) по правилу `kitcheck/fence.py`;
    "\\n".join кусков даёт исходный текст байт в байт."""
    lines = text.split("\n")
    flags = _fence.code_flags(lines)
    out: List[Tuple[bool, str]] = []
    start = 0
    for k in range(1, len(lines) + 1):
        if k == len(lines) or flags[k] != flags[start]:
            out.append((flags[start], "\n".join(lines[start:k])))
            start = k
    return out


def html_comments(text: str) -> List[str]:
    """HTML-комментарии вне блоков кода. Комментарий внутри ``` … ``` —
    содержимое примера (XML-образец payload источника), а не служебная
    пометка чистовика (proc-033 КК, 2026-11-02)."""
    return [c for is_code, chunk in _code_chunks(text) if not is_code
            for c in _HTML_COMMENT_RE.findall(chunk)]


def strip_html_comments(text: str, repl: str = " ") -> str:
    """Текст без HTML-комментариев вне блоков кода (К-13: значение,
    спрятанное в комментарии, сверкой не «находится»); внутри блоков кода
    комментарии — дословное содержимое примера и остаются для сверки."""
    return "\n".join(chunk if is_code else _HTML_COMMENT_RE.sub(repl, chunk)
                     for is_code, chunk in _code_chunks(text))


# Нотация атрибута после ссылки на сущность: срез пишет `[ENT-…](…).<Атрибут>` (выгрузка —
# `.\<Атрибут\>`), чистовик по нотации техбука — `.«Атрибут»` (КК PROM-5.3-NOT, 2026-11-01).
# Для сверок с источником это одна запись: `.<X>` сводится к `.«X»`, каждое звено цепочки.
# Признак — точка перед скобкой (срез пишет и «Клиент Банка. <X>» — один пробел допустим, форма
# сводится к `.«X»` без пробела; КК ent-015/ent-019); `<X>` без точки (подстановка в дословном
# тексте) и HTML-тег после точки («….<br>», «.<p class="x">», «.</td>») не трогаются.
_ATTR_ANGLE_RE = re.compile(r"\.[ \t]?\\?<(?![/!])([^<>\n]+?)\\?>")
_HTML_TAG_BODY_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:\s+[a-z][a-z0-9-]*(?:=(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?)*\s*/?")


def norm_attr_notation(text: str) -> str:
    """`.<X>` и `.\\<X\\>` → `.«X»`; HTML-теги и `<X>` без точки — как есть."""
    return _ATTR_ANGLE_RE.sub(
        lambda m: m.group(0) if _HTML_TAG_BODY_RE.fullmatch(m.group(1))
        else f".«{m.group(1)}»", text)


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


def stray_table_lines(text: str) -> List[Tuple[int, str]]:
    """[(номер строки с 1, строка)] — строки, которые разбор таблиц не видит, хотя они стоят в
    таблице (постановка 2026-11-09, П-6; КК 7d6781c9: строка долга разорвана переводом строки,
    обрубок с BOM без ведущего «|» шёл сразу за строками таблицы — matrix_sync и link_debts его
    не видели, прибор молчал). Признаки по форме: непустая строка без ведущего «|» сразу после
    строки таблицы (не заголовок «#»), и строка с BOM в начале, кроме первой строки файла.
    Абзац после пустой строки и блоки кода — не таблица."""
    lines = text.split("\n")
    flags = code_line_flags(lines)
    out: List[Tuple[int, str]] = []
    in_table = False
    for i, raw in enumerate(lines):
        s = raw.rstrip("\r")
        if flags[i]:
            in_table = False
            continue
        if i > 0 and s.startswith("﻿"):
            out.append((i + 1, s))
            in_table = s.lstrip("﻿").startswith("|")
            continue
        if not s.strip():
            in_table = False
        elif s.startswith("|"):
            in_table = True
        elif in_table and not s.lstrip().startswith("#"):
            out.append((i + 1, s))
        else:
            in_table = False
    return out


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

# Каталоги выгрузки внутри комплекта (пакет П3 ОНБ-В, п. 1, 2026-11-09): у комплекта в корне
# репозитория (`--docs .`) рядом с `srs/` лежат каталог выгрузки (`--sources`, у ОНБ-В —
# `confluence/`) и `sources/` (профиль источников, внешние источники). Страницы выгрузки и
# профиль — не документы комплекта: обход их не включает, признак — путь, не содержимое.
# Каталоги `--sources` прогона задаёт точка входа (`set_source_dirs`); `sources/` под корнем
# комплекта исключается всегда. Число снятых файлов печатает selfcheck строкой i.
_SOURCE_DIRS: List[Path] = []


def set_source_dirs(paths) -> None:
    """Каталоги выгрузки прогона (`--sources`), исключаемые из обхода комплекта."""
    _SOURCE_DIRS[:] = [Path(p).resolve() for p in paths if p]


def in_sources_dir(p: Path, docs: Path, sources: Optional[Path] = None) -> bool:
    """Файл в каталоге выгрузки внутри комплекта: `sources/` под корнем `docs` или каталог,
    переданный прогону как `--sources` (через `set_source_dirs` или явно — `sources`)."""
    try:
        rel = p.relative_to(docs)
    except ValueError:
        return False
    if len(rel.parts) >= 2 and rel.parts[0] == "sources":
        return True
    dirs = list(_SOURCE_DIRS) + ([Path(sources).resolve()] if sources is not None else [])
    if not dirs:
        return False
    rp = p.resolve()
    return any(rp.is_relative_to(s) for s in dirs)

def _kit_md(docs: Path):
    """Документы комплекта для обходов сторожей — без постановок `tasks/`, точечных
    каталогов и каталогов выгрузки внутри комплекта (`in_sources_dir`). Часть вне контура
    Экосистемы — обычная часть `docs/srs/<слаг>/`: путь её не выделяет, признак читается из
    разметки профиля источников (source_profile)."""
    return [p for p in sorted(docs.rglob("*.md"))
            if not is_task_file(p, docs) and not in_dot_dir(p, docs)
            and not in_sources_dir(p, docs)]

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
    try:
        lines = _fs.read_text(path, encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for ln, in_code in zip(lines, code_line_flags(lines)):
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
