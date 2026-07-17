#!/usr/bin/env python3
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from restructure_o2plus_clean import *  # noqa: F403,F401

src = [p for p in glob.glob(SRC_GLOB, recursive=True) if "SFR" not in p and "FE-" not in p][0]
_, body = parse_frontmatter(Path(src).read_text(encoding="utf-8"))
tab_sections = {
    "Открываемый счёт": get_section(
        body,
        '## Описание ЭФ "Открываемый счёт" основная часть',
        ["## Описание кнопок"],
    ),
    "Реквизиты ГК": get_section(
        body,
        '## Описание полей ЭФ (Вкладка "Реквизиты ГК")',
        ["## Описание кнопок"],
    ),
    "Подтверждение": get_section(
        body,
        '## Описание полей ЭФ (Вкладка "Подтверждение")',
        ["## Описание кнопок"],
    ),
}
all_fields = []
for tab, sec in tab_sections.items():
    table = find_field_table(sec)
    if table:
        all_fields.extend(extract_fields_from_table(table, tab))

analyses = build_field_analyses(all_fields)
for f in all_fields:
    if f.name == "Организация":
        a = analyses[field_key(f)]
        print(f"{f.tab} | {f.num} | extract={a.visibility_extract} | vis={a.visibility[:50]} | type={a.ui_type}")

vis, sf_map = extract_visibility_controls(all_fields, analyses, 1)
print("sf_map['Организация']:", sf_map.get("Организация"))
for c in vis:
    if "Организация" in c.title:
        print("CTRL:", c.id, c.orig, c.title)
