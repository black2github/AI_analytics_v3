# -*- coding: utf-8 -*-
"""Смысловой разбор поля ЭФ (проход 2a → 2b) по references/categories.md."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

SECTION_LABELS: list[tuple[str, str]] = [
    ("visibility", "Отображение на ЭФ:"),
    ("visibility", "Условие отображения:"),
    ("visibility", "Видимость:"),
    ("visibility", "Отображается на ЭФ:"),
    ("logic_list", "Формирование списка:"),
    ("logic_list", "Логика формирования списка:"),
    ("logic_default", "Предзаполнение:"),
    ("logic_default", "По умолчанию:"),
    ("logic_source", "Источник списка:"),
    ("format_display", "Формат отображения:"),
    ("format_display", "Сортировка списка:"),
    ("logic_change", "Действия при изменении значения в данном поле:"),
    ("logic_change", "Действия при изменении значения:"),
    ("logic_change", "Доп. действия"),
    ("fill_lock", "Доступность других полей:"),
    ("reaction", "Кнопка:"),
    ("format_text", "Текст:"),
    ("format_text", "Заголовок:"),
]

# Границы, обрывающие секцию (в т.ч. visibility) — начало логики/списка, не видимости
SECTION_BOUNDARY_LABELS: list[str] = [
    "Выбор из списка",
    "Предзаполнение и доступность",
    "Предзаполнение:",
    "Формирование списка:",
    "Логика формирования списка:",
    "Источник списка:",
    "Формат отображения:",
    "Сортировка списка:",
    "Действия при изменении значения в данном поле:",
    "Действия при изменении значения:",
    "Доп. действия",
    "Доступность других полей:",
    "Кнопка:",
    "Группа 1.",
    "Группа 2.",
    "Логика вычисления",
    "Поле заполняется",
    "Поле имеет",
    "Реализовать",
    "Выбор из списка записей",
]

# Только метки раздела в начале текста — не «отображается на ЭФ» внутри условия
VISIBILITY_LABEL_PREFIX_RE = re.compile(
    r"(?i)^(?:\*\*)?(?:[-–—]\s*)?(?:отображение на эф|условие отображения|видимость)"
    r"(?:\*\*)?\s*(?:\([^)]*\))?\s*:?\s*"
)

INLINE_VISIBILITY_PREFIX_RE = re.compile(
    r"(?i)^отображается на эф,?\s*"
)

VISIBILITY_TAIL_MARKERS: list[str] = [
    "логика вычисления",
    "поле заполняется",
    "поле имеет",
    "реализовать",
    "выбор из списка записей",
    "предзаполнение и доступность",
    "формат отображения",
    "текст по правилу",
    "пример:",
    "доступность других пол",
]

VISIBILITY_MARKERS = (
    "отображение на эф",
    "условие отображения",
    "видимость:",
    "наименование поля не отображается",
    "название поля не отображается",
    "наименование блока не отображается",
    "поле не отображается",
    "не отображается, если",
    "отображается, если",
    "отображается на эф",
    "скрытое поле",
    "свёрнут",
    "развёрнут",
    "полуразвёрнут",
)

RULE_PATTERNS: list[tuple[str, str, bool]] = [
    (r"(?i)проверка длины|длина реквизита", "Проверка длины поля", True),
    (r"(?i)только цифр|состоять из \d+ цифр", "Проверка формата (только цифры)", True),
    (r"(?i)контрол.{0,20}ключеван", "Проверка по контролю", True),
    (r"(?i)не может превышать|должн[аоы].{0,30}совпад", "Межполевая проверка", False),
]


def cell_text(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def bold_ifthen(text: str) -> str:
    text = re.sub(r"(?i)\bесли\b", "**Если**", text)
    text = re.sub(r"(?i)\bто\b", "**то**", text)
    text = re.sub(r"(?i)\bиначе\b", "**иначе**", text)
    return text


def section_end(plain: str, start: int, hits: list[tuple[int, str, str]], index: int) -> int:
    """Конец текущей секции: следующая метка раздела или граница логики/списка."""
    end = hits[index + 1][0] if index + 1 < len(hits) else len(plain)
    low = plain.lower()
    for marker in SECTION_BOUNDARY_LABELS:
        idx = low.find(marker.lower(), start)
        if start < idx < end:
            end = idx
    return end


def truncate_at_boundaries(text: str) -> str:
    low = text.lower()
    end = len(text)
    for marker in SECTION_BOUNDARY_LABELS:
        idx = low.find(marker.lower())
        if 0 < idx < end:
            end = idx
    return text[:end].strip().rstrip("-–—:;.").strip()


def strip_visibility_labels(text: str) -> str:
    """Убрать служебные префиксы «Отображение на ЭФ:» только в начале текста."""
    t = text.strip()
    prev = None
    while t != prev:
        prev = t
        t = VISIBILITY_LABEL_PREFIX_RE.sub("", t, count=1).strip()
        t = INLINE_VISIBILITY_PREFIX_RE.sub("", t, count=1).strip()
    t = re.sub(r"(?i)^\*\*\s*[-–—]?\s*", "", t).strip()
    t = re.sub(r"(?i)^поле отображается на эф\s*", "", t).strip()
    return t


def polish_visibility_condition(text: str) -> str:
    """Убрать артефакты разметки, не относящиеся к условию (не трогая лейбл)."""
    text = re.sub(r"(?i)^поле не отображается:\s*[-–]?\s*", "", text.strip())
    text = re.sub(r"(?i)^поле отображается на эф\s*", "", text.strip())
    text = re.sub(r"(?i)^заголовок не отображается на эф\s*", "", text.strip())
    text = re.sub(r"^[\*\s\-–—,;:]+", "", text).strip()
    return text


def is_visibility_reference_only(text: str) -> bool:
    """Ссылка на другое место вместо условия видимости — не контроль."""
    low = cell_text(text).lower()
    return bool(
        re.search(
            r"(?i)условие отображения описаны|условия отображения описаны|описаны в (поле|блоке)",
            low,
        )
    )


def extract_label_visibility_prefix(vis_raw: str) -> tuple[str, str]:
    """Префикс про скрытый лейбл (ось видимости) + остаток условия."""
    plain = cell_text(vis_raw)
    for pat, label in [
        (r"(?i)^(название поля не отображается на эф)", "Название поля не отображается на ЭФ"),
        (r"(?i)^(наименование поля не отображается)", "Наименование поля не отображается"),
        (r"(?i)^(наименование блока не отображается)", "Наименование блока не отображается"),
    ]:
        m = re.match(pat + r"\.?\s*[-–—.]?\s*(.*)", plain, re.S)
        if m:
            rest = m.group(2).strip()
            return label, rest
    return "", plain


def split_value_formula_from_visibility(text: str) -> str:
    """Отделить формулу значения от условия показа (categories.md: формулы — не в видимости)."""
    t = text.strip()
    m = re.search(r"(?is)(.+?\bне\s+пусто)\s*=\s*.+$", t)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"(?is)^(?:[-–—]\s*)?(?:если\b\s+)(.+?)\s*[-–—]\s*то\s+"
        r"(?!\b(?:отображается|не\s+отобража(?:ется|ется)|скрыт|нет)\b)"
        r"(.+?)\s*[-–—]\s*иначе\s+(.+)$",
        t,
    )
    if m:
        cond = m.group(1).strip().rstrip("-–—,")
        else_out = m.group(3).strip()
        if re.search(r"(?i)не\s+отображ", else_out):
            return f"Если {cond}, то отображается, иначе не отображается"
        return f"Если {cond}, то не отображается, иначе отображается"
    return t


def complete_if_then_outcome(text: str, *, negated: bool = False) -> str:
    """Дополнить неполное «если …» до полного Если-то-иначе про показ/скрытие."""
    t = text.strip()
    if re.search(r"(?i)\bто\b", t):
        if not re.search(r"(?i)\bиначе\b", t):
            if re.search(r"(?i)не\s+отображ", t):
                t += ", иначе отображается"
            else:
                t += ", иначе не отображается"
        return t
    if re.search(r"(?i)\bиначе\b", t):
        return t
    m = re.search(r"(?is)(?:если\b\s+)(.+)", t)
    if not m:
        return t
    cond = m.group(1).strip().rstrip(".")
    if negated:
        return f"Если {cond}, то не отображается, иначе отображается"
    return f"Если {cond}, то отображается, иначе не отображается"


def semantic_normalize_visibility(text: str, vis_raw: str = "") -> str:
    """Смысловая нормализация: только показ/скрытие, без формул значения."""
    label, rest = extract_label_visibility_prefix(vis_raw) if vis_raw else ("", text)
    if label:
        text = rest or text
    negated = bool(
        vis_raw
        and re.search(r"(?i)поле не отображается|нет записей", cell_text(vis_raw))
    )
    text = split_value_formula_from_visibility(text)
    text = complete_if_then_outcome(text, negated=negated)
    text = polish_visibility_condition(text)
    if label:
        text = f"{label}. {text}".strip()
    return text


def truncate_visibility_tail(text: str) -> str:
    """Обрезать хвост после первого полного Если-то-иначе (логика заполнения и т.п.)."""
    low = text.lower()
    end = len(text)
    for marker in VISIBILITY_TAIL_MARKERS:
        idx = low.find(marker)
        if 0 < idx < end:
            end = idx
    text = text[:end].strip().rstrip(".")
    m = re.search(
        r"(?is)(.+?\bиначе\b[^.]{0,160}(?:отображается|не отображается|нет|скрыт)[^.]*)",
        text,
    )
    if m:
        return m.group(1).strip().rstrip(".")
    return text


def visibility_body(vis_raw: str) -> str:
    """Текст условия видимости: ось «Видимость» — только показ/скрытие."""
    text = cell_text(vis_raw)
    text = strip_visibility_labels(text)
    text = truncate_at_boundaries(text)
    text = truncate_visibility_tail(text)
    text = semantic_normalize_visibility(text, vis_raw)
    return re.sub(r"\s+", " ", text).strip()


def clean_visibility_condition(vis_raw: str) -> str:
    """Условие visibility для контроля: только Если-то-иначе."""
    text = visibility_body(vis_raw)
    return bold_ifthen(text) if text else ""


def should_extract_visibility(vis_raw: str) -> bool:
    """Механический критерий вынесения (controls.md): ветвление ∨ внешнее состояние."""
    if not vis_raw or is_visibility_reference_only(vis_raw):
        return False
    body = visibility_body(vis_raw)
    if not body or is_visibility_reference_only(body):
        return False
    low = body.lower()
    if "скрытое поле" in low and "не отображается" in low:
        return False
    if re.search(r"(?i)отображается всегда|всегда отображ|^всегда$", body):
        return False
    if count_visibility_branching(body) > 1:
        return True
    if has_external_ref(body):
        return True
    return False


def resolve_visibility_extract(
    fields: list,
    analyses: dict,
    field_key_fn,
) -> None:
    """Повторный проход: вынести, если условие разделяют несколько полей (критерий 2)."""
    buckets: dict[str, list[str]] = {}
    for f in fields:
        a = analyses.get(field_key_fn(f))
        if not a or not a.visibility_control_text:
            continue
        key = a.visibility_control_text[:200]
        buckets.setdefault(key, []).append(field_key_fn(f))

    for f in fields:
        a = analyses.get(field_key_fn(f))
        if not a or not a.visibility_control_text:
            continue
        if a.visibility_extract:
            continue
        if is_visibility_reference_only(a.visibility_control_text):
            continue
        key = a.visibility_control_text[:200]
        if len(buckets.get(key, [])) > 1:
            a.visibility_extract = True


def split_sections(plain: str) -> tuple[dict[str, list[str]], str]:
    """Разбивка ячейки по меткам разделов; preamble — текст до первой метки."""
    hits: list[tuple[int, str, str]] = []
    low = plain.lower()
    for axis, label in SECTION_LABELS:
        start = 0
        label_low = label.lower()
        while True:
            idx = low.find(label_low, start)
            if idx < 0:
                break
            hits.append((idx, axis, label))
            start = idx + len(label_low)

    hits.sort(key=lambda x: x[0])
    sections: dict[str, list[str]] = {}
    preamble = plain[: hits[0][0]].strip() if hits else plain.strip()

    for i, (idx, axis, label) in enumerate(hits):
        end = section_end(plain, idx + len(label), hits, i)
        chunk = plain[idx + len(label) : end].strip()
        if chunk:
            sections.setdefault(axis, []).append(f"**{label.rstrip(':')}:** {chunk}")

    return sections, preamble


def classify_preamble(preamble: str) -> dict[str, list[str]]:
    """Классификация текста до первой метки раздела."""
    if not preamble:
        return {}
    low = preamble.lower()
    out: dict[str, list[str]] = {}

    if any(m in low for m in VISIBILITY_MARKERS):
        out.setdefault("visibility", []).append(preamble)
    elif re.search(r"(?i)выводится|отображается (кратк|полн|значен)", preamble):
        out.setdefault("logic_value", []).append(preamble)
        if re.search(r"(?i)кратк.{0,30}наименован", preamble):
            out.setdefault("format_constraint", []).append(
                "краткое наименование, если указано, иначе полное *(из типа)*"
            )
    elif re.search(r"(?i)пример\s*:|маск[аи]\s*:|не более \d|плейсхолдер", preamble):
        out.setdefault("format_constraint", []).append(preamble)
    elif re.search(r"(?i)формирование списка|предзаполнение|источник списка", preamble):
        out.setdefault("logic_misc", []).append(preamble)
    else:
        out.setdefault("misc", []).append(preamble)
    return out


def is_visibility_text(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in VISIBILITY_MARKERS)


def has_external_ref(text: str) -> bool:
    return bool(
        re.search(
            r"\[.*?\]\([^)]*datamodel|Заявка\s*\.|<[А-ЯA-Z][^>]+>|справочник|полномоч|ЕСК|настраиваем",
            text,
            re.I,
        )
    )


def count_visibility_branching(text: str) -> int:
    count = len(re.findall(r"(?i)\bесли\b", text))
    if count <= 1:
        return count
    if re.search(r"(?i)если\s+.+\s+если", text):
        return count
    if re.search(r"(?i)иначе\s+если", text):
        return 2
    if text.lower().count("иначе") >= 2:
        return count
    if count == 2 and re.search(r"(?i)если.+то.+иначе", text):
        return 1
    return count


def format_visibility_cell(vis_text: str) -> str:
    cleaned = clean_visibility_condition(vis_text)
    if not cleaned:
        return "Всегда"
    low = cleaned.lower()
    if "скрытое поле" in low:
        return "Скрытое поле (не отображается)"
    if re.search(r"(?i)отображается всегда|всегда отображ|^всегда$", cleaned.strip()):
        return "Всегда"
    return cleaned


def extract_visibility_raw(comment_raw: str) -> str:
    """Ось видимости — только из колонки «Комментарий», без «Логики заполнения»."""
    plain = cell_text(comment_raw)
    sections, preamble = split_sections(plain)
    pre_parts = classify_preamble(preamble)
    chunks = sections.get("visibility", []) + pre_parts.get("visibility", [])
    parts = [strip_visibility_labels(c) for c in chunks if strip_visibility_labels(c)]
    return " ".join(parts).strip()


def split_sections_from_blobs(comment_raw: str, fill_raw: str) -> tuple[dict[str, list[str]], str]:
    """Разбивка по меткам в plain-тексте и в markdown/HTML исходника."""
    plain = cell_text(f"{comment_raw} {fill_raw}")
    sections, preamble = split_sections(plain)

    for axis, label in SECTION_LABELS:
        patterns = [
            label,
            f"**{label.rstrip(':')}:**",
            f"<strong>{label}</strong>",
        ]
        blob = f"{comment_raw} {fill_raw}"
        low_blob = blob.lower()
        for pat in patterns:
            pat_low = pat.lower()
            start = 0
            while True:
                idx = low_blob.find(pat_low, start)
                if idx < 0:
                    break
                end = len(blob)
                for axis2, label2 in SECTION_LABELS:
                    for pat2 in (label2, f"**{label2.rstrip(':')}:**"):
                        j = low_blob.find(pat2.lower(), idx + len(pat))
                        if j > idx:
                            end = min(end, j)
                for marker in SECTION_BOUNDARY_LABELS:
                    j = low_blob.find(marker.lower(), idx + len(pat))
                    if j > idx:
                        end = min(end, j)
                chunk = cell_text(blob[idx + len(pat) : end]).strip()
                if chunk:
                    sections.setdefault(axis, []).append(f"**{label.rstrip(':')}:** {chunk}")
                start = idx + len(pat)

    return sections, preamble


def derive_fill_mode(fill_raw: str, sections: dict[str, list[str]], plain: str) -> str:
    fill_plain = cell_text(fill_raw).strip()
    low_fill = fill_plain.lower()

    if "выбор из списка" in low_fill:
        base = "Выбор из списка"
    elif "автоматически" in low_fill and "вручную" not in low_fill:
        base = "Автоматически"
    elif "вручную" in low_fill:
        base = "Вручную"
    elif fill_plain and len(fill_plain) < 60:
        base = fill_plain
    else:
        base = ""

    lock_blob = " ".join(sections.get("fill_lock", []))
    if re.search(r"(?i)недоступн|не доступн|заблокир|неактивн|не редактир", lock_blob + plain):
        cond = re.search(
            r"(?i)(недоступн[^.]{0,120}|не доступн[^.]{0,120}|заблокир[^.]{0,80})",
            lock_blob or plain,
        )
        if cond:
            return f"Автоматически, {cond.group(0).strip()}; иначе {base or 'Вручную'}"

    prefill = " ".join(sections.get("logic_default", []))
    if prefill and re.search(r"(?i)предзаполн|по умолчанию", prefill):
        if re.search(r"(?i)одн[аоу].{0,20}единственн", prefill):
            return f"Автоматически, если у пользователя одна связанная организация; иначе {base or 'Выбор из списка'}"
        if re.search(r"(?i)иначе", prefill) and base in ("Выбор из списка", "Вручную", ""):
            return f"Автоматически при создании; иначе {base or 'Выбор из списка'}"

    return base or "Вручную"


def derive_required(required_raw: str) -> str:
    req = cell_text(required_raw).strip()
    if not req:
        return "—"
    low = req.lower()
    if low in ("да", "yes"):
        return "Да"
    if low in ("нет", "no"):
        return "Нет"
    if re.search(r"(?i)услов|если", req):
        return "см. SF"
    return req


def derive_format(ui_type: str, sections: dict[str, list[str]], preamble_parts: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for key in ("format_display", "format_text", "format_constraint"):
        for chunk in sections.get(key, []) + preamble_parts.get(key, []):
            parts.append(chunk)

    plain_chunks = " ".join(parts)
    for pat in [
        r"(?i)пример[:\s][^.]{0,200}",
        r"(?i)маск[аи][^.]{0,120}",
        r"(?i)не более \d+[^.]{0,80}",
        r"(?i)\d+ символ",
        r"(?i)плейсхолдер[^.]{0,80}",
    ]:
        m = re.search(pat, plain_chunks)
        if m and m.group(0) not in parts:
            parts.append(m.group(0).strip())

    if ui_type.lower() in ("заголовок", "иконка", "информер"):
        return "—" if not parts else "<br>".join(parts)

    fmt = "<br>".join(parts) if parts else ""
    return fmt or "—"


def derive_logic(
    fill_raw: str,
    sections: dict[str, list[str]],
    preamble_parts: dict[str, list[str]],
    fmt_text: str,
) -> str:
    parts: list[str] = []
    fill_plain = cell_text(fill_raw).strip()
    if (
        fill_plain
        and "отображ" not in fill_plain.lower()
        and not re.match(r"(?i)^(выбор из списка|вручную|автоматически)\s*$", fill_plain)
    ):
        parts.append(fill_plain)

    for key in (
        "logic_list",
        "logic_default",
        "logic_source",
        "logic_change",
        "logic_value",
        "logic_misc",
    ):
        parts.extend(sections.get(key, []))
        parts.extend(preamble_parts.get(key, []))

    for m in re.finditer(r'=\s*"[^"]+"|=\s*[^.;]{5,120}', " ".join(parts)):
        token = m.group(0).strip()
        if token not in parts:
            parts.append(token)

    logic = "<br><br>".join(parts) if parts else "—"
    return logic


def normalize_ui_type(
    declared: str,
    fill_mode: str,
    logic: str,
    plain: str,
    fill_raw: str,
) -> str:
    low = declared.lower()
    blob = f"{plain} {fill_raw} {logic}".lower()

    if low.startswith("тип сообщения") or "информер" in low:
        return "Информер"
    if low == "заголовок":
        return "Заголовок"
    if low == "иконка":
        return "Иконка"
    if low == "изображение":
        return "Изображение"
    if low == "переключатель" or "переключатель" in blob:
        return "Переключатель"
    if low == "чекбокс":
        return "Чекбокс"
    if "выбор из списка" in blob or "формирование списка" in blob or fill_mode == "Выбор из списка":
        return "Список"
    if low == "текст" and ("список" in blob or "организац" in blob and "выбор" in blob):
        return "Список"
    return declared or "Текст"


def find_rule_fragments(name: str, plain: str, sections: dict[str, list[str]]) -> list[tuple[str, str, str, bool]]:
    """(title, condition, message, reactive) — только фрагменты оси Контроль."""
    excluded = set()
    for key in (
        "logic_list",
        "logic_default",
        "logic_source",
        "logic_change",
        "logic_value",
        "logic_misc",
        "visibility",
        "fill_lock",
        "format_display",
        "format_text",
        "reaction",
    ):
        for s in sections.get(key, []):
            excluded.add(s.lower())

    rules: list[tuple[str, str, str, bool]] = []
    for pat, title, reactive in RULE_PATTERNS:
        m = re.search(pat, plain)
        if not m:
            continue
        ctx_start = max(0, m.start() - 40)
        ctx_end = min(len(plain), m.end() + 400)
        ctx = plain[ctx_start:ctx_end]
        if any(ex in ctx.lower() for ex in excluded if len(ex) > 20):
            continue
        if "формирование списка" in ctx.lower() or "предзаполнение" in ctx.lower():
            continue
        cond = bold_ifthen(ctx[:500])
        msg_m = re.search(r"(?i)сообщени[ея][^.]{0,200}|текст[^.]{0,150}", ctx)
        msg = msg_m.group(0).strip() if msg_m else "—"
        rules.append((f"{title} «{name}»", cond, msg, reactive))
        break
    return rules


@dataclass
class FieldAnalysis:
    ui_type: str
    fmt: str
    fill_mode: str
    required: str
    visibility: str
    logic: str
    visibility_extract: bool = False
    visibility_control_text: str = ""
    rule_fragments: list[tuple[str, str, str, bool]] = field(default_factory=list)


def analyze_field(
    *,
    name: str,
    ui_type: str,
    fill_raw: str,
    required_raw: str,
    comment_raw: str,
    is_block: bool = False,
) -> FieldAnalysis:
    if is_block:
        vis_raw = extract_visibility_raw(comment_raw)
        vis_cell = format_visibility_cell(vis_raw) if vis_raw else "Всегда"
        return FieldAnalysis(
            ui_type="Заголовок",
            fmt="—",
            fill_mode="Автоматически",
            required="—",
            visibility=vis_cell,
            logic="—",
            visibility_extract=should_extract_visibility(vis_raw),
            visibility_control_text=clean_visibility_condition(vis_raw),
        )

    plain = cell_text(f"{comment_raw} {fill_raw}")
    sections, preamble = split_sections_from_blobs(comment_raw, fill_raw)
    pre_parts = classify_preamble(preamble)

    vis_raw = extract_visibility_raw(comment_raw)
    vis_cell = format_visibility_cell(vis_raw) if vis_raw else "Всегда"

    fill_mode = derive_fill_mode(fill_raw, sections, plain)
    fmt = derive_format(ui_type, sections, pre_parts)
    logic = derive_logic(fill_raw, sections, pre_parts, fmt)
    norm_type = normalize_ui_type(ui_type, fill_mode, logic, plain, fill_raw)
    required = derive_required(required_raw)
    rules = find_rule_fragments(name, plain, sections)

    return FieldAnalysis(
        ui_type=norm_type,
        fmt=fmt,
        fill_mode=fill_mode,
        required=required,
        visibility=vis_cell,
        logic=logic,
        visibility_extract=should_extract_visibility(vis_raw),
        visibility_control_text=clean_visibility_condition(vis_raw),
        rule_fragments=rules,
    )
