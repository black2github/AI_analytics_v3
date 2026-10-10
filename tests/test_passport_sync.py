"""Паспорт ЭКО: сборка yaml из канона и сторож расхождений (passport_sync.py, Д-39)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import passport_sync as ps  # noqa: E402

yaml = pytest.importorskip("yaml")

_README_TPL = (
    "# Шаблон\n\n## Условные обозначения\n\n### Контуры (суффиксы в ID)\n\n| Код | З |\n|---|---|\n"
    "| **CL** | К |\n\n### Типы артефактов (префиксы ID)\n\n| Префикс | Что обозначает | Где лежит |\n"
    "|---|---|---|\n| **VIS** | Концепция | `service-vision.md` |\n| **GLO** | Глоссарий | `glossary.md` |\n"
    "| **F-CL / F-BNK** | Фича | `brd/features/` |\n| **US / FR / NFR / RR** | внутри | внутри фич |\n"
    "| **PROC** | Процесс | `srs/process/` |\n| **SM** | Статусная модель | `srs/process/status-model.md` |\n"
    "| **FUN** | Функция | `srs/function/` |\n| **CTL / CTL-GRP** | Контроль | `srs/control/` |\n"
    "| **INTC** | Метод | `srs/internal-contract/` |\n| **LIBC** | Библиотека | `srs/lib-contract/` |\n"
    "| **CHD** | Агент | `srs/agent/` |\n\nВнутри экранных форм дополнительно: **FLD-N**.\n\n"
    "### Поля frontmatter\n\n| Поле | Назначение |\n|---|---|\n| `title` | имя |\n\n## Границы\n")

_CATALOG = ('[{"code":"a","repo":"https://gitlab.gboteam.ru/EAN/docs-a"},'
            '{"code":"b","repo":"https://gitlab.gboteam.ru/EAS/src-b"}]')


def make_canon(tmp_path: Path) -> Path:
    c = tmp_path / "canon"
    (c / "_meta/templates").mkdir(parents=True)
    (c / "_meta/templates/docs-readme.md").write_text(_README_TPL, encoding="utf-8")
    (c / "_meta/templates/function.md").write_text("---\nid: FUN-CL-NN\n---\n", encoding="utf-8")
    (c / "_meta/templates/data-model.md").write_text("---\nid: ENT-001\n---\n", encoding="utf-8")
    (c / "_meta/templates/contract-call.md").write_text("---\nid: EXTINT-<AS>-NNN\n---\n", encoding="utf-8")
    (c / "_meta/services.json").write_text(_CATALOG, encoding="utf-8")
    return c


def make_passport(tmp_path: Path, md: str, yml: dict) -> Path:
    d = tmp_path / "passport"
    d.mkdir()
    (d / "docs-kit-layout.md").write_text(md, encoding="utf-8")
    (d / "docs-kit-layout.yaml").write_text(yaml.safe_dump(yml, allow_unicode=True), encoding="utf-8")
    return d


def test_build_from_canon_homes(tmp_path):
    layout = ps.build_layout(make_canon(tmp_path))
    assert layout["ids"]["prefixes"][:3] == ["vis", "glo", "f"]
    assert "us" not in layout["ids"]["prefixes"] and "extint" in layout["ids"]["prefixes"]
    skills = {s["path"]: s["skill"] for s in layout["skills_by_path"] if s["skill"] != "api-asyncapi"}
    assert skills["srs/function/"] == "functions" and skills["srs/process/status-model.md"] == "status-model"
    paths = [s["path"] for s in layout["skills_by_path"]]
    assert paths.index("srs/process/status-model.md") < paths.index("srs/process/")
    assert [c["path"] for c in layout["canon_types"]] == ["srs/internal-contract/", "srs/lib-contract/", "srs/agent/"]
    assert layout["ids"]["widths"] == {"ent": 3, "extint": 3, "fun": 2}
    assert layout["repos"]["docs_group"] == "EAN" and layout["repos"]["src_group"] == "EAS"
    assert layout["links"]["code_ref"] == "HEAD" and "ECO_BE/ms-<service-id>" in layout["links"]["code_contracts"]
    text = ps.dump_layout(layout)
    assert text.startswith("# Машинная раскладка")
    assert yaml.safe_load(text.split("\n\n", 1)[1])["kit"] == "eco"


def test_check_reports_known_drifts(tmp_path):
    canon = make_canon(tmp_path)
    md = ("# Паспорт\n\n| `ECO_BE/ms-<service>` | api-specification |\n"
          "| `ECO_BE/lib-api-<service>` | `asyncapi/jms.yaml` (AsyncAPI 3.0, JMS) |\n\n"
          "## 7\n- **в репозиторий кода** — **явная ветка** (`…/-/blob/develop/api-specification/…`)\n\n"
          "## 8\n- `version` — необязательное историческое поле\n- Поле `title` — в новые документы не добавлять.\n"
          "- Закрытый набор `type` для новых документов: `vision | function`. В существующих встречаются другие "
          "(`internal-contract`) — читай как есть.\n\n"
          "## 3\nтаблица контуров в README «Условные обозначения», таблица «Подсервисы»\n")
    yml = {"traceability": {"file": "traceability-matrix.md", "api_coverage_section": "Покрытие: API ↔ SRS",
                            "business_registry_section": "Реестр ID бизнес-слоя"},
           "layers": [{"path": "brd/"}, {"path": "asyncapi/"}],
           "skills_by_path": [{"path": "srs/function/", "skill": "functions"},
                              {"path": "srs/control/", "skill": "validations"}],
           "ids": {"prefixes": ["f", "fun", "ctl", "proc", "sm", "intc", "ins", "scrp"],
                   "segments": ["cl", "bnk", "sys", "grp", "ext", "int", "cdn", "ausn"]}}
    contracts = tmp_path / "contracts"
    (contracts / "cdn").mkdir(parents=True)
    (contracts / "f1").mkdir()
    rep = ps.check_passport(canon, make_passport(tmp_path, md, yml), contracts)
    rows = {(m, t): (pp, c, h) for m, t, pp, c, h in rep.rows}
    assert "строка 4" in rows[("≠", "Место AsyncAPI")][0]
    assert "строка 7" in rows[("≠", "Реф в ссылке на репозиторий кода")][0]
    assert rows[("≠", "Префиксы ID в yaml")][0] == "нет CHD, EXTINT, GLO, LIBC, VIS"
    assert rows[("i", "Префиксы сверх канона")][0].startswith("INS, SCRP")
    assert ("i", "Тип `internal-contract`") in rows and ("i", "Поле frontmatter `title`") in rows
    assert ("=", "README «Условные обозначения»") in rows and ("=", "README «Подсервисы»") in rows
    assert rows[("≠", "Путь → навык `srs/control/`")][:2] == ("validations", "controls")
    assert rows[("≠", "Коды внешних АС")][0] == "ausn, cdn"
    assert ("i", "Реестр ID матрицы") in rows
    assert rep.diffs == 5
    lines = rep.render()
    assert lines[0].startswith("| Статус | Тема | В паспорте платформы | В стандарте ЭКО и каноне миграции | Дом факта |")
    statuses = [l.split("|")[1].strip()[0] for l in lines[2:] if l.startswith("|")]
    assert statuses == sorted(statuses, key={"≠": 0, "i": 1, "=": 2}.get)
    assert lines[-1].startswith("ИТОГ: расхождений 5, объявленных отличий"), lines[-1]


def test_check_clean_passport(tmp_path):
    canon = make_canon(tmp_path)
    built = ps.build_layout(canon)
    md = ("| `ECO_BE/ms-<service>` | `api-specification/` |\n- в репозиторий кода — `HEAD`\n"
          "README «Условные обозначения», «Подсервисы»\n- `version` — историческое\n")
    rep = ps.check_passport(canon, make_passport(tmp_path, md, built))
    assert rep.diffs == 0, "\n".join(rep.render())


def test_missing_passport(tmp_path):
    canon = make_canon(tmp_path)
    rep = ps.check_passport(canon, tmp_path / "nope")
    assert rep.diffs == 1 and "нет docs-kit-layout.md" in rep.rows[0][2]
