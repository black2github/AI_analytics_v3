#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SFR generator для open-add-account.

Создаёт пару SFR-файлов (ЭФ + FE), не перезаписывая исходники.
FE наполняется на базе существующего FE-документа control-split
(правила + группы + хвост документа) и дополняется visibility из ЭФ.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from restructure_o2plus_clean import (
    Control,
    RawField,
    ReferenceFeMeta,
    build_fe_table,
    build_field_analyses,
    extract_visibility_controls,
    field_key,
    field_row_md,
    format_group_descriptions,
    get_section,
    is_type_cell,
    load_reference_fe_meta,
    normalize_num,
    parse_frontmatter,
    resolve_fe_group_keys,
)

DEFAULT_SRC = (
    r"C:\doc-as-code\AI-docs-O2new\sources\confluence\open-add-account"
    r"\06-screens\01-client\03-6365126-эф-клиента-открытие-доп-счета-и-заключение-дбс-в-режиме-редактирования.md"
)
DEFAULT_FE_REF = (
    r"C:\doc-as-code\AI-docs-O2new\sources\confluence\open-add-account"
    r"\07-controls\FE-Контроли-6365126-эф-клиента-открытие-доп-счета-и-заключение-дбс-в-режиме-редактирования.md"
)


def clean_md_cell(raw: str) -> str:
    if not raw:
        return ""
    return raw.strip()


def parse_md_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        if re.match(r"^\|\s*[-:]+", line):
            continue
        cells = [clean_md_cell(c) for c in line.split("|")[1:-1]]
        if cells:
            rows.append(cells)
    return rows


def find_type_col_md(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        low = re.sub(r"\*+", "", cell).strip().lower()
        if low == "тип поля" or "тип поля" in low:
            return i
    return None


def is_field_table_header(header: list[str]) -> bool:
    blob = " ".join(header).lower()
    return "название поля" in blob and "тип поля" in blob


def find_field_table_md(section: str) -> list[list[str]] | None:
    lines = section.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].strip().startswith("|"):
            i += 1
            continue
        block: list[str] = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            block.append(lines[i])
            i += 1
        rows = parse_md_table_rows("\n".join(block))
        if len(rows) < 2:
            continue
        for ri, row in enumerate(rows[:4]):
            if is_field_table_header(row):
                return rows[ri:]
        if find_type_col_md(rows[0]) is not None:
            return rows
    return None


def extract_fields_from_md(rows: list[list[str]], tab: str) -> list[RawField]:
    if not rows:
        return []
    type_col = find_type_col_md(rows[0])
    if type_col is None:
        return []

    fields: list[RawField] = []
    for row in rows[1:]:
        if len(row) <= type_col:
            continue
        texts = row + [""] * (8 - len(row))
        ftype = re.sub(r"\*+", "", texts[type_col]).strip()
        if not is_type_cell(ftype):
            name = ""
            num_parts: list[str] = []
            for j in range(type_col):
                t = re.sub(r"\*+", "", texts[j]).strip()
                if not t:
                    continue
                if re.match(r"^[\d.*]+$", t.replace(" ", "")):
                    num_parts.append(t)
                elif not name:
                    name = t
            block_text = " ".join(texts[type_col : type_col + 2]).strip()
            name = name or block_text
            if name and ("блок" in name.lower() or len(name) > 3):
                comm = texts[type_col + 3] if type_col + 3 < len(texts) else texts[-1]
                fields.append(
                    RawField(
                        num=normalize_num(num_parts),
                        name=name.strip(),
                        ui_type="Заголовок",
                        fill_raw="",
                        required_raw="",
                        comment_raw=comm,
                        tab=tab,
                        is_block=True,
                    )
                )
            continue

        name = re.sub(r"\*+", "", texts[type_col - 1]).strip() if type_col > 0 else ""
        num = normalize_num(
            [re.sub(r"\*+", "", t).strip() for t in texts[: type_col - 1] if t.strip()]
        )
        fill = texts[type_col + 1] if type_col + 1 < len(texts) else ""
        req = texts[type_col + 2] if type_col + 2 < len(texts) else ""
        comm = texts[type_col + 3] if type_col + 3 < len(texts) else ""

        if not name:
            continue

        ui = ftype
        if ftype.lower().startswith("тип сообщения"):
            ui = "Информер"
        elif "информер" in ftype.lower():
            ui = "Информер"
        elif "блоккер" in ftype.lower():
            ui = "Блоккер"
        elif ftype.lower() == "заголовок":
            ui = "Заголовок"
        elif ftype.lower() == "иконка":
            ui = "Иконка"
        elif "checkbox" in ftype.lower() or "чекбокс" in ftype.lower():
            ui = "Чекбокс"
        elif "переключатель" in ftype.lower():
            ui = "Переключатель"
        elif "блок загрузки" in ftype.lower():
            ui = "Файл"

        fields.append(
            RawField(
                num=num,
                name=name,
                ui_type=ui,
                fill_raw=fill,
                required_raw=req,
                comment_raw=comm,
                tab=tab,
            )
        )
    return fields


def extract_ef_description_md(body: str) -> str:
    m = re.search(r"# Общие требования к ЭФ\s*\n(.*?)(?=\n# Вкладка|\Z)", body, re.S)
    if not m:
        return "_[НЕ РАСПОЗНАНО: раздел «Общие требования к ЭФ» не найден]_"
    block = m.group(1).strip()
    table_lines = [ln for ln in block.splitlines() if ln.strip().startswith("|")]
    if table_lines:
        return "\n".join(table_lines)
    return block[:8000]


def extract_buttons_md(section: str) -> list[str]:
    rows = parse_md_table_rows(section)
    if len(rows) < 2:
        return []
    lines: list[str] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        num = row[0] if row[0] else ""
        name = row[1] if len(row) > 1 else ""
        func = row[2] if len(row) > 2 else ""
        vis = row[3] if len(row) > 3 else ""
        if name and not name.startswith("**Кнопк"):
            lines.append(
                f"- **{name}** ({num}) — {func[:500]}{'…' if len(func) > 500 else ''}; "
                f"видимость: {vis or 'Всегда'}"
            )
    return lines


def sfr_ef_name(orig_name: str) -> str:
    """Именование по references/naming.md: SFR- первой частью (без [префикса])."""
    stem = orig_name.removesuffix(".md")
    if stem.startswith("SFR-"):
        return f"{stem}.md"
    return f"SFR-{stem}.md"


def sfr_fe_name(fe_name: str) -> str:
    """FE-Контроли-… → SFR-FE-Контроли-… (рядом с исходным FE)."""
    stem = fe_name.removesuffix(".md")
    if stem.startswith("SFR-FE-"):
        return f"{stem}.md"
    if stem.startswith("FE-"):
        return f"SFR-{stem}.md"
    if "FE-Контроли" in stem:
        return stem.replace("FE-Контроли", "SFR-FE-Контроли", 1) + ".md"
    return f"SFR-FE-Контроли-{stem}.md"


def detect_fe_table_layout(header_parts: list[str]) -> dict:
    """Индексы колонок в FE-таблице (старый и v3.1 форматы)."""
    lows = [re.sub(r"\*+", "", p).strip().lower() for p in header_parts]
    idx: dict = {}
    for i, low in enumerate(lows):
        if low == "id":
            idx["id"] = i
        elif low.startswith("ориг"):
            idx["orig"] = i
        elif "название" in low:
            idx["title"] = i
        elif low == "тип":
            idx["typ"] = i
        elif low.startswith("поле") or low == "поля":
            idx["fields"] = i
        elif "условие" in low:
            idx["condition"] = i
        elif "сообщение" in low:
            idx["message"] = i
        elif low == "r":
            idx["r"] = i
    idx["group_idxs"] = [i for i, low in enumerate(lows) if low.startswith("гр")]
    return idx


def load_rule_controls_from_ref(
    ref_path: Path, ref_meta: ReferenceFeMeta, start_id: int
) -> list[Control]:
    """Читает rule-строки из существующего FE (старый или v3.1 формат)."""
    text = ref_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header_idx = None
    header_parts: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("| ID") or line.startswith("|ID"):
            header_parts = [p.strip() for p in line.strip().strip("|").split("|")]
            header_idx = i
            break
    if header_idx is None:
        return []

    layout = detect_fe_table_layout(header_parts)
    # Fallback для старого формата:
    # ID | Ориг. | Поле | Название | Условие | Сообщение | Гр.1 | Гр.2 | Гр.3
    has_typ = "typ" in layout
    reactive_keys = (
        "обязательн",
        "длина",
        "формат",
        "символ",
        "согласи",
        "непуст",
        "ключеван",
        "ненулев",
        "даты",
    )

    controls: list[Control] = []
    n = start_id
    for line in lines[header_idx + 1 :]:
        if not line.startswith("| SF-"):
            if line.startswith("|") and "---" in line:
                continue
            if line.startswith("|"):
                continue
            # конец таблицы
            if controls:
                break
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 6:
            continue

        if has_typ:
            orig = parts[layout.get("orig", 1)]
            title = parts[layout.get("title", 2)]
            fields = parts[layout.get("fields", 4)]
            condition = parts[layout.get("condition", 5)]
            message = parts[layout.get("message", 6)] if len(parts) > 6 else "—"
            r_col = parts[layout["r"]] if "r" in layout and layout["r"] < len(parts) else ""
            typ = parts[layout["typ"]] if layout.get("typ", 99) < len(parts) else "rule"
            if typ.strip().lower() == "visibility":
                continue  # visibility берём из ЭФ заново
        else:
            # старый FE: Поле | Название
            orig = parts[1]
            fields = parts[2]
            title = parts[3]
            condition = parts[4]
            message = parts[5] if len(parts) > 5 else "—"
            r_col = ""
            typ = "rule"

        groups = dict(ref_meta.groups_by_orig.get(orig, {}))
        # если в meta нет — взять из строки
        if not any(groups.values()) and ref_meta.group_keys:
            # старый: группы с индекса 6; новый: после R
            start_g = 7 if has_typ else 6
            for gi, g in enumerate(ref_meta.group_keys):
                idx = start_g + gi
                val = parts[idx] if idx < len(parts) else ""
                groups[g] = "V" if val.strip().upper() == "V" else ""

        blob = f"{title} {condition} {fields}".lower()
        reactive = bool(r_col.strip().upper() == "R") or any(k in blob for k in reactive_keys)

        controls.append(
            Control(
                id=f"SF-{n:02d}",
                orig=orig,
                title=title,
                typ="rule",
                fields=fields,
                condition=condition,
                message=message or "—",
                r="R" if reactive else "",
                groups=groups,
            )
        )
        n += 1
    return controls


def extract_fe_tail(fe_text: str) -> str:
    """Секции после таблицы контролей (обоснование, примечания)."""
    lines = fe_text.splitlines()
    in_table = False
    after_table_start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith("| ID") or line.startswith("|ID"):
            in_table = True
            continue
        if in_table and line.startswith("| SF-"):
            continue
        if in_table and line.startswith("|") and "---" in line:
            continue
        if in_table and (not line.startswith("|") or line.strip() == "|"):
            after_table_start = i
            break
    if after_table_start is None:
        return ""
    # пропустить пустые строки сразу после таблицы
    j = after_table_start
    while j < len(lines) and not lines[j].strip():
        j += 1
    tail = "\n".join(lines[j:]).strip()
    return tail


def bump_version(ver: str | None) -> str:
    if not ver:
        return "1.1.0"
    parts = ver.strip().strip("'\" ").split(".")
    try:
        nums = [int(p) for p in parts]
        while len(nums) < 3:
            nums.append(0)
        nums[1] += 1
        nums[2] = 0
        return ".".join(str(x) for x in nums)
    except ValueError:
        return "1.1.0"


def main():
    ap = argparse.ArgumentParser(description="SFR open-add-account (SFR-пара, FE на базе существующего)")
    ap.add_argument("--src", type=Path, default=Path(DEFAULT_SRC))
    ap.add_argument("--fe-ref", type=Path, default=Path(DEFAULT_FE_REF))
    ap.add_argument(
        "--fe-out",
        type=Path,
        default=None,
        help="Путь SFR-FE (по умолчанию SFR- рядом с fe-ref)",
    )
    args = ap.parse_args()

    src_path = args.src
    fe_ref_path = args.fe_ref
    if not fe_ref_path.exists():
        raise SystemExit(f"FE base not found: {fe_ref_path}")

    fe_out_path = args.fe_out or (fe_ref_path.parent / sfr_fe_name(fe_ref_path.name))

    text = src_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    fe_text = fe_ref_path.read_text(encoding="utf-8")
    fe_fm, _fe_body = parse_frontmatter(fe_text)
    fe_tail = extract_fe_tail(fe_text)

    orig_name = src_path.name
    out_dir = src_path.parent

    tab_sections = {
        "Открываемый счёт": get_section(
            body,
            '## Описание ЭФ "Открываемый счёт" основная часть',
            ["## Описание кнопок"],
        ),
        "Реквизиты ГК": get_section(
            body,
            '## Описание полей ЭФ (Вкладка "Реквизиты ГК")',
            ["## Описание кнопок"],
        ),
        "Подтверждение": get_section(
            body,
            '## Описание полей ЭФ (Вкладка "Подтверждение")',
            ["## Описание кнопок"],
        ),
    }

    all_fields: list[RawField] = []
    for tab, sec in tab_sections.items():
        if not sec:
            continue
        rows = find_field_table_md(sec)
        if rows:
            all_fields.extend(extract_fields_from_md(rows, tab))

    analyses = build_field_analyses(all_fields)
    ref_fe = load_reference_fe_meta(src_path, fe_ref_path)
    vis_controls, sf_map = extract_visibility_controls(all_fields, analyses, start=1)
    rule_controls = load_rule_controls_from_ref(
        fe_ref_path, ref_fe, start_id=len(vis_controls) + 1
    )
    all_controls = vis_controls + rule_controls
    group_keys = resolve_fe_group_keys(ref_fe, all_controls)
    fe_rows = build_fe_table(all_controls, group_keys)
    group_desc_block = format_group_descriptions(group_keys, ref_fe.descriptions)

    btn_lines: list[str] = []
    btn_markers = [
        ("Открываемый счёт", '## Описание кнопок ЭФ (Вкладка "Открываемый счёт")'),
        ("Реквизиты ГК", '## Описание кнопок ЭФ (Вкладка "Реквизиты ГК")'),
        ("Подтверждение", '## Описание кнопок ЭФ (Вкладка "Подтверждение")'),
    ]
    for tab, marker in btn_markers:
        sec = get_section(body, marker, ["\n# Вкладка", "\n## Описание полей"])
        if sec:
            for line in extract_buttons_md(sec):
                btn_lines.append(f"**{tab}:** {line}")

    desc_block = extract_ef_description_md(body)
    sfr_ef_file = out_dir / sfr_ef_name(orig_name)

    # Каталог open-add-account → service_code из ЭФ; FE мог быть с чужим service (o2plus).
    service = (
        fm.get("service_id")
        or fm.get("service_code")
        or fe_fm.get("service_code")
        or "open-add-account"
    )
    page_id = fm.get("page_id") or fm.get("confluence_page_id") or "6365126"
    orig_title = fm.get("title", "ЭФ Клиента").strip("'\"")
    ef_title = f"SFR {orig_title}"

    # title/doc_id FE: сохранить основу, добавить SFR
    base_fe_title = (fe_fm.get("title") or "FE Контроли ЭФ").strip("'\"")
    if not base_fe_title.startswith("SFR"):
        fe_title = f"SFR {base_fe_title}"
    else:
        fe_title = base_fe_title

    be_title = "BE Контроли заявки"
    be_rel = "./6365377-BE-Контроли-заявки.md"

    entity = "../../04-data-model/related-entities/6364746-заявка-на-открытие-доп-счета-и-заключение-дбс.md"
    fe_rel_from_ef = f"../../07-controls/{fe_out_path.name}"
    ef_rel_from_fe = f"../06-screens/01-client/{sfr_ef_file.name}"

    field_lines = [
        "| Поле | Тип | Формат | Способ заполнения | Обяз. | Видимость | Логика установки значения |",
        "|------|-----|--------|-------------------|:-----:|-----------|---------------------------|",
    ]
    cur_tab = ""
    for f in all_fields:
        if f.tab != cur_tab:
            cur_tab = f.tab
            field_lines.append(f"| **Вкладка «{f.tab}»** | | | | | | |")
        field_lines.append(field_row_md(f, analyses[field_key(f)], sf_map))

    # Confluence version (напр. 352) — не semver; для SFR фиксируем 1.1.0 / bump FE.
    ef_version = "1.1.0"
    fe_ver_raw = str(fe_fm.get("version", "1.0.0")).strip("'\"")
    fe_version = bump_version(fe_ver_raw if re.match(r"^\d+\.\d+", fe_ver_raw) else "1.0.0")

    ef_doc = f"""---
doc_id: '{{{{{service}: {ef_title}}}}}'
title: '{ef_title}'
description: 'SFR: переформатированная ЭФ open-add-account (единая таблица полей).'
doc_type: requirement
requirement_type: screenItemForm
service_code: {service}
source: CONFLUENCE
confluence_page_id: '{page_id}'
status: draft
version: {ef_version}
related: '{{{{{service}: {fe_title}}}}}'
tags: [screen-form, sfr]
---

**История изменений:** перенесена из исходника [{orig_title}]({orig_name}) (см. там полную историю). Настоящая версия — результат переформатирования (SFR) screen-form-restructure v3.1.

| Дата | Описание | Автор | Задача |
| --- | --- | --- | --- |
| 2026-07-16 | SFR open-add-account: единая таблица полей; visibility + rule в [{fe_title}]({fe_rel_from_ef}) | agent | — |

# {orig_title}

Данная ЭФ предназначена для создания/редактирования [Заявка на открытие доп счета и заключение ДБС]({entity}).

## Описание ЭФ

> Таблица перенесена из исходника «Общие требования к ЭФ» **без изменения структуры**.

{desc_block}

ЭФ состоит из трёх вкладок:

| № | Вкладка | Условие видимости |
| --- | --- | --- |
| 1 | Открываемый счёт | Всегда |
| 2 | Реквизиты ГК | см. SF-01 (в FE-контролях) |
| 3 | Подтверждение | Всегда |

## Обозначения колонок

- **Тип** — UI-тип поля (словарь UI-типов).
- **Формат** — ограничение и отображение; `(на поле)` при расхождении с атрибутом модели.
- **Способ заполнения** — {{Вручную | Выбор из списка | Автоматически}}.
- **Обяз.** — Да/Нет; условная — `см. SF-NN`.
- **Видимость** — показ/скрытие лейбла и значения; нетривиальная — `см. SF-NN`.
- **Логика установки значения** — умолчание, источник списка, формулы (`=`), каскады у поля-получателя.

## Поля формы

{chr(10).join(field_lines)}

## Действия

{chr(10).join(btn_lines) if btn_lines else "_Кнопки — см. разделы «Описание кнопок» в исходнике._"}

## Проверки формы

Relational-правила и вынесенная видимость — в [{fe_title}]({fe_rel_from_ef}). Реакции (информеры, модалки) — в едином документе информирования сервиса.
"""

    # Назначение: сохранить смысл из FE, заменить ссылку на SFR-ЭФ
    fe_purpose_src = ""
    m_purpose = re.search(
        r"## Назначение\s*\n+(.*?)(?=\n## |\Z)", fe_text, re.S
    )
    if m_purpose:
        fe_purpose_src = m_purpose.group(1).strip()
        # обновить ссылку на ЭФ → SFR
        fe_purpose_src = re.sub(
            r"\]\([^)]*03-6365126-эф-клиента[^)]*\)",
            f"]({ef_rel_from_fe})",
            fe_purpose_src,
        )
        fe_purpose_src = re.sub(
            r"ЭФ Клиента \"Открытие доп счета и заключение ДБС\" в режиме редактирования",
            ef_title,
            fe_purpose_src,
        )

    zone3 = (
        f"> **Зона 3.** Проверки **полей** [{ef_title}]({ef_rel_from_fe}). "
        f"Гарантия — в BE ([{be_title}]({be_rel}))."
    )
    # если в исходном FE была развёрнутая врезка — сохранить и подменить ссылку
    m_zone = re.search(r"^> \*\*Зона 3\.\*\*.+$", fe_text, re.M)
    if m_zone:
        zone3 = m_zone.group(0)
        zone3 = re.sub(
            r"\]\([^)]*03-6365126-эф-клиента[^)]*\)",
            f"]({ef_rel_from_fe})",
            zone3,
        )

    fe_related = "{{" + service + ": " + ef_title + "}}, {{" + service + ": " + be_title + "}}"
    fe_desc = (
        fe_fm.get("description")
        or "Контроли полей и видимости ЭФ: visibility из SFR + rule из существующего FE."
    )
    if isinstance(fe_desc, str):
        fe_desc = fe_desc.strip("'\"")

    # обновить SF-ID в хвосте (SF-08… → с учётом сдвига visibility)
    # исходные SF-01..N стали SF-(vis+1).. ; для примечаний — мягкая пометка
    id_shift = len(vis_controls)
    adjusted_tail = fe_tail
    if adjusted_tail and id_shift:
        def _shift_sf(m: re.Match) -> str:
            num = int(m.group(1))
            return f"SF-{num + id_shift:02d}"

        # сдвигать только упоминания старых ID в хвосте (не трогать заголовки секций)
        adjusted_tail = re.sub(r"\bSF-(\d+)\b", _shift_sf, adjusted_tail)
        # ссылки на исходную ЭФ → SFR
        adjusted_tail = re.sub(
            r"\]\([^)]*03-6365126-эф-клиента[^)]*\)",
            f"]({ef_rel_from_fe})",
            adjusted_tail,
        )

    fe_doc = f"""---
doc_id: '{{{{{service}: {fe_title}}}}}'
title: '{fe_title}'
description: '{fe_desc} Дополнено visibility из SFR.'
doc_type: requirement
requirement_type: control
control_kind: screen-form
service_code: {service}
source: CONFLUENCE
confluence_page_id: '{fe_fm.get("confluence_page_id") or "6365377"}'
status: draft
version: {fe_version}
related: '{fe_related}'
tags: [control, screen-form, frontend, ux, sfr]
---

{zone3}

## Назначение

{fe_purpose_src or f"Контроли полей и видимости [{ef_title}]({ef_rel_from_fe}), выполняемые на клиенте при работе с формой."}

## Группы триггеров

Группа — событие формы, при котором запускается подмножество проверок. «V» на пересечении проверки и группы означает выполнение при наступлении события группы.

{group_desc_block}

## Контроли формы

`R` — реактивный; `V` — событийный. `visibility`: сообщение = «—».

Основа: [{fe_ref_path.name}](./{fe_ref_path.name}) (rule). Дополнено visibility из анализа ЭФ.

{chr(10).join(fe_rows)}

> Дополнено screen-form-restructure: {len(vis_controls)} visibility (из ЭФ) + {len(rule_controls)} rule (из [{fe_ref_path.name}](./{fe_ref_path.name})). Групп: {len(group_keys)}. Требуется ревью аналитиком.

{adjusted_tail}
"""

    sfr_ef_file.write_text(ef_doc, encoding="utf-8")
    fe_out_path.write_text(fe_doc, encoding="utf-8")

    print(f"Source EF: {src_path}")
    print(f"Base FE:   {fe_ref_path}")
    print(f"Fields: {len(all_fields)}")
    print(f"Controls: {len(all_controls)} (vis={len(vis_controls)}, rule={len(rule_controls)})")
    print(f"Groups: {group_keys}")
    print(f"SFR EF: {sfr_ef_file}")
    print(f"SFR FE: {fe_out_path}")
    print(f"(исходный FE не изменён)")


if __name__ == "__main__":
    main()
