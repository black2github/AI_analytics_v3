# app/scripts/CI/kitcheck/checks/card_branch_form.py
"""Проверки карточки: сторож формы ветвления.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import re
from typing import List, Tuple
from ..md import code_line_flags
from ..branch_form import (
    _BRANCH_ELSE_RE, _BRANCH_IF_RE, _BRANCH_OUT_RE, _branch_mention, _branch_nested,
    _guillemet_spans, normalize_branch_form
)
_BRANCH_SEG_RE = re.compile(r"<br\s*/?>", re.I)
_BRANCH_LEAD_RE = re.compile(r"^(?:\s|&nbsp;|&emsp;|&ensp;|>|[-*+•](?=\s)|\d+[.)](?=\s))*")
_LIST_ITEM_RE = re.compile(r"^(\s*)(?:[-*+•]|\d+[.)])\s+(.*)$")
_MD_LINK_RE = re.compile(r"\[(?:[^\[\]]|\[[^\]]*\])*\]\([^)]*\)")
_OUTCOME_END_RE = re.compile(r"\*\*(?:то|иначе(?:\s+если)?)[:,]?\*\*[:,]?\s*$", re.I)
_THEMATIC_BREAK_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")


def branch_form_hits(lines: List[str]) -> List[Tuple[bool, str]]:
    """(вложенное условие?, фрагмент) мест сторожа: **иначе** / **иначе если** не в начале
    строки, ячейки или отрезка между `<br>` после **Если** (или после исхода того же отрезка);
    положение **то** не проверяется: он стоит на строке условия, прежняя запись `,<br>**то**`
    допустима. Вложенное условие в одном отрезке (определение нормализатора) остаётся
    местом сторожа и без **иначе**: другого сигнала вне зон ЭФ у него нет, правит человек.
    Блоки кода и `инлайн-код` не проверяются (инлайн-код — содержание условия:
    заменяется словом-заглушкой); упоминание конструкции в прозе — не ветвление;
    слово-исход внутри «ёлочек» (цитата, литерал) — не проверяется, как и в
    нормализаторе (симметрия защит, FB-24)."""
    out: List[Tuple[bool, str]] = []
    for ln, in_code in zip(lines, code_line_flags(lines)):
        if in_code or "**" not in ln:
            continue
        clean = re.sub(r"`[^`\n]*`", " код ", ln)
        cells = re.split(r"(?<!\\)\|", clean) if clean.lstrip().startswith("|") else [clean]
        for cell in cells:
            seen_if = False
            for seg in _BRANCH_SEG_RE.split(cell):
                body = seg[_BRANCH_LEAD_RE.match(seg).end():]
                opened = bool(_BRANCH_OUT_RE.match(body))
                quoted = _guillemet_spans(body)
                nested = _branch_nested(body, lambda pos: not any(a <= pos < b for a, b in quoted))
                for m in _BRANCH_OUT_RE.finditer(body):
                    if m.start() == 0 or _branch_mention(body, m.start()):
                        continue
                    if any(a <= m.start() < b for a, b in quoted):
                        continue
                    if not (nested or _BRANCH_ELSE_RE.match(body, m.start())):
                        continue
                    if seen_if or opened or _BRANCH_IF_RE.search(body[:m.start()]):
                        out.append((nested, body.strip()[:70]))
                        break
                if _BRANCH_IF_RE.search(body):
                    seen_if = True
    return out


def branch_form_offenders(lines: List[str]) -> List[str]:
    """Фрагменты всех мест сторожа формы ветвления (см. branch_form_hits)."""
    return [frag for _nested, frag in branch_form_hits(lines)]


def _outcome_left_level(lines: List[str], flags: List[bool], i: int, indent: int) -> bool:
    """Следующая непустая строка после пункта i стоит не глубже него. Таблица, блок кода,
    заголовок, разделитель и конец файла — не считаются: исход может быть таблицей или
    кодом, а раздел мог закончиться."""
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines) or flags[j]:
        return False
    stripped = lines[j].lstrip()
    if (stripped.startswith(("|", "#", "<!--")) or stripped.lower().startswith("<table")
            or _THEMATIC_BREAK_RE.match(stripped)):
        return False
    return len(lines[j][:len(lines[j]) - len(stripped)].expandtabs(4)) <= indent


def branch_no_outcome(lines: List[str]) -> List[Tuple[int, str]]:
    """(номер строки, фрагмент) пунктов списка, которые заканчиваются на **то** или **иначе**,
    а следом идёт текст не глубже пункта: исходы съехали на уровень условия (у **иначе** исходы
    по тому же правилу, что у **то**). Признак по форме записи. Инлайн-код и ссылка заменяются
    заглушкой, а не удаляются: «**то** [MSG-1](#m)» — исход есть. В ячейке таблицы признак не
    применяется. Упоминание конструкции в прозе и незакрытая цитата «… — не ветвление."""
    flags = code_line_flags(lines)
    out: List[Tuple[int, str]] = []
    for i, (ln, in_code) in enumerate(zip(lines, flags)):
        if in_code or "**" not in ln:
            continue
        item = _LIST_ITEM_RE.match(ln)
        if not item:
            continue
        body = _MD_LINK_RE.sub(" ссылка ", re.sub(r"`[^`\n]*`", " код ", item.group(2)))
        end = _OUTCOME_END_RE.search(body)
        if not end or _branch_mention(body, end.start()):
            continue
        if body.count("«", 0, end.start()) > body.count("»", 0, end.start()):
            continue
        if _outcome_left_level(lines, flags, i, len(item.group(1).expandtabs(4))):
            out.append((i + 1, item.group(2).strip()[-70:]))
    return out


def branch_form_counts(text: str) -> Tuple[int, int]:
    """(мест сторожа формы ветвления, мест после сухого прогона --branch-form) —
    для сводной строки комплекта: закроет нормализатор = разность, вручную —
    остаток (вложенные условия)."""
    n = len(branch_form_offenders(text.splitlines()))
    if not n:
        return 0, 0
    new, _cnt, _skipped = normalize_branch_form(text)
    return n, len(branch_form_offenders(new.splitlines()))


def _fc_branch_form(fx: "_FileCtx") -> Tuple[List[str], bool]:
    # самопроверка комплекта сводит сторож в одну строку (selfcheck._kc_branch_form,
    # решение владельца пилота 2026-10-20); строка на файл — одиночной проверке
    if fx.kit_summary:
        return [], True
    hits = branch_form_hits(fx.lines)
    bad = [frag for nested, frag in hits if not nested]
    deep = [frag for nested, frag in hits if nested]
    report: List[str] = []
    if bad:
        report.append(
            f"предупреждение: форма ветвления — «**иначе**» не в начале строки после "
            f"«**Если**» ×{len(bad)} (нотация §1: «иначе» со своей строки — в ячейке `<br>`, "
            "вне таблиц — строка списка)")
        for b in bad[:2]:
            report.append(f"      пример: {b!r}")
    if deep:
        report.append("предупреждение: форма ветвления — второе «**Если**» в строке после исхода "
                      f"(вложенное условие одной строкой) ×{len(deep)}")
        for b in deep[:2]:
            report.append(f"      пример: {b!r}")
    lost = branch_no_outcome(fx.lines)
    if lost:
        report.append("предупреждение: форма ветвления: «то»/«иначе» без исхода — следующий пункт "
                      f"на уровне условия ×{len(lost)}")
        for _n, b in lost[:2]:
            report.append(f"      пример: {b!r}")
    return report, True
