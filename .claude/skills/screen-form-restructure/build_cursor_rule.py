# -*- coding: utf-8 -*-
"""Сборка скилла screen-form-restructure в Cursor-rule (лёгкий вариант).
Главное правило .cursor/rules/screen-form-restructure.mdc (Agent Requested) + справочники
отдельными файлами в .cursor/rules/screen-form-restructure/, подключённые через @-ссылки.

Запуск (из любого каталога): python .claude/skills/screen-form-restructure/build_cursor_rule.py

ВНИМАНИЕ: с v3.1 Cursor-ветка и Claude-скилл синхронизированы. build_cursor_rule.py
копирует references из .claude/skills → .cursor/rules; не перезаписывать .mdc
вручную без переноса правок в SKILL.md и references/.
"""
import os, re, shutil
from pathlib import Path

# корень проекта = на 3 уровня выше этого файла (screen-form-restructure -> skills -> .claude -> ROOT)
ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)

SKILL_DIR = ".claude/skills/screen-form-restructure"
REFS = [
    "controls",
    "categories",
    "field-table",
    "formatting",
    "type-dictionary",
    "templates",
    "parsing",
    "naming",
    "checklist",
]
RULES_DIR = ".cursor/rules"
REF_OUT = ".cursor/rules/screen-form-restructure"
REF_REL = ".cursor/rules/screen-form-restructure"
MAIN = os.path.join(RULES_DIR, "screen-form-restructure.mdc")

DESCRIPTION = (
    "Переформатирует описание экранной формы (ЭФ) ДБО к целевому виду Doc as Code / API First "
    "и выделяет проверки: единая таблица полей (Тип / Формат / Способ заполнения / Обязательность / "
    "Видимость / Логика установки значения), парный FE-документ контролей (rule/visibility, R/V). "
    "Применять, когда дана страница экранной формы (описание полей, форматов, логики показа, умолчаний) "
    "и нужно привести к целевой структуре, выделить контроли, разметить видимость или мигрировать ЭФ "
    "из Confluence. Для чистого разделения готового файла контролей — control-split."
)


def strip_frontmatter(text):
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n", text, re.S)
        if m:
            return text[m.end() :].lstrip("\n")
    return text


# тело SKILL.md без YAML-шапки; ссылки references/<имя>.md -> живые @-ссылки
skill_body = strip_frontmatter(
    open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8").read()
).rstrip()


def to_at(m):
    return f"@{REF_REL}/{m.group(1)}.md"


skill_body = re.sub(r"references/([a-z-]+)\.md", to_at, skill_body)

parts = []
parts.append("---")
parts.append(f"description: {DESCRIPTION}")
parts.append("alwaysApply: false")
parts.append("---")
parts.append("")
parts.append(
    "<!-- Сгенерировано build_cursor_rule.py из .claude/skills/screen-form-restructure (v3.1). "
    "Правки — в SKILL.md и references/; затем пересоберите скриптом. "
    "Не правьте .mdc вручную без переноса в скилл. -->"
)
parts.append("")
parts.append(
    "> Справочные материалы вынесены в отдельные файлы и подключены через `@`-ссылки "
    "(см. раздел «Справочные файлы» и пометки «см. @…» по тексту). Cursor подтянет их "
    "как контекст при активации правила."
)
parts.append("")
parts.append(skill_body)

os.makedirs(REF_OUT, exist_ok=True)
content = "\n".join(parts).rstrip() + "\n"
os.makedirs(RULES_DIR, exist_ok=True)
open(MAIN, "w", encoding="utf-8").write(content)

# справочники — копируем как есть (.md, не .mdc: Cursor не примет их за правила)
for name in REFS:
    src = os.path.join(SKILL_DIR, "references", f"{name}.md")
    dst = os.path.join(REF_OUT, f"{name}.md")
    shutil.copyfile(src, dst)

print("main rule:", MAIN, "|", len(content.encode("utf-8")), "bytes |", content.count(chr(10)) + 1, "lines")
print("refs ->", REF_OUT)
for name in REFS:
    print("   ", name + ".md")
print("@-ссылок в главном правиле:", skill_body.count("@" + REF_REL))
