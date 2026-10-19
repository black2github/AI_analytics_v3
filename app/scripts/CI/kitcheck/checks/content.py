# app/scripts/CI/kitcheck/checks/content.py
"""Проверки selfcheck: content — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
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
    from kitcheck.md import code_line_flags
    from kitcheck.md import frontmatter_end
    from kitcheck.md import read_frontmatter
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md  # type: ignore
    from ..md import code_line_flags  # type: ignore
    from ..md import frontmatter_end  # type: ignore
    from ..md import read_frontmatter  # type: ignore


# Схема шапки (техбук conventions §5, «Состав полей шапки — закрытый по типу
# документа»): общие поля + поля отдельных типов. Пакет 2 задача 6 / ПР-04.
_FM_COMMON = frozenset({"id", "type", "service", "title", "confluence_page_ids"})


_FM_BY_TYPE = {
    "kind": {"function"},
    "entity": {"control"},
    "partOf": None,  # файл-часть многофайлового документа любого типа
    "origin": {"feature", "use-case", "business-rules", "vision"},
    # волна 5 ОНБ-В (техбук `85db9fd`): документы уровня домена — концепция домена
    # (в шаблоне канона `type: domain-vision`) и доменный glossary; nfr; постановка
    "domain": {"domain-vision", "glossary", "vision"},
    "nfr_type": {"nfr"},
    "ingress": {"nfr"},
    "created": {"task"},
}


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
            has_version = True  # ни у одного типа (conventions §5, волна 5)
            continue
        allowed = _FM_BY_TYPE.get(k, set())
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
        # шапка — общая граница (BOM снимается; незакрытая шапка не прячет
        # файл: прежде его строки молча пропускались до конца)
        body_from = frontmatter_end(lines)
        code = [False] * body_from + code_line_flags(lines[body_from:])
        for i, ln in enumerate(lines, 1):
            st = ln.strip()
            if i <= body_from or code[i - 1]:
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
    lines = text.splitlines()
    # заголовок образца в блоке кода — не раздел карточки (вложенный
    # образец ````markdown с ``` внутри — тоже код целиком)
    for ln, in_code in zip(lines, code_line_flags(lines)):
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
