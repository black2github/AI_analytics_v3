# app/scripts/CI/kitcheck/checks/card_passport.py
"""Проверки карточки: паспортные и тяжёлые ячейки, лейбл-секции.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import html
import re
from typing import List, Tuple
from ..html import _norm_cell, html_fragment_to_markdown, passport_cell_html
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


def check_heavy_cells(card_text: str,
                      src_text: str) -> Tuple[List[str], bool]:
    """К-29: начало/середина содержимого тяжёлой ячейки не должны жить
    внутри одной |-строки карточки (пробы по трём смещениям — замена
    текста ссылки в одной из зон не прячет коллапс)."""
    heavy = heavy_source_cells(src_text)
    if not heavy:
        return [], True
    table_lines = [_norm_cell(ln) for ln in card_text.splitlines()
                   if ln.lstrip().startswith("|")]
    if not table_lines:
        return [], True
    bad = 0
    sample = ""
    for cell in heavy:
        plain = _norm_cell(re.sub(r"^[ \t]*[-+*] ", "",
                                  html_fragment_to_markdown(cell),
                                  flags=re.M))
        if len(plain) < 120:
            continue
        probes = [plain[0:40], plain[40:80],
                  plain[len(plain) // 2:len(plain) // 2 + 40]]
        for probe in probes:
            if len(probe) < 30:
                continue
            if any(probe in tl for tl in table_lines):
                bad += 1
                sample = probe
                break
    if bad:
        return ([f"тяжёлая ячейка источника расплющена строкой md-таблицы "
                 f"×{bad} (фрагмент: …{sample[:50]!r}…) — содержимое "
                 "разворачивается в соответствующий РАЗДЕЛ ШАБЛОНА по "
                 "эталону конвертера (--cell-to-md «<лейбл ячейки>»), не "
                 "строкой таблицы ✗ НИЖЕ ПОРОГА"],
                False)
    return [], True


def check_heavy_pair_structure(card_text: str,
                               src_text: str) -> Tuple[List[str], bool]:
    """К-25d (обобщение): профиль КАЖДОЙ лейбл-секции тяжёлой пары
    (найденной по началу содержимого, лейбл безразличен) обязан
    начинаться профилем эталона конвертера — склейка абзацев в
    простыню видна как усечение профиля."""
    heavy = heavy_source_cells(src_text)
    if not heavy:
        return [], True
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
    for cell in heavy:
        md = html_fragment_to_markdown(cell)
        expected = _md_profile(md.splitlines())
        if len(expected) < 3:
            continue
        plain = _norm_cell(re.sub(r"^[ \t]*[-+*] ", "", md, flags=re.M))
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
