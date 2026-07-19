# -*- coding: utf-8 -*-
"""SFR для O2+ ЭФ редактирования — screen-form-restructure v3.1.

Механический разбор HTML-таблиц + перенос FE-контролей из control-split.
"""
from __future__ import annotations

import glob
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError as e:
    raise SystemExit("pip install beautifulsoup4") from e


@dataclass
class FieldRow:
    num: str
    name: str
    ui_type: str
    fill_logic: str
    required: str
    comment: str
    tab: str
    is_header: bool = False


@dataclass
class FeControl:
    id: str
    orig: str
    title: str
    typ: str
    fields: str
    condition: str
    message: str
    r: str
    groups: dict[int, str]


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("'\"")
    return fm, m.group(2)


def clean_cell(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        label = a.get_text(strip=True)
        a.replace_with(f"[{label}]({href})" if href else label)
    for br in soup.find_all("br"):
        br.replace_with("<br>")
    for tag in soup.find_all(["strong", "p", "ul", "li", "ol"]):
        if tag.name == "li":
            tag.insert_before("• ")
        tag.unwrap()
    text = str(soup)
    text = re.sub(r"<img[^>]*>", lambda m: "[img]", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


UI_TYPES = {
    "список", "текст", "переключатель", "чекбокс", "дата", "заголовок",
    "информер", "кнопка", "гиперссылка", "блок", "файл", "таблица",
    "поле ввода", "радиокнопка", "текстовое поле",
}


def looks_like_type(s: str) -> bool:
    low = s.lower().strip()
    return any(t in low for t in UI_TYPES) or low in ("—", "-", "")


def normalize_row(row: list[str | None]) -> tuple[str, str, str, str, str, str]:
    cells = [clean_cell(c or "") for c in row[:6]]
    while len(cells) < 6:
        cells.append("")
    num, c1, c2, c3, c4, c5 = cells
    # colspan=2 в шапке: в данных бывает num|c1=name или num+name в c1
    if c2 and looks_like_type(c2):
        return num, c1, c2, c3, c4, c5
    if c3 and looks_like_type(c3):
        # сдвиг: num пустое имя в c1, тип в c3
        name = c1 or c2
        return num, name, c3, c4, c5, ""
    if c1 and not c2:
        return num, c1, c2, c3, c4, c5
    # num в первой колонке, имя во второй — стандарт
    name = c1 if c1 else num
    num = "" if c1 else num
    return num, name, c2, c3, c4, c5


def field_label(num: str, name: str) -> str:
    if num and name and re.match(r"^[\d.]+$", num):
        return name
    return name or num


def parse_field_table(html: str, tab: str) -> list[FieldRow]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []
    ncols = 6
    pending: list[tuple[str, int] | None] = [None] * ncols
    grid: list[list[str | None]] = []

    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])
        row: list[str | None] = [None] * ncols
        ci = 0
        col = 0
        while col < ncols:
            if pending[col] is not None:
                val, left = pending[col]
                row[col] = val
                pending[col] = (val, left - 1) if left > 1 else None
                col += 1
                continue
            if ci >= len(cells):
                col += 1
                continue
            cell = cells[ci]
            ci += 1
            rs = int(cell.get("rowspan", 1))
            cs = int(cell.get("colspan", 1))
            val = str(cell)
            for c in range(col, min(col + cs, ncols)):
                row[c] = val
                if rs > 1:
                    pending[c] = (val, rs - 1)
            col += cs
        grid.append(row)

    result: list[FieldRow] = []
    for row in grid:
        num, name, ui_type, fill_logic, required, comment = normalize_row(row)
        if not name and not num:
            continue
        label = field_label(num, name)
        is_header = (
            "основная часть" in label.lower()
            or label.startswith("Блок ")
            or (num and not re.match(r"^[\d.]+$", num) and len(label) > 40)
        )
        if label in ("Наименование ЭФ",) or "Наименование ЭФ" in label:
            is_header = True
        result.append(
            FieldRow(
                num=num,
                name=label,
                ui_type=ui_type,
                fill_logic=fill_logic,
                required=required,
                comment=comment,
                tab=tab,
                is_header=is_header,
            )
        )
    return result


def split_visibility(comment: str, fill: str) -> tuple[str, str, bool]:
    blob = f"{comment} {fill}"
    low = blob.lower()
    nontrivial = any(
        x in low
        for x in [
            " и ",
            " или ",
            "если",
            "иначе",
            "признак",
            "настраиваем",
            "список",
            "пуст",
            "тип сч",
            "заключить",
            "договор",
            "зарезерв",
            "комисси",
            "участник",
        ]
    )
    if not nontrivial and ("всегда" in low or "отображается всегда" in low):
        return "Всегда", "", False
    if "не отображается" in low or "скрыт" in low or "не отобража" in low:
        if nontrivial and (" и " in low or " или " in low or low.count("если") > 1):
            return "см. SFR-FE", blob, True
        vis = comment or fill
        vis = re.sub(r"(?i)^если\s+", "**Если** ", vis)
        vis = re.sub(r"(?i)\s+то\s+", ", **то** ", vis)
        vis = re.sub(r"(?i)\s+иначе\s+", ", **иначе** ", vis)
        return vis[:500] if len(vis) > 500 else vis, "", False
    if nontrivial:
        return "см. SFR-FE", blob, True
    if comment:
        return comment, "", False
    return "Всегда", "", False


def map_fill_mode(fill: str, comment: str) -> str:
    blob = f"{fill} {comment}".lower()
    if "выбор из списка" in blob or "список" in fill.lower():
        if "автоматически" in blob and "недоступ" in blob:
            return "Автоматически"
        return "Выбор из списка"
    if "автоматически" in blob or "недоступ" in blob or "заполняется автомат" in blob:
        if "вручную" in blob or "редактир" in blob:
            return "Автоматически, если условие; иначе Вручную"
        return "Автоматически"
    if "загрузк" in blob or "файл" in blob:
        return "Вручную"
    return "Вручную"


def map_format(ui_type: str, fill: str, comment: str) -> str:
    parts = []
    blob = f"{fill} {comment}"
    for pat in [
        r"маск[аи][^.]{0,120}",
        r"пример[^.]{0,120}",
        r"не более \d+",
        r"\d+ символ",
        r"только цифр",
        r"плейсхолдер[^.]{0,80}",
    ]:
        m = re.search(pat, blob, re.I)
        if m:
            parts.append(m.group(0).strip())
    if ui_type and ui_type not in ("—", "-"):
        parts.append(f"(тип: {ui_type})")
    return "; ".join(parts) if parts else ("—" if ui_type in ("Заголовок", "Текст", "—", "-", "") else "(на поле)")


def map_logic(fill: str, comment: str) -> str:
    chunks = []
    blob = f"{fill}\n{comment}"
    for label in ["Источник списка:", "По умолчанию:", "Каскад:"]:
        if label.lower() in blob.lower():
            idx = blob.lower().find(label.lower())
            end = len(blob)
            for other in ["Источник списка:", "По умолчанию:", "Каскад:", "Видимость:"]:
                if other != label and other.lower() in blob.lower()[idx + len(label) :]:
                    j = blob.lower().find(other.lower(), idx + len(label))
                    end = min(end, j)
            chunks.append(blob[idx:end].strip())
    if not chunks:
        if fill and not re.search(r"(?i)отображ", fill):
            chunks.append(fill)
    return "<br>".join(chunks) if chunks else ("—" if not fill else fill[:300])


def map_required(req: str, name: str) -> str:
    if not req:
        return "—"
    low = req.lower()
    if "да" in low and "нет" not in low:
        return "Да"
    if "нет" in low and "да" not in low:
        return "Нет"
    if "услов" in low or "если" in low:
        return "см. SF"
    return req


def extract_sections(body: str) -> dict[str, str]:
    tabs = {
        "Открываемый счёт": r'# Вкладка"Открываемый счёт":|# Вкладка "Открываемый счёт"',
        "Реквизиты ГК": r'# Вкладка "Реквизиты ГК"',
        "Подтверждение": r'# Вкладка "Подтверждение"',
    }
    positions = []
    for name, pat in tabs.items():
        m = re.search(pat, body)
        if m:
            positions.append((m.start(), name))
    positions.sort()
    sections: dict[str, str] = {}
    for i, (pos, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        sections[name] = body[pos:end]
    # general requirements
    m = re.search(r"# Общие требования к ЭФ", body)
    if m:
        end = positions[0][0] if positions else len(body)
        sections["Общие требования"] = body[m.start() : end]
    return sections


EF_DESCRIPTION_MARKERS = (
    "Зачем нужна ЭФ",
    "Как перейти на ЭФ",
    "Дополнительные действия",
    "Макеты ЭФ",
)


def _is_ef_description_table(table) -> bool:
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


def extract_ef_description_table(body: str) -> str:
    """Внешняя HTML-таблица «Общие требования к ЭФ» (см. restructure_o2plus_clean.py)."""
    m = re.search(r"# Общие требования к ЭФ\s*(.*?)(?=\n# Вкладка|\Z)", body, re.S)
    if not m:
        return ""
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
        return ""
    outers = [
        t
        for t in candidates
        if not any(t in other.descendants for other in candidates if other is not t)
    ]
    table = outers[0] if outers else max(candidates, key=lambda t: len(str(t)))
    return str(table).strip()


def find_first_table(section: str) -> str:
    """Первая таблица полей в секции вкладки (не таблица «Описание ЭФ»)."""
    for m in re.finditer(r"(<table>.*?</table>)", section, re.S):
        blob = m.group(1)
        if any(
            x in blob
            for x in ["Название поля", "Тип поля", "Логика заполнения", "№ п/п", "Обязательность"]
        ):
            return blob
    m = re.search(r"(<table>.*?</table>)", section, re.S)
    return m.group(1) if m else ""


def find_buttons(section: str) -> list[tuple[str, str, str]]:
    m = re.search(r"## Описание кнопок.*?\n(.*?)(?=\n# |\Z)", section, re.S)
    if not m:
        return []
    soup = BeautifulSoup(m.group(1), "html.parser")
    table = soup.find("table")
    if not table:
        return []
    out = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) >= 2:
            out.append(
                (
                    clean_cell(str(cells[0])),
                    clean_cell(str(cells[1])),
                    clean_cell(str(cells[2])) if len(cells) > 2 else "",
                )
            )
    return out


def parse_existing_fe(path: Path) -> list[FeControl]:
    text = path.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        if not line.startswith("| SF-"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 9:
            continue
        groups = {}
        for i, g in enumerate([1, 2, 3], start=6):
            groups[g] = parts[i] if i < len(parts) else ""
        rows.append(
            FeControl(
                id=parts[0],
                orig=parts[1],
                title=parts[3],
                typ="rule",
                fields=parts[2],
                condition=parts[4],
                message=parts[5],
                r="",
                groups=groups,
            )
        )
    return rows


def build_visibility_controls(fields: list[FieldRow], start_id: int) -> list[FeControl]:
    controls = []
    n = start_id
    seen = set()

    # tab visibility
    controls.append(
        FeControl(
            id=f"SF-{n:02d}",
            orig="вкладка",
            title="Видимость вкладки «Реквизиты ГК»",
            typ="visibility",
            fields="Вкладка «Реквизиты ГК» ← Тип счёта",
            condition="**Если** <Код типа счета> == 2, **то** вкладка отображается, **иначе** не отображается",
            message="—",
            r="R",
            groups={1: "", 2: "", 3: ""},
        )
    )
    n += 1
    seen.add("вкладка")

    key_vis = [
        ("Тип счёта", "Тип счёта ← Настраиваемые параметры.on_open_sec_acc_zak", "значение «Участник закупок»"),
        ("Заключить новый договор", "Заключить новый договор ← Организация, Договор банковского счёта", "поле и блок"),
        ("Договор банковского счёта", "Договор банковского счёта ← Заключить новый договор, список договоров Ф1", "поле"),
        ("Зарезервированный счёт", "Зарезервированный счёт ← Тип счёта, reservedAccountList (Ф1)", "поле"),
        ("Списать со счёта", "Списать со счёта ← Тип счёта, CommissionMark (Ф1)", "поле и блок «Комиссия»"),
        ("Согласие 2", "Согласие 2 ← Тип счёта", "чекбокс ГК"),
        ("блок «Реквизиты госконтракта»", "Блок «Реквизиты госконтракта» ← Тип счёта", "блок на вкладке Подтверждение"),
    ]

    for name, flds, _ in key_vis:
        fr = next((f for f in fields if name.lower() in f.name.lower()), None)
        cond = fr.comment or fr.fill_logic if fr else f"см. ЭФ, поле «{name}»"
        controls.append(
            FeControl(
                id=f"SF-{n:02d}",
                orig=fr.num if fr else "—",
                title=f"Видимость {name.lower() if 'блок' not in name else name}",
                typ="visibility",
                fields=flds,
                condition=cond[:800],
                message="—",
                r="R",
                groups={1: "", 2: "", 3: ""},
            )
        )
        n += 1

    # button visibility
    controls.append(
        FeControl(
            id=f"SF-{n:02d}",
            orig="кнопки",
            title="Видимость кнопки «Подписать и отправить»",
            typ="visibility",
            fields="Подписать и отправить ← результат проверки полномочий ЕСК",
            condition="**Если** проверка полномочий подписанта пройдена, **то** кнопка отображается, **иначе** отображается «Сохранить»",
            message="—",
            r="R",
            groups={3: ""},
        )
    )
    return controls


def fe_table_lines(controls: list[FeControl]) -> list[str]:
    header = (
        "| ID | Ориг. | Название проверки | Тип | Поля | Условие | Сообщение об ошибке | R | Гр.1 | Гр.2 | Гр.3 |"
    )
    sep = "|----|-------|-------------------|-----|------|---------|---------------------|:-:|:-:|:--:|"
    lines = [header, sep]
    for c in controls:
        g = [c.groups.get(i, "") for i in (1, 2, 3)]
        lines.append(
            f"| {c.id} | {c.orig} | {c.title} | {c.typ} | {c.fields} | {c.condition} | {c.message} | {c.r} | {g[0]} | {g[1]} | {g[2]} |"
        )
    return lines


def field_table_lines(fields: list[FieldRow]) -> list[str]:
    header = "| Поле | Тип | Формат | Способ заполнения | Обяз. | Видимость | Логика установки значения |"
    sep = "|------|-----|--------|-------------------|:-----:|-----------|---------------------------|"
    lines = [header, sep]
    current_tab = ""
    for f in fields:
        if f.tab != current_tab:
            current_tab = f.tab
            lines.append(f"| **Вкладка «{f.tab}»** | | | | | | |")
        if f.is_header:
            lines.append(f"| **{f.name}** | Заголовок | — | Автоматически | — | Всегда | — |")
            continue
        vis, _, nontriv = split_visibility(f.comment, f.fill_logic)
        if nontriv:
            vis = "см. SFR-FE"
        lines.append(
            "| "
            + " | ".join(
                [
                    f.name,
                    f.ui_type or "Текст",
                    map_format(f.ui_type, f.fill_logic, f.comment),
                    map_fill_mode(f.fill_logic, f.comment),
                    map_required(f.required, f.name),
                    vis,
                    map_logic(f.fill_logic, f.comment),
                ]
            )
            + " |"
        )
    return lines


def main():
    paths = glob.glob(
        r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*редактирования.md",
        recursive=True,
    )
    src_path = [p for p in paths if "FE-" not in p and "SFR-" not in p][0]
    fe_src = Path(
        r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\[O2+NEW]-Сервис-заключения-ДБС-и-открытия-дополнительного-счета\[O2+NEW]-FE-Контроли-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"
    )
    # resolve FE via glob if bracket path fails
    if not fe_src.exists():
        fe_candidates = glob.glob(
            r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*FE-Контроли*редактирования.md",
            recursive=True,
        )
        fe_src = Path(fe_candidates[0])

    text = Path(src_path).read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    sections = extract_sections(body)

    all_fields: list[FieldRow] = []
    for tab in ("Открываемый счёт", "Реквизиты ГК", "Подтверждение"):
        sec = sections.get(tab, "")
        tbl = find_first_table(sec)
        if tbl:
            all_fields.extend(parse_field_table(tbl, tab))

    out_dir = Path(src_path).parent
    sfr_ef = out_dir / "[O2+NEW]-SFR-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"
    sfr_fe = out_dir / "[O2+NEW]-SFR-FE-Контроли-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"

    orig_name = Path(src_path).name
    ef_title = '[O2+NEW] SFR ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования'
    fe_title = '[O2+NEW] SFR FE Контроли ЭФ Клиента: Открытие доп счета и заключение ДБС в режиме редактирования'
    ef_doc_id = "{{o2plus: " + ef_title + "}}"
    fe_doc_id = "{{o2plus: " + fe_title + "}}"

    # Описание ЭФ — внешняя таблица «Общие требования» (HTML как в исходнике)
    desc_table = extract_ef_description_table(body)

    buttons_md = []
    for tab in ("Открываемый счёт", "Реквизиты ГК", "Подтверждение"):
        for name, desc, vis in find_buttons(sections.get(tab, "")):
            buttons_md.append(f"- **{name}** — {desc[:200]}{'…' if len(desc)>200 else ''} (видимость: {vis[:120]})")

    existing = parse_existing_fe(fe_src)
    # upgrade to v3.1 columns
    upgraded: list[FeControl] = []
    for c in existing:
        upgraded.append(
            FeControl(
                id=c.id,
                orig=c.orig,
                title=c.title,
                typ="rule",
                fields=c.fields,
                condition=c.condition,
                message=c.message,
                r="R" if any(x in c.condition.lower() for x in ["длина", "символ", "цифр"]) else "",
                groups=c.groups,
            )
        )
    vis_controls = build_visibility_controls(all_fields, start_id=len(upgraded) + 1)
    all_fe = upgraded + vis_controls

    entity = "../../datamodel/Модель-данных/Заявки/Заявка-на-открытие-доп-счета-и-заключение-ДБС.md"
    be_link = "[O2+NEW]-BE-Контроли-заявки.md"
    orig_link = orig_name

    ef_doc = f"""---
doc_id: '{ef_doc_id}'
title: '{ef_title}'
description: 'Переформатированная ЭФ заявки O2+ (SFR): единая таблица полей Doc as Code / API First.'
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

**История изменений:** перенесена из исходника [{fm.get('title', orig_name)}]({orig_link}) (см. там полную историю). Настоящая версия — результат переформатирования (SFR) к целевой структуре Doc as Code / API First: единая таблица полей `Поле | Тип | Формат | Способ заполнения | Обяз. | Видимость | Логика установки значения`; проверки выделены в парный документ [{fe_title}]({sfr_fe.name}).

| Дата | Описание | Автор | Задача |
| --- | --- | --- | --- |
| 2026-07-14 | SFR (screen-form-restructure v3.1): единая таблица полей, парный SFR FE-контроли; согласование с [{fe_src.name}]({fe_src.name}) | agent | — |

# ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования

Данная ЭФ предназначена для создания/редактирования [Заявка на открытие доп счета и заключение ДБС]({entity}).

## Описание ЭФ

> Таблица перенесена из исходника «Общие требования к ЭФ» **без изменения структуры** (HTML, включая вложенные таблицы в ячейках).

{desc_table if desc_table else "_[НЕ РАСПОЗНАНО: таблица общих требований не извлечена]_"}

ЭФ состоит из трёх вкладок:

| № | Вкладка | Условие видимости |
| --- | --- | --- |
| 1 | Открываемый счёт | Всегда |
| 2 | Реквизиты ГК | **Если** <Код типа счета> == 2, **то** отображается, **иначе** не отображается (см. SFR-FE) |
| 3 | Подтверждение | Всегда |

Навигация — кнопки «Продолжить» и «Назад» (см. «Действия»).

## Обозначения колонок

- **Тип** — UI-тип поля.
- **Формат** — ограничение и отображение; `(на поле)` — расхождение с атрибутом модели.
- **Способ заполнения** — {{Вручную | Выбор из списка | Автоматически}}.
- **Обяз.** — Да/Нет; условная обязательность — `см. SFR-FE`.
- **Видимость** — показ/скрытие лейбла и значения; нетривиальная — `см. SFR-FE`.
- **Логика установки значения** — умолчание, источник списка, каскады (у поля-получателя).

## Поля формы

{chr(10).join(field_table_lines(all_fields))}

> **Примечание.** Механический SFR-разбор {len(all_fields)} строк; нетривиальная видимость и часть каскадов вынесены в [SFR FE-контроли]({sfr_fe.name}). Тексты условий в ячейках — из исходника; требуется ревью аналитиком.

## Действия

{chr(10).join(buttons_md) if buttons_md else "_Кнопки — см. исходник._"}

## Проверки формы

Relational-правила и вынесенная видимость — в [{fe_title}]({sfr_fe.name}). Гарантия целостности — в [[O2+NEW] BE Контроли заявки]({be_link}).
"""

    fe_doc = f"""---
doc_id: '{fe_doc_id}'
title: '{fe_title}'
description: 'Контроли полей и видимости SFR-ЭФ O2+; согласованы с control-split FE и дополнены visibility.'
doc_type: requirement
requirement_type: control
control_kind: screen-form
service_code: o2plus
source: CONFLUENCE
confluence_page_id: '{fm.get("confluence_page_id", "6365126")}'
status: draft
version: 1.1.0
related: '{{{{o2plus:{ef_title}}}, {{o2plus:[O2+NEW] BE Контроли заявки}}}}'
tags: [control, screen-form, frontend, ux, sfr]
---

> **Зона 3.** Проверки полей [[O2+NEW] SFR ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования]({sfr_ef.name}). Гарантия — в [[O2+NEW] BE Контроли заявки]({be_link}). Базовые rule-контроли перенесены из [[O2+NEW] FE Контроли ЭФ]({fe_src.name}) (control-split); добавлены visibility по механическому критерию из описания полей ЭФ.

## Назначение

Контроли полей и видимости [[O2+NEW] SFR ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования]({sfr_ef.name}), выполняемые на клиенте.

## Группы триггеров

- **Группа №1** — переход с вкладки «Открываемый счёт» по «Продолжить»; сохранение в DRAFT.
- **Группа №2** — переход с вкладки «Реквизиты ГК» по «Продолжить»/«Назад»; сохранение в NEW.
- **Группа №3** — «Подписать и отправить» / «Сохранить» на вкладке «Подтверждение».

Помимо FE-групп, те же события инициируют BE-группы 1–3 из [[O2+NEW] BE Контроли заявки]({be_link}) (x-controls: create/update/sign).

## Контроли формы

`R` — реактивный режим; `V` — событийный (в рамках группы). `visibility`: «Сообщение об ошибке» = «—».

{chr(10).join(fe_table_lines(all_fe))}

## Согласование с control-split

| Источник | SF-ID | Примечание |
| --- | --- | --- |
| [{fe_src.name}]({fe_src.name}) | SF-01…SF-{len(upgraded):02d} | rule-контроли заявки, сохранены `Ориг.` |
| SFR (видимость из ЭФ) | SF-{len(upgraded)+1:02d}…SF-{len(all_fe):02d} | новые `visibility`, режим `R` |

> Сгенерировано restructure_o2plus_ef.py; rule: {len(upgraded)}, visibility: {len(vis_controls)}. Требуется ревью условий видимости и каскадов.
"""

    sfr_ef.write_text(ef_doc, encoding="utf-8")
    sfr_fe.write_text(fe_doc, encoding="utf-8")
    print("EF:", sfr_ef, len(ef_doc), "fields:", len(all_fields))
    print("FE:", sfr_fe, len(fe_doc), "controls:", len(all_fe))


if __name__ == "__main__":
    main()
