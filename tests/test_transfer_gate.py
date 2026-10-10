"""Гейт переноса src → docs (transfer_gate.py, решение владельца 2026-10-10, P-02)."""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402

_README = ("# К\n\n## Условные обозначения\n\n| Префикс | Что |\n|---|---|\n"
           "| **VIS** | Концепция |\n| **GLO** | Глоссарий |\n| **FUN** | Функция |\n\n"
           "### Поля frontmatter\n\n| Поле | Назначение |\n|---|---|\n| `title` | наименование |\n\n"
           "## Разделы\n")
_CARD = ("---\nid: FUN-CL-01\ntitle: 'Ф'\ntype: function\nservice: X\n---\n\n"
         "# Ф\n\nсм. [матрицу](../../traceability-matrix.md)\n")
_MATRIX = ("# Матрица\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n"
           "|---|---|---|---|\n| FUN-CL-01 | function | Ф | srs/function/f1.md |\n"
           "| VIS-001 | vision | В | service-vision.md |\n| GLO-001 | glossary | Г | glossary.md |\n\n"
           "## 3. Покрытие: API ↔ SRS\n\n| Операция | Артефакты SRS |\n| --- | --- |\n")
_OQ_CLOSED = "# Открытые вопросы\n\n## OQ-001. Вопрос\n- **Статус:** закрыт\n- **Решение:** да\n"
_OQ_OPEN = _OQ_CLOSED + "\n## OQ-002. Ещё\n- **Статус:** открыт\n"


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_src(tmp_path: Path, oq: str = _OQ_CLOSED, matrix: str = _MATRIX) -> Path:
    src = tmp_path / "src-x"
    _w(src / "docs/README.md", _README)
    _w(src / "docs/service-vision.md", "---\nid: VIS-001\ntype: vision\n---\n# В\n")
    _w(src / "docs/glossary.md", "---\nid: GLO-001\ntype: glossary\n---\n# Г\n")
    _w(src / "docs/traceability-matrix.md", matrix)
    _w(src / "docs/srs/function/f1.md", _CARD)
    _w(src / "open-questions.md", oq)
    _w(src / "prompts/p1.md", "промпт")
    _w(src / "sandbox/x.txt", "x")
    _w(src / "docs/feedback.md", "# FB\n")
    return src


def _run(src: Path, **kw):
    kw.setdefault("no_validator", True)
    return tg.run_gate(src, **kw)


def test_ready_without_validator(tmp_path):
    lines, ready, data = _run(make_src(tmp_path))
    assert ready, "\n".join(lines)
    assert lines[-1].startswith("ИТОГ: READY — блокеров 0")
    assert data["verdict"] == "READY"
    assert any("[CORE-20] открытых вопросов нет" in l for l in lines)
    assert any("[SDLC-04] матрица: раздел «Покрытие: API ↔ SRS» есть" in l for l in lines)
    assert any("[ВАЛИДАТОР] валидатор платформы отключён" in l for l in lines)


def test_open_question_blocks(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path, oq=_OQ_OPEN))
    assert not ready
    assert any(l.startswith("✗ [CORE-20] открытые вопросы: 1 (OQ-002)") for l in lines)
    assert lines[-1].startswith("ИТОГ: NOT READY")


def test_missing_api_section_blocks(tmp_path):
    m = _MATRIX.split("## 3.")[0]
    lines, ready, _ = _run(make_src(tmp_path, matrix=m))
    assert not ready
    assert any(l.startswith("✗ [SDLC-04] матрица без раздела «Покрытие: API ↔ SRS»") for l in lines)


def test_api_dir_blocks(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/api/x-openapi.yaml", "openapi: 3.0.1\n")
    lines, ready, _ = _run(src)
    assert not ready
    assert any(l.startswith("✗ [ПЕРЕНОС] контракты в комплекте (api/") for l in lines)


def test_service_files_not_staged(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/open-questions.md", _OQ_CLOSED)
    _w(src / "docs/srs/function/f1.filled.md", "x")
    keep = tmp_path / "staged"
    lines, ready, _ = _run(src, keep=keep)
    assert ready, "\n".join(lines)
    assert not (keep / "open-questions.md").exists()
    assert not (keep / "feedback.md").exists()
    assert not (keep / "srs/function/f1.filled.md").exists()
    assert not (keep / "prompts").exists()
    assert (keep / "srs/function/f1.md").is_file() and (keep / "README.md").is_file()
    assert any("служебных пропущено 3" in l for l in lines)


def test_out_only_when_ready(tmp_path):
    out = tmp_path / "docs-x"
    out.mkdir()
    lines, ready, _ = _run(make_src(tmp_path, oq=_OQ_OPEN), out=out)
    assert not ready and not any(out.iterdir())
    assert any(l.startswith("✗ --out пропущен") for l in lines)
    lines, ready, _ = _run(make_src(tmp_path / "b"), out=out)
    assert ready and (out / "traceability-matrix.md").is_file()
    assert any("перенесено в" in l and "коммит и MR — человек" in l for l in lines)


def test_out_missing_dir_fails(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path), out=tmp_path / "nope")
    assert not ready and any("--out: каталог не существует" in l for l in lines)


def test_missing_readme_blocks_and_legend_warns(tmp_path):
    src = make_src(tmp_path)
    (src / "docs/README.md").unlink()
    lines, ready, _ = _run(src)
    assert not ready and any(l.startswith("✗ [SDLC-08] README.md комплекта отсутствует") for l in lines)
    _w(src / "docs/README.md", "# К\n\n## Разделы\n")
    lines, ready, _ = _run(src)
    assert ready and any(l.startswith("⚠ [SDLC-08] README.md без раздела") for l in lines)


def test_selfcheck_defect_blocks_with_criterion(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/srs/function/f1.md", _CARD.replace("../../traceability-matrix.md", "../none.md"))
    lines, ready, _ = _run(src)
    assert not ready
    assert any(l.startswith("✗ [CORE-06] битые относительные ссылки") for l in lines)


def test_validator_missing_blocks(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path), no_validator=False,
                           validator=tmp_path / "no-such.py")
    assert not ready and any(l.startswith("✗ [ВАЛИДАТОР] валидатор платформы не найден") for l in lines)


_HAS_GIT = shutil.which("git") is not None and tg._DEFAULT_VALIDATOR.is_file()


@pytest.mark.skipif(not _HAS_GIT, reason="нужны git и копия валидатора платформы")
def test_validator_clean_kit_and_bom_example(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path), no_validator=False)
    assert ready, "\n".join(lines)
    assert any("[ВАЛИДАТОР] валидатор платформы: ошибок нет" in l for l in lines)
    src = make_src(tmp_path / "b")
    _w(src / "docs/srs/function/f1.md",
       _CARD.replace("см.", "пример [r](examples/r.json); см."))
    p = src / "docs/srs/function/examples/r.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\xef\xbb\xbf{}")
    lines, ready, _ = _run(src, no_validator=False)
    assert not ready
    assert any(l.startswith("✗ [FMT-01] структурный файл") and "BOM" in l for l in lines)
    assert any("E_STRUCTURED_FILE_INVALID" in l and "[FMT-01]" in l for l in lines)


_DEBT_ROW = ("\n## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n"
             "| FUN-CL-01 | — | нет целевого артефакта data-model «Карта» у владельца cards — требуется заход create-data-model |\n"
             "| FUN-CL-01 | — | нет целевого артефакта process «Выпуск» — требуется заход create-process |\n")
_DEBT_RULE = ("### Долги по ссылкам\n\n| Поле поручения | Откуда |\n|---|---|\n"
              "| Формулировка | строка |\n\n")


def test_debts_require_reading_rule_in_readme(tmp_path):
    src = make_src(tmp_path, matrix=_MATRIX + _DEBT_ROW)
    # имена целей долгов упомянуты в карточке дословно — иначе долг неисполним (✗ прибора)
    _w(src / "docs/srs/function/f1.md", _CARD.replace("см.", "использует «Карта» и «Выпуск»; см."))
    lines, ready, _ = _run(src)
    assert not ready
    assert any(l.startswith("✗ [CORE-20] перенесённые долги: 2, из них межсервисных 1")
               and "README не объясняет" in l for l in lines), "\n".join(lines)
    _w(src / "docs/README.md", _README.replace("## Разделы\n", _DEBT_RULE + "## Разделы\n"))
    lines, ready, _ = _run(src)
    assert ready, "\n".join(lines)
    assert any(l.startswith("✓ [CORE-20] перенесённые долги: 2, из них межсервисных 1") for l in lines)


def test_no_debts_no_line(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path))
    assert ready and not any("перенесённые долги" in l for l in lines)
