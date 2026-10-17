# app/scripts/CI/kitcheck/checks/links.py
"""Проверки selfcheck: links — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
from urllib.parse import unquote
import re
try:
    from kitcheck.md import _MD_LINK_RE
    from kitcheck.md import _anchors_of
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md
    from kitcheck.md import is_fence
    from kitcheck.md import read_frontmatter
    from kitcheck.md import table_cells
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from ..md import _MD_LINK_RE  # type: ignore
    from ..md import _anchors_of  # type: ignore
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md  # type: ignore
    from ..md import is_fence  # type: ignore
    from ..md import read_frontmatter  # type: ignore
    from ..md import table_cells  # type: ignore


# служебные реестры комплекта — сверке нормализатора не подлежат
# (их сторожа — link_debts, срез 2)
_SERVICE_FILES = {"traceability-matrix.md", "open-questions.md"}


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
