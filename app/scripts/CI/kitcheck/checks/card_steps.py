# app/scripts/CI/kitcheck/checks/card_steps.py
"""Проверки карточки: шаги и поведение — маркеры шагов, вложенность, тела шагов, нумерация.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import re
from typing import Dict, List, Optional, Tuple
from .. import fs as _fs
from ..html import _fm_body, _norm_cell, _plain, expand_grid, find_top_tables, protect_token_tags
from bs4 import BeautifulSoup


# ---------- вложенность раздела «Поведение» ----------
#
# Смысл ветвления Если/то/иначе кодируется в источнике ВИЗУАЛЬНО
# (margin-left абзацев, вложенные списки) — выпрямление вложенности при
# переносе меняет смысл молча. Сверяем ПРОФИЛЬ вложенности: маркеры шагов
# переносятся дословно (система маркеров любая: 1.1 / A) / Шаг №2),
# уровень определяется РАЗМЕТКОЙ, пиксели и отступы нормализуются
# ранжированием уникальных значений (устойчиво к стилям разных авторов).
# Ограничение (честное): если вложенность в источнике не выражена ни
# списками, ни отступами (голый текст), механике не за что зацепиться —
# остаются правило шаблона, образец и глаза эксперта.

_STEP_MARKER_RE = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:\*\*)?\s*(?:шаг\s*)?№?\s*"
    r"([0-9A-Za-zА-Яа-я]{1,4}(?:\.[0-9A-Za-z]{1,3})*)\s*[).:\]]",
    re.IGNORECASE)
_MARGIN_RE = re.compile(r"margin-left:\s*([\d.]+)\s*px", re.IGNORECASE)
_BEHAVIOR_CELL_RE = re.compile(r"что\s+делает\s+функци", re.IGNORECASE)
# алгоритм МЕТОДА: сверяется только когда карточка несёт раздел
# «Поведение» (функция метода, FUN-SYS); карточка контракта INTC
# алгоритм законно не несёт — сверка не её (перенос — заходом
# create-function, потеря без долга сторожится правилом скилла)
_BEHAVIOR_CELL_METHOD_RE = re.compile(r"что\s+делает\s+метод", re.IGNORECASE)


def _marker_core(text: str) -> Optional[str]:
    m = _STEP_MARKER_RE.match(text)
    if not m:
        return None
    core = m.group(1)
    # маркер: содержит цифру либо одиночная буква (A/B/В…) — не слова
    if any(ch.isdigit() for ch in core) or (len(core) == 1 and core.isalpha()):
        return core.lower()
    return None


def _rank_levels(steps: List[Tuple[str, float]]) -> List[Tuple[str, int]]:
    """Нормализация отступов: уровень = ранг уникального отступа."""
    ranks = {v: i for i, v in enumerate(sorted({lv for _c, lv in steps}))}
    return [(c, ranks[lv]) for c, lv in steps]


@_fs.memoize(copy=list)
def behavior_steps_from_source(source_text: str,
                               cell_re=None) -> List[Tuple[str, int]]:
    """(маркер, уровень) из ячейки «Что делает функция» HTML-источника
    (или иной ячейки поведения по cell_re)."""
    soup = BeautifulSoup(protect_token_tags(source_text), "html.parser")
    cell = None
    rx = cell_re or _BEHAVIOR_CELL_RE
    for th in soup.find_all(["th", "td"]):
        if rx.search(th.get_text(" ", strip=True) or ""):
            cell = th.find_next_sibling("td")
            if cell is not None:
                break
    if cell is None:
        return []
    steps: List[Tuple[str, float]] = []
    for el in cell.find_all(["p", "li"]):
        text = el.get_text(" ", strip=True)
        core = _marker_core(text)
        if core is None:
            continue
        if el.name == "li":
            depth = len([a for a in el.parents
                         if a.name in ("ul", "ol") and cell in a.parents]) or 1
            indent = 40.0 * depth
        else:
            m = _MARGIN_RE.search(el.get("style") or "")
            indent = float(m.group(1)) if m else 0.0
        steps.append((core, indent))
    return _rank_levels(steps)


def behavior_steps_from_card(card_text: str) -> List[Tuple[str, int]]:
    """(маркер, уровень) из раздела «## Поведение» карточки."""
    m = re.search(r"^##\s+Поведение\s*$(.*?)(?=^##\s|\Z)", card_text,
                  re.M | re.S)
    if not m:
        return []
    steps: List[Tuple[str, float]] = []
    for ln in m.group(1).splitlines():
        if not ln.strip():
            continue
        core = _marker_core(ln.strip())
        if core is None:
            continue
        steps.append((core, float(len(ln) - len(ln.lstrip()))))
    return _rank_levels(steps)


def check_behavior_nesting(card_text: str,
                           source_text: str) -> Tuple[List[str], bool]:
    """Профиль вложенности «Поведения» карточки против источника."""
    src = behavior_steps_from_source(source_text)
    if len(src) < 2:
        # ячейка «Что делает функция» пуста/не размечена: пробуем алгоритм
        # МЕТОДА — он сверяется только с карточкой, несущей «Поведение»
        # (функция метода); карточка без раздела (контракт INTC) — не её
        src = behavior_steps_from_source(source_text,
                                         _BEHAVIOR_CELL_METHOD_RE)
        if len(src) < 2 or not re.search(r"^##\s+Поведение\s*$",
                                         card_text, re.M):
            return [], True
    card = behavior_steps_from_card(card_text)
    report: List[str] = []
    ok = True
    j = 0
    for core, lvl in src:
        k = next((i for i in range(j, len(card)) if card[i][0] == core), None)
        if k is None:
            report.append(f"поведение: шаг «{core}» источника не найден в "
                          "карточке ✗ ПОТЕРЯ ШАГА")
            ok = False
            continue
        if card[k][1] != lvl:
            report.append(
                f"поведение: шаг «{core}» — уровень вложенности {card[k][1]} "
                f"в карточке против {lvl} в источнике ✗ (выпрямление меняет "
                "смысл ветвления)")
            ok = False
        j = k + 1
    if ok:
        report.append(f"поведение: профиль вложенности совпадает "
                      f"({len(src)} шагов) ✓")
    return report, ok


# Валидный элемент markdown-списка: -/*/+ или ОДИНОЧНОЕ число с . или ).
# Составной маркер источника (1.1), А.2) — не маркер markdown: строка с ним
# рендерится продолжением абзаца, шаги склеиваются в плоский текст
# (инцидент mwqueue, 2026-08-14: структура в байтах ≠ структура в рендере).
_MD_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s")


# Маркеры шагов процесса: составные номера с подшагом (1.1 … 1.29) и
# «Шаг № N». Формат-агностичный сборщик: strong-токены и первые колонки
# таблиц HTML; md-таблицы источника сверяются полной сверкой значений и
# в этом стороже не нуждаются. Одиночные числа не собираются (шум:
# нумерация колонок, счётчики). Если распознаваемых маркеров < 2 —
# сверять нечего (голый текст без нумерации): честный skip, работают
# правила шаблона и глаза эксперта.
_STEP_TOKEN_RE = re.compile(r"^(?:шаг\s*№?\s*)?(\d+\.\d+(?:\.\d+)*)\)?\.?$",
                            re.IGNORECASE)


# К-23 (2026-08-18): объявление шага фразой «Шаг №N» — в markdown-
# заголовках (#### Шаг №1.), strong и первых колонках; прежний сборщик
# брал только СОСТАВНЫЕ номера из strong/таблиц — партия «Функции
# Банка» вела шаги md-заголовками, и потеря ВСЕГО поведения (12 шагов
# fun-bnk-08) прошла зелёной, замаскированная мешком литералов.
_STEP_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?\*{0,2}\s*Шаг\s*№\s*(\d+(?:\.\d+)*)", re.I)


def step_phrases(source_text: str) -> List[str]:
    """Номера шагов, объявленных фразой «Шаг №N» (заголовки/начала строк)."""
    seen, out = set(), []
    for ln in source_text.splitlines():
        m = _STEP_HEADING_RE.match(ln)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def step_markers_from_html(source_text: str) -> List[str]:
    """Составные номера шагов из HTML источника (strong + первые колонки)."""
    soup = BeautifulSoup(protect_token_tags(source_text), "html.parser")
    found: List[str] = []
    for el in soup.find_all("strong"):
        m = _STEP_TOKEN_RE.match(el.get_text(" ", strip=True))
        if m:
            found.append(m.group(1))
    for t in find_top_tables(source_text):
        for row in expand_grid(t)[1:]:
            if not row:
                continue
            m = _STEP_TOKEN_RE.match(_plain(row[0]).strip())
            if m:
                found.append(m.group(1))
    seen, out = set(), []
    for v in found:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def check_step_markers(card_text: str, source_text: str) -> Tuple[List[str], bool]:
    """Полнота маркеров шагов: каждый собранный из источника номер шага
    обязан присутствовать в карточке ДОСЛОВНО (номера — литералы;
    перенумерация и слияние шагов — потеря; инцидент src-locks:
    29 шагов источника «упакованы» в 22 своих при зелёном гейте)."""
    markers = step_markers_from_html(source_text)
    phrases = step_phrases(source_text)
    if len(markers) < 2 and len(phrases) < 2:
        return [], True
    norm_card = _norm_cell(card_text)
    # границы токена: «1.2» не должен «находиться» внутри «1.22»
    lost = [m for m in markers
            if not re.search(re.escape(m) + r"(?![.\d])", norm_card)]
    # шаги-фразы (К-23): в карточке обязано жить «шаг №N» (объявлением
    # или переходом) — полная потеря поведения даёт ноль вхождений
    if len(phrases) >= 2:
        # граница: «шаг №1» не должен находиться внутри «шаг №1.2», но
        # «шаг №1.» (точка-конец) — легален
        lost += [f"Шаг №{n}" for n in phrases
                 if not re.search(r"шаг\s*№?\s*" + re.escape(n)
                                  + r"(?!\.?\d)", norm_card)]
    if lost:
        return [f"маркеры шагов источника: в карточке отсутствуют "
                f"{len(lost)} из {len(markers)} ✗ НИЖЕ ПОРОГА (номера шагов — "
                f"литералы, перенумерация и слияние — потеря); примеры: "
                + ", ".join(lost[:5])], False
    return [f"маркеры шагов источника: все {len(markers)} на месте ✓"], True


# К-26 (2026-08-18): структура ТЕЛ шагов — по-шаговая сверка ранговых
# профилей с источником (fun-bnk-07: «Шаг №10 и все последующие
# предложения — один список», принадлежность уровней потеряна при
# зелёных гейтах; формула «процессные разделы — КАК ЕСТЬ»).
_STEP_DECL_RE = re.compile(
    r"^\s*(?:[-+*]\s+)?(?:#{1,6}\s*)?\*{0,2}\s*Шаг\s*№?\s*"
    r"(\d+(?:\.\d+)*)", re.I)
_TOP_HEADING_RE = re.compile(r"^#{1,4}\s+(?!Шаг)")


def _ranked_profile(lines: List[str]) -> List[str]:
    """Профиль тела: 'p' — абзац, 'liR' — пункт с РАНГОМ отступа
    (ширины отступов нормализуются в ранги: 0/4/8 и 0/2/4 сравнимы).

    Строки ТАБЛИЦ (md «|…|») и строки с HTML-разметкой (включая
    ОБЛОМКИ многострочных тегов — «…</strong></th>», «(сущность
    <a href=…») в профиль не входят (z06-fix ISS-03, FUN-CL-01:
    HTML-таблица источника против той же таблицы md в карточке —
    профили несопоставимы по построению, и несоответствие толкало
    исполнителя прятать маркеры шагов от парсера — обход). Профиль
    сверяет только текстовую структуру (абзацы/списки); содержимое
    таблиц держат сторожа значений. Кириллические <Атрибуты> — не
    HTML-теги, остаются в профиле. Перенос <br> — законная форма
    ветвления нотации (§1, FB-24 КК), не HTML-разметка: строка с ним
    остаётся в профиле своим видом (абзац/пункт)."""
    raw: List[Tuple[str, int]] = []
    widths = set()
    for ln in lines:
        s = ln.strip()
        if (not s or s.startswith("|")
                or re.search(r"</?[a-zA-Z][a-zA-Z0-9]*[ >/]|/>",
                             re.sub(r"(?i)<br\s*/?>", " ", s))):
            continue
        m = re.match(r"^( *)[-+*]\s", ln)
        if m:
            widths.add(len(m.group(1)))
            raw.append(("li", len(m.group(1))))
        else:
            raw.append(("p", -1))
    rank = {w: i for i, w in enumerate(sorted(widths))}
    return [t if t == "p" else f"li{rank[w]}" for t, w in raw]


def _step_bodies(lines: List[str]) -> Dict[str, List[str]]:
    """Тела шагов текста: от объявления «Шаг №N» до следующего
    объявления или верхнеуровневого заголовка."""
    out: Dict[str, List[str]] = {}
    cur: Optional[str] = None
    for ln in lines:
        m = _STEP_DECL_RE.match(ln)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
            continue
        if _TOP_HEADING_RE.match(ln):
            cur = None
            continue
        if cur is not None:
            out[cur].append(ln)
    return out


def _shift_profile(prof: List[str]) -> List[str]:
    """Ранговый профиль с базовым уровнем списка, приведённым к нулю
    (li1,li2 → li0,li1): сдвиг всех уровней на константу — артефакт
    конвертации выгрузки, не структура."""
    # базовый уровень — свой у каждого непрерывного блока списка: выгрузка
    # ведёт вложенный блок с отступом 4 (в markdown это код), а соседний
    # список в том же шаге — с нуля; карточка оба ведёт от нуля
    out: List[str] = []
    block: List[int] = []

    def flush() -> None:
        if block:
            base = min(block)
            out.extend(f"li{lvl - base}" for lvl in block)
            block.clear()

    for p in prof:
        if p.startswith("li") and p[2:].isdigit():
            block.append(int(p[2:]))
        else:
            flush()
            out.append(p)
    flush()
    return out


# FB-16 КК (решение владельца канона 2026-10-19): расхождение рангов тела шага —
# предупреждение, когда содержание шага на месте и вложенность условий не уменьшилась;
# брак — при уменьшении глубины вложенности условия (сплющивание, ЗК-18).
_COND_WORD_RE = re.compile(r"(?i)(?<![\w-])(?:если|иначе)(?![\w-])")
_STEP_LITERAL_RE = re.compile(r"«([^«»\n]+)»|\"([^\"\n]+)\"|<([^<>\n/][^<>\n]*)>")


def _cond_depths(lines: List[str]) -> List[int]:
    """Глубина каждого «если»/«иначе» тела шага по порядку: абзац — 0, пункт
    списка — ранг отступа внутри своего непрерывного блока списка + 1 (база блока
    — его наименьший отступ: ранги экспорта не влияют). Литералы в кавычках и
    строки таблиц не считаются."""
    items: List[Tuple[int, str]] = []  # (ширина отступа или -1, текст)
    for ln in lines:
        st = ln.strip()
        if not st or st.startswith("|"):
            continue
        m = re.match(r"^( *)[-+*]\s", ln)
        items.append((len(m.group(1)) if m else -1, st))
    out: List[int] = []
    k = 0
    while k < len(items):
        if items[k][0] < 0:
            t = re.sub(r'"[^"\n]*"|«[^»\n]*»', " ", items[k][1])
            out += [0] * len(_COND_WORD_RE.findall(t))
            k += 1
            continue
        j = k
        while j < len(items) and items[j][0] >= 0:
            j += 1
        rank = {w: i + 1 for i, w in enumerate(sorted({w for w, _ in items[k:j]}))}
        for w, t in items[k:j]:
            t = re.sub(r'"[^"\n]*"|«[^»\n]*»', " ", t)
            out += [rank[w]] * len(_COND_WORD_RE.findall(t))
        k = j
    return out


def _step_literals_kept(src_body: List[str], card_body: List[str]) -> bool:
    """Литералы шага источника («…», "…", <…>) — внутренним текстом в теле шага
    карточки (карточка вправе писать <Атрибут> источника как «Атрибут»)."""
    card = re.sub(r"\s+", " ", " ".join(card_body))
    for m in _STEP_LITERAL_RE.finditer(" ".join(src_body)):
        lit = next(g for g in m.groups() if g)
        # ссылка внутри литерала — её текстом: карточка снимает адреса Confluence
        lit = re.sub(r"\[((?:[^\[\]]|\\\[|\\\])*)\]\([^)]*\)", r"\1", lit).replace("\\[", "[").replace("\\]", "]")
        lit = re.sub(r"\s+", " ", lit).strip()
        if re.search(r"[a-zA-Z][a-zA-Z0-9]*[ >/=]", lit) and m.group(3):
            continue  # HTML-тег, не атрибут
        if lit and lit not in card:
            return False
    return True


def _max_list_depth(lines: List[str]) -> int:
    """Наибольшая глубина пункта списка тела шага (ранг внутри своего блока + 1;
    абзацы — 0): потеря вложенности пунктов без условий (fun-bnk-07, «все
    предложения — один список») остаётся браком."""
    depth, block = 0, []
    for ln in lines + [""]:
        st = ln.strip()
        if st.startswith("|"):
            continue
        m = re.match(r"^( *)[-+*]\s", ln) if st else None
        if m:
            block.append(len(m.group(1)))
            continue
        if block:
            depth = max(depth, len(set(block)))
            block = []
    return depth


def _step_form_only(src_body: List[str], card_body: List[str]) -> bool:
    """Расхождение — только форма экспорта: литералы на месте, число условий то же,
    глубина каждого условия и наибольшая глубина списка в карточке не меньше, чем в
    источнике."""
    ds, dc = _cond_depths(src_body), _cond_depths(card_body)
    return (_step_literals_kept(src_body, card_body) and len(ds) == len(dc)
            and all(c >= s for s, c in zip(ds, dc))
            and _max_list_depth(card_body) >= _max_list_depth(src_body))


def check_step_body_structure(card_text: str,
                              source_text: str) -> Tuple[List[str], bool]:
    """К-26: ранговый профиль тела КАЖДОГО шага карточки обязан
    совпадать с телом того же шага источника (md-источники; HTML-тела
    без md-разметки дают пустые профили — честный skip). Замены текстов
    ссылок профиль не меняют."""
    src_bodies = _step_bodies(_fm_body(source_text).splitlines())
    if len(src_bodies) < 2:
        return [], True
    card_bodies = _step_bodies(card_text.splitlines())
    bad: List[str] = []
    levels_only: List[str] = []
    form_only: List[str] = []
    for num, body in src_bodies.items():
        prof_src = _ranked_profile(body)
        if num not in card_bodies or not prof_src:
            continue  # полноту шагов держит К-23
        prof_card = _ranked_profile(card_bodies[num])
        if prof_src != prof_card:
            # FB-16 КК (2026-10-09): конвертированная HTML-выгрузка несёт
            # список с базовым отступом (li1 вместо li0) — сдвиг ВСЕХ
            # уровней на константу не меняет структуры; сравнение после
            # нормализации к нулевому базовому уровню. Уплощение
            # вложенности (li1 → li0 при соседях li0) структуру меняет и
            # ловится по-прежнему (К-24).
            if _shift_profile(prof_src) == _shift_profile(prof_card):
                levels_only.append(num)
            elif _step_form_only(body, card_bodies[num]):
                form_only.append(num)
            else:
                bad.append(num)
    report: List[str] = []
    if form_only:
        report.append(
            f"предупреждение: структура тел шагов расходится с источником при том же "
            f"содержании и не меньшей вложенности условий — шаги №{', №'.join(form_only[:5])}"
            + ("…" if len(form_only) > 5 else "")
            + " (ранги отступов экспорта, не потеря; брак — только при сплющивании "
            "условия или пропуске шага)")
    if levels_only:
        report.append(
            f"i структура тел шагов: базовый уровень отступа списка расходится "
            f"с источником при той же вложенности — шаги №{', №'.join(levels_only[:5])}"
            + ("…" if len(levels_only) > 5 else "")
            + " (ранговые уровни конвертированной выгрузки, не дефект)")
    if bad:
        return report + [f"структура тел шагов расходится с источником "
                         f"(уровни/принадлежность): шаги №{', №'.join(bad[:5])}"
                         + ("…" if len(bad) > 5 else "")
                         + " — тело шага переносится КАК ЕСТЬ с ранговыми "
                         "уровнями отступов ✗ НИЖЕ ПОРОГА"], False
    return report, True


# К-24 (2026-08-18): уплощение вложенности шагов. Источник ведёт
# многоуровневые списки (отступы 4/8/12/16 — правила, подусловия,
# расшифровки полей); правило шаблона «вложенность переносится
# структурой» без сторожа нарушалось молча (fun-bnk-08: 6 уровней
# источника → 2 в карточке, блоки-вставки выпали из своих шагов —
# находка пользователя). Формула переноса (решение 2026-08-18):
# процессные разделы источника переносятся КАК ЕСТЬ, без склейки.
def _list_indent_widths(lines: List[str]) -> set:
    """Множество ширин отступов списочных строк (маркеры -,+,*)."""
    return {len(m.group(1)) for ln in lines
            if (m := re.match(r"^( *)[-+*]\s", ln))}


def check_nesting_depth(card_text: str,
                        source_text: str) -> Tuple[List[str], bool]:
    src_w = _list_indent_widths(_fm_body(source_text).splitlines())
    card_w = _list_indent_widths(card_text.splitlines())
    if len(src_w) >= 4 and len(card_w) <= 2:
        return [f"вложенность шагов уплощена: источник ведёт "
                f"{len(src_w)} уровней списков, карточка — {len(card_w)} "
                "— уровни переносятся отступами (правило шаблона "
                "«вложенность — структурой», процессные разделы — КАК "
                "ЕСТЬ) ✗ НИЖЕ ПОРОГА"], False
    return [], True


def check_behavior_numbering(card_text: str) -> Tuple[List[str], bool]:
    """Самосогласованность карточки (работает и без --source):
    (1) каждая строка-шаг «Поведения» обязана быть элементом
    markdown-списка — иначе рендер склеит шаги в плоский абзац;
    (2) у точечной нумерации глубина номера (1.1.1 → 3) обязана
    совпадать с уровнем вложенности."""
    m = re.search(r"^##\s+Поведение\s*$(.*?)(?=^##\s|\Z)", card_text,
                  re.M | re.S)
    report: List[str] = []
    ok = True
    if m:
        prev_blank = True
        for ln in m.group(1).splitlines():
            if not ln.strip():
                prev_blank = True
                continue
            is_step = _marker_core(ln.strip()) is not None
            # склейка рендера — только у СМЕЖНЫХ строк: шаг-абзац,
            # отделённый пустыми строками, рендерится самостоятельно
            if (is_step and not prev_blank
                    and not _MD_LIST_ITEM_RE.match(ln)):
                report.append(
                    f"поведение: строка «{ln.strip()[:60]}» — не элемент "
                    "markdown-списка и прилипает к предыдущей: рендер склеит "
                    "шаги в плоский абзац ✗ (пункт создаёт маркер «-», "
                    "дословный маркер источника — текстом после него)")
                ok = False
            prev_blank = False
    for core, lvl in behavior_steps_from_card(card_text):
        if "." not in core:
            continue
        want = core.count(".")
        if lvl != want:
            report.append(
                f"поведение: шаг «{core}» — глубина номера {want + 1}, но "
                f"уровень отступа {lvl} ✗ (номер и структура расходятся)")
            ok = False
    return report, ok
