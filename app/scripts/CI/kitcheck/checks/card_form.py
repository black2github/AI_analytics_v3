# app/scripts/CI/kitcheck/checks/card_form.py
"""Проверки карточки: форма текста — разорванные ячейки, маркеры сокращения, гомоглифы,
невидимые символы, выноски, блоки кода, длинные строки, нотация.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import html
import re
from typing import List, Optional, Tuple
from .. import fence as _fence
from ..md import blank_code, code_line_flags, count_cells, table_cells
from ..html import _fm_body, _fm_head, _norm_cell, parse_md_tables
from .card_common import _norm_ws, blank_table_breaks


# нотация §2–§3, кандидаты автопроверок §9 — предупреждения, не авто-фикс
# (выбор между присваиванием и сравнением — смысловое решение)
_NOT_QUOTED_RE = re.compile(r'«[^»\n]*»|"[^"\n]*"|`[^`\n]*`')
_NOT_LINK_URL_RE = re.compile(r"\]\([^)]*\)")
_NOT_SINGLE_EQ_RE = re.compile(r"(?<![=!<>:])=(?![=>])")
_NOT_COND_START_RE = re.compile(r"\*\*(?:Если|ЕСЛИ|если|Иначе если|ИНАЧЕ ЕСЛИ|иначе если)\*\*")
_NOT_COND_END_RE = re.compile(r"\*\*(?:то|ТО|То)\b|,\s*то\b")
_NOT_NEXT_RE = re.compile(r"\*\*Далее:?\*\*:?(.*)")
_NOT_ARROW_OK_RE = re.compile(r"по ключу|найти|запис|Далее", re.I)
# (д) угловые скобки: HTML-теги (латинское имя тега) — не имена; имя начинается с буквы
_NOT_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?/?>")
_NOT_ANGLE_RE = re.compile(r"<([^<>\n]{1,80})>")
# закрытый словарь UI-типов полей (notation §4, базовый набор); «Тип» реестра
# полей ЭФ сверяется без уточнения в скобках и без регистра
_UI_TYPES = frozenset((
    "текст", "число", "пароль", "поиск", "дата", "список",
    "список с множественным выбором", "переключатель", "чекбокс",
    "блок загрузки", "сумма", "иконка", "гиперссылка", "текст со ссылками",
    "заголовок"))


def check_notation_hints(text: str) -> List[str]:
    """Предупреждения нотации (ПР-02 разбора замечаний ОНБ-В): одиночный «=»
    в условии — ожидается «==» (§2); обратная стрелка «←» — не используется
    ни в одном значении (§3). Дословные литералы в кавычках, inline-код,
    блоки кода и адреса ссылок не проверяются."""
    body = _fm_body(text)
    eq_hits: List[str] = []
    back_hits: List[str] = []
    fwd_hits: List[str] = []
    type_hits: List[str] = []
    angle_bare: List[str] = []
    angle_dotted = 0
    hdr: Optional[List[str]] = None
    body_lines = body.splitlines()
    for ln, in_code in zip(body_lines, code_line_flags(body_lines)):
        st = ln.strip()
        if in_code:
            continue
        # таблицы: заголовок запоминается, строка-разделитель пропускается
        if st.startswith("|"):
            cells = table_cells(st)
            if hdr is None:
                hdr = [re.sub(r"\*\*", "", c).strip().lower() for c in cells]
                continue
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                continue
            # (г) «Тип» реестра полей ЭФ — словарь нотации §4; таблица
            # сообщений («ID | Тип | Показ») — не реестр полей
            if "тип" in hdr and "поле" in hdr and len(cells) == len(hdr):
                v = re.sub(r"\*\*|`", "", cells[hdr.index("тип")]).strip().strip(".")
                vn = re.sub(r"\s*\([^)]*\)\s*$", "", v).strip().lower().replace("ё", "е")
                if vn and vn not in ("—", "-") and vn not in _UI_TYPES:
                    type_hits.append(v[:40])
        else:
            hdr = None
        clean = _NOT_LINK_URL_RE.sub("]", _NOT_QUOTED_RE.sub(" ", ln))
        if "←" in clean:
            back_hits.append(st[:60])
        # (д) угловые скобки — только подстановки в дословных текстах (§7);
        # строки таблиц параметров (заголовок с «параметр») не проверяются
        if not (st.startswith("|") and hdr and any("параметр" in h for h in hdr)):
            ang = _NOT_HTML_TAG_RE.sub(" ", clean)
            for m in _NOT_ANGLE_RE.finditer(ang):
                inner = m.group(1).strip()
                if not re.match(r"[A-Za-zА-Яа-яЁё]", inner):
                    continue
                if ang[:m.start()].rstrip().endswith("."):
                    angle_dotted += 1  # [Сущность].<Атрибут> — к замене на «…»
                else:
                    angle_bare.append(f"<{inner[:40]}>")
        # (в) «→» — только поиск записи по ключу («→ [Сущность]…») и переходы
        # «Далее»; исключение — таблица связей шаблона модели данных
        # (колонка «Связь»: «Заявка → История изменений») — противоречие
        # шаблона и нотации на решении владельца канона
        if ("→" in clean and not _NOT_ARROW_OK_RE.search(clean)
                and not (st.startswith("|") and hdr and "связь" in hdr)):
            if any(not clean[m.end():].lstrip().startswith("[")
                   for m in re.finditer("→", clean)):
                fwd_hits.append(st[:60])
        hit = False
        for m in _NOT_COND_START_RE.finditer(clean):
            seg = clean[m.end():]
            e = _NOT_COND_END_RE.search(seg)
            if _NOT_SINGLE_EQ_RE.search(seg[:e.start()] if e else seg):
                hit = True
                break
        if not hit:
            nm = _NOT_NEXT_RE.search(clean)
            if nm:
                hit = any("→" in part and _NOT_SINGLE_EQ_RE.search(part.split("→")[0])
                          for part in nm.group(1).split(";"))
        if hit:
            eq_hits.append(st[:60])
    out: List[str] = []
    if eq_hits:
        out.append(f"предупреждение: нотация — одиночный «=» в условии ×{len(eq_hits)} "
                   "(в условиях сравнение — «==», notation §2); первые: "
                   + "; ".join(repr(x) for x in eq_hits[:3]))
    if back_hits:
        out.append(f"предупреждение: нотация — обратная стрелка «←» ×{len(back_hits)} "
                   "(не используется ни в одном значении, notation §3; присваивание — «=» "
                   "с источником справа); первые: " + "; ".join(repr(x) for x in back_hits[:3]))
    if fwd_hits:
        out.append(f"предупреждение: нотация — стрелка «→» вне поиска записи по ключу ×{len(fwd_hits)} "
                   "(notation §3: последовательность — шагами, переход между экранами — «=>», "
                   "маппинг — «=» или словами); первые: " + "; ".join(repr(x) for x in fwd_hits[:3]))
    if angle_bare:
        out.append(f"предупреждение: нотация — имя в угловых скобках без сущности ×{len(angle_bare)} "
                   "(§7: угловые скобки — только подстановки в дословных текстах; атрибут — "
                   "[ENT-…](…).«Атрибут»)"
                   + (f"; ещё в форме [Сущность].<…> ×{angle_dotted} — к замене на «…»"
                      if angle_dotted else "")
                   + "; первые: " + "; ".join(repr(x) for x in angle_bare[:3]))
    if type_hits:
        out.append(f"предупреждение: нотация — «Тип» реестра полей вне словаря UI-типов ×{len(type_hits)} "
                   "(notation §4: Текст, Число, Дата, Список, Чекбокс, Гиперссылка…); первые: "
                   + "; ".join(repr(x) for x in type_hits[:3]))
    return out


_MARKER_CONTEXT_WORDS = 3


def _marker_hits_verbatim_in_source(card_text: str, marker: str,
                                    source_text: str) -> int:
    """Сколько вхождений маркера в карточке стоят в источнике дословно
    вместе с контекстом — соседними словами той же строки (до
    _MARKER_CONTEXT_WORDS перед маркером и столько же после; суммарно
    не меньше _MARKER_CONTEXT_WORDS, иначе не милуется — консервативно:
    «- и т.д.» отдельным пунктом списка остаётся замечанием). Вид
    кавычек («» / "") в сравнении не различается — чистовик меняет их
    по конвенциям, текст от этого не становится сокращением."""
    def _n(s: str) -> str:
        return _norm_ws(re.sub(r"[«»“”„]", '"', s))
    # снимаются только HTML-теги (имя с латинской буквы): подстановка
    # «<Текст ошибки не пройденного контроля>» в источнике — текст, он
    # есть и в карточке (proc-002 стенда)
    src = _n(html.unescape(re.sub(r"</?[A-Za-z][^>]*>", " ", source_text)))
    hits = 0
    low = card_text.casefold()
    for m in re.finditer(re.escape(marker), low):
        line_start = low.rfind("\n", 0, m.start()) + 1
        line_end = low.find("\n", m.end())
        line_end = len(low) if line_end == -1 else line_end
        strip_md = lambda s: re.sub(  # noqa: E731
            r"^\s*(?:[-*+]|\d+[.)])\s+", " ", re.sub(r"[*_`|]", " ", s))
        before = strip_md(card_text[line_start:m.start()]).split()
        after = strip_md(card_text[m.end():line_end]).split()
        if not before:
            # маркер открывает пункт списка («- и т.д.» после «- Ошибка 2:
            # <…>», proc-002 стенда): в источнике он продолжает ту же
            # ячейку — контекст берётся из предыдущей непустой строки
            prev = [ln for ln in card_text[:line_start].splitlines()
                    if ln.strip()]
            if prev:
                before = strip_md(prev[-1]).split()
        before, after = (before[-_MARKER_CONTEXT_WORDS:],
                         after[:_MARKER_CONTEXT_WORDS])
        # два кандидата: только слова ДО (маркер закрывает ячейку —
        # дальше в карточке уже соседняя ячейка) и ДО+ПОСЛЕ (маркер в
        # начале строки)
        cands = []
        if len(before) >= _MARKER_CONTEXT_WORDS:
            cands.append(before + [marker])
        if len(before) + len(after) >= _MARKER_CONTEXT_WORDS:
            cands.append(before + [marker] + after)
        if any(_n(" ".join(c)) in src for c in cands):
            hits += 1
    return hits


# Сплющивание атрибутов ЭФ (z04 ISS-03, FLD-29 «Места жительства»;
# расширено по замечаниям владельца на дозаходе: «При нажатии» с
# клееными шагами, «Формат» FLD-13 простынёй, недоразложенные
# элементы списков): вложенные условия/шаги/перечни источника,
# выпрямленные в одну строку, — дерево нечитаемо, реализация
# недостоверна. Значение, разложенное подсписком, в строке метки
# текста не несёт и не флагается (конструкция, не запрет).
# Кавычечные литералы и КОРОТКИЕ скобочные вставки («(если было
# заполнено)») из подсчёта исключены; длинная скобка с целым
# ветвлением (ФИАС-перечень FLD-29) остаётся в подсчёте.
_flat_attrs = (r"Логика установки значения|Видимость|Источник списка|"
               r"По умолчанию|При нажатии|Формат|Способ заполнения")

def _cond_count(s: str) -> int:
    s = re.sub(r'"[^"\n]*"|«[^»\n]*»', " ", s)
    s = re.sub(r"\([^()\n]{0,60}\)", " ", s)
    return len(re.findall(r"\bесли\b", s, re.I))

_attr_line_re = re.compile(
    rf"^\s*-\s+\*\*({_flat_attrs})[^\n:]*:\*\*(.+)$", re.M)


def _fc_torn_table_cells(fx: "_FileCtx") -> Tuple[List[str], bool]:
    lines, = fx.lines,
    report: List[str] = []
    ok = True
    # Голый текст, зажатый МЕЖДУ строками таблицы, — разорванная ячейка:
    # перенос строки внутри ячейки (вместо <br>) выталкивает её хвост из
    # таблицы (инцидент 6-дец: агент разнёс название и разрезал строку).
    # Fenced-блоки — вне зоны действия (notation §«вне зоны»): PlantUML
    # activity внутри ``` несёт свимлейны «|Система|» и шаги «:6 …;» —
    # для сторожа они выглядели таблицей с зажатым текстом (4 ложняка
    # process-файлов эталона, разбор ✗ 2026-08-21).
    _fenced = {k for k, c in enumerate(code_line_flags(lines)) if c}
    for k, ln in enumerate(lines):
        if k in _fenced:
            continue
        s = ln.strip()
        if not s or s.startswith("|") or s.startswith("#"):
            continue
        prev_is_pipe = (k > 0 and k - 1 not in _fenced
                        and lines[k - 1].strip().startswith("|"))
        nxt = next((lines[j].strip() for j in range(k + 1, len(lines))
                    if lines[j].strip() and j not in _fenced), "")
        if prev_is_pipe and nxt.startswith("|"):
            ok = False
            report.append(
                f"строка {k + 1}: голый текст между строками таблицы — "
                f"разорванная ячейка (перенос внутри ячейки должен быть <br>) "
                f"✗ НИЖЕ ПОРОГА: {s[:70]!r}")
    return report, ok


def _fc_blank_line_table_breaks(fx: "_FileCtx") -> Tuple[List[str], bool]:
    lines, = fx.lines,
    report: List[str] = []
    ok = True
    # К-16 (2026-08-17): ПУСТАЯ строка внутри pipe-таблицы рвёт её —
    # общий скан blank_table_breaks (используется и для служебных
    # реестров: матрица inkasso несла разрыв с захода 4 — служебные
    # файлы шли мимо check_file, находка пользователя 2026-08-17).
    for k in blank_table_breaks(lines):
        ok = False
        report.append(
            f"строка {k}: пустая строка разрывает таблицу — хвост "
            "рендерится плоским текстом (продолжение таблицы — без "
            "пустых строк) ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_shortening_markers(fx: "_FileCtx") -> Tuple[List[str], bool]:
    source_text, soft_markers, text = fx.source_text, fx.soft_markers, fx.text
    report: List[str] = []
    ok = True
    # Порядок колонок справочников НЕ проверяется: решение пользователя
    # 2026-08-09 — переносится как в источнике (дословность; целевое
    # переформатирование — работа поздних слоёв, не миграции).
    # Р-8 (2026-08-22): в командном профиле (selfcheck по умолчанию)
    # маркеры — предупреждение: на эталоне детектор дал 3/3 ложняков
    # («и т. д.» в описании колонки README, «фрагмент текста ПФ»,
    # scope-примечание). В полном профиле (--strict, наши прогоны) — ✗.
    # FB-09 «Корпоративных карт» (2026-10-05): маркер, стоящий в
    # источнике дословно («…отличного от месяца/квартала и т.д.» в
    # ячейке описания), — текст спецификации, а не сокращение
    # переносчика; без помилования карточке предъявлялись два
    # взаимоисключающих требования (полнота ячеек ✗ ↔ маркер ⚠/✗).
    # Помилование — по КОНТЕКСТУ (слова перед маркером в той же
    # строке), а не по счёту: «и т.д.» источника в одном месте не
    # покрывает сокращение перечня в другом.
    for marker in ("фрагмент", "см. источник", "и т.д.", "и т. д."):
        cnt = text.lower().count(marker)
        if cnt and source_text:
            pardoned = _marker_hits_verbatim_in_source(text, marker,
                                                       source_text)
            if pardoned:
                report.append(
                    f"маркер «{marker}» ×{pardoned} дословно из источника "
                    "(контекст совпадает) — сокращением не считается")
                cnt -= pardoned
        if cnt:
            # прогон без выгрузки (selfcheck без --sources) — об источнике
            # не говорим, его нет (трек rules, срез 3)
            if soft_markers and fx.without_sources:
                report.append(
                    f"предупреждение: маркер сокращения «{marker}» ×{cnt} — "
                    f"проверьте, что перечень приведён целиком")
            elif soft_markers:
                report.append(
                    f"предупреждение: маркер сокращения «{marker}» ×{cnt} — "
                    f"проверьте, что справочники и перечни источника "
                    f"перенесены целиком")
            else:
                ok = False
                report.append(
                    f"маркер сокращения «{marker}» ×{cnt}: справочники и "
                    f"перечни источника переносятся ЦЕЛИКОМ, без «фрагментов» "
                    f"✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_html_comments(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # К-13 (2026-08-17, анти-маскировка): HTML-коммент в чистовике.
    # Контрольный дозаход вскрыл обход гейта значений: агент экзамена
    # спрятал значения источника в <!-- selfcheck-coverage: … --> — сверка
    # «находила» их в невидимом комменте, потеря содержимого зеленела.
    # Правило канона «гейт закрывается ПЕРЕНОСОМ, а не упоминанием» —
    # теперь с сторожем: чистовику служебные комменты не положены вовсе
    # (черновые пометки запрещены шаблонами; фон 4 стендов: 0 легальных).
    cmts = re.findall(r"<!--.*?-->", text, re.S)
    if cmts:
        ok = False
        report.append(
            f"HTML-коммент в чистовике ×{len(cmts)}: служебные пометки и "
            "списки значений в комментах запрещены — гейт закрывается "
            "переносом содержимого, не упоминанием (обход = маскировка "
            f"потери) ✗ НИЖЕ ПОРОГА: {cmts[0][:60]!r}")
    return report, ok


def _fc_param_code_row_numbers(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # К-12 (2026-08-17): номера строк в колонке «Код параметра» —
    # суррогат (контрольный дозаход: fun-cl-03/18/20 получили «1», «2.1»
    # вместо пустых кодов). Правило волны B: технических имён источник
    # не даёт → «Код параметра» ПУСТОЙ; собственная нумерация источника —
    # отдельной дословной колонкой, не кодом.
    for i, (headers, rows) in enumerate(parse_md_tables(text)):
        hkeys = [h.strip().lower() for h in headers]
        if "код параметра" not in hkeys:
            continue
        ci = hkeys.index("код параметра")
        bad = [r[ci].strip().strip("`").strip() for r in rows
               if ci < len(r)
               and re.fullmatch(r"\d+(\.\d+)*",
                                r[ci].strip().strip("`").strip())]
        if bad:
            ok = False
            report.append(
                f"таблица {i}: «Код параметра» содержит номера строк "
                f"×{len(bad)} ({', '.join(bad[:3])}) — суррогат: источник "
                "технических имён не даёт → код ПУСТОЙ, нумерация "
                "источника — отдельной дословной колонкой ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_notation_hints(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # нотация (ПР-02 разбора замечаний ОНБ-В, 2026-10-16): предупреждения
    report.extend(check_notation_hints(text))
    return report, ok


def _fc_invisible_chars(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # К-30 (2026-08-18): невидимые символы в чистовике — брак. Дозаход
    # 5.3 вставил U+200B в «**ИНАЧЕ**», чтобы обойти ложную границу
    # секций сторожа (граница починена, но класс «невидимый юникод как
    # обход» сторожится навсегда: в карточках ему места нет).
    inv = sum(text.count(ch) for ch in ("​", "‌", "‍",
                                        "⁠", "﻿"))
    if inv:
        ok = False
        report.append(
            f"невидимые символы (zero-width/BOM) ×{inv} в чистовике — "
            "не содержимое и типовой обход сторожей ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_homoglyphs(fx: "_FileCtx") -> Tuple[List[str], bool]:
    source_text, text = fx.source_text, fx.text
    report: List[str] = []
    ok = True
    # К-31 (2026-08-19): гомоглифы — латиница внутри кириллического
    # слова (и наоборот) невидима читателю и тихо выключает
    # распознавание (пилот-2: «Kратность» с латинской K лишила колонку
    # роли «кратн» и валидации). Класс К-30: невидимая подмена.
    # Источники чистые (проверено), в честных переносах смешанных слов
    # нет; дефис/цифры слово разделяют — «md-файл», «Ф1» легитимны.
    # слово сразу после «\» — эскейп-последовательность («\nИПИ» в
    # метках PlantUML), не гомоглиф: ложняк вёл исполнителя «чинить»
    # легитимные \n (восстановительный дозаход 2026-08-19; замена на
    # реальные переводы строк в метках PlantUML эквивалентна — но
    # флагов быть не должно)
    mixed = sorted({m.group(0) for m in re.finditer(r"[^\W\d_]+", text)
                    if (m.start() == 0 or text[m.start() - 1] != "\\")
                    and re.search(r"[а-яёА-ЯЁ]", m.group(0))
                    and re.search(r"[a-zA-Z]", m.group(0))})
    # помилование (z03 ISS-03, кнопка «ОK» с кириллической О): слово,
    # ДОСЛОВНО пришедшее из кавычечного литерала источника, — данные
    # автора, не подмена; дословность сильнее гигиены (тот же принцип,
    # что source_literals у колонных ролей). Обход разметкой («О**K**»)
    # больше не нужен и не легален.
    if mixed and source_text:
        # FB-16/FB-20 КК (2026-10-09/14): слово с гомоглифом, дословно
        # стоящее в ТЕКСТЕ источника (тег «[КК_BК]», литерал
        # getCardFeeСounters), — данные автора, не подмена; раньше
        # миловались только слова из кавычечных литералов, и дословный
        # перенос бракуется за дословность. Сторож дефейса тега (К-32)
        # не ослабляется: он сверяет тег с источником отдельно.
        src_words = {w.group(0)
                     for w in re.finditer(r"[^\W\d_]+", _fm_body(source_text))}
        pardoned = [w for w in mixed if w in src_words]
        mixed = [w for w in mixed if w not in src_words]
        if pardoned:
            report.append(
                f"i гомоглифы ×{len(pardoned)} помилованы — дословно из "
                f"источника ({', '.join(repr(w) for w in pardoned[:3])})")
    if mixed:
        ok = False
        report.append(
            f"гомоглифы/смешанное письмо в словах ×{len(mixed)} "
            f"({', '.join(repr(w) for w in mixed[:5])}) — латиница внутри "
            "кириллического слова (или наоборот) невидима читателю и "
            "выключает распознавание — класс невидимых подмен К-30 "
            "✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_empty_tables(fx: "_FileCtx") -> Tuple[List[str], bool]:
    lines, = fx.lines,
    report: List[str] = []
    ok = True
    # пустая pipe-таблица-заглушка («| | |» без содержимого) — мусор
    # генераторных правок (Назначение fun-sys-07, 5.5-фикс): читателю
    # не видна, содержимого не несёт
    empty_tables = sum(
        1 for ln in lines
        if re.fullmatch(r"\|[\s|]*\|", ln.strip())
        and not re.fullmatch(r"\|[\s:|-]*-[\s:|-]*\|", ln.strip()))
    if empty_tables:
        ok = False
        report.append(
            f"пустая строка-заглушка pipe-таблицы ×{empty_tables} "
            "(«| | |» без содержимого) — мусор правок, убрать "
            "✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_separator_columns(fx: "_FileCtx") -> Tuple[List[str], bool]:
    lines, = fx.lines,
    report: List[str] = []
    ok = True
    # Сепаратор md-таблицы с числом колонок ≠ заголовку (реестр
    # контролей после консолидации d10, найдено владельцем 2026-08-29:
    # колонки групп сократили, сепаратор не подрезали): GFM при
    # расхождении НЕ рендерит таблицу вовсе — весь блок читается плоским
    # текстом; парсер прибора толерантен, рендер строг — класс
    # «структура в байтах ≠ структура в рендере».
    for _i in range(len(lines) - 1):
        _h, _s = lines[_i].strip(), lines[_i + 1].strip()
        if (_h.startswith("|") and _h.endswith("|")
                and re.fullmatch(r"\|[\s:|-]*-[\s:|-]*\|", _s)):
            _nh = count_cells(_h)
            _ns = count_cells(_s)
            if _nh != _ns:
                ok = False
                report.append(
                    f"сепаратор таблицы: {_ns} колонок против {_nh} в "
                    f"заголовке ({_h[:40]!r}…) — GFM таблицу не "
                    "отрендерит, блок читается плоским текстом "
                    "✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_flattened_attributes(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # помощники _flat_attrs, _cond_count, _attr_line_re — на уровне модуля
    for m in _attr_line_re.finditer(text):
        attr, tail = m.group(1), m.group(2)
        conds = _cond_count(tail)
        steps_glued = len(re.findall(r"\bШаг\s+\d+\.", tail))
        vis_len = len(_norm_cell(tail))
        if conds >= 2:
            ok = False
            report.append(
                f"сплющенный атрибут «{attr}»: {conds} условия "
                "«если» одной строкой — вложенное ветвление источника "
                "выпрямлено в простыню; переложить markdown-списком с "
                "уровнями вложенности источника ✗ НИЖЕ ПОРОГА")
        elif steps_glued >= 2:
            ok = False
            report.append(
                f"сплющенный атрибут «{attr}»: {steps_glued} шага "
                "склеены одной строкой — разложить по шагам "
                "markdown-списком ✗ НИЖЕ ПОРОГА")
        elif vis_len > 300:
            ok = False
            report.append(
                f"сплющенный атрибут «{attr}»: значение видимой длиной "
                f"{vis_len} символов одной строкой (длина видимая — без "
                "адресов ссылок; порог 300) — разложить "
                "markdown-списком по смысловым частям ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_undecomposed_lines(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # Недоразложенные строки тех же секций (замечание владельца: в
    # FLD-29 разложен только первый блок, ФИАС-перечень с вложенным
    # условием остался строкой li; z05 B-1 scr-bnk-02: абзац-продолжение
    # под пустым ярлыком — обходная конструкция того же класса): ≥2
    # «если» в ЛЮБОЙ строке зоны — ветвление не довскрыто. Строки-метки
    # атрибутов проверены первым проходом и здесь пропускаются.
    zones_re = re.compile(r"^###\s+(?:FLD|EV|B|MSG)-.*$", re.M)
    for zm in zones_re.finditer(text):
        z_end = re.search(r"^#{2,3}\s", text[zm.end():], re.M)
        zone_txt = text[zm.end():zm.end() + z_end.start()] if z_end \
            else text[zm.end():]
        for ln in zone_txt.splitlines():
            if _attr_line_re.match(ln):
                continue
            conds = _cond_count(ln)
            if conds >= 2:
                ok = False
                report.append(
                    f"сплющенная строка ({zm.group(0).strip()}): "
                    f"{conds} условия «если» одной строкой — вложенное "
                    "ветвление не довскрыто; разложить подсписком "
                    f"({ln.strip()[:60]!r}…) ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_long_lines(fx: "_FileCtx") -> Tuple[List[str], bool]:
    source_text, amnesty_text, lines = fx.source_text, fx.amnesty_text, fx.lines
    report: List[str] = []
    ok = True
    # Длинные строки тела (решение владельца 2026-08-29, README
    # SCR-CL-01: «Части» и зонтичные точки контролей простынями):
    # перечень одной строкой вне таблиц — сплющенный список, тот же
    # класс, что атрибутные простыни, но порог выше (легальные абзацы
    # прозы длиннее атрибутов). Длина видимая (_norm_cell); дословные
    # кавычечные цитаты (тексты сообщений) не считаются; строки таблиц,
    # заголовки и код пропускаются; атрибутные строки покрыты своим
    # порогом выше.
    # FB-19 КК (2026-10-13): амнистия дословности — по ОБЪЕДИНЕНИЮ всех
    # страниц карточки (amnesty_text), не только главной: дословные
    # абзацы дочерних страниц мультистраничной карточки бракуются иначе
    src_norm_full = _norm_cell(
        (source_text or "") + "\n" + (amnesty_text or "")) \
        if (source_text or amnesty_text) else None
    for ln, in_code in zip(lines, code_line_flags(lines)):
        s = ln.strip()
        if (in_code or not s or s.startswith("|") or s.startswith("#")
                or _attr_line_re.match(ln)):
            continue
        vis = len(_norm_cell(re.sub(r'"[^"\n]*"|«[^»\n]*»', " ", ln)))
        if vis > 500:
            # помилование дословности: строка, целиком присутствующая
            # в источнике, — форма САМОГО источника (сплошной абзац
            # юридического текста согласия, дословное описание), не
            # склейка переносом; сплющивание — только то, что в
            # источнике было структурой или собрано агентом
            if src_norm_full and _norm_cell(ln) in src_norm_full:
                continue
            ok = False
            report.append(
                f"строка видимой длиной {vis} символов вне таблицы "
                "(длина видимая — без адресов ссылок и текста в кавычках; "
                "порог 500) — "
                "сплющенный перечень/список одной строкой, разложить "
                f"(начало: {s[:50]!r}…) ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_readme_main_roles(fx: "_FileCtx") -> Tuple[List[str], bool]:
    md_path, text = fx.md_path, fx.text
    report: List[str] = []
    ok = True
    # README/main (решения владельца 2026-08-30/31): README группы
    # экранной формы — чистое оглавление БЕЗ frontmatter и БЕЗ разделов
    # карточки (вне сверки по Р-9; принцип «один факт — один дом»);
    # главная карточка экрана — scr-…-nn-main.md с ID экрана: дословное
    # назначение, шапка, открытие/закрытие, события/кнопки/сообщения
    # уровня страницы, контроли уровня формы. README с frontmatter
    # screen-form, несущий предметные секции, — старая структура: ⚠ до
    # структурного захода, сторож тиража после него.
    if (md_path.name.lower() == "readme.md"
            and re.search(r"^type:\s*screen-form\s*$", _fm_head(text), re.M)
            and re.search(r"^###\s+(?:FLD|EV|B|MSG)-", text, re.M)):
        report.append(
            "предупреждение: README группы ЭФ несёт предметные секции "
            "(FLD/EV/B/MSG) — README — чистое оглавление (решения "
            "2026-08-30/31), содержимое уровня страницы живёт в главной "
            "карточке scr-…-nn-main.md")
    return report, ok


def _fc_pseudo_screen_form(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # Псевдо-ЭФ (z06 ISS-03, SCR-CL-05 «Процедура сохранения»):
    # карточка screen-form без единого отображаемого поля — операционная
    # функция, натянутая на шаблон формы (шаблон screen-form сам
    # предписывает серверную логику выносить в function; фиктивное поле
    # с «Видимость: не отображается (серверная процедура)» — натяжка
    # типа). ⚠-кандидат на смену типа; решение — владельца.
    if re.search(r"^type:\s*screen-form\s*$", _fm_head(text), re.M):
        _vis = re.findall(r"^\s*-\s+\*\*Видимость:\*\*\s*(.+)$", text,
                          re.M)
        if _vis and all(re.search(r"не отображается|серверн", v, re.I)
                        for v in _vis):
            report.append(
                "предупреждение: screen-form без единого отображаемого "
                "поля (все «Видимость» — «не отображается») — "
                "операционная функция в шаблоне формы? кандидат на "
                "смену типа function (решение владельца)")
    return report, ok


def _fc_figma_mockups(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # Макеты Figma (решение владельца 2026-08-29, отмена запрета
    # 2026-08-14): URL макета — единственная связь аналитики с макетом
    # и обязан переноситься; раздел «Макеты» без единой figma-ссылки —
    # сигнал приёмке (не ✗: у части форм макетов в источнике нет).
    if (re.search(r"^type:\s*screen-form\s*$", _fm_head(text), re.M)
            and re.search(r"^#+\s.*Макеты", text, re.M)
            and "figma.com" not in text.lower()):
        report.append(
            "предупреждение: раздел «Макеты» без единой ссылки Figma — "
            "URL макетов обязаны переноситься (решение 2026-08-29), "
            "вернуть из источника")
    return report, ok


_GLOSSARY_TYPE_RE = re.compile(r"^type:\s*['\"]?glossary['\"]?\s*$", re.M)


def _fc_blockquote_indented_code(fx: "_FileCtx") -> Tuple[List[str], bool]:
    lines, = fx.lines,
    report: List[str] = []
    ok = True
    # Blockquote и отступные код-блоки в чистовике (README SCR-CL-01,
    # рецидив CALL-INT-001 c01 2026-08-31): конвертер --cell-to-md
    # переводит margin-left выгрузки в цитаты «>» и глубокие отступы —
    # в рендере это «заметки» на сером фоне и код-блоки, а не
    # вложенность; вложенность переносится СПИСКАМИ (канонная форма,
    # решение 2026-08-29/31). Эталон конвертера — эталон СОДЕРЖИМОГО,
    # не формы (сторож тяжёлых пар li-раскладку принимает).
    # строки внутри блока кода — текст примера, не цитата
    _code = code_line_flags(lines)
    # глоссарий: выноску-делегирование «> Полный справочник … — в …»
    # предписывает шаблон glossary.md (решение владельца канона
    # 2026-10-30) — сторож выносок к type: glossary не применяется;
    # отступные код-блоки сторожатся по-прежнему
    _bq = (0 if _GLOSSARY_TYPE_RE.search(_fm_head(fx.text)) else
           sum(1 for ln, code in zip(lines, _code)
               if not code and ln.lstrip().startswith(">")))
    if _bq:
        ok = False
        report.append(
            f"blockquote «>» ×{_bq} в чистовике — в рендере это цитаты-"
            "«заметки», а не вложенность; переложить вложенными "
            "списками с жирной нотацией (эталон --cell-to-md — эталон "
            "содержимого, не формы) ✗ НИЖЕ ПОРОГА")
    _codey = 0
    for _i in range(1, len(lines)):
        ln = lines[_i]
        if _code[_i]:
            continue  # fenced-блоки (mermaid и пр.) — легальный код
        if (re.match(r"^ {4,}\S", ln)
                and re.search(r"[а-яА-ЯёЁ]|\*\*", ln)
                and not lines[_i - 1].strip()
                and (_i < 2 or not re.match(r"^\s*(?:[-*+]|\d+\.)\s",
                                            lines[_i - 2]))
                and not ln.lstrip().startswith("|")):
            _codey += 1
    if _codey:
        ok = False
        report.append(
            f"отступный код-блок с текстом ×{_codey} — строки с "
            "отступом ≥4 вне списка рендерятся моноширинным кодом, "
            "разметка внутри не работает; переложить списками "
            "✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_unclosed_code_blocks(fx: "_FileCtx") -> Tuple[List[str], bool]:
    lines, = fx.lines,
    report: List[str] = []
    ok = True
    # Блок кода, не закрытый по правилам GitLab (решение владельца
    # 2026-10-17, правило kitcheck/fence.py): закрывающее ограждение с
    # инфо-строкой (опечатка ```text … ```text) прибор засчитывает закрытием,
    # чтобы текст ниже оставался под проверками, но в рендере GitLab блок не
    # закрыт — дальше всё код; незакрытый блок прячет хвост карточки так же.
    # Структура в байтах расходится со структурой в рендере — брак, как у
    # цитат и голых HTML-тегов.
    for i in _fence.issues(lines):
        ok = False
        if i.kind == "close-with-info":
            report.append(
                f"строка {i.line}: блок кода закрыт ограждением с инфо-строкой "
                f"(строка {i.close_line}) — в GitLab это не закрытие, дальше "
                "всё код; закрыть голым ``` того же вида и длины, вложенный "
                "пример обернуть внешним ```` ✗ НИЖЕ ПОРОГА")
        else:
            report.append(
                f"строка {i.line}: блок кода не закрыт до конца файла — в "
                "GitLab дальше всё код; закрыть ограждением того же вида и "
                "длины ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_invisible_html_tags(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # Невидимые в рендере HTML-теги (z04 ISS-03, B-5 «Выберите файл»):
    # голый ASCII-плейсхолдер размерности экрана — для рендера тег:
    # <S> зачёркивает документ до конца (незакрыт), неизвестные (<XS>,
    # <M>) исчезают молча — «структура в байтах ≠ структура в рендере».
    # Кириллические <Атрибуты> тегами не парсятся и легальны; <br> —
    # намеренный перенос в ячейках. Форма переноса — бэктики: `<S>`.
    nohtml = blank_code(text)
    nohtml = re.sub(r"`[^`\n]*`", " ", nohtml)
    tagish = sorted({m.group(0) for m in re.finditer(
        r"</?[A-Za-z][A-Za-z0-9-]*\s*/?>", nohtml)
        if m.group(0).strip("</> \t").rstrip("/").lower() != "br"})
    if tagish:
        ok = False
        report.append(
            f"голые HTML-теговидные плейсхолдеры ×{len(tagish)} "
            f"({', '.join(tagish[:5])}) — в рендере это HTML-теги: "
            "<S> зачёркивает всё до конца документа, неизвестные "
            "исчезают молча; угловые ASCII-плейсхолдеры переносить "
            "в бэктиках ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_screen_form_condition_notation(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # Нотация условий в секциях ЭФ (z04 ISS-03): канон — **Если** X,
    # **то** Y, **иначе** Z; голые «если/иначе» в зонах FLD/EV/B/MSG —
    # предупреждение (не вердикт: легальные обороты в тексте возможны,
    # асимметрия — лучше шум, чем молчаливо потерянная нотация).
    # Кавычечные литералы, скобочные вставки и строки условной
    # обязательности («Да, если не заполнено…») исключены.
    zones = list(re.finditer(r"^###\s+(?:FLD|EV|B|MSG)-.*$", text, re.M))
    plain_cond = 0
    for zm in zones:
        z_end = re.search(r"^#{2,3}\s", text[zm.end():], re.M)
        zone = text[zm.end():zm.end() + z_end.start()] if z_end \
            else text[zm.end():]
        zone = "\n".join(ln for ln in zone.splitlines()
                         if not re.match(r"\s*-\s+\*\*Обязательность",
                                         ln))
        zone = re.sub(r'"[^"\n]*"|«[^»\n]*»|`[^`\n]*`|\([^()\n]*\)',
                      " ", zone)
        for w in re.finditer(r"\b[Ее]сли\b|\b[Ии]наче\b", zone):
            if not (zone[max(0, w.start() - 2):w.start()] == "**"
                    and zone[w.end():w.end() + 2] == "**"):
                plain_cond += 1
    if plain_cond:
        report.append(
            f"предупреждение: нотация условий — «если/иначе» без "
            f"жирного ×{plain_cond} в секциях FLD/EV/B/MSG (канон: "
            "**Если** X, **то** Y, **иначе** Z)")
    return report, ok


def _fc_confluence_ui_artifacts(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # К-28 (2026-08-18): артефакты интерфейса Confluence из выгрузки
    # («Развернуть исходный код» — кнопка сворачивания код-блока) — не
    # содержимое, в чистовик не переносятся (fun-bnk-07: втянут в
    # простыню шага). Список расширяемый.
    for ui in ("Развернуть исходный код", "Скрыть исходный код"):
        cnt = text.count(ui)
        if cnt:
            ok = False
            report.append(
                f"артефакт интерфейса Confluence «{ui}» ×{cnt} в "
                "чистовике — элемент UI выгрузки, не содержимое "
                "✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_stub_card(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # К-27 (2026-08-18): карточка-заглушка вне правил. Заглушки канон
    # разрешает только карточкам вызова чужих контрактов (contract-call;
    # legacy-тип external-integration — стенды до модели CALL 2026-08-20)
    # и записям PLT; ЭФ — по своему шаблону. Рецидив rbac: дозаход
    # пересоздал заглушку и вписал RBAC-001 в матрицу — легализация
    # обошла К-21/К-22 (решение аналитика из разового промпта не
    # персистентно, сторожим класс).
    m_t = re.search(r"^type:\s*([\w-]+)", text[:600], re.M)
    if (m_t and m_t.group(1) not in
            ("contract-call", "external-integration", "screen-form")
            and re.search(r"(?mi)^\s*(?:документ-)?заглушка"
                          r"(?:\s+комплекта)?\s*[:.]", text)):
        ok = False
        report.append(
            "карточка-заглушка вне правил: заглушки предписаны только "
            "CALL/PLT/ЭФ — отсутствующая цель фиксируется долгом в "
            "матрице, артефакт чужого типа не заводится ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_strikethrough_marker(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # Н-7 (2026-08-17): «%зачёркнуто%» — постфиксный маркер ВЫГРУЗКИ:
    # зачёркнут ПРЕДЫДУЩИЙ фрагмент (текст неактуален). В чистовик маркер
    # не переносится — переносится семантика (~~…~~ / пометка
    # «Неактуален»). Инцидент scr-cl-02: маркер прочитан наоборот, смысл
    # шага инвертирован («шаг исключается» принято за действующее).
    cnt = len(re.findall(r"%зач[её]ркнуто%", text, re.I))
    if cnt:
        ok = False
        report.append(
            f"маркер выгрузки «%зачёркнуто%» ×{cnt}: в чистовик не "
            "переносится (постфикс — зачёркнут ПРЕДЫДУЩИЙ фрагмент; "
            "переносить семантику: зачёркнутое = неактуально) ✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_duplicate_headers(fx: "_FileCtx") -> Tuple[List[str], bool]:
    column_roles, text = fx.column_roles, fx.text
    report: List[str] = []
    ok = True
    # К-10 (волна B, Э-10): повторяющийся НЕПУСТОЙ заголовок в шапке
    # таблицы карточки — сетка-протяжка нормализатора перенесена как
    # формат («Название параметра ×3», fun-cl-03/18/20 экзамена);
    # лесенка уровней сводится в одну колонку с номерами. Протяжки в
    # СТРОКАХ ДАННЫХ легальны и не проверяются.
    if column_roles:
        for i, (headers, _rows) in enumerate(parse_md_tables(text)):
            keys = [h.strip() for h in headers if h.strip()]
            dups = {k for k in keys if keys.count(k) > 1}
            if dups:
                ok = False
                report.append(
                    f"таблица {i}: повторяющиеся заголовки в шапке "
                    f"({', '.join(sorted(dups)[:2])}) — сетка-протяжка "
                    "нормализатора не переносится: уровни сводятся в одну "
                    "колонку, иерархию несёт «Код параметра»-путь "
                    "✗ НИЖЕ ПОРОГА")
    return report, ok


def _fc_fun_call_token(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # Волна A (Э-12): вызов FUN-CL/FUN-BNK всегда идёт по токену с
    # проверкой привилегий — «Доступность» без их упоминания означает
    # недоработку источника. ПРЕДУПРЕЖДЕНИЕ, не брак (решение
    # аналитика: подсветка старым комплектам — честный долг).
    m_id = re.search(r"^id:\s*FUN-(CL|BNK)-", text[:600], re.M)
    if m_id:
        m_sec = re.search(r"##\s*(?:\d+\.\s*)?Доступность\b(.*?)(?=\n## |\Z)",
                          text, re.S)
        sec = m_sec.group(1) if m_sec else ""
        if not re.search(r"привилег|прав[оа]?\s+доступа|роль", sec,
                         re.I | re.S):
            report.append(
                "предупреждение: FUN-CL/BNK без упоминания привилегий/прав "
                "в «Доступности» (вызов всегда по токену с проверкой "
                "привилегий) — недоработка источника, нужен открытый "
                "вопрос ⚠")
    return report, ok
