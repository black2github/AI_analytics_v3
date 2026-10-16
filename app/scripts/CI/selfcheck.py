# app/scripts/CI/selfcheck.py
#
# Единый диспетчер механических гейтов самопроверки (срез 1: сверка
# карточек комплекта с источниками). Знание «что проверять» живёт
# здесь, а не в промпте и не у оператора: диспетчер сам находит
# карточки в docs/, сам сопоставляет каждой страницу-источник по
# confluence_page_id (frontmatter выгрузки) и прогоняет связку
# проверок нормализатора (normalize_tables.run_check — единая точка
# монтажа; двойного монтажа проверок нет).
#
# Правила устойчивости (решения 2026-08-16):
#   1) краш проверки одной карточки = брак ЭТОЙ карточки, прогон
#      продолжается (трейсбек одной строкой в отчёт);
#   2) молчаливых пропусков нет: КАЖДЫЙ md-файл комплекта попадает
#      ровно в одну категорию отчёта (✓ / ✗ / ⚠ с причиной), итог со
#      счётчиками; reverse-карточка (page_ids есть) без найденного
#      источника — брак, а не пропуск;
#   3) новой логики сверки здесь НЕТ — только обход, мэппинг, вызовы.
# Read-only: пишет только отчёт в stdout; код 2 при любом браке.
#
# Межтиповые страницы: карточки с одним главным page_id проверяются
# ОДНИМ вызовом (объединение значений; основная — первая по сортировке
# пути), внутренние сторожа прочих карточек группы — отдельными
# вызовами без источника. Дополнительные page_ids карточки (дочерние
# страницы) в срезе 1 не сверяются — честная пометка в отчёте.

import argparse
from dataclasses import dataclass
import json
import re
import subprocess
import sys
from urllib.parse import unquote
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import link_debts as ld  # noqa: E402
import normalize_tables as nt  # noqa: E402
import source_coverage as sc  # noqa: E402
try:
    from kitcheck import fs as _fs  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck import fs as _fs  # type: ignore  # noqa: E402
try:
    from kitcheck.md import (  # noqa: E402,F401 — примитивы markdown (этап 1б); имена
        _MD_LINK_RE, _PID_RE, _anchors_of, _kit_md,  # сохраняются в selfcheck для
        gitlab_slug, in_dot_dir, is_task_file,  # утилит и тестов, которые зовут их
        page_ids, read_frontmatter, table_cells, is_fence, FENCE_BOTH,  # как selfcheck.*
        FENCE_BACKTICK)
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.md import (  # type: ignore  # noqa: E402,F401
        _MD_LINK_RE, _PID_RE, _anchors_of, _kit_md,
        gitlab_slug, in_dot_dir, is_task_file,
        page_ids, read_frontmatter, table_cells, is_fence, FENCE_BOTH,
        FENCE_BACKTICK)
try:
    from kitcheck.core import Check, run_checks  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.core import Check, run_checks  # type: ignore  # noqa: E402

# служебные реестры комплекта — сверке нормализатора не подлежат
# (их сторожа — link_debts, срез 2)
_SERVICE_FILES = {"traceability-matrix.md", "open-questions.md"}


def index_sources(root: Path):
    """page_id -> файл выгрузки; дубли — списком (используется первый
    по сортировке, в отчёт — предупреждение)."""
    idx: Dict[str, Path] = {}
    dups: Dict[str, List[Path]] = {}
    for p in sorted(root.rglob("*.md")):
        # FB-21 КК (2026-10-14): --sources на родительский каталог
        # индексировал и sources/raw/ (нетронутый архив выгрузки) —
        # 615 дублей page_id; архив — не область сверки
        if "raw" in p.relative_to(root).parts[:-1]:
            continue
        fm = read_frontmatter(p) or {}
        ids = _PID_RE.findall(fm.get("confluence_page_id", ""))
        if not ids:
            continue
        pid = ids[0]
        if pid in idx:
            dups.setdefault(pid, [idx[pid]]).append(p)
        else:
            idx[pid] = p
    return idx, dups


def _empty_source_note(src: Path) -> Tuple[Optional[str], bool]:
    """(пояснение, заморожена) — если тело страницы-источника пусто;
    иначе (None, False).

    Пустой источник (2026-10-05, миграция «Корпоративных карт»): страница
    с флагом заморозки `unapproved_jira` после reject-all несёт один
    frontmatter. Карточка, ссылающаяся на неё, получала ✓: сверять не с
    чем, все сторожа полноты проходят вхолостую. Шесть карточек лимитов
    так прошли гейт, а после перевыгрузки страниц в них не хватило 23
    значений таблицы и 6 фрагментов. Пустота определяется строго — в
    теле нет ни одного непробельного символа; страница с заголовком или
    одной строкой пустой не считается.

    Ужесточение (решение владельца 2026-10-05, FB-08 «Корпоративных
    карт»): страница с флагом заморозки — ✗, а не ⚠. Разбор показал, что
    карточки по замороженным страницам были собраны из архива raw по
    записанному в промпте решению акцептующего, и предупреждение их не
    остановило бы. Теперь принять архив источником можно только осознанно
    приняв БРАК. Пустая страница БЕЗ флага остаётся ⚠: причина
    неизвестна, решение человеческое."""
    try:
        text = _fs.read_text(src, encoding="utf-8", errors="replace")
    except OSError:
        return None, False
    body = text.lstrip("\ufeff")
    fm_text = ""
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) == 3:
            fm_text, body = parts[1], parts[2]
    if body.strip():
        return None, False
    m = re.search(r"^unapproved_jira:\s*(.+)$", fm_text, re.M)
    if m:
        task = m.group(1).strip().strip("'\"[]")
        return ("источник пуст: страница заморожена флагом unapproved_jira "
                f"({task}) — сверка с источником не выполнялась, перенос "
                "не подтверждён; по замороженной странице карточка не "
                "создаётся, содержимое из архива raw основанием не служит "
                "✗"), True
    return ("источник пуст: в теле страницы-источника нет текста — сверка "
            "с источником не выполнялась, перенос не подтверждён; "
            "открытый вопрос акцептующему"), False


def _safe(fn, *args) -> Tuple[List[str], bool]:
    """Изоляция краша (правило 1): исключение = брак проверяемой
    единицы, прогон продолжается."""
    try:
        return fn(*args)
    except Exception as e:
        return [f"КРАШ проверки: {e!r} — брак, прогон продолжен"], False


def _run(files: List[Path], src: Optional[Path],
         docs_root: Optional[Path] = None,
         soft_markers: bool = True,
         pardon_src: Optional[Path] = None,
         amnesty: Optional[List[Path]] = None) -> Tuple[List[str], bool]:
    return _safe(lambda: nt.run_check(files, src, docs_root=docs_root,
                                      soft_markers=soft_markers,
                                      pardon_source=pardon_src,
                                      amnesty_sources=amnesty))


# написание как в таблице шаблона nfr.md (без «ё»)
_NFR_TYPE_BY_CODE = {
    "prf": "Производительность",
    "avl": "Доступность",
    "rel": "Надежность",
    "sca": "Масштабируемость",
    "log": "Протоколирование",
    "sec": "Безопасность",
    "cmp": "Совместимость",
    "ins": "Удобство установки",
    "itg": "Целостность",
    "rsl": "Устойчивость",
    "prt": "Защита",
    "use": "Удобство использования",
    "eff": "Эффективность",
    "mod": "Возможность модификации",
    "tst": "Проверяемость и тестируемость",
    "mig": "Миграция",
    "mnt": "Требования к сопровождению",
    "mon": "Мониторинг",
}
_NFR_CODES = frozenset(_NFR_TYPE_BY_CODE)
_NFR_ROW_RE = re.compile(r"(?m)^\|\s*(nfr-([a-z]{3})-(\d{3}))\s*\|")
_NFR_INGRESS = frozenset({"reverse", "forward", "mixed"})


def _nfr_repo_root(docs: Path) -> Path:
    """output/<service>/docs → корень репозитория. Иначе родитель docs."""
    if (docs.name == "docs" and docs.parent.parent.name == "output"):
        return docs.parent.parent.parent
    return docs.parent


def check_nfr_catalog(docs: Path) -> Tuple[List[str], bool]:
    """Сторож output/<service>/nfr рядом с docs/.

    Каталога нет — молчит: утилита не знает, был ли вход. Значение nfr
    в _KNOWN_TYPES пути srs/<тип>/ не добавляется.
    """
    report: List[str] = []
    ok = True
    features = docs / "brd" / "features"
    if features.is_dir():
        for p in sorted(features.rglob("*.md")):
            try:
                text = _fs.read_text(p, encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"(?m)^## Нефункциональные требования\s*$", text):
                ok = False
                report.append(
                    f"✗ {p.relative_to(docs)}: раздел «Нефункциональные "
                    "требования» внутри фичи; страницы НФТ — в ../nfr/")
    nfr_dir = docs.parent / "nfr"
    if not nfr_dir.is_dir():
        return report, ok
    for d in sorted(p for p in nfr_dir.rglob("*") if p.is_dir()):
        ok = False
        report.append(
            f"✗ {d.relative_to(docs.parent)}: вложенный каталог в nfr/")
    seen_codes: Dict[str, Path] = {}
    page_rows: set = set()
    repo = _nfr_repo_root(docs)
    for p in sorted(nfr_dir.glob("*.md")):
        rel = p.relative_to(docs.parent)
        fm = read_frontmatter(p)
        if not fm:
            ok = False
            report.append(f"✗ {rel}: frontmatter не распознан")
            continue
        if fm.get("type", "").strip("'\"") != "nfr":
            ok = False
            report.append(f"✗ {rel}: ожидался type: nfr")
        if "status" in fm:
            ok = False
            report.append(f"✗ {rel}: поле status запрещено")
        if "nfr_profile" in fm:
            ok = False
            report.append(f"✗ {rel}: поле nfr_profile запрещено")
        if p.name == "README.md":
            if fm.get("id", "").strip("'\"") != "nfr":
                ok = False
                report.append(f"✗ {rel}: у реестра id: nfr")
            if "ingress" in fm or "nfr_type" in fm:
                ok = False
                report.append(
                    f"✗ {rel}: у реестра нет ingress и nfr_type")
            continue
        m = re.fullmatch(r"nfr-([a-z]{3})\.md", p.name)
        if not m or m.group(1) not in _NFR_CODES:
            ok = False
            report.append(
                f"✗ {rel}: имя файла не из каталога nfr-<код>.md")
            continue
        code = m.group(1)
        if code in seen_codes:
            ok = False
            report.append(f"✗ {rel}: вторая страница кода {code}")
        seen_codes[code] = p
        expected_id = f"nfr-{code}"
        page_id = fm.get("id", "").strip("'\"")
        if page_id != expected_id:
            ok = False
            report.append(f"✗ {rel}: id должен быть {expected_id}")
        expected_type = _NFR_TYPE_BY_CODE[code]
        nfr_type = fm.get("nfr_type", "").strip("'\"")
        if nfr_type != expected_type:
            ok = False
            report.append(
                f"✗ {rel}: nfr_type должен быть «{expected_type}»")
        ingress = fm.get("ingress", "").strip("'\"")
        if ingress not in _NFR_INGRESS:
            ok = False
            report.append(
                f"✗ {rel}: ingress обязателен: reverse, forward или mixed")
        has_conf = bool(fm.get("confluence_page_ids", "").strip())
        has_src = bool(fm.get("source_artifacts", "").strip())
        if ingress == "reverse" and (not has_conf or has_src):
            ok = False
            report.append(
                f"✗ {rel}: reverse требует confluence_page_ids "
                "и запрещает source_artifacts")
        if ingress == "forward" and (has_conf or has_src):
            ok = False
            report.append(
                f"✗ {rel}: forward запрещает confluence_page_ids "
                "и source_artifacts")
        if ingress == "mixed" and (not has_conf or has_src):
            ok = False
            report.append(
                f"✗ {rel}: mixed требует confluence_page_ids "
                "и запрещает source_artifacts")
        if has_src:
            # путь в кавычках не режется по пробелам (имя файла БТ)
            for a, b, c in re.findall(
                    r"'([^']*)'|\"([^\"]*)\"|(\S+)",
                    fm.get("source_artifacts", "")):
                tok = (a or b or c).strip().strip("'\"")
                if not tok or tok.startswith("<"):
                    continue
                path = Path(tok)
                resolved = path if path.is_absolute() else (repo / tok)
                if not resolved.is_file():
                    ok = False
                    report.append(
                        f"✗ {rel}: source_artifacts не файл: {tok}")
        try:
            text = _fs.read_text(p, encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        seen_rows = set()
        for token, row_code, _num in _NFR_ROW_RE.findall(text):
            if row_code != code:
                ok = False
                report.append(f"✗ {rel}: строка {token} не типа {code}")
            if token in seen_rows:
                ok = False
                report.append(f"✗ {rel}: повтор номера {token}")
            seen_rows.add(token)
        page_rows.update(seen_rows)
        body = text
        if body.startswith("---"):
            end = body.find("\n---", 3)
            if end != -1:
                body = body[end + 4:]
        if re.search(
                r"OQ-|TODO|sources/|pageId|confluence|_meta/|REJ-|nfr_profile"
                r"|\]\([^)]*srs/|^status:",
                body, re.M):
            ok = False
            report.append(
                f"✗ {rel}: запрещённые слова вне frontmatter")
    matrix = docs / "traceability-matrix.md"
    if seen_codes:
        if not matrix.is_file():
            ok = False
            report.append(
                "✗ traceability-matrix.md: нет матрицы при каталоге НФТ")
            brd_rows: set = set()
        else:
            mtext = _fs.read_text(matrix, encoding="utf-8", errors="replace")
            sec = re.search(
                r"^## BRD-6\.2\..*?(?=^## |\Z)", mtext, re.S | re.M)
            brd_rows = set(re.findall(
                r"\|\s*(nfr-[a-z]{3}-\d{3})\s*\|",
                sec.group(0) if sec else ""))
        for missing in sorted(page_rows - brd_rows):
            ok = False
            report.append(f"✗ BRD-6.2: нет строки {missing}")
        for extra in sorted(brd_rows - page_rows):
            ok = False
            report.append(f"✗ BRD-6.2: строка {extra} без страницы типа")
    if ok:
        report.append(f"✓ {nfr_dir.relative_to(docs.parent)}: каталог НФТ")
    return report, ok


def run(docs: Path, sources: Optional[Path],
        strict: bool = False,
        catalog: Optional[Path] = None) -> Tuple[List[str], bool]:
    """Прогон самопроверки комплекта: (строки отчёта, вердикт OK).

    Файлы комплекта и выгрузки читаются с диска один раз за прогон — через
    кэш `kitcheck.fs` (сессия на время прогона)."""
    with _fs.session():
        return _run_impl(docs, sources, strict, catalog)


def _run_impl(docs: Path, sources: Optional[Path],
              strict: bool = False,
              catalog: Optional[Path] = None) -> Tuple[List[str], bool]:
    # Два профиля (Р-8, 2026-08-22): командный (по умолчанию) — маркеры
    # сокращения предупреждением (3/3 ложняков на эталоне); полный
    # (--strict, прогоны держателей канона) — маркеры браком, как раньше.
    report: List[str] = []
    counts = {"✓": 0, "✗": 0, "⚠": 0}
    all_ok = True

    idx: Dict[str, Path] = {}
    if sources is not None:
        idx, dups = index_sources(sources)
        if any(d.is_dir() for d in sources.rglob("raw")):
            report.append("i выгрузка: каталоги raw/ (архив) при индексации "
                          "источников пропущены — область сверки sources/confluence")
        for pid, paths in sorted(dups.items()):
            report.append(f"i выгрузка: page_id {pid} у нескольких файлов "
                          f"({', '.join(p.name for p in paths[:3])}) — "
                          "используется первый по сортировке")

    # перепись файлов комплекта (правило 2: каждый — ровно одна категория)
    groups: Dict[str, List[Path]] = {}
    solo: List[Tuple[Path, str]] = []  # (файл, пометка)
    extra_pids: Dict[Path, int] = {}   # карточка -> число доп. page_ids
    extra_page_ids: Dict[Path, List[str]] = {}  # карточка -> доп. page_ids
    card_ids: Dict[Path, str] = {}     # карточка -> id из frontmatter
    card_titles: Dict[Path, Tuple[str, str, str]] = {}  # карточка -> (type, title, id)
    fm_schema_issues: List[Tuple[str, List[str], bool]] = []  # (файл, поля вне схемы, version)
    for p in sorted(docs.rglob("*.md")):
        rel = p.relative_to(docs)
        if in_dot_dir(p, docs):
            continue
        if is_task_file(p, docs):
            # строка-сигнал без счётчика: постановка — источник правок,
            # а не документ комплекта (молчаливых пропусков нет)
            report.append(f"i {rel}: постановка задачи (type: task) — "
                          "источник правок forward, вне сверки")
            continue
        if p.name in _SERVICE_FILES:
            # содержательно реестр сторожит link_debts (срез 2), но
            # структурную целостность таблиц проверяем и здесь: разрыв
            # матрицы жил с захода 4 незамеченным (К-16, 2026-08-17)
            rep, ok = _safe(nt.check_service_table_integrity, p)
            if p.name == "traceability-matrix.md":
                rd_rep, rd_ok = _safe(check_registry_duplicates, p)
                if not rd_ok:
                    all_ok = False
                    report.extend(rd_rep)
            if ok:
                counts["⚠"] += 1
                report.append(f"⚠ {rel}: служебный реестр — сторож среза 2 "
                              "(link_debts), сверке нормализатора не "
                              "подлежит")
            else:
                counts["✗"] += 1
                all_ok = False
                report.append(f"✗ {rel}: служебный реестр — таблицы битые")
                report.extend(f"   {ln}" for ln in rep)
            continue
        fm = read_frontmatter(p)
        if fm is None:
            counts["✗"] += 1
            all_ok = False
            report.append(f"✗ {rel}: frontmatter не распознан (блок не "
                          "закрыт или файл нечитаем) — брак")
            continue
        if not fm:
            counts["⚠"] += 1
            # Р-9 (2026-08-22): навигационные README освобождены от
            # требования frontmatter — в эталоне их 5, техдолг осознан
            # и будет закрыт по всем сервисам одной волной. Файл остаётся
            # в переписи (правило 2: молчаливых пропусков нет).
            if p.name.lower() == "readme.md":
                report.append(f"⚠ {rel}: навигационный README без "
                              "frontmatter — вне сверки (освобождён, Р-9)")
            else:
                report.append(f"⚠ {rel}: без frontmatter — вне сверки "
                              "(для документов комплекта frontmatter "
                              "обязателен)")
            continue
        bad_fields, has_version = frontmatter_schema_issues(fm)
        if bad_fields or has_version:
            fm_schema_issues.append((rel.as_posix() if hasattr(rel, "as_posix") else str(rel),
                                     bad_fields, has_version))
        if fm.get("id"):
            card_ids[p] = fm["id"]
            if fm.get("title") and fm.get("type"):
                card_titles[p] = (fm["type"], fm["title"], fm["id"])
        pids = page_ids(fm)
        pid_key_present = ("confluence_page_ids" in fm
                           or "confluence_page_id" in fm)
        if fm.get("__multiline-confluence_page_ids") \
                or fm.get("__multiline-confluence_page_id"):
            # строка-сигнал без счётчика: файл получит свой ✓/✗ ниже,
            # инвариант «один файл — одна отметка» не ломаем
            report.append(f"i {rel}: confluence_page_ids многострочным "
                          "YAML — шаблон предписывает inline-список; "
                          "сверка выполняется, формат привести")
        if not pids:
            if pid_key_present:
                # П-8 (COM-01 Корпкарт, 2026-08-27): ключ есть, а id не
                # распознаны — раньше карточка МОЛЧА становилась
                # «forward» и теряла всю сверку с источником (девять
                # карточек первой сдачи COM-01, фиктивная зелень)
                counts["✗"] += 1
                all_ok = False
                report.append(f"✗ {rel}: confluence_page_ids задан, но "
                              "id не распознаны — reverse-карточка "
                              "выпала бы из сверки с источником; формат "
                              "по шаблону: inline-список")
                continue
            solo.append((p, "без источника (page_ids нет — forward/реестр)"))
        elif sources is None:
            solo.append((p, f"источник page_id {pids[0]} не сверялся — "
                            "--sources не задан"))
        elif pids[0] not in idx:
            counts["✗"] += 1
            all_ok = False
            # ЗК-12 ОНБ-В: у карточек вызова первым ставили page_id страницы
            # владельца метода (вне выгрузки) — 9 постоянных ✗ обесценили гейт
            hint = (" (карточка вызова: первым — page_id страницы ЭТОГО сервиса, "
                    "где описан вызов; страница метода владельца — не источник, "
                    "её page_id — в open-questions/долге; шаблон contract-call.md)"
                    if "contract-call" in p.parts else "")
            report.append(f"✗ {rel}: источник page_id {pids[0]} НЕ НАЙДЕН "
                          "в выгрузке — reverse-карточка без сверки, брак" + hint)
        else:
            groups.setdefault(pids[0], []).append(p)
            extra_pids[p] = len(pids) - 1
            extra_page_ids[p] = list(pids[1:])
            if len(pids) > 1:
                report.append(f"i {rel}: доп. страницы-источники "
                              f"({len(pids) - 1}) механически не сверяются "
                              "(сверка — по главной, первой в списке)")

    def _warns(rep: List[str]) -> List[str]:
        # предупреждения видимы и при ✓ (софт-сигналы, не влияют на
        # вердикт: сторож привилегий Э-12 и будущие); итог сторожа
        # полноты ячеек виден и при ✓ — иначе приёмщику не отличить
        # «сторож прошёл» от «сторож не запускался» (ложная тревога
        # приёмки COM-01-fix, 2026-08-27)
        # префикс «[файл] » у строк неглавных карточек группы не должен
        # прятать их ⚠ при зелёной группе (находка 2026-08-31: сторож
        # entity сработал на 37 файлах, в отчёте были видны 7)
        # помилованный маркер (FB-09: «и т.д.» дословно из источника)
        # тоже виден при ✓ — иначе исчезновение ⚠ неотличимо от
        # «сторож не запускался»
        return [ln for ln in rep
                if re.match(r"^(?:\[[^\]]+\]\s+)?(?:предупреждение|"
                            r"полнота ячеек источника|маркер «)", ln)]

    for p, note in solo:
        rep, ok = _run([p], None, docs, soft_markers=not strict)
        mark = "✓" if ok else "✗"
        counts[mark] += 1
        all_ok = all_ok and ok
        if ok:
            report.append(f"✓ {p.relative_to(docs)}: {note}")
            report.extend(f"   {ln}" for ln in _warns(rep))
        else:
            # Формулировка причины ✗ (2026-08-22): пометка режима сверки
            # («без источника…») читалась причиной брака — брак всегда
            # у внутренних сторожей, их строки ниже.
            report.append(f"✗ {p.relative_to(docs)}: брак внутренних "
                          f"сторожей (причины ниже); {note}")
            report.extend(f"   {ln}" for ln in rep)

    for pid, files in sorted(groups.items()):
        src = idx[pid]
        # К-20 (2026-08-18): паразитирование на «доп. страницы не
        # сверяются» — если группу по ОДНОМУ главному page_id делят
        # README-реестр и карточки, у которых есть СВОИ доп. страницы,
        # то карточкам главной поставлено оглавление каталога: их
        # собственные страницы выпадают из сверки целиком (прогон
        # inkasso-run1: 12 карточек «сверялись» против оглавления МД —
        # фиктивная зелень). Главная страница карточки — та, чьим
        # переносом она является; оглавление — главная только у README.
        has_readme = any(f.name.lower() == "readme.md" for f in files)
        misordered = [f for f in files
                      if f.name.lower() != "readme.md"
                      and extra_pids.get(f, 0) > 0] if has_readme else []
        if misordered:
            all_ok = False
            for f in misordered:
                counts["✗"] += 1
                report.append(
                    f"✗ {f.relative_to(docs)}: главной указана "
                    f"страница-оглавление ({src.name}) — карточка не "
                    "сверяется со СВОЕЙ страницей; порядок "
                    "confluence_page_ids: главная страница карточки "
                    "ПЕРВОЙ, оглавление — главная только у README")
            files = [f for f in files if f not in misordered]
            if not files:
                continue
        # FB-19 КК: дословные абзацы дочерних страниц карточки — амнистия
        # длинных строк по всем её page_ids (файлы выгрузки доп. страниц)
        amnesty = [idx[x] for x in extra_page_ids.get(files[0], [])
                   if x in idx and idx[x] != src]
        rep, ok = _run(files, src, docs, soft_markers=not strict,
                       amnesty=amnesty or None)
        # макеты Figma группы (решение 2026-08-31, модель README/main):
        # ссылки макетов живут в НЕсверяемом README-оглавлении — их
        # наличие сторожится здесь (сверка ячейки макетов отключена)
        try:
            _src_t = _fs.read_text(src, encoding="utf-8", errors="replace")
            _rd = files[0].parent / "README.md"
            if ("figma.com" in _src_t.lower() and _rd.exists()
                    and files[0].name.endswith("-main.md")
                    and "figma.com" not in _fs.read_text(_rd, encoding="utf-8", errors="replace").lower()):
                rep = rep + ["предупреждение: источник несёт ссылки "
                             "Figma, а README-оглавление группы — нет: "
                             "макеты живут в README (решение "
                             "2026-08-31), вернуть ссылки"]
        except OSError:
            pass
        # внутренние сторожа неглавных карточек группы — отдельно;
        # источник группы передаётся ТОЛЬКО каналом помилований
        # (pardon_source): без него честное «ОK» из литерала источника
        # бракует часть формы гомоглифом К-30, хотя главную карточку
        # та же страница милует (z03 ISS-03, scr-cl-01.4)
        for extra in files[1:]:
            rep2, ok2 = _run([extra], None, docs, soft_markers=not strict,
                             pardon_src=src)
            rep = rep + [f"[{extra.name}] {ln}" for ln in rep2]
            ok = ok and ok2
        mark = "✓" if ok else "✗"
        # пустой источник (2026-10-05): ✓ без сверки — фиктивная зелень.
        # Замороженная страница (флаг unapproved_jira) — ✗: карточка по
        # ней не создаётся. Пустая без флага — ⚠ (вердикт не меняется:
        # причина неизвестна, решение человеческое). README-оглавление
        # на странице-контейнере без собственного текста — норма, не
        # трогается.
        empty_note, frozen = _empty_source_note(src)
        if empty_note and all(f.name.lower() == "readme.md" for f in files):
            empty_note, frozen = None, False
        if empty_note and frozen:
            ok = False
            mark = "✗"
        elif ok and empty_note:
            mark = "⚠"
        for f in files:
            counts[mark] += 1
        all_ok = all_ok and ok
        names = ", ".join(str(f.relative_to(docs)) for f in files)
        report.append(f"{mark} {names} ← {src.name}")
        if empty_note:
            report.append(f"   {empty_note}")
        if not ok:
            report.extend(f"   {ln}" for ln in rep)
        else:
            report.extend(f"   {ln}" for ln in _warns(rep))

    # проверки уровня комплекта и репозитория — реестр KIT_CHECKS (ядро kitcheck.core):
    # порядок реестра — порядок строк отчёта; вердикт — в run_checks
    _kctx = _KitCtx(docs=docs, sources=sources, strict=strict, catalog=catalog,
                    card_ids=card_ids, card_titles=card_titles,
                    fm_schema_issues=fm_schema_issues, groups=groups, idx=idx)
    _k_lines, _k_ok = run_checks(KIT_CHECKS, _kctx)
    report.extend(_k_lines)
    all_ok = all_ok and _k_ok

    total = sum(counts.values())
    report.append(f"ИТОГО: файлов {total} — ✓ {counts['✓']}, "
                  f"✗ {counts['✗']}, ⚠ {counts['⚠']}; вердикт: "
                  + ("OK" if all_ok else "БРАК"))
    return report, all_ok


# --- проверки уровня комплекта и репозитория (этап 2 рефакторинга) ---
#
# Перенесены из _run_impl дословно: каждый фрагмент — функция-проверка с
# локальными report/all_ok; реестр KIT_CHECKS задаёт порядок строк отчёта.
# Новая проверка уровня комплекта — функция и строка в реестре.

@dataclass
class _KitCtx:
    """Контекст проверок уровня комплекта — итоги переписи файлов прогона."""
    docs: Path
    sources: Optional[Path]
    strict: bool
    catalog: Optional[Path]
    card_ids: Dict[Path, str]
    card_titles: Dict[Path, Tuple[str, str, str]]
    fm_schema_issues: List[Tuple[str, List[str], bool]]
    groups: Dict[str, List[Path]]
    idx: Dict[str, Path]


def _kc_repo_root(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, sources = ctx.docs, ctx.sources
    report: List[str] = []
    all_ok = True
    # --- комплект-уровневые сторожа (срез 2) ---
    # чистота корня репозитория отдачи (2026-08-19): дозаход 5.5 оставил
    # в корне 7 скриптов массовых правок и __pycache__ — прибор корень
    # не видел, устное «удали» не персистентно. Инвариант: корень несёт
    # штатные каталоги (docs/sources/sandbox/.git) и markdown/точечные
    # файлы; исполняемое и кэши = брак.
    # Две топологии комплекта: стендовая (--docs = <root>/docs, root =
    # родитель) и «комплект в корне репозитория» (эталон
    # docs-account-opening-request: brd/, srs/ и корневые документы лежат
    # прямо в корне; --docs = корень). Признак второй — сам docs является
    # корнем git-репозитория (.git внутри; у worktree это файл). Прежний
    # признак «srs/ или brd/ внутри docs» был ложным: в стендовой
    # топологии docs/srs — норма, и прибор молча мерил сам комплект, а
    # на свежей миграции (srs/ ещё нет) — корень репозитория; отсюда
    # ✗ на prompts/ у первого исполнителя v2.x (2026-09-11).
    # С «--docs .» docs.parent == docs («.».parent == «.») — тот же случай.
    _docs_r = docs.resolve()
    if (_docs_r / ".git").exists() or _docs_r.parent == _docs_r:
        root = _docs_r                      # комплект = корень репозитория
    elif (_docs_r.parent / ".git").exists():
        root = _docs_r.parent               # стендовая: <root>/docs
    elif (docs / "srs").is_dir() or (docs / "brd").is_dir():
        root = _docs_r                      # вне git (тесты): прежний признак
    else:
        root = _docs_r.parent
    # prompts/ — промпты этапов планировщика (протокол §10, инструкции
    # треков): штатный артефакт репозитория источника, не мусор
    # (инцидент 2026-09-11: первый исполнитель по плану v2.x получил
    # ✗ на PRE-01 из-за prompts/ и встал на вопрос владельцу).
    # nfr/ — каталог НФТ рядом с docs/ (шаблон nfr.md). На комплекте без
    # srs/ и brd корень проверки — папка сервиса, и без этого имени
    # каталог НФТ читается как посторонний.
    # tasks/ — постановки задач forward-режима «изменение по постановке»
    # (решение 2026-10-15): штатный каталог целевого docs-репозитория
    _ok_dirs = {"docs", "sources", "sandbox", "prompts", ".git", "brd", "srs",
                "nfr", "tasks", _docs_r.name}
    # корень домена: каталоги сервисов из таблицы корневого README законны
    # (решение владельца 2026-10-11); domain-vision.md и glossary.md —
    # markdown, он разрешён и так
    _dom = domain_context(docs)
    if _dom is not None and _dom[0] == root.resolve():
        _ok_dirs |= set(_dom[1].keys())
        _gm = domain_glossary_mode(root / "README.md")
        report.append(f"i домен: корень {root.name}, сервис "
                      + (f"«{_dom[2][0]}»" if _dom[2][1] else "без слота")
                      + " по таблице сервисов корневого README"
                      + ("; глоссарий доменный" if _gm == "domain" else
                         "; глоссарий доменный + указатели" if _gm == "pointers"
                         else ""))
    # штатные не-markdown файлы GitLab-репозитория комплекта
    _ok_files = {"CODEOWNERS", "gpb-manifest.json"}
    if sources is not None:
        # каталог выгрузки задаётся аргументом и не обязан зваться
        # «sources» — если он внутри корня, его вершина легитимна
        try:
            _ok_dirs.add(
                sources.resolve().relative_to(root.resolve()).parts[0])
        except (ValueError, IndexError, OSError):
            pass
    # точечные каталоги (.cursor, .claude, .vscode, .idea) — обёртки IDE,
    # в комплект не входят и в git не пушатся (гид: «только локально»);
    # как и точечные файлы, мусором не считаются (FB-01 lk-mp 2026-10-09:
    # пустой .cursor от IDE давал ✗ корня на первом же прогоне PRE-01)
    junk = sorted(
        p.name for p in root.iterdir()
        if (p.is_dir() and p.name not in _ok_dirs
            and not p.name.startswith("."))
        or (p.is_file() and not p.name.startswith(".")
            and p.name not in _ok_files
            and p.suffix.lower() not in (".md", ".markdown")))
    if junk:
        all_ok = False
        report.append(
            f"✗ корень репозитория: посторонние файлы ×{len(junk)} "
            f"({', '.join(junk[:8])}) — в корне только штатные каталоги "
            "(docs/sources/sandbox/prompts/nfr/tasks) и markdown; рабочие скрипты и кэши "
            "недопустимы (скрипты, изменяющие файлы комплекта, запрещены "
            "вовсе; read-only анализ — в sandbox)")
    return report, all_ok


def _kc_matrix_registry_and_debts(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_ids = ctx.docs, ctx.card_ids
    report: List[str] = []
    all_ok = True
    matrix = docs / "traceability-matrix.md"
    if matrix.is_file():
        # К-22 (2026-08-18): id из frontmatter каждой карточки обязан
        # состоять в реестре ID матрицы — фантомный/авансовый ID вне
        # реестра невидим сверкам и ломает правило выдачи ID (дозаход
        # 3.1: rbac-заглушка с RBAC-001, которого нет в матрице)
        mtext = _fs.read_text(matrix, encoding="utf-8", errors="replace")
        ghosts = sorted((p, cid) for p, cid in card_ids.items()
                        if cid not in mtext)
        if ghosts:
            all_ok = False
            report.append("✗ реестр ID матрицы: фантомные id карточек "
                          "(в реестре матрицы отсутствуют — ID выдаются "
                          "по реестру, авансовые запрещены):")
            report.extend(
                f"   {p.relative_to(docs)}: id {cid} ✗"
                for p, cid in ghosts[:10])
        rep, ok = _safe(ld.check, matrix, docs, catalog_codes())
        mark = "✓" if ok else "✗"
        all_ok = all_ok and ok
        report.append(f"{mark} долги ссылок (link_debts):")
        report.extend(f"   {ln}" for ln in rep)
    else:
        all_ok = False
        report.append("✗ traceability-matrix.md: матрица не найдена — "
                      "комплект без реестра ID (обязательна, conventions "
                      "§5.3)")
    return report, all_ok


def _kc_open_questions(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    oq = docs / "open-questions.md"
    if not oq.is_file():
        oq = docs.parent / "open-questions.md"
    rep, ok = _safe(ld.check_oq_order, oq)
    all_ok = all_ok and ok
    # К-17: page_id в текстах OQ — софт-сигнал (носители page_id — только
    # frontmatter и матрица; ужесточение после вычистки легаси-фона)
    wrep, _ = _safe(nt.check_oq_page_refs, oq)
    if rep or wrep:
        report.append(("✓" if ok else "✗") + " реестр открытых вопросов:")
        report.extend(f"   {ln}" for ln in rep)
        report.extend(f"   {ln}" for ln in wrep)
    return report, all_ok


def _kc_id_slots(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_ids = ctx.docs, ctx.card_ids
    report: List[str] = []
    all_ok = True
    # слот части сервиса в ID (2026-09-28): таблица кодов в README комплекта
    rep, ok = _safe(check_id_slots, docs, card_ids)
    all_ok = all_ok and ok
    if rep:
        report.append(("✓" if ok else "✗") + " слот части сервиса в ID:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_frontmatter_schema(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    fm_schema_issues, = ctx.fm_schema_issues,
    report: List[str] = []
    all_ok = True
    # одинаковые названия разных артефактов одного типа (ПР-08 разбора
    # замечаний ОНБ-В, 2026-10-16) — читатель не различит их по названию;
    # ⚠, вердикт не трогает
    fs_rep = format_frontmatter_schema(fm_schema_issues)
    report.extend(fs_rep)
    return report, all_ok


def _kc_title_uniqueness(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_titles = ctx.docs, ctx.card_titles
    report: List[str] = []
    all_ok = True
    tu_rep = check_title_uniqueness(docs, card_titles)
    if tu_rep:
        report.append("⚠ одинаковые названия разных артефактов одного типа:")
        report.extend(f"   {ln}" for ln in tu_rep)
    return report, all_ok


def _kc_source_silent(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # пробелы постановки (conventions §6 п.5, ПР-12 разбора ОНБ-В): ⚠
    ss_rep, _ = _safe(lambda: (check_source_silent(docs), True))
    report.extend(ss_rep)
    return report, all_ok


def _kc_required_sections(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # обязательные разделы шаблона (пакет 2 задача 7, ПР-05, ЗК-23): нет раздела — ⚠,
    # раздел вне шаблона — i; вердикт не трогают
    rs_rep, _ = _safe(lambda: (check_required_sections(docs), True))
    report.extend(rs_rep)
    return report, all_ok


def _kc_process_call(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # шаг процесса ↔ карточка вызова (пакет 2 задача 8, ЗК-13) — ⚠
    pc_rep, _ = _safe(lambda: (check_process_call_consistency(docs), True))
    report.extend(pc_rep)
    return report, all_ok


def _kc_readme_legend(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, card_ids = ctx.docs, ctx.card_ids
    report: List[str] = []
    all_ok = True
    # условные обозначения README (2026-10-10): самоописание комплекта
    # для внешних читателей — ⚠-сигналы, вердикт не трогают
    lg_rep, _ = _safe(lambda: (check_readme_legend(docs, card_ids), True))
    if lg_rep:
        report.append("⚠ условные обозначения README (самоописание "
                      "комплекта):")
        report.extend(f"   {ln}" for ln in lg_rep)
    return report, all_ok


def _kc_feedback_order(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # реестр замечаний команды (цикл обратной связи, модель 2026-08-17):
    # feedback.md живёт в КОРНЕ репозитория отдачи; файла нет — ок
    rep, ok = _safe(ld.check_feedback_order, docs.parent / "feedback.md")
    all_ok = all_ok and ok
    if rep:
        report.append(("✓" if ok else "✗") + " реестр замечаний команды:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_coordination_log(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # журнал координации (трек с координатором): длина записи — ⚠
    # (решение 2026-10-09: журнал должен читаться следующей сессией)
    rep, _ = _safe(ld.check_coordination_log,
                   docs.parent / "coordination-log.md")
    if rep:
        report.append("i журнал координации:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_config_params(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    rep, ok = _safe(ld.check_config_params, docs)
    all_ok = all_ok and ok
    if not ok:
        report.append("✗ настраиваемые параметры:")
        report.extend(f"   {ln}" for ln in rep)
    return report, all_ok


def _kc_sources_protocol(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, sources, groups = ctx.docs, ctx.sources, ctx.groups
    report: List[str] = []
    all_ok = True
    if sources is not None:
        # сторож разметки подсервисов (П-4): без таблицы в профиле
        # возвращает пусто и молчит
        sm_rep, sm_ok = _safe(check_subservice_mapping, docs, sources,
                              {pid: fs[0] for pid, fs in groups.items()})
        all_ok = all_ok and sm_ok
        report.extend(sm_rep)
        # сторож среза канона (П-5b): без строки в профиле молчит
        cut_rep, cut_ok = _safe(check_canon_cut, sources, canon_head())
        all_ok = all_ok and cut_ok
        report.extend(cut_rep)
        # сторож полноты промптов этапов (П-5b): информационный,
        # без строки «план миграции» в профиле молчит
        sp_rep, _ = _safe(check_stage_prompts, sources)
        report.extend(sp_rep)
        # сторожа протокольной дисциплины (П-5c): скрипты и retry-лимит
        pd_rep, pd_ok = _safe(check_protocol_discipline, sources)
        all_ok = all_ok and pd_ok
        report.extend(pd_rep)
    return report, all_ok


def _kc_service_catalog_and_h1(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, catalog = ctx.docs, ctx.catalog
    report: List[str] = []
    all_ok = True
    # сторож каталога сервисов (2026-09-29): ⚠-сигналы, вердикт не
    # трогают; без каталога (dev-копия вне канона, без --catalog) молчит
    cat_rep, _ = _safe(check_service_catalog,
                       catalog if catalog is not None
                       else canon_catalog_path(), docs)
    # H1 без названия сервиса (conventions §5; пакет 2 задача 9, ЗК-26) — ⚠
    h1_rep, _ = _safe(lambda: (check_h1_service(
        docs, catalog if catalog is not None else canon_catalog_path()), True))
    report.extend(h1_rep)
    report.extend(cat_rep)
    return report, all_ok


def _kc_no_api_in_bundle(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # контракты OpenAPI/AsyncAPI — в репозитории кода (2026-10-06):
    # каталог api/ и YAML в комплекте — ⚠ до удаления владельцем;
    # ссылки матрицы «API ↔ SRS» — через HEAD, явный ref по правилу
    na_rep, _ = _safe(check_no_api_in_bundle, docs)
    report.extend(na_rep)
    return report, all_ok


def _kc_api_matrix_refs(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, strict = ctx.docs, ctx.strict
    report: List[str] = []
    all_ok = True
    ar_rep, ar_ok = _safe(check_api_matrix_refs, docs, strict)
    all_ok = all_ok and ar_ok
    report.extend(ar_rep)
    return report, all_ok


def _kc_similar_group_points(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # детектор похожих точек применения групп (П-5e): i-сигналы,
    # вердикт не трогают — решение о консолидации только человеческое
    sg_rep, _ = _safe(lambda: (check_similar_group_points(docs), True))
    report.extend(sg_rep)
    return report, all_ok


def _kc_bare_entity_mentions(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # голые атрибутные обращения к сущностям реестра (2026-08-29):
    # ⚠-сигналы, вердикт не трогают
    bm_rep, _ = _safe(lambda: (check_bare_entity_mentions(docs), True))
    report.extend(bm_rep)
    return report, all_ok


def _kc_named_entity_links(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # ссылки-названия на сущности без более ранней полной ссылки с ID
    # (2026-10-02): ⚠-сигналы, вердикт не трогают
    ne_rep, _ = _safe(lambda: (check_named_entity_links(docs), True))
    report.extend(ne_rep)
    return report, all_ok


def _kc_group_contours(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # согласованность контура групп контролей (полигон 2026-08-29):
    # ⚠-сигналы, вердикт не трогают — решения о контуре человеческие
    gc_rep, _ = _safe(lambda: (check_group_contours(docs), True))
    report.extend(gc_rep)
    return report, all_ok


def _kc_file_artifacts(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # сторож не-markdown артефактов files/ (сироты и битые ссылки —
    # брак: потеря приложения молчаливая)
    fa_rep, fa_ok = _safe(check_file_artifacts, docs)
    all_ok = all_ok and fa_ok
    report.extend(fa_rep)
    return report, all_ok


def _kc_structured_examples(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, idx = ctx.docs, ctx.idx
    report: List[str] = []
    all_ok = True
    # структурные сторожа (2026-10-10): sidecar-примеры разбираются
    # (брак переноса ✗ / дефект источника ⚠), относительные ссылки
    # ведут на существующие файлы (✗)
    se_rep, se_ok = _safe(check_structured_examples, docs, idx)
    all_ok = all_ok and se_ok
    report.extend(se_rep)
    return report, all_ok


def _kc_relative_links(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    rl_rep, rl_ok = _safe(check_relative_links, docs)
    all_ok = all_ok and rl_ok
    report.extend(rl_rep)
    return report, all_ok


def _kc_link_anchors_and_ids(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    # якоря ссылок и упоминание карточки без ID (ПР-06 разбора замечаний
    # ОНБ-В, 2026-10-16) — ⚠, вердикт не трогают
    la_rep, _ = _safe(lambda: (check_link_anchors_and_ids(docs), True))
    report.extend(la_rep)
    return report, all_ok


def _kc_nfr_catalog(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, = ctx.docs,
    report: List[str] = []
    all_ok = True
    nfr_rep, nfr_ok = _safe(check_nfr_catalog, docs)
    all_ok = all_ok and nfr_ok
    report.extend(nfr_rep)
    return report, all_ok


def _kc_source_coverage(ctx: "_KitCtx") -> Tuple[List[str], bool]:
    docs, sources = ctx.docs, ctx.sources
    report: List[str] = []
    all_ok = True
    if sources is not None:
        # миграционный гейт покрытия — информационный: непокрытое —
        # остаток конвейера (судьба фиксируется долгами), не дефект
        # проверяемых карточек; на вердикт не влияет
        try:
            cov_lines, _n_unc = sc.coverage_report(sources, docs)
        except Exception as e:
            cov_lines = [f"КРАШ проверки: {e!r} — покрытие не оценено"]
        report.append("i покрытие выгрузки (миграционный гейт, "
                      "информационно):")
        report.extend(f"   {ln}" for ln in cov_lines)
    return report, all_ok


KIT_CHECKS: List[Check] = [
    Check("repo_root", _kc_repo_root, affects_verdict=True),
    Check("matrix_registry_and_debts", _kc_matrix_registry_and_debts, affects_verdict=True),
    Check("open_questions", _kc_open_questions, affects_verdict=True),
    Check("id_slots", _kc_id_slots, affects_verdict=True),
    Check("frontmatter_schema", _kc_frontmatter_schema, affects_verdict=False),
    Check("title_uniqueness", _kc_title_uniqueness, affects_verdict=False),
    Check("source_silent", _kc_source_silent, affects_verdict=False),
    Check("required_sections", _kc_required_sections, affects_verdict=False),
    Check("process_call", _kc_process_call, affects_verdict=False),
    Check("readme_legend", _kc_readme_legend, affects_verdict=False),
    Check("feedback_order", _kc_feedback_order, affects_verdict=True),
    Check("coordination_log", _kc_coordination_log, affects_verdict=False),
    Check("config_params", _kc_config_params, affects_verdict=True),
    Check("sources_protocol", _kc_sources_protocol, affects_verdict=True),
    Check("service_catalog_and_h1", _kc_service_catalog_and_h1, affects_verdict=False),
    Check("no_api_in_bundle", _kc_no_api_in_bundle, affects_verdict=False),
    Check("api_matrix_refs", _kc_api_matrix_refs, affects_verdict=True),
    Check("similar_group_points", _kc_similar_group_points, affects_verdict=False),
    Check("bare_entity_mentions", _kc_bare_entity_mentions, affects_verdict=False),
    Check("named_entity_links", _kc_named_entity_links, affects_verdict=False),
    Check("group_contours", _kc_group_contours, affects_verdict=False),
    Check("file_artifacts", _kc_file_artifacts, affects_verdict=True),
    Check("structured_examples", _kc_structured_examples, affects_verdict=True),
    Check("relative_links", _kc_relative_links, affects_verdict=True),
    Check("link_anchors_and_ids", _kc_link_anchors_and_ids, affects_verdict=False),
    Check("nfr_catalog", _kc_nfr_catalog, affects_verdict=True),
    Check("source_coverage", _kc_source_coverage, affects_verdict=False),
]


# --- сторож разметки подсервисов (П-4 песочницы, 2026-08-26) ---
#
# Крупный сервис из подсервисов (conventions §3.1): таблица «Разметка
# подсервисов» в профиле источников (sources/README.md) декларирует
# «тег/ветвь выгрузки → подсервис <слаг> | core <слаг> | общая часть |
# вне Экосистемы»; путь карточки — srs/[<слаг>/]<тип>/. Сторож держит
# соответствие «источник → путь» механически (иначе разметка — устная
# договорённость). Гейт МОЛЧИТ без таблицы (обычные сервисы не
# затронуты); матчер — тег-префикс титула источника или имя
# верхнеуровневой ветви выгрузки, первая подошедшая строка выигрывает.

_KNOWN_TYPES = {
    "function", "screen-form", "control", "process", "data-model",
    "contract-call", "internal-contract", "lib-contract", "print-form", "notification",
    "agent", "brd",
}
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
        if kind == "external":
            ok = False
            report.append(
                f"✗ разметка: {rel} — источник «{title[:50]}» размечен "
                "«вне Экосистемы», карточке в docs/ не место "
                "(мини-комплект вне комплекта, conventions §3.1)")
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


# --- сторож слота части сервиса в ID (2026-09-28) ---
#
# Сервис из подсервисов (conventions §3.1, схема ID «Слот части сервиса»):
# идентификатор нумерованного артефакта несёт слот части сразу после
# префикса — `FUN-DS-SYS-01`, `ENT-SHR-001`, `NTF-DS-000`. Коды частей
# объявляются один раз таблицей в README корня комплекта (колонки «Код»
# и «Каталог»); общая часть — каталог `srs/shared/`, код `SHR`. Сторож
# держит три инварианта механически: слот только у сервиса с таблицей;
# слот карточки в `srs/<каталог>/…` равен коду этого каталога по
# таблице; документ вне каталогов подсервисов (уровень сервиса, корень
# `srs/`) слота не несёт. Без таблицы и без каталогов подсервисов сторож
# молчит — обычные сервисы не затронуты. Прецедент: docs-sign (слот в
# каждом ID, таблица кодов в README) против §3.1 «подсервис в ID не
# кодируется» — решение владельца 2026-09-28 в пользу объявляемого слота.

_PART_TABLE_HEAD_RE = re.compile(
    r"^#+\s*.*(?:слот|подсервис|част[иь] сервиса|коды частей).*$", re.I | re.M)


# --- домен сервисов (решение владельца 2026-10-11) ---
#
# Доменный docs-репозиторий: в корне README с ТАБЛИЦЕЙ СЕРВИСОВ (колонки
# «Код», «Каталог» (или «service-id»), необязательно «Слот» — код либо
# «нет»), domain-vision.md и glossary.md домена; комплекты сервисов — в
# `<service-id>/`, общий сервис — `shared/`. Идентификатор артефакта
# комплекта домена несёт слот сервиса сразу после префикса
# (`FUN-REG-IDN-CL-01`, `ENT-SHR-001`), слот части — следом, как прежде.
# Без таблицы сервисов в README родителя комплекта прибор ведёт себя как
# раньше: одиночные сервисы и сервисы с частями не затронуты.

def _cell_plain(cell: str) -> str:
    """Текст ячейки без markdown: ссылка → её текст, без бэктиков/жирного."""
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    return cell.strip().strip("*`").strip()


def _load_service_table(readme: Path):
    """{каталог: (слот, слот_в_id)} по таблице сервисов корневого README
    домена; None — таблицы нет. Таблица узнаётся по шапке: колонка
    каталога («Каталог» либо «service-id») и колонка слота («Слот» либо
    «Код» — «Код в ID» у «Цифрового рубля»). Значение «нет» в колонке
    слота — сервис включён в домен без перенумерации (решение владельца
    2026-10-12: термины `service-id` и «слот сервиса» разведены, таблица
    `service-id | Слот | Название | Вход`)."""
    try:
        text = _fs.read_text(readme, encoding="utf-8", errors="replace")
    except OSError:
        return None
    header: Optional[List[str]] = None
    out: Dict[str, Tuple[str, bool]] = {}
    for ln in text.splitlines():
        st = ln.strip()
        if not st.startswith("|"):
            if header is not None and out:
                break               # таблица закончилась
            header = None
            continue
        cells = table_cells(st)
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        low = [c.lower() for c in cells]
        if header is None:
            if any("слот" in h or "код" in h for h in low) and any(
                    "каталог" in h or "service-id" in h for h in low):
                header = low
            continue
        idir = next((i for i, h in enumerate(header) if "каталог" in h), None)
        if idir is None:
            idir = next(i for i, h in enumerate(header) if "service-id" in h)
        islot = next((i for i, h in enumerate(header) if "слот" in h), None)
        if islot is None:
            islot = next(i for i, h in enumerate(header) if "код" in h)
        if len(cells) <= max(islot, idir):
            continue
        slot = _cell_plain(cells[islot])
        folder = _cell_plain(cells[idir]).strip("/")
        if folder.endswith("/README.md"):
            folder = folder[:-len("/README.md")]
        folder = folder.strip("/").split("/")[0]
        if not folder:
            continue
        if slot.lower() in ("нет", "no", "-", "—", ""):
            out[folder] = ("", False)
        elif _PART_CODE_RE.fullmatch(slot):
            out[folder] = (slot, True)
    return out or None


_GLOSSARY_MODE_RE = re.compile(r"Глоссарий\s*[:—-]\s*(доменный(?:\s*\+\s*указатели)?)",
                               re.I)


def domain_glossary_mode(readme: Path) -> Optional[str]:
    """Режим глоссария, объявленный в README домена (решение владельца
    2026-10-12): «доменный» — один файл домена, в комплектах глоссария нет;
    «доменный + указатели» — в каждом комплекте указатель. None — не
    объявлен (одиночный сервис либо режим не выбран)."""
    try:
        text = _fs.read_text(readme, encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _GLOSSARY_MODE_RE.search(text)
    if not m:
        return None
    return "pointers" if "указател" in m.group(1).lower() else "domain"


def domain_context(docs: Path):
    """(корень домена, таблица сервисов, запись этого комплекта) либо None:
    родитель комплекта несёт README с таблицей сервисов, в которой есть
    каталог комплекта."""
    d = docs.resolve()
    parent = d.parent
    if parent == d:
        return None
    table = _load_service_table(parent / "README.md")
    if not table or d.name not in table:
        return None
    return parent, table, table[d.name]
_PART_CODE_RE = re.compile(r"^[A-Z]{2,4}$")
# контуры и служебные сегменты ID — не слоты частей
_NOT_SLOT = {"CL", "BNK", "SYS", "GRP", "EXT", "INT"}
# каталоги типов в старой (множественной) раскладке — не подсервисы
_LEGACY_TYPE_DIRS = {"functions", "screen-forms", "controls", "print-forms",
                     "contract-calls", "internal-contracts", "lib-contracts",
                     "external-integrations", "processes"}


def _load_part_codes(readme: Path):
    """{код: каталог} по таблице кодов частей в README корня комплекта.
    None — таблицы нет; {} — таблица есть, но без колонки «Каталог»."""
    try:
        text = _fs.read_text(readme, encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _PART_TABLE_HEAD_RE.search(text)
    if not m:
        return None
    header: Optional[List[str]] = None
    codes: Dict[str, str] = {}
    for ln in text[m.end():].splitlines():
        st = ln.strip()
        if st.startswith("#"):
            break
        if not st.startswith("|"):
            continue
        cells = table_cells(st)
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        try:
            icode = next(i for i, h in enumerate(header) if "код" in h)
        except StopIteration:
            return None
        idir = next((i for i, h in enumerate(header) if "каталог" in h), None)
        if idir is None:
            return {}
        if len(cells) <= max(icode, idir):
            continue
        code = cells[icode].strip("*` ")
        folder = cells[idir].strip("*` /")
        if _PART_CODE_RE.fullmatch(code) and folder:
            codes[code] = folder
    if header is None:
        return None
    return codes


# Схема шапки (техбук conventions §5, «Состав полей шапки — закрытый по типу
# документа»): общие поля + поля отдельных типов. Пакет 2 задача 6 / ПР-04.
_FM_COMMON = frozenset({"id", "type", "service", "title", "confluence_page_ids"})
_FM_BY_TYPE = {
    "kind": {"function"},
    "entity": {"control"},
    "partOf": None,  # файл-часть многофайлового документа любого типа
    "origin": {"feature", "use-case", "business-rules", "vision"},
}
# ВРЕМЕННЫЕ исключения — до схемы техбука §5 волны 5: поля, которые задают
# шаблоны канона, но которых пока нет в yaml-схеме стандарта (domain —
# domain-vision и доменный glossary; ingress, nfr_type — nfr; task, created —
# task); после вливания волны 5 техбука убрать одной правкой вместе с
# _FM_VERSION_EXEMPT (version уходит из шаблона nfr.md)
_FM_TEMPLATE_EXTRA = {
    "domain": {"domain-vision", "glossary", "vision"},
    "ingress": {"nfr"},
    "nfr_type": {"nfr"},
    "task": {"task"},
    "created": {"task"},
}
_FM_VERSION_EXEMPT = {"nfr"}  # ВРЕМЕННО: до схемы техбука §5 волны 5


def frontmatter_schema_issues(fm: Dict[str, str]) -> Tuple[List[str], bool]:
    """(поля вне схемы типа, есть ли устаревшее `version`). Служебные ключи
    разбора (`__…`) не считаются."""
    typ = str(fm.get("type", "")).strip().strip("'\"")
    bad: List[str] = []
    has_version = False
    for k in fm:
        if k.startswith("__") or k in _FM_COMMON:
            continue
        if k == "version":
            has_version = typ not in _FM_VERSION_EXEMPT
            continue
        allowed = _FM_BY_TYPE.get(k, _FM_TEMPLATE_EXTRA.get(k, set()))
        if allowed is None or typ in allowed:
            continue
        bad.append(k)
    return sorted(bad), has_version


def format_frontmatter_schema(issues: List[Tuple[str, List[str], bool]]) -> List[str]:
    """Строки отчёта сторожа состава шапки (⚠, вердикт не меняют)."""
    out: List[str] = []
    bad = [(f, b) for f, b, _v in issues if b]
    ver = [f for f, _b, v in issues if v]
    if bad:
        out.append(f"⚠ поля шапки вне схемы типа (conventions §5, состав закрыт по типу): "
                   f"файлов {len(bad)}")
        out.extend(f"   {f}: {', '.join(b)}" for f, b in bad[:30])
        if len(bad) > 30:
            out.append(f"   … и ещё {len(bad) - 30}")
        by_field: Dict[str, int] = {}
        for _f, b in bad:
            for k in b:
                by_field[k] = by_field.get(k, 0) + 1
        out.append("   по полям: " + ", ".join(f"{k} ×{n}" for k, n in
                                                 sorted(by_field.items(), key=lambda x: -x[1])))
    if ver:
        out.append(f"⚠ поле шапки version устарело (в новых комплектах не используется, "
                   f"conventions §2): файлов {len(ver)} — убрать ближайшим заходом")
    return out


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().strip("'\"")).lower().replace("ё", "е")


def check_title_uniqueness(docs: Path,
                           card_titles: Dict[Path, Tuple[str, str, str]]) -> List[str]:
    """Строки отчёта (пусто — дублей нет). Ключ — тип + нормализованный
    title (регистр и пробелы не различаются, тег «[…]» входит в название).
    Не дубль: README-реестры (навигация) и части одной группы с общим
    базовым ID (`SCR-CL-01.1…01.5` законно несут название экрана)."""
    groups: Dict[Tuple[str, str], List[Tuple[Path, str, str]]] = {}
    for p, (typ, title, cid) in card_titles.items():
        if p.name.lower() == "readme.md":
            continue
        groups.setdefault((typ.strip().lower(), _norm_title(title)), []).append(
            (p, title, str(cid).strip()))
    out: List[str] = []
    for (typ, _t), items in sorted(groups.items()):
        bases = {re.sub(r"\.\d+$", "", cid) for _p, _ti, cid in items}
        if len(bases) < 2:
            continue
        ids = ", ".join(sorted(cid for _p, _ti, cid in items))
        files = ", ".join(sorted(p.relative_to(docs).as_posix() for p, _ti, _c in items))
        out.append(f"{typ}: {ids} — «{items[0][1].strip().strip(chr(39) + chr(34))}» "
                   f"×{len(items)} ({files})")
    return out


_SILENT_FORMULA = "в постановке не задано"
_GAP_MARK_RE = re.compile(r"не задано|вне выгрузки|в срезе|уточняется|\bTBD\b", re.I)
_GAP_QUOTED_RE = re.compile(r'«[^»\n]*»|"[^"\n]*"|`[^`\n]*`')


def check_source_silent(docs: Path) -> List[str]:
    """Перечень пробелов постановки (conventions §6 п.5, ПР-12 разбора
    замечаний ОНБ-В): вхождения формулы «в постановке не задано» с адресами
    и пометки о пробеле не по формуле («не задано», «вне выгрузки», «в
    срезе», «уточняется», «TBD») вне формулы, frontmatter, кода и
    кавычечных литералов (дословная цитата источника — данные). Только ⚠."""
    found: List[str] = []
    other: List[str] = []
    for md in _kit_md(docs):
        try:
            lines = _fs.read_text(md, encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = md.relative_to(docs).as_posix()
        in_fm = bool(lines) and lines[0].strip() == "---"
        in_code = False
        for i, ln in enumerate(lines, 1):
            st = ln.strip()
            if in_fm:
                if i > 1 and st == "---":
                    in_fm = False
                continue
            if is_fence(st):
                in_code = not in_code
                continue
            if in_code:
                continue
            low = ln.lower()
            if _SILENT_FORMULA in low:
                found.append(f"{rel}:{i}: {st[:80]}")
            rest = _GAP_QUOTED_RE.sub(" ", low.replace(_SILENT_FORMULA, " "))
            if _GAP_MARK_RE.search(rest):
                other.append(f"{rel}:{i}: {st[:80]}")
    out: List[str] = []
    if found:
        out.append(f"⚠ формула «{_SILENT_FORMULA}» ×{len(found)} — перечень пробелов постановки:")
        out.extend(f"   {x}" for x in found[:30])
        if len(found) > 30:
            out.append(f"   … и ещё {len(found) - 30}")
    if other:
        out.append(f"⚠ пометка о пробеле не по формуле ×{len(other)} (conventions §6 п.5: "
                   f"единственная допустимая пометка — «{_SILENT_FORMULA}»):")
        out.extend(f"   {x}" for x in other[:30])
        if len(other) > 30:
            out.append(f"   … и ещё {len(other) - 30}")
    return out


# Обязательные разделы по шаблонам канона (пакет 2, задача 7, ПР-05, ЗК-23; решения
# владельца канона 2026-10-16). Только шаблоны с явной пометкой «(обязательный)»;
# H2 образцов карточек обязательными не считаются. Сравнение — без номеров,
# ID-префикса («NTF-AGR-01. …»), пометки в скобках, регистра и ё/е; раздел
# совпадает и по началу имени («Как перейти на страницу» ~ «как перейти»).
# Условные разделы ЭФ («Видимость блоков» — если блоков больше одного, «События»,
# «Кнопки», «Сообщения», «Функции формы») не требуются: условие по тексту не
# проверяемо. Раздел, где только формула «в постановке не задано», — законный:
# проверяется наличие заголовка, не содержимое.
_REQ_SECTIONS: Dict[str, Tuple[str, ...]] = {
    "agent": ("описание агента", "описание процесса"),
    "control": ("назначение", "группы контролей", "реестр контролей",
                "карточки контролей"),
    "function": ("назначение", "доступность", "вызов функции", "поведение"),
    "notification": ("каналы и адреса доставки", "сообщения нотификации"),
    "screen-form": ("назначение", "реестр полей", "правила полей"),
}
# Все разделы шаблона (для строки «вне шаблона», i). Функция — None: шаблон
# разрешает дополнительные H2 («Дополнительные разделы»). ЭФ — с разделами
# README группы и главной карточки из описания ролей файлов шаблона.
_KNOWN_SECTIONS: Dict[str, Optional[Tuple[str, ...]]] = {
    "agent": ("описание агента", "схема", "описание процесса"),
    "control": _REQ_SECTIONS["control"],
    "function": None,
    "notification": ("вводное описание", "каналы и адреса доставки",
                     "сообщения нотификации", "общие шаблоны сообщений"),
    "screen-form": ("назначение", "реестр полей", "видимость блоков",
                    "правила полей", "события", "кнопки", "сообщения",
                    "функции формы", "боковая часть", "части", "макеты",
                    "как перейти", "структура экрана", "дополнительные действия",
                    "группы контролей", "определения"),
}
# заглушка ЭФ (шаблон screen-form): frontmatter + «Назначение» + строка
# «Документ-заглушка: …» — прочие обязательные разделы не требуются
_STUB_MARK = "документ-заглушка"
_SECTION_ID_RE = re.compile(r"^[A-ZА-ЯЁ]{2,}(?:-[A-ZА-ЯЁ0-9]+)+(?:\.[A-Z0-9]+)*\.?\s+")


def _section_key(heading: str) -> str:
    h = re.sub(r"^#+\s*", "", heading).strip()
    h = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", h)
    h = _SECTION_ID_RE.sub("", h)
    h = re.sub(r"\s*\([^)]*\)\s*$", "", h)
    return h.lower().replace("ё", "е").strip(" .:")


def _h2_keys(text: str) -> List[str]:
    out: List[str] = []
    in_code = False
    for ln in text.splitlines():
        st = ln.strip()
        if is_fence(st):
            in_code = not in_code
            continue
        if not in_code and re.match(r"^##\s", ln):
            out.append(_section_key(ln))
    return out


def _has_section(keys: List[str], name: str) -> bool:
    return any(k == name or k.startswith(name) for k in keys)


def check_required_sections(docs: Path) -> List[str]:
    """⚠ «нет обязательного раздела» и i «раздел вне шаблона» для типов agent,
    control, function, notification, screen-form. Единица проверки: файл;
    документ контролей — каталог (README CTL-000 и файлы карточек); экранная
    форма — группа по ID без суб-номера (README группы без шапки, главная
    карточка, части), частям отдельного сигнала нет. README-реестры каталогов
    (README функций, ID ЭФ на «-00»/«-000») не проверяются."""
    units: Dict[Tuple[str, str], List[Path]] = {}
    for md in _kit_md(docs):
        fm = read_frontmatter(md) or {}
        typ = str(fm.get("type", "")).strip("'\"")
        fid = str(fm.get("id", "")).strip("'\"")
        if not typ and md.name.lower() == "readme.md":
            mains = sorted(md.parent.glob("*-main.md"))
            if mains:
                mfm = read_frontmatter(mains[0]) or {}
                typ = str(mfm.get("type", "")).strip("'\"")
                fid = str(mfm.get("id", "")).strip("'\"")
        if typ not in _REQ_SECTIONS or md.name == "status-model.md":
            continue
        if typ == "screen-form":
            if not fid or re.search(r"-0+$", fid):
                continue
            key = re.sub(r"(?:\.\d+)+$", "", fid)
        elif typ == "control":
            key = md.parent.relative_to(docs).as_posix() + "/"
        else:
            if md.name.lower() == "readme.md":
                continue
            key = md.relative_to(docs).as_posix()
        units.setdefault((typ, key), []).append(md)
    missing: List[str] = []
    extra: Dict[Tuple[str, str], int] = {}
    for (typ, key), files in sorted(units.items()):
        keys: List[str] = []
        stub = False
        for f in files:
            try:
                text = _fs.read_text(f, encoding="utf-8", errors="replace")
            except OSError:
                continue
            keys.extend(_h2_keys(text))
            stub = stub or _STUB_MARK in text.lower()
        req = ("назначение",) if typ == "screen-form" and stub else _REQ_SECTIONS[typ]
        lost = [r for r in req if not _has_section(keys, r)]
        if lost:
            where = key if typ != "screen-form" else (
                f"{key} ({sorted(files)[0].relative_to(docs).as_posix()})")
            missing.append(f"{where} [{typ}]: " + ", ".join(
                f"«{r.capitalize()}»" for r in lost))
        known = _KNOWN_SECTIONS[typ]
        if known is None:
            continue
        for k in sorted(set(keys)):
            if k and not any(k == n or k.startswith(n) for n in known):
                extra[(typ, k)] = extra.get((typ, k), 0) + 1
    out: List[str] = []
    if missing:
        out.append(f"⚠ нет обязательного раздела шаблона (пометка «(обязательный)» "
                   f"в _meta/templates; раздел с одной формулой «{_SILENT_FORMULA}» "
                   f"законен): единиц {len(missing)}")
        out.extend(f"   {x}" for x in missing[:30])
        if len(missing) > 30:
            out.append(f"   … и ещё {len(missing) - 30}")
    if extra:
        top = sorted(extra.items(), key=lambda kv: (-kv[1], kv[0]))
        out.append(f"i разделы вне шаблона (к сведению): имён {len(extra)}, "
                   f"вхождений {sum(extra.values())} — "
                   + "; ".join(f"{t}: «{k}» ×{n}" for (t, k), n in top[:12])
                   + (" …" if len(top) > 12 else ""))
    return out


# Шаг процесса ↔ карточка вызова (пакет 2, задача 8, ЗК-13). Норма: шаг через
# вызов чужого контракта ссылается на карточку CALL-* (шаблон process, «Таблица
# шагов»); карточка вызова в разделе «Использование в сервисе» ссылается на
# процессы и шаги (шаблон contract-call). Номер шага — литерал; диапазон
# «1.4–1.5» / «3–7» с общим префиксом раскрывается в перечень номеров.
_STEP_NUM_RE = re.compile(r"\d+(?:\.\d+)*")
_STEP_CELL_RE = re.compile(r"\**\d+(?:\.\d+)*\.?\**")
_STEP_HEAD_RE = re.compile(r"^#{3,4}\s+(?:Шаг\s+)?(\d+(?:\.\d+)*)\b")
_STEP_RANGE_RE = re.compile(r"(\d+(?:\.\d+)*)\s*[–—-]\s*(\d+(?:\.\d+)*)")
_CALL_USAGE_RE = re.compile(r"^##\s+(?:\d+\.\s*)?(?:Использование в сервисе|Где используется)",
                            re.I)


def _step_literals(cell: str) -> set:
    """Номера шагов ячейки «Шаг / место»: литералы и раскрытые диапазоны."""
    out = set(_STEP_NUM_RE.findall(cell))
    for a, b in _STEP_RANGE_RE.findall(cell):
        pa, pb = a.rsplit(".", 1) if "." in a else ("", a), \
            b.rsplit(".", 1) if "." in b else ("", b)
        if pa[0] == pb[0] and int(pa[1]) < int(pb[1]) <= int(pa[1]) + 50:
            pre = pa[0] + "." if pa[0] else ""
            out |= {f"{pre}{n}" for n in range(int(pa[1]), int(pb[1]) + 1)}
    return out


def _link_targets(md: Path, text: str):
    for m in _MD_LINK_RE.finditer(text):
        raw_t = m.group(2).strip()
        if "://" in raw_t or raw_t.startswith(("mailto:", "<")):
            continue
        path_part = unquote(raw_t).partition("#")[0].replace("\\", "/")
        if not path_part:
            continue
        try:
            yield (md.parent / path_part).resolve()
        except OSError:
            continue


def check_process_call_consistency(docs: Path) -> List[str]:
    """⚠ при расхождении прямой и обратной ссылок «PROC шаг N → CALL» /
    «CALL → PROC, шаг N»: нет обратной, нет прямой, номер шага расходится.
    Строки карточки вызова, ведущие на FUN/SCR, не сверяются (норма — процессы);
    ячейка места без номера («Отображение») номер не сверяет."""
    ids: Dict[Path, str] = {}
    meta: Dict[Path, Tuple[str, str, str]] = {}
    for md in _kit_md(docs):
        fm = read_frontmatter(md) or {}
        cid = str(fm.get("id", "")).strip("'\"")
        if cid:
            ids[md.resolve()] = cid
        meta[md] = (str(fm.get("type", "")).strip("'\""), cid,
                    md.relative_to(docs).as_posix())
    fwd: Dict[Tuple[str, str], set] = {}
    back: Dict[Tuple[str, str], Tuple[set, str]] = {}
    for md, (typ, cid, _rel) in meta.items():
        if typ == "process" and cid.startswith("PROC") \
                and md.name.lower() not in ("readme.md", "status-model.md"):
            try:
                lines = _fs.read_text(md, encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            in_code, head_step = False, ""
            for ln in lines:
                st = ln.strip()
                if is_fence(st):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                if st.startswith("#"):
                    hm = _STEP_HEAD_RE.match(st)
                    head_step = hm.group(1) if hm else ""
                    continue
                step = ""
                if st.startswith("|"):
                    cells = table_cells(st)
                    if cells and _STEP_CELL_RE.fullmatch(cells[0]):
                        step = _STEP_NUM_RE.search(cells[0]).group(0)
                elif head_step:
                    step = head_step
                if not step:
                    continue
                for t in _link_targets(md, ln):
                    tid = ids.get(t, "")
                    if tid.startswith("CALL-"):
                        fwd.setdefault((cid, tid), set()).add(step)
        elif typ == "contract-call" and cid.startswith("CALL-"):
            try:
                text = _fs.read_text(md, encoding="utf-8", errors="replace")
            except OSError:
                continue
            sec, on = [], False
            for ln in text.splitlines():
                if ln.startswith("## "):
                    on = bool(_CALL_USAGE_RE.match(ln))
                    continue
                if on:
                    sec.append(ln)
            for ln in sec:
                if not ln.strip().startswith("|"):
                    continue
                cells = table_cells(ln)
                if len(cells) < 2:
                    continue
                for t in _link_targets(md, cells[0]):
                    pid = ids.get(t, "")
                    if pid.startswith("PROC"):
                        steps, cell = back.get((pid, cid), (set(), ""))
                        back[(pid, cid)] = (steps | _step_literals(cells[1]),
                                            (cell + "; " if cell else "") + cells[1])
    rel_of = {cid: rel for _md, (_t, cid, rel) in meta.items() if cid}
    issues: List[str] = []
    for (pid, cid), steps in sorted(fwd.items()):
        st = ", ".join(sorted(steps))
        if (pid, cid) not in back:
            issues.append(f"нет обратной: {pid} шаг {st} → {cid}; в карточке {cid} "
                          f"({rel_of.get(cid, '?')}) нет строки процесса {pid}")
        else:
            bsteps, cell = back[(pid, cid)]
            if bsteps and not (steps & bsteps):
                issues.append(f"номер шага расходится: {pid} шаг {st} → {cid}; "
                              f"в карточке {cid} — «{cell[:40]}»")
    for (pid, cid), (_bs, cell) in sorted(back.items()):
        if (pid, cid) not in fwd:
            issues.append(f"нет прямой: {cid} → {pid} «{cell[:40]}»; в шагах {pid} "
                          f"({rel_of.get(pid, '?')}) нет ссылки на {cid}")
    if not issues:
        return []
    out = [f"⚠ шаг процесса ↔ карточка вызова (шаблоны process и contract-call: шаг "
           f"ссылается на CALL, карточка — на процесс и шаг): расхождений {len(issues)}"]
    out.extend(f"   {x}" for x in issues[:30])
    if len(issues) > 30:
        out.append(f"   … и ещё {len(issues) - 30}")
    return out


def check_id_slots(docs: Path, card_ids: Dict[Path, str]):
    """(отчёт, ok). card_ids: карточка docs -> id из frontmatter."""
    report: List[str] = []
    ok = True

    def seg_of(p: Path) -> Optional[str]:
        parts = p.relative_to(docs).as_posix().split("/")
        if (len(parts) > 2 and parts[0] == "srs"
                and parts[1] not in _KNOWN_TYPES
                and parts[1] not in _LEGACY_TYPE_DIRS):
            return parts[1]
        return None

    def slot_like(cid: str) -> Optional[str]:
        tokens = cid.split("-")
        if len(tokens) >= 3 and _PART_CODE_RE.fullmatch(tokens[1])                 and tokens[1] not in _NOT_SLOT:
            return tokens[1]
        return None

    # слот сервиса (домен): срезается с идентификатора ДО проверки слота
    # части; у сервиса со «Слот: нет» слота сервиса в ID быть не должно
    dom = domain_context(docs)
    svc_code = dom[2][0] if dom is not None and dom[2][1] else None
    orig_ids = dict(card_ids)       # для сообщений — исходный id, не срезанный
    svc_codes = ({c for c, has in dom[1].values() if has}
                 if dom is not None else set())
    if dom is not None:
        stripped: Dict[Path, str] = {}
        for p, cid in sorted(card_ids.items()):
            rel = p.relative_to(docs).as_posix()
            tokens = cid.split("-")
            if svc_code:
                if len(tokens) >= 3 and tokens[1] == svc_code:
                    stripped[p] = "-".join([tokens[0]] + tokens[2:])
                else:
                    ok = False
                    if len(tokens) >= 3 and tokens[1] in svc_codes:
                        what = f"несёт слот «{tokens[1]}»"
                    elif svc_code in tokens[2:]:
                        what = (f"несёт слот «{svc_code}» не на месте "
                                "(слот сервиса стоит сразу после префикса: "
                                f"{tokens[0]}-{svc_code}-…)")
                    else:
                        what = "без слота сервиса"
                    report.append(
                        f"✗ слот сервиса: {rel} — id {cid} {what}, комплект "
                        f"«{docs.name}» объявлен в таблице сервисов домена со "
                        f"слотом «{svc_code}»")
            else:
                if (len(tokens) >= 3 and tokens[1] in svc_codes
                        and tokens[1] not in (_load_part_codes(
                            docs / "README.md") or {})):
                    ok = False
                    report.append(
                        f"✗ слот сервиса: {rel} — id {cid} несёт слот "
                        f"сервиса «{tokens[1]}», а комплект «{docs.name}» "
                        "объявлен в таблице сервисов домена со «Слот: нет»")
                else:
                    stripped[p] = cid
        card_ids = stripped
    codes = _load_part_codes(docs / "README.md")
    if codes is None:
        if svc_code and not any(ln.startswith("✗") for ln in report):
            report.append(f"слот сервиса «{svc_code}»: по таблице сервисов "
                          "корневого README, частей нет ✓")
        # без таблицы сторож молчит, кроме явного признака слота: карточка в
        # каталоге подсервиса с id вида <PREFIX>-<КОД>-… (обычные сервисы и
        # старая раскладка с каталогами типов во множественном числе не задеты)
        hits = sorted((p.relative_to(docs).as_posix(), cid)
                      for p, cid in card_ids.items()
                      if seg_of(p) and slot_like(cid))
        if hits:
            ok = False
            report.append(
                "✗ слот части: идентификаторы со слотом части без таблицы "
                "кодов частей в README корня комплекта (колонки «Код», "
                "«Каталог»; conventions §3.1): "
                + ", ".join(f"{rel} ({orig_ids.get(docs / rel, cid)})" for rel, cid in hits[:5])
                + (" …" if len(hits) > 5 else ""))
        return report, ok
    if not codes:
        ok = False
        report.append(
            "✗ слот части: в таблице кодов частей README нет колонки "
            "«Каталог» — соответствие «слот ↔ каталог» непроверяемо "
            "(conventions §3.1)")
        return report, ok
    dir2code = {folder: code for code, folder in codes.items()}
    for p, cid in sorted(card_ids.items()):
        rel = p.relative_to(docs).as_posix()
        seg = seg_of(p)
        tokens = cid.split("-")
        shown = orig_ids.get(p, cid)
        slot = tokens[1] if len(tokens) >= 3 and tokens[1] in codes else None
        if seg is None:
            if slot is not None:
                ok = False
                report.append(
                    f"✗ слот части: {rel} — id {shown} несёт слот «{slot}», "
                    "а документ лежит вне каталогов подсервисов (уровень "
                    "сервиса / корень srs/ слота не несут)")
            continue
        expected = dir2code.get(seg)
        if expected is None:
            ok = False
            report.append(
                f"✗ слот части: {rel} — каталог «{seg}» не объявлен в "
                "таблице кодов частей README")
        elif slot != expected:
            ok = False
            report.append(
                f"✗ слот части: {rel} — id {shown} "
                + (f"несёт слот «{slot}»" if slot else "без слота")
                + f", каталог «{seg}» объявлен с кодом «{expected}»")
    if not any(ln.startswith("✗") for ln in report):
        report.append(f"слоты частей: {len(codes)} кодов по таблице README, "
                      "соответствие «слот ↔ каталог» выдержано ✓"
                      + (f"; слот сервиса «{svc_code}» ✓" if svc_code else ""))
    return report, ok


# --- сторож условных обозначений README комплекта (2026-10-10) ---
# README комплекта — самоописание: внешние читатели (агенты платформы
# AI Factory по её паспорту ЭКО «Как читать» п. 2) берут из раздела
# «Условные обозначения» контуры, коды частей (таблица «Подсервисы»),
# префиксы ID и идентификатор статусной модели; где README молчит,
# действует их паспорт, а не канон миграции. Сторож держит самоописание
# полным: каждый префикс ID, встречающийся в комплекте, описан; статусная
# модель названа; поля frontmatter объяснены; таблица частей носит имя,
# по которому её ищут. Только ⚠ — действующие комплекты не ломаются;
# без README сторож называет это одним предупреждением.

_LEGEND_HEAD_RE = re.compile(r"^(#+)\s*Условные обозначения.*$", re.M)
_LEGEND_TOKEN_RE = re.compile(r"\*\*([^*\n]{1,40})\*\*|`([A-Z][A-Z0-9-]{0,12})`")
_PREFIX_RE = re.compile(r"^[A-Z]{1,6}$")
_FM_DESCRIBED = ("title", "confluence_page_ids", "version")


def _legend_section(text: str) -> Optional[str]:
    """Текст раздела «Условные обозначения» README (до заголовка того же
    или более высокого уровня); None — раздела нет."""
    m = _LEGEND_HEAD_RE.search(text)
    if not m:
        return None
    level = len(m.group(1))
    body: List[str] = []
    for ln in text[m.end():].splitlines():
        hm = re.match(r"^(#+)\s", ln)
        if hm and len(hm.group(1)) <= level:
            break
        body.append(ln)
    return "\n".join(body)


def _declared_prefixes(section: str) -> set:
    """Префиксы ID, описанные в разделе: жирные ячейки таблиц (`**CTL /
    CTL-GRP**`, `**F-CL / F-BNK**` → CTL, F) и токены в обратных кавычках."""
    out: set = set()
    for m in _LEGEND_TOKEN_RE.finditer(section):
        raw = m.group(1) or m.group(2) or ""
        for tok in re.split(r"\s*[/,]\s*", raw):
            head = tok.strip("` ").split("-")[0]
            if _PREFIX_RE.fullmatch(head):
                out.add(head)
    return out


def check_readme_legend(docs: Path, card_ids: Dict[Path, str]) -> List[str]:
    """⚠-сигналы о неполном самоописании комплекта в README."""
    readme = docs / "README.md"
    if not readme.is_file():
        return ["README комплекта отсутствует — внешние читатели берут "
                "контуры, части и префиксы ID из его раздела «Условные "
                "обозначения» (шаблон docs-readme.md)"]
    text = _fs.read_text(readme, encoding="utf-8", errors="replace")
    section = _legend_section(text)
    if section is None:
        return ["README: нет раздела «Условные обозначения» — контуры, "
                "части, префиксы ID и поля frontmatter комплекта не "
                "объявлены (шаблон docs-readme.md)"]
    report: List[str] = []
    declared = _declared_prefixes(section)
    used: Dict[str, int] = {}
    for cid in card_ids.values():
        head = cid.split("-")[0]
        if _PREFIX_RE.fullmatch(head):
            used[head] = used.get(head, 0) + 1
    missing = sorted(p for p in used if p not in declared)
    if missing:
        report.append(
            "префиксы ID комплекта не описаны в таблице типов: "
            + ", ".join(f"{p} ×{used[p]}" for p in missing))
    sm_missing = sorted(cid for cid in card_ids.values()
                        if cid.startswith("SM-") and cid not in section)
    if sm_missing:
        report.append("идентификатор статусной модели не назван: "
                      + ", ".join(sm_missing))
    fields: set = set()
    for p in card_ids:
        fm = read_frontmatter(p) or {}
        fields.update(f for f in _FM_DESCRIBED if f in fm)
    fm_missing = sorted(f for f in fields if f not in section)
    if fm_missing:
        report.append("поля frontmatter комплекта не описаны (таблица "
                      "«Поля frontmatter»): " + ", ".join(fm_missing))
    pm = _PART_TABLE_HEAD_RE.search(text)
    if pm and "подсервис" not in pm.group(0).lower():
        report.append(f"таблица кодов частей озаглавлена «{pm.group(0).strip('# ')}» "
                      "— внешние читатели ищут её по имени «Подсервисы»")
    return report


# --- структурные сторожа (2026-10-10, решение владельца P-20) ---
# Два свойства комплекта, которых прибор не проверял, а валидатор
# платформы AI Factory блокирует на входе (E_STRUCTURED_FILE_INVALID,
# E_LOCAL_LINK_MISSING): sidecar-примеры JSON/YAML/XML разбираются;
# относительные ссылки в документах ведут на существующие файлы. Замер
# 2026-10-07 на КК: три невалидных JSON-примера (BOM; синтаксис), две
# битые ссылки — гейт миграции их не видел. Сторож обнаруживает, не
# лечит, и разводит причину по источнику: пример испорчен переносом
# (BOM, обрезка, склейка — в источнике тот же текст разбирается или
# пример в источнике не найден) — брак миграции ✗, чинится; пример
# невалиден уже в источнике — дефект аналитики ⚠: файл сохраняется как
# `.txt` с пометкой в карточке и записью в вопросы, не правится.

_STRUCT_EXT = {".json", ".yaml", ".yml", ".xml"}
_BOM = b"\xef\xbb\xbf"
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-.]{7,}")


def _parse_structured(raw: bytes, ext: str) -> Optional[str]:
    """None — разбирается; иначе короткое описание ошибки."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return f"не UTF-8 ({e.reason})"
    try:
        if ext == ".json":
            import json
            json.loads(text)
        elif ext in (".yaml", ".yml"):
            try:
                import yaml  # noqa: WPS433 — есть в окружении прибора
            except ImportError:
                return None  # без PyYAML YAML не проверяем (молчим)
            yaml.safe_load(text)
        elif ext == ".xml":
            import xml.etree.ElementTree as ET
            ET.fromstring(text)
    except Exception as e:  # noqa: BLE001 — любой сбой разбора — находка
        return str(e).splitlines()[0][:120]
    return None


def _source_candidates(text: str) -> List[str]:
    """Фрагменты страницы источника, которые могли быть примером:
    блоки кода и ячейки таблиц (инлайн-код в ячейке склеивается, `<br>`
    — перевод строки)."""
    out = list(_FENCE_RE.findall(text))
    for ln in text.splitlines():
        if ln.lstrip().startswith("|"):
            for cell in ln.strip().strip("|").split("|"):
                c = re.sub(r"<br\s*/?>", "\n", cell)
                c = c.replace("`", "").replace("\\|", "|").strip()
                if len(c) > 10:
                    out.append(c)
    return out


def _struct_tokens(raw: bytes) -> List[str]:
    text = raw.decode("utf-8", errors="replace")
    seen: List[str] = []
    for t in _TOKEN_RE.findall(text):
        if t not in seen and not t.isdigit():
            seen.append(t)
        if len(seen) >= 6:
            break
    return seen


_CARD_ID_HEAD_RE = re.compile(
    r"^\s*\\?\[?(?:CTL-GRP-[\w-]*\d+|CTL-[\w-]*\d+|CALL-[\w-]*\d+|PLT-[\w-]*\d+)\b")


def check_link_anchors_and_ids(docs: Path) -> List[str]:
    """Предупреждения (ПР-06 разбора замечаний ОНБ-В): (1) якорь ссылки
    на md-файл комплекта не совпадает ни с одним заголовком цели по
    правилам GitLab; (2) упоминание конкретной карточки вызова, контроля
    или платформенной функции без ID в тексте ссылки (conventions §5:
    «всегда ID + название»). Навигационные ссылки на файл целиком
    (README, матрица, `platform-functions.md` без якоря) — не упоминание
    карточки."""
    cache: Dict[Path, set] = {}
    bad_anchor: List[Tuple[str, str]] = []
    no_id: List[Tuple[str, str]] = []
    for md in _kit_md(docs):
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        src_nav = md.name.lower() in ("readme.md", "traceability-matrix.md")
        for m in _MD_LINK_RE.finditer(text):
            label, raw_t = m.group(1), m.group(2).strip()
            if "://" in raw_t or raw_t.startswith(("mailto:", "<")):
                continue
            path_part, _, anchor = unquote(raw_t).partition("#")
            path_part = path_part.replace("\\", "/")
            try:
                tgt = (md.parent / path_part).resolve() if path_part else md
            except OSError:
                continue
            if anchor and tgt.suffix.lower() == ".md" and tgt.is_file():
                if anchor.lower() not in _anchors_of(tgt, cache):
                    bad_anchor.append((md.relative_to(docs).as_posix(), raw_t))
            if src_nav:
                continue
            low = path_part.lower()
            name = low.rsplit("/", 1)[-1]
            card_ref = (("/contract-call/" in "/" + low and name.startswith("call-"))
                        or (anchor and "/control/" in "/" + low
                            and anchor.lower().startswith("ctl-"))
                        or (anchor and name == "platform-functions.md"
                            and anchor.lower().startswith("plt-")))
            if card_ref and not _CARD_ID_HEAD_RE.match(label):
                no_id.append((md.relative_to(docs).as_posix(), label[:50]))
    out: List[str] = []
    if bad_anchor:
        out.append(f"⚠ якоря ссылок: {len(bad_anchor)} не совпадают с заголовками цели "
                   "(якорь строится как в GitLab: нижний регистр, без знаков, повторные "
                   "дефисы схлопываются; якорь в стиле GitHub с «--» в GitLab не работает):")
        out.extend(f"   {rel} → {t}" for rel, t in bad_anchor[:15])
        if len(bad_anchor) > 15:
            out.append(f"   … ещё {len(bad_anchor) - 15}")
    if no_id:
        out.append(f"⚠ ссылки на карточку вызова, контроля или платформенной функции "
                   f"без ID в тексте: {len(no_id)} (conventions §5: всегда «ID + название»):")
        out.extend(f"   {rel}: [{lab}]" for rel, lab in no_id[:15])
        if len(no_id) > 15:
            out.append(f"   … ещё {len(no_id) - 15}")
    return out


def check_structured_examples(docs: Path, idx: Dict[str, Path]
                              ) -> Tuple[List[str], bool]:
    """(отчёт, ok). idx: page_id -> файл выгрузки (пусто без источников)."""
    files = sorted(p for p in docs.rglob("*")
                   if p.is_file() and p.suffix.lower() in _STRUCT_EXT)
    if not files:
        return [], True
    owners: Dict[Path, List[Path]] = {}
    for md in _kit_md(docs):
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _ART_LINK_RE.finditer(text):
            tgt = unquote(m.group(1)).split("#", 1)[0].replace("\\", "/")
            if not tgt or "://" in tgt:
                continue
            try:
                rp = (md.parent / Path(tgt)).resolve()
            except OSError:
                continue
            if rp.suffix.lower() in _STRUCT_EXT:
                owners.setdefault(rp, []).append(md)
    rep: List[str] = []
    ok = True
    n_ok = 0
    for f in files:
        rel = f.relative_to(docs).as_posix()
        raw = _fs.read_bytes(f)
        ext = f.suffix.lower()
        if raw.startswith(_BOM):
            ok = False
            rep.append(f"✗ структурный файл {rel}: BOM в начале — брак "
                       "переноса (источник BOM не несёт); снять BOM")
            continue
        err = _parse_structured(raw, ext)
        if err is None:
            n_ok += 1
            continue
        # развод причины по источнику
        cards = owners.get(f.resolve(), [])
        pages: List[Path] = []
        for c in cards:
            for pid in page_ids(read_frontmatter(c) or {}):
                if pid in idx and idx[pid] not in pages:
                    pages.append(idx[pid])
        tokens = _struct_tokens(raw)
        located = None
        src_parses = False
        for pg in pages:
            try:
                ptext = _fs.read_text(pg, encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits = sum(1 for t in tokens if t in ptext)
            if tokens and hits >= max(2, len(tokens) // 2):
                located = pg
                for cand in _source_candidates(ptext):
                    if sum(1 for t in tokens if t in cand) >= 2 and \
                            _parse_structured(cand.encode("utf-8"),
                                              ext) is None:
                        src_parses = True
                        break
                break
        if located is not None and not src_parses:
            rep.append(f"⚠ структурный файл {rel} не разбирается ({err}); "
                       "в источнике пример тоже не разбирается — дефект "
                       "аналитики: сохранить как .txt с пометкой в карточке "
                       "и записью в вопросы, не чинить "
                       f"(источник: {located.name})")
            continue
        ok = False
        why = ("в источнике тот же пример разбирается" if src_parses
               else "в источнике пример не найден" if pages
               else "источника нет")
        rep.append(f"✗ структурный файл {rel} не разбирается ({err}); "
                   f"{why} — брак переноса, чинится по источнику")
    for f in files:
        if f.resolve() not in owners:
            rep.append(f"⚠ структурный файл {f.relative_to(docs).as_posix()} "
                       "без ссылающейся карточки — пример, о котором "
                       "комплект молчит")
    if n_ok and ok:
        rep.insert(0, f"структурные файлы: {n_ok} разбираются ✓")
    return rep, ok


def check_relative_links(docs: Path) -> Tuple[List[str], bool]:
    """Относительные ссылки документов комплекта ведут на существующие
    файлы или каталоги; якоря и внешние адреса не проверяются; блоки кода
    вырезаются (в них ссылки — иллюстрации)."""
    broken: List[Tuple[str, str]] = []
    total = 0
    for md in _kit_md(docs):
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        for m in _MD_LINK_RE.finditer(text):
            raw_t = m.group(2).strip()
            if not raw_t or raw_t.startswith("#") or "://" in raw_t \
                    or raw_t.startswith(("mailto:", "<")):
                continue
            tgt = unquote(raw_t).split("#", 1)[0].replace("\\", "/")
            if not tgt:
                continue
            total += 1
            try:
                rp = (md.parent / Path(tgt)).resolve()
            except OSError:
                broken.append((md.relative_to(docs).as_posix(), raw_t))
                continue
            if not rp.exists():
                broken.append((md.relative_to(docs).as_posix(), raw_t))
    if not broken:
        return ([f"относительные ссылки: {total} ведут на существующие "
                 "файлы ✓"] if total else []), True
    rep = [f"✗ битые относительные ссылки: {len(broken)} из {total} "
           "(цели нет — читатель и агент теряют переход):"]
    rep.extend(f"   {rel} → {tgt}" for rel, tgt in broken[:20])
    if len(broken) > 20:
        rep.append(f"   … ещё {len(broken) - 20}")
    return rep, False


# --- сторож среза канона (П-5b, 2026-08-27) ---
# Профиль src-репозитория несёт строку «срез канона: <hash>» — источник
# истины о том, на каком каноне должен работать стенд. selfcheck знает
# свой фактический HEAD (он лежит в каноне) и сверяет сам: промпты
# заходов хэш не носят (дважды за пилот он устаревал между генерацией
# и запуском); обновление строки — осознанное действие владельца при
# приёмке правки канона, а забытое обновление — громкий ✗, не
# молчаливая работа на старом срезе. Без строки сторож молчит (мягкое
# включение, как у сторожа разметки). Dev-копия selfcheck вне канона
# (analyzer) или недоступный git — ⚠, не ✗.

_CANON_CUT_RE = re.compile(r"срез\s+канона\D{0,40}?([0-9a-f]{7,40})",
                           re.I)


def canon_head() -> Optional[str]:
    """Фактический HEAD репозитория, из которого запущен selfcheck;
    None — dev-копия вне канона или git недоступен."""
    tool_dir = Path(__file__).resolve().parent
    if tool_dir.name != "tools" or tool_dir.parent.name != "_meta":
        return None
    root = tool_dir.parent.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


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
        return [], True
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


# --- сторож каталога сервисов (2026-09-29) ---
# Каталог `_meta/services.json` — единственный дом адресации чужих
# сервисов (документ cross-service-addressing): по `code` ищут запись,
# по `repo` строят абсолютные ссылки на чужие комплекты. За один день
# 29.09 каталог правили три команды: поле repo в формате
# `…/-/tree/master/…?ref_type=heads` вместо `/-/tree/HEAD/…`,
# переименование кода (ломает `service:` во frontmatter комплекта и
# чужие ссылки), давний дубль кода EPR у двух записей. Прибор каталог не
# читал вовсе. Сторож: целостность каталога — ⚠-строки уровня отчёта
# (вердикт команды не трогают: каталог чинит владелец канона, а не
# команда, но сигнал виден в каждом отчёте); код документируемого
# сервиса (`service:` во frontmatter) не найден в каталоге — тоже ⚠
# (решение о переводе в ✗ — после приведения frontmatter пилота КК к
# коду каталога). Без каталога (dev-копия selfcheck вне канона и без
# --catalog) сторож молчит.

_REPO_HOST = "https://gitlab.gboteam.ru/"
_REPO_TREE_RE = re.compile(r"/-/(tree|blob|raw)/([^/?#]+)")


def catalog_codes() -> Optional[set]:
    """Коды сервисов каталога канона для сторожа владельцев долгов
    (link_debts); None — каталог недоступен (dev-копия вне канона)."""
    cat = canon_catalog_path()
    if cat is None:
        return None
    try:
        data = json.loads(_fs.read_text(cat, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {s.get("code") for s in data if isinstance(s, dict) and s.get("code")}


_H1_QUOTED_RE = re.compile(r'«[^»\n]*»|"[^"\n]*"|“[^”\n]*”')


def _service_names(code: str, catalog: Optional[Path]) -> List[str]:
    """Названия сервиса для поиска в H1: `code` и `name` каталога без тега."""
    names = [code]
    if catalog is not None:
        try:
            data = json.loads(_fs.read_text(catalog, encoding="utf-8-sig"))
        except (OSError, ValueError):
            data = []
        for rec in data if isinstance(data, list) else []:
            if isinstance(rec, dict) and rec.get("code") == code and rec.get("name"):
                names.append(re.sub(r"^\[[^\]]*\]\s*", "", rec["name"]).strip())
    return [n for n in names if n and len(n) > 3]


def check_h1_service(docs: Path, catalog: Optional[Path]) -> List[str]:
    """⚠: H1 документа содержит название сервиса (conventions §5 — сервис
    задают поле `service` и путь комплекта). Название внутри кавычек —
    часть дословного названия артефакта из источника, не приписка.
    Исключения: README корня комплекта, доменный глоссарий и концепция
    домена (у них H1 называет домен)."""
    hits: List[str] = []
    for md in _kit_md(docs):
        if md.parent == docs and md.name.lower() == "readme.md":
            continue
        fm = read_frontmatter(md) or {}
        typ = str(fm.get("type", "")).strip("'\"")
        if typ == "domain-vision" or (typ == "glossary" and fm.get("domain")):
            continue
        code = str(fm.get("service", "")).strip("'\"")
        if not code:
            continue
        try:
            lines = _fs.read_text(md, encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        h1 = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), "")
        if not h1:
            continue
        bare = _H1_QUOTED_RE.sub(" ", re.sub(r"\[[^\]]*\]", " ", h1)).lower()
        for nm in _service_names(code, catalog):
            if re.search(r"(?<![\w-])" + re.escape(nm.lower()) + r"(?![\w-])", bare):
                hits.append(f"{md.relative_to(docs).as_posix()}: «{h1[:70]}»")
                break
    if not hits:
        return []
    out = [f"⚠ H1 с названием сервиса (conventions §5: сервис задают поле service и путь "
           f"комплекта, H1 — название артефакта): файлов {len(hits)}"]
    out.extend(f"   {h}" for h in hits[:30])
    if len(hits) > 30:
        out.append(f"   … и ещё {len(hits) - 30}")
    return out


def canon_catalog_path() -> Optional[Path]:
    """`_meta/services.json` канона, из которого запущен selfcheck;
    None — dev-копия вне канона."""
    tool_dir = Path(__file__).resolve().parent
    if tool_dir.name != "tools" or tool_dir.parent.name != "_meta":
        return None
    cat = tool_dir.parent / "services.json"
    return cat if cat.is_file() else None


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


# --- сторожа протокольной дисциплины (П-5c, 2026-08-28) ---
# Замер «слабый исполнитель × компактный промпт» (ISS-02): модель
# написала генерирующий скрипт и сделала третий retry — оба прямых
# запрета протокола (§3, §6) потерялись из её внимания за два часа
# работы. Правило и образец есть — не было сторожа; закон обходов:
# ненаблюдаемое правило со временем нарушается любым исполнителем,
# вопрос лишь ёмкости. Мягкое включение: только на протокольном
# стенде (в профиле есть строка «срез канона»). confluence/ исключён
# из скана — это данные источника, не рабочие файлы исполнителя.

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
# План обязан иметь промпт-файл prompts/<ЭТАП>.md на КАЖДЫЙ этап
# (план-промпт v2.2 п.10); неполный пакет промптов обнаруживался
# только внимательностью приёмщика (кейс: «дособери с ISS-02 и далее»
# прочитано планировщиком как «без COM-03+»). Сторож делает неполноту
# видимой на каждом прогоне. Мягкое включение: активен только при
# строке «план миграции: <файл>» в профиле источников; этапы, чьи
# отчёты уже лежат в sandbox/ (selfcheck-<ЭТАП>*.txt), считаются
# выполненными — промпт для них не требуется. Информационный гейт:
# вердикт не трогает (неполнота пакета — не дефект комплекта docs).

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


# --- сторожа П-5d (2026-08-28) ---
# 1) Имя журнала: §4 фиксирует sandbox/journal.txt — самодельные имена
#    расщепляют историю стенда (два живых случая: selfcheck-journal.md
#    у слабого исполнителя d05b, дрейф имён первой редакции COM-01).
#    Замечание владельца лечит один прогон — сторож лечит класс.
# 2) Дубли реестровых ID: два CTL-000 прошли мимо всех гейтов (d01
#    ISS-02). Сторож — по секции «Реестр ID» матрицы: строки покрытия
#    легально повторяют ID и не проверяются.

def check_journal_name(journal: Path,
                       sources: Path) -> Optional[str]:
    """Строка-✗, если журнал прогона не sandbox/journal.txt стенда."""
    expected = _stand_root(sources) / "sandbox" / "journal.txt"
    if journal.resolve() == expected:
        return None
    return (f"✗ протокол §4: журнал прогона «{journal}» — единый журнал "
            "стенда ФИКСИРОВАН: sandbox/journal.txt; самодельные имена "
            "расщепляют историю (запись выполнена, но прогон "
            "аннулирован — повтори с правильным журналом)")


_REGISTRY_HDR_RE = re.compile(r"^#+\s*(?:\d+\.\s*)?Реестр\s+ID",
                              re.I | re.M)


def check_registry_duplicates(matrix_path: Path) -> Tuple[List[str], bool]:
    """Дубли ID в секции «Реестр ID» матрицы — ✗ (реестровый ID
    уникален; кейс: два CTL-000 у общего и подсервисного README)."""
    try:
        text = _fs.read_text(matrix_path, encoding="utf-8", errors="replace")
    except OSError:
        return [], True
    m = _REGISTRY_HDR_RE.search(text)
    if not m:
        return [], True
    sect = text[m.end():]
    nxt = re.search(r"^#+\s", sect, re.M)
    if nxt:
        sect = sect[:nxt.start()]
    seen: Dict[str, str] = {}
    report: List[str] = []
    ok = True
    for ln in sect.splitlines():
        cells = table_cells(ln)
        if len(cells) < 2 or not re.match(r"^[A-ZА-Я]{2,}[-\w]*\d$",
                                          cells[0]):
            continue
        rid = cells[0]
        if rid in seen:
            ok = False
            report.append(f"✗ реестр ID: дубль {rid} в «Реестре ID» "
                          f"матрицы — реестровый ID уникален "
                          f"(строки: «{seen[rid][:60]}» и "
                          f"«{ln.strip()[:60]}»)")
        else:
            seen[rid] = ln.strip()
    return report, ok


# --- детектор похожих точек применения групп (П-5e, 2026-08-28) ---
# Механический перенос «страница × группа → GRP» размножает одну точку
# применения, описанную разными страницами с разных сторон (живой кейс:
# три группы «Подписать и отправить» GRP-7/9/16 в cc-card-issue нашёл
# вопрос владельца, не прибор). Детектор — НЕ решатель: пары групп
# одного реестра с общим цитируемым литералом (кнопка «…», статус
# `…`) поднимаются i-строкой; решение «слить/различить как фазы» —
# только человеческое (шаг консолидации этапа). Скоуп — ОДИН реестровый
# README: совпадение кнопок между подсервисами — разные ЭФ, не дубль.

_GRP_ROW_RE = re.compile(r"^\|\s*\[?(CTL-GRP-\d+)\]?[^|]*\|\s*([^|]+)")
# формат с колонкой «Контур» (полигон 2026-08-29): | ID | FE/BE | Привязка |
_GRP_ROW_C_RE = re.compile(
    r"^\|\s*\[?(CTL-GRP-\d+)\]?[^|]*\|\s*(FE|BE)\s*\|\s*([^|]+)")
_QUOTE_TOKEN_RE = re.compile(r"«([^»]{3,60})»|`([A-Za-z_]{3,30})`")

_UI_MARK_RE = re.compile(
    r"кнопк|нажат|\bэф\b|экранн|вкладк|дровер|фокус", re.I)
_ST_MARK_RE = re.compile(r"статус|переход", re.I)
_OP_MARK_RE = re.compile(r"при выполнении|функц", re.I)


_ART_LINK_RE = re.compile(r"\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")


def check_file_artifacts(docs: Path) -> Tuple[List[str], bool]:
    """Сторож не-markdown артефактов комплекта (files/): приложение
    источника (XSD/JSON-схема и т.п.) живёт в подкаталоге files/ рядом
    с карточкой-владельцем, и карточка ОБЯЗАНА на него ссылаться.
    Файл в files/ без входящей ссылки — «сирота» (✗): артефакт, о
    котором комплект молчит. Ссылка карточки в files/ на несуществующий
    файл — тоже ✗ (потеря артефакта). Каталоги img/ — вне сторожа:
    перенос картинок — отдельная существующая конвенция."""
    arts = {p.resolve() for p in docs.rglob("*")
            if p.is_file() and "files" in p.relative_to(docs).parts
            and "img" not in p.relative_to(docs).parts}
    linked: set = set()
    broken: List[Tuple[str, str]] = []
    for md in _kit_md(docs):
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _ART_LINK_RE.finditer(text):
            tgt = unquote(m.group(1)).split("#", 1)[0]
            if not tgt or "://" in tgt or tgt.startswith("mailto:"):
                continue
            norm_t = tgt.replace("\\", "/")
            if "files/" not in norm_t and not norm_t.startswith("files/"):
                continue
            try:
                rp = (md.parent / Path(norm_t)).resolve()
            except OSError:
                continue
            if rp.is_file():
                linked.add(rp)
            else:
                broken.append((md.relative_to(docs).as_posix(), tgt))
    rep: List[str] = []
    ok = True
    for a in sorted(arts - linked):
        ok = False
        rep.append("✗ файл-артефакт без ссылающейся карточки (сирота "
                   "files/): "
                   + Path(a).relative_to(docs.resolve()).as_posix()
                   + " — артефакт, о котором комплект молчит")
    for rel, tgt in broken:
        ok = False
        rep.append(f"✗ битая ссылка на files-артефакт: {rel} → {tgt} "
                   "(файла нет — потеря артефакта)")
    return rep, ok


def check_group_contours(docs: Path) -> List[str]:
    """Согласованность контура групп контролей (решение владельца
    2026-08-29): контур — явная колонка FE/BE реестра групп, сторож
    сверяет её с формулировкой привязки. FE привязывается к UI-событию;
    BE — к переходу статусной модели или серверной операции, БЕЗ
    UI-мест (сервер не знает, откуда пришёл запрос, — API First;
    перечни триггеров заведомо неполны). Неоднозначность не угадывается
    — ⚠-вопрос аналитику (асимметрия). Реестр без колонки «Контур» —
    один ⚠ на файл (разметить при перегонке)."""
    report: List[str] = []
    for readme in sorted(docs.rglob("control/README.md")):
        try:
            text = _fs.read_text(readme, encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = readme.relative_to(docs)
        has_rows = any(_GRP_ROW_RE.match(ln.strip())
                       for ln in text.splitlines())
        if not has_rows:
            continue
        header_ok = re.search(r"^\|\s*ID\s*\|\s*Контур\s*\|", text, re.M)
        if not header_ok:
            report.append(
                f"⚠ {rel}: реестр групп без колонки «Контур» (FE/BE) — "
                "разметить при перегонке групп (шаблон controls §2, "
                "решение 2026-08-29)")
            continue
        for ln in text.splitlines():
            m = _GRP_ROW_C_RE.match(ln.strip())
            if not m:
                continue
            gid, contour, bind = m.group(1), m.group(2), m.group(3)
            ui = bool(_UI_MARK_RE.search(bind))
            st = bool(_ST_MARK_RE.search(bind))
            op = bool(_OP_MARK_RE.search(bind))
            if contour == "FE":
                if st:
                    report.append(
                        f"⚠ {rel}: {gid} (FE) — привязка содержит "
                        "статусные маркеры: контур/привязка ошибочны "
                        "либо событие двух контуров — расщепить на "
                        "FE- и BE-группы")
                elif not ui:
                    report.append(
                        f"⚠ {rel}: {gid} (FE) — привязка не называет "
                        "UI-событие; контур неопределим по формулировке "
                        "— вопрос аналитику")
            else:
                if ui:
                    report.append(
                        f"⚠ {rel}: {gid} (BE) — привязка содержит "
                        "UI-маркеры: сервер не знает мест инициирования "
                        "(API First) — убрать UI-места либо пересмотреть "
                        "контур")
                elif not (st or op):
                    report.append(
                        f"⚠ {rel}: {gid} (BE) — привязка не называет ни "
                        "переход статуса, ни серверную операцию — "
                        "неопределима, вопрос аналитику")
    return report


def check_bare_entity_mentions(docs: Path) -> List[str]:
    """Голые атрибутные обращения «Название.<Атрибут>» к сущностям
    реестра ID без ссылки на карточку (решение владельца 2026-08-29,
    README SCR-CL-01: «Клиент Банка.<Краткое наименование>» голым
    текстом при существующей EXT-002 в комплекте).

    Матчинг — по НАИМЕНОВАНИЯМ реестра ID матрицы, не по тегам [XX]:
    теги в титулах Confluence — частая рекомендация, не требование
    (платформенные страницы почти без них), теговый сторож упоминаний
    этот класс не видит. Флагается только обращение к атрибуту
    («Название.<…>») — место, где ссылка на модель данных обязательна;
    прочие голые упоминания имён не флагаются (шум: имена встречаются
    в каждом абзаце). ⚠-сигнал, вердикт не трогает — оформление ссылок
    закрывается дозаходом."""
    matrix = docs / "traceability-matrix.md"
    if not matrix.exists():
        return []
    text = _fs.read_text(matrix, encoding="utf-8", errors="replace")
    m = re.search(r"^#{1,3}\s.*Реестр ID\s*$", text, re.M)
    names: dict = {}
    for ln in (text[m.end():] if m else "").splitlines():
        cells = table_cells(ln)
        if len(cells) < 3 or not re.fullmatch(r"[A-Z]+-[\w.]+", cells[0]):
            continue
        name = re.sub(r"^\[[^\]]+\]\s*", "", cells[1]).strip()
        # короткие/односложные имена — шум («Фильтр», «Заявка»)
        if len(name) >= 10 and " " in name:
            names[name.lower()] = cells[0]
    if not names:
        return []
    report: List[str] = []
    for p in _kit_md(docs):
        if p == matrix:
            continue
        body = _fs.read_text(p, encoding="utf-8", errors="replace")
        # ссылки вырезаются целиком: ярлык со ссылкой — оформлено верно
        bare = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", body)
        hits: dict = {}
        for am in re.finditer(r"([^\n<>|]{3,80}?)\.<", bare):
            cand = am.group(1).strip().lower()
            for name, rid in names.items():
                if cand.endswith(name):
                    hits[name] = hits.get(name, 0) + 1
                    break
        for name, cnt in sorted(hits.items()):
            report.append(
                f"⚠ {p.relative_to(docs)}: голое обращение "
                f"«{name}.<…>» ×{cnt} — карточка {names[name]} есть в "
                "реестре, обращение к атрибуту оформляется ссылкой")
    return report


# --- сторож ссылок-названий на сущности (решение владельца 2026-10-02) ---
# Конвенции §5: первое упоминание сущности в документе — полная ссылка
# `[ENT-NNN <название>](…)`; повторное в прозе — короткой ссылкой
# `[ENT-NNN](…)` ЛИБО ссылкой с названием без ID
# `[Заявке на выпуск карты](…/ent-016-….md)` (читаемость прозы; текст
# ссылки свободный — слова в падеже предложения, совпадение с названием
# не требуется и не проверяется: морфологии в приборе нет). Обращения к
# атрибутам, формулы и таблицы связей — по-прежнему короткой ссылкой.
# Инвариант, который держит сторож: у ссылки-названия в ТОМ ЖЕ документе
# есть полная ссылка с ID на ту же цель, и она стоит раньше — иначе
# идентификатор сущности в видимом тексте документа не встречается ни
# разу. ID сущности берётся из имени файла цели (`ent-016-…`,
# `ent-shr-012-…`), поэтому правило действует только для ENT: у EXT цель
# общая (`dictionaries.md`), ID в адресе нет — там повторное упоминание
# только с ID. Документ со старой формой (одни короткие ссылки) сторож
# не трогает. Дословное наименование источника С ТЕГОМ сервиса
# (`[[КК_ВК] Заявка на выпуск карты](…)`) считается полноценным
# упоминанием наравне с полной ссылкой: тег с названием однозначно
# определяет сущность, а дословность reverse-переноса запрещает
# вставлять в текст источника ID (живой прогон 2026-10-02: на стенде
# КК ~540 таких ссылок в 65 принятых документах — первая редакция
# сторожа флаговала их все). ⚠-сигнал, вердикт не меняет —
# оформление ссылок, как у сторожа голых обращений.

_ENT_FILE_RE = re.compile(r"^(ent(?:-[a-z]{1,4})?-\d+(?:\.\d+)?)[-.]", re.I)
_NAMED_LINK_SKIP = {"readme.md", "dictionaries.md"} | _SERVICE_FILES
# тег сервиса в начале текста ссылки, экранированный или нет:
# `\[КК_ВК\] Название` / `[КК_ВК] Название`
_TAGGED_NAME_RE = re.compile(r"^\\?\[[^\[\]\\\n]{2,14}\\?\]\s*\S")


def check_named_entity_links(docs: Path) -> List[str]:
    """Ссылки на сущности ENT названием без ID: в документе должна быть
    более ранняя полная ссылка `[ENT-NNN <название>]` на ту же цель либо
    ссылка с дословным наименованием источника с тегом сервиса."""
    report: List[str] = []
    for p in _kit_md(docs):
        if p.name.lower() in _NAMED_LINK_SKIP:
            continue
        body = _fs.read_text(p, encoding="utf-8", errors="replace")
        body = re.sub(r"```.*?```", " ", body, flags=re.S)   # примеры кода
        first_full: Dict[str, int] = {}
        named: Dict[str, List[int]] = {}
        for m in _MD_LINK_RE.finditer(body):
            text, target = m.group(1).strip(), m.group(2)
            fname = unquote(target.split("#", 1)[0]).replace("\\", "/")
            fname = fname.rsplit("/", 1)[-1]
            fm = _ENT_FILE_RE.match(fname)
            if not fm or fname.lower() == p.name.lower():
                continue
            ent_id = fm.group(1).upper()
            if text.lower().endswith(".md"):       # ссылка именем файла
                continue
            if re.search(rf"(?<![\w-]){re.escape(ent_id)}(?![\w-])", text):
                rest = re.sub(re.escape(ent_id), "", text)
                if len(re.sub(r"[\W_]+", "", rest)) >= 3:
                    first_full.setdefault(ent_id, m.start())
            elif _TAGGED_NAME_RE.match(text):
                # дословное имя источника с тегом — полноценное упоминание
                first_full.setdefault(ent_id, m.start())
            else:
                named.setdefault(ent_id, []).append(m.start())
        rel = p.relative_to(docs)
        for ent_id, poss in sorted(named.items()):
            if ent_id not in first_full:
                report.append(
                    f"⚠ {rel}: ссылка на {ent_id} названием без ID "
                    f"×{len(poss)}, а полной ссылки `[{ent_id} <название>]` "
                    "(или дословного наименования источника с тегом) в "
                    "документе нет — первое упоминание сущности "
                    "оформляется полной ссылкой с ID")
            elif poss[0] < first_full[ent_id]:
                report.append(
                    f"⚠ {rel}: ссылка на {ent_id} названием без ID стоит "
                    f"раньше полной ссылки `[{ent_id} <название>]` — "
                    "полная ссылка с ID ставится при первом упоминании")
    return report


def check_similar_group_points(docs: Path) -> List[str]:
    """i-строки о парах групп с общим цитируемым литералом точки."""
    report: List[str] = []
    for readme in sorted(docs.rglob("control/README.md")):
        try:
            text = _fs.read_text(readme, encoding="utf-8", errors="replace")
        except OSError:
            continue
        toks: Dict[str, List[Tuple[str, str]]] = {}
        for ln in text.splitlines():
            # формат с колонкой «Контур»: описание привязки — третья
            # колонка; без неё — вторая (старый формат)
            mc = _GRP_ROW_C_RE.match(ln.strip())
            m = mc or _GRP_ROW_RE.match(ln.strip())
            if not m:
                continue
            gid = m.group(1)
            desc = (m.group(3) if mc else m.group(2)).strip()
            for qm in _QUOTE_TOKEN_RE.finditer(desc):
                tok = (qm.group(1) or qm.group(2)).strip().lower()
                toks.setdefault(tok, []).append((gid, desc[:50]))
        rel = readme.relative_to(docs)
        for tok, grps in sorted(toks.items()):
            ids = sorted({g for g, _ in grps})
            if len(ids) > 1:
                report.append(
                    f"i похожие точки применения [{rel}]: "
                    f"{' ↔ '.join(ids)} — общий литерал «{tok}»; "
                    "кандидат на консолидацию (решение владельца, "
                    "шаг консолидации этапа)")
    return report


# --- дельта против базлайна (протокол сдачи, 2026-08-19) ---
#
# «Монотонно падать» — неверный инвариант: честный рост находок бывает
# (снятие маскировки/починка frontmatter раскрывает скрытое — пилот-3:
# возврат тегов добавил ⚠). Верный инвариант сдачи: каждый ✗ на момент
# сдачи погашен или объяснён блокером, НОВЫЕ ✗ квалифицированы
# (раскрытие в зоне правок либо ПОРЧА вне зоны = брак дозахода —
# авария достройки 5.5: правки функций ломали prc-файлы молча).
# Протокол: старт дозахода — «--out sandbox/baseline.txt», сдача —
# «--baseline sandbox/baseline.txt», дельта-блок в сдаче дословно.

_MARKS = ("✓", "✗", "⚠")


def _verdict_map(lines) -> Dict[str, str]:
    """вердикт по единице отчёта: файл (в группах «a.md, b.md ← src» —
    каждый) или комплект-уровневый гейт (текст до двоеточия)."""
    out: Dict[str, str] = {}
    for ln in lines:
        s = ln.strip()
        if not s or s[0] not in _MARKS:
            continue
        mark, rest = s[0], s[1:].strip()
        rest = rest.split(" ← ")[0].split(":")[0].strip()
        for name in rest.split(", "):
            if name:
                out[name] = mark
    return out


def delta_report(baseline_path: Path, cur_lines: List[str]) -> List[str]:
    try:
        raw = _fs.read_text(baseline_path, encoding="utf-8", errors="replace")
    except OSError as e:
        return [f"i дельта: базлайн не прочитан ({e!r}) — сравнение "
                "пропущено"]
    base = _verdict_map(ln.lstrip("# ").rstrip()
                        for ln in raw.splitlines())
    cur = _verdict_map(cur_lines)
    n_base = sum(1 for v in base.values() if v == "✗")
    n_cur = sum(1 for v in cur.values() if v == "✗")
    closed = sorted(k for k, v in cur.items()
                    if v != "✗" and base.get(k) == "✗")
    opened = sorted(k for k, v in cur.items()
                    if v == "✗" and base.get(k) != "✗")
    out = [f"дельта против базлайна {baseline_path.name}: "
           f"✗ было {n_base} → стало {n_cur}",
           # замечание координатора КК 2026-10-05: «дельта на единицу
           # больше ИТОГО» читалась дефектом прибора
           "   (в счёт дельты входят и ✗ сторожей уровня комплекта — "
           "долги ссылок, срез канона, реестр матрицы и подобные, — "
           "поэтому число может быть больше ✗ в ИТОГО, где считаются "
           "только файлы)"]
    if closed:
        out.append(f"   закрыто ✗→✓ ×{len(closed)}: "
                   + ", ".join(closed[:10]))
    if opened:
        out.append(f"   НОВЫЕ ✗ ×{len(opened)}: " + ", ".join(opened[:10])
                   + " — каждый квалифицировать в сдаче: раскрытие в "
                   "зоне правок (в работу или блокер) либо ПОРЧА вне "
                   "зоны правок (брак дозахода)")
    if not closed and not opened:
        out.append("   изменений вердиктов нет")
    # FB-02 lk-mp (2026-10-09): «✗ было 0 → стало 0» читалось как «ничего
    # не сделано» — дельта сравнивает ВЕРДИКТЫ, не содержание; строка
    # состава показывает, что единицы отчёта прибавились/убыли; изменение
    # внутри уже существовавших файлов — по строке «изменены:» журнала
    # гейта (sandbox/journal.txt) и git-скоупу сдачи
    added = sorted(k for k in cur if k not in base)
    gone = sorted(k for k in base if k not in cur)
    comp = (f"   состав: единиц в отчёте было {len(base)} → стало {len(cur)}"
            + (f"; новых ×{len(added)}: " + ", ".join(added[:6])
               + (" …" if len(added) > 6 else "") if added else "")
            + (f"; исчезло ×{len(gone)}: " + ", ".join(gone[:6])
               + (" …" if len(gone) > 6 else "") if gone else ""))
    out.append(comp + " (дельта сравнивает вердикты; изменения внутри "
               "прежних файлов — строка «изменены:» журнала гейта)")
    return out


def main() -> int:
    # Windows-консоль cp1251 падает на ✓/✗ — печатаем с заменой, файл
    # отчёта (--out) всегда полный UTF-8 (три самодельных лаунчера
    # агентов решали ровно эту проблему — теперь она решена утилитой).
    # До argparse: текст --help тоже содержит «✗» и падал до перестройки.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Единый диспетчер самопроверки комплекта: сам находит "
                    "карточки, сопоставляет источники по confluence_page_id "
                    "и гоняет связку проверок нормализатора; код 2 при "
                    "браке. Read-only.")
    ap.add_argument("--docs", type=Path, required=True,
                    help="корень docs/ комплекта")
    ap.add_argument("--sources", type=Path, default=None,
                    help="каталог выгрузки Confluence (reverse); без него "
                         "выполняются только внутренние сторожа карточек")
    ap.add_argument("--out", type=Path, default=None,
                    help="записать полный отчёт в файл (UTF-8) — вместо "
                         "самодельных лаунчеров и shell-редиректов "
                         "(PowerShell `>` пишет UTF-16)")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="сравнить вердикты с ранее сохранённым отчётом "
                         "(--out в начале дозахода): дельта закрытых и "
                         "НОВЫХ ✗ — блок обязателен в сдаче")
    ap.add_argument("--strict", action="store_true",
                    help="полный профиль (держатели канона): маркеры "
                         "сокращения — брак; без флага — командный "
                         "профиль, маркеры — предупреждение (Р-8)")
    ap.add_argument("--catalog", type=Path, default=None,
                    help="каталог сервисов services.json для сторожа "
                         "каталога; по умолчанию — _meta/services.json "
                         "канона, из которого запущен selfcheck")
    ap.add_argument("--journal", type=Path, default=None,
                    help="дописать строку «таймстемп | ИТОГО…» в файл "
                         "журнала (хронометраж этапов дозахода: время "
                         "штампует прибор, не исполнитель — у LLM нет "
                         "часов, самодельные таймстемпы фабрикуются)")
    args = ap.parse_args()
    report, ok = run(args.docs, args.sources, strict=args.strict,
                     catalog=args.catalog)
    if args.journal is not None and args.sources is not None:
        jwarn = check_journal_name(args.journal, args.sources)
        if jwarn:
            report.append(jwarn)
            ok = False
    if args.baseline is not None:
        report.extend(delta_report(args.baseline, report))
    if args.journal is not None:
        import json
        from datetime import datetime
        itogo = next((ln for ln in report if ln.startswith("ИТОГО")),
                     "ИТОГО: ?")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # изменённые с ПРОШЛОГО прогона файлы (mtime-скан docs):
            # интервал журнала и его содержимое — в одной строке,
            # повторные правки одного файла видны по-прогонно (вопрос
            # аналитика о соотнесении тихих интервалов с шагами)
            state_p = args.journal.with_suffix(
                args.journal.suffix + ".state")
            cur_mt = {str(p.relative_to(args.docs)):
                      round(p.stat().st_mtime, 2)
                      for p in sorted(args.docs.rglob("*.md"))}
            try:
                prev_mt = json.loads(_fs.read_text(state_p, encoding="utf-8"))
            except (OSError, ValueError):
                prev_mt = None
            if prev_mt is None:
                changed_note = "первый прогон (точка отсчёта)"
            else:
                changed = sorted(f for f, mt in cur_mt.items()
                                 if prev_mt.get(f) != mt)
                changed_note = ("изменены: " + ", ".join(changed[:12])
                                + (f" (+{len(changed) - 12})"
                                   if len(changed) > 12 else "")
                                if changed else "изменений файлов нет")
            args.journal.parent.mkdir(parents=True, exist_ok=True)
            with open(args.journal, "a", encoding="utf-8") as jf:
                jf.write(f"{stamp} | {itogo} | {changed_note}\n")
            state_p.write_text(json.dumps(cur_mt, ensure_ascii=False),
                               encoding="utf-8")
        except OSError as e:
            report.append(f"i журнал не записан: {e!r}")
    lines = [f"# {ln}" for ln in report]
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for ln in lines:
        print(ln)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
