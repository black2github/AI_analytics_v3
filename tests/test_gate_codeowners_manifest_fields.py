# tests/test_gate_codeowners_manifest_fields.py
"""Пакет П2 ОНБ-В, п. 3 (замечание 62): CORE-04 — ✗ при плейсхолдере «@REPLACE_…» в
CODEOWNERS; SDLC-07 — ⚠ при плейсхолдере «REPLACE_…» в строковом поле паспорта, пустых
обязательных полях teamInfo и projectType вне словаря схемы техбука."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402

# паспорт по образцу техбука (cookbook/devops/assets/gpb-manifest-setup), контакт — null
_MF = {"automatedSystemCode": "ECO", "name": "docs-x", "title": "Документация X",
       "type": "documentation", "emailItLeader": "lead@example.ru", "emailDevOps": None,
       "teamInfo": {"team": "Papa", "projectType": "ECO_AN", "platform": False}}


def _out(tmp_path: Path, codeowners: str = "/ @owner\n", mf=None) -> Path:
    out = tmp_path / "docs-x"
    out.mkdir(parents=True)
    (out / "CODEOWNERS").write_text(codeowners, encoding="utf-8")
    if mf is not None:
        (out / "gpb-manifest.json").write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
    return out


def _gate(out: Path):
    g = tg.Gate()
    tg.check_target_repo(g, out)
    return g


def test_codeowners_placeholder_blocks(tmp_path):
    g = _gate(_out(tmp_path, "# владельцы\n/ @REPLACE_GITLAB_USER\n", _MF))
    bad = [ln for ln in g.render() if ln.startswith("✗ [CORE-04]")]
    assert bad and "плейсхолдер вместо владельца в строках ×1" in bad[0], g.render()
    assert g.blockers == 1


def test_codeowners_placeholder_in_comment_or_word_silent(tmp_path):
    # НЕсрабатывание: комментарий и чужое слово с подстрокой
    g = _gate(_out(tmp_path, "# заменить @REPLACE_ME\n/ @owner @team/REPLACE_x\n", _MF))
    assert g.blockers == 0, g.render()


def test_codeowners_placeholder_in_domain_root_mode(tmp_path):
    # ветка репозитория с комплектами в подкаталогах (_check_codeowners)
    g = tg.Gate()
    root = tmp_path / "repo"
    (root / "kit").mkdir(parents=True)
    (root / "CODEOWNERS").write_text("/kit/ @REPLACE_TEAM\n", encoding="utf-8")
    tg._check_codeowners(g, root / "kit", root, "в репозитории документации")
    assert any(ln.startswith("✗ [CORE-04] CODEOWNERS (CODEOWNERS): плейсхолдер") for ln in g.render())


def test_manifest_without_team_warned(tmp_path):
    mf = dict(_MF, teamInfo={"projectType": "ECO_AN", "platform": False})
    g = _gate(_out(tmp_path, mf=mf))
    warn = [ln for ln in g.render() if ln.startswith("⚠ [SDLC-07]")]
    assert warn == ["⚠ [SDLC-07] gpb-manifest.json: teamInfo: нет или пусто обязательных полей — team"]
    assert g.blockers == 0


def test_manifest_placeholder_blocks_project_type_warned(tmp_path):
    """Пакет П3 ОНБ-В (решение владельца 2026-11-09): плейсхолдер «REPLACE_…» — ✗ SDLC-07; тип
    вне словаря — ⚠ как прежде."""
    mf = dict(_MF, emailItLeader="REPLACE_ME", teamInfo={"team": "REPLACE_TEAM",
                                                          "projectType": "EAN", "platform": False})
    lines = _gate(_out(tmp_path, mf=mf)).render()
    err = [ln for ln in lines if ln.startswith("✗ [SDLC-07]")]
    warn = [ln for ln in lines if ln.startswith("⚠ [SDLC-07]")]
    assert len(err) == 1 and len(warn) == 1, lines
    assert "плейсхолдер в полях ×2: emailItLeader=REPLACE_ME, teamInfo.team=REPLACE_TEAM" in err[0]
    assert "teamInfo.projectType «EAN» вне словаря схемы" in warn[0]


def test_manifest_null_contact_not_blocking(tmp_path):
    """НЕсрабатывание (П3 п. 2): null в контактном поле — норма стандарта, ни ✗, ни ⚠."""
    mf = dict(_MF, emailItLeader=None)
    lines = _gate(_out(tmp_path, mf=mf)).render()
    assert not [ln for ln in lines if ln.startswith(("✗ [SDLC-07]", "⚠ [SDLC-07]"))], lines


def test_manifest_without_teaminfo_warned(tmp_path):
    mf = {k: v for k, v in _MF.items() if k != "teamInfo"}
    warn = [ln for ln in _gate(_out(tmp_path, mf=mf)).render() if ln.startswith("⚠ [SDLC-07]")]
    assert warn and "секции teamInfo нет" in warn[0]


def test_sample_manifest_silent(tmp_path):
    # образец техбука, null в контактном поле — норма: строк нет
    lines = _gate(_out(tmp_path, mf=_MF)).render()
    assert not any(ln.startswith(("⚠ [SDLC-07]", "✗ [")) for ln in lines), lines
    assert any(ln.startswith("✓ [SDLC-07]") for ln in lines)


def test_platform_false_is_not_empty(tmp_path):
    # НЕсрабатывание: platform=false — значение, а не пустое поле
    assert tg._manifest_issues(_MF) == []
