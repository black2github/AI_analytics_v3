# -*- coding: utf-8 -*-
"""Сборка скилла control-split в Cursor-rule (лёгкий вариант).
Главное правило .cursor/rules/control-split.mdc (Agent Requested) + справочники
отдельными файлами в .cursor/rules/control-split/, подключённые через @-ссылки.

Запуск (из любого каталога): python .claude/skills/control-split/build_cursor_rule.py
Источник истины — сам скилл (.claude/skills/control-split); .cursor/rules — производное."""
import os, re, shutil
from pathlib import Path

# корень проекта = на 3 уровня выше этого файла (control-split -> skills -> .claude -> ROOT)
ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)

SKILL_DIR = ".claude/skills/control-split"
REFS = ["classification","multi-entity","formatting","templates","edge-cases","checklist"]
RULES_DIR = ".cursor/rules"
REF_OUT = ".cursor/rules/control-split"          # подпапка со справочниками
REF_REL = ".cursor/rules/control-split"          # путь для @-ссылок (от корня проекта)
MAIN = os.path.join(RULES_DIR, "control-split.mdc")

DESCRIPTION = ("Разделение единого документа контролей (проверок) ДБО на документы проверок "
 "экранных форм (screen-form, Зона 3) и сущностей модели данных (data-model, Зона 1) "
 "для API First / Doc as Code. Применять, когда дан документ контролей заявки "
 "(единая таблица с группами триггеров и матрицей «V») и нужно разнести фронтовые/бэковые "
 "проверки по объекту, присвоить стабильные ID (SF-/DM-), разметить x-controls или "
 "мигрировать страницу контролей из Confluence.")

def strip_frontmatter(text):
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n", text, re.S)
        if m:
            return text[m.end():].lstrip("\n")
    return text

# тело SKILL.md без YAML-шапки; ссылки references/<имя>.md -> живые @-ссылки
skill_body = strip_frontmatter(open(os.path.join(SKILL_DIR,"SKILL.md"),encoding="utf-8").read()).rstrip()
def to_at(m):
    return f"@{REF_REL}/{m.group(1)}.md"
SHARED_SRC = ".claude/skills/_shared"
SHARED_OUT = ".cursor/rules/_shared"
def rewrite_shared(text):
    """Ссылки на общее ядро ../_shared/ (любая глубина) -> @-пути Cursor."""
    return re.sub(r"(?:\.\./)+_shared/([a-z-]+)\.md", rf"@{SHARED_OUT}/\1.md", text)
skill_body = rewrite_shared(re.sub(r"references/([a-z-]+)\.md", to_at, skill_body))

parts = []
parts.append("---")
parts.append(f"description: {DESCRIPTION}")
parts.append("alwaysApply: false")
parts.append("---")
parts.append("")
parts.append("<!-- Сгенерировано из .claude/skills/control-split (build_cursor_rule.py). "
             "Источник истины — Claude-скилл; при правках меняйте его и пересобирайте. -->")
parts.append("")
parts.append("> Справочные материалы вынесены в отдельные файлы и подключены через `@`-ссылки "
             "(см. раздел «Справочные файлы» и пометки «см. @…» по тексту). Cursor подтянет их "
             "как контекст при активации правила.")
parts.append("")
parts.append(skill_body)

os.makedirs(REF_OUT, exist_ok=True)
content = "\n".join(parts).rstrip()+"\n"
os.makedirs(RULES_DIR, exist_ok=True)
open(MAIN,"w",encoding="utf-8").write(content)

# справочники — копируем с переписыванием ссылок на общее ядро
for name in REFS:
    src = os.path.join(SKILL_DIR,"references",f"{name}.md")
    dst = os.path.join(REF_OUT,f"{name}.md")
    open(dst,"w",encoding="utf-8").write(rewrite_shared(open(src,encoding="utf-8").read()))

# общее ядро _shared — копируем в зеркало (идемпотентно; генераторы других
# скиллов делают то же самое)
os.makedirs(SHARED_OUT, exist_ok=True)
for f in sorted(os.listdir(SHARED_SRC)):
    if f.endswith(".md"):
        shutil.copyfile(os.path.join(SHARED_SRC, f), os.path.join(SHARED_OUT, f))

print("main rule:", MAIN, "|", len(content.encode("utf-8")), "bytes |", content.count(chr(10))+1, "lines")
print("refs ->", REF_OUT)
for name in REFS:
    print("   ", name+".md")
print("shared ->", SHARED_OUT)
print("@-ссылок в главном правиле:", skill_body.count("@"+REF_REL))
