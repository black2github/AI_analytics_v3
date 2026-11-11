# app/scripts/CI/kitcheck/checks/source_profile.py
# Слой: миграция
"""Проверки selfcheck: source_profile — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import re
try:
    from kitcheck import fs as _fs
    from kitcheck.md import table_cells
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import table_cells  # type: ignore
from ._common import (  # noqa: F401
    _KNOWN_TYPES, domain_context, in_outside_eco_part, passport_slugs)


# зона части: «вне Экосистемы <слаг>» — часть сервиса вне контура Экосистемы в штатном
# каталоге docs/srs/<слаг>/ (решение владельца канона 2026-11-08); строка без слага —
# переходная форма (⚠, каталог части не задан)
_ZONE_RE = re.compile(
    r"^(?:(подсервис|core)\s+([\w-]+)|общая часть|вне Экосистемы(?:\s+([\w-]+))?.*)$",
    re.I)


# домен: «сервис <service-id>» и необязательная зона части через запятую
# («сервис registration, подсервис idn»; «сервис shared, общая часть»)
_SERVICE_ZONE_RE = re.compile(r"^сервис\s+([\w-]+)\s*(?:,\s*(.+))?$", re.I)


# комплект репозитория: «комплект <путь>» — корень второго комплекта от корня исходного
# репозитория, прямые косые (сервис нескольких команд ведётся доменным репозиторием с комплектом
# на команду; команда держит свой комплект такого сервиса вторым корнем рядом с docs/). Страница
# под строкой принадлежит этому комплекту; не попавшая ни под одну строку «комплект …» — основному
# (docs/). Необязательная зона части через запятую — как у формы «сервис <id>».
_KIT_ZONE_RE = re.compile(r"^комплект\s+`?([^\s,`]+)`?\s*(?:,\s*(.+))?$", re.I)


def _profile_rows(profile: Path) -> Optional[List[Tuple[str, str]]]:
    """Строки таблицы «Разметка подсервисов» профиля источников: [(матчер, зона)] как в файле;
    None — файла или таблицы нет. Единственный разбор таблицы: зоны частей
    (_load_subservice_map) и объявленные комплекты (kit_rows) — представления этих строк."""
    try:
        text = _fs.read_text(profile, encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"^#+\s*Разметка подсервисов.*$", text, re.M)
    if not m:
        return None
    rows: List[Tuple[str, str]] = []
    for ln in text[m.end():].splitlines():
        s = ln.strip()
        if s.startswith("#"):
            break
        if not s.startswith("|"):
            continue
        cells = table_cells(s)
        if len(cells) < 2 or cells[0].lower() in ("матчер (тег или ветвь)",
                                                  "матчер"):
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        rows.append((cells[0], cells[1]))
    return rows


def _zone_row(matcher: str, zone_text: str):
    """Строка зоны части (матчер, слаг|None, вид, сервис|None); None — форма зоны не распознана."""
    service = None
    sm = _SERVICE_ZONE_RE.match(zone_text)
    if sm:
        service = sm.group(1)
        zone_text = sm.group(2) or ""
        if not zone_text:
            return (matcher, None, "service", service)
    zm = _ZONE_RE.match(zone_text)
    if not zm:
        return None
    zone = zone_text.lower()
    slug = zm.group(2) or zm.group(3)
    kind = ("slug" if zm.group(1) else
            "common" if zone.startswith("общая") else "external")
    return (matcher, slug, kind, service)


def _kit_row(matcher: str, zone_text: str):
    """(матчер, путь комплекта, строка зоны части|None) для строки «комплект <путь>[, <зона>]»;
    None — не строка комплекта. Путь — относительный, без «.»/«..»; зона через запятую — только
    зона части (как у формы «сервис <id>»), иначе строка не распознана целиком."""
    km = _KIT_ZONE_RE.match(zone_text.strip())
    if not km:
        return None
    path = km.group(1).replace("\\", "/").strip("/")
    if not path or ":" in path or any(p in ("", ".", "..") for p in path.split("/")):
        return None
    zone = None
    if km.group(2):
        zone = _zone_row(matcher, km.group(2).strip())
        if zone is None or zone[2] == "service" or zone[3] is not None:
            return None
    return (matcher, path, zone)


def _load_subservice_map(profile: Path):
    """[(матчер, слаг|None, зона)]; None — таблицы/файла нет. Строка «комплект …» зону части не
    задаёт (принадлежность комплекту — отдельное измерение, kit_rows); её зона через запятую —
    обычная строка зоны с тем же матчером."""
    raw = _profile_rows(profile)
    if raw is None:
        return None
    rows = []
    for matcher, zone_text in raw:
        kr = _kit_row(matcher, zone_text)
        row = kr[2] if kr is not None else _zone_row(matcher, zone_text)
        if row is not None:
            rows.append(row)
    return rows or None


def kit_rows(profile: Path) -> List[Tuple[str, str]]:
    """Строки «комплект <путь>» профиля по порядку таблицы: [(матчер, путь комплекта)]."""
    out: List[Tuple[str, str]] = []
    for matcher, zone_text in _profile_rows(profile) or []:
        kr = _kit_row(matcher, zone_text)
        if kr is not None:
            out.append((kr[0], kr[1]))
    return out


def declared_kits(profile: Path) -> List[str]:
    """Объявленные корни комплектов (пути от корня репозитория) без повторов, по порядку."""
    out: List[str] = []
    for _m, path in kit_rows(profile):
        if path not in out:
            out.append(path)
    return out


def row_matches(matcher: str, title: str, branch: str, pid: Optional[str]) -> bool:
    """Страница под строкой разметки. Матчер из одних цифр — page_id: ровно эта страница, без
    потомков; иначе — тег-префикс титула или имя верхней ветви выгрузки, как прежде."""
    if matcher.isdigit():
        return pid == matcher
    return title.startswith(matcher) or matcher.strip("[]") == branch or matcher == branch


def kit_of_page(krows: List[Tuple[str, str]], title: str, branch: str,
                pid: Optional[str]) -> Optional[str]:
    """Комплект страницы: путь первой подошедшей строки «комплект …»; None — основной комплект.
    Порядок строк зон частей на комплект не влияет: у комплекта и зоны части свои строки,
    в каждом измерении выигрывает первая подошедшая строка своего вида."""
    return next((path for matcher, path in krows
                 if row_matches(matcher, title, branch, pid)), None)


@_fs.memoize()
def kit_of_root(docs: Path) -> Optional[Tuple[Path, str]]:
    """(корень исходного репозитория, путь комплекта), если каталог комплекта объявлен строкой
    «комплект <путь>» в профиле источников (README.md) одного из предков, — до четырёх уровней
    вверх; иначе None (основной комплект или репозиторий без объявления)."""
    d = Path(docs).resolve()
    for root in list(d.parents)[:4]:
        rel = d.relative_to(root).as_posix()
        if rel in declared_kits(root / "README.md"):
            return root, rel
    return None


def _page_head(src_file: Path, sources: Path) -> Tuple[Optional[str], str, str]:
    """(page_id, титул, верхняя ветвь) файла выгрузки — по шапке первых 2000 знаков."""
    head = _fs.read_text(src_file, encoding="utf-8", errors="replace")[:2000]
    pid_m = re.search(r"^confluence_page_id:\s*['\"]?(\d+)", head, re.M)
    title_m = re.search(r"^title:\s*(.+)$", head, re.M)
    title = title_m.group(1).strip().strip("'\"") if title_m else ""
    try:
        branch = src_file.relative_to(sources).parts[0]
    except ValueError:
        branch = ""
    return (pid_m.group(1) if pid_m else None), title, branch


def _stand_root(sources: Path) -> Path:
    """Корень стенда/репозитория источника по каталогу выгрузки.

    Две топологии: пилотный стенд ``<root>/confluence`` и репозиторий
    источника линии 2.x ``<src>/sources/confluence`` (track-manual,
    гид «Файлы репозитория»). Прежний признак «родитель выгрузки» на
    второй топологии давал ``<src>/sources``: гейт требовал журнал
    ``sources/sandbox/journal.txt``, искал профиль в ``sources/README.md``
    и молча пропускал сверку среза канона — первый исполнитель v2.x
    (PRE-01, 2026-09-11) создал ``sources/sandbox/`` по подсказке
    прибора, координатор велел удалить, круг замкнулся (FB-03; класс
    тот же, что FB-01 — прибор молчаливо предполагает топологию пилота).
    Признак: родитель ``sources`` без собственного ``.git`` — контейнер
    выгрузок, корень выше на уровень; иначе — родитель (пилот, тесты).
    """
    s = sources.resolve()
    parent = s.parent
    if parent.name == "sources" and not (parent / ".git").exists():
        return parent.parent
    return parent


def _profile_path(sources: Path) -> Tuple[Path, Path]:
    """(корень, профиль источников): ``<root>/README.md``; фолбэк —
    README внутри выгрузки (корень = выгрузка), прежнее поведение."""
    root = _stand_root(sources)
    profile = root / "README.md"
    if not profile.is_file():
        profile = sources / "README.md"
        root = sources
    return root, profile


def check_subservice_mapping(docs: Path, sources: Path,
                             card_files: Dict[str, Path], kit: Optional[str] = None):
    """(отчёт, ok). card_files: page_id -> карточка docs. Зона источника
    определяется по титулу/ветви его файла выгрузки; путь карточки
    обязан начинаться srs/<слаг>/ (подсервис/core и вне Экосистемы <слаг>) или не иметь
    слага (общая часть); зона «вне Экосистемы» без слага путь не задаёт (⚠).
    kit — комплект прогона (путь строки «комплект …»; None — основной): страницы другого
    комплекта здесь не судятся — их ловит check_kit_mapping."""
    _, profile = _profile_path(sources)
    smap = _load_subservice_map(profile)
    if not smap:
        # без таблицы разметки сторож молчит; паспорт границы части в комплекте без строки
        # профиля — ⚠ (признак части взят по паспорту)
        return outside_eco_lines(docs, [], passport_slugs(docs)), True
    krows = kit_rows(profile)
    report: List[str] = []
    ok = True
    slugs = {row[1] for row in smap if row[2] in ("slug", "external") and row[1]}
    dom = domain_context(docs)
    my_service = docs.resolve().name if dom is not None else None
    for src_file in sorted(sources.rglob("*.md")):
        if src_file.name.lower() == "index.md":
            continue
        pid, title, branch = _page_head(src_file, sources)
        if pid is None or pid not in card_files:
            continue
        if krows and kit_of_page(krows, title, branch, pid) != (kit or None):
            continue            # страница другого комплекта — сторож «страница → свой комплект»
        zone = next(((row[1], row[2], row[3]) for row in smap
                     if row_matches(row[0], title, branch, pid)), None)
        if zone is None:
            continue
        slug, kind, service = zone
        card = card_files[pid]
        rel = card.relative_to(docs).as_posix()
        if service is not None and my_service is not None \
                and service != my_service:
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                f"в сервис «{service}», карточка лежит в комплекте "
                f"«{my_service}» (домен: страница → свой сервис)")
            continue
        if kind == "service":
            continue            # только сервис, зоны части не заданы
        parts = rel.split("/")
        seg = (parts[1] if len(parts) > 2 and parts[0] == "srs"
               and parts[1] not in _KNOWN_TYPES else None)
        if kind == "external" and not slug:
            continue            # зона без слага: каталог части не задан (⚠ строкой ниже)
        if kind == "external" and seg != slug:
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                f"«вне Экосистемы {slug}», ожидался путь srs/{slug}/… "
                f"(фактический сегмент: {seg or 'нет — корень srs'})")
        elif kind == "slug" and seg != slug:
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                f"в подсервис «{slug}», ожидался путь srs/{slug}/… "
                f"(фактический сегмент: {seg or 'нет — корень srs'})")
        elif kind == "common" and seg is not None:
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                f"«общая часть», карточка лежит в подсервисе «{seg}»")
        elif seg is not None and seg not in slugs:
            ok = False
            report.append(
                f"✗ разметка: {rel} — сегмент «{seg}» отсутствует в "
                "таблице разметки профиля (самодеятельный подкаталог)")
    if not report:
        report.append("разметка подсервисов: соответствие "
                      "«источник → путь» выдержано ✓")
    report.extend(outside_eco_lines(docs, smap, passport_slugs(docs)))
    return report, ok


def _kit_label(kit: Optional[str]) -> str:
    return f"{kit}/" if kit else "основной docs/"


def check_kit_mapping(docs: Path, sources: Path, card_files: Dict[str, Path],
                      kit: Optional[str] = None) -> Tuple[List[str], bool]:
    """Сторож «страница → свой комплект» (по образцу «страница → свой сервис»): карточка,
    главный источник которой (page_id шапки — первый в confluence_page_ids) размечен строкой
    «комплект …» в комплект X, лежит в комплекте прогона Y — ✗ с обоими путями. Работает в обе
    стороны: kit — комплект прогона (None — основной). Доп. источники карточки не судятся:
    карточка вызова основного комплекта вправе назвать страницу метода другого комплекта.
    Строка с матчером page_id, которого в выгрузке нет, — ⚠ (строка ничего не размечает).
    Без строк «комплект …» в профиле — пусто."""
    _, profile = _profile_path(sources)
    krows = kit_rows(profile)
    if not krows:
        return [], True
    here = kit or None
    report: List[str] = []
    ok = True
    seen: set = set()
    for src_file in sorted(sources.rglob("*.md")):
        if src_file.name.lower() == "index.md":
            continue
        pid, title, branch = _page_head(src_file, sources)
        if pid is None or pid in seen:
            continue            # повтор page_id (архив raw/ под --sources) — судится раз
        seen.add(pid)
        if pid not in card_files:
            continue
        there = kit_of_page(krows, title, branch, pid)
        if there == here:
            continue
        ok = False
        rel = card_files[pid].relative_to(docs).as_posix()
        report.append(
            f"✗ разметка комплекта: {_kit_label(here)}{rel} — источник «{title[:50]}» размечен "
            f"в комплект {_kit_label(there)}, карточка лежит в комплекте {_kit_label(here)} "
            "(профиль источников: страница → свой комплект; карточку перенести в свой комплект)")
    for matcher, path in krows:
        if matcher.isdigit() and matcher not in seen:
            report.append(f"⚠ разметка комплекта: строка «комплект {path}» с матчером page_id "
                          f"{matcher} — страницы в выгрузке нет, строка ничего не размечает")
    if ok:
        report.insert(0, f"разметка комплектов: соответствие «источник → комплект» выдержано ✓ "
                         f"(прогон: {_kit_label(here)}; объявлено комплектов: "
                         f"{len(declared_kits(profile))})")
    return report, ok


def outside_eco_slugs(sources: Optional[Path]) -> frozenset:
    """Слаги частей вне контура Экосистемы по профилю источников — строки `вне Экосистемы
    <слаг>` таблицы «Разметка подсервисов» (решение владельца канона 2026-11-08). Путь каталога
    признака не несёт. Нет выгрузки, профиля или таблицы — пусто. Второй источник признака —
    паспорт границы в комплекте (passport_slugs); карта частей — объединение."""
    if sources is None:
        return frozenset()
    smap = _load_subservice_map(_profile_path(sources)[1]) or []
    return frozenset(row[1] for row in smap if row[2] == "external" and row[1])


def outside_eco_lines(docs: Path, smap, passports: frozenset = frozenset()) -> List[str]:
    """Строки о частях вне контура Экосистемы по разметке и паспортам: ⚠ на зону без слага
    (переходный период — каталог части не задан), i по каждой части (карточек, паспорт границы
    BND), ⚠ без паспорта границы boundary-passport.md, ⚠ паспорт без строки разметки профиля
    (passports — passport_slugs комплекта). Только ⚠ и i, вердикт не меняют."""
    out: List[str] = []
    bare = [row[0] for row in smap if row[2] == "external" and not row[1]]
    for matcher in bare:
        out.append(f"⚠ разметка: зона «вне Экосистемы» без слага каталога части (матчер "
                   f"{matcher}) — часть вне контура Экосистемы описывается в docs/srs/<слаг>/, "
                   "строка разметки — «вне Экосистемы <слаг>»; до правки строки путь её "
                   "карточек не сверяется")
    seen = set()
    for row in smap:
        slug = row[1]
        if row[2] != "external" or not slug or slug in seen:
            continue
        seen.add(slug)
        part = docs / "srs" / slug
        n = sum(1 for _ in part.rglob("*.md")) if part.is_dir() else 0
        has_passport = (part / "boundary-passport.md").is_file()
        out.append(f"i часть вне Экосистемы {slug}: карточек {n}, паспорт BND "
                   + ("есть" if has_passport else "нет"))
        if not has_passport:
            out.append(f"⚠ у части вне Экосистемы нет boundary-passport.md: srs/{slug}/ — "
                       "паспорт границы обязателен (шаблон module-passport.md)")
    for slug in sorted(set(passports) - seen):
        part = docs / "srs" / slug
        n = sum(1 for _ in part.rglob("*.md")) if part.is_dir() else 0
        out.append(f"i часть вне Экосистемы {slug}: карточек {n}, паспорт BND есть")
        out.append(f"⚠ паспорт границы srs/{slug}/boundary-passport.md без строки разметки "
                   f"«вне Экосистемы {slug}» в профиле источников — признак части взят по "
                   "паспорту; строку разметки добавить (шаблон sources-readme.md)")
    return out


_CANON_CUT_RE = re.compile(r"срез\s+канона\D{0,40}?([0-9a-f]{7,40})",
                           re.I)


def check_canon_cut(sources: Path,
                    head: Optional[str]) -> Tuple[List[str], bool]:
    """Сверка строки «срез канона: <hash>» профиля с фактическим HEAD."""
    _, profile = _profile_path(sources)
    try:
        text = _fs.read_text(profile, encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    m = _CANON_CUT_RE.search(text)
    if not m:
        # волна 9 ОНБ-В (ЗК-14): молчание при отсутствии строки скрывало, что
        # срез канона в комплекте не записан нигде; профиля нет вовсе — молчание
        # (его отсутствие ловит другой сторож)
        return ["⚠ в профиле источников нет строки «Срез канона» — свежесть канона не "
                "проверяется; добавить строкой по шаблону sources-readme или "
                "`accept_canon.py --profile`"], True
    want = m.group(1).lower()
    if head is None:
        return [f"⚠ срез канона: профиль требует {want}, но фактический "
                "HEAD канона не определён (dev-копия selfcheck вне "
                "канона или git недоступен) — сверка не выполнена"], True
    have = head.lower()
    if have.startswith(want) or want.startswith(have):
        return [f"✓ срез канона: профиль {want} = HEAD канона {have}"], True
    return [f"✗ срез канона: профиль требует {want}, фактический HEAD "
            f"канона {have} — обновите клон канона либо строку «срез "
            "канона» профиля (решение владельца)"], False


_SCRIPT_EXT = {".py", ".ps1", ".psm1", ".sh", ".bat", ".cmd", ".js"}


_RETRY_RE = re.compile(r"-retry-(\d+)", re.I)


def check_protocol_discipline(sources: Path) -> Tuple[List[str], bool]:
    """✗ на следы нарушений протокола: посторонние скрипты в src-репо
    (§3) и отчёты попыток сверх лимита двух (§6)."""
    root, profile = _profile_path(sources)
    try:
        ptext = _fs.read_text(profile, encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    if not _CANON_CUT_RE.search(ptext):
        return [], True
    report: List[str] = []
    ok = True
    # §5: нормализация только на КОПИЯХ в sandbox/normalized —
    # sidecar рядом с источниками = нормализатор гоняли по выгрузке
    # (STS-01 2026-08-31: два *.tables.md легли в confluence/,
    # копий в sandbox не было вовсе)
    stray = sorted(sources.rglob("*.tables.md"))
    if stray:
        ok = False
        for s in stray[:5]:
            report.append(
                f"✗ протокол §5: sidecar в выгрузке — {s.relative_to(root)}"
                " (нормализация только на копиях в sandbox/normalized; "
                "файл удалить, прогон нормализатора повторить по копии)")
    try:
        src_rel = sources.resolve().relative_to(root.resolve()).parts[0]
    except ValueError:
        src_rel = None
    scripts = []
    for p in root.rglob("*"):
        if p.suffix.lower() not in _SCRIPT_EXT:
            continue
        parts = p.relative_to(root).parts
        if ".git" in parts or (src_rel and parts[0] == src_rel):
            continue
        scripts.append(p.relative_to(root))
    for s in scripts[:6]:
        ok = False
        report.append(f"✗ протокол §3: посторонний скрипт в src-репо — "
                      f"{s} (файлы комплекта правятся пофайлово; "
                      "скрипты исполнителю запрещены, разрешены только "
                      "канонические инструменты)")
    if len(scripts) > 6:
        report.append(f"   … и ещё {len(scripts) - 6} скриптов")
    sandbox = root / "sandbox"
    if sandbox.is_dir():
        # retry-N в имени — номер повторного ПРОГОНА захода; лимит §6
        # считается по каждому ✗ отдельно (параллельные ✗ легально
        # дают retry-3 при ≤2 попыток на каждый — кейс z01 ISS-03).
        # 3–4 прогона — ⚠ приёмке проверить по-✗ квалификацию в сдаче;
        # 5+ — ✗ (столько параллельных ✗ в одном заходе не живёт).
        for f in sorted(sandbox.iterdir()):
            m = _RETRY_RE.search(f.name)
            if not m:
                continue
            n = int(m.group(1))
            if n >= 5:
                ok = False
                report.append(f"✗ протокол §6: отчёт {f.name} — "
                              "пятый повторный прогон; лимит попыток "
                              "заведомо исчерпан, требуется исход "
                              "«СТОП по лимиту» и решение человека")
            elif n >= 3:
                report.append(f"⚠ протокол §6: отчёт {f.name} — "
                              "третий+ повторный прогон; приёмке "
                              "проверить по-✗ квалификацию попыток в "
                              "сдаче (легально при параллельных ✗ с "
                              "≤2 попыток на каждый)")
    return report, ok


_PLAN_LINE_RE = re.compile(r"план\s+миграции\D{0,40}?`?([\w.\- ]+\.md)`?",
                           re.I)


_STAGE_ROW_RE = re.compile(r"^\|\s*`([A-ZА-Я]{2,4}-\d{2})`\s*\|", re.M)


def check_stage_prompts(sources: Path) -> Tuple[List[str], bool]:
    """⚠-строки о этапах плана без файла промпта; ok всегда True."""
    root, profile = _profile_path(sources)
    try:
        ptext = _fs.read_text(profile, encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    m = _PLAN_LINE_RE.search(ptext)
    if not m:
        return [], True
    plan = root / m.group(1).strip()
    if not plan.is_file():
        return [f"⚠ промпты этапов: план «{m.group(1).strip()}» из "
                "профиля не найден — сверка пакета не выполнена"], True
    stages = set(_STAGE_ROW_RE.findall(
        _fs.read_text(plan, encoding="utf-8", errors="replace")))
    if not stages:
        return ["⚠ промпты этапов: в плане не распознаны коды этапов "
                "(таблица с `КОД-NN` первой ячейкой) — сверка пакета "
                "не выполнена"], True
    pdir = root / "prompts"
    have = ({f.stem for f in pdir.glob("*.md")} if pdir.is_dir()
            else set())
    sandbox = root / "sandbox"
    done = {s for s in stages
            if sandbox.is_dir() and any(sandbox.glob(f"selfcheck-{s}*"))}
    missing = sorted(stages - have - done)
    orphans = sorted(have - stages)
    lines: List[str] = []
    if missing:
        lines.append(f"⚠ промпты этапов: без файла prompts/<ЭТАП>.md — "
                     f"{len(missing)} из {len(stages)} этапов плана: "
                     + ", ".join(missing[:12])
                     + (" …" if len(missing) > 12 else ""))
    else:
        lines.append(f"✓ промпты этапов: файлы либо выполненные отчёты "
                     f"есть для всех {len(stages)} этапов плана")
    for s in orphans[:6]:
        lines.append(f"i промпт prompts/{s}.md не соответствует ни "
                     "одному коду этапа плана")
    return lines, True
