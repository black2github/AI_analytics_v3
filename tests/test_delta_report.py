"""Отчёт дельты режима «изменение по постановке» (delta_report.py, Д-43, срез С2):
изменённые файлы, идентификаторы, матрица, затронутые карточки, заготовка фактов,
открытые вопросы, выбор постановки, база, --out/--json."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import delta_report as dr  # noqa: E402

_README = "# Комплект x\n\n## Разделы\n"
_MATRIX = ("# Матрица\n\n## 1. Реестр ID\n\n| ID | Тип | Наименование | Файл |\n|---|---|---|---|\n"
           "| SCR-CL-02 | screen-form | Форма | srs/screen-form/scr-cl-02.md |\n"
           "| ENT-001 | data-model | Клиент | srs/data-model/ent-001.md |\n"
           "| PRN-001 | print-form | Печать | srs/print-form/prn-001.md |\n\n"
           "## 2. Связи\n\n| От | К | Связь |\n|---|---|---|\n"
           "| SCR-CL-02 | ENT-001 | поля формы → атрибуты |\n\n"
           "## 5. Долги по ссылкам\n\n| От | — | Долг |\n|---|---|---|\n")
_SCR = ("---\nid: SCR-CL-02\ntype: screen-form\nservice: x\ntitle: 'Форма'\n---\n\n# Форма\n\n"
        "см. [Клиент](../data-model/ent-001.md)\n\n## Поля\n\n| Поле | Тип | Обязательность |\n"
        "|---|---|---|\n| Имя | строка | да |\n\n### FLD-1. Имя\n\n- **Формат:** строка\n")
_ENT = ("---\nid: ENT-001\ntype: data-model\nservice: x\ntitle: 'Клиент'\n---\n\n# Клиент\n\n"
        "| Атрибут | Тип |\n|---|---|\n| name | string |\n")
# печатная форма ссылается на экранную — «затронуто», сама не меняется
_PRN = ("---\nid: PRN-001\ntype: print-form\nservice: x\ntitle: 'Печать'\n---\n\n# Печать\n\n"
        "поля — см. [форму](../screen-form/scr-cl-02.md)\n")
_CTL = ("---\nid: CTL-CL-001\ntype: control\nservice: x\ntitle: 'Контроль даты'\n---\n\n"
        "# Контроль даты\n\nсм. [форму](../screen-form/scr-cl-02.md)\n\n"
        "### CTL-001. Дата обязательна\n\n- **Сообщение:** «Укажите дату рождения»\n")
_CTL_ROW = "| CTL-CL-001 | control | Контроль даты | srs/control/ctl-cl-001.md |\n"
_LINK_ROW = "| CTL-CL-001 | SCR-CL-02 | контроль поля |\n"
_DEBT_ROW = ("| SCR-CL-02 | — | долг открытый вопрос: «Нужен ли контроль возраста» — причина: в "
             "постановке нет; ответственный: аналитик x; ограничение: контроль возраста не "
             "разрабатывать; закрытие: ответ аналитика; источник: OQ-001 |\n")
_TASK = ("---\ntype: task\ntask: ECO-123\nservice: x\ncreated: 2026-10-15\n---\n\n"
         "# ECO-123. Поле даты рождения\n\n## Постановка (дословно)\n\n"
         "- **T-ECO-123-01** (2026-10-15, аналитик): добавить поле «Дата рождения»\n"
         "- **T-ECO-123-02** (2026-10-15, аналитик): текст ошибки — «Укажите дату рождения»\n\n"
         "## Вопросы и ответы\n\n| № | Вопрос агента | Ответ |\n|---|---|---|\n"
         "| 1 | Тип атрибута birthDate? | T-ECO-123-02 |\n"
         "| 2 | Нужен ли контроль возраста? | — (долг «открытый вопрос», ответственный аналитик) |\n")
_SCR_ADD = "\n| Дата рождения | дата | да |\n\n### FLD-3. Дата рождения\n\n- **Формат:** ДД.ММ.ГГГГ\n"


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=str(repo), check=True, capture_output=True)


def make_repo(tmp_path: Path, branch: str = "master") -> Path:
    """Репозиторий документации: комплект в корне, базовый коммит на ветке branch."""
    repo = tmp_path / "docs-x"
    _w(repo / "README.md", _README)
    _w(repo / "traceability-matrix.md", _MATRIX)
    _w(repo / "srs/screen-form/scr-cl-02.md", _SCR)
    _w(repo / "srs/data-model/ent-001.md", _ENT)
    _w(repo / "srs/print-form/prn-001.md", _PRN)
    _git(repo, "init", "-q", "-b", branch)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def make_delta(repo: Path, registry_row: str = _CTL_ROW, debt_row: str = _DEBT_ROW,
               task: str = _TASK) -> Path:
    """Типовая дельта: правка формы (FLD-3), новая карточка контроля со строкой
    реестра, связь, долг «открытый вопрос», постановка tasks/ECO-123.md."""
    scr = repo / "srs/screen-form/scr-cl-02.md"
    _w(scr, scr.read_text(encoding="utf-8") + _SCR_ADD)
    _w(repo / "srs/control/ctl-cl-001.md", _CTL)
    m = (repo / "traceability-matrix.md").read_text(encoding="utf-8")
    m = m.replace("| PRN-001 | print-form | Печать | srs/print-form/prn-001.md |\n",
                  "| PRN-001 | print-form | Печать | srs/print-form/prn-001.md |\n" + registry_row)
    m = m.replace("| SCR-CL-02 | ENT-001 | поля формы → атрибуты |\n",
                  "| SCR-CL-02 | ENT-001 | поля формы → атрибуты |\n" + _LINK_ROW)
    m += debt_row
    _w(repo / "traceability-matrix.md", m)
    if task:
        _w(repo / "tasks/ECO-123.md", task)
    return repo


def _build(repo: Path, **kw) -> dict:
    data, err = dr.build(repo, **kw)
    assert err is None, err
    return data


def _file(data: dict, path: str) -> dict:
    return next(f for f in data["files"] if f["path"] == path)


# 1. изменённые файлы --------------------------------------------------------------

def test_changed_files_statuses_and_task_line(tmp_path):
    repo = make_delta(make_repo(tmp_path))
    (repo / "srs/print-form/prn-001.md").unlink()  # снятая карточка
    data = _build(repo)
    assert _file(data, "srs/control/ctl-cl-001.md")["action"] == "создан"
    assert _file(data, "srs/control/ctl-cl-001.md")["id"] == "CTL-CL-001"
    assert _file(data, "srs/screen-form/scr-cl-02.md")["action"] == "изменён"
    assert _file(data, "srs/screen-form/scr-cl-02.md")["type"] == "screen-form"
    snat = _file(data, "srs/print-form/prn-001.md")
    assert snat["action"] == "снят" and snat["id"] == "PRN-001" and snat["kind"] == "card"
    task = _file(data, "tasks/ECO-123.md")
    assert task["kind"] == "task" and task["action"] == "создан"
    text = dr.render(data)
    table = text.split("## Изменённые файлы")[1].split("## Идентификаторы")[0]
    rows = [l for l in table.splitlines() if l.startswith("| `")]
    assert any("`srs/control/ctl-cl-001.md` | создан | `CTL-CL-001` (control)" in r for r in rows)
    assert any("`srs/print-form/prn-001.md` | снят | `PRN-001`" in r for r in rows)
    # постановка — отдельной строкой, не в таблице карточек
    assert not any("tasks/ECO-123.md" in r for r in rows)
    assert "Постановка: `tasks/ECO-123.md` — создан, `ECO-123`." in table


def test_renamed_card_reported_with_old_path(tmp_path):
    repo = make_repo(tmp_path)
    _git(repo, "mv", "srs/print-form/prn-001.md", "srs/print-form/prn-001-new.md")
    _w(repo / "tasks/ECO-123.md", _TASK)
    data = _build(repo)
    f = _file(data, "srs/print-form/prn-001-new.md")
    assert f["action"] == "переименован" and f["old"] == "srs/print-form/prn-001.md"
    assert f["id"] == "PRN-001"
    assert "переименован (из `srs/print-form/prn-001.md`)" in dr.render(data)


# 2. идентификаторы ------------------------------------------------------------------

def test_new_id_in_registry_no_notes(tmp_path):
    # НЕсрабатывание: новый ID со строкой реестра — замечаний нет
    data = _build(make_delta(make_repo(tmp_path)))
    assert data["ids"]["new"] == ["CTL-CL-001"]
    assert data["ids"]["removed"] == []
    assert not any("вне реестра" in n or "дубль" in n for n in data["notes"])
    assert "дублей и пропусков нет" in dr.render(data)
    assert "## Замечания прибора" not in dr.render(data)


def test_new_card_without_registry_row_noted(tmp_path):
    data = _build(make_delta(make_repo(tmp_path), registry_row=""))
    assert "CTL-CL-001" in data["ids"]["outside_registry"]
    assert any(n.startswith("карточка вне реестра: `CTL-CL-001`") for n in data["notes"])
    text = dr.render(data)
    assert "## Замечания прибора" in text and "карточка вне реестра: `CTL-CL-001`" in text


def test_duplicate_registry_id_noted(tmp_path):
    data = _build(make_delta(make_repo(tmp_path), registry_row=_CTL_ROW + _CTL_ROW))
    assert data["ids"]["duplicates"] == ["CTL-CL-001"]
    assert any("дубль ID в реестре матрицы: `CTL-CL-001`" in n for n in data["notes"])


def test_registry_file_as_markdown_link_label_not_noted(tmp_path):
    # колонка «Файл» — ссылка «[ярлык](цель)»: ярлыка на диске нет, цель есть — замечания нет
    row = '| PRN-001 | print-form | Печать | [print-form/prn-001.md](srs/print-form/prn-001.md) |' + chr(10)
    repo = make_repo(tmp_path)
    _w(repo / 'traceability-matrix.md', _MATRIX.replace(
        '| PRN-001 | print-form | Печать | srs/print-form/prn-001.md |' + chr(10), row))
    _git(repo, 'commit', '-qam', 'link label')
    data = _build(make_delta(repo))
    assert 'PRN-001' not in data['ids']['missing_files']
    assert not any('без файла на диске: `PRN-001`' in n for n in data['notes'])


def test_registry_file_found_when_id_also_in_coverage_rows(tmp_path):
    # ID встречается раньше в разделе покрытия (без путей), реестр — ниже: путь берётся из реестра
    repo = make_repo(tmp_path)
    cov = '# Матрица' + chr(10) + chr(10) + '## 1. Покрытие' + chr(10) + chr(10) + '| ID | Экраны |' + chr(10) + '|---|---|' + chr(10) + '| PRN-001 | SCR-CL-02 |' + chr(10) + chr(10)
    row = '| PRN-001 | print-form | Печать | [prn-001.md](srs/print-form/prn-001.md) |' + chr(10)
    _w(repo / 'traceability-matrix.md', cov + _MATRIX.replace('# Матрица' + chr(10) + chr(10), '').replace(
        '| PRN-001 | print-form | Печать | srs/print-form/prn-001.md |' + chr(10), row))
    _git(repo, 'commit', '-qam', 'coverage first')
    data = _build(make_delta(repo))
    assert 'PRN-001' not in data['ids']['missing_files'], data['notes']


def test_affected_one_entry_per_card_id(tmp_path):
    # README с id и часть с partOf того же ID, обе изменены — одна запись «Затронуто»
    repo = make_delta(make_repo(tmp_path))
    fm = lambda head: '---' + chr(10) + head + chr(10) + 'type: control' + chr(10) + 'service: x' + chr(10) + '---' + chr(10) + chr(10)
    _w(repo / 'srs/control/README.md', fm('id: CTL-000') + '# Реестр' + chr(10) + chr(10) + 'изменён' + chr(10))
    _w(repo / 'srs/control/cards-x.md', fm('partOf: CTL-000') + '### CTL-CL-009. Новый' + chr(10))
    data = _build(repo)
    assert sum(1 for a in data['affected'] if a['id'] == 'CTL-000') == 1


def test_registry_id_without_file_noted(tmp_path):
    row = "| ENT-002 | data-model | Призрак | srs/data-model/ent-002.md |\n"
    data = _build(make_delta(make_repo(tmp_path), registry_row=_CTL_ROW + row))
    assert "ENT-002" in data["ids"]["missing_files"]
    assert any("ID реестра без файла на диске: `ENT-002`" in n for n in data["notes"])


def test_inner_ids_from_added_headings(tmp_path):
    data = _build(make_delta(make_repo(tmp_path)))
    assert data["ids"]["inner"]["SCR-CL-02"] == ["FLD-3"]
    assert data["ids"]["inner"]["CTL-CL-001"] == ["CTL-001"]
    # НЕсрабатывание: FLD-1 был в базе — не новый
    assert "FLD-1" not in data["ids"]["inner"]["SCR-CL-02"]
    assert "`SCR-CL-02`: FLD-3" in dr.render(data)


def test_deleted_card_id_removed(tmp_path):
    repo = make_delta(make_repo(tmp_path))
    (repo / "srs/print-form/prn-001.md").unlink()
    data = _build(repo)
    assert data["ids"]["removed"] == ["PRN-001"]
    assert data["ids"]["deleted_cards"] == ["PRN-001"]


# 3. матрица ---------------------------------------------------------------------------

def test_matrix_rows_grouped(tmp_path):
    data = _build(make_delta(make_repo(tmp_path)))
    added = data["matrix"]["added"]
    assert [r["id"] for r in added["registry"]] == ["CTL-CL-001"]
    assert added["registry"][0]["file"] == "srs/control/ctl-cl-001.md"
    assert added["links"] == ["| CTL-CL-001 | SCR-CL-02 | контроль поля |"]
    assert len(added["debts"]) == 1
    d = added["debts"][0]
    assert d["kind"] == "открытый вопрос" and d["responsible"] == "аналитик x"
    assert d["from"] == ["SCR-CL-02"] and d["source"] == "OQ-001"
    text = dr.render(data)
    assert "Новые строки реестра: `CTL-CL-001` (control, `srs/control/ctl-cl-001.md`)." in text
    assert "- `| CTL-CL-001 | SCR-CL-02 | контроль поля |`" in text
    assert "долг «открытый вопрос»: «Нужен ли контроль возраста» (от SCR-CL-02; ответственный: аналитик x" in text


def test_matrix_first_form_debt_and_removed_rows(tmp_path):
    repo = make_repo(tmp_path)
    row = ("| SCR-CL-02 | — | нет целевого артефакта process «Выпуск» у владельца cards — "
           "требуется заход create-process |\n")
    m = (repo / "traceability-matrix.md").read_text(encoding="utf-8")
    m = m.replace("| PRN-001 | print-form | Печать | srs/print-form/prn-001.md |\n", "") + row
    _w(repo / "traceability-matrix.md", m)
    _w(repo / "tasks/ECO-123.md", _TASK)
    data = _build(repo)
    d = data["matrix"]["added"]["debts"][0]
    assert d["kind"] == "нет цели" and d["type"] == "process" and d["name"] == "Выпуск"
    assert d["owner"] == "cards"
    assert [r["id"] for r in data["matrix"]["removed"]["registry"]] == ["PRN-001"]
    assert data["ids"]["removed"] == ["PRN-001"]
    assert "Снятые строки реестра: `PRN-001`." in dr.render(data)
    # открытым вопросом долг первой формы не считается
    assert data["questions"]["debts"] == []


def test_matrix_unchanged(tmp_path):
    repo = make_repo(tmp_path)
    _w(repo / "tasks/ECO-123.md", _TASK)
    data = _build(repo)
    assert data["matrix"]["changed"] is False
    assert "Матрица не изменена." in dr.render(data)


# 4. затронуто --------------------------------------------------------------------------

def test_affected_referrers_with_change_mark(tmp_path):
    data = _build(make_delta(make_repo(tmp_path)))
    scr = next(a for a in data["affected"] if a["id"] == "SCR-CL-02")
    refs = {r["id"]: r["changed"] for r in scr["referrers"]}
    # PRN-001 ссылается и не изменена; CTL-CL-001 ссылается и создана в этой дельте
    assert refs == {"CTL-CL-001": True, "PRN-001": False}
    # матрица и README не считаются ссылающимися
    assert "traceability-matrix" not in refs and "README" not in refs
    text = dr.render(data)
    assert "`CTL-CL-001` (изменена в этой дельте)" in text
    assert "`PRN-001` (не изменена — почему: …)" in text
    ctl = next(a for a in data["affected"] if a["id"] == "CTL-CL-001")
    assert ctl["referrers"] == []
    assert "`CTL-CL-001` (создан): ссылающихся карточек нет." in text


# 5. факты ---------------------------------------------------------------------------------

def test_facts_draft_from_diff(tmp_path):
    data = _build(make_delta(make_repo(tmp_path)))
    facts = {f["fact"]: f for f in data["facts"]}
    assert "Дата рождения \\| дата \\| да" in facts
    assert "**Формат:** ДД.ММ.ГГГГ" in facts
    assert facts["**Формат:** ДД.ММ.ГГГГ"]["where"] == "`SCR-CL-02`, FLD-3"
    assert facts["**Сообщение:** «Укажите дату рождения»"]["where"] == "`CTL-CL-001`, CTL-001"
    assert all(f["origin"] == "" for f in data["facts"])
    # НЕсрабатывание: frontmatter, разделители и шапки таблиц, старые строки не попали
    texts = list(facts)
    assert not any(t.startswith("id:") or t.startswith("type:") or "---" in t for t in texts)
    assert not any("Поле \\| Тип" in t for t in texts)
    assert not any("Имя \\| строка" in t for t in texts)
    assert data["facts_overflow"] == 0
    text = dr.render(data)
    assert "| **Формат:** ДД.ММ.ГГГГ | `SCR-CL-02`, FLD-3 |  |" in text


def test_facts_limit(tmp_path):
    repo = make_repo(tmp_path)
    rows = "".join(f"| п{i} | строка | да |\n" for i in range(dr.FACTS_LIMIT + 7))
    scr = repo / "srs/screen-form/scr-cl-02.md"
    _w(scr, scr.read_text(encoding="utf-8") + "\n" + rows)
    _w(repo / "tasks/ECO-123.md", _TASK)
    data = _build(repo)
    assert len(data["facts"]) == dr.FACTS_LIMIT and data["facts_overflow"] == 7
    assert "| …ещё 7 | | |" in dr.render(data)


# 6. открытые вопросы ----------------------------------------------------------------------

def test_open_questions_from_task_and_debts(tmp_path):
    data = _build(make_delta(make_repo(tmp_path)))
    qs = data["questions"]["questions"]
    assert [q["n"] for q in qs] == ["2"]
    assert qs[0]["question"] == "Нужен ли контроль возраста?"
    assert [d["name"] for d in data["questions"]["debts"]] == ["Нужен ли контроль возраста"]
    text = dr.render(data).split("## Открытые вопросы")[1].split("## Проверки")[0]
    assert "вопрос 2: Нужен ли контроль возраста?" in text
    assert "Тип атрибута birthDate" not in text
    assert "долг: долг «открытый вопрос»" in text


def test_no_open_questions(tmp_path):
    task = _TASK.replace("| — (долг «открытый вопрос», ответственный аналитик) |", "| нет |")
    data = _build(make_delta(make_repo(tmp_path), debt_row="", task=task))
    assert data["questions"] == {"questions": [], "debts": []}
    assert "## Открытые вопросы\n\nнет\n" in dr.render(data)


# 7. выбор постановки ------------------------------------------------------------------------

def test_task_detected_from_single_task_file(tmp_path):
    data = _build(make_delta(make_repo(tmp_path)))
    assert data["task"] == "ECO-123" and data["task_name"] == "Поле даты рождения"
    assert data["service"] == "x"
    assert dr.render(data).startswith("# Отчёт дельты: ECO-123 — Поле даты рождения\n")
    assert not any("постановка" in n.lower() for n in data["notes"])


def test_two_task_files_require_task_key(tmp_path):
    repo = make_delta(make_repo(tmp_path))
    _w(repo / "tasks/ECO-124.md", _TASK.replace("ECO-123", "ECO-124"))
    data, err = dr.build(repo)
    assert data is None
    assert "несколько постановок" in err and "--task" in err
    assert "tasks/ECO-123.md" in err and "tasks/ECO-124.md" in err
    data = _build(repo, task_arg="ECO-124")
    assert data["task"] == "ECO-124"


def test_task_without_type_task_noted(tmp_path):
    data = _build(make_delta(make_repo(tmp_path), task=_TASK.replace("type: task\n", "type: note\n")))
    assert any("нет `type: task`" in n for n in data["notes"])
    data = _build(make_delta(make_repo(tmp_path / "b"), task=_TASK.replace("task: ECO-123", "task: ECO-999")))
    assert any("`task:` = «ECO-999», ожидается `ECO-123`" in n for n in data["notes"])


def test_task_key_without_file_noted(tmp_path):
    repo = make_delta(make_repo(tmp_path), task="")
    data = _build(repo, task_arg="ECO-777")
    assert data["task"] == "ECO-777"
    assert any("файл постановки не найден: `tasks/ECO-777.md`" in n for n in data["notes"])
    assert "# Отчёт дельты: ECO-777 — —" in dr.render(data)


def test_no_task_in_delta_noted_not_fatal(tmp_path):
    data = _build(make_delta(make_repo(tmp_path), task=""))
    assert data["task"] == ""
    assert any("постановка в дельте не найдена" in n for n in data["notes"])
    assert dr.render(data).startswith("# Отчёт дельты: задача не определена")


# 8. база ------------------------------------------------------------------------------------

def test_base_falls_back_to_trunk(tmp_path):
    # целевой docs-репозиторий GitLab живёт на trunk (полигон docs-account-opening-request)
    data = _build(make_delta(make_repo(tmp_path, branch="trunk")))
    assert data["base"] == "trunk" and data["branch"] == "trunk"
    assert not any("не найдена" in n for n in data["notes"])


def test_base_falls_back_to_main(tmp_path):
    data = _build(make_delta(make_repo(tmp_path, branch="main")))
    assert data["base"] == "main" and data["branch"] == "main"
    assert data["ids"]["new"] == ["CTL-CL-001"]
    assert not any("не найдена" in n for n in data["notes"])


def test_explicit_missing_base_noted(tmp_path):
    data = _build(make_delta(make_repo(tmp_path)), base_arg="release")
    assert data["base"] == "master"
    assert any("база `release` в репозитории не найдена" in n for n in data["notes"])


def test_delta_against_base_includes_commits_on_branch(tmp_path):
    repo = make_delta(make_repo(tmp_path))
    _git(repo, "checkout", "-q", "-b", "feature/eco-123")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "ECO-123")
    data = _build(repo)
    assert data["branch"] == "feature/eco-123" and data["base"] == "master"
    assert _file(data, "srs/control/ctl-cl-001.md")["action"] == "создан"
    assert data["ids"]["inner"]["SCR-CL-02"] == ["FLD-3"]


def test_not_git_repo_is_error(tmp_path):
    repo = tmp_path / "plain"
    _w(repo / "traceability-matrix.md", _MATRIX)
    data, err = dr.build(repo)
    assert data is None and "не git-репозиторий" in err


def test_missing_matrix_is_error(tmp_path):
    repo = tmp_path / "docs-x"
    _w(repo / "README.md", _README)
    _git(repo, "init", "-q")
    data, err = dr.build(repo)
    assert data is None and "матрица трассировки не найдена" in err


def test_docs_subdir_layout(tmp_path):
    # рабочий репозиторий миграции: комплект в docs/, матрицы в корне нет
    repo = tmp_path / "src-x"
    _w(repo / "docs/README.md", _README)
    _w(repo / "docs/traceability-matrix.md", _MATRIX)
    _w(repo / "docs/srs/screen-form/scr-cl-02.md", _SCR)
    _w(repo / "docs/srs/data-model/ent-001.md", _ENT)
    _w(repo / "docs/srs/print-form/prn-001.md", _PRN)
    _w(repo / "open-questions.md", "# OQ\n")
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    make_delta(repo / "docs")
    _w(repo / "open-questions.md", "# OQ\n\n## OQ-001. Вопрос\n")
    data = _build(repo)
    assert Path(data["kit"]) == (repo / "docs").resolve()
    assert _file(data, "srs/control/ctl-cl-001.md")["action"] == "создан"
    assert data["task"] == "ECO-123"
    oq = _file(data, "open-questions.md")
    assert oq["in_kit"] is False and oq["kind"] == "other"
    assert "`open-questions.md` | изменён, вне комплекта | — |" in dr.render(data)


# 9. --out / --json ------------------------------------------------------------------------------

def _cli(*args: str) -> subprocess.CompletedProcess:
    script = Path(dr.__file__)
    return subprocess.run([sys.executable, str(script), *args], capture_output=True,
                          encoding="utf-8", env={"PYTHONIOENCODING": "utf-8", "PATH": __import__("os").environ["PATH"]})


def test_cli_out_and_json(tmp_path):
    repo = make_delta(make_repo(tmp_path))
    out = tmp_path / "rep" / "delta.md"
    r = _cli("--repo", str(repo), "--out", str(out), "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    raw = out.read_bytes()
    assert b"\r\n" not in raw
    text = raw.decode("utf-8")
    assert text.startswith("# Отчёт дельты: ECO-123")
    assert f"отчёт дельты записан: {out}" in r.stdout
    js = r.stdout[r.stdout.index("{"):]
    data = json.loads(js)
    for key in ("files", "ids", "matrix", "affected", "facts", "questions", "notes"):
        assert key in data
    assert data["task"] == "ECO-123"
    # read-only: рабочее дерево репозитория не тронуто (только дельта)
    st = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo), capture_output=True,
                        encoding="utf-8").stdout
    assert "delta.md" not in st


def test_affected_before_edits(tmp_path):
    # до правок: кто ссылается на SCR-CL-02 (PRN-001; матрица и README не считаются) и на кого ссылается она (ENT-001)
    repo = make_repo(tmp_path)
    # постановка с id T-… ссылается на форму — соседом не считается
    _w(repo / 'tasks/ECO-9.md', '---' + chr(10) + 'id: T-ECO-9' + chr(10) + 'type: task' + chr(10) + 'task: ECO-9' + chr(10) + '---' + chr(10) + chr(10) + 'см. [форму](../srs/screen-form/scr-cl-02.md)' + chr(10))
    rows, notes = dr.affected_before(repo, ["SCR-CL-02", "NO-SUCH-1"])
    assert notes == ["карточка `NO-SUCH-1` не найдена (frontmatter `id` ни у одного файла комплекта)"]
    assert len(rows) == 1 and rows[0]["id"] == "SCR-CL-02"
    assert rows[0]["incoming"] == ["PRN-001"] and rows[0]["outgoing"] == ["ENT-001"]
    text = dr.render_affected(rows, notes)
    assert "## SCR-CL-02 (`srs/screen-form/scr-cl-02.md`)" in text and "`PRN-001`" in text


def test_affected_cli(tmp_path):
    repo = make_repo(tmp_path)
    r = _cli("--repo", str(repo), "--affected", "SCR-CL-02")
    assert r.returncode == 0 and r.stdout.startswith("# Затронуто до правок")
    r = _cli("--repo", str(repo), "--affected", "NO-SUCH-1")
    assert r.returncode == 2 and "не найдена" in r.stdout


def test_cli_exit_codes(tmp_path):
    r = _cli("--repo", str(tmp_path))
    assert r.returncode == 2 and "не git-репозиторий" in r.stdout
    repo = make_delta(make_repo(tmp_path))
    _w(repo / "tasks/ECO-124.md", _TASK.replace("ECO-123", "ECO-124"))
    r = _cli("--repo", str(repo))
    assert r.returncode == 2 and "несколько постановок" in r.stdout
    r = _cli("--repo", str(repo), "--task", "ECO-123")
    assert r.returncode == 0 and r.stdout.startswith("# Отчёт дельты: ECO-123")


def test_cli_notes_do_not_change_exit_code(tmp_path):
    repo = make_delta(make_repo(tmp_path), registry_row=_CTL_ROW + _CTL_ROW)
    r = _cli("--repo", str(repo))
    assert r.returncode == 0 and "## Замечания прибора" in r.stdout


def test_broken_frontmatter_is_note_not_crash(tmp_path):
    repo = make_delta(make_repo(tmp_path))
    _w(repo / "srs/control/ctl-cl-002.md", "---\nid: CTL-CL-002\ntype: control\n\n# без закрытия\n")
    data = _build(repo)
    assert any("frontmatter не разбирается" in n and "ctl-cl-002.md" in n for n in data["notes"])
