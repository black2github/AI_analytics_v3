# -*- coding: utf-8 -*-
import re
from pathlib import Path

root = Path(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus")
src = next(
    p
    for p in root.rglob("*ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md")
    if "SFR" not in p.name and "FE" not in p.name and "Контроли" not in p.name
)
sfr = next(
    p
    for p in root.rglob("*SFR*ЭФ*Открытие*редактирования.md")
    if "FE" not in p.name and "\u041e2+NEW" in p.name  # Cyrillic О
)

for label, p in [("SRC", src), ("SFR", sfr)]:
    t = p.read_text(encoding="utf-8")
    i = t.find("Дополнительные действия")
    chunk = t[i : i + 3000]
    print("===", label, p.name, "===")
    print("<strong>Шаг:", chunk.count("<strong>Шаг"))
    print("plain Шаг N):", len(re.findall(r"Шаг \d", chunk)))
    print("**Шаг:", chunk.count("**Шаг"))
    m = re.search(r"(Шаг 1\)[^<]{0,200}|Шаг 1\)<[^>]+>[^<]{0,100})", chunk)
    print("sample:", (m.group(0)[:250] if m else "n/a"))
    print()
