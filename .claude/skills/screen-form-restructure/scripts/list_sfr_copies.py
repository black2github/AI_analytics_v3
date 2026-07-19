# -*- coding: utf-8 -*-
from pathlib import Path

root = Path(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus")
files = list(root.rglob("*SFR*ЭФ*Открытие*редактирования.md"))
files = [p for p in files if "FE" not in p.name and "Контроли" not in p.name]
for p in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
    rel = p.relative_to(root)
    t = p.read_text(encoding="utf-8")
    i = t.find("## Описание ЭФ")
    sec = t[i : i + 500] if i >= 0 else ""
    print(rel)
    print("  name repr:", repr(p.name[:60]))
    print("  parent repr:", repr(p.parent.name[:60]))
    print("  size:", p.stat().st_size, "tables:", sec.count("<table>"), "flat:", "**Зачем" in sec and "<table>" not in sec)
    print()
