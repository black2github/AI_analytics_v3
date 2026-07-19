#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean SFR generator for O2+ ЭФ — screen-form-restructure v3.1.

Парсит только исходную ЭФ; FE-контроли извлекаются из описания формы.
"""
from __future__ import annotations

import glob
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup

from semantic_field import FieldAnalysis, analyze_field, resolve_visibility_extract

SRC_GLOB = r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*редактирования.md"

UI_TYPES = {
    "текст",
    "число",
    "дата",
    "список",
    "переключатель",
    "чекбокс",
    "заголовок",
    "гиперссылка",
    "кнопка",
    "иконка",
    "изображение",
    "файл",
    "таблица",
    "информер",
    "блоккер информер",
    "блоккер",
}


@dataclass
class RawField:
    num: str
    name: str
    ui_type: str
    fill_raw: str
    required_raw: str
    comment_raw: str
    tab: str
    is_block: bool = False


@dataclass
class ReferenceFeMeta:
    path: Path | None
    group_keys: list[int]
    descriptions: dict[int, str]
    groups_by_orig: dict[str, dict[int, str]]


@dataclass
class Control:
    id: str
    orig: str
    title: str
    typ: str  # rule | visibility
    fields: str
    condition: str
    message: str
    r: str
    groups: dict[int, str] = field(default_factory=dict)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("'\"")
    return fm, m.group(2)


def build_grid(table) -> list[list[str]]:
    rows = table.find_all("tr")
    grid: list[list[str]] = []
    pending: dict[int, tuple[str, int]] = {}

    for tr in rows:
        cells = tr.find_all(["td", "th"])
        row: list[str] = []
        ci = 0
        col = 0
        while col < 24:
            if col in pending and pending[col][1] > 0:
                html, left = pending[col]
                row.append(html)
                if left > 1:
                    pending[col] = (html, left - 1)
                else:
                    del pending[col]
                col += 1
                continue
            if ci >= len(cells):
                break
            cell = cells[ci]
            ci += 1
            rs = int(cell.get("rowspan") or 1)
            cs = int(cell.get("colspan") or 1)
            html = str(cell)
            for c in range(col, col + cs):
                row.append(html)
                if rs > 1:
                    pending[c] = (html, rs - 1)
            col += cs
        grid.append(row)

    width = max((len(r) for r in grid), default=0)
    for r in grid:
        r.extend([""] * (width - len(r)))
    return grid


def cell_text(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def html_to_md(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        label = a.get_text(strip=True) or href
        a.replace_with(f"[{label}]({href})" if href else label)
    for br in soup.find_all("br"):
        br.replace_with("<br>")
    for tag in soup.find_all(["p", "ul", "ol", "li", "strong", "em"]):
        if tag.name == "li":
            tag.insert_before("<br>- ")
        tag.unwrap()
    out = str(soup)
    # keep img tags
    out = re.sub(r"<img\s+([^>]*?)>", r'<img \1>', out, flags=re.I)
    out = re.sub(r"<(?!img|br)[^>]+>", "", out)
    out = unescape(out)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"(<br>)+", "<br>", out)
    return out.strip()


def is_type_cell(text: str) -> bool:
    if not text:
        return False
    low = text.lower().strip()
    if low.startswith("тип сообщения"):
        return True
    if low in UI_TYPES:
        return True
    if low in ("текст", "список", "переключатель", "чекбокс", "заголовок", "иконка", "изображение"):
        return True
    return False


def find_type_col(header: list[str]) -> int | None:
    for i, html in enumerate(header):
        t = cell_text(html).lower()
        if t == "тип поля" or "тип поля" in t:
            return i
    return None


def find_header_row(grid: list[list[str]]) -> tuple[int, int] | None:
    for ri, row in enumerate(grid[:6]):
        tc = find_type_col(row)
        if tc is not None:
            return ri, tc
    return None


def find_field_table(section_html: str):
    soup = BeautifulSoup(section_html, "html.parser")
    for table in soup.find_all("table"):
        grid = build_grid(table)
        if len(grid) < 2:
            continue
        if find_header_row(grid):
            return table
    return None


def normalize_num(parts: list[str]) -> str:
    uniq = []
    for p in parts:
        p = p.strip()
        if p and (not uniq or p != uniq[-1]):
            uniq.append(p)
    return " ".join(uniq)


def extract_fields_from_table(table, tab: str) -> list[RawField]:
    grid = build_grid(table)
    if len(grid) < 2:
        return []
    hdr = find_header_row(grid)
    if hdr is None:
        return []
    header_idx, type_col = hdr

    fields: list[RawField] = []
    for row in grid[header_idx + 1 :]:
        texts = [cell_text(h) for h in row]
        htmls = row

        # block header: no type, name spans after num
        if type_col < len(texts) and not is_type_cell(texts[type_col]):
            # section row like "Блок ..."
            name_candidate = ""
            num_parts = []
            for j in range(type_col):
                if texts[j]:
                    if re.match(r"^[\d.]+$", texts[j]) or texts[j].replace(".", "").isdigit():
                        num_parts.append(texts[j])
                    elif not name_candidate:
                        name_candidate = texts[j]
            block_text = " ".join(texts[type_col : type_col + 3]).strip()
            name = name_candidate or block_text
            if name and ("блок" in name.lower() or len(name) > 3):
                cond = texts[type_col + 3] if type_col + 3 < len(texts) else ""
                if not cond and type_col + 2 < len(texts):
                    cond = texts[type_col + 2]
                fields.append(
                    RawField(
                        num=normalize_num(num_parts),
                        name=name.strip(),
                        ui_type="Заголовок",
                        fill_raw="",
                        required_raw="",
                        comment_raw=html_to_md(htmls[type_col + 2] if type_col + 2 < len(htmls) else htmls[-1]),
                        tab=tab,
                        is_block=True,
                    )
                )
            continue

        ftype = texts[type_col]
        name = texts[type_col - 1] if type_col > 0 else ""
        num = normalize_num([t for t in texts[: type_col - 1] if t])
        fill = html_to_md(htmls[type_col + 1]) if type_col + 1 < len(htmls) else ""
        req = html_to_md(htmls[type_col + 2]) if type_col + 2 < len(htmls) else ""
        comm = html_to_md(htmls[type_col + 3]) if type_col + 3 < len(htmls) else ""

        if not name:
            continue

        # normalize UI type
        ui = ftype
        if ftype.lower().startswith("тип сообщения"):
            ui = ftype.split(":")[-1].strip() if ":" in ftype else "Информер"
            ui = "Информер" if "информер" in ui.lower() else ui
        elif ftype.lower() == "заголовок":
            ui = "Заголовок"
        elif ftype.lower() == "иконка":
            ui = "Иконка"
        elif ftype.lower() == "изображение":
            ui = "Изображение"

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


def field_key(f: RawField) -> str:
    return f"{f.tab}|{f.num}|{f.name}"


def build_field_analyses(fields: list[RawField]) -> dict[str, FieldAnalysis]:
    """Проход 2a→2b: смысловой разбор каждого поля по осям (ключ tab|num|name)."""
    out: dict[str, FieldAnalysis] = {}
    for f in fields:
        out[field_key(f)] = analyze_field(
            name=f.name,
            ui_type=f.ui_type,
            fill_raw=f.fill_raw,
            required_raw=f.required_raw,
            comment_raw=f.comment_raw,
            is_block=f.is_block,
        )
    resolve_visibility_extract(fields, out, field_key)
    return out


def parse_group_keys_from_table_header(text: str) -> list[int]:
    """Номера групп из заголовка markdown-таблицы (колонки «Гр.N»)."""
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        keys = [int(m.group(1)) for m in re.finditer(r"Гр\.(\d+)", line)]
        if keys:
            return sorted(keys)
    return []


def parse_group_descriptions(text: str) -> dict[int, str]:
    """Тексты групп из раздела «## Группы триггеров»."""
    m = re.search(r"## Группы триггеров\s*\n(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        return {}
    result: dict[int, str] = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^- \*\*Группа №(\d+)\*\* — (.+)$", line.strip())
        if mm:
            result[int(mm.group(1))] = mm.group(2).strip()
    return result


def find_reference_fe_controls(ef_path: Path) -> Path | None:
    """Парный FE-документ сервиса (control-split), не SFR-FE."""
    for parent in ef_path.parents:
        candidates = [
            p
            for p in parent.glob("*FE-Контроли*.md")
            if "SFR-FE" not in p.name and "SFR-FE" not in p.stem
        ]
        if candidates:
            return sorted(candidates, key=lambda p: p.name)[0]
    return None


def load_reference_fe_meta(ef_path: Path, fe_ref: Path | None = None) -> ReferenceFeMeta:
    path = fe_ref or find_reference_fe_controls(ef_path)
    if not path or not path.exists():
        return ReferenceFeMeta(None, [], {}, {})
    text = path.read_text(encoding="utf-8")
    group_keys = parse_group_keys_from_table_header(text)
    descriptions = parse_group_descriptions(text)
    groups_by_orig: dict[str, dict[int, str]] = {}
    for line in text.splitlines():
        if not line.startswith("| SF-"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 7:
            continue
        orig = parts[1]
        row_groups: dict[int, str] = {}
        for i, g in enumerate(group_keys):
            idx = 6 + i
            val = parts[idx] if idx < len(parts) else ""
            row_groups[g] = "V" if val.strip().upper() == "V" else ""
        groups_by_orig[orig] = row_groups
    return ReferenceFeMeta(path, group_keys, descriptions, groups_by_orig)


def resolve_fe_group_keys(
    ref: ReferenceFeMeta,
    controls: list[Control],
    *,
    exclude_be_only: bool = True,
) -> list[int]:
    """Объединение групп из референса, строк контролей и описаний; без BE-only №4 на FE."""
    keys: set[int] = set(ref.group_keys)
    keys.update(ref.descriptions)
    for c in controls:
        keys.update(c.groups)
    if exclude_be_only:
        keys.discard(4)
    return sorted(keys)


def build_fe_table(controls: list[Control], group_keys: list[int]) -> list[str]:
    """Заголовок, разделитель и строки FE-таблицы с динамическим числом групп."""
    header = (
        "| ID | Ориг. | Название проверки | Тип | Поля | Условие | Сообщение об ошибке | R"
    )
    sep = "|----|-------|-------------------|-----|------|---------|---------------------|:-:|"
    if group_keys:
        header += " | " + " | ".join(f"Гр.{g}" for g in group_keys) + " |"
        sep += "|".join(":--:" for _ in group_keys) + "|"
    else:
        header += " |"
    lines = [header, sep]
    for c in controls:
        base = (
            f"| {c.id} | {c.orig} | {c.title} | {c.typ} | {c.fields} | "
            f"{c.condition} | {c.message} | {c.r}"
        )
        if group_keys:
            gvals = " | ".join(c.groups.get(g, "") for g in group_keys)
            lines.append(f"{base} | {gvals} |")
        else:
            lines.append(f"{base} |")
    return lines


def format_group_descriptions(group_keys: list[int], descriptions: dict[int, str]) -> str:
    lines: list[str] = []
    for g in group_keys:
        desc = descriptions.get(g, f"_[описание группы №{g} не найдено]_")
        lines.append(f"- **Группа №{g}** — {desc}")
    return "\n".join(lines)


def extract_rule_controls(
    fields: list[RawField],
    analyses: dict[str, FieldAnalysis],
    start: int,
    ref: ReferenceFeMeta | None = None,
) -> list[Control]:
    controls: list[Control] = []
    n = start
    for f in fields:
        a = analyses.get(field_key(f))
        if not a or not a.rule_fragments:
            continue
        for title, cond, msg, reactive in a.rule_fragments:
            groups: dict[int, str] = {}
            if ref and f.num and f.num in ref.groups_by_orig:
                groups = dict(ref.groups_by_orig[f.num])
            controls.append(
                Control(
                    id=f"SF-{n:02d}",
                    orig=f.num or "—",
                    title=title,
                    typ="rule",
                    fields=f.name,
                    condition=cond,
                    message=msg or "—",
                    r="R" if reactive else "",
                    groups=groups,
                )
            )
            n += 1
    return controls


def extract_visibility_controls(
    fields: list[RawField],
    analyses: dict[str, FieldAnalysis],
    start: int,
) -> tuple[list[Control], dict[str, str]]:
    """Returns controls and field_name -> SF-id for см. links."""
    controls: list[Control] = []
    sf_map: dict[str, str] = {}
    n = start

    controls.append(
        Control(
            id=f"SF-{n:02d}",
            orig="вкладка",
            title="Видимость вкладки «Реквизиты ГК»",
            typ="visibility",
            fields="Вкладка «Реквизиты ГК» ← Тип счёта",
            condition="**Если** <Код типа счета> == 2, **то** вкладка отображается, **иначе** не отображается",
            message="—",
            r="R",
        )
    )
    sf_map["Вкладка «Реквизиты ГК»"] = f"SF-{n:02d}"
    n += 1

    cond_index: dict[str, str] = {}

    for f in fields:
        a = analyses.get(field_key(f))
        if not a or not a.visibility_extract:
            continue
        vis_ctrl = a.visibility_control_text
        key = vis_ctrl[:200]
        if key in cond_index:
            sf_map[f.name] = cond_index[key]
            continue
        cid = f"SF-{n:02d}"
        cond_index[key] = cid
        sf_map[f.name] = cid
        controls.append(
            Control(
                id=cid,
                orig=f.num or "—",
                title=f"Видимость «{f.name}»",
                typ="visibility",
                fields=f"{f.name} ← (см. Условие)",
                condition=vis_ctrl[:1200],
                message="—",
                r="R",
            )
        )
        n += 1

    return controls, sf_map


def field_row_md(f: RawField, a: FieldAnalysis, sf_map: dict[str, str]) -> str:
    vis = a.visibility
    if f.name in sf_map:
        vis = f"см. {sf_map[f.name]}"
    if f.is_block:
        return (
            f"| **{f.name}** | {a.ui_type} | {a.fmt} | {a.fill_mode} | {a.required} | {vis} | {a.logic} |"
        )
    return "| " + " | ".join(
        [
            f.name,
            a.ui_type,
            a.fmt,
            a.fill_mode,
            a.required,
            vis,
            a.logic,
        ]
    ) + " |"


def extract_buttons(section: str) -> list[str]:
    m = re.search(r"## Описание кнопок[^\n]*\n(.*?)(?=\n## |\Z)", section, re.S)
    if not m:
        return []
    soup = BeautifulSoup(m.group(1), "html.parser")
    table = soup.find("table")
    if not table:
        return []
    lines = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        num = cell_text(str(cells[0]))
        name = cell_text(str(cells[1]))
        func = html_to_md(str(cells[2])) if len(cells) > 2 else ""
        vis = html_to_md(str(cells[3])) if len(cells) > 3 else ""
        if name:
            lines.append(f"- **{name}** ({num}) — {func[:400]}{'…' if len(func)>400 else ''}; видимость: {vis or 'Всегда'}")
    return lines


def get_section(body: str, marker: str, end_markers: list[str]) -> str:
    idx = body.find(marker)
    if idx < 0:
        return ""
    end = len(body)
    for em in end_markers:
        j = body.find(em, idx + len(marker))
        if j > 0:
            end = min(end, j)
    return body[idx:end]


EF_DESCRIPTION_MARKERS = (
    "Зачем нужна ЭФ",
    "Как перейти на ЭФ",
    "Дополнительные действия",
    "Макеты ЭФ",
)


def _is_ef_description_table(table) -> bool:
    """Таблица «Общие требования» — 2 колонки (лейбл | содержимое), не таблица полей."""
    for tr in table.find_all("tr"):
        for cell in tr.find_all(["td", "th"], recursive=False):
            text = cell.get_text(" ", strip=True)
            if any(marker in text for marker in EF_DESCRIPTION_MARKERS):
                return True
    return False


def _is_field_definition_table(table) -> bool:
    blob = table.get_text(" ", strip=True)
    return any(
        x in blob
        for x in ("Название поля", "Тип поля", "Логика заполнения", "№ п/п", "Обязательность")
    )


def sfr_output_names(orig_name: str) -> tuple[str, str]:
    """Имена SFR-пары из исходника: префикс в скобках как в источнике ([О2+NEW] ≠ [O2+NEW])."""
    if "]-ЭФ-" in orig_name:
        prefix, rest = orig_name.split("]-ЭФ-", 1)
        return (
            f"{prefix}]-SFR-ЭФ-{rest}",
            f"{prefix}]-SFR-FE-Контроли-ЭФ-{rest}",
        )
    stem = orig_name.removesuffix(".md")
    return f"{stem}-SFR-ЭФ.md", f"{stem}-SFR-FE-Контроли.md"


def extract_ef_description_table(body: str) -> str:
    """Внешняя HTML-таблица раздела «Общие требования к ЭФ» (вложенные <table> в ячейках сохраняются).

    Нельзя извлекать regex'ом (<table>.*?</table>) — при вложенных таблицах (макеты Figma)
    обрывается на первой внутренней </table>.
    """
    m = re.search(r"# Общие требования к ЭФ\s*(.*?)(?=\n# Вкладка|\Z)", body, re.S)
    if not m:
        return "_[НЕ РАСПОЗНАНО: раздел «Общие требования к ЭФ» не найден]_"
    soup = BeautifulSoup(m.group(1).strip(), "html.parser")
    candidates = [
        t
        for t in soup.find_all("table")
        if _is_ef_description_table(t) and not _is_field_definition_table(t)
    ]
    if not candidates:
        top_level = [t for t in soup.find_all("table") if t.find_parent("table") is None]
        if top_level and not _is_field_definition_table(top_level[0]):
            return str(top_level[0]).strip()
        return "_[НЕ РАСПОЗНАНО: таблица описания ЭФ не извлечена]_"
    outers = [
        t
        for t in candidates
        if not any(t in other.descendants for other in candidates if other is not t)
    ]
    table = outers[0] if outers else max(candidates, key=lambda t: len(str(t)))
    return str(table).strip()


def main(fe_ref: Path | None = None, fe_only: bool = False):
    src_path = [p for p in glob.glob(SRC_GLOB, recursive=True) if "SFR" not in p and "FE-" not in p][0]
    text = Path(src_path).read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    orig_name = Path(src_path).name
    out_dir = Path(src_path).parent

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
        table = find_field_table(sec)
        if table:
            all_fields.extend(extract_fields_from_table(table, tab))

    analyses = build_field_analyses(all_fields)
    ref_fe = load_reference_fe_meta(Path(src_path), fe_ref)
    vis_controls, sf_map = extract_visibility_controls(all_fields, analyses, start=1)
    rule_controls = extract_rule_controls(
        all_fields, analyses, start=len(vis_controls) + 1, ref=ref_fe
    )
    all_controls = vis_controls + rule_controls
    group_keys = resolve_fe_group_keys(ref_fe, all_controls)
    fe_rows = build_fe_table(all_controls, group_keys)
    group_desc_block = format_group_descriptions(group_keys, ref_fe.descriptions)

    btn_lines: list[str] = []
    btn_markers = [
        ('Открываемый счёт', '## Описание кнопок ЭФ (Вкладка "Открываемый счёт")'),
        ('Реквизиты ГК', '## Описание кнопок ЭФ (Вкладка "Реквизиты ГК")'),
        ('Подтверждение', '## Описание кнопок ЭФ (Вкладка "Подтверждение")'),
    ]
    for tab, marker in btn_markers:
        sec = get_section(body, marker, ['\n# Вкладка', '\n## Описание полей'])
        if sec:
            for line in extract_buttons(sec):
                btn_lines.append(f"**{tab}:** {line}")

    # Описание ЭФ — внешняя таблица «Общие требования» (HTML как в исходнике)
    desc_block = extract_ef_description_table(body)

    ef_title = '[O2+NEW] SFR ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования'
    fe_title = "[O2+NEW] SFR FE Контроли ЭФ Клиента Открытие доп счета и заключение ДБС в режиме редактирования"
    sfr_ef_name, sfr_fe_name = sfr_output_names(orig_name)
    sfr_ef = out_dir / sfr_ef_name
    sfr_fe = out_dir / sfr_fe_name

    entity = "../../datamodel/Модель-данных/Заявки/Заявка-на-открытие-доп-счета-и-заключение-ДБС.md"

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

    history_table = ""
    intro = body.split("## ")[0]
    hm = re.search(r"(<table>.*?</table>)", intro, re.S)
    if hm:
        history_table = hm.group(1)

    ef_doc = f"""---
doc_id: '{{{{o2plus: {ef_title}}}}}'
title: '{ef_title}'
description: 'SFR: переформатированная ЭФ O2+ (единая таблица полей).'
doc_type: requirement
requirement_type: screenItemForm
service_code: o2plus
source: CONFLUENCE
confluence_page_id: '{fm.get("confluence_page_id", "6365126")}'
status: draft
version: 1.1.0
related: '{{{{o2plus:{fe_title}}}}}'
tags: [screen-form, sfr]
---

**История изменений:** перенесена из исходника [{fm.get("title", orig_name)}]({orig_name}) (см. там полную историю). Настоящая версия — результат переформатирования (SFR) screen-form-restructure v3.1: единая таблица полей; проверки — в [{fe_title}]({sfr_fe.name}).

{history_table}

| Дата | Описание | Автор | Задача |
| --- | --- | --- | --- |
| 2026-07-14 | SFR (чистый эксперимент): парсинг только исходной ЭФ, без control-split | agent | — |

# ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования

Данная ЭФ предназначена для создания/редактирования [Заявка на открытие доп счета и заключение ДБС]({entity}).

## Описание ЭФ

> Таблица перенесена из исходника «Общие требования к ЭФ» **без изменения структуры** (HTML, включая вложенные таблицы в ячейках).

{desc_block}

ЭФ состоит из трёх вкладок:

| № | Вкладка | Условие видимости |
| --- | --- | --- |
| 1 | Открываемый счёт | Всегда |
| 2 | Реквизиты ГК | см. SF-01 (в SFR FE-контролях) |
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

Relational-правила и вынесенная видимость — в [{fe_title}]({sfr_fe.name}). Реакции (информеры, модалки) — в едином документе информирования сервиса.
"""

    fe_doc = f"""---
doc_id: '{{{{o2plus: {fe_title}}}}}'
title: '{fe_title}'
description: 'SFR FE-контроли: извлечены из описания ЭФ (без control-split).'
doc_type: requirement
requirement_type: control
control_kind: screen-form
service_code: o2plus
source: CONFLUENCE
confluence_page_id: '{fm.get("confluence_page_id", "6365126")}'
status: draft
version: 1.1.0
related: '{{{{o2plus:{ef_title}}}}}'
tags: [control, screen-form, frontend, ux, sfr]
---

> **Зона 3.** Проверки полей [{ef_title}]({sfr_ef.name}). Контроли извлечены **только** из исходной ЭФ (screen-form-restructure, без внешних FE/BE файлов).

## Назначение

Контроли полей и видимости [{ef_title}]({sfr_ef.name}), выполняемые на клиенте.

## Группы триггеров

{group_desc_block}

## Контроли формы

`R` — реактивный; `V` — событийный. `visibility`: сообщение = «—».

{chr(10).join(fe_rows)}

> Сгенерировано restructure_o2plus_clean.py: {len(vis_controls)} visibility, {len(rule_controls)} rule; групп: {len(group_keys)} ({", ".join(f"№{g}" for g in group_keys) or "—"}). Референс групп: {ref_fe.path.name if ref_fe.path else "не найден"}. Требуется ревью аналитиком: условия visibility нормализованы по осям (смысловой разбор), критерий вынесения — механический (controls.md).
"""

    if not fe_only:
        sfr_ef.write_text(ef_doc, encoding="utf-8")
    sfr_fe.write_text(fe_doc, encoding="utf-8")
    print(f"Source: {src_path}")
    print(f"Fields: {len(all_fields)}")
    print(f"Controls: {len(all_controls)} (vis={len(vis_controls)}, rule={len(rule_controls)})")
    print(f"Groups: {group_keys} (ref: {ref_fe.path})")
    if not fe_only:
        print(f"EF: {sfr_ef}")
    print(f"FE: {sfr_fe}")
    latin_twin = out_dir / sfr_ef.name.replace("О2+NEW", "O2+NEW", 1) if "О2+NEW" in sfr_ef.name else None
    if latin_twin and latin_twin.exists() and latin_twin != sfr_ef:
        print(f"WARN: устаревший дубликат (латинская O): {latin_twin.name} — откройте {sfr_ef.name}")
    # sanity: field names
    for f in all_fields[:5]:
        print(f"  OK: {f.num} | {f.name}")
    for f in all_fields[10:15]:
        print(f"  OK: {f.num} | {f.name}")


def debug_tabs():
    src_path = [p for p in glob.glob(SRC_GLOB, recursive=True) if "SFR" not in p and "FE-" not in p][0]
    _, body = parse_frontmatter(Path(src_path).read_text(encoding="utf-8"))
    markers = [
        ("Открываемый счёт", '## Описание ЭФ "Открываемый счёт" основная часть'),
        ("Реквизиты ГК", '## Описание полей ЭФ (Вкладка "Реквизиты ГК")'),
        ("Подтверждение", '## Описание полей ЭФ (Вкладка "Подтверждение")'),
    ]
    for tab, marker in markers:
        sec = get_section(body, marker, ["## Описание кнопок"])
        table = find_field_table(sec)
        n = len(extract_fields_from_table(table, tab)) if table else 0
        print(tab, "sec", len(sec), "table", bool(table), "fields", n)


if __name__ == "__main__":
    import argparse
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        debug_tabs()
    else:
        ap = argparse.ArgumentParser(description="SFR generator O2+ (clean)")
        ap.add_argument("--fe-ref", type=Path, help="Парный FE-Контроли для групп триггеров")
        ap.add_argument("--fe-only", action="store_true", help="Перегенерировать только SFR FE")
        args = ap.parse_args()
        main(fe_ref=args.fe_ref, fe_only=args.fe_only)
