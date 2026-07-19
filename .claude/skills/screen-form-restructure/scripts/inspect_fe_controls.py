# -*- coding: utf-8 -*-
import re
from pathlib import Path

root = Path(r"C:\doc-as-code\AI-docs-O2new\sources\confluence.int\o2plus")
files = sorted(
    [p for p in root.rglob("*SFR-FE*Открытие*редактирования.md")],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
out = Path(__file__).resolve().parents[4] / "inspect_fe_controls_out.txt"
lines = []
for p in files:
    t = p.read_text(encoding="utf-8")
    lines.append("=" * 80)
    lines.append(str(p))
    lines.append(f"size={p.stat().st_size} prefix_hex={p.name[:12].encode('utf-8').hex()}")
    # find controls table section
    for marker in ["## Контроли", "## Контроли формы", "| ID |", "<table>"]:
        idx = t.find(marker)
        if idx >= 0:
            lines.append(f"  found {marker!r} at {idx}")
    chunk = t[t.find("## Контроли"): t.find("## Контроли") + 4000] if "## Контроли" in t else t[-4000:]
    lines.append(f"  <table> count in chunk: {chunk.count('<table>')}")
    lines.append(f"  pipe rows (| at line start): {sum(1 for ln in chunk.splitlines() if ln.strip().startswith('|'))}")
    lines.append(f"  separator row |---|: {'|---|' in chunk or '|----' in chunk}")
    lines.append("--- first 120 lines from ## Контроли ---")
    if "## Контроли" in t:
        start = t.find("## Контроли")
        lines.extend(t[start:start+3500].splitlines()[:80])
    lines.append("")

out.write_text("\n".join(lines), encoding="utf-8")
print(out)
