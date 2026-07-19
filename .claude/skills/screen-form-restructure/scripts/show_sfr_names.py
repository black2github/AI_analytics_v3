# -*- coding: utf-8 -*-
from pathlib import Path

parent = next(
    p.parent
    for p in Path(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus").rglob(
        "*SFR*ЭФ*Открытие*редактирования.md"
    )
    if "FE" not in p.name
)
print("DIR:", parent)
for p in sorted(parent.iterdir()):
    if "SFR" in p.name and "ЭФ" in p.name and p.suffix == ".md":
        print()
        print("NAME:", p.name)
        print("HEX prefix:", p.name[:20].encode("utf-8").hex())
        print("size:", p.stat().st_size)
        t = p.read_text(encoding="utf-8")
        i = t.find("## Описание ЭФ")
        sec = t[i : i + 300] if i >= 0 else ""
        print("table:", "<table>" in sec, "flat:", "**Зачем нужна ЭФ:**" in sec)
