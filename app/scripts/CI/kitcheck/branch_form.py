# app/scripts/CI/kitcheck/branch_form.py
"""Правка формы ветвления (notation §1): нормализатор `--branch-form` и сторож формы
ветвления считают по одной функции `normalize_branch_form`.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена."""
import re
from typing import Dict, List, Optional, Tuple
from .md import code_line_flags


# ПР-15 ОНБ-В (волна 5; стандарт notation.md §1 «Форма ветвления — одна»):
# условие и каждый исход со своей строки — **то** / **иначе** / **иначе если**
# открывают строку (в ячейке таблицы — после `<br>`, вне таблиц — строкой
# списка). Слово-исход посреди строки после **Если** (или после другого
# исхода той же строки) — предупреждение, вердикт не меняет. Сосед —
# сторожа сплющивания «≥2 если в строке» (✗, только зоны ЭФ).
_BRANCH_OUT_RE = re.compile(r"\*\*(?:то|иначе(?:\s+если)?)[:,]?\*\*", re.I)
_BRANCH_IF_RE = re.compile(r"\*\*(?:иначе\s+)?если[:,]?\*\*", re.I)


def _branch_mention(body: str, pos: int) -> bool:
    """Исход на pos — упоминание конструкции в прозе, не ветвление: между ним и
    предыдущим словом конструкции того же отрезка нет содержания («в форме
    **Если**/**то**/**иначе**», «слова **Если**, **то**, **иначе**», «ветвлением
    «**Если** …, **то** …»» — шаблоны и правила канона, FB-24)."""
    prev = [m.end() for rx in (_BRANCH_IF_RE, _BRANCH_OUT_RE)
            for m in rx.finditer(body, 0, pos)]
    return bool(prev) and not re.search(r"\w", body[max(prev):pos])


# Нормализация формы ветвления (решения владельца 2026-10-19; правило — стандарт
# notation.md §1 «Форма ветвления — одна»; FB-24 КК, решение А — одна механика везде):
# «**Если** X, **то** Y, **иначе** Z» одной строкой → «**Если** X,<br>**то** Y,<br>**иначе** Z»
# в ячейке таблицы, в элементе списка и в абзаце тела (образец канона — controls.md,
# «Логика проверки» элементом списка с <br>). Только отрезки, где сторож branch_form даёт ⚠.
# Не трогаются: заголовки, шапка документа, блоки кода, HTML-комментарии, текст в «ёлочках»
# и "кавычках" (литералы сообщений), инлайн-код, отрезок с вложенным условием (два **Если**
# или **Если** после исхода — вложенность человеку). Маркер списка, отступ и ярлык перед
# **Если** («- **Логика проверки:** **Если** …») остаются; строка с «то» в конце и исходами
# подпунктами — перенос перед «то», подпункты не сдвигаются. Отступ &nbsp; отрезка
# переносится на новые строки. Идемпотентно.
_BRANCH_INDENT_RE = re.compile(r"^(?:\s|&nbsp;|&emsp;|&ensp;)*")
_BRANCH_MARKER_RE = re.compile(r"^(?:>|[-*+•](?=\s)|\d+[.)](?=\s))\s*")
_BRANCH_PLAIN_IF_RE = re.compile(r"(?<!иначе )\*\*если[:,]?\*\*", re.I)


def _guillemet_spans(body: str) -> List[Tuple[int, int]]:
    """Отрезки «…» с вложенностью; незакрытая «ёлочка» отрезка не даёт."""
    spans: List[Tuple[int, int]] = []
    depth, start = 0, 0
    for i, ch in enumerate(body):
        if ch == "«":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "»" and depth:
            depth -= 1
            if depth == 0:
                spans.append((start, i + 1))
    return spans


def _branch_protected(body: str) -> List[Tuple[int, int]]:
    """Отрезки, которые не разрезаются: «…» с вложенностью, "…", `…`."""
    spans = _guillemet_spans(body)
    for m in re.finditer(r'"[^"\n]*"|`[^`\n]*`', body):
        spans.append(m.span())
    return spans


def _branch_fix_segment(seg: str, seen_if: bool) -> Tuple[str, int, str]:
    """(отрезок, вставлено переносов, причина пропуска или «»). Начало отрезка — отступ
    и маркер списка — сохраняется; на новых строках повторяется только отступ &nbsp;."""
    indent = _BRANCH_INDENT_RE.match(seg).group(0)
    rest = seg[len(indent):]
    mk = _BRANCH_MARKER_RE.match(rest)
    marker = mk.group(0) if mk else ""
    body = rest[len(marker):]
    cont = re.sub(r"[ \t]", "", indent)
    prot = _branch_protected(body)
    free = lambda pos: not any(a <= pos < b for a, b in prot)  # noqa: E731
    ifs = [m.start() for m in _BRANCH_IF_RE.finditer(body) if free(m.start())]
    # «**иначе**, **если** …» и «**Иначе** (**если** …» — та же цепочка, что «**иначе если**»
    plain_ifs = [m.start() for m in _BRANCH_PLAIN_IF_RE.finditer(body) if free(m.start())
                 and not re.search(r"(?i)иначе\*\*[\s,(]*$", body[:m.start()])]
    opened = bool(_BRANCH_OUT_RE.match(body))
    outs = [m.start() for m in _BRANCH_OUT_RE.finditer(body) if free(m.start())]
    cut = [p for p in outs if p > 0 and (seen_if or opened or any(i < p for i in ifs))
           and not _branch_mention(body, p)]
    if not cut:
        return seg, 0, ""
    # вложенность: два простых **Если** или **Если** после исхода («**то** **Если** …»);
    # цепочка «**иначе если**» — не вложенность
    if len(plain_ifs) > 1 or (plain_ifs and (opened or any(o < plain_ifs[0] for o in outs))):
        return seg, 0, "вложенное условие"
    for pos in reversed(cut):
        body = body[:pos].rstrip() + "<br>" + cont + body[pos:]
    return indent + marker + body, len(cut), ""


def _branch_fix_line(text: str, kind: str, skipped: Dict[str, int]) -> Tuple[str, int]:
    """Отрезки строки (или ячейки) между <br>: перенос перед словом-исходом."""
    segs = re.split(r"(<br\s*/?>)", text, flags=re.I)
    seen_if = False
    total = 0
    for j in range(0, len(segs), 2):
        lead = 1 if (j == 0 and kind == "cell") else 0  # пробел после «|» — часть ячейки
        head = segs[j][:len(segs[j]) - len(segs[j].lstrip(" "))] if lead else ""
        seg = segs[j][len(head):]
        new, cnt, why = _branch_fix_segment(seg, seen_if)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
        if cnt:
            segs[j] = head + new
            total += cnt
        if _BRANCH_IF_RE.search(seg):
            seen_if = True
    return "".join(segs), total


def normalize_branch_form(text: str, kinds: Optional[Dict[str, int]] = None
                          ) -> Tuple[str, int, Dict[str, int]]:
    """(текст, вставлено переносов, пропуски по причинам); kinds — счётчик переносов по
    видам мест («ячейки», «списки», «абзацы»). EOL сохраняется."""
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    total = 0
    skipped: Dict[str, int] = {}
    kinds = kinds if kinds is not None else {}
    fm_end = -1
    if lines and lines[0].lstrip("\ufeff").strip() == "---":
        fm_end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), -1)
    in_comment = False
    for n, (ln, in_code) in enumerate(zip(lines, code_line_flags(lines))):
        if n <= fm_end or in_code:
            continue
        if in_comment:
            if "-->" in ln:
                in_comment = False
            continue
        if "<!--" in ln and "-->" not in ln[ln.index("<!--"):]:
            in_comment = True
            continue
        if "**" not in ln or ln.lstrip().startswith("#"):
            continue
        if ln.lstrip().startswith("|"):
            cells = re.split(r"(?<!\\)\|", ln)
            cnt_line = 0
            for k in range(1, len(cells) - 1):
                cells[k], cnt = _branch_fix_line(cells[k], "cell", skipped)
                cnt_line += cnt
            if cnt_line:
                lines[n] = "|".join(cells)
                kinds["ячейки"] = kinds.get("ячейки", 0) + cnt_line
                total += cnt_line
            continue
        if re.search(r"<!--", ln):
            continue  # однострочный комментарий в строке — не трогать
        kind = "списки" if _BRANCH_MARKER_RE.match(ln[len(_BRANCH_INDENT_RE.match(ln).group(0)):]) else "абзацы"
        new, cnt = _branch_fix_line(ln, kind, skipped)
        if cnt:
            lines[n] = new
            kinds[kind] = kinds.get(kind, 0) + cnt
            total += cnt
    return eol.join(lines), total, skipped
