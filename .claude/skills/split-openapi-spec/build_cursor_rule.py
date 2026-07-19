# -*- coding: utf-8 -*-
"""Сборка скилла split-openapi-spec в Cursor-rule (лёгкий вариант).
Главное правило .cursor/rules/split-openapi-spec.mdc (Agent Requested) + справочник
в .cursor/rules/split-openapi-spec/, подключённый через @-ссылку.

Скрипты (split_spec.py, verify_roundtrip.py, domains.example.json) остаются
в .claude/skills/split-openapi-spec/scripts/ — Cursor-правило ссылается на них
напрямую; дублировать не нужно.

Запуск (из любого каталога): python .claude/skills/split-openapi-spec/build_cursor_rule.py
Источник истины — сам скилл (.claude/skills/split-openapi-spec); .cursor/rules — производное."""
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)

SKILL_DIR = ".claude/skills/split-openapi-spec"
REFS = ["approach"]
RULES_DIR = ".cursor/rules"
REF_OUT = ".cursor/rules/split-openapi-spec"
REF_REL = ".cursor/rules/split-openapi-spec"
MAIN = os.path.join(RULES_DIR, "split-openapi-spec.mdc")
SCRIPTS_REL = ".claude/skills/split-openapi-spec/scripts"

DESCRIPTION = (
    "Разбивает большой OpenAPI-файл (JSON/YAML) на доменные папки для анализа и правки "
    "и собирает обратно через redocly bundle без изменения спецификации (round-trip структурно "
    "идентичен исходнику). Применять, когда спека слишком большая для LLM/командной работы, "
    "нужен доменный сплит paths/schemas, либо bundle + проверка эквивалентности "
    "(verify_roundtrip)."
)


def strip_frontmatter(text):
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n", text, re.S)
        if m:
            return text[m.end() :].lstrip("\n")
    return text


skill_body = strip_frontmatter(
    open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8").read()
).rstrip()

# reference/approach.md -> @-ссылка Cursor
skill_body = re.sub(
    r"`?reference/([a-z0-9-]+)\.md`?",
    lambda m: f"@{REF_REL}/{m.group(1)}.md",
    skill_body,
)

# Уже абсолютные пути к скриптам оставляем; относительные scripts/ -> полный путь от корня
skill_body = re.sub(
    r"(?<![./\w])scripts/(split_spec\.py|verify_roundtrip\.py|domains\.example\.json)",
    rf"{SCRIPTS_REL}/\1",
    skill_body,
)

parts = []
parts.append("---")
parts.append(f"description: {DESCRIPTION}")
parts.append("alwaysApply: false")
parts.append("---")
parts.append("")
parts.append(
    "<!-- Сгенерировано из .claude/skills/split-openapi-spec (build_cursor_rule.py). "
    "Источник истины — Claude-скилл; при правках меняйте его и пересобирайте. -->"
)
parts.append("")
parts.append(
    "> Справочные материалы подключены через `@`-ссылки. Исполняемые скрипты "
    f"живут в `{SCRIPTS_REL}/` (не дублируются в `.cursor/rules`)."
)
parts.append("")
parts.append(skill_body)
parts.append("")
parts.append("## Справочные файлы")
parts.append("")
parts.append(
    f"- `@{REF_REL}/approach.md` — обоснование доменного сплита, common vs "
    "domain schemas, $ref и композиция через allOf."
)
parts.append("")
parts.append("## Скрипты")
parts.append("")
parts.append(f"- `{SCRIPTS_REL}/split_spec.py` — доменный сплиттер OpenAPI.")
parts.append(f"- `{SCRIPTS_REL}/verify_roundtrip.py` — проверка структурной эквивалентности.")
parts.append(f"- `{SCRIPTS_REL}/domains.example.json` — пример маппинга path → домен.")

os.makedirs(REF_OUT, exist_ok=True)
content = "\n".join(parts).rstrip() + "\n"
os.makedirs(RULES_DIR, exist_ok=True)
open(MAIN, "w", encoding="utf-8").write(content)

# Справочник: в Claude-скилле лежит в reference/ (ед.ч.)
for name in REFS:
    src = os.path.join(SKILL_DIR, "reference", f"{name}.md")
    dst = os.path.join(REF_OUT, f"{name}.md")
    shutil.copyfile(src, dst)

print("main rule:", MAIN, "|", len(content.encode("utf-8")), "bytes |", content.count("\n") + 1, "lines")
print("refs ->", REF_OUT)
for name in REFS:
    print("   ", name + ".md")
print("scripts remain at:", SCRIPTS_REL)
print("@-ссылок в главном правиле:", skill_body.count("@" + REF_REL))
