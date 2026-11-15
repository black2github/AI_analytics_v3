# app/scripts/CI/kitcheck/checks/call_one_caller.py
"""Сторож «карточка вызова — одна вызывающая функция» (шаблон contract-call.md, раздел B, пункт
«Карточка — одна вызывающая функция»; решение владельца канона 16.11.2026, постановка прибору
2026-11-16). Норма шаблона: правила заполнения и сопоставление входящего сообщения в карточке
принадлежат одной точке вызова — одной функции (процессу, экранной форме или контролю, если вызов
записан в них). Метод вызывают несколько функций — у каждой своя карточка.

Признак (структурный, слова подписи в него не входят) — в одном разделе карточки:
- две и более таблицы, у каждой подпись — абзац или заголовок прямо над таблицей (пустые строки между
  подписью и таблицей допустимы);
- подпись ссылается на документ комплекта, чей `type` во frontmatter — точка вызова по тексту нормы:
  `function`, `process`, `screen-form`, `control` (`_CALLER_TYPES`);
- наборы документов в подписях таблиц различаются.
Документ различается по файлу; контроль — по файлу и якорю (контроли живут якорями в общем файле
реестра). Раздел — участок от ближайшего заголовка выше без локальной ссылки: заголовок-подпись несёт
ссылку и раздела не открывает. Раздел любой: «Правила заполнения…» и «Сопоставление…» одинаково.
Таблицы — любые, не только с шапкой привязки «Параметр контракта | …» (шапка по шаблону стоит не у
всех карточек наследия — замер 16.11: КК 48 из 76, docs-account-opening-request 12 из 21).

Срабатывание — ✗ строкой на карточку: вызывающие функции из подписей и строки подписей. Вердикт
меняется.

Не срабатывание (законные случаи нормы и формы записи):
- несколько таблиц одного вызова без подписей (блоки сообщения, записи массива);
- одна подписанная таблица; подписи двух функций над одной таблицей;
- две подписи на один документ (шаги одной функции);
- подписи со ссылками на документы модели данных и другие не-вызыватели (блоки по сущностям);
- несколько функций в «Процессах» при одной таблице правил — общая функция и место запуска
  структурно не отделяются от объединения, класс сторожем не ловится.
Отсылка к таблице другой карточки вызова в признак не входит: на замере 16.11 она или повторяет
признак, или ложна (квитанция, ответ другого вызова как источник данных) — остаётся пунктом
чек-листа шаблона.

Вне проверки: блоки кода, HTML-комментарии, frontmatter, README реестров, документы других типов.
Слой — ядро: проверка читает только комплект (и frontmatter документов по ссылкам) и без выгрузки
работает полностью."""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, code_line_flags, read_frontmatter, table_cells  # noqa: F401
    from kitcheck.checks.call_algorithms import _COMMENT_RE, _HEAD_RE, _LINK_RE, _card_id, _is_call_card
    from kitcheck.checks.call_contract_props import _SEP_ROW_RE
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, code_line_flags, read_frontmatter, table_cells  # type: ignore  # noqa: F401
    from .call_algorithms import _COMMENT_RE, _HEAD_RE, _LINK_RE, _card_id, _is_call_card  # type: ignore
    from .call_contract_props import _SEP_ROW_RE  # type: ignore

LF = chr(10)

# Точки вызова по тексту нормы: «одной функции (процессу, экранной форме или контролю)» — значения
# `type` frontmatter документа, на который ссылается подпись таблицы.
_CALLER_TYPES = ("function", "process", "screen-form", "control")
_ANCHORED_TYPES = ("control",)  # точка вызова — якорь в общем файле реестра
_TARGET_RE = re.compile(r"\]\(([^)\s]*)")
_ID_RE = re.compile(r"^\s*([A-Z][A-Z0-9]*(?:[-.][A-Z0-9]+)+)")


def _doc_type(p: Path, cache: Dict[Path, str]) -> str:
    if p not in cache:
        fm = read_frontmatter(p) if p.is_file() else None
        cache[p] = str((fm or {}).get("type", "")).strip().strip("'\"")
    return cache[p]


def _doc_id(p: Path) -> str:
    fm = read_frontmatter(p) or {}
    return str(fm.get("id", "")).strip().strip("'\"") or p.stem


def callers(line: str, md: Path, cache: Dict[Path, str]) -> List[Tuple[str, str]]:
    """Документы-вызыватели, на которые ссылается строка: [(ключ, имя)]. Ключ — путь файла, у
    контроля — путь и якорь; имя — ID из текста ссылки, иначе id из frontmatter цели."""
    out: List[Tuple[str, str]] = []
    for m in _LINK_RE.finditer(line):
        link = m.group(0)
        if link.startswith("!"):
            continue
        t = _TARGET_RE.search(link)
        target = t.group(1) if t else ""
        if not target or target.startswith("#") or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
            continue
        path, _, anchor = target.partition("#")
        if not path.lower().endswith(".md"):
            continue
        p = (md.parent / path).resolve()
        typ = _doc_type(p, cache)
        if typ not in _CALLER_TYPES:
            continue
        key = str(p) + ("#" + anchor if typ in _ANCHORED_TYPES and anchor else "")
        label = link[1:link.rfind("](")]
        mid = _ID_RE.match(label.replace("\\", ""))
        name = mid.group(1) if mid else (anchor if typ in _ANCHORED_TYPES and anchor else _doc_id(p))
        out.append((key, name))
    return out


def analyse(text: str, md: Path, cache: Optional[Dict[Path, str]] = None) -> List[Tuple[int, List[str]]]:
    """Подписи таблиц в разделах-нарушениях: [(строка подписи с 1, [имена вызывателей])] в порядке
    текста; пусто — карточка описывает одну точку вызова."""
    cache = {} if cache is None else cache
    lines = _COMMENT_RE.sub(lambda m: LF * m.group(0).count(LF), text).splitlines()
    code = code_line_flags(lines)
    body_from = 0
    if lines and lines[0].strip() == "---":
        body_from = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    live = [ln if i >= body_from and not code[i] else "" for i, ln in enumerate(lines)]

    def is_table(ln: str) -> bool:
        return ln.lstrip().startswith("|")

    section = -1
    groups: Dict[int, List[Tuple[int, List[Tuple[str, str]]]]] = {}
    i = 0
    while i < len(live):
        ln = live[i]
        if _HEAD_RE.match(ln) and "](" not in ln:
            section = i
        if is_table(ln) and i + 1 < len(live) and _SEP_ROW_RE.match(live[i + 1]):
            k = i - 1
            while k >= 0 and not live[k].strip():
                k -= 1
            cap: List[Tuple[str, str]] = []
            cap_line = 0
            while k >= 0 and live[k].strip() and not is_table(live[k]):
                found = callers(live[k], md, cache)
                if found and not cap_line:
                    cap_line = k + 1
                cap = found + cap
                if _HEAD_RE.match(live[k]):
                    break
                k -= 1
            if cap:
                groups.setdefault(section, []).append((cap_line, cap))
            j = i + 2
            while j < len(live) and is_table(live[j]):
                j += 1
            i = j
            continue
        i += 1
    hits: List[Tuple[int, List[str]]] = []
    for caps in groups.values():
        sets = {frozenset(k for k, _n in cap) for _l, cap in caps}
        if len(caps) >= 2 and len(sets) >= 2:
            for cap_line, cap in caps:
                names = list(dict.fromkeys(n for _k, n in cap))
                hits.append((cap_line, names))
    return sorted(hits)


def check_call_one_caller(docs: Path) -> Tuple[List[str], bool]:
    """Строки отчёта и ok (False — есть ✗): ✗ строкой на карточку вызова с правилами нескольких
    вызывающих функций."""
    bad: List[str] = []
    cache: Dict[Path, str] = {}
    for md in _kit_md(docs):
        if not _is_call_card(md):
            continue
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = analyse(text, md, cache)
        if not hits:
            continue
        names = list(dict.fromkeys(n for _l, ns in hits for n in ns))
        rows = ", ".join(str(n) for n, _ns in hits)
        bad.append(f"✗ карточка вызова {_card_id(md)} ({md.relative_to(docs).as_posix()}): правила "
                   f"нескольких вызывающих функций — {', '.join(names)} (таблицы под подписями, "
                   f"строки {rows}) — разнести по карточкам: у каждой вызывающей функции своя карточка "
                   "с полным набором параметров, строки перенести дословно (шаблон contract-call.md, "
                   "«Карточка — одна вызывающая функция»)")
    return bad, not bad
