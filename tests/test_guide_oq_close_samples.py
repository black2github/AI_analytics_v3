# tests/test_guide_oq_close_samples.py
"""Волна Д ОНБ-В, срез 3 (решение владельца 2026-11-09): образцы строк записи OQ из гида
миграции канона проходят сторож формы закрытия.

Норма закрытия записи OQ живёт в техбуке (conventions §6, пп. 7–8); в гиде канона
(`_meta/migration/reference.md`, пункт «Вопросы агентов к источнику…») — рабочая выжимка с
указанием дома, осознанная локальная копия. Тест держит копию и сторож вместе: из пункта
гида вырезаются code-span с образцами (две формы заголовка, две строки закрытия,
промежуточные «ответ получен …»), угловые плейсхолдеры подставляются образцовыми значениями,
из образцов собирается временный `open-questions.md`. Ожидание: `check_oq_close_form` молчит,
закрытые строки читаются закрытыми по норме и с каналом, промежуточные — открытыми,
заголовки обеих форм — без ⚠ формы заголовка.

Образец здесь — code-span внутри пункта списка (может переноситься на следующую строку
пункта), а не блок кода: помощник вырезания блоков из теста образцов шаблонов
(`test_template_samples_guards.samples`) к нему не подходит, поэтому свой — `code_spans`.

Гид читается через git из `origin/master` клона канона (`CANON_ROOT`, по умолчанию
C:\\doc-as-code\\EAN\\docs-o2new); без клона — skip с причиной. Падение — сигнал автору гида
или автору сторожа, а не повод править тест."""
import os
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from app.scripts.CI.kitcheck.checks.review_guards import (check_oq_close_form,
                                                           oq_class_counter, oq_close_ref,
                                                           oq_closed_new_form, oq_statuses,
                                                           oq_status_class)

_CANON = Path(os.environ.get("CANON_ROOT", r"C:\doc-as-code\EAN\docs-o2new"))
_GUIDE = "_meta/migration/reference.md"
_ITEM_HEAD = "- Вопросы агентов к источнику"

# образцовые значения угловых плейсхолдеров (постановка волны Д, п. 3); ключ — подстрока
# текста плейсхолдера, порядок важен: первое совпадение
_VALUES = [
    ("ГГГГ-ММ-ДД", "2026-11-09"),
    ("ID карточек", "FUN-CL-01"),
    ("кто ответил", "аналитик команды, тред MR"),
    ("ID постановки", "постановка 2026-11-09"),
    ("формулировка", "Вопрос к источнику"),
    ("ID", "GBO-1"),
]
_CHANNEL_PH = "<коммит или тег src/…>"
_CHANNELS = ["abc1234", "src/OQ-007"]  # обе ветки плейсхолдера канала


def guide_item(text: str, head: str = _ITEM_HEAD) -> str:
    """Текст пункта верхнего уровня списка, начинающегося с `head`, до следующего пункта
    верхнего уровня; строки продолжения склеены пробелом (как code-span в Markdown)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(head)), None)
    if start is None:
        return ""
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.startswith("- ") or (ln.strip() and not ln.startswith((" ", "\t"))):
            break
        out.append(ln.strip())
    return " ".join(x for x in out if x)


def code_spans(text: str) -> List[str]:
    """Содержимое code-span в одну обратную кавычку."""
    return [m.group(1).strip() for m in re.finditer(r"(?<!`)`([^`]+)`(?!`)", text)]


def fill(sample: str) -> str:
    """Угловые плейсхолдеры → образцовые значения; голые NNN и ГГГГ-ММ-ДД (заголовок записи
    пишет дату без угловых скобок) — 007 и 2026-11-09."""
    def one(m: re.Match) -> str:
        body = m.group(1)
        for key, val in _VALUES:
            if key in body:
                return val
        raise AssertionError(f"плейсхолдер без образцового значения: <{body}> в «{sample}»")
    return (re.sub(r"<([^<>]+)>", one, sample).replace("NNN", "007")
            .replace("ГГГГ-ММ-ДД", "2026-11-09"))


def classify(spans: List[str]) -> Dict[str, List[str]]:
    """Образцы пункта гида по видам; прочие code-span (`src/<ID>`, `- Статус: …` и т. п.)
    образцами строк записи не являются."""
    heads = [s for s in spans if s.startswith("## OQ-")]
    closed = [s for s in spans if s.startswith("- Статус: закрыт:")]
    interim = [s if s.startswith("- Статус:") else f"- Статус: {s}"
               for s in spans if "ответ получен" in s]
    return {"heads": heads, "closed": closed, "interim": interim}


def journal(kinds: Dict[str, List[str]]) -> Tuple[str, Dict[str, str]]:
    """Временный журнал: каждая строка статуса — своя запись; заголовки чередуют обе формы.
    Возврат: текст и номер записи → вид образца («closed» / «interim»)."""
    statuses = []
    for s in kinds["closed"]:
        if _CHANNEL_PH in s:
            statuses += [("closed", fill(s.replace(_CHANNEL_PH, ch))) for ch in _CHANNELS]
        else:
            statuses.append(("closed", fill(s)))
    statuses += [("interim", fill(s)) for s in kinds["interim"]]
    parts, kind_of = ["# Открытые вопросы\n"], {}
    for i, (kind, st) in enumerate(statuses, 1):
        num = f"{i:03d}"
        head = fill(kinds["heads"][i % len(kinds["heads"])]).replace("OQ-007", f"OQ-{num}")
        parts.append(f"{head}\n\n{st}\n- Затронуто: FUN-CL-01\n")
        kind_of[num] = kind
    return "\n".join(parts), kind_of


def assert_samples_pass(text: str, kind_of: Dict[str, str], tmp: Path) -> None:
    oq = tmp / "open-questions.md"
    oq.write_text(text, encoding="utf-8")
    assert check_oq_close_form(oq) == []
    sts = oq_statuses(text)
    assert set(sts) == set(kind_of)
    for num, st in sts.items():
        if kind_of[num] == "closed":
            assert oq_closed_new_form(st) == date(2026, 11, 9), st
            assert oq_close_ref(st), st
        else:
            assert oq_status_class(st) == "открыт", st
    counter = oq_class_counter(oq, today=date(2026, 11, 9))
    assert not [x for x in counter if x.startswith("⚠")], counter


# ------------------------------------------------------------ логика (без канона)

_FRAGMENT = """\
- Предыдущий пункт.
- Вопросы агентов к источнику — записями OQ-NN в `open-questions.md`;
  - заголовок `## OQ-NNN — ГГГГ-ММ-ДД — <формулировка>` (прежняя форма
    `## OQ-NNN. <формулировка>` допустима);
  - строка закрытой записи — `- Статус: закрыт: <ГГГГ-ММ-ДД>, <коммит или
    тег src/…>, затронуто: <ID карточек>` либо `- Статус: закрыт:
    <ГГГГ-ММ-ДД>, без изменений: <кто ответил, где>`;
  - пока ответ разбирается — `- Статус: ответ получен, разбор`, затем
    `ответ получен, канал: источник, задача <ID>` или `ответ получен,
    канал: комплект, <ID постановки>`; такие записи открыты;
- Следующий пункт `## OQ-999. чужой`.
"""


def test_item_and_spans_cross_line_breaks():
    kinds = classify(code_spans(guide_item(_FRAGMENT)))
    assert kinds["heads"] == ["## OQ-NNN — ГГГГ-ММ-ДД — <формулировка>",
                              "## OQ-NNN. <формулировка>"]
    assert kinds["closed"] == [
        "- Статус: закрыт: <ГГГГ-ММ-ДД>, <коммит или тег src/…>, затронуто: <ID карточек>",
        "- Статус: закрыт: <ГГГГ-ММ-ДД>, без изменений: <кто ответил, где>"]
    assert kinds["interim"] == [
        "- Статус: ответ получен, разбор",
        "- Статус: ответ получен, канал: источник, задача <ID>",
        "- Статус: ответ получен, канал: комплект, <ID постановки>"]


def test_fragment_samples_pass(tmp_path):
    text, kind_of = journal(classify(code_spans(guide_item(_FRAGMENT))))
    assert "<" not in text and "NNN" not in text and "ГГГГ" not in text
    assert sorted(kind_of.values()) == ["closed"] * 3 + ["interim"] * 3
    assert_samples_pass(text, kind_of, tmp_path)


def test_closed_without_channel_bites(tmp_path):
    """НЕсрабатывание теста не пустое: строка закрытия без канала даёт ⚠."""
    oq = tmp_path / "open-questions.md"
    oq.write_text("## OQ-001. Вопрос\n\n- Статус: закрыт: 2026-11-09, затронуто: FUN-CL-01\n",
                  encoding="utf-8")
    assert len(check_oq_close_form(oq)) == 1


def test_unknown_placeholder_fails():
    with pytest.raises(AssertionError):
        fill("- Статус: закрыт: <что-то новое>")


# ------------------------------------------------------------ живой гид канона


def _canon_guide() -> str:
    if not (_CANON / ".git").exists():
        pytest.skip(f"клона канона нет ({_CANON}; путь задаётся CANON_ROOT) — "
                    "страж гида не выполнен")
    r = subprocess.run(["git", "-C", str(_CANON), "show", f"origin/master:{_GUIDE}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        pytest.skip(f"в клоне канона {_CANON} нет origin/master:{_GUIDE} — страж не выполнен")
    return r.stdout


def test_canon_guide_oq_samples_pass_guard(tmp_path):
    item = guide_item(_canon_guide())
    assert item, f"в гиде {_GUIDE} нет пункта «{_ITEM_HEAD}…»"
    kinds = classify(code_spans(item))
    # состав образцов гида: две формы заголовка, две строки закрытия, три промежуточные;
    # пропажа образца — тоже сигнал (выжимка разошлась с нормой техбука)
    assert len(kinds["heads"]) == 2, kinds["heads"]
    assert len(kinds["closed"]) == 2, kinds["closed"]
    assert len(kinds["interim"]) == 3, kinds["interim"]
    text, kind_of = journal(kinds)
    assert "<" not in text and "NNN" not in text and "ГГГГ" not in text
    assert_samples_pass(text, kind_of, tmp_path)
