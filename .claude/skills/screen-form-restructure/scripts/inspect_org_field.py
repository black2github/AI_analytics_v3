#!/usr/bin/env python3
import glob, re
from bs4 import BeautifulSoup

def build_grid(table):
    rows = table.find_all("tr")
    grid, pending = [], {}
    for tr in rows:
        cells = tr.find_all(["td", "th"])
        row, ci, col = [], 0, 0
        while col < 24:
            if col in pending and pending[col][1] > 0:
                html, left = pending[col]
                row.append(html)
                pending[col] = (html, left - 1) if left > 1 else None
                if left <= 1:
                    del pending[col]
                col += 1
                continue
            if ci >= len(cells):
                break
            cell = cells[ci]
            ci += 1
            rs, cs = int(cell.get("rowspan") or 1), int(cell.get("colspan") or 1)
            html = str(cell)
            for c in range(col, col + cs):
                row.append(html)
                if rs > 1:
                    pending[c] = (html, rs - 1)
            col += cs
        grid.append(row)
    w = max(len(r) for r in grid)
    for r in grid:
        r.extend([""] * (w - len(r)))
    return grid

src = [p for p in glob.glob(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*редактирования.md", recursive=True) if "SFR" not in p and "FE-" not in p][0]
body = re.sub(r"^---\n.*?\n---\n", "", open(src, encoding="utf-8").read(), flags=re.S)
marker = '## Описание ЭФ "Открываемый счёт" основная часть'
chunk = body[body.find(marker) : body.find(marker) + 80000]
soup = BeautifulSoup(chunk, "html.parser")
for table in soup.find_all("table"):
    grid = build_grid(table)
    for row in grid:
        texts = [BeautifulSoup(h, "html.parser").get_text(" ", strip=True) for h in row]
        if "Организация" in texts and "Тип поля" not in texts:
            i = texts.index("Организация")
            print("=== SOURCE Организация row ===")
            for j, t in enumerate(texts):
                print(f"  col{j}: {t[:200]}")
            comm = BeautifulSoup(row[i + 4] if i + 4 < len(row) else row[-1], "html.parser").get_text(" ", strip=True)
            print("\n--- comment excerpt ---")
            for phrase in ["кратк", "полн", "Отображ", "формат", "список", "поиск"]:
                if phrase.lower() in comm.lower():
                    m = re.search(f".{{0,40}}{phrase}.{{0,80}}", comm, re.I)
                    if m:
                        print(" ", m.group(0))
