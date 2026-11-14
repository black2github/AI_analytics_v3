# app/scripts/CI/kitcheck/checks/method_function_contour.py
"""Сторож «контур функции метода не совпадает с контуром контракта» (шаблоны internal-contracts.md и
function.md, норма канона 14.11.2026; решение постановщика по замеру 14.11). Функция, в которой
описано поведение метода с карточкой internal-contract, получает контур по авторизации метода:
обращение по токену пользователя — клиентская или банковская функция (FUN-CL / FUN-BNK), ТУЗ —
системная (FUN-SYS). Контур функции совпадает с подкаталогом контракта (client/, bank/, system/).

Признак — по структуре, без слов источника:
- пара «функция ↔ контракт» — ссылка функции на карточку контракта в строке «по контракту …»
  либо общая страница в confluence_page_ids. Пара по ссылке главнее: если у функции или у контракта
  есть пара по ссылке, их пары по странице не считаются;
- контур функции — префикс идентификатора (FUN-CL / FUN-BNK / FUN-SYS, со слотом части —
  FUN-<КОД>-SYS-NN); идентификатор без контура — вне проверки;
- контур контракта — подкаталог internal-contract/<client|bank|system>/. Строка паспорта
  «Авторизация» — вторым источником, только при одном однозначном значении (Bearer token →
  клиентская или банковская, Basic authorization / ТУЗ → системная) и только когда подкаталога нет:
  расхождение подкаталога с «Авторизацией» — отдельный класс, в этот признак не подмешивается.

Строка ⚠ уровня комплекта с числом пар и первыми идентификаторами, перечень — в --out; вердикт не
меняет: в комплектах наследие прежней нормы (функция метода — системная), ошибкой проверка станет
отдельным решением владельца после захода команд.

Вне проверки: расхождение префикса идентификатора функции с её каталогом, «Авторизация» с двумя
значениями или без значения — отдельные классы.

Слой — ядро: проверка читает только комплект и без выгрузки работает полностью."""
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, code_line_flags, read_frontmatter
    from kitcheck.checks.call_algorithms import _COMMENT_RE
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, code_line_flags, read_frontmatter  # type: ignore
    from .call_algorithms import _COMMENT_RE  # type: ignore

# строки, которые selfcheck пишет только в файл отчёта --out (тот же префикс, что selfcheck.OUT_ONLY)
_OUT_ONLY = "   · "
LF = chr(10)
_DIR = "internal-contract"
_SUBDIRS = {"client": "CL", "bank": "BNK", "system": "SYS"}
_FUN_CONTOUR_RE = re.compile(r"^FUN-(?:[A-Z0-9]+-)?(CL|BNK|SYS)-\d")
_PAGE_RE = re.compile(r"\d{5,}")
_BY_CONTRACT_RE = re.compile(r"по\s+контракту", re.I)
_MD_LINK_RE = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)\s]*)?\)")
_AUTH_RE = re.compile(r"^\|?\s*\**\s*Авторизация\s*:?\s*\**\s*:?\s*\|?\s*(.*?)\s*\|?\s*$", re.I)
_NAME = {"CL": "клиентская (FUN-CL)", "BNK": "банковская (FUN-BNK)", "SYS": "системная (FUN-SYS)"}


def _type(fm: Dict[str, str]) -> str:
    return str(fm.get("type", "")).strip().strip("'\"")


def _id(fm: Dict[str, str], md: Path) -> str:
    return str(fm.get("id", "")).strip().strip("'\"") or md.stem


def _pages(fm: Dict[str, str]) -> Set[str]:
    return set(_PAGE_RE.findall(str(fm.get("confluence_page_ids", ""))))


def _live_lines(text: str) -> List[str]:
    lines = _COMMENT_RE.sub(lambda m: LF * m.group(0).count(LF), text).splitlines()
    code = code_line_flags(lines)
    return ["" if code[i] else ln for i, ln in enumerate(lines)]


def fun_contour(fid: str) -> Optional[str]:
    """Контур функции по префиксу идентификатора: CL / BNK / SYS или None."""
    m = _FUN_CONTOUR_RE.match(fid)
    return m.group(1) if m else None


def auth_contours(lines: List[str]) -> Optional[Set[str]]:
    """Допустимые контуры функции по строке «Авторизация» паспорта: одно однозначное значение —
    {CL, BNK} (Bearer) или {SYS} (Basic / ТУЗ); иначе None."""
    for ln in lines:
        if "Авторизация" not in ln:
            continue
        m = _AUTH_RE.match(ln.strip())
        if not m:
            continue
        val = m.group(1).lower()
        bearer = "bearer" in val
        basic = "basic" in val or "туз" in val
        if bearer and not basic:
            return {"CL", "BNK"}
        if basic and not bearer:
            return {"SYS"}
        return None
    return None


def contract_contours(rel: str, lines: List[str]) -> Optional[Set[str]]:
    """Допустимые контуры функции метода для карточки контракта: по подкаталогу
    internal-contract/<client|bank|system>/, без подкаталога — по однозначной «Авторизации»."""
    parts = rel.split("/")[:-1]
    if _DIR in parts:
        i = parts.index(_DIR)
        sub = parts[i + 1] if i + 1 < len(parts) else ""
        if sub in _SUBDIRS:
            return {_SUBDIRS[sub]}
    return auth_contours(lines)


def find_pairs(docs: Path) -> List[Tuple[Path, str, Path, str, str]]:
    """Пары (функция, её ID, контракт, его ID, «ссылка» | «страница»)."""
    funs: List[Tuple[Path, str, Dict[str, str]]] = []
    intcs: Dict[Path, Tuple[str, Dict[str, str]]] = {}
    for md in _kit_md(docs):
        if md.name.lower() == "readme.md":
            continue
        fm = read_frontmatter(md) or {}
        t = _type(fm)
        if t == "function":
            funs.append((md, _id(fm, md), fm))
        elif t == "internal-contract":
            intcs[md.resolve()] = (_id(fm, md), fm)
    link_pairs: Set[Tuple[Path, Path]] = set()
    for md, _fid, _fm in funs:
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ln in _live_lines(text):
            if not _BY_CONTRACT_RE.search(ln):
                continue
            for target in _MD_LINK_RE.findall(ln):
                p = (md.parent / target).resolve()
                if p in intcs:
                    link_pairs.add((md.resolve(), p))
    linked_f = {f for f, _ in link_pairs}
    linked_c = {c for _, c in link_pairs}
    out: List[Tuple[Path, str, Path, str, str]] = []
    for md, fid, fm in funs:
        f = md.resolve()
        fp = _pages(fm)
        for c, (cid, cfm) in intcs.items():
            if (f, c) in link_pairs:
                out.append((md, fid, c, cid, "ссылка"))
            elif f not in linked_f and c not in linked_c and fp & _pages(cfm):
                out.append((md, fid, c, cid, "страница"))
    return out


def check_method_function_contour(docs: Path) -> List[str]:
    """Строка ⚠ комплекта с числом пар, где контур функции метода не совпадает с контуром
    контракта, и первыми парами; перечень «функция ↔ контракт — что» — в --out."""
    bad: List[Tuple[str, str, str]] = []
    root = docs.resolve()
    for fmd, fid, c, cid, how in find_pairs(docs):
        have = fun_contour(fid)
        if have is None:
            continue
        try:
            crel = c.relative_to(root).as_posix()
            text = _fs.read_text(c, encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue
        want = contract_contours(crel, _live_lines(text))
        if not want or have in want:
            continue
        frel = fmd.relative_to(docs).as_posix()
        need = " или ".join(_NAME[w] for w in ("CL", "BNK", "SYS") if w in want)
        bad.append((f"{fid} ↔ {cid}", frel,
                    f"{_OUT_ONLY}{frel} ({fid}) ↔ {crel} ({cid}), пара по {'ссылке' if how == 'ссылка' else 'странице'}"
                    f" — функция {_NAME[have]}, по контракту — {need}"))
    if not bad:
        return []
    bad.sort(key=lambda r: r[1])
    head = ", ".join(p for p, _, _ in bad[:3]) + (f", и ещё {len(bad) - 3}" if len(bad) > 3 else "")
    return ([f"⚠ функция метода — контур функции не совпадает с контуром контракта: {len(bad)} пар "
             f"({head}) — контур функции метода — по подкаталогу контракта: client/ → FUN-CL, bank/ → "
             "FUN-BNK, system/ → FUN-SYS (шаблоны internal-contracts.md, function.md); переименование "
             "функции — с правкой ссылок на неё"]
            + [line for _, _, line in bad])
