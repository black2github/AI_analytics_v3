# tests/test_template_samples_guards.py
"""Пакет П2 ОНБ-В, п. 7 (замечания 17 и 51): образцы карточек в шаблонах канона проходят
сторожа классов «форма ветвления» (и «то/иначе» без исхода) и «пометка о пробеле не по
формуле».

Класс «имя в угловых скобках» в тест не входит: образцы шаблонов — в основном заготовки,
где `<название>`, `<ссылка …>` — нотация плейсхолдера шаблона; отличить заготовку от
заполненного образца по форме нельзя (у заготовок тоже числовые ID: DM-000, GLO-001).
Замер 2026-11-07: класс срабатывает на 29 образцах из 36; кандидаты в заполненных
образцах перечислены в отчёте пакета для автора шаблонов.

Образец — блок кода с меткой markdown/md (```markdown, ````markdown, с отступом пункта
списка тоже). Сторожа вызываются на тексте образца напрямую: часть образцов — фрагменты
без шапки (образец ветвления function.md), на них карточная проверка selfcheck не
запускается. Прочие ✗ полного прогона (плейсхолдеры `<…>` в шапке, ссылки на соседей,
которых в образце нет) — по построению образца, тест их не проверяет.

Шаблоны читаются через git из `origin/master` клона канона (`CANON_ROOT`, по умолчанию
C:\\doc-as-code\\EAN\\docs-o2new); без клона — skip с причиной. Падение — сигнал автору
шаблона, а не причина менять сторож. Находки на шаблонах среза приёмки пакета записаны в
KNOWN: такая запись не валит тест, пока воспроизводится, и валит, когда исчезла (запись
снимается вместе с правкой шаблона); новая находка валит тест сразу."""
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from app.scripts.CI.kitcheck.checks.card_branch_form import (branch_form_offenders,
                                                              branch_no_outcome)
from app.scripts.CI.kitcheck.checks.content import check_source_silent

from tests.test_required_sections_templates import _canon_templates

_BLOCK_RE = re.compile(r"^([ \t]*)(`{3,})(?:markdown|md)[^\n`]*\n(.*?)^[ \t]*\2[ \t]*$",
                       re.M | re.S)

# (шаблон, класс) — находки на срезе канона приёмки пакета (origin/master 60d3512, 2026-11-07);
# правит автор шаблона отдельной волной, запись снимается вместе с правкой
# четыре находки 07.11 (agent, process, screen-form — форма ветвления; data-model — пометка не
# по формуле) исправлены в шаблонах канона (master 07a3c5d) и сняты
KNOWN: Set[Tuple[str, str]] = set()


def samples(text: str) -> List[str]:
    """Образцы шаблона: тело блока с меткой markdown/md, отступ блока снят."""
    out = []
    for m in _BLOCK_RE.finditer(text):
        ind = len(m.group(1))
        out.append("\n".join(ln[ind:] if ln[:ind].strip() == "" else ln
                             for ln in m.group(3).split("\n")))
    return out


def findings(name: str, sample: str, tmp: Path) -> Set[str]:
    """Классы находок трёх сторожей на одном образце."""
    lines = sample.splitlines()
    got: Set[str] = set()
    if branch_form_offenders(lines) or branch_no_outcome(lines):
        got.add("форма ветвления")
    kit = tmp / re.sub(r"\W", "_", name)
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "sample.md").write_text(sample, encoding="utf-8")
    if any("не по формуле" in x for x in check_source_silent(kit)):
        got.add("пометка не по формуле")
    return got


def collect(templates: Dict[str, str], tmp: Path) -> Dict[Tuple[str, str], List[int]]:
    found: Dict[Tuple[str, str], List[int]] = {}
    for name, text in sorted(templates.items()):
        for i, s in enumerate(samples(text), 1):
            for cls in findings(f"{name}-{i}", s, tmp):
                found.setdefault((Path(name).name, cls), []).append(i)
    return found


# ------------------------------------------------------------ логика (без канона)


def test_samples_extraction_forms():
    t = ("Текст\n\n```markdown\n# A\n```\n\n- пункт:\n\n  ```md\n  - **1)** шаг\n  ```\n\n"
         "````markdown\n```\nкод\n```\n````\n\n```yaml\nk: v\n```\n")
    s = samples(t)
    assert s == ["# A\n", "- **1)** шаг\n", "```\nкод\n```\n"], s


def test_findings_catch_each_class(tmp_path):
    # «иначе» не со своей строки (notation §1)
    bad_branch = "- **1)** **Если** X, **то** Y, **иначе** Z\n"
    assert "форма ветвления" in findings("b", bad_branch, tmp_path)
    assert "пометка не по формуле" in findings("g", "Поле: не задано.\n", tmp_path)
    # плейсхолдер шаблона — не находка теста (класс угловых имён не входит)
    assert findings("a", "Значение <название> поля.\n", tmp_path) == set()


def test_findings_silent_on_clean_sample(tmp_path):
    ok = ("- **1)** **Если** «Тип» == \"Критичное\", **то:**\n  - **1.1)** Разместить\n"
          "- **иначе:**\n  - **1.2)** Отказ\n\nПоле — в постановке не задано.\n")
    assert findings("ok", ok, tmp_path) == set()


# ------------------------------------------------------------ живой канон


def test_canon_template_samples_pass_guards(tmp_path):
    found = collect(_canon_templates(), tmp_path)
    new = {k: v for k, v in found.items() if k not in KNOWN}
    gone = KNOWN - set(found)
    assert not new, "образцы шаблонов не проходят сторожа (сигнал автору шаблона): " + "; ".join(
        f"{t}: {c} (образцы {v})" for (t, c), v in sorted(new.items()))
    assert not gone, ("находка из KNOWN больше не воспроизводится — снять запись: "
                      + "; ".join(f"{t}: {c}" for t, c in sorted(gone)))
