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
    assert any("[CORE-20] открытых вопросов без долга нет" in l for l in lines)
    assert any("[SDLC-04] раздел есть" in l for l in lines)
    assert any("[ВАЛИДАТОР] валидатор платформы отключён" in l for l in lines)


def test_open_question_blocks(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path, oq=_OQ_OPEN))
    assert not ready
    assert any(l.startswith("✗ [CORE-20] открытые вопросы без долга в матрице: 1 (OQ-002)") for l in lines)
    assert lines[-1].startswith("ИТОГ: NOT READY")


def test_missing_api_section_blocks(tmp_path):
    m = _MATRIX.split("## 3.")[0]
    lines, ready, _ = _run(make_src(tmp_path, matrix=m))
    assert not ready
    assert any(l.startswith("✗ [SDLC-04] раздела нет") for l in lines)


def test_api_dir_blocks(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/api/x-openapi.yaml", "openapi: 3.0.1\n")
    lines, ready, _ = _run(src)
    assert not ready
    assert any(l.startswith("✗ [TRF-03] контракты в комплекте (api/") for l in lines)


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
    assert any("служебных файлов миграции не перенесено: 3" in l for l in lines)


def _target(tmp_path: Path) -> Path:
    out = tmp_path / "docs-x"
    out.mkdir()
    _w(out / "CODEOWNERS", "# владельцы\n* @team-cc\n")
    _w(out / "gpb-manifest.json", '{"service-id": "x", "owner": "team-cc"}')
    return out


def test_out_only_when_ready(tmp_path):
    out = _target(tmp_path)
    lines, ready, _ = _run(make_src(tmp_path, oq=_OQ_OPEN), out=out)
    assert not ready and not (out / "traceability-matrix.md").exists()
    assert any(l.startswith("✗ --out пропущен") for l in lines)
    lines, ready, _ = _run(make_src(tmp_path / "b"), out=out)
    assert ready and (out / "traceability-matrix.md").is_file()
    assert any("перенесено в" in l and "коммит и MR — человек" in l for l in lines)


def test_out_missing_dir_fails(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path), out=tmp_path / "nope")
    assert not ready and any("каталог назначения не существует" in l for l in lines)


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
    assert any("[ВАЛИДАТОР] ошибок нет" in l for l in lines)
    src = make_src(tmp_path / "b")
    _w(src / "docs/srs/function/f1.md",
       _CARD.replace("см.", "пример [r](examples/r.json); см."))
    p = src / "docs/srs/function/examples/r.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\xef\xbb\xbf{}")
    lines, ready, data = _run(src, no_validator=False)
    assert not ready
    assert any(l.startswith("✗ [FMT-01] структурный файл") and "BOM" in l for l in lines)
    assert any(r["criterion"] == "FMT-01" and r["check"] == "валидатор E_STRUCTURED_FILE_INVALID"
               for r in data["lines"])


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


def test_table_format_grouped_with_legend(tmp_path):
    lines, ready, data = _run(make_src(tmp_path, oq=_OQ_OPEN), fmt="table")
    assert lines[0] == "| Статус | Критерий | Проверка | Результат |"
    rows = [l for l in lines[2:] if l.startswith("|")]
    statuses = [r.split("|")[1].strip()[0] for r in rows]
    assert statuses == sorted(statuses, key={"✗": 0, "⚠": 1, "i": 2, "✓": 3}.get)
    assert rows[0].startswith("| ✗ блокер | CORE-20 | открытые вопросы |")
    assert any(l.startswith("ИТОГ: NOT READY") for l in lines)
    assert lines[-1].startswith("Критерии — чек-лист DoR") and "TRF-01…05 —" in lines[-1]
    assert data["lines"][0]["check"] == "комплект в целевой раскладке"
    assert data["lines"][0]["criterion"] == "TRF-01" and data["lines"][1]["criterion"] == "TRF-02"


def test_report_file(tmp_path):
    src = make_src(tmp_path)
    lines, ready, data = _run(src, fmt="table")
    rep = tmp_path / "out" / "gate.md"
    tg.write_report(rep, src, lines, data)
    txt = rep.read_text(encoding="utf-8")
    assert txt.startswith("# Гейт переноса: src-x") and "| Статус | Критерий |" in txt
    assert "Срез канона по профилю: `не указан`" in txt



def test_glossary_absent_ok_in_domain_mode(tmp_path):
    # домен с режимом «Глоссарий: доменный» (объявлен в профиле src): отсутствие
    # glossary.md в комплекте — ✓, не ⚠; без объявления — ⚠ как прежде
    src = make_src(tmp_path)
    (src / "docs/glossary.md").unlink()
    lines, _ok, _ = _run(src)
    assert any("glossary.md отсутствует" in ln for ln in lines), lines
    _w(src / "README.md", "# src\n\nГлоссарий: доменный\n")
    lines, _ok, _ = _run(src)
    assert any("glossary.md в комплекте нет по правилу" in ln for ln in lines), lines
    assert not any("glossary.md отсутствует" in ln for ln in lines)


def test_oq_translated_to_debt_not_blocker(tmp_path):
    matrix = _MATRIX + ("\n## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n"
                        "| FUN-CL-01 | — | нет целевого артефакта process «Выпуск» — требуется заход create-process; вопрос OQ-002 |\n")
    src = make_src(tmp_path, oq=_OQ_OPEN, matrix=matrix)
    _w(src / "docs/srs/function/f1.md", _CARD.replace("см.", "использует «Выпуск»; см."))
    _w(src / "docs/README.md", _README.replace("## Разделы\n", "### Долги по ссылкам\n\nправило\n\n## Разделы\n"))
    lines, ready, data = _run(src)
    assert ready, "\n".join(lines)
    assert any(l.startswith("i [CORE-20] переведены в долги матрицы: 1 (OQ-002)") for l in lines)
    assert data["debts"][0]["oq"] == "OQ-002" and data["debts"][0]["owner"] == "аналитик сервиса"


_ISSUE_ROW = ("| FUN-CL-01 | — | долг открытый вопрос: «Что такое сегмент» — причина: определения нет; "
              "ответственный: аналитик сервиса X; ограничение: шаги доступа к сегменту; "
              "закрытие: определение в глоссарии; источник: OQ-002 |\n")
_DEBT_HEAD = "\n## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n"


def test_oq_translated_to_issue_debt_with_fields(tmp_path):
    # НЕсрабатывание: открытый вопрос переведён строкой второго формата со всеми полями
    src = make_src(tmp_path, oq=_OQ_OPEN, matrix=_MATRIX + _DEBT_HEAD + _ISSUE_ROW)
    _w(src / "docs/README.md", _README.replace("## Разделы\n", _DEBT_RULE + "## Разделы\n"))
    lines, ready, data = _run(src)
    assert ready, "\n".join(lines)
    assert any(l.startswith("i [CORE-20] переведены в долги матрицы: 1 (OQ-002)") for l in lines)
    assert any(l.startswith("✓ [CORE-20] перенесённые долги: 1, из них межсервисных 0, без отсутствующей цели 1")
               for l in lines), "\n".join(lines)
    d = data["debts"][0]
    assert d["kind"] == "открытый вопрос" and d["owner"] == "аналитик сервиса X"
    assert d["closure"] == "определение в глоссарии" and d["oq"] == "OQ-002"


def test_oq_issue_debt_incomplete_blocks(tmp_path):
    # срабатывание: строка второго формата без ограничения и закрытия — блокер с перечнем полей
    row = ("| FUN-CL-01 | — | долг открытый вопрос: «Что такое сегмент» — причина: нет; "
           "ответственный: аналитик; источник: OQ-002 |\n")
    src = make_src(tmp_path, oq=_OQ_OPEN, matrix=_MATRIX + _DEBT_HEAD + row)
    _w(src / "docs/README.md", _README.replace("## Разделы\n", _DEBT_RULE + "## Разделы\n"))
    lines, ready, _ = _run(src)
    assert not ready
    bad = [l for l in lines if l.startswith("✗ [CORE-20] строки долга из вопроса неполны")]
    assert bad and "OQ-002 — нет полей ограничение, закрытие" in bad[0], "\n".join(lines)
    assert not any("открытые вопросы без долга" in l for l in lines)


def test_debt_register_affected_and_closure(tmp_path):
    # «Затронуто»: карточка, ссылающаяся на FROM-ID, попадает в реестр; условие закрытия по виду
    src = make_src(tmp_path, matrix=_MATRIX.replace(
        "| VIS-001 |", "| FUN-CL-02 | function | Ф2 | srs/function/f2.md |\n| VIS-001 |") + _DEBT_ROW)
    _w(src / "docs/srs/function/f1.md", _CARD.replace("см.", "использует «Карта» и «Выпуск»; см."))
    _w(src / "docs/srs/function/f2.md",
       "---\nid: FUN-CL-02\ntitle: 'Ф2'\ntype: function\nservice: X\n---\n\n# Ф2\n\nсм. [Ф](f1.md)\n")
    _w(src / "docs/README.md", _README.replace("## Разделы\n", _DEBT_RULE + "## Разделы\n"))
    lines, ready, data = _run(src, fmt="table")
    assert ready, "\n".join(lines)
    rep = tmp_path / "r.md"
    tg.write_report(rep, src, lines, data)
    assert data["debts"][0]["affected"] == ["FUN-CL-02"]
    assert data["debts"][0]["kind"] == "нет цели" and "содержание цели проверено" in data["debts"][0]["closure"]
    text = rep.read_text(encoding="utf-8")
    assert "| Затронуто (ссылаются на FROM-ID) | Условие закрытия |" in text
    assert "| 1: FUN-CL-02 |" in text and "без отсутствующей цели 0" in text
    assert "Автор проверки:" in text


def test_types_outside_platform_set_listed(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/srs/internal-contract/README.md", "---\nid: INTC-000\ntype: internal-contract\nservice: X\n---\n# Р\n")
    _w(src / "docs/srs/internal-contract/intc-001.md", "---\nid: INTC-001\ntype: internal-contract\nservice: X\n---\n# М\n")
    _w(src / "docs/traceability-matrix.md", _MATRIX.replace("| VIS-001 |", "| INTC-000 | internal-contract | Р | srs/internal-contract/README.md |\n| INTC-001 | internal-contract | М | srs/internal-contract/intc-001.md |\n| VIS-001 |"))
    _w(src / "docs/README.md", _README.replace("| **FUN** | Функция |", "| **FUN** | Функция |\n| **INTC** | Метод |"))
    lines, ready, _ = _run(src)
    assert any(l.startswith("i [TRF-04] типы вне закрытого набора платформы: internal-contract ×2 — объявлены в README") for l in lines), "\n".join(lines)
    # пустой раздел API при наличии INTC — предупреждение SDLC-04
    assert any(l.startswith("⚠ [SDLC-04] раздел есть, но пуст, а в комплекте 2 описаний") for l in lines)


def test_txt_example_that_parses_is_warned(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/srs/function/examples/r.txt", '{"a": 1}')
    _w(src / "docs/srs/function/examples/frag.txt", '{"a": 1,')
    lines, _, _ = _run(src)
    hits = [l for l in lines if l.startswith("⚠ [FMT-01] пример помечен фрагментом")]
    assert len(hits) == 1 and "examples/r.txt" in hits[0] and "frag.txt" not in hits[0]


def test_catalog_without_readme_warned(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/srs/data-model/e1.md", "---\nid: ENT-001\ntype: data-model\nservice: X\n---\n# С\n")
    _w(src / "docs/traceability-matrix.md", _MATRIX.replace("| VIS-001 |", "| ENT-001 | data-model | С | srs/data-model/e1.md |\n| VIS-001 |"))
    lines, _, _ = _run(src)
    assert any(l.startswith("⚠ [SDLC-08] каталоги с карточками без README-реестра: 2 (srs/data-model, srs/function)") for l in lines), "\n".join(lines)


def test_external_links_listed(tmp_path):
    src = make_src(tmp_path)
    _w(src / "docs/srs/function/f1.md", _CARD.replace("см.", "[рег](https://cbr.ru/x) [рег2](https://cbr.ru/y) см."))
    lines, _, _ = _run(src)
    assert any(l.startswith("i [CORE-09] внешних ссылок 2: cbr.ru ×2") for l in lines)


def test_out_target_without_codeowners_blocks(tmp_path):
    out = tmp_path / "docs-x"
    out.mkdir()
    lines, ready, _ = _run(make_src(tmp_path), out=out)
    assert not ready and any(l.startswith("✗ [CORE-04] CODEOWNERS") for l in lines)
    assert any(l.startswith("⚠ [SDLC-07] gpb-manifest.json") for l in lines)


def test_without_out_target_checks_are_informational(tmp_path):
    lines, ready, _ = _run(make_src(tmp_path))
    assert ready and any(l.startswith("i [SDLC-07] CODEOWNERS и gpb-manifest.json проверяются") for l in lines)


def test_report_sections(tmp_path):
    src = make_src(tmp_path)
    lines, ready, data = _run(src, fmt="table")
    rep = tmp_path / "gate.md"
    tg.write_report(rep, src, lines, data)
    txt = rep.read_text(encoding="utf-8")
    assert "Вид допуска: **техническое подключение сервиса**" in txt
    assert "## Реестр долгов" in txt and "Долгов в матрице нет." in txt
    assert "## Ручная часть протокола до подключения" in txt and "**CORE-01, CORE-02**" in txt
    assert "Критерии раздела 1 без автоматической проверки" in txt and "**SDLC-03**" in txt
