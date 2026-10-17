# app/scripts/CI/kitcheck/checks/catalog_api.py
"""Проверки selfcheck: catalog_api — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import json
import re
try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md
    from kitcheck.md import read_frontmatter
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md  # type: ignore
    from ..md import read_frontmatter  # type: ignore


_REPO_HOST = "https://gitlab.gboteam.ru/"


_REPO_TREE_RE = re.compile(r"/-/(tree|blob|raw)/([^/?#]+)")


# адрес каталога контрактов чужого сервиса по коду (документ адресации
# §5.2): код сервиса = имя репозитория кода без префикса ms-
_API_SPEC_RULE = ("https://gitlab.gboteam.ru/ECO_BE/ms-{code}"
                  "/-/tree/HEAD/api-specification")


def check_no_api_in_bundle(docs: Path) -> Tuple[List[str], bool]:
    """Контракты OpenAPI/AsyncAPI живут в api-specification/ репозитория
    кода (решение 2026-10-06): каталог `api/` и YAML-контракты в
    комплекте — унаследованное состояние, ⚠ до удаления владельцем;
    вердикт не трогает (docs-sign, docs-file-storage на момент решения
    такие каталоги несли)."""
    lines: List[str] = []
    dirs = sorted(p for p in docs.rglob("api") if p.is_dir())
    for d in dirs:
        n = sum(1 for f in d.rglob("*") if f.is_file())
        lines.append(f"⚠ контракты в комплекте: каталог "
                     f"{d.relative_to(docs).as_posix()}/ ({n} файлов) — "
                     "контракты OpenAPI/AsyncAPI живут в api-specification/ "
                     "репозитория кода, в комплекте каталог api/ не "
                     "создаётся (унаследованное состояние: убрать при "
                     "ближайшей правке)")
    yamls = []
    for f in sorted(docs.rglob("*.y*ml")):
        if f.suffix.lower() not in (".yaml", ".yml"):
            continue
        if any(p.name == "api" for p in f.relative_to(docs).parents):
            continue  # уже учтён каталогом
        try:
            head = _fs.read_text(f, encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if re.search(r"^(openapi|asyncapi):", head, re.M):
            yamls.append(f.relative_to(docs).as_posix())
    if yamls:
        lines.append(f"⚠ контракты в комплекте: YAML OpenAPI/AsyncAPI ×"
                     f"{len(yamls)} ({', '.join(yamls[:3])}"
                     f"{'…' if len(yamls) > 3 else ''}) — копий контрактов "
                     "в комплекте нет, единственная копия — "
                     "api-specification/ репозитория кода")
    return lines, True


_DEFAULT_BRANCHES = {"master", "main", "trunk", "develop"}


_API_SECTION_RE = re.compile(r"^#{1,3}\s+(?:\d+\.\s*)?Покрытие:\s*API\s*↔\s*SRS",
                             re.M)


_LINK_REF_RE = re.compile(r"https?://[^\s)]+?/-/(?:blob|tree|raw)/([^/\s)]+)/")


def check_api_matrix_refs(docs: Path, strict: bool = False
                          ) -> Tuple[List[str], bool]:
    """Ссылки раздела матрицы «Покрытие: API ↔ SRS» ведут в репозиторий
    кода через HEAD (решение 2026-10-06, вариант В по вопросу 1):
    явный ref допустим, только если комплект описывает не основную
    линию кода — тогда ref назван в шапке раздела (между заголовком и
    таблицей, в обратных кавычках) с причиной, и ссылки с ним ✓. Иной
    явный ref — ⚠; имя ветки по умолчанию (master/main/trunk/develop)
    — ✗ в строгом профиле, ⚠ в командном."""
    matrix = docs / "traceability-matrix.md"
    if not matrix.is_file():
        return [], True
    text = _fs.read_text(matrix, encoding="utf-8", errors="replace")
    m = _API_SECTION_RE.search(text)
    if not m:
        return [], True
    level = len(m.group(0)) - len(m.group(0).lstrip("#"))
    rest = text[m.end():]
    # раздел тянется до следующего заголовка того же или верхнего уровня
    # (подразделы «### 3.1. REST …» — внутри; docs-sign)
    nxt = re.search(r"^#{1,%d}\s" % level, rest, re.M)
    section = rest[:nxt.start()] if nxt else rest
    first_row = re.search(r"^\|", section, re.M)
    header = section[:first_row.start()] if first_row else section
    used = _LINK_REF_RE.findall(section)
    # объявленный ref — токен в обратных кавычках шапки, который реально
    # стоит в ссылках раздела (прочие кавычки шапки — пути, ID — не ref)
    declared = set(re.findall(r"`([^`\s]+)`", header)) & set(used)
    lines: List[str] = []
    ok = True
    refs: Dict[str, int] = {}
    for ref in used:
        if ref == "HEAD" or ref in declared:
            continue
        refs[ref] = refs.get(ref, 0) + 1
    for ref, n in sorted(refs.items()):
        if ref in _DEFAULT_BRANCHES:
            mark = "✗" if strict else "⚠"
            ok = ok and not strict
            lines.append(f"{mark} матрица «API ↔ SRS»: ссылки с именем ветки "
                         f"по умолчанию `{ref}` ×{n} — вместо него HEAD "
                         "(адрес переживает переименование ветки)")
        else:
            lines.append(f"⚠ матрица «API ↔ SRS»: ссылки с явным ref "
                         f"`{ref}` ×{n} — допустимо только для комплекта "
                         "не основной линии кода: назвать ref в шапке "
                         "раздела с причиной (conventions §5.3 п. 7)")
    if declared:
        lines.append("i матрица «API ↔ SRS»: в шапке раздела назван ref "
                     f"{', '.join(sorted(declared))} — ссылки с ним приняты")
    return lines, ok


def _repo_format_issue(url: str) -> Optional[str]:
    """Отклонение адреса `repo` от правила адресации; None — норма."""
    if not url.startswith(_REPO_HOST):
        return f"адрес не в GitLab контура ({_REPO_HOST})"
    if "?" in url or "#" in url:
        return "хвост запроса/якоря (например `?ref_type=heads`) — " \
               "адрес должен оканчиваться путём"
    m = _REPO_TREE_RE.search(url)
    if m and m.group(1) != "tree":
        return f"сегмент `/-/{m.group(1)}/` — корень комплекта " \
               "адресуется через `/-/tree/HEAD/<путь>`"
    if m and m.group(2) != "HEAD":
        return f"имя ветки `{m.group(2)}` в адресе — вместо него `HEAD`" \
               " (адрес переживает переименование ветки)"
    return None


def _service_codes(docs: Path) -> Dict[str, int]:
    """Коды `service:` из frontmatter карточек комплекта → число файлов."""
    codes: Dict[str, int] = {}
    for f in _kit_md(docs):
        fm = read_frontmatter(f) or {}
        code = fm.get("service", "").strip().strip("'\"")
        if code:
            codes[code] = codes.get(code, 0) + 1
    return codes


def check_service_catalog(catalog: Optional[Path],
                          docs: Path) -> Tuple[List[str], bool]:
    """Целостность каталога сервисов и наличие в нём кода комплекта.
    Все сигналы — ⚠ (вердикт не трогают); ok всегда True."""
    if catalog is None:
        return [], True
    import json
    try:
        data = json.loads(_fs.read_text(catalog, encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return [f"⚠ каталог сервисов: {catalog.name} не читается "
                f"({e.__class__.__name__}: {e}) — адресация чужих "
                "сервисов по каталогу невозможна"], True
    items = data if isinstance(data, list) else data.get("services")
    if not isinstance(items, list):
        return [f"⚠ каталог сервисов: {catalog.name} — ожидался список "
                "записей"], True
    lines: List[str] = []
    by_code: Dict[str, List[str]] = {}
    by_key: Dict[str, List[str]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip() or "<без имени>"
        code = str(it.get("code", "")).strip()
        key = str(it.get("key", "")).strip()
        if code:
            by_code.setdefault(code, []).append(name)
        if key:
            by_key.setdefault(key, []).append(name)
        repo = it.get("repo")
        if isinstance(repo, str) and repo.strip():
            issue = _repo_format_issue(repo.strip())
            if issue:
                lines.append(f"⚠ каталог сервисов: repo у `{code or name}` — "
                             f"{issue}: {repo.strip()}")
        # поле api — адрес каталога контрактов ТОЛЬКО для исключений из
        # правила «ECO_BE/ms-<code>/-/tree/HEAD/api-specification»
        # (документ адресации §5.2, решение 2026-10-06); форма та же,
        # что у repo
        dom_field = it.get("domain")
        if isinstance(dom_field, str) and dom_field.strip() \
                and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", dom_field.strip()):
            lines.append(f"⚠ каталог сервисов: domain у `{code or name}` — "
                         f"не kebab-case ({dom_field.strip()})")
        api = it.get("api")
        if isinstance(api, str) and api.strip():
            issue = _repo_format_issue(api.strip())
            if issue:
                lines.append(f"⚠ каталог сервисов: api у `{code or name}` — "
                             f"{issue}: {api.strip()}")
            elif api.strip() == _API_SPEC_RULE.format(code=code):
                lines.append(f"⚠ каталог сервисов: api у `{code}` совпадает "
                             "с адресом по правилу — поле для исключений, "
                             "здесь лишнее")
    for code, names in sorted(by_code.items()):
        if len(names) > 1:
            lines.append(f"⚠ каталог сервисов: код `{code}` у {len(names)} "
                         f"записей ({'; '.join(names)}) — по коду нельзя "
                         "однозначно найти сервис")
    for key, names in sorted(by_key.items()):
        if len(names) > 1:
            lines.append(f"⚠ каталог сервисов: ключ `{key}` у {len(names)} "
                         f"записей ({'; '.join(names)})")
    for code, n in sorted(_service_codes(docs).items()):
        if code in by_code:
            entry = next((it for it in items if isinstance(it, dict)
                          and str(it.get("code", "")).strip() == code), {})
            repo = str(entry.get("repo", "")).strip()
            lines.append(f"✓ каталог сервисов: код `{code}` ({n} файлов) — "
                         f"запись найдена" + (f", repo {repo}" if repo
                                              else ", поле repo не заполнено"))
        else:
            lines.append(f"⚠ каталог сервисов: код `{code}` из frontmatter "
                         f"{n} файлов не найден в каталоге — по коду ищут "
                         "запись сервиса при адресации; привести `service:` "
                         "к коду каталога или завести запись")
    return lines, True
