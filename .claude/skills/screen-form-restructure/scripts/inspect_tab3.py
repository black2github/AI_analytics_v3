#!/usr/bin/env python3
import glob, re
from bs4 import BeautifulSoup

src = [p for p in glob.glob(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*редактирования.md", recursive=True) if "SFR" not in p and "FE-" not in p][0]
text = open(src, encoding="utf-8").read()
body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
idx = body.find('## Описание полей ЭФ (Вкладка "Подтверждение")')
chunk = body[idx:idx+50000]
soup = BeautifulSoup(chunk, "html.parser")
tables = soup.find_all("table")
print("tables", len(tables))
for ti, table in enumerate(tables):
    rows = table.find_all("tr")
    print(f"\n--- table {ti} rows={len(rows)} ---")
    for i, tr in enumerate(rows[:8]):
        cells = tr.find_all(["td", "th"])
        print(f"row {i} n={len(cells)}")
        for j, c in enumerate(cells):
            t = c.get_text(" ", strip=True)[:55]
            print(f"  {j} cs={c.get('colspan','')} rs={c.get('rowspan','')} | {t}")
