# app/scripts/CI/delta_report.py
#
# ОТЧЁТ ДЕЛЬТЫ для режима «изменение по постановке» (решение владельца
# 2026-10-15, Д-43; трек «Forward без платформы», срез С2). После миграции
# комплект в репозитории документации `docs-<service-id>` развивается
# задачами аналитика без платформы: постановка хранится в
# `tasks/<JIRA-ID>.md` (frontmatter `type: task`, `task: <JIRA-ID>`;
# строки `T-<JIRA-ID>-NN`), агент правит карточки по правилам, объект
# акцепта — отчёт дельты в описании MR (шаблон канона
# `_meta/templates/delta-report.md`).
#
# ЗАЧЕМ ПРИБОР. Детерминированную часть отчёта (файлы, идентификаторы,
# матрица, затронутые карточки, заготовка фактов, открытые вопросы) должен
# собирать прибор, а не агент по памяти: что изменено — читается из git,
# что в реестре — из матрицы. Агент дописывает только происхождение
# фактов (колонка «Происхождение») и результаты прогона проверок.
#
# ЧТО ДЕЛАЕТ. По изменениям рабочего дерева репозитория документации
# относительно базы (`--base`, по умолчанию `master` → `main` → только
# рабочее дерево против `HEAD`) собирает markdown-отчёт по шаблону:
#   1. Изменённые файлы: `git diff --name-status <base>` плюс незакоммиченные
#      и неотслеживаемые файлы (`git status --porcelain`); для карточек —
#      `id`/`partOf` и `type` из frontmatter; постановки `tasks/*.md` —
#      отдельной строкой, в таблицу карточек не входят.
#   2. Идентификаторы: новые — `id` созданных карточек плюс новые строки
#      реестра матрицы; снятые — ID удалённых карточек и снятых строк
#      реестра. Сверка: новая карточка есть в реестре, дублей ID нет, у ID
#      реестра есть файл на диске. Внутренние идентификаторы (FLD-N, EV-N,
#      B-N, MSG-N, CTL-NNN) — добавленные заголовки `### <ID>.` в диффе.
#   3. Матрица трассировки: добавленные и снятые строки реестра, связей и
#      долгов (обе формы строки долга — через `link_debts.parse_matrix`).
#   4. Затронуто: карточки, ссылающиеся относительной ссылкой на изменённые
#      (`transfer_gate.card_referrers`), с пометкой «изменена в этой дельте».
#   5. Факты и происхождение: заготовка из добавленных строк диффа карточек
#      (строки таблиц, пункты списков `- **…**`, заголовки `### `); колонка
#      «Происхождение» пустая — её дописывает агент. Не больше 200 строк.
#   6. Открытые вопросы: строки «Вопросы и ответы» постановки с ответом «—»
#      и добавленные долги вида «открытый вопрос». Форма вопросов (все
#      строки таблицы, решение владельца 2026-10-26) — сторож
#      `check_questions` по правилам опроса канона `_meta/rules/questions.md`:
#      голый идентификатор без наименования, префикс типа вместо названия
#      типа требований словами, вопрос реализации (физическое имя, тип и
#      ограничения БД), нет рекомендации агента, несколько «?» в строке.
#      Пункты «Границ захода» («… — по умолчанию DFR-NNN», решение
#      владельца 2026-10-27) рекомендации не требуют, `DFR-NNN` — не ID
#      артефакта. Замечания — в блок «Замечания прибора», заход не блокируют.
#   7. Проверки: блок-заглушка (selfcheck / link_debts / гейт) — результаты
#      вписывает агент после прогона; прибор лишь проверяет, что постановка
#      существует и её frontmatter несёт `type: task` и `task: <JIRA-ID>`.
#   8. Сторож отчёта перед сдачей (`--check <файл.md>`, решение владельца
#      2026-10-27 после прогона TEAMTB-202610272 на слабой модели: отчёт
#      сдан с пустым «Происхождением», заглушками «почему: …» и шаблонным
#      разделом «Проверки», собран до правки матрицы): факты без
#      происхождения, оставшиеся «почему: …» в «Затронуто», незаполненный
#      раздел «Проверки», неразобранный блок «Замечания прибора», отчёт
#      старее дельты рабочего дерева (файлы дельты, которых нет в
#      «Изменённых файлах»). Замечания, код 0; гейт — скилл («пока есть
#      замечания — не сдавать»).
#
# ОГРАНИЧИТЕЛИ. Утилита read-only: в репозитории ничего не меняет, пишет в
# stdout и/или в файл `--out`. Это вход для человека, не гейт: замечания
# (дубль ID, карточка вне реестра, нечитаемый файл) не роняют сборку — они
# собираются в блок «Замечания прибора» в конце, код выхода остаётся 0.
# Асимметрия ошибок: лучше лишняя строка в отчёте, чем молчаливый пропуск.
# Зависимости — только стандартная библиотека и `git` в PATH.
#
# Ключи:
#   --repo <путь>    корень клона репозитория документации (комплект в корне;
#                    если есть docs/, а матрицы в корне нет — комплект в docs/)
#   --base <ref>     база дельты (по умолчанию master, иначе main, иначе trunk, иначе HEAD)
#   --task <JIRA-ID> задача; без ключа — из единственной постановки в дельте
#   --out <файл.md>  записать отчёт в файл (UTF-8, переводы строк \n)
#   --json           дополнительно напечатать данные отчёта в JSON
#   --affected <ID[,ID…]>  ДО правок: соседи карточек по относительным ссылкам
#                    (кто ссылается на карточку и на кого ссылается она) —
#                    детерминированный перечень для шага 2 режима C; дельта не
#                    строится, git не нужен; код 2, если ни один ID не найден
#   --questions <JIRA-ID>  ДО показа вопросов аналитику: проверка формы таблицы
#                    «Вопросы и ответы» постановки `tasks/<JIRA-ID>.md` (сторож
#                    `check_questions`); дельта не строится, git не нужен; код 0
#                    и при замечаниях (замечание, не гейт), код 2 — постановки нет
#   --check <файл.md>  ПЕРЕД СДАЧЕЙ: проверка заполненного отчёта дельты (сторож
#                    `check_report`) и его свежести против дельты рабочего дерева
#                    `--repo` (`--base`, `--task` — как у сборки); код 0 и при
#                    замечаниях, код 2 — файла нет
#
# Код выхода: 0 — отчёт собран; 2 — собрать нельзя (не git-репозиторий,
# матрицы нет, постановка в дельте неоднозначна).

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import link_debts as ld  # noqa: E402
import selfcheck as sc  # noqa: E402
import transfer_gate as tg  # noqa: E402

FACTS_LIMIT = 200

# действие по статусу git (diff --name-status / status --porcelain)
_ACTION_BY_STATUS = {"A": "создан", "M": "изменён", "D": "снят", "R": "переименован",
                     "C": "создан", "T": "изменён", "?": "создан"}
# внутренний идентификатор карточки в заголовке: `### FLD-3. …`, `### EV-2.1 …`,
# `### CTL-012.` — латинский префикс (с дефисами), номер, суб-номера через точку
_INNER_ID_RE = re.compile(r"^#{3,}\s+([A-Z]{1,6}(?:-[A-Z]{1,6})*-\d+(?:\.\d+)*)\b")
_TABLE_ROW_RE = re.compile(r"^\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_LIST_FACT_RE = re.compile(r"^\s*[-*]\s+\*\*")
_HEADING_FACT_RE = re.compile(r"^###\s+\S")
_TASK_TITLE_RE = re.compile(r"^#\s+([A-Za-z][\w-]*-\d+)\s*[.:—-]\s*(.+?)\s*$", re.M)
_QA_HEAD_RE = re.compile(r"^##\s+Вопросы\s+и\s+ответы", re.I | re.M)
# сторож формы вопросов (check_questions, правила опроса канона
# `_meta/rules/questions.md`): markdown-ссылка «[label](target)» → label
_Q_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# идентификатор артефакта (`EXT-007`, `SCR-CL-03.1`, `CTL-GRP-1`); слева не буква,
# не цифра и не дефис — поэтому строки постановки `T-<КЛЮЧ>-NN` не считаются
_Q_ID_RE = re.compile(r"(?<![\w-])(?:[A-Z]{2,6}-GRP-\d+|[A-Z]{2,6}(?:-[A-Z]{1,6})*-\d+(?:\.\d+)*)(?!\w)")
# ID назван, если прямо перед ним — закрывающая кавычка наименования, «(» и не
# больше 30 символов без скобок: «Пользователь» (`EXT-007`), «Счёт» (вкладка `SCR-CL-03.1`).
# Окно «»» где-то рядом» ловило чужое наименование («…на «Продолжить» или во всей
# CTL-GRP-1») — живой прогон 26.10
_Q_NAMED_BEFORE_RE = re.compile(r"»\s*\([^()]{0,30}$")
_Q_CYR_RE = re.compile(r"[А-Яа-яЁё]")
# префикс типа отдельным словом (за ним не дефис — иначе это часть ID)
_Q_PREFIXES = ("NTF", "PRN", "CTL", "SM", "CALL", "ENT", "EXT", "FUN", "PROC", "SCR", "RBAC",
               "INTC", "LIBC", "EXTINT", "PLT", "FLD", "MSG", "EV")
_Q_PREFIX_RE = re.compile(r"\b(" + "|".join(sorted(_Q_PREFIXES, key=len, reverse=True)) + r")\b(?!-)")
# фразы вопроса реализации — в forward не задаются никем
_Q_IMPL_PHRASES = ("физ. имя", "физическое имя", "varchar", "NOT NULL", "ограничения БД",
                   "ограничений БД", "имя колонки", "тип БД")


# --- git ---------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """git без пейджера и без экранирования кириллицы в путях."""
    return subprocess.run(["git", "-c", "core.quotepath=false", "--no-pager", *args],
                          cwd=str(cwd), capture_output=True, encoding="utf-8",
                          errors="replace")


def git_toplevel(repo: Path) -> Optional[Path]:
    """Корень рабочего дерева git; None — не git-репозиторий (или git нет)."""
    try:
        r = _git(repo, "rev-parse", "--show-toplevel")
    except OSError:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip()).resolve()


def _ref_exists(top: Path, ref: str) -> bool:
    return _git(top, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0


def resolve_base(top: Path, base: Optional[str]) -> Tuple[Optional[str], List[str]]:
    """(ref базы или None — только рабочее дерево против HEAD, замечания).
    Явно заданная, но отсутствующая база — замечание, затем та же цепочка
    умолчаний master → main → trunk → HEAD (целевые docs-репозитории
    GitLab живут на `trunk` — полигон docs-account-opening-request, 15.10)."""
    notes: List[str] = []
    chain: List[str] = []
    if base:
        chain.append(base)
    chain.extend(r for r in ("master", "main", "trunk") if r not in chain)
    for ref in chain:
        if _ref_exists(top, ref):
            if base and ref != base:
                notes.append(f"база `{base}` в репозитории не найдена — дельта считается от `{ref}`")
            return ref, notes
    if _ref_exists(top, "HEAD"):
        notes.append("веток master/main нет — дельта считается от HEAD (только рабочее дерево)")
        return "HEAD", notes
    notes.append("в репозитории нет коммитов — дельта: только рабочее дерево")
    return None, notes


def changed_files(top: Path, base: Optional[str]) -> Tuple[List[dict], List[str]]:
    """Изменённые файлы рабочего дерева против базы: [{path, status, action,
    old}] (path — относительно корня git, POSIX; status — буква git; old —
    прежний путь при переименовании). Источники: `git diff --name-status -M
    <base>` (закоммиченное и незакоммиченное против базы) плюс
    неотслеживаемые файлы из `git status --porcelain`."""
    notes: List[str] = []
    found: Dict[str, dict] = {}
    if base is not None:
        r = _git(top, "diff", "--name-status", "-M", "-z", base, "--")
        if r.returncode != 0:
            notes.append(f"git diff против `{base}` не отработал: {r.stderr.strip()[:200]}")
        else:
            parts = r.stdout.split("\0")
            i = 0
            while i < len(parts):
                st = parts[i]
                if not st:
                    i += 1
                    continue
                letter = st[0]
                if letter in ("R", "C") and i + 2 < len(parts):
                    old, new = parts[i + 1], parts[i + 2]
                    i += 3
                    found[new] = {"path": new, "status": letter, "old": old,
                                  "action": _ACTION_BY_STATUS.get(letter, "изменён")}
                elif i + 1 < len(parts):
                    p = parts[i + 1]
                    i += 2
                    found[p] = {"path": p, "status": letter, "old": None,
                                "action": _ACTION_BY_STATUS.get(letter, "изменён")}
                else:
                    break
    r = _git(top, "status", "--porcelain", "-uall", "-z", "--")
    if r.returncode != 0:
        notes.append(f"git status не отработал: {r.stderr.strip()[:200]}")
    else:
        parts = r.stdout.split("\0")
        i = 0
        while i < len(parts):
            ent = parts[i]
            if not ent or len(ent) < 4:
                i += 1
                continue
            xy, p = ent[:2], ent[3:]
            i += 1
            if xy[0] in ("R", "C"):
                i += 1  # прежний путь — отдельной записью
            if xy == "??" and p not in found:
                found[p] = {"path": p, "status": "?", "old": None, "action": "создан"}
            elif base is None and xy != "!!" and p not in found:
                # нет коммитов: вся картина — из status
                letter = (xy.strip() or "M")[0]
                found[p] = {"path": p, "status": letter, "old": None,
                            "action": _ACTION_BY_STATUS.get(letter, "изменён")}
    return [found[k] for k in sorted(found)], notes


def _show_base(top: Path, base: Optional[str], rel: str) -> Optional[str]:
    """Текст файла в базе; None — в базе файла нет."""
    if base is None:
        return None
    r = _git(top, "show", f"{base}:{rel}")
    return r.stdout if r.returncode == 0 else None


def added_removed_lines(top: Path, base: Optional[str], rec: dict) -> Tuple[List[str], List[str]]:
    """Добавленные и снятые строки файла против базы. Неотслеживаемый или
    отсутствующий в базе файл — все его строки добавлены; снятый — все
    строки базы сняты. Строки с «@@» (границы ханков) сохраняются в
    добавленных как маркер «@@», чтобы потребитель мог сбросить контекст."""
    path = top / rec["path"]
    if rec["status"] == "D":
        old = _show_base(top, base, rec["old"] or rec["path"]) or ""
        return [], old.splitlines()
    if rec["status"] == "?" or base is None:
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines(), []
        except OSError:
            return [], []
    paths = [rec["path"]] + ([rec["old"]] if rec.get("old") else [])
    r = _git(top, "diff", "-M", "--no-color", "-U0", base, "--", *paths)
    if r.returncode != 0 or not r.stdout.strip():
        # отслеживаемый файл, которого в базе не было: diff пуст лишь если
        # файл тождествен базе — тогда и строк нет; иначе считаем все строки
        if _show_base(top, base, rec["old"] or rec["path"]) is None and path.is_file():
            return path.read_text(encoding="utf-8", errors="replace").splitlines(), []
        return [], []
    added: List[str] = []
    removed: List[str] = []
    # заголовок диффа (diff --git, index, ---/+++) — до первого «@@» файла;
    # внутри ханка строка на «---»/«+++» — снятая «-- …» или добавленная
    # «++ …» строка текста (прежде по префиксу она молча выпадала)
    in_hunk = False
    for ln in r.stdout.splitlines():
        if ln.startswith("diff --git "):
            in_hunk = False
            continue
        if ln.startswith("@@"):
            in_hunk = True
            added.append("@@")
        elif not in_hunk:
            continue
        elif ln.startswith("+"):
            added.append(ln[1:])
        elif ln.startswith("-"):
            removed.append(ln[1:])
    return added, removed


# --- комплект --------------------------------------------------------------------

def kit_root(repo: Path) -> Tuple[Optional[Path], Optional[str]]:
    """(корень комплекта, причина отказа). Как transfer_gate.detect_layout:
    комплект в корне (матрица там) либо в docs/ рабочего репозитория."""
    docs, _docs_repo = tg.detect_layout(repo, "docs")
    if docs is None:
        return None, f"матрица трассировки не найдена ни в {repo}, ни в {repo / 'docs'}"
    if not (docs / "traceability-matrix.md").is_file():
        return None, f"матрица трассировки не найдена: {docs / 'traceability-matrix.md'}"
    return docs, None


def _rel_kit(top: Path, kit: Path, git_rel: str) -> Optional[str]:
    """Путь git (от корня git) → путь относительно корня комплекта (POSIX);
    None — файл вне комплекта."""
    try:
        return (top / git_rel).resolve().relative_to(kit.resolve()).as_posix()
    except ValueError:
        return None


def _registry_rows(text: str) -> List[str]:
    """ID строк реестра в порядке появления, с дублями (parse_matrix дубли
    схлопывает — для сверки «дублей нет» нужны все вхождения)."""
    ids: List[str] = []
    for ln in text.splitlines():
        reg, debts = ld.parse_matrix(ln)
        if reg and not debts:
            ids.extend(reg.keys())
    return ids


def _card_type_file(path: Path) -> Tuple[Optional[Dict[str, str]], str, str]:
    """(frontmatter | None, ID карточки, тип). ID — `id` или `partOf`."""
    fm = sc.read_frontmatter(path)
    if not fm:
        return fm, "", ""
    cid = str(fm.get("id") or fm.get("partOf") or "").strip()
    return fm, cid, str(fm.get("type", "")).strip()


_ID_LINE_RE = re.compile(r"^(?:id|partOf):\s*(.+?)\s*$", re.M)


def _id_from_text(text: str) -> str:
    """ID из frontmatter текста (для файлов, которых на диске уже нет)."""
    head = sc.frontmatter_split(text)[0]
    if head is None:
        return ""
    m = _ID_LINE_RE.search(head)
    return m.group(1).strip() if m else ""


# --- разделы отчёта --------------------------------------------------------------

def collect_files(top: Path, kit: Path, base: Optional[str], changed: List[dict],
                  base_registry: Dict[str, Tuple[str, str]], notes: List[str]) -> dict:
    """Раздел «Изменённые файлы»: карточки (с ID и типом), постановки, прочие
    файлы. Каждому изменённому файлу — своя запись: files[*] = {path, action,
    id, type, kind ∈ card|task|matrix|other, old}."""
    out: List[dict] = []
    for rec in changed:
        rel = _rel_kit(top, kit, rec["path"])
        entry = {"path": rel if rel is not None else rec["path"], "git_path": rec["path"],
                 "action": rec["action"], "status": rec["status"], "old": rec["old"],
                 "id": "", "type": "", "kind": "other", "in_kit": rel is not None}
        abs_path = top / rec["path"]
        if rel is not None and rel == "traceability-matrix.md":
            entry["kind"] = "matrix"
        elif rel is not None and sc.is_task_file(abs_path, kit):
            entry["kind"] = "task"
            fm = sc.read_frontmatter(abs_path) if abs_path.is_file() else {}
            entry["id"] = str((fm or {}).get("task", "")).strip()
            entry["type"] = str((fm or {}).get("type", "")).strip()
        elif abs_path.suffix.lower() == ".md":
            if rec["status"] == "D":
                text = _show_base(top, base, rec["path"]) or ""
                cid = _id_from_text(text)
                if not cid:
                    cid = next((i for i, (_t, f) in base_registry.items()
                                if rel is not None and f.replace("\\", "/").lstrip("./") == rel), "")
                entry["id"], entry["kind"] = cid, "card" if cid else "other"
            elif abs_path.is_file():
                fm, cid, typ = _card_type_file(abs_path)
                if fm is None:
                    notes.append(f"frontmatter не разбирается (блок не закрыт): `{entry['path']}`")
                entry["id"], entry["type"] = cid, typ
                entry["kind"] = "card" if cid else "other"
            else:
                notes.append(f"файл из дельты не найден на диске: `{entry['path']}`")
        out.append(entry)
    return {"files": out}


def collect_ids(kit: Path, files: List[dict], matrix_now: str, matrix_base: Optional[str],
                inner: Dict[str, List[str]], notes: List[str]) -> dict:
    """Раздел «Идентификаторы» и сверка с реестром матрицы."""
    reg_now, _ = ld.parse_matrix(matrix_now)
    reg_base, _ = ld.parse_matrix(matrix_base or "")
    created = [f["id"] for f in files if f["kind"] == "card" and f["action"] == "создан" and f["id"]]
    deleted = [f["id"] for f in files if f["kind"] == "card" and f["action"] == "снят" and f["id"]]
    new_rows = [i for i in reg_now if i not in reg_base]
    gone_rows = [i for i in reg_base if i not in reg_now]
    new_ids = sorted(set(created) | set(new_rows))
    removed_ids = sorted(set(deleted) | set(gone_rows))
    outside: List[str] = []
    for f in files:
        if f["kind"] != "card" or f["action"] == "снят" or not f["id"] or f["id"] in reg_now:
            continue
        outside.append(f["id"])
        notes.append(f"карточка вне реестра: `{f['id']}` (`{f['path']}`, {f['action']}) — "
                     "строки в «Реестре ID» матрицы нет")
    seen: Dict[str, int] = {}
    for rid in _registry_rows(matrix_now):
        seen[rid] = seen.get(rid, 0) + 1
    dups = sorted(i for i, n in seen.items() if n > 1)
    for rid in dups:
        notes.append(f"дубль ID в реестре матрицы: `{rid}` ({seen[rid]} строки)")
    missing_files = []
    for rid, (_typ, fpath) in reg_now.items():
        # колонка «Файл» бывает markdown-ссылкой «[label](path)»: parse_matrix
        # берёт первый путь (ярлык), а на диске лежит цель ссылки — проверяем
        # все пути строки реестра (полигон docs-account-opening-request, 15.10)
        cands = [fpath] + _row_paths(matrix_now, rid)
        if not any((kit / c.replace("\\", "/").lstrip("./")).is_file() for c in cands):
            missing_files.append(rid)
            notes.append(f"ID реестра без файла на диске: `{rid}` → `{fpath}`")
    return {"new": new_ids, "removed": removed_ids, "created_cards": created,
            "deleted_cards": deleted, "new_registry": new_rows, "removed_registry": gone_rows,
            "outside_registry": outside, "duplicates": dups, "missing_files": missing_files,
            "inner": inner}


def _split_matrix_rows(lines: List[str]) -> List[str]:
    """Строки таблиц из набора строк диффа: шапки (строка перед разделителем)
    и разделители отбрасываются, маркеры ханков — тоже."""
    rows: List[str] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not _TABLE_ROW_RE.match(s) or _TABLE_SEP_RE.match(s):
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if _TABLE_SEP_RE.match(nxt):
            continue  # шапка таблицы
        rows.append(s)
    return rows


def _classify_rows(rows: List[str]) -> dict:
    """Строки матрицы → реестр / связи / долги (через link_debts.parse_matrix)."""
    out = {"registry": [], "links": [], "debts": []}
    for row in rows:
        reg, debts = ld.parse_matrix(row)
        if debts:
            from_ids, typ, name, owner, raw = debts[0]
            d = {"from": from_ids, "type": typ, "name": name, "owner": owner, "row": raw,
                 "kind": None, "responsible": None, "source": None}
            if typ.startswith("долг:"):
                fields = ld.issue_fields(raw) or {}
                d["kind"] = fields.get("kind")
                d["responsible"] = fields.get("responsible")
                d["source"] = fields.get("source")
            else:
                d["kind"] = "нет цели"
            out["debts"].append(d)
        elif reg:
            rid, (typ, fpath) = next(iter(reg.items()))
            out["registry"].append({"id": rid, "type": typ, "file": fpath, "row": row})
        else:
            out["links"].append(row)
    return out


def collect_matrix(top: Path, base: Optional[str], matrix_rec: Optional[dict]) -> dict:
    """Раздел «Матрица трассировки»: добавленные и снятые строки по группам."""
    if matrix_rec is None:
        return {"changed": False, "added": _classify_rows([]), "removed": _classify_rows([])}
    added, removed = added_removed_lines(top, base, matrix_rec)
    return {"changed": True,
            "added": _classify_rows(_split_matrix_rows(added)),
            "removed": _classify_rows(_split_matrix_rows(removed))}


def _row_paths(matrix_text: str, rid: str) -> List[str]:
    """Все пути `.md` во всех строках матрицы с данным ID в первой колонке (реестр и
    покрытие; ярлык и цель ссылки) — ID встречается и в разделах покрытия без путей."""
    out: List[str] = []
    for ln in matrix_text.splitlines():
        if re.match(r"^\|\s*" + re.escape(rid) + r"\s*\|", ln):
            out.extend(re.findall(r"[\w./-]+\.md\b", ln))
    return out


def collect_affected(kit: Path, files: List[dict]) -> List[dict]:
    """Раздел «Затронуто»: для каждой изменённой/созданной карточки — кто на
    неё ссылается относительной ссылкой и изменён ли ссылающийся в этой же
    дельте. Матрица и README не считаются (card_referrers)."""
    referrers = tg.card_referrers(kit)
    changed_ids = {f["id"] for f in files if f["kind"] == "card" and f["id"]}
    out: List[dict] = []
    done: set = set()
    for f in files:
        if f["kind"] != "card" or not f["id"] or f["action"] == "снят":
            continue
        if f["id"] in done:
            # несколько файлов одной карточки (README с id + части с partOf) —
            # одна запись «Затронуто» на ID, не на файл
            continue
        done.add(f["id"])
        refs = referrers.get(f["id"], [])
        out.append({"id": f["id"], "action": f["action"],
                    "referrers": [{"id": r, "changed": r in changed_ids} for r in refs]})
    return out


def _fact_text(line: str) -> str:
    """Текст факта для ячейки таблицы: без крайних «|», с экранированием."""
    s = line.strip()
    if s.startswith("|"):
        s = s.strip("|").strip()
    s = re.sub(r"^(?:#{1,6}\s+|[-*]\s+)", "", s)
    s = s.replace("|", "\\|")
    return s if len(s) <= 200 else s[:197] + "…"


def collect_facts(top: Path, base: Optional[str], files: List[dict],
                  notes: List[str]) -> Tuple[List[dict], Dict[str, List[str]], int]:
    """Заготовка «Факты и происхождение» и новые внутренние идентификаторы:
    по добавленным строкам диффа карточек — строки таблиц, пункты `- **…**`,
    заголовки `### `; frontmatter, разделители и шапки таблиц не входят.
    Возвращает (факты, {ID карточки: [внутренние ID]}, сколько строк сверх
    лимита не вошло)."""
    facts: List[dict] = []
    inner: Dict[str, List[str]] = {}
    overflow = 0
    for f in files:
        if f["kind"] != "card" or f["action"] == "снят" or not f["id"]:
            continue
        added, _ = added_removed_lines(top, base, {"path": f["git_path"], "status": f["status"],
                                                  "old": f["old"]})
        # шапка созданной карточки — не факты (общая граница шапки); у
        # изменённой карточки первая добавленная «---» — черта текста, не
        # шапка: прежде она срезала факты до следующей «---»
        if f["action"] == "создан":
            lead = 1 if added[:1] == ["@@"] else 0
            end = sc.frontmatter_end(added[lead:])
            if end:
                added = added[:lead] + added[lead + end:]
        current_inner: Optional[str] = None
        for i, ln in enumerate(added):
            if ln == "@@":
                current_inner = None
                continue
            s = ln.rstrip()
            if not s.strip():
                continue
            m = _INNER_ID_RE.match(s.strip())
            if m:
                current_inner = m.group(1)
                inner.setdefault(f["id"], []).append(m.group(1))
            is_row = bool(_TABLE_ROW_RE.match(s.strip())) and not _TABLE_SEP_RE.match(s.strip())
            if is_row:
                nxt = added[i + 1].strip() if i + 1 < len(added) else ""
                if _TABLE_SEP_RE.match(nxt):
                    continue  # шапка таблицы
            if not (is_row or _LIST_FACT_RE.match(s) or _HEADING_FACT_RE.match(s.strip())):
                continue
            where = f"`{f['id']}`" + (f", {current_inner}" if current_inner and not m else "")
            if len(facts) >= FACTS_LIMIT:
                overflow += 1
                continue
            facts.append({"fact": _fact_text(s), "where": where, "card": f["id"],
                          "inner": None if m else current_inner, "file": f["path"],
                          "origin": ""})
    return facts, inner, overflow


_QA_BOUNDARY_HEAD_RE = re.compile(r"^###\s+Границы\s+захода", re.I)


def _qa_rows(task_text: str) -> List[Tuple[bool, List[str]]]:
    """Строки таблиц раздела «Вопросы и ответы» постановки (без шапки и
    разделителя) с признаком «строка подраздела «### Границы захода»»
    (шаблон `task.md`: два списка — «Решения» и «Границы захода»); раздела
    нет — пусто."""
    m = _QA_HEAD_RE.search(task_text)
    if not m:
        return []
    sect = task_text[m.end():]
    nxt = re.search(r"^#{1,2}\s", sect, re.M)
    if nxt:
        sect = sect[:nxt.start()]
    out: List[Tuple[bool, List[str]]] = []
    boundary = False
    block: List[str] = []

    def flush() -> None:
        out.extend((boundary, sc.table_cells(row)) for row in _split_matrix_rows(block))
        block.clear()

    for line in sect.splitlines():
        if line.startswith("###"):
            flush()
            boundary = bool(_QA_BOUNDARY_HEAD_RE.match(line))
            continue
        block.append(line)
    flush()
    return out


def _qa_cells(task_text: str) -> List[List[str]]:
    """Ячейки всех строк таблиц раздела «Вопросы и ответы» (оба подраздела)."""
    return [cells for _, cells in _qa_rows(task_text)]


def task_questions(task_text: str) -> List[dict]:
    """Строки таблицы «Вопросы и ответы» постановки с ответом «—»."""
    out: List[dict] = []
    for cells in _qa_cells(task_text):
        if len(cells) < 3:
            continue
        answer = cells[2]
        if answer == "—" or answer.startswith("— ") or answer.startswith("—("):
            out.append({"n": cells[0], "question": cells[1], "answer": answer})
    return out


def all_task_questions(task_text: str) -> List[dict]:
    """Все строки таблицы «Вопросы и ответы» (для --questions --json)."""
    return [{"n": c[0], "question": c[1], "answer": c[2] if len(c) > 2 else ""}
            for c in _qa_cells(task_text) if len(c) >= 2]


def _question_notes(cell: str, boundary: bool = False) -> List[str]:
    """Замечания к одной ячейке «Вопрос агента» в порядке a → b → c → d → e;
    `boundary` — строка подраздела «Границы захода»."""
    # a. ID назван в двух случаях: (1) он в ярлыке markdown-ссылки, где есть
    # кириллица (форма реестра «ID Наименование» / «Наименование (ID)»; ярлык из
    # одного ID — не наименование); (2) прямо перед ним «Наименование» ( и не
    # больше 30 символов без скобок. Всё прочее — голый ID, в том числе точечная
    # нотация `ENT-001`.«Поле». Одно замечание на ID, даже если он встречается
    # и названным по случаю (2); ярлык ссылки (1) называет ID для всей ячейки
    named: set = set()
    for lm in _Q_MD_LINK_RE.finditer(cell):
        if _Q_CYR_RE.search(lm.group(1)):
            named.update(m.group(0) for m in _Q_ID_RE.finditer(lm.group(1)))
    text = _Q_MD_LINK_RE.sub(r"\1", cell)
    out: List[str] = []
    bare: List[str] = []
    for m in _Q_ID_RE.finditer(text):
        ident = m.group(0)
        # умолчание постановки `DFR-NNN` (_meta/rules/defaults.md) — основание
        # границы захода, не артефакт комплекта: наименования у него нет
        if ident.startswith("DFR-"):
            continue
        if ident in named or _Q_NAMED_BEFORE_RE.search(text[:m.start()]):
            continue
        if ident not in bare:
            bare.append(ident)
    out += [f"голый идентификатор «{i}» — рядом нет наименования" for i in bare]
    # b. префикс типа вместо наименования типа требований
    prefixes: List[str] = []
    for m in _Q_PREFIX_RE.finditer(text):
        if m.group(1) not in prefixes:
            prefixes.append(m.group(1))
    out += [f"префикс типа «{p}» вместо наименования типа требований "
            "(словами: уведомления, печатные формы…)" for p in prefixes]
    # c. вопрос реализации — одно замечание на строку, фразы как в тексте
    found: List[str] = []
    for ph in _Q_IMPL_PHRASES:
        m = re.search(re.escape(ph), text, re.I)
        if m and m.group(0) not in found:
            found.append(m.group(0))
    if found:
        out.append("вопрос реализации (" + ", ".join(f"«{f}»" for f in found)
                   + ") — физическое имя, тип и ограничения БД в forward не задаются")
    # d. нет рекомендации агента
    # пункт «Границ захода» — утверждение «что делаю / чего не делаю» с
    # основанием, рекомендации ему не нужно (правила опроса п. 6): любая строка
    # подраздела «### Границы захода», а вне подраздела — строка в форме
    # «… — по умолчанию DFR-NNN» (постановка без подразделов). Границу,
    # переписанную после ответа аналитика без DFR («добавляю — решение
    # аналитика»), старая форма считала вопросом без рекомендации — живой
    # прогон 27.10 (TEAMTB-202610272); голые ID в границах проверяются как везде
    boundary = boundary or ("по умолчанию" in text.lower() and "DFR-" in text)
    if "рекоменду" not in text.lower() and not boundary:
        out.append("нет рекомендации агента («Рекомендую …»)")
    # e. несколько вопросов в одной строке
    n_q = text.count("?")
    if n_q > 1:
        out.append(f"в одной строке несколько вопросов ({n_q} знаков «?») — один вопрос — один факт")
    return out


def check_questions(task_text: str) -> List[str]:
    """Сторож формы таблицы «Вопросы и ответы» постановки (решение владельца
    2026-10-26): по ВСЕМ строкам, не только с ответом «—», проверяет ячейку
    «Вопрос агента» по правилам опроса канона `_meta/rules/questions.md` —
    механическая защита, не зависящая от того, прочитал ли агент правило.
    Замечания вида `вопрос N: <что не так>` — по порядку строк, внутри строки
    a → b → c → d → e. Раздела или таблицы нет — пусто (шаблон допускает
    заход без вопросов). Карточки не проверяются — шума по комплекту нет."""
    if not task_text:
        return []
    out: List[str] = []
    for k, (boundary, cells) in enumerate(_qa_rows(task_text), 1):
        if len(cells) < 2:
            continue
        n = cells[0] or str(k)
        out += [f"вопрос {n}: {x}" for x in _question_notes(cells[1], boundary)]
    return out


def collect_questions(task_text: Optional[str], matrix: dict) -> dict:
    """Раздел «Открытые вопросы»: вопросы постановки без ответа и
    добавленные долги вида «открытый вопрос»."""
    qs = task_questions(task_text) if task_text else []
    debts = [d for d in matrix["added"]["debts"] if d["kind"] == "открытый вопрос"]
    return {"questions": qs, "debts": debts}


def pick_task(files: List[dict], task_arg: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(JIRA-ID, ошибка). Без --task — из единственной изменённой или новой
    постановки в дельте; несколько — ошибка (код 2); ни одной — None."""
    if task_arg:
        return task_arg.strip(), None
    tasks = [f for f in files if f["kind"] == "task" and f["action"] != "снят"]
    if len(tasks) > 1:
        names = ", ".join(f"`{t['path']}`" for t in tasks)
        return None, (f"в дельте несколько постановок ({names}) — задайте --task <JIRA-ID>")
    if tasks:
        return Path(tasks[0]["path"]).stem, None
    return None, None


def check_task_file(kit: Path, task_id: Optional[str], notes: List[str]) -> Tuple[Optional[str], str]:
    """(текст постановки | None, имя задачи). Сторожит существование файла
    и frontmatter `type: task`, `task: <JIRA-ID>`."""
    if not task_id:
        notes.append("постановка в дельте не найдена и --task не задан — разделы по постановке пусты")
        return None, ""
    path = kit / "tasks" / f"{task_id}.md"
    if not path.is_file():
        notes.append(f"файл постановки не найден: `tasks/{task_id}.md`")
        return None, ""
    fm = sc.read_frontmatter(path)
    if fm is None:
        notes.append(f"frontmatter постановки `tasks/{task_id}.md` не разбирается (блок не закрыт)")
        fm = {}
    if fm.get("type") != "task":
        notes.append(f"постановка `tasks/{task_id}.md`: в frontmatter нет `type: task`")
    if fm.get("task") != task_id:
        notes.append(f"постановка `tasks/{task_id}.md`: frontmatter `task:` = "
                     f"«{fm.get('task', '')}», ожидается `{task_id}`")
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _TASK_TITLE_RE.search(text)
    name = m.group(2).strip() if m else ""
    if not name:
        notes.append(f"постановка `tasks/{task_id}.md`: заголовок `# {task_id}. <имя>` не найден")
    return text, name


def find_service(kit: Path, task_text: Optional[str], files: List[dict]) -> str:
    """service — из frontmatter постановки, иначе изменённой карточки, иначе
    любой карточки комплекта."""
    if task_text:
        m = re.search(r"^service:\s*(.+?)\s*$", task_text.split("\n---", 1)[0], re.M)
        if m:
            return m.group(1).strip().strip("'\"")
    candidates = [kit / f["path"] for f in files if f["kind"] == "card" and f["action"] != "снят"]
    for p in candidates:
        fm = sc.read_frontmatter(p) if p.is_file() else {}
        if fm and fm.get("service"):
            return str(fm["service"]).strip().strip("'\"")
    for p in sorted(kit.rglob("*.md")):
        if sc.is_task_file(p, kit):
            continue
        fm = sc.read_frontmatter(p)
        if fm and fm.get("service"):
            return str(fm["service"]).strip().strip("'\"")
    return ""


# --- сборка ----------------------------------------------------------------------

def build(repo: Path, base_arg: Optional[str] = None,
          task_arg: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """(данные отчёта, ошибка). Ошибка — отчёт собрать нельзя (код 2)."""
    repo = repo.resolve()
    top = git_toplevel(repo)
    if top is None:
        return None, f"не git-репозиторий: {repo}"
    kit, why = kit_root(repo)
    if kit is None:
        return None, why
    notes: List[str] = []
    base, base_notes = resolve_base(top, base_arg)
    notes.extend(base_notes)
    changed, git_notes = changed_files(top, base)
    notes.extend(git_notes)
    matrix_path = kit / "traceability-matrix.md"
    matrix_now = matrix_path.read_text(encoding="utf-8", errors="replace")
    matrix_git_rel = matrix_path.resolve().relative_to(top).as_posix()
    matrix_base = _show_base(top, base, matrix_git_rel)
    base_registry, _ = ld.parse_matrix(matrix_base or "")

    files = collect_files(top, kit, base, changed, base_registry, notes)["files"]
    task_id, err = pick_task(files, task_arg)
    if err:
        return None, err
    task_text, task_name = check_task_file(kit, task_id, notes)
    if task_text:
        notes.extend(check_questions(task_text))
    matrix_rec = next((f for f in files if f["kind"] == "matrix"), None)
    matrix = collect_matrix(top, base, {"path": matrix_rec["git_path"], "status": matrix_rec["status"],
                                        "old": matrix_rec["old"]} if matrix_rec else None)
    facts, inner, overflow = collect_facts(top, base, files, notes)
    ids = collect_ids(kit, files, matrix_now, matrix_base, inner, notes)
    affected = collect_affected(kit, files)
    questions = collect_questions(task_text, matrix)
    branch = _git(top, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "—"
    base_sha = (_git(top, "rev-parse", "--short", base).stdout.strip() if base else "") or "—"
    data = {"task": task_id or "", "task_name": task_name,
            "service": find_service(kit, task_text, files),
            "branch": branch, "base": base or "", "base_sha": base_sha,
            "repo": str(repo), "kit": str(kit),
            "files": files, "ids": ids, "matrix": matrix, "affected": affected,
            "facts": facts, "facts_overflow": overflow, "questions": questions,
            "notes": notes}
    return data, None


# --- рендер ----------------------------------------------------------------------

def _debt_line(d: dict) -> str:
    frm = ", ".join(d["from"]) or "—"
    if d["kind"] == "нет цели":
        name = f" «{d['name']}»" if d["name"] else ""
        owner = f" у владельца {d['owner']}" if d["owner"] else ""
        return f"нет целевого артефакта {d['type']}{name}{owner} (от {frm})"
    resp = f"; ответственный: {d['responsible']}" if d["responsible"] else ""
    src = f"; источник: {d['source']}" if d["source"] else ""
    return f"долг «{d['kind']}»: «{d['name']}» (от {frm}{resp}{src})"


def render(data: dict) -> str:
    """Markdown-отчёт по шаблону канона `_meta/templates/delta-report.md`."""
    tid = data["task"] or "задача не определена"
    name = data["task_name"] or "—"
    L: List[str] = [f"# Отчёт дельты: {tid} — {name}", ""]
    task_ref = f"`tasks/{data['task']}.md`, строки `T-{data['task']}-NN`" if data["task"] else "не задана"
    L.append(f"Постановка: {task_ref}. Комплект `{data['service'] or '—'}`, ветка "
             f"`{data['branch']}`, база `{data['base'] or 'рабочее дерево'}` ({data['base_sha']}).")
    L += ["", "## Изменённые файлы", ""]
    cards = [f for f in data["files"] if f["kind"] != "task"]
    if cards:
        L += ["| Файл | Действие | Карточка |", "|---|---|---|"]
        for f in cards:
            action = f["action"] + (f" (из `{f['old']}`)" if f["old"] else "")
            card = f"`{f['id']}`" if f["id"] else "—"
            if f["type"]:
                card += f" ({f['type']})"
            if f["kind"] == "matrix":
                card = "матрица"
            if not f["in_kit"]:
                action += ", вне комплекта"
            L.append(f"| `{f['path']}` | {action} | {card} |")
    else:
        L.append("Изменённых файлов, кроме постановки, нет.")
    tasks = [f for f in data["files"] if f["kind"] == "task"]
    for t in tasks:
        L += ["", f"Постановка: `{t['path']}` — {t['action']}" + (f", `{t['id']}`" if t["id"] else "") + "."]
    ids = data["ids"]
    L += ["", "## Идентификаторы", ""]
    new = ", ".join(f"`{i}`" for i in ids["new"]) or "`—`"
    removed = ", ".join(f"`{i}`" for i in ids["removed"]) or "`—`"
    ok = ("дублей и пропусков нет"
          if not (ids["duplicates"] or ids["outside_registry"] or ids["missing_files"])
          else "есть замечания — см. «Замечания прибора»")
    L.append(f"Новые: {new} (по реестру матрицы, {ok}). Снятые: {removed}.")
    if ids["inner"]:
        L += ["", "Новые внутренние идентификаторы: "
              + "; ".join(f"`{cid}`: {', '.join(v)}" for cid, v in ids["inner"].items()) + "."]
    m = data["matrix"]
    L += ["", "## Матрица трассировки", ""]
    if not m["changed"]:
        L.append("Матрица не изменена.")
    else:
        a, r = m["added"], m["removed"]
        L.append("Новые строки реестра: "
                 + (", ".join(f"`{x['id']}` ({x['type'] or 'тип не указан'}, `{x['file']}`)"
                              for x in a["registry"]) or "нет") + ".")
        if r["registry"]:
            L.append("Снятые строки реестра: " + ", ".join(f"`{x['id']}`" for x in r["registry"]) + ".")
        L += ["", "Связи (добавлено):"] + ([f"- `{x}`" for x in a["links"]] or ["- нет"])
        if r["links"]:
            L += ["", "Связи (снято):"] + [f"- `{x}`" for x in r["links"]]
        L += ["", "Долги (добавлено):"] + ([f"- {_debt_line(d)}" for d in a["debts"]] or ["- нет"])
        if r["debts"]:
            L += ["", "Долги (снято):"] + [f"- {_debt_line(d)}" for d in r["debts"]]
    L += ["", "## Затронуто", ""]
    if not data["affected"]:
        L.append("Изменённых карточек нет.")
    for a in data["affected"]:
        if a["referrers"]:
            refs = ", ".join(f"`{x['id']}`" + (" (изменена в этой дельте)" if x["changed"]
                                                else " (не изменена — почему: …)")
                             for x in a["referrers"])
            L.append(f"- `{a['id']}` ({a['action']}): ссылаются {refs}.")
        else:
            L.append(f"- `{a['id']}` ({a['action']}): ссылающихся карточек нет.")
    L += ["", "## Факты и происхождение", "",
          "| Факт (что записано) | Где | Происхождение |", "|---|---|---|"]
    for f in data["facts"]:
        L.append(f"| {f['fact']} | {f['where']} | {f['origin']} |")
    if not data["facts"]:
        L.append("| — | — | — |")
    if data["facts_overflow"]:
        L.append(f"| …ещё {data['facts_overflow']} | | |")
    L += ["", "Происхождение — одно из четырёх: `T-NN` (постановка), ID карточки (комплект), "
          "адрес внешнего доказательства, номер вопроса. Колонку заполняет агент; строк без "
          "происхождения в таблице быть не должно."]
    q = data["questions"]
    L += ["", "## Открытые вопросы", ""]
    if not q["questions"] and not q["debts"]:
        L.append("нет")
    for x in q["questions"]:
        L.append(f"- вопрос {x['n']}: {x['question']} — ответ: {x['answer']}")
    for d in q["debts"]:
        L.append(f"- долг: {_debt_line(d)}")
    L += ["", "## Проверки", "",
          "`selfcheck`: …; `link_debts`: …; гейт переноса (режим репозитория документации): "
          "`READY` / `NOT READY` — отчёт приложен."]
    if data["notes"]:
        L += ["", "## Замечания прибора", ""] + [f"- {n}" for n in data["notes"]]
    return "\n".join(L) + "\n"


def card_index(kit: Path) -> Dict[str, Path]:
    """ID карточки → файл (frontmatter `id`; README-реестры не считаются,
    как в transfer_gate.card_referrers)."""
    out: Dict[str, Path] = {}
    for f in kit.rglob("*.md"):
        if f.name.lower() == "readme.md" or sc.is_task_file(f, kit) or sc.in_dot_dir(f, kit):
            continue
        fid = (sc.read_frontmatter(f) or {}).get("id")
        if fid:
            out[str(fid)] = f
    return out


def affected_before(kit: Path, ids: List[str]) -> Tuple[List[dict], List[str]]:
    """Режим --affected (решение владельца 2026-10-21): до правок, по ID
    карточек, которые собираются менять, — кто на них ссылается относительной
    ссылкой (входящие, transfer_gate.card_referrers) и на кого ссылаются они
    (исходящие). Детерминированный перечень соседей для шага 2 режима C
    «Разбор постановки и затронутые карточки» — агент любой силы получает его
    из прибора, а не из памяти. Матрица и README-реестры не считаются.
    Возвращает (записи по ID, замечания)."""
    index = card_index(kit)
    by_path = {p.resolve(): i for i, p in index.items()}
    referrers = tg.card_referrers(kit)
    rows: List[dict] = []
    notes: List[str] = []
    for cid in ids:
        f = index.get(cid)
        if f is None:
            notes.append(f"карточка `{cid}` не найдена (frontmatter `id` ни у одного файла комплекта)")
            continue
        outgoing: List[str] = []
        text = f.read_text(encoding="utf-8", errors="replace")
        for rel in tg._MD_LINK_RE.findall(text):
            try:
                tid = by_path.get((f.parent / rel).resolve())
            except OSError:
                tid = None
            if tid and tid != cid and tid not in outgoing:
                outgoing.append(tid)
        # входящие — только карточки комплекта: постановки tasks/ (id T-…) и файлы
        # вне индекса соседями не считаются
        incoming = [i for i in referrers.get(cid, []) if i in index]
        rows.append({"id": cid, "file": f.relative_to(kit).as_posix(),
                     "incoming": incoming, "outgoing": sorted(outgoing)})
    return rows, notes


def render_affected(rows: List[dict], notes: List[str]) -> str:
    L = ["# Затронуто до правок", "",
         "Соседи карточек по относительным ссылкам (матрица и README-реестры не считаются). "
         "Каждая входящая карточка — кандидат в «Затронуто» постановки: меняется или остаётся "
         "со ссылкой — решает разбор по домам.", ""]
    for r in rows:
        L.append(f"## {r['id']} (`{r['file']}`)")
        L.append("")
        L.append("- ссылаются на неё: " + (", ".join(f"`{i}`" for i in r["incoming"]) if r["incoming"] else "нет"))
        L.append("- она ссылается на: " + (", ".join(f"`{i}`" for i in r["outgoing"]) if r["outgoing"] else "нет"))
        L.append("")
    if notes:
        L += ["## Замечания прибора", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(L)


# --- сторож отчёта дельты перед сдачей (--check) -----------------------------

_REPORT_TITLE_RE = re.compile(r"^#\s+Отчёт дельты:\s*(\S+)", re.M)
_REPORT_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
_REPORT_FILE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.M)
_REPORT_TASK_LINE_RE = re.compile(r"^Постановка:\s*`([^`]+)`", re.M)
# заглушки, которые печатает render(): агент обязан их заменить
_REPORT_WHY_STUB = "почему: …"
_REPORT_CHECKS_STUBS = ("`selfcheck`: …", "`READY` / `NOT READY`")


def _report_sections(text: str) -> Dict[str, str]:
    """Разделы отчёта `## Имя` → текст раздела (до следующего `## `)."""
    parts = _REPORT_SECTION_RE.split(text)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def check_report(report_text: str, repo: Optional[Path] = None, base: Optional[str] = None,
                 task: Optional[str] = None) -> List[str]:
    """Сторож заполненного отчёта дельты перед сдачей в описание MR. Проверяет
    то, что агент обязан дописать после сборки прибором (шаблон канона
    `_meta/templates/delta-report.md`), и свежесть отчёта: `repo` задан —
    дельта рабочего дерева собирается заново и файлы, которых нет в разделе
    «Изменённые файлы», — замечание (отчёт собран до части правок, живой прогон
    27.10: «матрица не изменена» при изменённой матрице). Замечания — строки;
    код выхода не меняют."""
    notes: List[str] = []
    secs = _report_sections(report_text)
    if not _REPORT_TITLE_RE.search(report_text) or "Факты и происхождение" not in secs:
        notes.append("это не отчёт дельты по шаблону канона: нет заголовка «# Отчёт дельты: …» "
                     "или раздела «Факты и происхождение» — собери `--task <JIRA-ID> --out <файл>`")
        return notes
    # 1. факты без происхождения (служебные строки прибора «…ещё N» и «—» не считаются)
    rows = [sc.table_cells(r) for r in _split_matrix_rows(secs["Факты и происхождение"].splitlines())]
    rows = [r for r in rows if len(r) >= 3 and not r[0].startswith("…ещё") and r[0].strip() != "—"]
    empty = [r for r in rows if not r[2].strip()]
    if empty:
        notes.append(f"фактов без происхождения: {len(empty)} из {len(rows)} — колонку "
                     "«Происхождение» заполняет агент (строка постановки T-NN, ID карточки "
                     "комплекта или номер вопроса), строк без происхождения быть не должно")
    # 2. затронутые карточки с заглушкой «почему: …»
    n_why = secs.get("Затронуто", "").count(_REPORT_WHY_STUB)
    if n_why:
        notes.append(f"затронутые карточки без ответа «почему не изменена»: {n_why} — заглушка "
                     "«почему: …» заменяется причиной (или карточка правится)")
    # 3. раздел «Проверки» — шаблонный текст или пусто
    chk = secs.get("Проверки", "")
    if not chk.strip() or any(s in chk for s in _REPORT_CHECKS_STUBS):
        notes.append("раздел «Проверки» не заполнен — результаты selfcheck, link_debts и гейта "
                     "переноса вписываются после прогона (новых ✗ нет / NOT READY с чем)")
    # 4. блок «Замечания прибора» оставлен как есть
    rem = [ln for ln in secs.get("Замечания прибора", "").splitlines() if ln.startswith("- ")]
    if rem:
        notes.append(f"блок «Замечания прибора» не разобран: {len(rem)} — каждое либо исправлено "
                     "в комплекте, либо объяснено в отчёте как предсуществующее")
    # 5. свежесть: дельта рабочего дерева против раздела «Изменённые файлы»
    if repo is not None:
        if task is None:
            m = _REPORT_TITLE_RE.search(report_text)
            task = m.group(1) if m else None
        try:
            data, err = build(repo, base, task)
        except Exception as e:  # noqa: BLE001
            data, err = None, repr(e)
        if err or data is None:
            notes.append(f"сверка с дельтой рабочего дерева не выполнена: {err}")
        else:
            files_sec = secs.get("Изменённые файлы", "")
            listed = set(_REPORT_FILE_ROW_RE.findall(files_sec)) | set(_REPORT_TASK_LINE_RE.findall(files_sec))
            missing = sorted({f["path"] for f in data["files"]} - listed)
            if missing:
                notes.append("отчёт собран до части правок — в дельте есть файлы, которых нет в "
                             "«Изменённых файлах»: " + ", ".join(f"`{p}`" for p in missing)
                             + " — пересобери отчёт после всех правок (включая матрицу) и "
                             "заполни заново")
    return notes


def render_check(path: Path, notes: List[str]) -> str:
    """Текст режима --check: замечания сторожа отчёта или «OK»."""
    L = [f"# Отчёт дельты `{path.name}` — проверка перед сдачей", ""]
    if notes:
        L += [f"- {n}" for n in notes] + ["",
              f"i замечаний: {len(notes)} — отчёт к сдаче не готов (create-artifact, режим C, "
              "шаг 8: доведи и проверь снова)"]
    else:
        L.append("OK: отчёт дельты готов к сдаче")
    return "\n".join(L) + "\n"


def render_questions(task_id: str, notes: List[str]) -> str:
    """Текст режима --questions: замечания сторожа формы вопросов или «OK»."""
    L = [f"# Вопросы постановки {task_id} — проверка формы", ""]
    if notes:
        L += [f"- {n}" for n in notes] + ["",
              f"i замечаний: {len(notes)} — переформулируй по правилам опроса "
              "(_meta/rules/questions.md) до показа аналитику"]
    else:
        L.append("OK: замечаний по вопросам нет")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Отчёт дельты комплекта документации по изменениям рабочего дерева "
                    "относительно базы (режим «изменение по постановке»)")
    ap.add_argument("--repo", required=True, type=Path,
                    help="корень клона репозитория документации (комплект в корне или в docs/)")
    ap.add_argument("--base", default=None,
                    help="ref базы дельты (по умолчанию master, иначе main, иначе HEAD)")
    ap.add_argument("--task", default=None,
                    help="JIRA-ID задачи; без ключа — из единственной постановки tasks/ в дельте")
    ap.add_argument("--out", type=Path, default=None, help="записать отчёт в файл (UTF-8, \\n)")
    ap.add_argument("--json", action="store_true", help="дополнительно вывести данные в JSON")
    ap.add_argument("--affected", default=None,
                    help="ДО правок: ID карточек через запятую — кто на них ссылается и на кого "
                         "ссылаются они (соседи для шага 2 режима C); отчёт дельты не строится")
    ap.add_argument("--questions", default=None, metavar="JIRA-ID",
                    help="ДО показа аналитику: проверка формы таблицы «Вопросы и ответы» "
                         "постановки tasks/<JIRA-ID>.md по правилам опроса; код 0 и при "
                         "замечаниях, код 2 — постановки нет; отчёт дельты не строится")
    ap.add_argument("--check", type=Path, default=None, metavar="ФАЙЛ.md",
                    help="ПЕРЕД СДАЧЕЙ: проверка заполненного отчёта дельты (происхождение "
                         "фактов, «почему: …», «Проверки», замечания прибора) и его свежести "
                         "против дельты --repo; код 0 и при замечаниях, код 2 — файла нет")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.check is not None:
        if not a.check.is_file():
            print(f"✗ отчёт дельты не найден: {a.check}")
            return 2
        report_text = a.check.read_text(encoding="utf-8", errors="replace")
        notes = check_report(report_text, a.repo, a.base, a.task)
        text = render_check(a.check, notes)
        if a.out is not None:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print(f"i проверка отчёта записана: {a.out}")
        else:
            print(text, end="")
        if a.json:
            print(json.dumps({"report": str(a.check), "notes": notes}, ensure_ascii=False, indent=1))
        return 0
    if a.affected:
        kit, err = kit_root(a.repo.resolve())
        if err:
            print(f"✗ соседи не найдены: {err}")
            return 2
        ids = [i.strip() for i in a.affected.split(",") if i.strip()]
        rows, notes = affected_before(kit, ids)
        text = render_affected(rows, notes)
        if a.out is not None:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print(f"i соседи записаны: {a.out}")
        else:
            print(text, end="")
        if a.json:
            print(json.dumps({"affected": rows, "notes": notes}, ensure_ascii=False, indent=1))
        return 0 if rows else 2
    if a.questions:
        task_id = a.questions.strip()
        kit, err = kit_root(a.repo.resolve())
        path = kit / "tasks" / f"{task_id}.md" if kit is not None else None
        if path is None or not path.is_file():
            print(f"✗ постановка не найдена: tasks/{task_id}.md" + (f" ({err})" if err else ""))
            return 2
        task_text = path.read_text(encoding="utf-8", errors="replace")
        notes = check_questions(task_text)
        text = render_questions(task_id, notes)
        if a.out is not None:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print(f"i проверка вопросов записана: {a.out}")
        else:
            print(text, end="")
        if a.json:
            print(json.dumps({"questions": all_task_questions(task_text), "notes": notes},
                             ensure_ascii=False, indent=1))
        return 0
    try:
        data, err = build(a.repo, a.base, a.task)
    except Exception as e:  # noqa: BLE001
        print(f"✗ отчёт дельты не собран: {e!r}")
        return 2
    if err:
        print(f"✗ отчёт дельты не собран: {err}")
        return 2
    text = render(data)
    if a.out is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"i отчёт дельты записан: {a.out}")
    else:
        print(text, end="")
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
