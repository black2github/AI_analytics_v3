#!/usr/bin/env python3
"""Audit all fields: raw comment visibility vs cleaned condition."""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from restructure_o2plus_clean import *  # noqa: F403,F401
from semantic_field import (
    extract_visibility_raw,
    visibility_body,
    clean_visibility_condition,
    should_extract_visibility,
    split_sections_from_blobs,
)

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
ctrl_by_name = {c.title.replace("Видимость «", "").rstrip("»"): c for c in vis}

lines = []
for f in all_fields:
    a = analyses.get(field_key(f))
    if not a:
        continue
    vr = extract_visibility_raw(f.comment_raw)
    if not vr and not a.visibility_extract:
        continue
    sections, _ = split_sections_from_blobs(f.comment_raw, f.fill_raw)
    sec_axes = {k: " | ".join(v)[:120] for k, v in sections.items()}
    ctrl = ctrl_by_name.get(f.name)
    flag = []
    clean = a.visibility_control_text
    if re.search(r"(?i)отображение на эф\s*:|видимость\s*:|поле отображается на эф", clean):
        flag.append("PREFIX")
    if re.search(r"(?i)предзаполнение|выбор из списка|формат отображения|логика вычисления|поле заполняется|текст по правилу|доступность других", clean):
        flag.append("TAIL")
    if re.search(r'(?i)="г\."\s*\+|не пусто=', clean):
        flag.append("FORMAT_IN_VIS")
    if re.search(r"(?i)описаны в (поле|блоке)", clean):
        flag.append("REF_NOT_COND")
    if a.visibility_extract and not re.search(r"(?i)\bесли\b", clean) and "всегда" not in clean.lower():
        flag.append("NO_IF")
    if flag or a.visibility_extract:
        lines.append(f"{'EXTRACT' if a.visibility_extract else 'SKIP'} | {f.num} | {f.name} | flags={','.join(flag) or '-'}")
        if ctrl:
            lines.append(f"  SF: {ctrl.id} | {clean[:300]}")
        lines.append(f"  RAW vis: {vr[:250]}")
        lines.append(f"  sections: {sec_axes}")
        lines.append("")

Path("vis_full_audit.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"lines={len(lines)}")
