#!/usr/bin/env python3
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from restructure_o2plus_clean import *  # noqa: F403,F401

src = [p for p in glob.glob(SRC_GLOB, recursive=True) if "SFR" not in p and "FE-" not in p][0]
_, body = parse_frontmatter(Path(src).read_text(encoding="utf-8"))
all_fields = []
for tab, marker in [
    ("x", '## Описание ЭФ "Открываемый счёт" основная часть'),
    ("x", '## Описание полей ЭФ (Вкладка "Реквизиты ГК")'),
    ("x", '## Описание полей ЭФ (Вкладка "Подтверждение")'),
]:
    sec = get_section(body, marker, ["## Описание кнопок"])
    table = find_field_table(sec)
    if table:
        all_fields.extend(extract_fields_from_table(table, tab))

analyses = build_field_analyses(all_fields)
lines = []
for f in all_fields:
    a = analyses.get(field_key(f))
    if a and a.visibility_extract:
        lines.append(f"EXTRACT | {f.num} | {f.name} | {a.visibility_control_text[:200]}")
    elif a and a.visibility_control_text:
        lines.append(f"SKIP? | {f.num} | {f.name} | vis={a.visibility} | {a.visibility_control_text[:120]}")
Path("vis_extract_audit.txt").write_text("\n".join(lines), encoding="utf-8")
print("written")
