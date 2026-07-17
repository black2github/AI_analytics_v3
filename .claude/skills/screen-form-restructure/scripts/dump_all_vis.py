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
vis, _ = extract_visibility_controls(all_fields, analyses, 1)
lines = [f"{c.id} | {c.title} | {c.condition[:350]}" for c in vis]
Path("all_vis_controls.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"controls: {len(vis)}")
