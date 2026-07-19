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
    ("Открываемый счёт", '## Описание ЭФ "Открываемый счёт" основная часть'),
    ("Реквизиты ГК", '## Описание полей ЭФ (Вкладка "Реквизиты ГК")'),
    ("Подтверждение", '## Описание полей ЭФ (Вкладка "Подтверждение")'),
]:
    sec = get_section(body, marker, ["## Описание кнопок"])
    table = find_field_table(sec)
    if table:
        all_fields.extend(extract_fields_from_table(table, tab))

analyses = build_field_analyses(all_fields)
vis, _ = extract_visibility_controls(all_fields, analyses, 1)
lines = []
for c in vis:
    if c.id in ("SF-02", "SF-03", "SF-04", "SF-05", "SF-06", "SF-07", "SF-08", "SF-09"):
        lines.append(f"{c.id} | {c.title}")
        lines.append(c.condition[:500])
        lines.append("---")
Path("vis_conditions_check.txt").write_text("\n".join(lines), encoding="utf-8")
