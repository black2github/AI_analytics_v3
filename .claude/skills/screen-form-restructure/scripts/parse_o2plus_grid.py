#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug: extract fields from O2+ ЭФ with correct grid."""
import glob
import re
from bs4 import BeautifulSoup


def build_grid(table):
    rows = table.find_all("tr")
    grid = []
    pending = {}  # col -> (html, remaining_rows)

    for tr in rows:
        cells = tr.find_all(["td", "th"])
        row = []
        ci = 0
        col = 0
        while col < 20:  # safety cap
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

    width = max(len(r) for r in grid) if grid else 0
    for r in grid:
        while len(r) < width:
            r.append("")
    return grid


def cell_text(html):
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def find_type_col(header_row):
    for i, html in enumerate(header_row):
        t = cell_text(html).lower()
        if "тип поля" in t or t == "тип поля":
            return i
    return 3


def extract_fields(grid):
    if len(grid) < 2:
        return []
    type_col = find_type_col(grid[0])
    fields = []
    for row in grid[1:]:
        texts = [cell_text(h) for h in row]
        if type_col >= len(texts):
            continue
        ftype = texts[type_col]
        if not ftype:
            continue
        known = (
            "Текст",
            "Число",
            "Дата",
            "Список",
            "Переключатель",
            "Чекбокс",
            "Заголовок",
            "Гиперссылка",
            "Кнопка",
            "Файл",
            "Таблица",
        )
        if not (
            ftype in known
            or ftype.startswith("Тип сообщения")
            or "сообщени" in ftype.lower()
        ):
            continue
        name = texts[type_col - 1] if type_col > 0 else ""
        num_parts = texts[: type_col - 1]
        num = " ".join(p for p in num_parts if p).strip()
        fill = texts[type_col + 1] if type_col + 1 < len(texts) else ""
        req = texts[type_col + 2] if type_col + 2 < len(texts) else ""
        comm = texts[type_col + 3] if type_col + 3 < len(texts) else ""
        if not name:
            continue
        fields.append(
            {
                "num": num,
                "name": name,
                "type": ftype,
                "fill": fill[:40],
                "req": req,
                "comm_len": len(comm),
            }
        )
    return fields


def main():
    src = [
        p
        for p in glob.glob(
            r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*редактирования.md",
            recursive=True,
        )
        if "SFR" not in p and "FE-" not in p
    ][0]
    text = open(src, encoding="utf-8").read()
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)

    sections = [
        ("Открываемый счёт", '## Описание ЭФ "Открываемый счёт" основная часть'),
        ("Реквизиты ГК", '## Описание полей ЭФ (Вкладка "Реквизиты ГК")'),
        ("Подтверждение", '## Описание полей ЭФ (Вкладка "Подтверждение")'),
    ]
    total = 0
    for tab, marker in sections:
        idx = body.find(marker)
        if idx < 0:
            print("MISSING", tab)
            continue
        chunk = body[idx : idx + 80000]
        soup = BeautifulSoup(chunk, "html.parser")
        table = soup.find("table")
        if not table:
            print("NO TABLE", tab)
            continue
        grid = build_grid(table)
        fields = extract_fields(grid)
        total += len(fields)
        print(f"\n=== {tab} cols={len(grid[0])} fields={len(fields)} ===")
        for f in fields[:8]:
            print(f"  {f['num']!r:12} | {f['name'][:45]!r}")
        if len(fields) > 8:
            print(f"  ... +{len(fields)-8} more")
    print(f"\nTOTAL FIELDS: {total}")


if __name__ == "__main__":
    main()
