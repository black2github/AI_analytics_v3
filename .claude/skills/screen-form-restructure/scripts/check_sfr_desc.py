# -*- coding: utf-8 -*-
from pathlib import Path
import re

root = Path(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus")
sfr = next(root.rglob("*SFR-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"))
text = sfr.read_text(encoding="utf-8")

print("FILE:", sfr)
print("SIZE:", len(text), "mtime:", sfr.stat().st_mtime)

m = re.search(r"(## Описание ЭФ.*?)(?=\n## Обозначения|\n## Поля|\Z)", text, re.S)
if not m:
    print("SECTION NOT FOUND")
    raise SystemExit(1)

sec = m.group(1)
print("SECTION LEN:", len(sec))
print("TABLE tags:", sec.count("<table>"), sec.count("</table>"))
print("Has 'без изменения структуры':", "без изменения структуры" in sec)
print("Has flat **Зачем нужна**:", "**Зачем нужна ЭФ:**" in sec and "<table>" not in sec[:500])
print("\n--- FIRST 2500 chars of section ---\n")
print(sec[:2500])
print("\n--- ... ---\n")
# show where table starts
idx = sec.find("<table>")
print("First <table> at offset:", idx)
if idx >= 0:
    print(sec[idx : idx + 400])
