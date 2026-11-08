# app/scripts/CI/kitcheck/checks/card_passport.py
"""Проверки карточки: паспортные и тяжёлые ячейки, лейбл-секции.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import html
import re
from typing import List, Tuple
from ..html import _norm_cell, html_fragment_to_markdown, passport_cell_html
from ..md import table_cells
from .card_common import _LAYOUT_ROW_RE


def _fragment_profile(html: str) -> List[str]:
    """Структурный профиль фрагмента: ['p', 'li0', 'li1', …] — типы и
    глубины в порядке следования (замены текстов ссылок профиль не
    меняют — сверка структуры без ложняков на правиле трёх случаев)."""
    md = html_fragment_to_markdown(html)
    return _md_profile(md.splitlines())


def _md_profile(lines: List[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        mq = re.match(r"^((?:>\s*)+)", ln)
        if mq:
            out.append(f"q{mq.group(1).count('>')}")
            continue
        m = re.match(r"^( *)[-+*]\s", ln)
        if m:
            out.append(f"li{len(m.group(1)) // 2}")
        else:
            out.append("p")
    return out


# К-29 (2026-08-18): ИНВАРИАНТ вместо детекторов макета. Три обойдённых
# вариации обкладки за день (th / td+двоеточие / структура p-абзацами
# без ul) показали: перечислять макеты кодом — гонка вооружений
# (решение аналитика: сторожа — от инвариантов; семантика поиска полей —
# у исполнителя, он находит их безошибочно). Инвариант: ТЯЖЁЛАЯ ячейка
# источника не коллапсирует в |-строку карточки, каков бы ни был её
# лейбл и разметка. Порог тяжести — рычаг «строгость/скорость»:
# короткие правило-ячейки параметрических таблиц легитимно живут в
# строках и не флагуются.
_HEAVY_LEN = 600
_HEAVY_BLOCKS = 3


def heavy_source_cells(src_text: str) -> List[str]:
    """Тяжёлые ЗНАЧЕНИЯ ПАР «лейбл → значение»: строка <tr> ровно из
    двух ячеек (паспорт и подобные), второе — структурное/длинное.
    Ячейки многоколонных таблиц ДАННЫХ (описания параметров) легитимно
    живут в строках карточек и не собираются (боевой контроль: 26
    флагов первой версии — ложняки на колонках «Описание»)."""
    out: List[str] = []
    for m in re.finditer(
            r"<tr[^>]*>\s*<t[hd][^>]*>((?:(?!</?t[dr]).)*?)</t[hd]>\s*"
            r"<td([^>]*)>((?:(?!</td>).)*)</td>\s*</tr>",
            src_text, re.S):
        label, attrs, cell = m.group(1), m.group(2), m.group(3)
        # Пара «лейбл → значение» требует НЕПУСТОГО лейбла и значения без
        # colspan. Строка вида <td></td><td colspan="4">…</td> — это
        # растянутая строка многоколонной таблицы ДАННЫХ (образцы вызова
        # под строкой кода результата), а не паспорт: собирать её пары
        # функция не должна — см. абзац про ложняки на колонках «Описание».
        m_span = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
        if not re.sub(r"<[^>]+>", "", label).strip():
            continue
        if m_span and int(m_span.group(1)) > 1:
            continue
        # ячейка макетов (Figma/размерности) — структурная сверка не
        # применяется (решение 2026-08-31, README/main): ссылки макетов
        # живут в НЕсверяемом README-оглавлении группы, дословные ярлыки
        # («Размер XL - ссылка») ценности не несут; НАЛИЧИЕ ссылок в
        # README держит сторож figma-ссылок группы (selfcheck)
        if _LAYOUT_ROW_RE.search(cell):
            continue
        blocks = len(re.findall(r"<(?:p|ul|ol)\b", cell))
        if ("<ul" in cell or "<ol" in cell or len(cell) > _HEAVY_LEN
                or blocks >= _HEAVY_BLOCKS):
            out.append(cell)
    return out


def _table_widths(lines: List[str]) -> List[int]:
    """Для каждой |-строки — число колонок её таблицы (по первой строке блока |-строк)."""
    widths: List[int] = []
    cur = 0
    prev_table = False
    for ln in lines:
        is_table = ln.lstrip().startswith("|")
        if is_table:
            if not prev_table:
                cur = len(table_cells(ln.strip()))
            widths.append(cur)
        prev_table = is_table
    return widths


def check_heavy_cells(card_text: str,
                      src_text: str,
                      passport_rows_ok: bool = False) -> Tuple[List[str], bool]:
    """К-29: начало/середина содержимого тяжёлой ячейки не должны жить
    внутри одной |-строки карточки (пробы по трём смещениям — замена
    текста ссылки в одной из зон не прячет коллапс).

    Расплющивание — когда в ОДНОЙ |-строке найдены две пробы и больше, либо
    проба найдена в |-строке, а вне таблиц содержимого ячейки нет (ни одной
    пробы). Одна проба в строке при содержимом вне таблиц — совпадение
    фрагмента (имя метода в правиле заполнения, строка «Потребители»), а не
    коллапс: i-строка. Ложный ✗ на базовом контракте EXTINT-SVFE-002 (проба —
    имя метода из правила §2), замечание 2026-11-08.

    passport_rows_ok — карточка, у которой тяжёлая ячейка паспорта законно
    остаётся строкой двухколоночной таблицы «лейбл | значение» (базовый контракт
    внешней АС: шаблон contract-call.md, раздел A — «ячейки §1 в подразделы ради
    прибора не выводятся»). Тогда расплющивание в строке таблицы из двух колонок —
    i-строка; в таблицах параметров и справочников (три колонки и больше) — ✗."""
    heavy = heavy_source_cells(src_text)
    if not heavy:
        return [], True
    lines = card_text.splitlines()
    table_lines = [_norm_cell(ln) for ln in lines
                   if ln.lstrip().startswith("|")]
    if not table_lines:
        return [], True
    widths = _table_widths(lines)
    # текст вне таблиц одной строкой: пробы режутся по схлопнутому
    # содержимому и пересекают границы абзацев (как в check_heavy_pair_structure)
    flat_body = " ".join(
        t for t in (_norm_cell(re.sub(r"^[ \t]*[-+*] ", "", ln))
                    for ln in lines if not ln.lstrip().startswith("|"))
        if t)
    bad = 0
    sample = ""
    single = 0
    single_sample = ""
    passport = 0
    passport_sample = ""
    for cell in heavy:
        plain = _norm_cell(re.sub(r"^[ \t]*[-+*] ", "",
                                  html_fragment_to_markdown(cell),
                                  flags=re.M))
        if len(plain) < 120:
            continue
        probes = [p for p in (plain[0:40], plain[40:80],
                              plain[len(plain) // 2:len(plain) // 2 + 40])
                  if len(p) >= 30]
        in_rows = [sum(1 for p in probes if p in tl) for tl in table_lines]
        hits = [p for p in probes if any(p in tl for tl in table_lines)]
        if not hits:
            continue
        multi = [k for k, cnt in enumerate(in_rows) if cnt >= 2]
        if multi and passport_rows_ok and all(widths[k] == 2 for k in multi):
            passport += 1
            passport_sample = hits[0]
        elif multi or not any(p in flat_body for p in probes):
            bad += 1
            sample = hits[0]
        else:
            single += 1
            single_sample = hits[0]
    notes: List[str] = []
    if passport:
        notes.append(f"i тяжёлая ячейка паспорта перенесена строкой: {passport} (фрагмент: "
                     f"…{passport_sample[:50]!r}…) — строка таблицы «лейбл | значение» по шаблону "
                     "базового контракта, ячейки §1 в подразделы не выводятся")
    if single:
        notes.append(f"i К-29: фрагмент тяжёлой ячейки источника в строке md-таблицы ×{single} "
                     f"(фрагмент: …{single_sample[:50]!r}…) — одна проба из трёх, содержимое "
                     "ячейки есть вне таблиц: совпадение, не расплющивание")
    if bad:
        return (notes + [f"тяжёлая ячейка источника расплющена строкой md-таблицы "
                         f"×{bad} (фрагмент: …{sample[:50]!r}…) — содержимое "
                         "разворачивается в соответствующий РАЗДЕЛ ШАБЛОНА по "
                         "эталону конвертера (--cell-to-md «<лейбл ячейки>»), не "
                         "строкой таблицы ✗ НИЖЕ ПОРОГА"],
                False)
    return notes, True


# маркер контура в тексте пункта: «[O2+NEW]», «[КК_ВК]», «[ОНБ_2021]»
_CONTOUR_MARK_RE = re.compile(r"\[([^\[\]\n]{1,30})\]")
_LI_RE = re.compile(r"<li\b[^>]*>(?:(?!<li\b|</li>).)*</li>", re.S | re.I)


def _drop_foreign_items(cell: str, own: str) -> Tuple[str, int]:
    """Пункты списка ячейки страницы-копии метода, у которых первый маркер контура — не
    этого сервиса (основа маркера до «_» ≠ own), снимаются: чужие точки вызова (Р-1,
    решение владельца канона 2026-11-02; КК CALL-EXT-024/025). Пункт без маркера и со своим
    маркером остаётся. Вложенный пункт снимается вместе с родителем, сам по себе — нет."""
    n = 0

    def repl(m: "re.Match[str]") -> str:
        nonlocal n
        mark = _CONTOUR_MARK_RE.search(re.sub(r"<[^>]+>", "", m.group(0)))
        if mark and mark.group(1).split("_")[0].strip().upper() != own:
            n += 1
            return ""
        return m.group(0)

    return _LI_RE.sub(repl, cell), n


def check_heavy_pair_structure(card_text: str,
                               src_text: str,
                               own_contour: str = "") -> Tuple[List[str], bool]:
    """К-25d (обобщение): профиль КАЖДОЙ лейбл-секции тяжёлой пары
    (найденной по началу содержимого, лейбл безразличен) обязан
    начинаться профилем эталона конвертера — склейка абзацев в
    простыню видна как усечение профиля.

    own_contour — основа маркера сервиса (например «КК») у страницы-копии метода: пункты
    списков с чужим маркером контура из эталона снимаются (i-строка с числом)."""
    heavy = heavy_source_cells(src_text)
    if not heavy:
        return [], True
    dropped = 0
    if own_contour:
        cleaned = []
        for cell in heavy:
            c, k = _drop_foreign_items(cell, own_contour.upper())
            dropped += k
            cleaned.append(c)
        heavy = cleaned
    lines = card_text.splitlines()
    # пробы режутся по СХЛОПНУТОМУ содержимому ячейки и могут пересекать
    # границы абзацев эталона («Функция вызывается:» + список — проба
    # склейка двух блоков): построчный поиск требовал склеивать первые
    # строки секций и противоречил профилю — исполнитель подгонял текст
    # под прибор (дозаход 5.5-фикс, 2026-08-19). Ищем в конкатенате
    # не-табличных строк с маппингом позиции → строка старта.
    _offs: List[Tuple[int, int]] = []
    _parts: List[str] = []
    _pos = 0
    for _i, _ln in enumerate(lines):
        if _ln.lstrip().startswith("|"):
            continue
        # маркеры списков срезаются как при нарезке проб — иначе
        # проба «p+li» не совпадает со строкой «- …»
        _t = _norm_cell(re.sub(r"^[ \t]*[-+*] ", "", _ln))
        if not _t:
            continue
        _offs.append((_pos, _i))
        _parts.append(_t)
        _pos += len(_t) + 1
    flat_body = " ".join(_parts)
    bad = 0
    sample = ""
    report_notes: List[str] = []
    if dropped:
        report_notes.append(f"i чужие точки вызова страницы-копии: {dropped} снято (Р-1) — пункты "
                            "с маркером контура не этого сервиса в карточке не требуются")
    for cell in heavy:
        md = html_fragment_to_markdown(cell)
        expected = _md_profile(md.splitlines())
        if len(expected) < 3:
            continue
        # маркеры цитат «> » (перевод margin-left выгрузки) срезаются
        # при нарезке проб, как маркеры списков: в карточке цитаты
        # запрещены (вложенность — списками), и проба с «> » не
        # находилась никогда — quote-first ячейка сверялась по одной
        # средней пробе и падала при любой законной раскладке (FB-44
        # КК, fun-cl-33). Профиль expected берётся из md как есть.
        plain = _norm_cell(re.sub(r"^[ \t]*[-+*] ", "",
                                  re.sub(r"^[ \t]*(?:>[ \t]*)+", "", md,
                                         flags=re.M),
                                  flags=re.M))
        probes = [p for p in (plain[:40], plain[40:80],
                              plain[len(plain) // 2:len(plain) // 2 + 40])
                  if len(p) >= 30]
        if not probes:
            continue
        # сверка с ЛУЧШИМ вхождением, не с первым: начало ячейки
        # легитимно дублируется в «Назначении» (первые предложения
        # дословно — решение аналитика), полное содержимое — в
        # «Поведении»; сверка с первым вхождением флагала дубль и
        # спровоцировала подстройку формы (пилот 5.5, fun-sys-03)
        starts: List[int] = []
        for pr in probes:
            j = flat_body.find(pr)
            while j != -1:
                k = max((idx for off, idx in _offs if off <= j),
                        default=None)
                if k is not None and k not in starts:
                    starts.append(k)
                j = flat_body.find(pr, j + 1)
        starts.sort()
        start = starts[0] if starts else None
        if start is None:
            # ни одна проба не найдена вне таблиц: либо контент в
            # |-строке (зона check_heavy_cells), либо ПОТЕРЯН
            in_table = any(pr in tl for pr in probes
                           for tl in (_norm_cell(ln)
                                      for ln in lines
                                      if ln.lstrip().startswith("|")))
            if not in_table:
                bad += 1
                sample = probes[0]
            continue
        # граница секции — только заголовок или таблица: строки «**…**»
        # НЕ граница (внутри секций легитимны жирные «**ИНАЧЕ**» и
        # т.п. — ложная граница усекала профиль и спровоцировала обход
        # невидимым U+200B; сравнение префиксное, лишний хвост безвреден)
        matched = False
        listy = False
        for st in starts:
            section: List[str] = []
            for ln in lines[st:]:
                if ln.startswith("#") or ln.lstrip().startswith("|"):
                    break
                section.append(ln)
            actual = _md_profile(section)
            if (len(actual) >= len(expected)
                    and actual[:len(expected)] == expected):
                matched = True
                break
            # раскладка markdown-списком (решение владельца 2026-08-29,
            # README SCR-CL-01): канонная форма вложенности — списки с
            # жирной нотацией, а эталон конвертера несёт quote-абзацы
            # (перевод margin-left выгрузки) — профили расходятся
            # ЗАКОННО. Профильная сверка уступает: склейку в простыню
            # теперь ловят сторожа сплющивания (≥2 «если»/шаги/длина),
            # содержимое — сверка ячеек и литералов.
            if (sum(1 for a in actual[:max(len(expected), 1)]
                    if a.startswith("li")) >= len(expected) // 2):
                listy = True
        if listy and not matched:
            report_notes.append(
                "i тяжёлая пара разложена markdown-списком — профиль "
                "эталона конвертера (quote-абзацы) не требуется "
                "(решение 2026-08-29: канонная форма вложенности — "
                "списки); полноту держат сторожа содержимого")
            continue
        if not matched:
            bad += 1
            sample = probes[0]
    if bad:
        return (report_notes
                + [f"содержимое/структура тяжёлых пар расходится с "
                   f"эталоном конвертера ×{bad} (пример: "
                   f"…{sample[:45]!r}…) — содержимое ячейки "
                   "раскладывается в соответствующий раздел шаблона с "
                   "абзацами и уровнями КАК В ЭТАЛОНЕ "
                   "(--cell-to-md «<лейбл>») ✗ НИЖЕ ПОРОГА"], False)
    return report_notes, True


def check_passport_cell_structure(card_text: str,
                                  src_text: str) -> Tuple[List[str], bool]:
    """К-25: лейбл-секция «Что делает функция» обязана структурно
    совпадать с эталонной конвертацией ячейки источника (профиль
    «абзац/пункт@уровень» в порядке следования)."""
    # К-25d (2026-08-18): ul-ограничение снято — p-абзацные ячейки
    # сверяются тоже (fun-sys-03: шесть абзацев источника склеены в
    # один; профиль [p×6] vs [p×1] ловит склейку тривиально)
    cell = passport_cell_html(src_text)
    if cell is None:
        return [], True
    # секция: от отдельной строки-лейбла до следующего заголовка/таблицы
    lines = card_text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if "Что делает функция" in ln
                  and not ln.lstrip().startswith("|")), None)
    if start is None:
        return [], True  # отсутствие/таблица — ветки К-24/К-24b
    section: List[str] = []
    for ln in lines[start + 1:]:
        if ln.startswith("#") or ln.lstrip().startswith("|"):
            break
        section.append(ln)
    expected = _fragment_profile(cell)
    actual = _md_profile(section)
    if expected != actual:
        def _short(p: List[str]) -> str:
            s = ",".join(p[:12])
            return s + ("…" if len(p) > 12 else "")
        return [f"структура секции «Что делает функция» расходится с "
                f"ячейкой источника: эталон {len(expected)} элементов "
                f"[{_short(expected)}], в карточке {len(actual)} "
                f"[{_short(actual)}] — эталон даёт конвертер "
                "нормализатора (--cell-to-md) ✗ НИЖЕ ПОРОГА"], False
    return [], True


# --- К-34 (2026-08-19): лейбл-секции паспорта в карточках функций ---
#
# Решение аудита 2026-08-18: у шаблона function нет слота «паспорт» —
# лейблы ячеек источника («Что делает функция», «Как вызывается
# функция», «Доступность функции»…) НЕ переносятся, содержимое
# раскладывается по штатным разделам шаблона. Сторожа содержимого
# (пробы/профиль) размещение не видели — карточки со свалкой паспорта
# в «Назначении» стояли зелёными (вопрос аналитика по fun-sys-02).
# Инвариант — ПРОИСХОЖДЕНИЕ, не жирность: флагуется строка, дословно
# совпадающая с лейблом двухъячеечной пары источника (жирным абзацем
# или парой-таблицей); жирный текст ВНУТРИ значения ячейки
# («ПРИМЕЧАНИЯ!») — контент, переносится как есть и не флагуется.
# Только type: function — у data-model паспорт-таблица легитимна (Э-1).

_PAIR_LABEL_RE = re.compile(
    r"<tr[^>]*>\s*<t[hd][^>]*>((?:(?!</?t[dr]).)*?)</t[hd]>\s*<td",
    re.S | re.I)


def source_pair_labels(src_text: str) -> set:
    labels = set()
    for m in _PAIR_LABEL_RE.finditer(src_text):
        lbl = re.sub(r"<[^>]+>", " ", m.group(1))
        lbl = re.sub(r"\s+", " ", lbl).strip().strip(":").strip()
        if len(lbl) >= 6:
            labels.add(lbl)
    return labels


def check_label_sections(card_text: str,
                         src_text: str) -> Tuple[List[str], bool]:
    labels = source_pair_labels(src_text)
    if not labels:
        return [], True
    bad: List[str] = []
    for ln in card_text.splitlines():
        s = ln.strip()
        m = re.fullmatch(r"\*\*([^*]+?)\*\*", s)
        if m is None:
            m = re.match(r"\|\s*\*\*([^*|]+?)\*\*\s*\|", s)
        if m is None:
            continue
        t = m.group(1).strip().strip(":").strip()
        if t in labels:
            bad.append(t)
    if not bad:
        return [], True
    uniq = sorted(set(bad))
    return [f"К-34 лейбл-секции паспорта источника ×{len(bad)} "
            f"({', '.join(repr(t) for t in uniq[:4])}) — лейблы ячеек "
            "источника в карточку функции не переносятся (ни жирной "
            "строкой, ни парой-таблицей): содержимое раскладывается в "
            "соответствующий РАЗДЕЛ ШАБЛОНА ✗ НИЖЕ ПОРОГА"], False
