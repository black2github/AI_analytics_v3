# tests/test_transfer_gate_external_inventory.py
"""Гейт переноса: опись и архив выгрузки явными ключами (--inventory, --raw, --bundle). В
репозиторий документации опись не переносится (stage_kit копирует только комплект), поэтому
гейт целевого без ключа идёт без помилований по описи и даёт ✗, которых нет в src (КК после
переноса, 08.11: ✗30 против ✗0 прямого прогона с описью). На переходный период гейт целевого
запускается с описью и выгрузкой из src; явный путь сильнее локатора, строка «опись: …»
называет, какая опись действовала."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402
from tests.test_kit_inventory_locator import (  # noqa: E402
    _CALL, _CALL_REL, _CARD_LINE, _INV, _NO_HEADING, _card_mark, _sources)
from tests.test_transfer_gate import _README, _w  # noqa: E402

_MATRIX = ("# Матрица\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
           f"| CALL-EXT-011 | contract-call | Вызов | {_CALL_REL} |\n\n"
           "## 3. Покрытие: API ↔ SRS\n\n| Операция | Артефакты SRS |\n| --- | --- |\n")


def make_target(tmp_path: Path) -> Path:
    """Целевой репозиторий документации после переноса: комплект в корне, описи и выгрузки нет."""
    repo = tmp_path / "docs-x"
    _w(repo / "README.md", _README)
    _w(repo / "traceability-matrix.md", _MATRIX)
    _w(repo / _CALL_REL, _CALL)
    _w(repo / "CODEOWNERS", "* @team-x\n")
    _w(repo / "gpb-manifest.json", '{"name": "docs-x", "owner": "team-x"}\n')
    return repo


def make_src_archive(tmp_path: Path) -> Path:
    """Рабочий репозиторий src: выгрузка и опись в другом каталоге."""
    src = tmp_path / "src-x"
    _sources(src)
    _w(src / "inventory.md", _INV)
    return src


def _gate(repo: Path, **kw):
    kw.setdefault("no_validator", True)
    return tg.run_gate(repo, **kw)


def _inv_line(lines):
    hit = [ln for ln in lines if "[ПРИБОР] опись" in ln]
    assert len(hit) == 1, "\n".join(lines)
    return hit[0]


# ---------------------------------------------------------------- поведение без ключа — как прежде

def test_docs_repo_without_inventory_unchanged(tmp_path):
    # НЕсрабатывание послабления: описи нет — довод по описи не действует, ✗ карточки остаётся
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    lines, ready, data = _gate(repo, sources=src / "sources" / "confluence")
    assert data["docs_repo"] is True
    assert not ready and _card_mark(lines) == "✗", "\n".join(lines)
    assert _inv_line(lines).startswith("i [ПРИБОР] опись: не найдена — помилования по описи не "
                                       "действуют"), "\n".join(lines)
    assert data["inventory"] is None


# ---------------------------------------------------------------- внешняя опись

def test_docs_repo_with_external_inventory_pardons(tmp_path):
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    lines, _ready, data = _gate(repo, sources=src / "sources" / "confluence",
                                inventory=src / "inventory.md")
    text = "\n".join(lines)
    assert not any(_CARD_LINE in ln for ln in lines), text      # ✓ карточек гейт не печатает
    assert not any(ln.startswith("✗ [ПРИБОР]") for ln in lines), text
    assert _NO_HEADING not in text, text
    assert _inv_line(lines) == (f"i [ПРИБОР] опись: {(src / 'inventory.md').as_posix()} (внешняя, "
                                "--inventory); план миграции: рядом с описью не найден"), text
    assert data["inventory"] == str(src / "inventory.md")


def test_homoglyph_verbatim_not_defect_with_external_inventory(tmp_path):
    # НЕсрабатывание ✗ по гомоглифу: слово дословно в выгрузке src — данные автора, не подмена
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    word = "Bыпуск"  # латинская B
    _w(repo / _CALL_REL, _CALL.replace("Привязка данных.", f"Привязка данных: {word}."))
    conf = src / "sources" / "confluence"
    _w(conf / "main.md", (conf / "main.md").read_text(encoding="utf-8").replace(
        "текст", f"текст {word}"))
    lines, _ready, _data = _gate(repo, sources=conf, inventory=src / "inventory.md")
    text = "\n".join(lines)
    assert "гомоглифы/смешанное письмо" not in text, text
    assert not any(_CARD_LINE in ln for ln in lines), text


def test_homoglyph_not_in_source_still_defect(tmp_path):
    # ограничитель: слова в выгрузке нет — ✗ остаётся и с внешней описью
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    _w(repo / _CALL_REL, _CALL.replace("Привязка данных.", "Привязка данных: Bыпуск."))
    conf, kept = src / "sources" / "confluence", tmp_path / "kept"
    lines, ready, _data = _gate(repo, sources=conf, inventory=src / "inventory.md", keep=kept)
    assert not ready and _card_mark(lines) == "✗", "\n".join(lines)
    # причину ✗ гейт печатает строкой карточки без подстрок — она видна прямым прогоном той же сборки
    rep, _ok = tg.sc.run(kept, conf, inventory=src / "inventory.md")
    assert "гомоглифы/смешанное письмо в словах ×1 ('Bыпуск')" in "\n".join(rep), "\n".join(rep)


def test_explicit_inventory_wins_over_locator(tmp_path):
    # опись рядом с комплектом есть, но ключ указывает другую — действует указанная
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    _w(repo.parent / "inventory.md", "| page_id | title |\n|---|---|\n")   # родитель комплекта
    lines, _ready, data = _gate(repo, sources=src / "sources" / "confluence",
                                inventory=src / "inventory.md")
    assert "(внешняя, --inventory)" in _inv_line(lines)
    assert data["inventory"] == str(src / "inventory.md")
    assert not any(_CARD_LINE in ln for ln in lines), "\n".join(lines)


def test_explicit_missing_inventory_is_defect(tmp_path):
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    missing = tmp_path / "nope" / "inventory.md"
    lines, ready, data = _gate(repo, sources=src / "sources" / "confluence", inventory=missing)
    assert not ready
    assert _inv_line(lines) == (f"✗ [ПРИБОР] опись (--inventory) не найдена: {missing.as_posix()} "
                                "— помилования по описи не действуют"), "\n".join(lines)
    assert data["inventory"] is None


def test_src_mode_locator_line(tmp_path):
    # рабочий репозиторий: опись рядом с docs/ находится сама, строка называет её без «внешняя»
    from tests.test_kit_inventory_locator import make_kit
    root = make_kit(tmp_path)
    lines, _ready, _data = _gate(root)
    assert _inv_line(lines) == f"i [ПРИБОР] опись: {(root / 'inventory.md').as_posix()}"


# ---------------------------------------------------------------- проброс в прибор и CORE-20

def test_keys_passed_to_selfcheck(tmp_path, monkeypatch):
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    seen = {}

    def fake_run(staged, sources, **kw):
        seen.update(kw)
        return ["ИТОГО: файлов 1 — ✓ 1, ✗ 0"], True

    monkeypatch.setattr(tg.sc, "run", fake_run)
    raw, bundle = src / "sources" / "raw", tmp_path / "bundle"
    _gate(repo, sources=src / "sources" / "confluence", inventory=src / "inventory.md",
          raw=raw, bundle=bundle)
    assert seen["inventory"] == src / "inventory.md"
    assert seen["raw"] == raw and seen["bundle"] == bundle


def test_own_debts_read_external_inventory_and_plan(tmp_path):
    # CORE-20 «долги на собственный заход» читает ту же внешнюю опись и план рядом с ней
    repo = make_target(tmp_path)
    src = make_src_archive(tmp_path)
    _w(src / "inventory.md", _INV + "| 101 | [КК] Живая страница | р | ТТ | 1 | srs/core/function | с |\n")
    _w(src / "migration-plan.md", "# План\n\n- подсервис core\n")
    _w(repo / "traceability-matrix.md", _MATRIX + "\n## 4. Долги по ссылкам\n\n| FROM-ID | Цель | Долг |\n"
       "|---|---|---|\n| CALL-EXT-011 | — | нет целевого артефакта function «[КК] Живая страница» — "
       "требуется заход create-function |\n")
    _lines, _ready, data = _gate(repo, sources=src / "sources" / "confluence",
                                 inventory=src / "inventory.md")
    assert data["own_debts"]["inventory"] is True and data["own_debts"]["a"] == 1, data["own_debts"]
    lines0, _r, data0 = _gate(repo, sources=src / "sources" / "confluence")
    assert data0["own_debts"]["inventory"] is False and data0["own_debts"]["a"] == 0
