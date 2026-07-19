# -*- coding: utf-8 -*-
from pathlib import Path
import re

root = Path(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus")
candidates = list(root.rglob("*ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"))
src = next(p for p in candidates if "SFR" not in p.name and "FE-Контроли" not in p.name)
sfr = next(root.rglob("*SFR-ЭФ-Клиента-Открытие-доп-счета-и-заключение-ДБС-в-режиме-редактирования.md"))

out = Path(__file__).resolve().parents[4] / "inspect_ef_desc_out.txt"
lines: list[str] = []
for label, p in [("SRC", src), ("SFR", sfr)]:
    text = p.read_text(encoding="utf-8")
    lines.append("=" * 60)
    lines.append(f"{label} {p.name}")
    if label == "SRC":
        m = re.search(r"(# Общие требования к ЭФ.*?)(?=\n# Вкладка|\Z)", text, re.S)
        chunk = m.group(1) if m else "(not found)"
    else:
        m = re.search(r"(## Описание ЭФ.*?)(?=\n## Обозначения|\Z)", text, re.S)
        chunk = m.group(1) if m else "(not found)"
    lines.append(chunk[:2000] + ("...[truncated]..." if len(chunk) > 2000 else ""))
    lines.append("")

# also dump table tags count
for label, p in [("SRC", src), ("SFR", sfr)]:
    text = p.read_text(encoding="utf-8")
    if label == "SRC":
        m = re.search(r"# Общие требования к ЭФ(.*)", text, re.S)
        sec = m.group(1) if m else ""
    else:
        m = re.search(r"## Описание ЭФ(.*)", text, re.S)
        sec = m.group(1) if m else ""
    lines.append(f"--- {label} stats: <table> count={sec.count('<table>')}, markdown | rows={sec.count(chr(10)+'|')} ---")

out.write_text("\n".join(lines), encoding="utf-8")
print(out)
