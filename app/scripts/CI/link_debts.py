# app/scripts/CI/link_debts.py
#
# Сторож долгов ссылок: URL несёт два смысла — семантический (связь) и
# навигационный (переход). Семантику держит матрица трассировки; навигацию
# восстанавливает заход-создатель цели (правило create-artifact «закрытие
# входящих долгов»). Утилита проверяет, что механизм не молчит:
#
#   1) ПРОСРОЧКА: долг, чья цель уже существует в комплекте, — брак
#      (заход-создатель не закрыл входящие долги: ссылка не проставлена).
#   2) ИСПОЛНИМОСТЬ: дословное имя долга находится в документе-ожидателе
#      (иначе долг нельзя закрыть механической заменой «имя → ссылка» —
#      нарушена дословность упоминания, чинить в документе).
#
# Формат строки долга в матрице (create-artifact, шаг 6):
#   | <FROM-ID[, FROM-ID…]> | — | нет целевого артефакта <тип> «<дословное имя>» — требуется заход <скилл> |
# Имя опционально для однофайловых типов (rbac): существование проверяется
# по типу в реестре ID. Диапазоны FROM («FUN-BNK-01…05») разворачиваются.
#
# Второй формат (решение 2026-10-14, комментарии платформы AI Factory: реестр
# долгов должен включать все известные проблемы, не только отсутствующие
# ссылки) — долг БЕЗ отсутствующей цели:
#   | <FROM-ID[, …]> | — | долг <вид>: «<формулировка>» — причина: <…>; ответственный: <кто>;
#     ограничение: <какое поведение нельзя разрабатывать>; закрытие: <условие>[; источник: OQ-NNN] |
# Виды — закрытый перечень: открытый вопрос, противоречие, правило на
# изображении, источник недоступен. Поля ответственный / ограничение /
# закрытие обязательны; у вида «открытый вопрос» обязателен источник OQ-NNN
# (журнал open-questions.md в docs-репозиторий не переезжает — вопрос должен
# жить в строке целиком). Просрочка и исполнимость к таким строкам не
# применяются (цели нет); сторожится полнота полей и наличие FROM-ID в
# реестре. Раньше такие строки раздел тихо игнорировал.
#
# Стадии запуска (одна утилита, три рубежа): самопроверка агента в заходе →
# приёмка эксперта → CI docs-репо (после переезда комплекта).
#
# Мягкий гейт: код 0 и отчёт; --strict — код 2 при нарушениях.

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_DEBT_RE = re.compile(
    r"нет целевого артефакта\s+([\w./-]+)(?:\s+«([^»]+)»)?", re.IGNORECASE)
# Межсервисный долг: цель принадлежит другому сервису Экосистемы —
# владелец указывается в строке долга («…«имя» у владельца <service-id>…»,
# create-artifact «Недостающая цель ссылки», микро-волна 2026-08-23).
# Локальная просрочка для таких долгов не проверяется (цель живёт в
# чужом репозитории), исполнимость имени — как обычно.
_OWNER_RE = re.compile(r"»\s+у\s+владельца\s+([\w.-]+)", re.IGNORECASE)
_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
ISSUE_KINDS = ("открытый вопрос", "противоречие", "правило на изображении",
               "источник недоступен")
_ISSUE_RE = re.compile(
    r"долг\s+(" + "|".join(ISSUE_KINDS) + r")\s*:\s*«([^»]+)»", re.IGNORECASE)
_ISSUE_FIELD_RES = {
    "cause": re.compile(r"причина:\s*([^;|]+)", re.IGNORECASE),
    "responsible": re.compile(r"ответственный:\s*([^;|]+)", re.IGNORECASE),
    "constraint": re.compile(r"ограничение:\s*([^;|]+)", re.IGNORECASE),
    "closure": re.compile(r"закрытие:\s*([^;|]+)", re.IGNORECASE),
    # OQ-NNN — журнал рабочего репозитория; T-<JIRA-ID>[-NN] — постановка
    # tasks/<JIRA-ID>.md режима C (в docs-репозитории журнала нет; полигон 15.10)
    "source": re.compile(r"источник:\s*(OQ-\d+|T-[A-Z][A-Z0-9]*-\d+(?:-\d+)?)", re.IGNORECASE),
}
ISSUE_REQUIRED = {"responsible": "ответственный", "constraint": "ограничение",
                  "closure": "закрытие"}

# Третий формат — пробел НФТ (шаблон nfr.md, скилл create-nfr): это не
# отсутствующий артефакт, а названное в колонке «Не задано» значение:
#   | nfr-<код> | — | «<текст пробела>» |
# Просрочка «цель уже существует» к пробелу не применяется — тексту и
# положено стоять на странице. Исполнимость та же: цитата находится в
# файле страницы типа.
_GAP_RE = re.compile(r"—\s+«([^»]+)»\s*$")


def issue_fields(row: str) -> Optional[dict]:
    """Поля строки долга без цели (None — строка не этого формата):
    kind, statement, cause, responsible, constraint, closure, source, missing
    (перечень обязательных полей, которых нет, русскими именами)."""
    m = _ISSUE_RE.search(row)
    if not m:
        return None
    out = {"kind": m.group(1).lower(), "statement": m.group(2).strip()}
    for key, rx in _ISSUE_FIELD_RES.items():
        fm = rx.search(row)
        out[key] = fm.group(1).strip() if fm else None
    missing = [name for key, name in ISSUE_REQUIRED.items() if not out[key]]
    if out["kind"] == "открытый вопрос" and not out["source"]:
        missing.append("источник OQ-NNN или T-<JIRA-ID>")
    out["missing"] = missing
    return out

_RANGE_RE = re.compile(r"^(.*?)(\d+)\s*(?:…|\.\.\.)\s*(\d+)$")
_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$")


def _norm(s: str) -> str:
    s = re.sub(r"[«»\"'`]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _expand_from(cell: str) -> List[str]:
    ids: List[str] = []
    for tok in re.split(r"[,;]\s*", cell.strip()):
        tok = tok.strip().strip("*").strip()
        if not tok or tok in "—-":
            continue
        m = _RANGE_RE.match(tok)
        if m:
            prefix, a, b = m.group(1), m.group(2), m.group(3)
            width = len(a)
            ids.extend(f"{prefix}{i:0{width}d}"
                       for i in range(int(a), int(b) + 1))
        else:
            ids.append(tok)
    return ids


def _doc_title(path: Path) -> Optional[str]:
    """title из frontmatter; YAML-перенос длинного значения склеивается."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return None
    lines = body.splitlines()
    for i, ln in enumerate(lines[1:60], start=1):
        if ln.strip() == "---":
            return None
        m = _TITLE_RE.match(ln)
        if not m:
            continue
        v = m.group(1)
        q = v[0] if v and v[0] in "'\"" else None
        closed = (q is None or (len(v) >= 2 and v.endswith(q)
                                and not v.endswith(q * 2)))
        j = i + 1
        while not closed and j < len(lines) and lines[j].startswith(" "):
            v += " " + lines[j].strip()
            closed = v.endswith(q) and not v.endswith(q * 2)
            j += 1
        if q and len(v) >= 2 and v.endswith(q):
            v = v[1:-1]
            if q == "'":
                v = v.replace("''", "'")
        return v
    return None


def parse_matrix(matrix_text: str):
    """(реестр: ID -> (тип, файл),
    долги: [(from_ids, тип, имя|None, владелец|None, строка)])."""
    registry: Dict[str, Tuple[str, str]] = {}
    debts: List[Tuple[List[str], str, Optional[str], Optional[str], str]] = []
    for ln in matrix_text.splitlines():
        row = _ROW_RE.match(ln)
        if not row:
            continue
        cells = [c.strip() for c in row.group(1).split("|")]
        joined = " ".join(cells)
        issue = issue_fields(joined)
        if issue:
            # долг без цели: тип — «долг:<вид>», имя — формулировка,
            # владелец — ответственный (межсервисным не считается)
            debts.append((_expand_from(cells[0]), "долг:" + issue["kind"],
                          issue["statement"], None, ln.strip()))
            continue
        gap = _GAP_RE.search(joined)
        if gap and cells[0].lower().startswith("nfr"):
            debts.append((_expand_from(cells[0]), "nfr-gap", gap.group(1),
                          None, ln.strip()))
            continue
        m = _DEBT_RE.search(joined)
        if m:
            owner = _OWNER_RE.search(joined)
            debts.append((_expand_from(cells[0]), m.group(1), m.group(2),
                          owner.group(1) if owner else None, ln.strip()))
            continue
        # реестр ID: первая ячейка — ID, любая другая несёт путь .md
        # (голый или внутри markdown-ссылки). Жёсткая 4-колонная форма
        # «| ID | Тип | Наименование | Файл |» видела 7 записей из ~40:
        # реальные реестры матрицы разноколонны («| ID | Название |
        # Файл |», у функций «| ID | page_id | Файл |») и пишут файл
        # ссылкой — слепая зона жила до первого именованного долга от
        # FUN-ID (пилот-3, 2026-08-19). Тип — только если ячейка после
        # ID выглядит словом типа (латиница с дефисом: data-model, rbac).
        # суб-ID с точкой (SCR-CL-01.0, SCR-BNK-05.1) — легальные ID
        # реестра (FRAME-01 2026-08-31: парсер их не принимал, и долги
        # групп нельзя было переписать на карточку-носитель); точка —
        # только перед цифрами, чтобы не принять имя файла за ID
        if (len(cells) >= 2
                and re.match(
                    # nfr / nfr-<код> / nfr-<код>-<номер> — строчные ID
                    # каталога НФТ (шаблон nfr.md); прежний класс [A-Z…]
                    # их не видел, и долг от страницы типа не находил свой
                    # файл в реестре
                    r"^(?:[A-ZА-Я]{2,}[-\w]*"
                    r"|nfr(?:-[a-z]{3}(?:-\d{3})?)?)"
                    r"(?:\.\d+)*$",
                    cells[0])):
            fpath = next((fm.group(0) for c in cells[1:]
                          for fm in [re.search(r"[\w./-]+\.md\b", c)]
                          if fm), None)
            if fpath:
                typ = (cells[1]
                       if re.fullmatch(r"[a-z][a-z-]*", cells[1]) else "")
                registry.setdefault(cells[0], (typ, fpath))
    return registry, debts


def check(matrix_path: Path, docs_root: Path):
    registry, debts = parse_matrix(
        matrix_path.read_text(encoding="utf-8", errors="replace"))
    # титулы и типы существующих артефактов комплекта
    titles: Dict[Path, str] = {}
    for p in docs_root.rglob("*.md"):
        t = _doc_title(p)
        if t:
            titles[p] = _norm(t)
    # тип карточки по файлу (из реестра матрицы) — для сверки с типом долга
    type_of: Dict[str, str] = {}
    for _id, (typ, fpath) in registry.items():
        if typ:
            type_of[fpath.replace("\\", "/").lstrip("./")] = typ.lower()

    def _card_type(path: Path) -> str:
        rel = path.relative_to(docs_root).as_posix()
        return next((t for f, t in type_of.items()
                     if rel == f or rel.endswith("/" + f)), "")
    types_present = {t for t, _f in registry.values()}
    report: List[str] = []
    ok = True
    cross: Dict[str, int] = {}
    n_issue = 0
    n_gap = 0
    for from_ids, typ, name, owner, raw in debts:
        if typ.startswith("долг:"):
            # долг без цели: полнота полей и FROM-ID в реестре; просрочка
            # и исполнимость не применяются — цели нет
            n_issue += 1
            fields = issue_fields(raw) or {"missing": []}
            if fields["missing"]:
                report.append(f"долг без цели НЕПОЛОН: нет полей "
                              f"{', '.join(fields['missing'])} ✗ — {raw[:100]}")
                ok = False
            for fid in from_ids:
                if fid not in registry:
                    report.append(f"долг от {fid}: ID отсутствует в реестре "
                                  f"матрицы ✗ — {raw[:80]}")
                    ok = False
            continue
        # 1) просрочка: цель существует? (межсервисный долг — цель в
        # чужом репозитории, локальная просрочка не проверяется; пробел
        # НФТ — цели-артефакта нет, цитата обязана быть на странице)
        if typ == "nfr-gap":
            n_gap += 1
        elif owner is not None:
            cross[owner] = cross.get(owner, 0) + 1
        else:
            target = None
            if name:
                # FB-02 common-dictionary (2026-10-14): «цель существует» —
                # карточка с ТЕМ ЖЕ заголовком (с тегом или без) и, если тип
                # известен, того же типа; поиск подстрокой ловил чужой
                # заголовок («…что пользователь является УЛ» для долга
                # data-model «Пользователь») и останавливал приёмку этапа
                nname = _norm(name)
                want = typ.lower()
                for p, t in titles.items():
                    tagless = re.sub(r"^\[[^\]]+\]\s*", "", t)
                    if t != nname and tagless != nname:
                        continue
                    ct = _card_type(p)
                    if ct and want and ct != want:
                        continue
                    target = p
                    break
            elif not name:
                target = typ if typ.lower() in {t.lower()
                                                for t in types_present} \
                    else None
            if target:
                report.append(f"ПРОСРОЧЕН долг: цель существует "
                              f"({target if isinstance(target, str) else target.name}), "
                              f"ссылка не проставлена ✗ — {raw[:100]}")
                ok = False
        # 2) исполнимость: имя находится в документах-ожидателях
        if not name:
            continue
        nname = _norm(name)
        for fid in from_ids:
            reg = registry.get(fid)
            if not reg:
                report.append(f"долг от {fid}: ID отсутствует в реестре "
                              f"матрицы ✗ — {raw[:80]}")
                ok = False
                continue
            doc = docs_root / reg[1]
            if not doc.is_file():
                report.append(f"долг от {fid}: файл реестра не найден "
                              f"({reg[1]}) ✗")
                ok = False
                continue
            body = _norm(doc.read_text(encoding="utf-8", errors="replace"))
            if nname not in body:
                report.append(
                    f"долг НЕИСПОЛНИМ: имя «{name}» не найдено дословно в "
                    f"{reg[1]} ✗ (замена «имя → ссылка» невозможна — "
                    "дословность упоминания нарушена)")
                ok = False
    if n_issue:
        report.append(f"долгов без отсутствующей цели {n_issue} (открытые "
                      "вопросы, противоречия, правила на изображении, "
                      "недоступные источники) — сторожится полнота полей")
    if n_gap:
        report.append(f"пробелов НФТ {n_gap} («Не задано» на страницах типов) "
                      "— просрочка не применяется, цитата сторожится")
    if cross:
        report.append(
            f"межсервисных долгов {sum(cross.values())} "
            f"(владельцы: {', '.join(sorted(cross))}) — локальная "
            "просрочка не проверяется, дозакрытие при появлении "
            "комплекта владельца ✓")
    if ok:
        report.append(f"OK: долгов {len(debts)}, просроченных нет, "
                      "все имена находятся в документах-ожидателях ✓")
    return report, ok


_OQ_NUM_RE = re.compile(r"^##\s+OQ-(\d+)\b", re.M)

# Настраиваемые параметры: упоминание «[Настраиваемые параметры]
# <сервис>.<ключ>» в документах комплекта требует строки с этим ключом в
# разделе параметров data-model/dictionaries.md (conventions §5.2 —
# параметры фиксируются вместе со значениями; инцидент src-locks
# 2026-08-15: h2h_in_path/h2h_path_polling_time упоминались агентом и
# процессом, в справочнике отсутствовали, долг не заводился).
# пробелы вокруг точки допускаются: «БлокН2Н .h2h_out_path» — дефект
# набора источника прятал третий параметр от сторожа (src-locks)
_PARAM_MENTION_RE = re.compile(
    r"Настраиваемые параметры\W{0,4}\s+[\w-]+(?:\.[\w-]+)*\s*\.\s*(\w+)")


def check_config_params(docs_root: Path) -> Tuple[List[str], bool]:
    dicts = docs_root / "srs" / "data-model" / "dictionaries.md"
    dict_text = (dicts.read_text(encoding="utf-8", errors="replace")
                 if dicts.is_file() else "")
    missing: Dict[str, List[str]] = {}
    for p in docs_root.rglob("*.md"):
        if "data-model" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in _PARAM_MENTION_RE.finditer(text):
            key = m.group(1)
            if key not in dict_text:
                missing.setdefault(key, []).append(p.name)
    if missing:
        return [f"настраиваемые параметры без строки в dictionaries "
                f"(conventions §5.2): "
                + "; ".join(f"{k} ({', '.join(sorted(set(v))[:2])})"
                            for k, v in sorted(missing.items()))
                + " ✗ — требуется дозаход create-data-model"], False
    return [], True


_FB_NUM_RE = re.compile(r"^##\s+FB-(\d+)\b", re.M)


def _check_register_order(path: Path, num_re, prefix: str,
                          name: str) -> Tuple[List[str], bool]:
    """Общий сторож append-only реестров записей «## <PREFIX>-NN»:
    номера монотонно возрастают по позиции в файле; вставка в середину
    и перемещение записей при правке — брак."""
    if not path.is_file():
        return [], True
    text = path.read_text(encoding="utf-8", errors="replace")
    # заголовок-образец внутри блока кода записью не является (FB-04
    # «Корпоративных карт», 2026-09-15: пересозданный скелет с примером
    # формата давал «1 записей ✓» при нуле настоящих записей)
    text = re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.S | re.M)
    nums = [int(m.group(1)) for m in num_re.finditer(text)]
    bad = [(a, b) for a, b in zip(nums, nums[1:]) if b < a]
    if bad:
        return [f"{name}: порядок реестра нарушен (append-only): "
                + ", ".join(f"{prefix}-{b:03d} стоит после {prefix}-{a:03d}"
                            for a, b in bad[:3]) + " ✗"], False
    return [f"{name}: порядок реестра append-only соблюдён "
            f"({len(nums)} записей) ✓"], True


def check_oq_order(oq_path: Path) -> Tuple[List[str], bool]:
    """Реестр open-questions — append-only (трёхкратный инцидент,
    третий — src-locks 2026-08-15: закрытая запись переехала в конец)."""
    return _check_register_order(oq_path, _OQ_NUM_RE, "OQ",
                                 "open-questions")


def check_feedback_order(fb_path: Path) -> Tuple[List[str], bool]:
    """Реестр замечаний команды feedback.md (цикл обратной связи,
    модель принята 2026-08-17) — та же дисциплина, что у OQ: записи
    FB-NN append-only, статусы правятся на месте."""
    return _check_register_order(fb_path, _FB_NUM_RE, "FB", "feedback")


# Журнал координации (трек с координатором): запись — строка «- YYYY-MM-DD |
# тема | …» плюс её продолжения с отступом. Лимит длины записи — решение
# владельца 2026-10-09: четвёртая сессия координатора КК, журнал 340
# записей / 700 КБ (средняя 2 060 знаков, максимум 10 535) — «новая сессия
# поднимется с журнала» невыполнимо на любом окне контекста. Доказательства
# (выводы прибора, команд, диффы) живут в sandbox/ и файлах сдачи, запись на
# них ссылается. Сигнал — ⚠ (вердикт не трогает): журнал ведёт агент по
# отмашке, брак здесь не остановил бы ничего, а длинные записи до решения
# были нормой.
COORD_LOG_ENTRY_LIMIT = 600
_COORD_ENTRY_RE = re.compile(r"^- \d{4}-\d{2}-\d{2} \|")


def check_coordination_log(log_path: Path,
                           limit: int = COORD_LOG_ENTRY_LIMIT
                           ) -> Tuple[List[str], bool]:
    """Длина записей coordination-log.md: запись длиннее limit знаков —
    ⚠ с датой и темой; итог — число записей и сколько сверх лимита.
    Файла нет (трек без координатора) — пусто."""
    if not log_path.is_file():
        return [], True
    text = log_path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.S | re.M)
    entries: List[Tuple[str, int]] = []
    cur: Optional[str] = None
    size = 0
    for ln in text.splitlines():
        if _COORD_ENTRY_RE.match(ln):
            if cur is not None:
                entries.append((cur, size))
            cur, size = ln, len(ln)
        elif cur is not None and (ln.startswith(" ") or ln.startswith("\t")):
            size += len(ln.strip()) + 1
        elif cur is not None and ln.strip():
            # непустая строка без отступа — запись кончилась
            entries.append((cur, size))
            cur, size = None, 0
    if cur is not None:
        entries.append((cur, size))
    if not entries:
        return [], True
    long = [(head, n) for head, n in entries if n > limit]
    out = [f"coordination-log: записей {len(entries)}, сверх лимита "
           f"{limit} знаков — {len(long)}" + (" ✓" if not long else "")]
    for head, n in long[-5:]:
        parts = [x.strip() for x in head.split("|")]
        who = " | ".join(parts[:2]).lstrip("- ")[:60]
        out.append(f"предупреждение: запись журнала «{who}» — {n} знаков "
                   f"(лимит {limit}): факты и решение — в запись, "
                   "доказательства — ссылкой на отчёт в sandbox/ или файл "
                   "сдачи")
    if len(long) > 5:
        out.append(f"предупреждение: … и ещё {len(long) - 5} записей сверх "
                   "лимита (показаны последние пять)")
    return out, True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Сторож долгов ссылок: просрочка (цель существует, "
                    "ссылки нет) и исполнимость (имя находится дословно); "
                    "плюс порядок реестра open-questions (append-only).")
    ap.add_argument("--matrix", type=Path, required=True)
    ap.add_argument("--docs", type=Path, required=True,
                    help="корень docs/ комплекта")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    report, ok = check(args.matrix, args.docs)
    oq = args.docs / "open-questions.md"
    if not oq.is_file():
        oq = args.docs.parent / "open-questions.md"
    oq_report, oq_ok = check_oq_order(oq)
    report.extend(oq_report)
    ok = ok and oq_ok
    # feedback.md живёт в корне репозитория (уровень сервиса, вне docs/)
    fb_report, fb_ok = check_feedback_order(
        args.docs.parent / "feedback.md")
    report.extend(fb_report)
    ok = ok and fb_ok
    cp_report, cp_ok = check_config_params(args.docs)
    report.extend(cp_report)
    ok = ok and cp_ok
    for ln in report:
        print(f"# {ln}")
    return 0 if ok or not args.strict else 2


if __name__ == "__main__":
    sys.exit(main())
