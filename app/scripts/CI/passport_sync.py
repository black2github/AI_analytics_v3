# app/scripts/CI/passport_sync.py
#
# ПАСПОРТ РАСКЛАДКИ ЭКО ДЛЯ ПЛАТФОРМЫ AI FACTORY — сборка машинной части из
# канона и сторож расхождений прозаической части. Решение владельца канона
# 2026-10-10 (гармонизация с платформой, предложения P-17/P-11/P-09):
# «паспорт раскладки проекта ЭКО — производное от стандарта ЭКО и канона
# миграции; машинная часть собирается инструментом, прозаическая сверяется
# сторожем; дом значений — стандарт, не паспорт».
#
# ЗАЧЕМ. Платформа читает значения проекта из паспорта (`docs-kit-layout.md`
# для ролей и `docs-kit-layout.yaml` для скриптов). Пока паспорт пишется
# руками, он отстаёт от стандарта: снимок от 2026-09-22 требовал ветку
# `develop` в ссылках на код (стандарт — `HEAD`) и место AsyncAPI в
# `lib-api-<service>` (концепция техбука снята 2026-10, действует
# `api-specification/` репозитория сервиса). Каждое такое расхождение —
# разные инструкции аналитику миграции и агенту платформы на одном
# комплекте. Утилита переводит спор из писем в диф: собирает yaml из домов
# фактов канона и показывает, где паспорт платформы с ними расходится.
#
# ДОМА ФАКТОВ, из которых собирается паспорт (ничего не придумывается):
#   - шаблон README комплекта `_meta/templates/docs-readme.md`, таблица
#     «Типы артефактов (префиксы ID)» — префиксы и каталоги типов
#     (самоописание комплекта, решение 2026-10-10);
#   - шаблоны типов `_meta/templates/*.md` — формы идентификаторов
#     (`id: FUN-CL-NN`, `id: ENT-001`) → ширина номера;
#   - документ адресации `_meta/migration/cross-service-addressing.md` и
#     прибор `selfcheck.py` — адрес контрактов в репозитории кода
#     (`ECO_BE/ms-<code>/-/tree/HEAD/api-specification`), раздел матрицы
#     «Покрытие: API ↔ SRS»;
#   - каталог сервисов `_meta/services.json` — группы репозиториев (EAN —
#     документация, EAS — рабочие репозитории миграции);
#   - репозиторий базовых контрактов (если указан --contracts) — коды
#     внешних АС = имена папок корня.
#   Соответствие «тип канона → навык платформы» — единственная таблица,
#   которую утилита задаёт сама (TYPE_TO_SKILL ниже): имена навыков —
#   собственность платформы, при смене имён меняется только эта таблица.
#
# РЕЖИМЫ.
#   --build <выходной .yaml>   собрать `docs-kit-layout.yaml` проекта ЭКО из
#                              канона; расширения канона (типы без навыка
#                              платформы, группы репозиториев) — отдельными
#                              ключами `canon_types`, `repos`, которые
#                              скрипты платформы не читают, а люди — да.
#   --check <каталог паспорта> сверить паспорт платформы (`docs-kit-layout.md`
#                              и `.yaml` в каталоге) с каноном: машинная
#                              часть — по полям, прозаическая — по известным
#                              домам фактов (место AsyncAPI, реф ссылки на
#                              код, набор типов и префиксов, поля
#                              frontmatter, имена разделов README и матрицы).
#                              Выход: markdown-таблица «Статус | Тема | В
#                              паспорте платформы | В стандарте ЭКО и каноне
#                              миграции | Дом факта», строки сгруппированы:
#                              ≠ расхождения, затем i объявленные отличия
#                              (не расхождения), затем = совпадения; итоговая
#                              строка со счётом; код возврата 1 при
#                              расхождениях.
#   --canon <путь>             корень клона канона (по умолчанию — канон,
#                              в котором лежит утилита; из analyzer —
#                              обязателен)
#   --contracts <путь>         клон `docs-external-contracts` для списка
#                              кодов АС (без него сегменты АС не собираются,
#                              а в проверке не сравниваются)
#   --json                     отчёт проверки дополнительно в JSON
#
# ПРИМЕР.
#   python _meta/tools/passport_sync.py --build out/docs-kit-layout.yaml
#   python _meta/tools/passport_sync.py --check C:\doc-as-code\ai-factory\analytics-agent-prose\projects\eco\knowledge\analytics-docs-kit
#
# ОГРАНИЧИТЕЛИ. Утилита не правит ни канон, ни паспорт платформы.
# Прозаический паспорт не генерируется: пересказ стандартов остаётся за
# людьми, сторож лишь показывает, где пересказ отстал. Проверка не знает
# фактов, у которых нет дома в каноне, — такие расхождения ищутся руками
# (реестр R-NN в разборе материалов платформы).

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import selfcheck as sc  # noqa: E402

try:
    import yaml  # noqa: E402
except ImportError:  # pragma: no cover
    yaml = None

_HERE = Path(__file__).resolve().parent

# тип канона (каталог/файл в комплекте) → навык платформы; None — навыка нет
TYPE_TO_SKILL: Dict[str, Optional[str]] = {
    "service-vision.md": "service-vision",
    "glossary.md": "glossary",
    "brd/features/": "feature-spec",
    "brd/use-cases/": "use-case",
    "brd/business-rules.md": "business-rules",
    "srs/process/status-model.md": "status-model",
    "srs/process/": "process",
    "srs/data-model/": "data-model",
    "srs/data-model/dictionaries.md": "data-model",
    "srs/function/": "functions",
    "srs/screen-form/": "screen-forms",
    "srs/control/": "controls",
    "srs/print-form/": "print-forms",
    "srs/ntf-notification.md": "ntf-notification",
    "srs/contract-call/": "contract-call",
    "srs/rbac.md": "rbac",
    "srs/internal-contract/": None,
    "srs/lib-contract/": None,
    "srs/platform-functions.md": None,
    "srs/agent/": None,
}
# префиксы, которые не нумеруют документы (внутренние элементы карточек)
_INNER_PREFIXES = {"US", "FR", "NFR", "RR", "FLD", "EV", "B", "MSG", "BR", "ТР"}
_CONTOURS = ["cl", "bnk", "sys"]
_SEGMENTS_FIXED = ["grp", "ext", "int"]

_PREFIX_ROW_RE = re.compile(r"^\|\s*\*\*([^*|]+)\*\*\s*\|([^|]*)\|([^|]*)\|", re.M)
_ID_FORM_RE = re.compile(r"^id:\s*([A-Z]+(?:-[A-Z<>]+)*)-(N+|\d+)\s*$", re.M)


# --- чтение домов фактов канона -------------------------------------------------

def readme_prefix_table(canon: Path) -> List[Tuple[str, str, str]]:
    """[(префикс(ы), назначение, путь)] из таблицы типов шаблона README."""
    text = (canon / "_meta/templates/docs-readme.md").read_text(encoding="utf-8",
                                                                errors="replace")
    m = re.search(r"### Типы артефактов.*?\n(\|.*?)(?:\n\n|\Z)", text, re.S)
    rows: List[Tuple[str, str, str]] = []
    if not m:
        return rows
    for pm in _PREFIX_ROW_RE.finditer(m.group(1)):
        rows.append((pm.group(1).strip(), pm.group(2).strip(), pm.group(3).strip()))
    return rows


def prefixes_from_table(rows) -> List[str]:
    out: List[str] = []
    for cell, _, _ in rows:
        for tok in re.split(r"\s*/\s*", cell):
            head = tok.strip().split("-")[0]
            if re.fullmatch(r"[A-ZА-Я]{1,6}", head) and head not in _INNER_PREFIXES \
                    and head.lower() not in out:
                out.append(head.lower())
    return out


def paths_from_table(rows) -> List[str]:
    out: List[str] = []
    for _, _, where in rows:
        for p in re.findall(r"`([^`]+)`", where):
            p = p.strip()
            if p and p not in out and not p.startswith("<"):
                out.append(p)
    return out


def id_widths(canon: Path) -> Dict[str, int]:
    """Ширина номера по формам `id:` в шаблонах типов: {префикс: цифр}."""
    widths: Dict[str, int] = {}
    for t in sorted((canon / "_meta/templates").glob("*.md")):
        text = t.read_text(encoding="utf-8", errors="replace")
        for m in _ID_FORM_RE.finditer(text):
            head = m.group(1).split("-")[0]
            w = len(m.group(2))
            if head not in widths or m.group(2).startswith("N"):
                widths[head] = w
    return widths


def catalog_groups(canon: Path) -> Dict[str, str]:
    """Группы GitLab из каталога сервисов: {docs: EAN, src: EAS}."""
    p = canon / "_meta/services.json"
    groups: Dict[str, str] = {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return groups
    rows = data if isinstance(data, list) else data.get("services", data)
    rows = rows if isinstance(rows, list) else list(rows.values())
    for r in rows:
        repo = (r.get("repo") or "")
        m = re.match(r"https://gitlab\.gboteam\.ru/([^/]+)/(docs|src)-", repo)
        if m:
            groups.setdefault(m.group(2), m.group(1))
    return groups


def as_codes(contracts: Optional[Path]) -> List[str]:
    if contracts is None or not contracts.is_dir():
        return []
    return sorted(p.name for p in contracts.iterdir()
                  if p.is_dir() and not p.name.startswith(".")
                  and re.fullmatch(r"[a-z0-9-]+", p.name))


# --- сборка ---------------------------------------------------------------------

def build_layout(canon: Path, contracts: Optional[Path] = None) -> dict:
    rows = readme_prefix_table(canon)
    prefixes = prefixes_from_table(rows)
    # базовые контракты внешних АС живут вне комплекта (docs-external-contracts),
    # в таблице README комплекта их нет, но семейство ID — каноническое
    # (шаблон contract-call.md: `EXTINT-<AS>-NNN`)
    if "extint" not in prefixes:
        prefixes.append("extint")
    paths = paths_from_table(rows)
    code_rule = sc._API_SPEC_RULE  # https://gitlab.gboteam.ru/ECO_BE/ms-{code}/-/tree/HEAD/api-specification
    code_group = re.search(r"gboteam\.ru/([^/]+)/", code_rule).group(1)
    groups = catalog_groups(canon)
    skills: List[dict] = []
    canon_types: List[dict] = []
    # более специфичные пути раньше: файлы перед каталогами, длинные перед короткими
    for p in sorted(paths, key=lambda s: (s.endswith("/"), -len(s))):
        skill = TYPE_TO_SKILL.get(p, "?")
        if skill == "?":
            continue  # путь без решения о навыке — не выдумывать
        if skill is None:
            canon_types.append({"path": p, "skill": None,
                                "note": "тип канона миграции; у платформы навыка нет — "
                                        "документ без навыка (канон §10)"})
        elif not any(s["path"] == p for s in skills):
            skills.append({"path": p, "skill": skill})
    skills.append({"path": "api-specification/", "skill": "api-openapi"})
    skills.append({"path": "api-specification/", "skill": "api-asyncapi",
                   "note": "AsyncAPI лежит рядом с OpenAPI в api-specification/ "
                           "репозитория сервиса (техбук api-first-async-yojo); "
                           "отдельного каталога asyncapi/ и репозитория lib-api-* нет"})
    widths = id_widths(canon)
    layout = {
        "schema": 1,
        "kit": "eco",
        "traceability": {
            "file": "traceability-matrix.md",
            "api_coverage_section": "Покрытие: API ↔ SRS",
            "registry_section": "Реестр ID",
            "debts_section": "Долги по ссылкам",
        },
        "business_layer": {"marker_dir": "brd"},
        "layers": [
            {"path": "brd/", "sublayers": False},
            {"path": "srs/", "sublayers": True},
            {"path": "api-specification/", "sublayers": False,
             "note": "репозиторий кода ECO_BE/ms-<service>, не комплект"},
        ],
        "skills_by_path": skills,
        "ids": {
            "prefixes": prefixes,
            "segments": _CONTOURS + _SEGMENTS_FIXED + as_codes(contracts),
            "parts": "readme",
            "constant": {"status_model": "SM-000"},
            "widths": {k.lower(): v for k, v in sorted(widths.items())},
        },
        "links": {
            "code_ref": "HEAD",
            "code_contracts": code_rule.replace("{code}", "<service-id>"),
            "docs_ref": "HEAD",
        },
        "canon_types": canon_types,
        "repos": {
            "code_group": code_group,
            "docs_group": groups.get("docs", "EAN"),
            "src_group": groups.get("src", "EAS"),
            "external_contracts": f"{groups.get('docs', 'EAN')}/docs-external-contracts",
            "code": f"{code_group}/ms-<service-id>",
            "docs": f"{groups.get('docs', 'EAN')}/docs-<service-id>",
            "src": f"{groups.get('src', 'EAS')}/src-<service-id>",
        },
        "frontmatter": {
            "required": ["id|partOf", "type", "service"],
            "provenance": ["title", "confluence_page_ids"],
            "historical": ["version"],
        },
    }
    return layout


def dump_layout(layout: dict) -> str:
    head = ("# Машинная раскладка комплекта документов проекта `eco` (Экосистема).\n"
            "# СОБРАНО ИНСТРУМЕНТОМ passport_sync.py из канона миграции и каталога сервисов —\n"
            "# не редактировать руками: правка значения делается в доме факта (шаблон README,\n"
            "# документ адресации, каталог сервисов), затем сборка повторяется.\n"
            "# Ключи canon_types, repos, links, frontmatter, ids.widths — расширения канона;\n"
            "# скрипты платформы их не читают.\n\n")
    if yaml is None:
        return head + json.dumps(layout, ensure_ascii=False, indent=2)
    return head + yaml.safe_dump(layout, allow_unicode=True, sort_keys=False, width=100)


# --- проверка -------------------------------------------------------------------

class Report:
    """Структурные записи сверки: (статус, тема, в паспорте, в стандарте, дом факта).
    Выводится таблицей с группировкой: сначала расхождения, затем объявленные
    отличия, затем совпадения — человек видит отличия в привычном виде."""

    _ORDER = {"≠": 0, "i": 1, "=": 2}
    _LABEL = {"≠": "расхождение", "i": "объявленное отличие", "=": "совпадает"}

    def __init__(self) -> None:
        self.rows: List[Tuple[str, str, str, str, str]] = []

    def add(self, mark: str, topic: str, passport: str, canon: str, home: str = "") -> None:
        self.rows.append((mark, topic, passport, canon, home))

    @property
    def diffs(self) -> int:
        return sum(1 for r in self.rows if r[0] == "≠")

    def sorted_rows(self) -> List[Tuple[str, str, str, str, str]]:
        return sorted(self.rows, key=lambda r: self._ORDER.get(r[0], 9))

    def summary(self) -> str:
        same = sum(1 for r in self.rows if r[0] == "=")
        info = sum(1 for r in self.rows if r[0] == "i")
        return (f"ИТОГ: расхождений {self.diffs}, объявленных отличий {info}, "
                f"совпадений {same}")

    def render(self) -> List[str]:
        """Markdown-таблица с группировкой и итоговой строкой."""
        esc = lambda s: s.replace("|", "\\|").replace("\n", " ")  # noqa: E731
        out = ["| Статус | Тема | В паспорте платформы | В стандарте ЭКО и каноне миграции | Дом факта |",
               "|---|---|---|---|---|"]
        for m, t, p, c, h in self.sorted_rows():
            out.append(f"| {m} {self._LABEL[m]} | {esc(t)} | {esc(p)} | {esc(c)} | {esc(h)} |")
        out.append("")
        out.append(self.summary())
        return out

    def as_dicts(self) -> List[dict]:
        return [{"status": m, "topic": t, "passport": p, "canon": c, "home": h}
                for m, t, p, c, h in self.sorted_rows()]


def _find(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text, re.M)
    if not m:
        return None
    line_no = text[:m.start()].count("\n") + 1
    return f"строка {line_no}: «{m.group(0).strip()[:110]}»"


def check_passport(canon: Path, passport_dir: Path,
                   contracts: Optional[Path] = None) -> Report:
    rep = Report()
    built = build_layout(canon, contracts)
    md_path = passport_dir / "docs-kit-layout.md"
    yml_path = passport_dir / "docs-kit-layout.yaml"
    md = md_path.read_text(encoding="utf-8", errors="replace") if md_path.is_file() else ""
    their: dict = {}
    if yml_path.is_file() and yaml is not None:
        try:
            their = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            rep.add("≠", "yaml паспорта", f"не разбирается: {e}", "разбираемый yaml", "—")
    if not md and not their:
        rep.add("≠", "паспорт", f"в {passport_dir} нет docs-kit-layout.md / .yaml",
                "паспорт из двух файлов", "—")
        return rep

    # 1. место AsyncAPI
    hit = _find(md, r".*(lib-api-<service>|asyncapi/jms\.yaml).*")
    y_async = any(l.get("path") == "asyncapi/" for l in their.get("layers", []) or [])
    if hit or y_async:
        rep.add("≠", "Место AsyncAPI",
                "отдельный репозиторий `ECO_BE/lib-api-<service>`, файл `asyncapi/jms.yaml`"
                + (f" ({hit})" if hit else "") + ("; в yaml — слой `asyncapi/`" if y_async else ""),
                "`api-specification/<service>-<surface>-asyncapi.yaml` в репозитории "
                "`ECO_BE/ms-<service>` рядом с OpenAPI",
                "cross-service-addressing §2, §5.2 (SF-01); техбук concepts/api-first-async-yojo "
                "(прежняя api-first-async — deprecated)")
    else:
        rep.add("=", "Место AsyncAPI", "api-specification/ репозитория сервиса",
                "api-specification/ репозитория сервиса", "SF-01")

    # 2. реф ссылки на репозиторий кода
    hit = _find(md, r".*(blob/develop/|явная ветка).*")
    if hit:
        rep.add("≠", "Реф в ссылке на репозиторий кода",
                f"явная ветка, пример `develop` ({hit})",
                "`HEAD`; явный ref только у комплекта не основной линии, назван один раз в "
                "шапке раздела матрицы «Покрытие: API ↔ SRS»",
                "conventions §5.3 п. 7 (строки 102–103, 605–610); repo-topology 412–416 "
                "«согласованный merge: код — в default branch»; ADR-0017")
    else:
        rep.add("=", "Реф в ссылке на репозиторий кода", "HEAD", "HEAD", "conventions §5.3 п. 7")

    # 3. адрес контрактов
    if "ECO_BE/ms-<service>" in md or "ECO_BE/ms-" in json.dumps(their, ensure_ascii=False):
        rep.add("=", "Адрес контрактов OpenAPI", "`ECO_BE/ms-<service>/api-specification/`",
                "`ECO_BE/ms-<service-id>/-/tree/HEAD/api-specification`",
                "cross-service-addressing §5.2; selfcheck")
    else:
        rep.add("≠", "Адрес контрактов OpenAPI", "не назван",
                built["links"]["code_contracts"], "cross-service-addressing §5.2")

    # 4. префиксы
    ours = set(built["ids"]["prefixes"])
    theirs = {str(p).lower() for p in (their.get("ids", {}) or {}).get("prefixes", [])}
    if theirs:
        missing = sorted(ours - theirs)
        extra = sorted(theirs - ours)
        if missing:
            rep.add("≠", "Префиксы ID в yaml",
                    "нет " + ", ".join(p.upper() for p in missing),
                    "семейства " + ", ".join(p.upper() for p in built["ids"]["prefixes"]),
                    "шаблон docs-readme.md, таблица «Типы артефактов» (Д-35)")
        else:
            rep.add("=", "Префиксы ID в yaml", "все префиксы канона есть", "—",
                    "шаблон docs-readme.md")
        if extra:
            rep.add("i", "Префиксы сверх канона",
                    ", ".join(p.upper() for p in extra) + " — наблюдения платформы по "
                    "существующим комплектам",
                    "не типы канона: INS — практика docs-sign вне srs/; SCRP, PRC, DM — "
                    "старая нотация", "решение 2026-09-28 (Д-27 п. 5)")
    # 5. набор type
    closed = re.search(r"Закрытый набор `type`.*?\n(?:.*\n){0,4}", md)
    closed_txt = closed.group(0) if closed else ""
    for t, where in (("internal-contract", "srs/internal-contract/"),
                     ("lib-contract", "srs/lib-contract/"),
                     ("agent", "srs/agent/")):
        if f"`{t}`" in closed_txt and "читай как есть" not in closed_txt:
            rep.add("=", f"Тип `{t}`", "в закрытом наборе", "тип канона", "шаблон типа")
        else:
            rep.add("i", f"Тип `{t}`",
                    "вне закрытого набора: «документ без навыка», читается как источник",
                    f"тип канона миграции, каталог `{where}`, объявлен в README комплекта",
                    "шаблон типа; канон платформы §10; письмо платформе, вопрос 3")

    # 6. поля frontmatter
    if re.search(r"`title`[^\n]*не добавлять", md):
        rep.add("i", "Поле frontmatter `title`", "в новые документы не добавлять",
                "провенанс reverse: дословное наименование страницы источника; у forward-"
                "документов не требуется; объявлено в README комплекта",
                "шаблон docs-readme.md «Поля frontmatter»")
    if re.search(r"`version`[^\n]*историческ", md):
        rep.add("=", "Поле frontmatter `version`", "историческое: не добавлять, не трогать",
                "необязательно, старые комплекты не трогаются", "Д-27 п. 4")
    if "confluence_page_ids" not in md:
        rep.add("i", "Поле frontmatter `confluence_page_ids`", "паспорт поля не знает",
                "привязка карточки к страницам источника на время переноса и доработки "
                "задач; объявлено в README комплекта", "шаблон docs-readme.md «Поля frontmatter»")

    # 7. имена разделов README
    for name in ("Условные обозначения", "Подсервисы"):
        if name in md:
            rep.add("=", f"README «{name}»", "читает раздел под этим именем",
                    "дом контуров, частей, типов, статусной модели, полей", "SF-02")
        else:
            rep.add("≠", f"README «{name}»", "раздел не назван",
                    "дом контуров/частей комплекта", "SF-02")

    # 8. матрица
    tr = their.get("traceability", {}) or {}
    if tr.get("file", "traceability-matrix.md") != "traceability-matrix.md":
        rep.add("≠", "Имя матрицы", str(tr.get("file")), "traceability-matrix.md", "conventions §5.3")
    else:
        rep.add("=", "Имя матрицы", "traceability-matrix.md", "traceability-matrix.md",
                "conventions §5.3")
    if tr.get("api_coverage_section") == "Покрытие: API ↔ SRS":
        rep.add("=", "Раздел матрицы API", "«Покрытие: API ↔ SRS»", "«Покрытие: API ↔ SRS»",
                "selfcheck; conventions §5.3 п. 7")
    elif tr:
        rep.add("≠", "Раздел матрицы API", f"«{tr.get('api_coverage_section')}»",
                "«Покрытие: API ↔ SRS»", "selfcheck")
    if tr.get("business_registry_section"):
        rep.add("i", "Реестр ID матрицы", f"ждёт раздел «{tr['business_registry_section']}»",
                "один раздел «Реестр ID» для всех слоёв; у мигрированных комплектов brd/ нет, "
                "раздел бизнес-слоя появляется при деривации BRD", "шаблоны матрицы; Д-27 п. 3")

    # 9. путь → навык
    their_map: Dict[str, set] = {}
    for s in their.get("skills_by_path", []) or []:
        their_map.setdefault(s.get("path"), set()).add(s.get("skill"))
    mism = 0
    for s in built["skills_by_path"]:
        p, sk = s["path"], s["skill"]
        if p in their_map and sk not in their_map[p] and sk != "api-asyncapi":
            mism += 1
            rep.add("≠", f"Путь → навык `{p}`",
                    ", ".join(sorted(str(x) for x in their_map[p])), sk,
                    "passport_sync TYPE_TO_SKILL (имена навыков — платформы)")
    if their_map and not mism:
        rep.add("=", "Путь → навык", "пути типов совпадают", "—", "TYPE_TO_SKILL")

    # 10. коды внешних АС
    if contracts is not None:
        ours_as = set(as_codes(contracts))
        theirs_as = {str(s).lower() for s in (their.get("ids", {}) or {}).get("segments", [])}
        theirs_as -= set(_CONTOURS + _SEGMENTS_FIXED)
        if ours_as and ours_as != theirs_as:
            rep.add("≠", "Коды внешних АС", ", ".join(sorted(theirs_as)),
                    ", ".join(sorted(ours_as)) + " (папки корня docs-external-contracts)",
                    "репозиторий docs-external-contracts")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description="Паспорт раскладки ЭКО: сборка yaml из канона "
                                             "и сторож расхождений паспорта платформы")
    ap.add_argument("--canon", type=Path, default=None, help="корень клона канона")
    ap.add_argument("--contracts", type=Path, default=None,
                    help="клон docs-external-contracts (коды АС)")
    ap.add_argument("--build", type=Path, default=None, help="собрать yaml в этот файл")
    ap.add_argument("--check", type=Path, default=None,
                    help="каталог паспорта платформы (docs-kit-layout.md/.yaml)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    canon = a.canon
    if canon is None:
        cand = _HERE.parent.parent  # _meta/tools → корень канона
        if (cand / "_meta/templates/docs-readme.md").is_file():
            canon = cand
    if canon is None or not (canon / "_meta/templates/docs-readme.md").is_file():
        print("✗ не найден канон: укажите --canon <корень клона docs-o2new>")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.build is not None:
        a.build.parent.mkdir(parents=True, exist_ok=True)
        a.build.write_text(dump_layout(build_layout(canon, a.contracts)),
                           encoding="utf-8", newline="\n")
        print(f"✓ собрано: {a.build}")
    if a.check is not None:
        rep = check_passport(canon, a.check, a.contracts)
        for ln in rep.render():
            print(ln)
        if a.json:
            print(json.dumps(rep.as_dicts(), ensure_ascii=False, indent=1))
        return 1 if rep.diffs else 0
    if a.build is None:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
