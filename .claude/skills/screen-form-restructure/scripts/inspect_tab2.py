#!/usr/bin/env python3
import glob, re
from pathlib import Path
from bs4 import BeautifulSoup

SRC_GLOB = r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus\**\*редактирования.md"

def get_section(body, marker, end_markers):
    idx = body.find(marker)
    if idx < 0:
        return ""
    end = len(body)
    for em in end_markers:
        j = body.find(em, idx + len(marker))
        if j > 0:
            end = min(end, j)
    return body[idx:end]

src = [p for p in glob.glob(SRC_GLOB, recursive=True) if "SFR" not in p and "FE-" not in p][0]
body = re.sub(r"^---\n.*?\n---\n", "", Path(src).read_text(encoding="utf-8"), flags=re.S)
sec = get_section(body, '## Описание полей ЭФ (Вкладка "Реквизиты ГК")', ["## Описание кнопок"])
soup = BeautifulSoup(sec, "html.parser")
for ti, table in enumerate(soup.find_all("table")):
    rows = table.find_all("tr")
    print(f"table {ti} rows {len(rows)}")
    for i, tr in enumerate(rows[:3]):
        print(" ", i, [c.get_text(" ", strip=True)[:40] for c in tr.find_all(["td","th"])])
