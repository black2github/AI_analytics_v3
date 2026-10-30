# app/scripts/CI/kitcheck/checks/card_controls.py
"""Проверки карточки: сообщения контролей, файл = сущность, приписанные атрибуты.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from ..html import _fm_head, cell_text, find_top_tables, parse_md_tables
from bs4 import Tag


_ENTITY_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+$")


def _frontmatter_entity(text: str) -> str:
    """Значение entity из frontmatter карточного файла контролей без
    обрамляющих кавычек; '' — ключа нет или значение пустое."""
    m = re.search(r"^entity:[ \t]*(.*?)[ \t]*$", _fm_head(text), re.M)
    if not m:
        return ""
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
        val = val[1:-1].strip()
    return val


def _fc_fabricated_attributes(fx: "_FileCtx") -> Tuple[List[str], bool]:
    source_text, text = fx.source_text, fx.text
    report: List[str] = []
    ok = True
    # Фабрикация атрибутов (STS-01 ENT-022, 2026-08-31): reverse-карточка
    # data-model несёт таблицу атрибутов (роли Атрибут/Тип), а её
    # страница-источник ТАБЛИЦ НЕ СОДЕРЖИТ — состав придуман «по
    # аналогии» с другой сущностью (источник истории: 3 предложения +
    # имя таблицы БД; карточка: 7 атрибутов с типами и длинами).
    # Сверка с источником односторонняя и этого не ловит. ⚠ — решение
    # владельца: подтвердить аналогию явной пометкой-предположением и
    # OQ либо сократить карточку до фактов источника.
    if (source_text is not None
            and re.search(r"^type:\s*data-model\s*$", _fm_head(text), re.M)
            and re.search(r"^\|[^\n]*Атрибут[^\n]*\|[^\n]*Тип",
                          text, re.M)
            and not re.search(r"<table|^\|.*\|.*\|", source_text, re.M)):
        report.append(
            "предупреждение: карточка несёт таблицу атрибутов, а "
            "страница-источник таблиц не содержит — состав атрибутов "
            "взят не из источника (кандидат на фабрикацию «по "
            "аналогии»); подтвердить предположением+OQ или сократить "
            "до фактов источника (решение владельца)")
    return report, ok


# Приписка источнику обратного направления (FB-12 КК, замер 2026-10-29, решение владельца
# 29.10): карточка контроля задаёт текст сообщения, а ячейка сообщения однозначно
# сопоставленной строки источника пуста — текст взят не из источника (CTL-052: из соседней
# строки). Односторонняя сверка «всё ли перенесено» такое не видит. Только ⚠ / i.
# Колонка сообщения — заголовок целиком из словаря; интеграционные «Структура сообщения»,
# «XML структура сообщения», «Пример сообщения» колонкой сообщения не считаются.
_MSG_COL_RE = re.compile(
    r"(сообщение( об ошибке( на фронте)?| для пользователя| пользователю| ошибки контроля)?"
    r"|текст (ошибки|сообщения))\.?( \(атрибут error\.message\))?", re.I)
_MSG_LOGIC_COL_RE = re.compile(r"логик|правил|услови|описание провер|алгоритм", re.I)
_MSG_NAME_COL_RE = re.compile(r"название|наименование", re.I)
_MSG_NOT_SET_RE = re.compile(r"в\s+постановке\s+не\s+задан", re.I)
_CTL_HEAD_RE = re.compile(r"^### (CTL-\d+)\.\s*(.*)$", re.M)
_CTL_FIELD_RE = re.compile(r"^- \*\*([^*]+?):\*\*\s?(.*)$")
# пояснения канона в скобках («справочник вне комплекта … долг») — не текст источника
_CTL_NOTE_RE = re.compile(
    r"\((?:[^()]|\([^()]*\))*(?:комплект|долг|выгрузк|артефакт|источник|постановк)"
    r"(?:[^()]|\([^()]*\))*\)", re.I)


def _hdr_plain(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>|\*", "", h)).strip()


def _msg_norm(v: str) -> str:
    """Нормальная форма логики для сопоставления карточки со строкой источника."""
    v = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", v)
    v = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", v)
    v = re.sub(r"<br\s*/?>|&nbsp;", " ", v, flags=re.I)
    v = re.sub(r"\b[A-Z]{2,6}(?:-[A-Z]{2,6})*-\d+(?:\.\d+)*\b", " ", v)
    v = v.replace("\\", "").replace("ё", "е").replace("Ё", "Е").replace(" ", " ")
    v = re.sub(r"[*_`«»\"“”„'’<>~]", " ", v)
    v = re.sub(r"\s*([.,:;()=])\s*", r"\1", v)
    return re.sub(r"\s+", " ", v).strip().lower()


def _grid_with_merges(table: Tag) -> Tuple[List[List[Tuple[str, int]]], int]:
    """Сетка таблицы с флагом объединения у каждой позиции: 0 — своя ячейка, 1 — исходная
    объединённая (colspan/rowspan), 2 — протяжка rowspan сверху; число ведущих строк из одних
    th. expand_grid флагов не отдаёт — разновидность для сторожа приписки."""
    grid: List[List[Tuple[str, int]]] = []
    carry: Dict[int, List] = {}
    head_n = 0
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells = tr.find_all(["td", "th"], recursive=False)
        if cells and all(c.name == "th" for c in cells) and head_n == len(grid):
            head_n += 1
        row: List[Tuple[str, int]] = []
        col = 0

        def fill() -> None:
            nonlocal col
            while col in carry:
                rem, val = carry[col]
                row.append((val, 2))
                if rem - 1:
                    carry[col][0] = rem - 1
                else:
                    del carry[col]
                col += 1

        fill()
        for c in cells:
            fill()
            val = cell_text(c)
            cs = int(c.get("colspan", 1) or 1)
            rs = int(c.get("rowspan", 1) or 1)
            for _ in range(cs):
                row.append((val, 1 if (cs > 1 or rs > 1) else 0))
                if rs > 1:
                    carry[col] = [rs - 1, val]
                col += 1
        fill()
        grid.append(row)
    w = max((len(r) for r in grid), default=0)
    return [r + [("", 0)] * (w - len(r)) for r in grid], head_n


def message_rows(source_text: str) -> List[dict]:
    """Строки данных таблиц источника с колонкой сообщения: ячейки, сообщение, его
    заполненность и объединение, колонки логики и названия. Строки-разделы на всю ширину и
    хвосты rowspan без собственных ячеек строками данных не считаются."""
    out: List[dict] = []
    tables: List[Tuple[List[str], List[List[Tuple[str, int]]]]] = []
    for t in find_top_tables(source_text):
        grid, head_n = _grid_with_merges(t)
        if not grid:
            continue
        if head_n == 0:  # шапка из td — первая строка с колонкой сообщения среди трёх
            head_n = next((i + 1 for i, r in enumerate(grid[:3])
                           if any(_MSG_COL_RE.fullmatch(_hdr_plain(v)) for v, _ in r)), 0)
        # строка-раздел шапки («Контроли <сущность>» на всю ширину) — не заголовок колонки
        heads = [r for r in grid[:head_n] if len({v for v, _ in r if v.strip()}) > 1
                 or sum(1 for v, _ in r if v.strip()) < len(r) - 1]
        labels = []
        for ci in range(len(grid[0])):
            parts: List[str] = []
            for r in heads:
                if r[ci][0] and r[ci][0] not in parts:
                    parts.append(r[ci][0])
            labels.append(" / ".join(parts))
        tables.append((labels, grid[head_n:]))
    md_only = re.sub(r"<table.*?</table>", "", source_text, flags=re.S | re.I)
    for hdr, rows in parse_md_tables(md_only):
        tables.append((hdr, [[(v, 0) for v in r] for r in rows]))
    for ti, (labels, data) in enumerate(tables):
        msg_cols = [i for i, h in enumerate(labels)
                    if any(_MSG_COL_RE.fullmatch(_hdr_plain(p)) for p in h.split(" / "))]
        if not msg_cols:
            continue
        logic = [i for i, h in enumerate(labels) if _MSG_LOGIC_COL_RE.search(h) and i not in msg_cols]
        names = [i for i, h in enumerate(labels) if _MSG_NAME_COL_RE.search(h) and i not in msg_cols]
        for ri, r in enumerate(data):
            vals = [v for v, _ in r]
            if not any(v.strip() for v in vals) or len(set(vals)) == 1:
                continue
            if all(m == 2 for v, m in r if v.strip()):
                continue
            # несколько колонок сообщения (разделены по условию: «файлов == 0» / «> 0», стенд
            # CTL-009) — ячейка пуста, только если пусты все; объединена — если любая
            msgs = [vals[i] for i in msg_cols if i < len(vals)]
            bares = [re.sub(r"<br\s*/?>|&nbsp;|\s|\*", "", m) for m in msgs]
            out.append({
                "table": ti, "row": ri, "msg": " | ".join(m for m in msgs if m.strip()),
                "empty": all(not b or re.fullmatch(r"[-—–]+", b) for b in bares),
                "merged": any(r[i][1] for i in msg_cols if i < len(r)),
                "cells": [v for i, v in enumerate(vals) if i not in msg_cols],
                "logic": [vals[i] for i in logic if i < len(vals)],
                "names": [vals[i] for i in names if i < len(vals)],
            })
    return out


def control_cards(text: str) -> List[dict]:
    """Карточки «### CTL-NNN. Реквизит: Название» карточного файла контролей с полями."""
    heads = list(_CTL_HEAD_RE.finditer(text))
    cards = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = re.split(r"^#{1,3} ", text[h.end():end], maxsplit=1, flags=re.M)[0]
        fields: Dict[str, str] = {}
        cur = None
        for ln in body.splitlines():
            fm = _CTL_FIELD_RE.match(ln)
            if fm:
                cur = fm.group(1).strip()
                fields[cur] = fm.group(2)
            elif cur and ln.strip():
                fields[cur] += "\n" + ln
        cards.append({"id": h.group(1), "title": h.group(2).strip(), "fields": fields})
    return cards


def match_message_row(card: dict, rows: List[dict]) -> Optional[dict]:
    """Строка источника карточки — только однозначно: реквизит + название проверки из
    заголовка, затем логика (± «Условие выполнения») точно или подобием ≥ 0.9 у
    единственного кандидата; равные кандидаты — по заголовку, иначе только при одинаковой
    заполненности ячейки (для сторожа важна лишь она). Иначе None."""
    import difflib
    attr, _, name = card["title"].rpartition(":")
    n, an = _msg_norm(name), _msg_norm(attr)

    def by_title(pool: List[dict]) -> Optional[dict]:
        if not n:
            return None
        cand = [r for r in pool if any(_msg_norm(v) == n for v in r["names"])]
        if len(cand) > 1 and an:
            exact = [r for r in cand if any(_msg_norm(v) == an for v in r["cells"])]
            cand = exact or [r for r in cand if any(
                an in _msg_norm(v) or (_msg_norm(v) and _msg_norm(v) in an) for v in r["cells"])]
        return cand[0] if len(cand) == 1 else None

    hit = by_title(rows)
    if hit is not None:
        return hit
    logic = _CTL_NOTE_RE.sub(" ", card["fields"].get("Логика проверки", ""))
    cond = _CTL_NOTE_RE.sub(" ", card["fields"].get("Условие выполнения", ""))
    keys = [k for k in {_msg_norm(logic), _msg_norm(cond + " " + logic)} if k]
    best, tops = 0.0, []
    for r in rows:
        rs = 0.0
        for c in (r["logic"] or r["cells"]):
            nc = _msg_norm(c)
            for k in keys:
                if not nc:
                    break
                if k == nc:
                    rs = 1.0
                    break
                sm = difflib.SequenceMatcher(None, k, nc, autojunk=False)
                if sm.real_quick_ratio() < max(best, rs, 0.9) or sm.quick_ratio() < max(best, rs, 0.9):
                    continue
                rs = max(rs, sm.ratio())
        if rs > best + 1e-9:
            best, tops = rs, [r]
        elif rs and abs(rs - best) <= 1e-9:
            tops.append(r)
    if best < 0.9 or not tops:
        return None
    if len(tops) == 1:
        return tops[0]
    hit = by_title(tops)
    if hit is not None:
        return hit
    return tops[0] if len({(t["empty"], t["merged"]) for t in tops}) == 1 else None


def message_attribution(card_text: str, source_texts: List[Tuple[str, str]]) -> Tuple[List[str], Optional[int]]:
    """⚠ по карточкам с текстом сообщения при пустой необъединённой ячейке строки источника.
    source_texts — [(page_id, текст страницы)]. Второе значение — число строк с колонкой
    сообщения (None/0 — сверка не выполнена)."""
    rows: List[dict] = []
    for pid, st in source_texts:
        for r in message_rows(st):
            r["pid"] = pid
            rows.append(r)
    if not rows:
        return [], 0
    report: List[str] = []
    for c in control_cards(card_text):
        msg = c["fields"].get("Сообщение об ошибке", "").strip()
        if not msg or _MSG_NOT_SET_RE.search(msg):
            continue
        r = match_message_row(c, rows)
        if r is None or not r["empty"] or r["merged"]:
            continue
        flat = re.sub(r"\s+", " ", msg)
        short = flat[:60] + ("…" if len(flat) > 60 else "")
        quoted = short if short.startswith("«") else f"«{short}»"
        where = (f"а ячейка сообщения строки источника «{c['title']}» на странице {r['pid']} "
                 "пуста")
        if re.search(r"«[^»]+»|\"[^\"]+\"", msg):
            tail = "текст не из источника (приписка; правило шаблона: ровно «в постановке не задано»)"
        else:
            # пояснение без цитаты (стенд CTL-029: «мягкий контроль — сообщение не
            # отображается» — пересказ абзаца страницы) — не подставленный текст, но и не
            # формула шаблона
            tail = ("поле без цитаты — по шаблону ровно «в постановке не задано», пояснение — "
                    "не в этом поле")
        report.append(
            f"предупреждение: {c['id']} — поле «Сообщение об ошибке» задано ({quoted}), "
            f"{where} — {tail}")
    return report, len(rows)


def is_control_cards_file(md_path: Path, text: str) -> bool:
    return (md_path.name.lower().startswith("cards-")
            and bool(re.search(r"^type:\s*control\s*$", _fm_head(text), re.M)))


def _fc_message_attribution(fx: "_FileCtx") -> Tuple[List[str], bool]:
    if not is_control_cards_file(fx.md_path, fx.text):
        return [], True
    m = re.search(r"^confluence_page_ids?:\s*(.*)$", _fm_head(fx.text), re.M)
    pids = re.findall(r"\d+", m.group(1)) if m else []
    texts = []
    if fx.source_text is not None:
        texts.append((pids[0] if pids else "?", fx.source_text))
    if fx.amnesty_text:  # доп. страницы файла (selfcheck: amnesty по его page_ids)
        texts.append((",".join(pids[1:]) or "доп.", fx.amnesty_text))
    report, n_rows = message_attribution(fx.text, texts)
    # сверка не выполнена — одна i-строка на файл; в самопроверке комплекта — сводной
    # строкой комплекта (selfcheck._kc_message_attribution_unchecked)
    if not n_rows and not fx.kit_summary:
        report.append("i сверка сообщений карточек с источником не выполнена: "
                      + ("страница не указана" if fx.source_text is None
                         else "на странице нет таблицы с колонкой сообщения"))
    return report, True


def _fc_control_cards_by_entity(fx: "_FileCtx") -> Tuple[List[str], bool]:
    md_path, text = fx.md_path, fx.text
    report: List[str] = []
    ok = True
    # Нарезка карточных файлов контролей по сущности (решение владельца
    # 2026-08-31: файл = сущность/форма, frontmatter entity; прежняя
    # нарезка по заходам чтения разбрасывала контроли сущности по
    # файлам). Сторож: «Проверяемый атрибут» каждой карточки содержит
    # ID из entity файла; карточка-чужак → ⚠; файл без entity → один ⚠
    # «разметить» (старые файлы до перенарезки/перегона — легальны).
    # FB-11 «Корпоративных карт» (2026-10-05): значение entity бывает
    # и ИМЕНЕМ формы в кавычках (карточки формы в комплекте ещё нет —
    # шаблон controls.md); прежняя маска [\w.-]+ не видела кавычек,
    # пробелов и кириллицы и рапортовала «без entity» при заполненном
    # поле. Сверка «чужих» карточек — только для значения-ID: имени
    # формы в «Проверяемом атрибуте» сравнивать не с чем.
    if (md_path.name.lower().startswith("cards-")
            and re.search(r"^type:\s*control\s*$", _fm_head(text), re.M)):
        _eid = _frontmatter_entity(text)
        if not _eid:
            report.append(
                "предупреждение: карточный файл контролей без entity во "
                "frontmatter — файл = сущность/форма (решение "
                "2026-08-31), разметить при перенарезке или перегоне")
        elif _ENTITY_ID_RE.match(_eid):
            _aliens = []
            for cm in re.finditer(
                    r"^###\s+(CTL-\d+)\..*?\n(.*?)(?=^###\s|\Z)",
                    text, re.M | re.S):
                attr = re.search(
                    r"^\s*-\s+\*\*Проверяемый атрибут:\*\*(.+)$",
                    cm.group(2), re.M)
                if attr and _eid not in attr.group(1):
                    _aliens.append(cm.group(1))
            if _aliens:
                report.append(
                    f"предупреждение: карточки чужой сущности "
                    f"×{len(_aliens)} в файле entity={_eid} "
                    f"({', '.join(_aliens[:4])}) — файл = сущность, "
                    "карточка кладётся в файл своей сущности")
    return report, ok
