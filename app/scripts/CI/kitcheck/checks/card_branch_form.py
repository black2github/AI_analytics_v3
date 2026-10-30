# app/scripts/CI/kitcheck/checks/card_branch_form.py
"""Проверки карточки: сторож формы ветвления.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import re
from typing import List, Tuple
from ..md import code_line_flags
from ..branch_form import (
    _BRANCH_IF_RE, _BRANCH_OUT_RE, _branch_mention, _guillemet_spans, normalize_branch_form
)
_BRANCH_SEG_RE = re.compile(r"<br\s*/?>", re.I)
_BRANCH_LEAD_RE = re.compile(r"^(?:\s|&nbsp;|&emsp;|&ensp;|>|[-*+•](?=\s)|\d+[.)](?=\s))*")


def branch_form_offenders(lines: List[str]) -> List[str]:
    """Фрагменты, где **то** / **иначе** стоит не в начале строки, ячейки или
    отрезка между `<br>` после **Если** (или после исхода того же отрезка).
    Блоки кода и `инлайн-код` не проверяются (инлайн-код — содержание условия:
    заменяется словом-заглушкой); упоминание конструкции в прозе — не ветвление;
    слово-исход внутри «ёлочек» (цитата, литерал) — не проверяется, как и в
    нормализаторе (симметрия защит, FB-24)."""
    out: List[str] = []
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
                for m in _BRANCH_OUT_RE.finditer(body):
                    if m.start() == 0 or _branch_mention(body, m.start()):
                        continue
                    if any(a <= m.start() < b for a, b in quoted):
                        continue
                    if seen_if or opened or _BRANCH_IF_RE.search(body[:m.start()]):
                        out.append(body.strip()[:70])
                        break
                if _BRANCH_IF_RE.search(body):
                    seen_if = True
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
    bad = branch_form_offenders(fx.lines)
    report: List[str] = []
    if bad:
        report.append(
            f"предупреждение: форма ветвления — «**то**»/«**иначе**» не в начале "
            f"строки после «**Если**» ×{len(bad)} (notation §1: условие и каждый "
            "исход со своей строки — в ячейке `<br>`, вне таблиц — строки списка)")
        for b in bad[:2]:
            report.append(f"      пример: {b!r}")
    return report, True
