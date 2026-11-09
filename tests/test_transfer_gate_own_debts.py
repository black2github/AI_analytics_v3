# tests/test_transfer_gate_own_debts.py
"""Гейт переноса: долги «нет целевого артефакта» при источнике в выгрузке (create-artifact,
«Недостающая цель ссылки»). Признак А — имя цели совпало с титулом страницы описи вне
структурных классов, Б — цель карточка вызова; строка с записью переноса считается отдельно.
Полный режим — ⚠, --after-step — i, ✗ только при --own-debts block в полном режиме."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
from tests.test_transfer_gate import _CARD, _MATRIX, _README, _w, make_src  # noqa: E402

_INV_HEAD = ("# Опись\n\n| page_id | title | родитель | req_type | целевой тип (гипотеза) | основание |\n"
             "|---|---|---|---|---|---|\n")
LIVE = "| 101 | [КК] Живая страница | р | ТТ | srs/core/function | сигналы согласны |\n"
FROZEN = "| 102 | [КК] Замороженная | р | ТТ | вне SRS: заморожено GBO-1 | frozen |\n"
OUT_OF_PLAN = "| 103 | [КК] Вне плана | р | ТТ | srs/other/function | сигналы |\n"
WITHDRAWN = "| 104 | [КК] Снятая | р | ТТ | снято с миграции | преемник покрыт |\n"
BASE = "| 105 | [КК] Метод АС | р | ТТ | вне SRS: базовый контракт EXTINT-TESSA-001 | копия |\n"
CONTAINER = "| 106 | [КК] Раздел | р | ТТ | README-реестр | контейнер |\n"
TAIL = "| 107 | [КК_ВК] Виджет: Хвост | р | ТТ | srs/core/function | сигналы |\n"
OTHER_TAG = "| 108 | [КК_ЛК] Двойник | р | ТТ | srs/core/function | сигналы |\n"
FROZEN_TAG = "| 109 | [КК_БК] Двойник | р | ТТ | вне SRS: заморожено GBO-2 | frozen |\n"
INVENTORY = _INV_HEAD + LIVE + FROZEN + OUT_OF_PLAN + WITHDRAWN + BASE + CONTAINER + TAIL + OTHER_TAG + FROZEN_TAG
PLAN = "# План\n\n- подсервис core\n"
TRANSFER = "; перенос: решение владельца 2026-11-06, срок: итерация 2"


def _debt(rest: str) -> str:
    return f"| FUN-CL-01 | — | {rest} |\n"


def _matrix(*rows: str) -> str:
    return (_MATRIX + "\n## 4. Долги по ссылкам\n\n| FROM-ID | Цель | Долг |\n|---|---|---|\n"
            + "".join(rows))


def _own(*rows: str, inventory: bool = True):
    def run(tmp: Path):
        inv, plan = None, None
        if inventory:
            inv = tmp / "inventory.md"
            plan = tmp / "migration-plan.md"
            _w(inv, INVENTORY)
            _w(plan, PLAN)
        return tg.own_target_debts(_matrix(*rows), inv, plan)
    return run


def _counts(res):
    return res["a"], res["b"], res["k"]


def _src(tmp_path: Path, *rows: str, inventory: bool = True) -> Path:
    src = make_src(tmp_path, matrix=_matrix(*rows))
    # прежние сторожа долгов довольны: README объясняет раздел, имена целей есть в карточке
    _w(src / "docs/README.md", _README + "\n### Долги по ссылкам\n\nПравило чтения.\n")
    _w(src / "docs/srs/function/f1.md", _CARD + "\n[КК] Живая страница, Метод, [КК] Нет такой\n")
    if inventory:
        _w(src / "inventory.md", INVENTORY)
        _w(src / "migration-plan.md", PLAN)
    return src


def _gate_line(lines):
    return next(l for l in lines if "долги «требуется заход» при источнике в выгрузке" in l)


FUNC_LIVE = _debt("нет целевого артефакта function «[КК] Живая страница» — требуется заход create-function")
CALL = _debt("нет целевого артефакта contract-call «Метод» — требуется заход create-contract-call")


# ---------------------------------------------------------------- признак А

@pytest.mark.parametrize("name", ["[КК] Живая страница", "Живая страница"])
def test_a_fires_on_title_by_existing_rule(tmp_path, name):
    res = _own(_debt(f"нет целевого артефакта function «{name}» — требуется заход create-function"))(tmp_path)
    assert _counts(res) == (1, 0, 0)
    assert res["rows"][0]["sign"] == "А" and res["rows"][0]["page_id"] == "101"


def test_a_fires_on_title_tail(tmp_path):
    res = _own(_debt("нет целевого артефакта screen-form «Хвост» — требуется заход create-screen-form"))(tmp_path)
    assert _counts(res) == (1, 0, 0) and res["rows"][0]["page_id"] == "107"


def test_a_silent_when_page_not_in_inventory(tmp_path):
    res = _own(_debt("нет целевого артефакта function «[КК] Нет такой» — требуется заход create-function"))(tmp_path)
    assert _counts(res) == (0, 0, 0) and res["total"] == 1 and res["rows"] == []


@pytest.mark.parametrize("name", ["[КК] Замороженная", "[КК] Вне плана", "[КК] Снятая", "[КК] Метод АС",
                                  "[КК] Раздел"])
def test_a_silent_on_structural_classes(tmp_path, name):
    res = _own(_debt(f"нет целевого артефакта function «{name}» — требуется заход create-function"))(tmp_path)
    assert _counts(res) == (0, 0, 0)


def test_exact_frozen_title_wins_over_live_title_of_other_tag(tmp_path):
    # КК: «[КК_БК] Контроли ЭФ (front)» заморожена, «[КК_ВК] Контроли ЭФ (front)» живая
    res = _own(_debt("нет целевого артефакта control «[КК_БК] Двойник» — требуется заход create-controls"))(tmp_path)
    assert _counts(res) == (0, 0, 0)


@pytest.mark.parametrize("name", ["[КК_ВК] Двойник", "[Другой] Живая страница"])
def test_live_title_of_other_tag_is_not_a_match(tmp_path, name):
    # постановка 2026-11-09, П-7: «[КК_ЗК] X» вне выгрузки ложно сопоставлялось с «[КК_Заявки] X»
    # описи — у разных тегов разные страницы, признак А не ставится
    res = _own(_debt(f"нет целевого артефакта control «{name}» — требуется заход create-controls"))(tmp_path)
    assert _counts(res) == (0, 0, 0) and res["rows"] == []


def test_untagged_name_still_matches_tagged_title(tmp_path):
    # НЕсрабатывание ограничения: имя без тега сопоставляется с титулом с тегом, как прежде
    res = _own(_debt("нет целевого артефакта control «Двойник» — требуется заход create-controls"))(tmp_path)
    assert _counts(res) == (1, 0, 0) and res["rows"][0]["page_id"] == "108"


def test_out_of_export_row_excluded_from_count(tmp_path):
    row = _debt("нет целевого артефакта function «[КК] Живая страница» — страница 2166860928 вне выгрузки")
    res = _own(row, FUNC_LIVE)(tmp_path)
    assert res["out_of_export"] == 1 and res["total"] == 1 and _counts(res) == (1, 0, 0)


def test_out_of_export_in_gate_line(tmp_path):
    row = _debt("нет целевого артефакта function «[КК] Нет такой» — страница 1 вне выгрузки")
    lines, _ready, _data = tg.run_gate(_src(tmp_path, row), no_validator=True)
    assert "строк «вне выгрузки» — 1 (вне счёта)" in _gate_line(lines)


def test_a_not_checked_without_inventory(tmp_path):
    assert _counts(_own(FUNC_LIVE, inventory=False)(tmp_path)) == (0, 0, 0)


# ---------------------------------------------------------------- признак Б

def test_b_fires_on_type(tmp_path):
    res = _own(_debt("нет целевого артефакта contract-call «Метод» — ждёт регистрации"))(tmp_path)
    assert _counts(res) == (0, 1, 0) and res["rows"][0]["sign"] == "Б"


def test_b_fires_on_skill(tmp_path):
    res = _own(_debt("нет целевого артефакта external «Метод» — требуется заход create-contract-call"))(tmp_path)
    assert _counts(res) == (0, 1, 0)


def test_b_does_not_depend_on_inventory(tmp_path):
    assert _counts(_own(CALL, inventory=False)(tmp_path)) == (0, 1, 0)


def test_b_takes_row_with_both_signs_once(tmp_path):
    res = _own(_debt("нет целевого артефакта contract-call «[КК] Живая страница» — требуется заход "
                     "create-contract-call"))(tmp_path)
    assert _counts(res) == (0, 1, 0) and res["rows"][0]["page_id"] == "—"


@pytest.mark.parametrize("row", [
    "нет целевого артефакта contract-call «Метод» у владельца payments — требуется заход create-contract-call",
    "нет базового контракта «Метод» у владельца ТЕССА — требуется контур base",
    "нет базового контракта «Метод» — требуется контур base",
    "нет целевого артефакта function «[КК] Живая страница» у владельца payments — требуется заход create-function",
])
def test_owner_forms_do_not_fire(tmp_path, row):
    res = _own(_debt(row))(tmp_path)
    assert _counts(res) == (0, 0, 0) and res["total"] == 0


def test_issue_debt_does_not_fire(tmp_path):
    res = _own(_debt("долг противоречие: «[КК] Живая страница» — причина: два текста; ответственный: "
                     "аналитик; ограничение: нет; закрытие: одна формулировка"))(tmp_path)
    assert res["total"] == 0


# ---------------------------------------------------------------- запись переноса

@pytest.mark.parametrize("row", [FUNC_LIVE, CALL])
def test_transfer_record_counts_in_k_not_in_signs(tmp_path, row):
    res = _own(row.replace(" |\n", TRANSFER + " |\n"))(tmp_path)
    assert _counts(res) == (0, 0, 1) and res["rows"][0]["transfer"] == "запись"


def test_transfer_record_on_objective_debt_counts_in_k(tmp_path):
    res = _own(_debt("нет целевого артефакта function «[КК] Нет такой» — требуется заход create-function"
                     + TRANSFER))(tmp_path)
    assert _counts(res) == (0, 0, 1) and res["rows"][0]["sign"] == "—"


def test_transfer_record_date_dotted(tmp_path):
    res = _own(CALL.replace(" |\n", "; перенос: решение владельца 06.11.2026, срок: 2026-12-01 |\n"))(tmp_path)
    assert _counts(res) == (0, 0, 1)


@pytest.mark.parametrize("tail", [
    "; перенос: решение владельца, срок: итерация 2",
    "; перенос: решение владельца 2026-11-06",
    "; перенос: решение владельца 2026-11-06, срок: ",
    "; перенос: по договорённости",
])
def test_partial_record_stays_in_signs(tmp_path, tail):
    res = _own(CALL.replace(" |\n", tail + " |\n"))(tmp_path)
    assert _counts(res) == (0, 1, 0) and res["partial"] == 1 and res["rows"][0]["transfer"] == "неполная"


def test_word_transfer_in_name_is_not_a_record(tmp_path):
    res = _own(_debt("нет целевого артефакта contract-call «Перенос: Метод» — требуется заход "
                     "create-contract-call"))(tmp_path)
    assert _counts(res) == (0, 1, 0) and res["partial"] == 0


def test_transfer_tail_accepted_by_link_debts_parser(tmp_path):
    # формат строки долга не меняется: хвост проходит прежний разбор, строка не «нераспознанная»
    _reg, debts, unrecognized = tg.ld.parse_matrix_full(_matrix(CALL.replace(" |\n", TRANSFER + " |\n")))
    assert unrecognized == [] and debts[0][1] == "contract-call" and debts[0][2] == "Метод"


# ---------------------------------------------------------------- строка гейта и режимы

def test_full_warn_is_warning_and_verdict_unchanged(tmp_path):
    lines, ready, data = tg.run_gate(_src(tmp_path, FUNC_LIVE, CALL), no_validator=True)
    line = _gate_line(lines)
    assert line.startswith("⚠ [CORE-20] долги «требуется заход» при источнике в выгрузке: А — 1, "
                           "Б (карточки вызова) — 1; с записью переноса — 0")
    assert ready and data["own_debts"]["a"] == 1 and data["own_debts"]["b"] == 1


def test_after_step_is_info(tmp_path):
    lines, ready, _ = tg.run_gate(_src(tmp_path, FUNC_LIVE, CALL), no_validator=True, after_step=True)
    assert _gate_line(lines).startswith("i [CORE-20]") and ready


def test_block_gives_blocker_in_full_mode(tmp_path):
    lines, ready, data = tg.run_gate(_src(tmp_path, FUNC_LIVE, CALL), no_validator=True, own_debts="block")
    assert _gate_line(lines).startswith("✗ [CORE-20]") and not ready and data["blockers"] >= 1


def test_block_is_info_after_step(tmp_path):
    lines, ready, _ = tg.run_gate(_src(tmp_path, FUNC_LIVE, CALL), no_validator=True, after_step=True,
                                  own_debts="block")
    assert _gate_line(lines).startswith("i [CORE-20]") and ready


def test_block_passes_rows_with_record(tmp_path):
    rows = [r.replace(" |\n", TRANSFER + " |\n") for r in (FUNC_LIVE, CALL)]
    lines, ready, _ = tg.run_gate(_src(tmp_path, *rows), no_validator=True, own_debts="block")
    line = _gate_line(lines)
    assert line.startswith("i [CORE-20]") and "с записью переноса — 2" in line and ready


def test_block_stops_on_partial_record(tmp_path):
    lines, ready, _ = tg.run_gate(_src(tmp_path, CALL.replace(" |\n", "; перенос: на потом |\n")),
                                  no_validator=True, own_debts="block")
    line = _gate_line(lines)
    assert line.startswith("✗ [CORE-20]") and "запись переноса без даты или срока — 1" in line and not ready


def test_block_does_not_fire_on_objective_debt(tmp_path):
    row = _debt("нет целевого артефакта function «[КК] Нет такой» — требуется заход create-function")
    lines, ready, _ = tg.run_gate(_src(tmp_path, row), no_validator=True, own_debts="block")
    assert _gate_line(lines).startswith("✓ [CORE-20]") and ready


def test_no_debts_is_pass(tmp_path):
    lines, ready, data = tg.run_gate(make_src(tmp_path), no_validator=True)
    assert _gate_line(lines).startswith("✓ [CORE-20]") and ready and data["own_debts"]["total"] == 0


def test_without_inventory_says_sign_a_not_checked(tmp_path):
    lines, ready, _ = tg.run_gate(_src(tmp_path, FUNC_LIVE, inventory=False), no_validator=True)
    line = _gate_line(lines)
    assert line.startswith("i [CORE-20]") and "описи нет — признак А не проверялся" in line and ready


def test_report_lists_rows(tmp_path):
    src = _src(tmp_path, FUNC_LIVE, CALL)
    lines, _, data = tg.run_gate(src, no_validator=True, fmt="table")
    rep = tmp_path / "r.md"
    tg.write_report(rep, src, lines, data)
    text = rep.read_text(encoding="utf-8")
    assert "### Долги «требуется заход» при источнике в выгрузке" in text
    assert "| FUN-CL-01 | А | function | [КК] Живая страница | 101 | — |" in text
    assert "| FUN-CL-01 | Б | contract-call | Метод | — | — |" in text


def test_report_without_signs_has_no_section(tmp_path):
    src = _src(tmp_path, _debt("нет целевого артефакта function «[КК] Нет такой» — требуется заход create-function"))
    lines, _, data = tg.run_gate(src, no_validator=True, fmt="table")
    rep = tmp_path / "r.md"
    tg.write_report(rep, src, lines, data)
    assert "### Долги «требуется заход»" not in rep.read_text(encoding="utf-8")


def test_cli_default_is_warn(tmp_path, monkeypatch, capsys):
    src = _src(tmp_path, FUNC_LIVE, CALL)
    monkeypatch.setattr(sys, "argv", ["transfer_gate.py", "--src", str(src), "--no-validator", "--log"])
    assert tg.main() == 0
    assert "⚠ [CORE-20] долги «требуется заход»" in capsys.readouterr().out


def test_cli_block(tmp_path, monkeypatch, capsys):
    src = _src(tmp_path, FUNC_LIVE, CALL)
    monkeypatch.setattr(sys, "argv", ["transfer_gate.py", "--src", str(src), "--no-validator", "--log",
                                      "--own-debts", "block"])
    assert tg.main() == 1
    assert "✗ [CORE-20] долги «требуется заход»" in capsys.readouterr().out
