#!/usr/bin/env python3
"""Inspect HTML table structure in O2+ screen form source."""
import glob
import re
from bs4 import BeautifulSoup

paths = glob.glob(
    r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*ЭФ-Клиента-Открытие-доп-счета*редактирования.md",
    recursive=True,
)
src = [p for p in paths if "SFR" not in p and "FE-" not in p][0]
text = open(src, encoding="utf-8").read()
body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)

idx = body.find('## Описание ЭФ "Открываемый счёт"')
idx2 = body.find("<table>", idx)
idx3 = body.find("</table>", idx2) + 8
tbl = body[idx2:idx3]
soup = BeautifulSoup(tbl, "html.parser")
rows = soup.find_all("tr")
print("rows", len(rows))
for i, tr in enumerate(rows[:15]):
    cells = tr.find_all(["td", "th"])
    print(f"--- row {i} n={len(cells)}")
    for j, c in enumerate(cells):
        rs = c.get("rowspan", "")
        cs = c.get("colspan", "")
        t = c.get_text(" ", strip=True)[:60]
        print(f"  {j} rs={rs} cs={cs} | {t}")
