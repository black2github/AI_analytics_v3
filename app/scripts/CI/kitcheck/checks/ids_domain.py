# app/scripts/CI/kitcheck/checks/ids_domain.py
"""Проверки selfcheck: ids_domain — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
import re
try:
    from kitcheck import fs as _fs
    from kitcheck.md import read_frontmatter
    from kitcheck.md import table_cells
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import read_frontmatter  # type: ignore
    from ..md import table_cells  # type: ignore
from ._common import (  # noqa: F401
    _KNOWN_TYPES, _PART_CODE_RE, domain_context)


_PART_TABLE_HEAD_RE = re.compile(
    r"^#+\s*.*(?:слот|подсервис|част[иь] сервиса|коды частей).*$", re.I | re.M)


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
