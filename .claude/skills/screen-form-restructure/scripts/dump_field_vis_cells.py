#!/usr/bin/env python3
import glob, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from restructure_o2plus_clean import *

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
names = ["Офис обслуживания","Валюта","Договор банковского счёта","Зарезервированный счёт","Использовать карточку ОПОП, ранее предоставленную к счёту","Комиссия","Списать со счёта","Наименование ЭФ","Место заключения Договора","Комиссию за открытие списать со счёта"]
lines = []
for f in all_fields:
    if f.name in names:
        a = analyses[field_key(f)]
        lines.append(f"{f.num} | {f.name}")
        lines.append(f"  vis cell: {a.visibility[:200]}")
        lines.append(f"  control:  {a.visibility_control_text[:200]}")
        lines.append("")
Path("field_vis_cells.txt").write_text("\n".join(lines), encoding="utf-8")
