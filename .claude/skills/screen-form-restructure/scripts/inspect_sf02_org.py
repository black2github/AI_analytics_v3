#!/usr/bin/env python3
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from restructure_o2plus_clean import SRC_GLOB, build_field_analyses, extract_fields_from_table, find_field_table, get_section, parse_frontmatter
from semantic_field import analyze_field

src = [p for p in glob.glob(SRC_GLOB, recursive=True) if "SFR" not in p and "FE-" not in p][0]
text = Path(src).read_text(encoding="utf-8")
_, body = parse_frontmatter(text)
sec = get_section(body, '## Описание ЭФ "Открываемый счёт" основная часть', ["## Описание кнопок"])
table = find_field_table(sec)
fields = extract_fields_from_table(table, "Открываемый счёт")
for f in fields:
    if f.name != "Организация":
        continue
    a = analyze_field(
        name=f.name,
        ui_type=f.ui_type,
        fill_raw=f.fill_raw,
        required_raw=f.required_raw,
        comment_raw=f.comment_raw,
    )
    print("FIELD:", f.name)
    print("  type:", a.ui_type)
    print("  visibility:", a.visibility[:80])
    print("  extract:", a.visibility_extract)
    print("  fill:", a.fill_mode[:100])
    print("  fmt:", a.fmt[:100])
    print("  logic start:", a.logic[:120].replace("\n", " "))
