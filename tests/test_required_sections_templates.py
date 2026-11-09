# tests/test_required_sections_templates.py
"""Пакет П2 ОНБ-В, п. 2 (замечание 47): обязательные разделы печатной формы и паспорта
границы части вне контура Экосистемы (module-passport; тесты паспорта — в
test_outside_eco_part.py); страж «словарь прибора равен пометкам «(обязательный)» шаблонов
канона».

Страж на живом каноне читает шаблоны через git из `origin/master` клона канона
(`CANON_ROOT`, по умолчанию C:\\doc-as-code\\EAN\\docs-o2new); без клона — skip с
причиной. Логика стража проверяется синтетикой и без канона."""
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

import pytest

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.checks import content as c
from app.scripts.CI.kitcheck.md import code_line_flags

_CANON = Path(os.environ.get("CANON_ROOT", r"C:\doc-as-code\EAN\docs-o2new"))


def template_required(text: str) -> Tuple[Optional[str], Tuple[str, ...]]:
    """(type из схемы шапки шаблона, разделы с пометкой ровно «(обязательный)»).
    «обязательный, если …» — условный раздел, в перечень не входит; заголовки
    внутри блоков кода (образцы карточек) — не разделы шаблона."""
    lines = text.splitlines()
    req = []
    for ln, code in zip(lines, code_line_flags(lines)):
        if code or not re.match(r"^#{2,4}\s", ln):
            continue
        m = re.search(r"\(([^()]*)\)\s*$", ln)
        if m and m.group(1).strip().lower() == "обязательный":
            req.append(c._section_key(ln))
    tm = re.search(r"^type:\s*([\w-]+)", text, re.M)
    return (tm.group(1) if tm else None), tuple(req)


def guard(templates: Dict[str, str]) -> list:
    """Расхождения словаря прибора с пометками шаблонов (пусто — совпадает)."""
    bad = []
    for name, text in sorted(templates.items()):
        typ, req = template_required(text)
        if not req:
            continue
        have = c._REQ_SECTIONS.get(typ or "")
        if have != req:
            bad.append(f"{name}: type={typ}, шаблон {req}, словарь {have}")
        elif typ not in c._KNOWN_SECTIONS:
            bad.append(f"{name}: type={typ} нет в _KNOWN_SECTIONS")
    return bad


# ------------------------------------------------------------ логика стража


def test_guard_catches_template_without_dictionary_row():
    tpl = ("```yaml\n---\ntype: brand-new\n---\n```\n\n## Структура\n\n"
           "### 1. Назначение (обязательный)\n\nт\n\n### 2. Детали (обязательный, если есть)\n")
    assert guard({"brand-new.md": tpl}) == [
        "brand-new.md: type=brand-new, шаблон ('назначение',), словарь None"]


def test_guard_silent_on_matching_and_conditional_only_templates():
    tpl = ("```yaml\n---\ntype: print-form\n---\n```\n"
           "### 1. Назначение и использование (обязательный)\n### 2. Файл печатной формы (обязательный)\n"
           "### 3. Макет (обязательный)\n### 4. Правила заполнения (обязательный)\n"
           "### 5. Штамп ЭП Клиента (для подписываемых форм)\n"
           "````markdown\n## 1. Назначение (обязательный)\n````\n")
    only_cond = "```yaml\n---\ntype: vision\n---\n```\n## Условия доступности (обязательный, если есть)\n"
    assert guard({"print-form.md": tpl, "service-vision.md": only_cond}) == []


def test_guard_catches_changed_template_list():
    tpl = ("```yaml\n---\ntype: print-form\n---\n```\n"
           "### 1. Назначение и использование (обязательный)\n### 3. Макет (обязательный)\n")
    assert len(guard({"print-form.md": tpl})) == 1


# ------------------------------------------------------------ живой канон


def _canon_templates() -> Dict[str, str]:
    def git(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(_CANON), *a], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    if not (_CANON / ".git").exists():
        pytest.skip(f"клона канона нет ({_CANON}; путь задаётся CANON_ROOT) — "
                    "страж по живым шаблонам не выполнен")
    ls = git("ls-tree", "--name-only", "origin/master", "_meta/templates/")
    if ls.returncode != 0:
        pytest.skip(f"в клоне канона {_CANON} нет origin/master — страж не выполнен")
    return {n: git("show", f"origin/master:{n}").stdout
            for n in ls.stdout.splitlines() if n.endswith(".md")}


def test_dictionary_equals_canon_template_marks():
    templates = _canon_templates()
    assert any(template_required(t)[1] for t in templates.values()), \
        "в шаблонах канона не найдено ни одной пометки «(обязательный)»"
    assert guard(templates) == []


# ------------------------------------------------------------ сторож разделов


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fm(i: str, t: str) -> str:
    return f"---\nid: {i}\ntype: {t}\nservice: x\n---\n\n# Заголовок\n\n"


def test_print_form_missing_layout_warned_registry_readme_skipped(tmp_path):
    docs = tmp_path / "docs"
    w(docs / "srs/print-form/prn-01-report.md", fm("PRN-01", "print-form")
      + "## 1. Назначение и использование\n\nт\n\n## 2. Файл печатной формы\n\nт\n\n"
      "## 4. Правила заполнения\n\nт\n\n## 5. Штамп ЭП Клиента\n\nт\n")
    w(docs / "srs/print-form/README.md", fm("PRN-000", "print-form") + "## Реестр ПФ\n\nт\n")
    rep = sc.check_required_sections(docs)
    assert rep and "единиц 1" in rep[0], rep
    assert "prn-01-report.md [print-form]: «Макет»" in rep[1], rep
    assert not any("вне шаблона" in x for x in rep), rep
