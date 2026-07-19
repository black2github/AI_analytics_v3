# -*- coding: utf-8 -*-
"""Разделение единого документа контролей на BE/FE по правилам control-split.

Использование:
  python split_controls.py --src PATH --out-dir DIR [options]

Требует: beautifulsoup4 (pip install beautifulsoup4)
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError as e:
    raise SystemExit("pip install beautifulsoup4") from e


@dataclass
class ControlRow:
    orig: str
    attr: str
    name: str
    logic: str
    message: str
    groups: dict[int, bool] = field(default_factory=dict)
    obsolete: bool = False
    attr_note: str = ""


def parse_frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("'\"")
    return fm


BR_PLACEHOLDER = "\x00BR\x00"


def clean_html_cell(html: str) -> str:
    if not html:
        return ""
    if "<" not in html:
        return clean_cell_text(html)
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        label = a.get_text(strip=True)
        if href:
            a.replace_with(f"[{label}]({href})")
        else:
            a.replace_with(label)
    for br in soup.find_all("br"):
        br.replace_with(BR_PLACEHOLDER)
    for tag in soup.find_all(["strong", "p", "ul", "li", "ol"]):
        if tag.name == "li":
            tag.insert_before("• ")
        tag.unwrap()
    text = str(soup)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = text.replace(BR_PLACEHOLDER, "<br>")
    parts = [re.sub(r"[ \t]+", " ", p).strip() for p in text.split("<br>")]
    return "<br>".join(p for p in parts if p or len(parts) == 1)


def clean_cell_text(raw: str) -> str:
    if not raw:
        return ""
    text = unescape(raw.strip())
    text = text.replace(BR_PLACEHOLDER, "<br>")
    parts = [re.sub(r"[ \t]+", " ", p).strip() for p in text.split("<br>")]
    return "<br>".join(p for p in parts if p or len(parts) == 1)


def extract_attr_name(raw: str) -> tuple[str, str, bool]:
    if "<" in raw:
        note = ""
        obsolete = "неактуал" in raw.lower()
        m = re.search(r"Примечание:\s*([^<]+)", raw, re.I)
        if m:
            note = m.group(1).strip()
        soup = BeautifulSoup(raw, "html.parser")
        plain = soup.get_text(" ", strip=True)
        plain = re.sub(r"\s*Примечание:.*", "", plain, flags=re.I).strip()
        if "Обязательные поля вкладки" in plain:
            return plain, note, obsolete
        plain = re.sub(r"\[O2\+NEW\].*$", "", plain).strip()
        plain = plain.split("  ")[0].strip()
        return plain, note, obsolete
    return extract_attr_name_plain(raw)


def extract_attr_name_plain(raw: str) -> tuple[str, str, bool]:
    note = ""
    obsolete = "неактуал" in raw.lower()
    text = clean_cell_text(raw)
    m = re.search(r"Примечание:\s*(.+)$", text, re.I | re.M)
    if m:
        note = m.group(1).strip()
    plain = re.sub(r"\s*Примечание:.*", "", text, flags=re.I | re.S).strip()
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    plain = plain.replace("<br>", " ").strip()
    plain = re.sub(r"\s+", " ", plain).strip()
    if "Обязательные поля вкладки" in plain:
        return plain, note, obsolete
    return plain, note, obsolete


def parse_controls_table(html: str) -> list[ControlRow]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")
    # find header with group numbers
    group_cols: list[int] = []
    data_rows = rows[2:]  # skip 2 header rows
    header2 = rows[1].find_all(["td", "th"])
    for cell in header2:
        t = cell.get_text(strip=True)
        if t.isdigit():
            group_cols.append(int(t))

    ncols = 5 + len(group_cols)
    grid: list[list[str | None]] = []
    # (value, rows_left) per column; standard HTML table rowspan carry-over
    pending: list[tuple[str, int] | None] = [None] * ncols

    for tr in data_rows:
        cells = tr.find_all(["td", "th"])
        row: list[str | None] = [None] * ncols
        cell_idx = 0
        col = 0
        while col < ncols:
            if pending[col] is not None:
                val, left = pending[col]
                row[col] = val
                pending[col] = (val, left - 1) if left > 1 else None
                col += 1
                continue
            if cell_idx >= len(cells):
                col += 1
                continue
            cell = cells[cell_idx]
            cell_idx += 1
            rs = int(cell.get("rowspan", 1))
            cs = int(cell.get("colspan", 1))
            val = str(cell)
            for c in range(col, min(col + cs, ncols)):
                row[c] = val
                if rs > 1:
                    pending[c] = (val, rs - 1)
            col += cs
        grid.append(row)

    result: list[ControlRow] = []
    for row in grid:
        if not row or not row[0]:
            continue
        orig = clean_html_cell(row[0] or "")
        if not orig or orig.lower() == "№":
            continue
        attr_raw = row[1] or ""
        attr, note, obsolete = extract_attr_name(attr_raw)
        name = clean_html_cell(row[2] or "")
        logic = clean_html_cell(row[3] or "")
        message = clean_html_cell(row[4] or "")
        groups = {}
        for i, g in enumerate(group_cols):
            cell = row[5 + i] if 5 + i < len(row) else ""
            txt = clean_html_cell(cell or "")
            groups[g] = txt.upper() == "V"
        result.append(
            ControlRow(
                orig=orig,
                attr=attr,
                name=name,
                logic=logic,
                message=message,
                groups=groups,
                obsolete=obsolete,
                attr_note=note,
            )
        )
    return result


def parse_markdown_controls_table(text: str) -> list[ControlRow]:
    m = re.search(r"\*\*Контроли заявки:\*\*\s*\n+((?:\|.*\n)+)", text)
    if not m:
        return []

    lines = [line for line in m.group(1).splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return []

    group_cols: list[int] = []
    data_start = 3
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.split("|")[1:-1]]
        nums: list[int] = []
        for cell in cells[5:]:
            cell_num = re.sub(r"\*+", "", cell).strip()
            if cell_num.isdigit():
                nums.append(int(cell_num))
        if len(nums) >= 2:
            group_cols = nums
            data_start = i + 1
            break

    if not group_cols:
        return []

    result: list[ControlRow] = []
    for line in lines[data_start:]:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 5:
            continue
        orig = clean_cell_text(cells[0])
        if not orig or orig.lower() == "№":
            continue
        attr, note, obsolete = extract_attr_name_plain(cells[1])
        name = clean_cell_text(cells[2])
        logic = clean_cell_text(cells[3])
        message = clean_cell_text(cells[4])
        groups: dict[int, bool] = {}
        for i, g in enumerate(group_cols):
            if 5 + i < len(cells):
                txt = clean_cell_text(cells[5 + i])
                groups[g] = txt.upper() == "V"
        if not name and not logic and not message and not any(groups.values()):
            continue
        result.append(
            ControlRow(
                orig=orig,
                attr=attr,
                name=name,
                logic=logic,
                message=message,
                groups=groups,
                obsolete=obsolete,
                attr_note=note,
            )
        )
    return result


def extract_controls_table(text: str) -> list[ControlRow]:
    m = re.search(r"\*\*Контроли заявки:\*\*\s*\n\s*(<table>.*?</table>)", text, re.S)
    if m:
        rows = parse_controls_table(m.group(1))
        if rows:
            return rows
    return parse_markdown_controls_table(text)


def is_fe_aggregate(attr: str) -> bool:
    return "Обязательные поля вкладки" in attr


def is_rule(logic: str, name: str, attr: str) -> bool:
    keys = [
        "справочник",
        "Клиент Банка",
        "Соглашени",
        "РКО Ф1",
        "БСК",
        "ЕСК",
        "Заявка на открытие",
        "другой заявки",
        "Версионность",
        "423",
        "полномоч",
        "привилеги",
        "Ф1",
        "внешн",
    ]
    blob = f"{logic} {name} {attr}".lower()
    if any(k.lower() in blob for k in keys):
        return True
    if "если" in blob and ("<" in logic or "реквизит" in blob) and (
        "соответств" in blob or "завис" in blob or "если" in blob and " и " in blob
    ):
        if "длина" not in name.lower() and "обязательн" not in name.lower():
            if "формат" not in name.lower() and "символ" not in name.lower():
                if "ключеван" not in name.lower():
                    return True
    return False


def should_mirror_fe(row: ControlRow) -> bool:
    if is_fe_aggregate(row.attr):
        return True
    if row.obsolete:
        return False
    blob = f"{row.logic} {row.name} {row.attr}"
    if is_fe_aggregate(row.attr):
        return True
    if "На ЭФ" in row.logic or "вкладки" in row.logic and "отображается" in row.logic:
        return True
    # early rejection / field-level
    if any(
        x in blob
        for x in [
            "Обязательность",
            "Проверка длины",
            "недопустимых символов",
            "непуст",
            "формат",
            "Проверка наличия согласия",
            "чекбокс",
            "Согласие",
        ]
    ):
        if is_rule(row.logic, row.name, row.attr):
            # external but user-visible early
            if any(
                x in blob
                for x in ["Организация", "конституции", "договор", "РКО Ф1", "комисси"]
            ):
                return True
            return False
        return True
    if "Организация" in row.attr and "конституции" in row.name:
        return True
    if "РКО Ф1" in row.logic and "договор" in row.message.lower():
        return True
    return False


def fmt_groups(groups: dict[int, bool], keys: list[int]) -> list[str]:
    return ["V" if groups.get(k) else "" for k in keys]


def gen_be_table(rows: list[ControlRow], group_keys: list[int]) -> tuple[list[str], int]:
    lines = []
    n = 0
    for row in rows:
        n += 1
        typ = "rule" if is_rule(row.logic, row.name, row.attr) else "field"
        attr = row.attr
        if row.obsolete:
            attr = f"⚠️ {attr}"
        gs = "|".join([":--:" if True else "" for _ in group_keys])
        gvals = "|".join(fmt_groups(row.groups, group_keys))
        lines.append(
            f"| DM-{n:02d} | {row.orig} | {typ} | {attr} | {row.name} | {row.logic} | {row.message} | {gvals} |"
        )
    header = "| ID | Ориг. | Тип | Проверяемый атрибут | Название проверки | Условие | Сообщение об ошибке | " + " | ".join(
        [f"Гр.{g}" for g in group_keys]
    ) + " |"
    sep = "|----|-------|-----|---------------------|-------------------|---------|---------------------|" + "|".join(
        [":--:" for _ in group_keys]
    ) + "|"
    return [header, sep] + lines, n


def gen_fe_table(rows: list[ControlRow], group_keys: list[int]) -> tuple[list[str], int]:
    lines = []
    n = 0
    for row in rows:
        if not should_mirror_fe(row):
            continue
        n += 1
        attr = row.attr
        if row.obsolete:
            attr = f"⚠️ {attr}"
        gvals = "|".join(fmt_groups(row.groups, group_keys))
        lines.append(
            f"| SF-{n:02d} | {row.orig} | {attr} | {row.name} | {row.logic} | {row.message} | {gvals} |"
        )
    header = "| ID | Ориг. | Поле / объект формы | Название проверки | Условие | Сообщение об ошибке | " + " | ".join(
        [f"Гр.{g}" for g in group_keys]
    ) + " |"
    sep = "|----|-------|---------------------|-------------------|---------|---------------------|" + "|".join(
        [":--:" for _ in group_keys]
    ) + "|"
    return [header, sep] + lines, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--service", default="")
    ap.add_argument("--be-title", default="")
    ap.add_argument("--fe-title", default="")
    ap.add_argument("--be-file", default="")
    ap.add_argument("--fe-file", default="")
    ap.add_argument("--confluence-id", default="")
    args = ap.parse_args()

    src = Path(args.src)
    text = src.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)

    service = args.service or fm.get("service_code") or fm.get("service_id") or "open-add-account"
    confluence_id = args.confluence_id or fm.get("confluence_page_id") or fm.get("page_id") or "6365377"
    src_stem = src.stem

    if service == "open-add-account" or "open-add-account" in str(src):
        be_title = args.be_title or "BE Контроли заявки"
        fe_title = (
            args.fe_title
            or 'FE Контроли ЭФ Клиента: "Открытие доп счета и заключение ДБС" в режиме редактирования'
        )
        be_file = args.be_file or f"{src_stem.replace('-контроли-', '-be-контроли-')}.md"
        fe_file = (
            args.fe_file
            or "6365126-fe-контроли-эф-клиента-открытие-доп-счета-и-заключение-дбс-в-режиме-редактирования.md"
        )
        entity_link = "../04-data-model/related-entities/6364746-заявка-на-открытие-доп-счета-и-заключение-дбс.md"
        ef_link = "../06-screens/01-client/03-6365126-эф-клиента-открытие-доп-счета-и-заключение-дбс-в-режиме-редактирования.md"
        create_fn = "../05-system-functions/01-client/04-6364636-клиент-функция-создания-заявки.md"
        edit_fn = "../05-system-functions/01-client/05-6364637-клиент-функция-редактирования-заявки.md"
        process_create = "../03-process/02-6363396-создать-заявку-подписать-эп-и-отправить-в-банк.md"
        process_accept = "../03-process/03-6363397-принять-и-проверить-заявку.md"
        statuses = "../03-process/90-6364671-описание-статусов-заявки.md"
        openapi_note = "open-add-account"
    else:
        be_title = args.be_title or "[O2+NEW] BE Контроли заявки"
        fe_title = (
            args.fe_title
            or '[O2+NEW] FE Контроли ЭФ Клиента: Открытие доп счета и заключение ДБС в режиме редактирования'
        )
        be_file = args.be_file or "[O2+NEW]-BE-Контроли-заявки.md"
        fe_file = (
            args.fe_file
            or "[O2+NEW]-FE-Контроли-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"
        )
        entity_link = "../../datamodel/Модель-данных/Заявки/Заявка-на-открытие-доп-счета-и-заключение-ДБС.md"
        ef_link = "[O2+NEW]-Экранные-формы/[O2+NEW]-ЭФ-Клиента/[O2+NEW]-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС/[O2+NEW]-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"
        create_fn = "[O2+NEW]-Функции-системы/[O2+NEW]-Функции-Клиента/[O2+NEW]-Клиент-Функция-создания-заявки.md"
        edit_fn = "[O2+NEW]-Функции-системы/[O2+NEW]-Функции-Клиента/[O2+NEW]-Клиент-Функция-редактирования-заявки.md"
        process_create = "[O2+NEW]-Процесс-обработки-заявки/[O2+NEW]-ЖЦ-заявки-на-заключение-ДБС-и-открытие-доп-счета/[O2+NEW]-Создать-заявку,-подписать-ЭП-и-отправить-в-Банк.md"
        process_accept = "[O2+NEW]-Процесс-обработки-заявки/[O2+NEW]-ЖЦ-заявки-на-заключение-ДБС-и-открытие-доп-счета/[O2+NEW]-Принять-и-проверить-заявку.md"
        statuses = "[O2+NEW]-Процесс-обработки-заявки/[O2+NEW]-Описание-статусов-заявки.md"
        openapi_note = "o2plus-split"

    rows = extract_controls_table(text)
    if not rows:
        raise SystemExit("controls table not found")
    print(f"parsed {len(rows)} control rows")

    group_keys = sorted({g for r in rows for g in r.groups})
    fe_group_keys = [g for g in group_keys if g != 4]  # group 4 = ESK/BE lifecycle

    be_doc_id = f"{{{{{service}: {be_title}}}}}"
    fe_doc_id = f"{{{{{service}: {fe_title}}}}}"
    be_related = "{{" + service + ": " + fe_title + "}}"
    fe_related = "{{" + service + ": " + be_title + "}}"
    be_table, _ = gen_be_table(rows, group_keys)
    fe_table, fe_count = gen_fe_table(rows, fe_group_keys)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    be = f"""---
doc_id: '{be_doc_id}'
title: '{be_title}'
description: 'Контроли, оперирующие атрибутами сущности [Заявка на открытие доп счета и заключение ДБС]({entity_link}): обязательность, формат, справочники, межатрибутные и межсистемные правила. Зона 1 — публичный контракт, проецируется в OpenAPI через x-controls.'
doc_type: requirement
requirement_type: control
control_kind: data-model
service_code: {service}
source: CONFLUENCE
confluence_page_id: '{confluence_id}'
status: draft
version: 1.0.0
related: '{be_related}'
tags: [control, data-model, backend]
---

> **Зона 1 (публичный контракт).** Эти проверки оперируют **атрибутами сущности** [Заявка на открытие доп счета и заключение ДБС]({entity_link}). Выполняются сервисом при создании/сохранении, подписании и проверке полномочий. Парный FE-документ ({fe_title}) описывает проверки полей формы; осознанное дублирование.

## Назначение

Контроли заявки на открытие дополнительного счёта и заключение ДБС, оперирующие атрибутами модели данных. Применяются при создании/редактировании ([Клиент: Функция создания заявки]({create_fn}), [Клиент: Функция редактирования заявки]({edit_fn})), подписании и приёме в банк (шаг №2 [Принять и проверить заявку]({process_accept})).

## Группы триггеров

Группа — событие жизненного цикла / сохранения, при котором запускается подмножество проверок. Группы **сквозные** по документу. Группы 1–2 — также события переходов вкладок формы (см. парный FE-документ).

- **Группа №1** — контроли при переходе с вкладки «Открываемый счёт» по кнопке «Продолжить»; при сохранении заявки в статусе **DRAFT** ([Описание статусов заявки]({statuses})).
- **Группа №2** — контроли при переходе с вкладки «Реквизиты ГК» по кнопке «Продолжить»/«Назад»; при сохранении в статусе **NEW** (Ожидает подписи).
- **Группа №3** — контроли, обязательные для подписи документа («Подписать и отправить») — [Создать заявку, подписать ЭП и отправить в Банк]({process_create}).
- **Группа №4** — контроли по реквизитам, заполняемым после проверки полномочий данными из ЕСК.

## Контроли заявки

`ID` — стабильный сквозной идентификатор; `Ориг.` — исходный № Confluence; `Тип` — `field` / `rule`.

{chr(10).join(be_table)}

## Связь с OpenAPI

Операции из `{openapi_note}` ссылаются на этот документ через `x-controls` (один `source`, разные `group`).

```yaml
# POST /account-opening-contract — создать заявку
post:
  operationId: create
  summary: Создать заявку
  x-controls:
    source: "{be_doc_id}"
    group: [1, 2, 3]
---
# PUT /account-opening-contract — обновить заявку
put:
  operationId: update
  summary: Обновление заявки
  x-controls:
    source: "{be_doc_id}"
    group: [1, 2, 3]
---
# POST /account-opening-contract/sign — подписать
post:
  operationId: sign
  summary: Подписать заявку
  x-controls:
    source: "{be_doc_id}"
    group: 3
---
# POST /account-opening-contract/validate-sign — проверка полномочий / данные ЕСК
post:
  operationId: validateSign_1
  summary: Проверить подпись
  x-controls:
    source: "{be_doc_id}"
    group: 4
```

> Контроль №38 (полномочия УЛ) в исходнике без отметок групп — выполняется вне групповой матрицы при проверке полномочий.

> Согласия (№34–36): по умолчанию в BE; на FE дублируются проверки отметки на вкладке «Подтверждение» (предмет согласования с командой).
"""

    fe = f"""---
doc_id: '{fe_doc_id}'
title: '{fe_title}'
description: 'Контроли, оперирующие полями экранной формы: обязательность вкладок, формат и подтверждение полей. В OpenAPI не проецируются.'
doc_type: requirement
requirement_type: control
control_kind: screen-form
service_code: {service}
source: CONFLUENCE
confluence_page_id: '{confluence_id}'
status: draft
version: 1.0.0
related: '{fe_related}'
tags: [control, screen-form, frontend, ux]
---

> **Зона 3.** Проверки **полей** [ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования]({ef_link}). Гарантия — в BE ({be_title}).

## Назначение

Контроли полей формы заявки, выполняемые на клиенте при работе с [ЭФ Клиента "Открытие доп счета и заключение ДБС" в режиме редактирования]({ef_link}).

## Группы триггеров

- **Группа №1** — переход с вкладки «Открываемый счёт» на «Реквизиты ГК»/«Подтверждение» по «Продолжить».
- **Группа №2** — переход с вкладки «Реквизиты ГК» на «Подтверждение»/«Открываемый счёт» по «Продолжить»/«Назад».
- **Группа №3** — действие «Подписать и отправить» на вкладке «Подтверждение».

## Контроли заявки

`ID` — стабильный сквозной идентификатор; `Ориг.` — исходный № Confluence.

{chr(10).join(fe_table)}

> Сгенерировано split_controls.py; FE-записей: {fe_count}. Межсистемные проверки без полевой реакции оставлены только в BE.
"""

    be_path = out / be_file
    fe_path = out / fe_file
    be_path.write_text(be, encoding="utf-8")
    fe_path.write_text(fe, encoding="utf-8")
    print("BE:", be_path, len(be))
    print("FE:", fe_path, len(fe), "rows:", fe_count)


if __name__ == "__main__":
    main()
