# -*- coding: utf-8 -*-
"""Сборка скилла event-driven-screen-form-design в Cursor-rule (лёгкий вариант).
Главное правило .cursor/rules/event-driven-screen-form-design.mdc (Agent Requested)
+ справочники в .cursor/rules/event-driven-screen-form-design/, через @-ссылки.

Запуск (из любого каталога):
  python .claude/skills/event-driven-screen-form-design/build_cursor_rule.py

Источник истины — Claude-скилл (.claude/skills/event-driven-screen-form-design);
.cursor/rules — производное. Не правьте .mdc вручную без переноса в скилл.
"""
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)

SKILL_DIR = ".claude/skills/event-driven-screen-form-design"
REFS = ["templates", "checklist", "usage-examples"]
RULES_DIR = ".cursor/rules"
REF_OUT = ".cursor/rules/event-driven-screen-form-design"
REF_REL = ".cursor/rules/event-driven-screen-form-design"
SFR_REL = ".cursor/rules/screen-form-restructure"
MAIN = os.path.join(RULES_DIR, "event-driven-screen-form-design.mdc")

DESCRIPTION = (
    "Описывает экранную форму (ЭФ) ДБО в событийном формате: реестр полей, "
    "видимость блоков, правила полей (FR-N), события (EV-N) с пошаговыми реакциями "
    "(стабильные ID шагов EV-N.M) и реестр сообщений (MSG-N). Два режима: reverse — "
    "переформатирование существующей страницы ЭФ (Confluence/markdown) в событийную "
    "структуру; forward — проектирование новой ЭФ или нового клиентского пути с нуля "
    "по процессу, модели данных и функциям, с ревью человеком. Применять, когда нужно "
    "описать ЭФ в событийном формате / событийной модели, спроектировать новую "
    "экранную форму или клиентский путь, перевести описание ЭФ на события, привязать "
    "событийную ЭФ к реестру контролей (CTL). Привязка по умолчанию — к готовому "
    "реестру CTL сервиса; конвейер с control-split — только по явному запросу "
    "разделения контролей. Для легаси-формата «единая таблица полей» — "
    "screen-form-restructure; для разделения контролей — control-split (этот скилл "
    "контроли НЕ создаёт, только ссылается)."
)


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n", text, re.S)
        if m:
            return text[m.end() :].lstrip("\n")
    return text


def rewrite_refs(text: str) -> str:
    """Ссылки на локальные references/ и на screen-form-restructure → @-пути Cursor."""
    # Сначала длинный относительный путь (../../), затем короткий (../),
    # иначе фрагмент ../../.. совпал бы с шаблоном ../.
    text = re.sub(
        r"(?:\.\./)+screen-form-restructure/references/([a-z-]+)\.md",
        rf"@{SFR_REL}/\1.md",
        text,
    )
    text = re.sub(r"references/([a-z-]+)\.md", rf"@{REF_REL}/\1.md", text)
    return text


skill_body = rewrite_refs(
    strip_frontmatter(
        open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8").read()
    ).rstrip()
)

parts = [
    "---",
    f"description: {DESCRIPTION}",
    "alwaysApply: false",
    "---",
    "",
    "<!-- Сгенерировано build_cursor_rule.py из "
    ".claude/skills/event-driven-screen-form-design (v1.1). "
    "Правки — в SKILL.md и references/; затем пересоберите скриптом. "
    "Не правьте .mdc вручную без переноса в скилл. -->",
    "",
    "> Справочные материалы вынесены в отдельные файлы и подключены через `@`-ссылки "
    "(см. раздел «Справочные файлы» и пометки «см. @…» по тексту). Cursor подтянет их "
    "как контекст при активации правила. Ссылки на screen-form-restructure ведут в "
    f"`@{SFR_REL}/`.",
    "",
    skill_body,
]

os.makedirs(REF_OUT, exist_ok=True)
os.makedirs(RULES_DIR, exist_ok=True)
content = "\n".join(parts).rstrip() + "\n"
open(MAIN, "w", encoding="utf-8").write(content)

for name in REFS:
    src = os.path.join(SKILL_DIR, "references", f"{name}.md")
    dst = os.path.join(REF_OUT, f"{name}.md")
    ref_text = rewrite_refs(open(src, encoding="utf-8").read())
    open(dst, "w", encoding="utf-8").write(ref_text)

print(
    "main rule:",
    MAIN,
    "|",
    len(content.encode("utf-8")),
    "bytes |",
    content.count("\n") + 1,
    "lines",
)
print("refs ->", REF_OUT)
for name in REFS:
    print("   ", name + ".md")
print("@-ссылок на этот скилл:", skill_body.count("@" + REF_REL))
print("@-ссылок на screen-form-restructure:", skill_body.count("@" + SFR_REL))
