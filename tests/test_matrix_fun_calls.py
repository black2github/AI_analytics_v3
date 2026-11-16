# tests/test_matrix_fun_calls.py
"""Колонка «Вызовы» в разделе матрицы «Покрытие: функции → артефакты» (решение владельца канона
16.11.2026, постановка прибору 2026-11-16): выводимая, то же правило связи, что у «Вызовов»
процессов, — markdown-ссылка в любую сторону, колонка по префиксу ID (CALL, PLT, EXTINT, INTC).
Контракт пары «функция метода ↔ внутренний контракт» (определение сторожа контура функции метода:
строка «по контракту …», иначе общая страница) — не вызов. Матрица до изменения: --check ⚠ «нет
колонки», --write добавляет, повторный --check ✓."""
from pathlib import Path

from app.scripts.CI import matrix_sync as ms
from tests.test_matrix_sync import REGISTRY, fm, kit, w

OLD_HDR = "| Функция | Название | Экраны | Данные | Контроли | Уведомления | Печатные формы |"
NEW_HDR = "| Функция | Название | Вызовы | Экраны | Данные | Контроли | Уведомления | Печатные формы |"
FUN = "srs/function/fun-cl-01.md"
REGISTRY_CALL = REGISTRY.replace(
    "| --- | --- | --- |\n",
    "| --- | --- | --- |\n| CALL-INT-001 | Вызов метода | `srs/contract-call/internal/call-int-001.md` |\n", 1)


def _old_matrix(docs: Path) -> None:
    """Матрица по шаблону до колонки «Вызовы» у функций."""
    m = docs / "traceability-matrix.md"
    t = m.read_text(encoding="utf-8")
    t = t.replace(NEW_HDR + "\n| --- | --- | --- | --- | --- | --- | --- | --- |",
                  OLD_HDR + "\n| --- | --- | --- | --- | --- | --- | --- |")
    t = t.replace("| FUN-CL-01 | Сохранение | — | SCR-CL-01 |", "| FUN-CL-01 | Сохранение | SCR-CL-01 |")
    assert OLD_HDR in t
    m.write_text(t, encoding="utf-8")


def _call_card(docs: Path, links_function: bool = False) -> None:
    body = "## Использование в сервисе\n\n### Процессы\n\n| Процесс / функция | Шаг / место |\n|---|---|\n"
    if links_function:
        body += "| [FUN-CL-01 Сохранение](../../function/fun-cl-01.md) | Шаг 2 |\n"
    w(docs / "srs/contract-call/internal/call-int-001.md",
      fm("CALL-INT-001", "contract-call", "Вызов метода") + body)


def _intc(docs: Path, n: int, page: str = "") -> None:
    extra = f"confluence_page_ids: ['{page}']\n" if page else ""
    w(docs / f"srs/internal-contract/intc-00{n}.md", fm(f"INTC-00{n}", "internal-contract", f"Метод {n}", extra))


def _fun_row(docs: Path) -> list:
    text = (docs / "traceability-matrix.md").read_text(encoding="utf-8")
    sec = next(s for s in ms.parse_matrix(text) if s.key == "fun")
    row = next(r for r in sec.rows if r[0] == "FUN-CL-01")
    return dict(zip(sec.header, row))


def _write_ok(docs: Path) -> None:
    rep, code = ms.write(docs)
    assert code == 0, rep
    report, warn = ms.check(docs)
    assert not warn, report


# --- место колонки и добавление в существующую матрицу ---

def test_template_column_third_after_name():
    cols = ms.SECTION_COLS["fun"]
    assert cols[:3] == ["Функция", "Название", "Вызовы"] and cols[3] == "Экраны"
    assert ms.FUN_COLS[0] == "ext" and ms.COL_PREFIXES["ext"] == {"CALL", "PLT", "EXTINT", "INTC"}


def test_old_matrix_warned_then_write_adds_and_keeps_other_cells(tmp_path):
    docs = kit(tmp_path, fun_extra="Вызов — [CALL-INT-001](../contract-call/internal/call-int-001.md).\n",
               registry=REGISTRY_CALL)
    _call_card(docs)
    _old_matrix(docs)
    report, warn = ms.check(docs)
    text = "\n".join(report)
    assert warn and ("⚠ «Покрытие: функции → артефакты»: нет колонки «Вызовы» — --write добавит "
                     "(новая колонка шаблона)") in text, text
    assert "структура матрицы не по шаблону" not in text, text
    before = (docs / "traceability-matrix.md").read_text(encoding="utf-8")
    _write_ok(docs)
    after = (docs / "traceability-matrix.md").read_text(encoding="utf-8")
    assert NEW_HDR in after
    assert "| FUN-CL-01 | Сохранение | CALL-INT-001 | SCR-CL-01 | ENT-001 | CTL-GRP-1 | — | — |" in after, after
    # раздел процессов и всё до покрытия функций — байт в байт
    assert before.split("## Покрытие: функции")[0] == after.split("## Покрытие: функции")[0]
    assert before.split("## Покрытие: процессы")[1] == after.split("## Покрытие: процессы")[1]
    rep2, code2 = ms.write(docs)
    assert code2 == 0 and "не перезаписан" in rep2[0], rep2


def test_function_without_calls_dash(tmp_path):
    docs = kit(tmp_path)
    _old_matrix(docs)
    _write_ok(docs)
    assert _fun_row(docs)["Вызовы"] == "—"


def test_call_card_linking_function_counts(tmp_path):
    # связь в любую сторону: карточка вызова ссылается на функцию в «Процессах»
    docs = kit(tmp_path)
    _call_card(docs, links_function=True)
    _write_ok(docs)
    assert _fun_row(docs)["Вызовы"] == "CALL-INT-001"


# --- свой контракт функции метода — не вызов ---

def test_own_contract_by_link_not_a_call(tmp_path):
    docs = kit(tmp_path, fun_extra="Входные и исходящие параметры — по контракту "
                                   "[INTC-001 Метод 1](../internal-contract/intc-001.md).\n")
    _intc(docs, 1)
    _write_ok(docs)
    assert _fun_row(docs)["Вызовы"] == "—"


def test_own_contract_by_page_not_a_call(tmp_path):
    docs = kit(tmp_path, fun_extra="Метод [INTC-001 Метод 1](../internal-contract/intc-001.md).\n")
    f = docs / FUN
    f.write_text(f.read_text(encoding="utf-8").replace(
        "service: x\n", "service: x\nconfluence_page_ids: ['2166869999']\n", 1), encoding="utf-8")
    _intc(docs, 1, page="2166869999")
    _write_ok(docs)
    assert _fun_row(docs)["Вызовы"] == "—"


def test_other_contract_is_a_call_next_to_own(tmp_path):
    # пара есть, но обращение к чужому методу прямой ссылкой — вызов
    docs = kit(tmp_path, fun_extra="Входные и исходящие параметры — по контракту "
                                   "[INTC-001 Метод 1](../internal-contract/intc-001.md).\n\n"
                                   "Шаг 2: вызывается метод [INTC-002 Метод 2](../internal-contract/intc-002.md).\n")
    _intc(docs, 1)
    _intc(docs, 2)
    _write_ok(docs)
    assert _fun_row(docs)["Вызовы"] == "INTC-002"


def test_contract_without_pair_formula_stays_a_call(tmp_path):
    # нет строки «по контракту» и общей страницы — связь с INTC остаётся вызовом
    docs = kit(tmp_path, fun_extra="Метод обрабатывает сообщение ([INTC-001](../internal-contract/intc-001.md)).\n")
    _intc(docs, 1)
    _write_ok(docs)
    assert _fun_row(docs)["Вызовы"] == "INTC-001"


def test_own_contract_written_in_cell_warned_and_removed(tmp_path):
    docs = kit(tmp_path, fun_extra="Входные и исходящие параметры — по контракту "
                                   "[INTC-001 Метод 1](../internal-contract/intc-001.md).\n")
    _intc(docs, 1)
    _write_ok(docs)
    m = docs / "traceability-matrix.md"
    m.write_text(m.read_text(encoding="utf-8").replace(
        "| FUN-CL-01 | Сохранение | — |", "| FUN-CL-01 | Сохранение | INTC-001 |"), encoding="utf-8")
    report, warn = ms.check(docs)
    text = "\n".join(report)
    assert warn and "свой контракт функции метода в «Вызовах»" in text and "FUN-CL-01 «Вызовы»: INTC-001" in text, text
    assert "связь только в матрице" not in text, text
    _write_ok(docs)
    assert _fun_row(docs)["Вызовы"] == "—"


def test_process_calls_unchanged_by_pair_rule(tmp_path):
    # правило пары — только у функций: «Вызовы» процесса считаются как прежде
    docs = kit(tmp_path, fun_extra="Входные и исходящие параметры — по контракту "
                                   "[INTC-001 Метод 1](../internal-contract/intc-001.md).\n")
    _intc(docs, 1)
    p = docs / "srs/process/proc-001.md"
    p.write_text(p.read_text(encoding="utf-8")
                 + "| 2 | вызов [INTC-001](../internal-contract/intc-001.md) |\n", encoding="utf-8")
    _write_ok(docs)
    text = (docs / "traceability-matrix.md").read_text(encoding="utf-8")
    assert "| PROC-001 | Обработка | — | FUN-CL-01 | INTC-001 |" in text, text
