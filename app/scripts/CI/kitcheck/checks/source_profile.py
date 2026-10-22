# app/scripts/CI/kitcheck/checks/source_profile.py
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
    _KNOWN_TYPES, domain_context)


_ZONE_RE = re.compile(
    r"^(?:(подсервис|core)\s+([\w-]+)|общая часть|вне Экосистемы.*)$",
    re.I)


# домен: «сервис <service-id>» и необязательная зона части через запятую
# («сервис registration, подсервис idn»; «сервис shared, общая часть»)
_SERVICE_ZONE_RE = re.compile(r"^сервис\s+([\w-]+)\s*(?:,\s*(.+))?$", re.I)


def _load_subservice_map(profile: Path):
    """[(матчер, слаг|None, зона)]; None — таблицы/файла нет."""
    try:
        text = _fs.read_text(profile, encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"^#+\s*Разметка подсервисов.*$", text, re.M)
    if not m:
        return None
    rows = []
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
        service = None
        zone_text = cells[1]
        sm = _SERVICE_ZONE_RE.match(zone_text)
        if sm:
            service = sm.group(1)
            zone_text = sm.group(2) or ""
            if not zone_text:
                rows.append((cells[0], None, "service", service))
                continue
        zm = _ZONE_RE.match(zone_text)
        if not zm:
            continue
        zone = zone_text.lower()
        slug = zm.group(2)
        kind = ("slug" if zm.group(1) else
                "common" if zone.startswith("общая") else "external")
        rows.append((cells[0], slug, kind, service))
    return rows or None


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
                             card_files: Dict[str, Path]):
    """(отчёт, ok). card_files: page_id -> карточка docs. Зона источника
    определяется по титулу/ветви его файла выгрузки; путь карточки
    обязан начинаться srs/<слаг>/ (подсервис/core), не иметь слага
    (общая часть) или карточки не должно быть вовсе (вне Экосистемы)."""
    _, profile = _profile_path(sources)
    smap = _load_subservice_map(profile)
    if not smap:
        return [], True
    report: List[str] = []
    ok = True
    slugs = {row[1] for row in smap if row[2] == "slug"}
    dom = domain_context(docs)
    my_service = docs.resolve().name if dom is not None else None
    for src_file in sorted(sources.rglob("*.md")):
        if src_file.name.lower() == "index.md":
            continue
        head = _fs.read_text(src_file, encoding="utf-8",
                                  errors="replace")[:2000]
        pid_m = re.search(r"^confluence_page_id:\s*['\"]?(\d+)",
                          head, re.M)
        if not pid_m or pid_m.group(1) not in card_files:
            continue
        title_m = re.search(r"^title:\s*(.+)$", head, re.M)
        title = title_m.group(1).strip().strip("'\"") if title_m else ""
        try:
            branch = src_file.relative_to(sources).parts[0]
        except ValueError:
            branch = ""
        zone = next(((row[1], row[2], row[3]) for row in smap
                     if title.startswith(row[0])
                     or row[0].strip("[]") == branch
                     or row[0] == branch), None)
        if zone is None:
            continue
        slug, kind, service = zone
        card = card_files[pid_m.group(1)]
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
        # мини-комплект зоны «вне Экосистемы» живёт в docs/modules/<имя>/ (Д-49 п. 4)
        in_zone = rel.startswith("modules/")
        if kind == "external":
            if in_zone:
                continue
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                "«вне Экосистемы», карточке комплекта не место — дом "
                "мини-комплект docs/modules/<имя>/ (conventions §3.1)")
        elif in_zone:
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» не размечен "
                "«вне Экосистемы», а файл лежит в мини-комплекте зоны "
                "docs/modules/ — зона только для страниц вне Экосистемы")
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
    return report, ok


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
