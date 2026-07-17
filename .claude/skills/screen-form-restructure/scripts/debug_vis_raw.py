#!/usr/bin/env python3
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from restructure_o2plus_clean import *  # noqa: F403,F401
from semantic_field import extract_visibility_raw, visibility_body, clean_visibility_condition

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

names = [
    "Офис обслуживания",
    "Договор банковского счёта",
    "Заключить новый договор",
    "Зарезервированный счёт",
    "Комиссия",
    "Списать со счёта",
    "Статус",
]
lines = []
for f in all_fields:
    if f.name in names:
        vr = extract_visibility_raw(f.comment_raw)
        lines.append(f"=== {f.name} ===")
        lines.append(f"RAW: {vr[:600]}")
        lines.append(f"BODY: {visibility_body(vr)[:600]}")
        lines.append(f"CLEAN: {clean_visibility_condition(vr)[:600]}")
        lines.append("")

Path("debug_vis_raw.txt").write_text("\n".join(lines), encoding="utf-8")
print("written debug_vis_raw.txt")
