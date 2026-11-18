# -*- coding: utf-8 -*-
"""FB-05 сервиса «Обновление сведений» (2026-11-18): заглушка ЭФ по шаблону screen-form
(frontmatter + «Назначение» + строка «Документ-заглушка: …») не получает P0 no_skill_markers;
перечень заглушек — в отчёте и в выводе; заглушка с маркерами FLD-/EV-/B- — P1 stub_with_content.
Признак заглушки — тот же, что у самопроверки (kitcheck.checks.content._STUB_MARK)."""
import subprocess
import sys
from pathlib import Path

from app.scripts.CI import validate_screen_forms as vsf
from app.scripts.CI.kitcheck.checks import content

SCRIPT = Path(vsf.__file__)
FM = "---\nid: SCR-CL-07\ntype: screen-form\ntitle: 'ЭФ Клиента «Контакты»'\n---\n\n"
STUB = FM + "## 1. Назначение\n\nПросмотр контактов.\n\nДокумент-заглушка: форма будет описана позже.\n"
FULL = FM + "## 1. Назначение\n\nПросмотр.\n\n## 3. Поля\n\n| ID | Поле |\n|---|---|\n| FLD-1 | ИНН |\n"
BARE = FM + "## 1. Назначение\n\nПросмотр контактов.\n"


def _card(tmp_path: Path, text: str, name: str = "scr-cl-07.md") -> Path:
    p = tmp_path / "srs" / "screen-form" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _codes(tmp_path, text):
    stubs = []
    issues = vsf.analyze_file(_card(tmp_path, text), tmp_path, stubs)
    return [(i["code"], i["severity"]) for i in issues], stubs


def test_stub_mark_one_home():
    # признак импортируется из самопроверки, своего литерала у скрипта нет
    assert vsf._STUB_MARK == content._STUB_MARK
    src = SCRIPT.read_text(encoding="utf-8").lower()
    assert f'"{content._STUB_MARK}"' not in src and f"'{content._STUB_MARK}'" not in src
    assert "from kitcheck.checks.content import _stub_mark" in src


def test_stub_no_p0_and_listed(tmp_path):
    codes, stubs = _codes(tmp_path, STUB)
    assert codes == [] and stubs == ["srs/screen-form/scr-cl-07.md"]


def test_bare_card_still_p0(tmp_path):
    # НЕсрабатывание: ни строки-заглушки, ни маркеров — P0, как прежде
    codes, stubs = _codes(tmp_path, BARE)
    assert codes == [("no_skill_markers", "P0")] and stubs == []


def test_full_card_no_issues(tmp_path):
    codes, stubs = _codes(tmp_path, FULL)
    assert codes == [] and stubs == []


def test_stub_with_markers_p1(tmp_path):
    codes, stubs = _codes(tmp_path, FULL + "\nДокумент-заглушка: форма будет описана позже.\n")
    assert codes == [("stub_with_content", "P1")] and len(stubs) == 1


def test_word_zaglushka_alone_not_stub(tmp_path):
    # НЕсрабатывание: слово «заглушка» без формы «Документ-заглушка» — не признак
    codes, stubs = _codes(tmp_path, BARE + "\nЗаглушка экрана показывается при ошибке загрузки.\n")
    assert codes == [("no_skill_markers", "P0")] and stubs == []


def test_cli_report_and_stdout(tmp_path):
    _card(tmp_path, STUB)
    _card(tmp_path, FULL, "scr-cl-08.md")
    out = tmp_path / "rep.md"
    r = subprocess.run([sys.executable, str(SCRIPT), "--docs", str(tmp_path), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "files=2 stubs=1 P0=0 P1=0" in r.stdout
    rep = out.read_text(encoding="utf-8")
    assert "| Заглушки | 1 |" in rep and "- `srs/screen-form/scr-cl-07.md`" in rep
    assert "| Вердикт | PASS |" in rep


def test_cli_bare_card_fails(tmp_path):
    _card(tmp_path, BARE)
    out = tmp_path / "rep.md"
    r = subprocess.run([sys.executable, str(SCRIPT), "--docs", str(tmp_path), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "stubs=0 P0=1" in r.stdout
    assert "## Заглушки\n\nКарточки" in out.read_text(encoding="utf-8")
