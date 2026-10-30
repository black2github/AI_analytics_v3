# app/scripts/CI/kitcheck/checks/card_source.py
"""Проверки карточки: литералы и источник — кавычечные литералы, сверка таблиц и
значений, полнота ячеек, title, имена параметров HTML.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import re
from typing import Dict, List, Optional, Tuple
from .. import fence as _fence
from ..html import (
    _BR_RE, _fm_body, _norm_cell, _plain, _title_key, expand_grid, find_top_tables,
    parse_md_tables
)
from ..columns import _COLUMN_RULES, _is_section_row, validate_columns
from .card_common import _LAYOUT_ROW_RE


# Буквы-двойники кириллицы и латиницы (после приведения к нижнему регистру;
# н/в/т/м/к — от прописных Н/В/Т/М/К). Сверки «значение источника есть в
# карточке» (таблицы источника, кавычечные литералы, полнота ячеек) их не
# различают — свёртка применяется к ОБЕИМ сторонам только в момент
# сравнения, роли колонок и тексты замечаний видят исходные буквы
# (OQ-134 «Корпоративных карт», 2026-10-07): по политике помилования
# гомоглифов (OQ-22 КК, 2026-09-24) гомоглиф источника исправляется в
# карточке по алфавиту-носителю слова, источник не правится — и дословная
# сверка таблиц читала исправленную ячейку «== CLOSE» как потерю строки
# «== СLOSE». Детектор смешанного письма К-31 этим не ослабляется: он
# смотрит на сам текст карточки.
_HOMOGLYPH_FOLD = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "к": "k", "н": "h", "в": "b", "т": "t", "м": "m", "і": "i", "ј": "j",
    "ѕ": "s", "ё": "e",
})


_CONFLUENCE_URL_RE = re.compile(r"https?://[^\s)\]]*confluence[^\s)\]]*", re.I)


def _fold_homoglyphs(s: str) -> str:
    return s.translate(_HOMOGLYPH_FOLD)


# Значение-вложение: markdown-ссылка на приложенный файл Confluence. В base-
# карточку такие ссылки легитимно НЕ переносятся (место примеров — sidecar
# examples/, конвенция скилла) — сверка наличия их пропускает.
_ATTACHMENT_RE = re.compile(r"\]\(/download/attachments/", re.IGNORECASE)


# Токен-имя параметра: латинский идентификатор, возможно составной путь
# (JSON через точку, XML через слэш, заголовки через дефис).
_NAME_TOKEN_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:[./\-\[\]][A-Za-z0-9_\[\]]+)*$")
# Слова, похожие на имена, но имена параметров не являющиеся (типы, методы,
# форматы) — их отсутствие в карточке потерей не считается.
_TOKEN_STOP = frozenset({
    "get", "post", "put", "delete", "patch", "rest", "soap", "json", "xml",
    "true", "false", "null", "body", "string", "uuid", "guid", "int",
    "integer", "boolean", "bool", "number", "object", "array", "multipart",
    "bearer", "base64", "utf", "http", "https", "id", "api", "sync", "async",
    "clob", "blob", "timestamp", "date", "datetime",
})


def html_param_names(source_text: str) -> set:
    """Имена параметров из СЫРЫХ HTML-таблиц источника (первые две колонки
    раскрытой сетки): file_id, upload_token, Content-Type…

    Нужны для --check --source: гейт проверял валидность колонок карточки,
    но НЕ полноту HTML-таблиц источника — потеря строки (file_id и
    upload_token в MFlash «Подготовка к загрузке», 2026-08-12) проходила
    зелёным. Каждый найденный токен обязан присутствовать в карточке."""
    names: set = set()
    for t in find_top_tables(source_text):
        grid = expand_grid(t)
        # Таблица заполнения полей из «Логики работы метода» («поле |
        # значение», вложена в ячейку шаговой таблицы) — не сетка
        # параметров контракта: её имена (storage_type…) в карточку не
        # требуются (OQ-033 file-storage, intc-035, 2026-08-14).
        if grid and [_plain(c).strip().lower() for c in grid[0][:2]] == ["поле", "значение"]:
            continue
        # Таблица-паспорт функции («**Код привилегии:** | CLIENT_CONTRACT_VIEW», skillCore P2
        # FUN-CL-02, 2026-10-29) — «лейбл | значение», не сетка параметров: значение
        # паспорта (имя константы) требовалось как имя параметра, а шаблон function.md берёт
        # код привилегии из rbac.md — проходила только карточка с вписанной константой.
        # Признак — тот же, что у сверки значений (passport_kind). Ограничитель: лейбл,
        # похожий на имя параметра («**file_id**» — сетка без шапки с жирными именами), паспорт
        # не делает — такая таблица сторожится по-прежнему.
        if grid and passport_kind(grid[0], grid[1:]) and not any(
                _NAME_TOKEN_RE.match(_plain(r[0]).strip().strip("*:` ").strip())
                for r in grid if r and r[0].strip()):
            continue
        for row in grid[1:]:
            for cell in row[:2]:
                v = _plain(_BR_RE.sub(" ", cell)).strip().strip("`").strip()
                if (2 < len(v) <= 64 and " " not in v
                        and _NAME_TOKEN_RE.match(v)
                        and v.lower() not in _TOKEN_STOP):
                    names.add(v)
    return names


# ── Сторож полноты ячеек источника (COM-01 Корпкарт, 2026-08-27) ──
# Класс тихой потери: при выносе перечислений в справочник исполнитель
# отбрасывал ХВОСТ ячейки («допустимый алфавит…», «входит в составной
# ключ», определение атрибута), заменяя его ссылкой. Дословность —
# механический прокси сохранения смысла: иерархия и разметка при
# переносе свободны (HTML-ячейка легально расщепляется на карточку и
# справочник), но каждый фрагмент исходной ячейки обязан найтись в
# тексте комплекта в нормальной форме.

_COVER_HDR_KEYS = ("тип", "описан", "коммент")
_COVER_SPLIT_RE = re.compile(r"(?<=[.;:])\s+")
_COVER_QUOTES_RE = re.compile(r"[\"'«»„“”]")
_COVER_DASH_RE = re.compile(r"[–—−]")
# пара «CODE - расшифровка»: значение перечисления, разложенное автором
# прямо в ячейке; в комплекте живёт строкой таблицы справочника
_COVER_PAIR_RE = re.compile(r"^([a-z0-9_./-]+)\s*[-:]\s*(.+)$")
_COVER_LATIN_RE = re.compile(r"^[a-z0-9_./\- ]+$")
_COVER_MIN = 6  # нормализованных символов; короче — «да», «—», обрывки


def _cover_norm(v: str) -> str:
    """Нормальная форма сверки полноты: поверх _norm_cell гасятся
    типографские кавычки и тире (карточка вправе печатать «…», источник
    — "…"; лексика важна, типографика — нет)."""
    v = _COVER_QUOTES_RE.sub(" ", _norm_cell(v))
    v = _COVER_DASH_RE.sub("-", v)
    return re.sub(r"\s+", " ", v).strip(" .,;:-")


# Хвост-пример удаляется из карточек ПО ПРАВИЛУ шаблона — его отсутствие
# в комплекте потерей не считается (иначе гейт зажимал бы исполнителя
# между правилом и сверкой — прецедент OQ-029)
_COVER_EXAMPLE_RE = re.compile(
    r"(?<![а-яёa-z])(пример[ы]?|например)\b.*$", re.I | re.S)
# Ссылочная конструкция источника («Ссылка на идентификатор записи
# справочника X», «Объект типа X») в карточке легально становится
# EXT/ENT-ссылкой — служебные слова конструкции не сверяются, сверяется
# название цели
_COVER_REF_HEAD_RE = re.compile(r"^(ссылка на|объект типа)\b")
_COVER_REF_STOP = frozenset({
    "ссылка", "на", "идентификатор", "записи", "запись", "справочника",
    "справочник", "сущности", "сущность", "объект", "типа", "тип"})


def _cover_fragments(cell: str) -> List[str]:
    """Нарезка ячейки: по <br>, затем по границам предложений и «:»;
    хвосты-примеры отрезаются до нарезки (шаблон предписывает их
    удаление из карточек). НОРМАЛИЗАЦИЯ — ДО нарезки: markdown-ссылка
    с двоеточием в тексте («[[СпрВал] Модель данных: Валюта](url)»)
    резалась пополам, и правая половина тащила сырой URL в требуемые
    фрагменты — гейт требовал то, что запрещает правило чистовика
    (блокер ISS-01, найден исполнителем, 2026-08-27)."""
    frags: List[str] = []
    for chunk in _BR_RE.split(cell):
        chunk = _COVER_EXAMPLE_RE.sub("", _cover_norm(chunk))
        for part in _COVER_SPLIT_RE.split(chunk):
            part = part.strip(" .,;:-")
            if len(part) >= _COVER_MIN:
                frags.append(part)
    return frags


def _window_covered(frag: str, corpus: str) -> bool:
    """Все слова фрагмента по порядку в ОДНОЙ ячейке/абзаце корпуса:
    терпит вставку служебных слов переносом («…в соответствии СО
    СТАТУСНОЙ МОДЕЛЬЮ „X“»), но не россыпь слов по разным местам —
    окно обрезается ближайшей границей ячейки « | »."""
    tokens = [t for t in frag.split() if len(t) >= 3]
    if len(tokens) < 2:
        return False
    first = tokens[0]
    start, hits = 0, 0
    while hits < 20:
        pos = corpus.find(first, start)
        if pos < 0:
            return False
        hits += 1
        start = pos + 1
        window = corpus[pos:pos + len(frag) + 80]
        cell_end = window.find(" | ")
        if cell_end != -1:
            window = window[:cell_end]
        wpos = 0
        for t in tokens:
            i = window.find(t, wpos)
            if i < 0:
                break
            wpos = i + len(t)
        else:
            return True
    return False


def _fragment_covered(frag: str, corpus: str, corpus_ns: str) -> bool:
    # корпус свёрнут по буквам-двойникам при построении (OQ-134); фрагмент
    # сворачивается ТОЛЬКО в момент сравнения — разбор его формы
    # (конструкция «ссылка на …», пары «код - расшифровка») идёт по
    # исходным буквам
    f = _fold_homoglyphs
    if f(frag) in corpus or f(frag).replace(" ", "") in corpus_ns:
        return True
    if _COVER_REF_HEAD_RE.match(frag):
        rest = [t for t in re.findall(r"[\wёа-я-]+", frag)
                if len(t) >= 3 and t not in _COVER_REF_STOP]
        if rest and all(f(t) in corpus for t in rest):
            return True
    if _window_covered(f(frag), corpus):
        return True
    # фрагмент из запятых-частей: каждая часть — подстрокой, парой
    # «код - расшифровка» (разложено в таблицу справочника) или
    # латинским перечнем значений (разложено по строкам)
    for part in (p.strip(" .,;:-") for p in frag.split(",")):
        if len(part) < _COVER_MIN or f(part) in corpus \
                or f(part).replace(" ", "") in corpus_ns:
            continue
        m = _COVER_PAIR_RE.match(part)
        if m and f(_cover_norm(m.group(1))) in corpus \
                and f(_cover_norm(m.group(2))) in corpus:
            continue
        if _COVER_LATIN_RE.match(part) and all(
                f(t) in corpus for t in part.split() if len(t) >= 2):
            continue
        if _window_covered(f(part), corpus):
            continue
        return False
    return True


def check_cell_coverage(source_text: str,
                        corpus_text: str) -> Tuple[List[str], bool]:
    """Каждый фрагмент непустых ячеек «Тип»/«Описание»/«Комментарии»
    строк данных источника должен быть покрыт текстом комплекта в
    нормальной форме. Секционные строки и повторы шапки — не данные."""
    corpus = _fold_homoglyphs(_cover_norm(corpus_text))
    corpus_ns = corpus.replace(" ", "")
    lost: List[str] = []
    checked = 0
    for t in find_top_tables(source_text):
        grid = expand_grid(t)
        if len(grid) < 2:
            continue
        header = grid[0]
        hdr_keys = [_title_key(h) for h in header]
        cols = [i for i, h in enumerate(hdr_keys)
                if any(k in h for k in _COVER_HDR_KEYS)]
        if not cols:
            continue
        name_idx = next((i for i, h in enumerate(hdr_keys)
                         if "наимен" in h or "назван" in h or "атрибут" in h
                         or "параметр" in h or "поле" in h), None)
        hdr_norm = [_cover_norm(c) for c in header]
        for r in grid[1:]:
            if _is_section_row(r) or [_cover_norm(c) for c in r] == hdr_norm:
                continue
            label = (_norm_cell(r[name_idx])[:40]
                     if name_idx is not None and name_idx < len(r) else "?")
            for i in cols:
                if i >= len(r) or not r[i].strip():
                    continue
                for frag in _cover_fragments(r[i]):
                    checked += 1
                    if not _fragment_covered(frag, corpus, corpus_ns):
                        lost.append(f"строка «{label}», колонка "
                                    f"«{_norm_cell(header[i])[:24]}»: "
                                    f"не покрыт фрагмент {frag[:90]!r}")
    if lost:
        return ([f"полнота ячеек источника: потеряно {len(lost)} из "
                 f"{checked} фрагментов ✗ НИЖЕ ПОРОГА (хвост ячейки "
                 "Тип/Описание обязан быть покрыт текстом комплекта "
                 "дословно; ссылка на справочник дополняет, не заменяет)"]
                + [f"   {ln}" for ln in lost[:12]]
                + ([f"   … и ещё {len(lost) - 12}"] if len(lost) > 12
                   else []), False)
    return ([f"полнота ячеек источника: фрагментов {checked}, "
             "потерь 0 ✓"], True)


# Кавычечные литералы источника: тексты в «ёлочках» и прямых кавычках —
# сообщения пользователю, названия кнопок, значения-константы. Свободный
# текст вне таблиц построчно не сверяется — перефраз и сокращения
# проходили зелёными (src-locks: пояснение категорий сокращено, буква
# «жестко»→«жёстко»); литералы — механизируемая часть класса: каждый
# обязан присутствовать в карточке дословно. Полные описания так не
# защитить (там законна адаптация формата) — только кавычечные литералы.
_QUOTED_RE = re.compile(r"[«\"]([^«»\"\n]{2,80})[»\"]")
_QUOTED_SKIP_RE = re.compile(
    r"figma|confluence|download/attachments|https?://", re.IGNORECASE)
# отсев HTML-атрибутов и путей, попадающих в прямые кавычки сырого HTML
# (href="../…", class="…"): литерал текстоподобен — без разметочных символов
_QUOTED_MARKUP_RE = re.compile(r"[<>=/\\{}\[\]|`;]|&\w+")


def _source_headings(body: str) -> set:
    """Нормализованные заголовки разделов страницы: кавычечная отсылка на
    СВОЙ раздел («см. "Фильтры ЭФ"») — навигация по структуре источника,
    карточка переструктурирована по шаблону — не требуется."""
    hs = set()
    for m in re.finditer(r"^#{1,6}\s+(.+)$", body, re.M):
        hs.add(_norm_cell(m.group(1)))
    for m in re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>", body,
                         re.I | re.S):
        hs.add(_norm_cell(m.group(1)))
    return hs


_FLK_EXAMPLE_HDR_RE = re.compile(r"\s*(флк|пример)")
_EXAMPLE_MARK_RE = re.compile(r"(?<![а-яё])пример[ы]?\s*[:.]", re.I)


def _flk_example_cells(body: str) -> List[str]:
    """Нормализованные тексты ячеек колонок «ФЛК» / «Пример(ы)» всех
    таблиц источника (md и HTML-сетки) — их содержимое в модель не
    переносится (К-18, Э-3), кавычечный сторож его не требует."""
    out: List[str] = []

    def take(headers: List[str], rows: List[List[str]]) -> None:
        idx = [i for i, h in enumerate(headers)
               if _FLK_EXAMPLE_HDR_RE.match(_norm_cell(h))]
        for r in rows:
            for i in idx:
                if i < len(r) and r[i].strip():
                    out.append(_norm_cell(r[i]))

    for hdr, rows in parse_md_tables(body):
        take(hdr, rows)
    for t in find_top_tables(body):
        grid = expand_grid(t)
        if len(grid) > 1:
            take(grid[0], grid[1:])
    return out


def _example_value_segments(body: str) -> List[str]:
    """Нормализованные ЗНАЧЕНИЯ примеров источника: текст после маркера
    «Пример:» до конца абзаца/ячейки (сегменты короче 15 знаков — шум)."""
    out: List[str] = []
    for m in _EXAMPLE_MARK_RE.finditer(body):
        tail = body[m.end():m.end() + 1200]
        cut = len(tail)
        for b in ("</p>", "</td>", "\n\n", "|", "</li>"):
            i = tail.find(b)
            if i != -1:
                cut = min(cut, i)
        seg = _norm_cell(tail[:cut])
        if len(seg) >= 15:
            out.append(seg)
    return out


def check_example_values_absent(card_text: str,
                                source_text: str) -> Tuple[List[str], bool]:
    """К-19 (2026-08-18, data-model): значения примеров источника НЕ
    должны присутствовать в карточке — шаблон велит «значения из примера
    не переносить», ПД в примерах обезличены. Ловит и ЧАСТИЧНЫЙ вырез
    (хвост примера, вклеенный в описание: обрывок ФЗ в ent-001,
    необезличенный «Выпискин О. О.» в ent-006 — найдено глазами
    пользователя, прогон inkasso-run1): проверяются скользящие фрагменты
    сегмента по 20 знаков."""
    segs = _example_value_segments(_fm_body(source_text))
    if not segs:
        return [], True
    card_norm = _norm_cell(card_text)
    hits: List[str] = []
    for seg in segs:
        for i in range(0, max(1, len(seg) - 19), 10):
            frag = seg[i:i + 20]
            if len(frag) >= 15 and frag in card_norm:
                hits.append(frag)
                break
    if hits:
        return [f"значения примеров источника перенесены в карточку "
                f"×{len(hits)} — шаблон data-model: «значения из примера "
                "не переносить» (абзац примера удаляется ЦЕЛИКОМ, ПД "
                "обезличиваются) ✗ НИЖЕ ПОРОГА; фрагменты: "
                + "; ".join(repr(h) for h in hits[:3])], False
    return [], True


def quoted_literals(source_text: str) -> List[str]:
    body = _fm_body(source_text)
    headings = _source_headings(body)
    flk_cells = _flk_example_cells(body)
    # Чётность кавычек (z04 ISS-03, маска "+7 (ХXX) XXX-XX-XX"):
    # кавычки HTML-атрибутов (href="…", style="…") сбивают рамки
    # _QUOTED_RE — «литералом» становится спан МЕЖДУ закрывающей
    # кавычкой атрибута и открывающей кавычкой честного литерала
    # (отсеивается как разметка), а сам литерал остаётся без
    # открывающей кавычки и не распознаётся ВОВСЕ — молчаливая потеря
    # и сверки, и К-30-помилования. Теги С КАВЫЧКАМИ вырезаются до
    # матчинга; теги без атрибутов (</p>, </td>, <br>) сохраняются —
    # они несут границы ячеек/абзацев для контекстных фильтров ниже.
    scan = re.sub(r"</?[A-Za-z][^>\n\"]*\"[^>\n]*>", " ", body)
    seen, out = set(), []
    for m in _QUOTED_RE.finditer(scan):
        v = m.group(1).strip()
        if (not v or _QUOTED_SKIP_RE.search(v)
                or _QUOTED_MARKUP_RE.search(v)):
            continue
        # значение HTML-атрибута ВНУТРИ открытого тега (class="critic-del",
        # data-task="GBO-104711") — разметка, не текст источника: контекст
        # «<тег … attr=» перед кавычкой без закрывающей «>» (финальный
        # прогон locks 2026-08-15: CriticMarkup-атрибуты ложно требовались
        # в карточке; содержимое-присваивание `= "O2PLUS"` вне тега — текст)
        pre = scan[:m.start()]
        lt = pre.rfind("<")
        if (lt != -1 and ">" not in pre[lt:]
                and re.search(r"[\w-]+\s*=\s*$", pre)):
            continue
        # К-14 (2026-08-17): кавычки ВНУТРИ адреса markdown-ссылки —
        # якоря Confluence вида #id-…"Журналдокументов"-… — навигация,
        # не литерал текста (контрольный прогон: агент был вынужден
        # вписать мусорный токен из якоря ради гейта)
        lp = pre.rfind("](")
        if lp != -1 and ")" not in pre[lp:]:
            continue
        # К-18 (2026-08-18, Э-3): значение ВНУТРИ примера — по шаблону
        # «значения из примера не переносить», ПД в примерах обезличены
        # (чек-лист data-model); маркер «Пример:» перед литералом без
        # границы ячейки/абзаца ('userFio':'Выпискин О. О.' в JSON)
        tail = pre[-600:]
        marks = list(_EXAMPLE_MARK_RE.finditer(tail))
        if marks:
            after = tail[marks[-1].end():]
            if ("</td>" not in after and "</p>" not in after
                    and "\n\n" not in after and "|" not in after):
                continue
        # К-18: ячейка колонки ФЛК/Пример — содержимое не переносится,
        # судьба — обязательный долг create-controls (шаблон data-model)
        nv = _norm_cell(v)
        if any(nv and nv in c for c in flk_cells):
            continue
        # структурная отсылка «см. раздел "..."» — навигация по источнику,
        # карточка переструктурирована по шаблону: не требуется
        if re.search(r"(?:раздел[еа]?|см\.)\s*$", scan[:m.start()][-24:],
                     re.IGNORECASE):
            continue
        # захват должен быть словом, а не межкавычечным обрезком («, то …»);
        # «+» — легальное начало литерала-маски («+7 (ХXX) XXX-XX-XX»)
        if not re.match(r"^[+\wА-Яа-яЁё]", v) or not re.search(
                r"[\wА-Яа-яЁё).%]$", v):
            continue
        # имена файлов-вложений (Имя_файла_1.8_28.08.2024.vsdx) — служебные
        if v.count("_") >= 2 or re.search(r"\.\w{2,5}$", v):
            continue
        n = _norm_cell(v)
        if not n or n in headings:
            continue
        if n not in seen:
            seen.add(n)
            out.append(v)
    return out


def check_quoted_literals(card_text: str,
                          source_text: str,
                          sibling_text: Optional[str] = None
                          ) -> Tuple[List[str], bool]:
    """Каждый кавычечный литерал источника обязан присутствовать в карточке
    (сравнение нормализованное, кавычки не требуются).

    sibling_text — объединение соседних карточек каталога главной
    (z04 ISS-03, «Подписать и отправить» страницы контролей держателя):
    содержимое страницы законно расходится по нескольким карточкам
    одного реестра — точки применения живут в README реестра, не в
    cards-файлах группы. Литерал, найденный у соседей, — не потеря:
    i-сигнал приёмке вместо ✗ (тот же принцип корпуса, что у полноты
    ячеек data-model)."""
    lits = quoted_literals(source_text)
    if not lits:
        return [], True
    norm_card = _fold_homoglyphs(_norm_cell(card_text))
    lost = [v for v in lits
            if _fold_homoglyphs(_norm_cell(v)) not in norm_card]
    report: List[str] = []
    if lost and sibling_text:
        sib_norm = _fold_homoglyphs(_norm_cell(sibling_text))
        relocated = [v for v in lost
                     if _fold_homoglyphs(_norm_cell(v)) in sib_norm]
        if relocated:
            lost = [v for v in lost if v not in relocated]
            report.append(
                f"i кавычечные литералы ×{len(relocated)} найдены в "
                "соседних карточках каталога, не в группе сверки "
                f"({'; '.join(repr(v[:40]) for v in relocated[:3])}) — "
                "разложение по реестру, принадлежность проверить приёмкой")
    if lost:
        report.append(
            f"кавычечные литералы источника: в карточке отсутствуют "
            f"{len(lost)} из {len(lits)} ✗ НИЖЕ ПОРОГА (тексты сообщений, "
            "кнопок и значений переносятся дословно); примеры: "
            + "; ".join(repr(v[:50]) for v in lost[:4]))
        return report, False
    report.append(f"кавычечные литералы источника: все {len(lits)} "
                  "на месте ✓")
    return report, True


_FM_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.M)


def _frontmatter_title(text: str) -> Optional[str]:
    """Значение title из YAML frontmatter (до второго ---); None, если нет.

    Длинный title экспортёр пишет YAML-переносом (продолжение со сдвигом
    на следующей строке) — однострочный regex обрезал значение у ОБЕИХ
    сторон сверки, и хвост наименования не сверялся вовсе (слепое пятно;
    находка агента src-locks, 2026-08-14). Продолжения склеиваются
    пробелом по семантике YAML flow scalar."""
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return None
    lines = body.splitlines()
    for i, ln in enumerate(lines[1:60], start=1):
        if ln.strip() == "---":
            return None
        m = re.match(r"^title:\s*(.+?)\s*$", ln)
        if not m:
            continue
        v = m.group(1)
        q = v[0] if v and v[0] in "'\"" else None
        closed = (q is None or (len(v) >= 2 and v.endswith(q)
                                and not v.endswith(q * 2)))
        j = i + 1
        while not closed and j < len(lines):
            nxt = lines[j]
            if nxt.strip() == "---" or not nxt.startswith(" "):
                break
            v += " " + nxt.strip()
            closed = v.endswith(q) and not v.endswith(q * 2)
            j += 1
        if q and len(v) >= 2 and v.endswith(q):
            v = v[1:-1]
            if q == "'":
                v = v.replace("''", "'")
        return v
    return None


# Маркеры контура-потребителя в начале title страницы-источника: это
# указание на комплект, из которого страница пришла, а не часть
# наименования метода. Базовый контракт внешней АС общий для ВСЕХ
# потребителей и префикс одного из них не наследует (решение аналитика
# 2026-08-25, EXTINT-F1-004). Список закрытый: имена систем в скобках
# («[Файловый сервис] Банк: Функция выгрузки файла») — часть
# наименования и снятию НЕ подлежат.
_CONTOUR_PREFIX_RE = re.compile(
    r"^\[(?:O2\+NEW|О2\+NEW|ОНБ_2021|КК_ВК|ББ_РЕГ|ГЭП|РЭП)\]\s*",
    re.IGNORECASE)


def check_title(card_text: str, source_text: str) -> Tuple[List[str], bool]:
    """Дословный перенос title источника во frontmatter карточки.

    title — постоянный атрибут (наименование в языке предметной области;
    у функций отражён в ролевой модели): при переименовании файлов в слаги
    он единственный носитель исходного наименования — тихая потеря хуже
    шумного отказа. Источник без title сверке не подлежит.

    Исключение — базовый контракт внешней АС (type: external-integration):
    ведущий маркер контура-потребителя из закрытого списка не переносится."""
    src = _frontmatter_title(source_text)
    if src is None:
        return [], True
    card = _frontmatter_title(card_text)
    if card == src:
        return [f"title: дословно перенесён ({src!r}) ✓"], True
    is_base = re.search(r"^type:\s*external-integration\s*$",
                        card_text[:600], re.M) is not None
    stripped = _CONTOUR_PREFIX_RE.sub("", src)
    if is_base and card is not None and card == stripped and stripped != src:
        marker = src[:len(src) - len(stripped)].strip()
        return [f"title: перенесён без маркера контура {marker!r} — "
                f"базовый контракт общий для потребителей ✓"], True
    if card is None:
        return [f"title: ОТСУТСТВУЕТ в карточке — у источника {src!r} "
                "✗ ПОТЕРЯ НАИМЕНОВАНИЯ"], False
    return [f"title: расходится с источником ✗ (карточка {card!r}, "
            f"источник {src!r} — перенос дословный)"], False


# FB-01 access-rules (2026-10-26): лейблы паспорта функции без двоеточия, которые
# встречаются на страницах функций обычным текстом («Код привилегии | …»). Закрытый перечень,
# расширяется по сигналу; лейбл с двоеточием распознаётся и без перечня (_is_passport_label).
_PASSPORT_LABELS = frozenset({
    "код привилегии",
    "какие методы закрывает функция",
    "кому доступна функция",
    "как вызывается функция",
    "что делает функция",
})
# заголовки колонок обычной двухколонной таблицы данных: шапка с ними — не строка паспорта
_DATA_COLUMN_TITLES = frozenset({
    "описание", "значение", "расшифровка", "комментарий", "примечание", "наименование",
    "параметр", "поле", "код", "value", "description",
})


# Сверка значений таблиц источника (решение владельца канона 2026-10-26, замер FB-01): две
# разницы записи различием не считаются, симметрично для источника и карточки —
#   - кавычки: «ёлочки», лапки, прямые двойные и одинарные снимаются совсем — знак кавычки
#     не содержание; замена живой ссылки названием в «ёлочках» — законная (правило «живые
#     URL не переносятся»). Только в этой сверке: сторож кавычечных литералов не затронут;
#   - ID карточки в начале текста ссылки — правило ссылок комплекта «[ID Название]»:
#     «[ENT-019 [КК_ЛК] Заявка…](…)» сверяется как «[[КК_ЛК] Заявка…](…)». ID — по форме
#     идентификаторов канона: префикс типа заглавными с дефисами и трёхзначный номер. ID не в
#     начале текста ссылки и снятый тег («[КК_БК]») — различие, как прежде.
_CMP_QUOTES_RE = re.compile(r"[«»“”„\"']")
_LINK_TEXT_ID_RE = re.compile(r"\[(?:[A-Z][A-Z0-9]*-)+\d{3}\s+(?=\S)")


def _cmp_text(v: str) -> str:
    """Нормальная форма для сверки значений таблиц источника: _norm_cell без ID карточки в
    начале текста ссылки и без кавычек, кириллица/латиница — без двойников."""
    v = _LINK_TEXT_ID_RE.sub("[", v)
    v = _CMP_QUOTES_RE.sub("", _fold_homoglyphs(_norm_cell(v)))
    return re.sub(r"\s+", " ", v).strip()


def _is_passport_label(cell: str) -> bool:
    """Первая ячейка строки паспорта: целиком жирный лейбл (К-35) либо обычный текст —
    короткий (не длиннее 6 слов и 60 символов, без точки внутри) с двоеточием в конце или
    лейбл из закрытого перечня паспорта функции."""
    c = cell.strip()
    if re.fullmatch(r"\*\*[^*]+\*\*", c):
        return True
    if not c or "**" in c:
        return False
    plain = c.rstrip(":").strip()
    if plain.lower() in _PASSPORT_LABELS:
        return True
    return (c.endswith(":") and "." not in plain and len(c) <= 60
            and len(plain.split()) <= 6)


def passport_kind(hdr: List[str], rows: List[List[str]]) -> Optional[str]:
    """Двухколонная таблица-паспорт «лейбл → значение»: "bold" — лейблы целиком жирные (К-35),
    "plain" — лейблы обычным текстом, первая строка паспорта стала шапкой (FB-01 access-rules);
    иначе None. Один признак для сверки значений markdown-таблиц и сбора имён параметров
    HTML-таблиц."""
    if len(hdr) != 2:
        return None
    data = [r for r in rows if r and any(c.strip() for c in r)]
    if (re.fullmatch(r"\*\*[^*]+\*\*", hdr[0].strip())
            and all(re.fullmatch(r"\*\*[^*]+\*\*", r[0].strip()) for r in data)):
        return "bold"
    if (_is_passport_label(hdr[0])
            and all(_is_passport_label(r[0]) for r in data)
            and any(len(r) > 1 and r[1].strip() for r in rows)):
        return "plain"
    return None


def check_source_tables(card_text: str, source_text: str) -> Tuple[List[str], bool]:
    """Сверка с источником: каждая ГОТОВАЯ markdown-таблица источника (вне
    сырого HTML — например «Коды банковских продуктов») обязана присутствовать
    в карточке значениями ВСЕХ колонок.

    Агент четырежды ужимал справочник (итерации 6-секст…6-нон, 2026-08-09),
    в том числе обойдя словесный гейт «фрагмент» — сторожим содержимое, а не
    слова. Таблицы из 1 колонки или <2 строк не сверяются (служебные)."""
    report: List[str] = []
    ok = True
    card_norm = _cmp_text(card_text)
    for hdr, rows in parse_md_tables(source_text):
        if len(hdr) < 2 or len(rows) < 2:
            continue
        hdr_norm = " ".join(_norm_cell(h) for h in hdr)
        # Служебная секция «Документация» страницы (реестр док-файлов) —
        # в контракт не переносится, сверке не подлежит.
        if "документ" in hdr_norm and "дата" in hdr_norm:
            continue
        # История изменений страницы («Дата | Описание | Автор [| Задача]»)
        # — по канону в чистовик не переносится; гейт требовал её значения
        # (ретро-перегон [КК_ВК] 2026-08-15, конфликт гейт↔шаблон — агент
        # честно сдал «НЕ ГОТОВО» вместо маскировки таблицей).
        if "дата" in hdr_norm and "описани" in hdr_norm and "автор" in hdr_norm:
            continue
        # Таблица макетов ЭФ (размерности экрана + ссылки на Figma) —
        # служебная: шаблон screen-form запрещает Figma/Confluence-URL в
        # чистовике, макеты живут в src. Гейт требовал её значения — агент
        # включил сырой HTML с живыми URL в карточку (src-locks,
        # 2026-08-14, конфликт шаблон↔гейт).
        if "figma" in hdr_norm or "размерност" in hdr_norm:
            continue
        # К-18 (2026-08-18, Э-3): колонки ФЛК и «Пример(ы)» страниц МД в
        # модель не переносятся (их судьба — обязательный долг
        # create-controls по шаблону) — их ячейки гейт не требует
        skip_cols = {i for i, h in enumerate(hdr)
                     if re.match(r"\s*(флк|пример)", _norm_cell(h))}
        # К-35 (2026-08-20, эталон O2+ ent-005/007/008): двухколонная
        # таблица-паспорт «лейбл → значение» (заголовочная ячейка И первая
        # ячейка КАЖДОЙ строки — целиком жирный лейбл) — лейблы служебные
        # носители структуры: содержимое раскладывается в слоты шаблона,
        # дословное присутствие лейблов в карточке не требуется. Требование
        # провоцировало гашение вписыванием жирной строки-дубля рядом со
        # слотом шаблона («Таблица БД» + «**Название физической таблицы
        # БД**»). Значения второй колонки сторожатся по-прежнему
        # (асимметрия: данные — сторожим, носители структуры — нет).
        # FB-01 access-rules (2026-10-26): паспорт с лейблами обычным текстом («Кому
        # доступна функция: | …», «Код привилегии | …») и без строки шапки — первая строка
        # паспорта стала заголовком таблицы. Лейблы не требуются, как у жирного паспорта;
        # значение строки-«шапки» проверяется наравне со строками (раньше терялось молча).
        kind = passport_kind(hdr, rows)
        bold_passport = kind == "bold"
        plain_passport = kind == "plain"
        if bold_passport or plain_passport:
            skip_cols.add(0)
        check_rows = list(rows)
        # строка-шапка паспорта — данные и у жирного паспорта К-35 (решение владельца канона
        # 2026-10-26: тихая потеря значения шапки — нарушение асимметрии), если её вторая
        # ячейка — не заголовок колонки
        if ((plain_passport or bold_passport) and hdr[1].strip()
                and _norm_cell(hdr[1]).strip(" :*").lower() not in _DATA_COLUMN_TITLES):
            check_rows.insert(0, list(hdr))
        missing: List[str] = []
        img_mixed: List[str] = []
        url_cells: List[str] = []
        for row in check_rows:
            # Строка с вложением (пример Запрос.xml/Ответ.xml) — целиком в
            # sidecar examples/, в карточке её значений законно нет.
            if any(_ATTACHMENT_RE.search(c) for c in row):
                continue
            # Строка макетов ЭФ (Figma/размерности) — служебная, см. выше.
            if any(_LAYOUT_ROW_RE.search(c) for c in row):
                continue
            # Строка-указатель («Логика работы | …см. ниже») — навигация по
            # странице, дублирующая целевой раздел карточки: не требуется
            # (решение по шаблону agent, 2026-08-15).
            if any(re.search(r"см\.\s*ниже", c, re.IGNORECASE) for c in row):
                continue
            for ci, cell in enumerate(row):
                if ci in skip_cols:
                    continue
                cv = _norm_cell(cell)
                # обрезки текстового CriticMarkup («++}», «{++», «~~}») —
                # разметка правок, не содержимое: вход с невлитыми
                # правками (Вх-1 экзамена inkasso, страницы-draft)
                if re.fullmatch(r"[{}+~\-\s|]*", cell.strip()):
                    continue
                # ячейки-изображения (<img …> — скриншоты/эскизы макетов):
                # шаблоны запрещают перенос изображений в комплект, гейт
                # их не требует (К-6 экзамена inkasso: журнальный README —
                # гейт требовал скриншоты и провоцировал их перенос)
                if re.fullmatch(r"(?:\s*<img\b[^>]*>\s*)+",
                                cell.strip(), re.I):
                    continue
                # смешанная ячейка с <img> ВНУТРИ текста (z04 ISS-03,
                # «Выход с ЭФ» view): изображения не переносятся (К-6),
                # и дословность вокруг вырезанных картинок разрушена по
                # построению — легитимный перенос перефразирует подписи
                # («отображается иконка <img>» → «иконка «назад»»).
                # Дословная сверка пропускается с сигналом приёмке;
                # кавычечные литералы ячейки сверяет штатный сторож.
                if re.search(r"<img\b", cell, re.I):
                    img_mixed.append(cell.strip()[:50])
                    continue
                # FB-16 КК (2026-10-09): значение-ссылка на Confluence
                # («Cм. внутр. Сonfluence [https://confluence…») — перенос
                # живых URL запрещён правилами, требовать его полнотой
                # нельзя; такая ячейка — не потеря, а отсылка источника.
                # FB-41 КК (2026-10-28): ячейка целиком URL (markdown-ссылка
                # с URL в тексте или голый URL) — та же отсылка; признак —
                # значение ячейки после сведения ссылок к тексту само URL,
                # а не пустой остаток: у [Название](url) остаток тоже пуст,
                # но название — содержание, оно переносится (FB-38)
                if cv and _CONFLUENCE_URL_RE.search(cell):
                    if re.fullmatch(r"(?:https?://\S+\s*)+", cv):
                        url_cells.append(cell.strip()[:50])
                        continue
                    rest = _norm_cell(re.sub(
                        r"\[([^\]]*)\]\([^)]*\)|https?://\S+", " ", cell))
                    if (len(rest) <= 40
                            and ("confluence" in rest.lower()
                                 or rest.lower().startswith(("см", "cм")))):
                        url_cells.append(cell.strip()[:50])
                        continue
                if cv and _cmp_text(cell) not in card_norm:
                    missing.append(cell.strip()[:60])
        if plain_passport:
            title = " | ".join(h.strip() for h in hdr[:3])[:80]
            report.append(
                f"i таблица-паспорт «{title}»: лейблы не требуются ({len(check_rows)} строк), "
                "значения проверены")
        if missing:
            ok = False
            title = " | ".join(h.strip() for h in hdr[:3])
            report.append(
                f"таблица источника «{title}» ({len(check_rows)} строк): в карточке "
                f"отсутствуют {len(missing)} значений ✗ НИЖЕ ПОРОГА")
            for v in missing[:3]:
                report.append(f"      пример потери: {v!r}")
        if img_mixed:
            title = " | ".join(h.strip() for h in hdr[:3])
            report.append(
                f"предупреждение: таблица источника «{title}» — ячейки со "
                f"смешанным текстом и изображениями ×{len(img_mixed)}: "
                "дословная сверка пропущена (изображения не переносятся), "
                "полноту переноса проверить приёмкой")
        if url_cells:
            title = " | ".join(h.strip() for h in hdr[:3])
            report.append(
                f"i таблица источника «{title}»: ячейки-ссылки на Confluence "
                f"×{len(url_cells)} полнотой не считаются (живые URL не "
                "переносятся); содержимое по ссылке — отдельная страница "
                "или долг")
    # Полнота HTML-таблиц источника: каждое имя параметра из раскрытых
    # сеток обязано присутствовать в карточке (инцидент 2026-08-12:
    # file_id/upload_token потеряны при зелёном гейте).
    html_names = html_param_names(source_text)
    lost = sorted(n for n in html_names
                  if _cmp_text(n) not in card_norm)
    if lost:
        ok = False
        report.append(
            f"HTML-таблицы источника: в карточке отсутствуют "
            f"{len(lost)} имён параметров ✗ НИЖЕ ПОРОГА")
        for v in lost[:5]:
            report.append(f"      пример потери: {v!r}")
    elif html_names:
        report.append(
            f"HTML-таблицы источника: все {len(html_names)} имён параметров "
            f"на месте ✓")
    if ok:
        report.append("markdown-таблицы источника: все значения на месте ✓")
    return report, ok


# Волна 9 ОНБ-В (ЗК-04): таблица источника без единого дословного значения (ячейки —
# ссылки, изображения, пусто, макеты ЭФ) сверке не подлежала вовсе: «Макеты ЭФ» с
# размерностями и ссылками не перенесли, прибор молчал. Теперь ищутся её заголовки и
# ключевые ячейки первой колонки — в карточке и в README группы. Только ⚠ / i.
def _table_keys(hdr: List[str], rows: List[List[str]]) -> List[str]:
    """Заголовки и первые ячейки строк без ссылок и картинок (≥ 2 символов)."""
    out = []
    for cell in list(hdr) + [r[0] for r in rows if r]:
        t = re.sub(r"<img\b[^>]*>|!\[[^\]]*\]\([^)]*\)", " ", cell, flags=re.I)
        t = re.sub(r"\[([^\]]*)\]\([^)]*\)|https?://\S+", r" \1 ", t)
        t = _norm_cell(t)
        if len(t) >= 2:
            out.append(t)
    return out


def check_unchecked_tables(card_text: str, source_text: str,
                           readme_text: str = "") -> List[str]:
    """T1: таблицы источника, ни одно значение которых не попало в дословную сверку
    (все ячейки — ссылки, изображения, пусто; таблицы макетов ЭФ), — по заголовкам и
    ключевым ячейкам первой колонки в карточке и README группы."""
    hay = _fold_homoglyphs(_norm_cell(card_text + "\n" + readme_text))
    out: List[str] = []
    for hdr, rows in parse_md_tables(source_text):
        if len(rows) < 1:
            continue
        hdr_norm = " ".join(_norm_cell(h) for h in hdr)
        if ("документ" in hdr_norm and "дата" in hdr_norm) or (
                "дата" in hdr_norm and "описани" in hdr_norm and "автор" in hdr_norm):
            continue  # реестр документов страницы и история изменений не переносятся
        plain = 0
        # как в check_source_tables: таблица и строки макетов ЭФ, строки вложений и
        # строки-указатели в дословную сверку не входят
        layout = "figma" in hdr_norm or "размерност" in hdr_norm
        for row in ([] if layout else rows):
            if any(_ATTACHMENT_RE.search(c) or _LAYOUT_ROW_RE.search(c)
                   or re.search(r"см\.\s*ниже", c, re.IGNORECASE) for c in row):
                continue
            for cell in row:
                c = cell.strip()
                if not _norm_cell(c) or re.fullmatch(r"[{}+~\-\s|]*", c):
                    continue
                if re.search(r"<img\b|!\[", c, re.I) or _CONFLUENCE_URL_RE.search(c) \
                        or _LAYOUT_ROW_RE.search(c) or re.search(r"figma\.com", c, re.I):
                    continue
                if re.fullmatch(r"\[[^\]]*\]\([^)]*\)|https?://\S+", c):
                    continue
                plain += 1
        if plain:
            continue
        keys = _table_keys(hdr, rows)
        found = [k for k in keys if _fold_homoglyphs(k) in hay]
        title = " | ".join(h.strip() for h in hdr[:3]) or "без заголовка"
        if keys and not found:
            out.append(
                f"предупреждение: таблица источника «{title}» ({len(rows)} строк): дословных "
                "значений нет (ссылки/изображения), заголовки в карточке и README не найдены — "
                "таблица не перенесена? (макеты ЭФ — README группы; правило на изображении — "
                "долг)")
        elif keys:
            out.append(f"i таблица без дословных значений «{title}» ({len(rows)} строк): найдено "
                       f"{len(found)} из {len(keys)} заголовков и ключевых ячеек — перенос "
                       "проверить приёмкой")
    return out


_SRC_IMG_RE = re.compile(r"<img\b(?![^>]*emoticon)[^>]*>|!\[[^\]]*\]\([^)]*\)", re.I)


def check_image_trace(card_text: str, source_text: str, debts_text: str = "",
                      card_ids: Optional[List[str]] = None) -> List[str]:
    """T2: изображения страницы-источника без следа в карточке — нет ни блока
    приложений, ни ссылок на files/, ни долга «правило на изображении» (в карточке или
    в строке матрицы с ID карточки). Смайлики Confluence не считаются."""
    n = len(_SRC_IMG_RE.findall(source_text))
    if not n:
        return []
    if re.search(r"^#{2,4}\s+Приложен", card_text, re.M | re.I) or re.search(r"\]\(\.{0,2}/?(?:[^)]*/)?files/", card_text):
        return []
    if "правило на изображении" in card_text.lower():
        return []
    for ln in debts_text.splitlines():
        if "правило на изображении" in ln.lower() and any(
                re.search(r"(?<![\w-])" + re.escape(i) + r"(?![\w-])", ln) for i in (card_ids or [])):
            return []
    return [f"предупреждение: изображения источника ×{n}: в карточке нет ни блока приложений, "
            "ни files/, ни долга «правило на изображении» — проверить приёмкой (изображения "
            "не переносятся, правила на них — долг)"]


def source_tables_summary(source_text: str) -> List[str]:
    """T3: перечень таблиц источника (заголовок, строк) — подсказка акцептующему для
    потерь, которые механически не ловятся. Markdown-таблицы и HTML-сетки."""
    items: List[Tuple[str, int]] = []
    for hdr, rows in parse_md_tables(source_text):
        items.append((" | ".join(h.strip() for h in hdr[:3]) or "без заголовка", len(rows)))
    for t in find_top_tables(source_text):
        try:
            grid = expand_grid(t)
        except Exception:  # noqa: BLE001 — перечень не должен ронять сверку
            continue
        if grid:
            head = " | ".join(_norm_cell(c)[:30] for c in grid[0][:3])
            items.append((head or "без заголовка", max(len(grid) - 1, 0)))
    if not items:
        return []
    shown = "; ".join(f"«{h}» ({r})" for h, r in items[:3])
    rest = f"; ещё {len(items) - 3}" if len(items) > 3 else ""
    return [f"i таблицы источника: {len(items)} — {shown}{rest}"]


def source_role_literals(source_text: str) -> Dict[str, set]:
    """Дословные значения якорных колонок ИСТОЧНИКА, сгруппированные по роли
    («обязат», «кратн»): из готовых markdown-таблиц и из сырых HTML-таблиц
    (первая строка сетки — шапка; многострочные шапки не распознаются — тогда
    просто нет помилования, поведение прежнее, гейт строже, не мягче).

    Нужны для --check --source: см. validate_columns (дословный перенос
    авторского литерала — не брак, инцидент «Обяз.=[1]» жанра 3 file-storage,
    2026-08-10)."""
    lits: Dict[str, set] = {}

    def add(headers: List[str], rows: List[List[str]]) -> None:
        for i, h in enumerate(headers):
            low = _title_key(h)
            key = None
            for k, _fn in _COLUMN_RULES:
                if k in low or k[:4] in low:
                    key = k
                    break
            # колонка названий — по тому же распознаванию, что роль
            # «название» в validate_columns (OQ-128: имя «Дата» из
            # источника); колонки физимён БД/DEV — не названия
            if key is None and ("назван" in low or "наимен" in low
                                or "параметр" in low) \
                    and "бд" not in low and "dev" not in low:
                key = "название"
            if key is None:
                continue
            vals = lits.setdefault(key, set())
            for r in rows:
                if i < len(r) and _norm_cell(r[i]):
                    vals.add(_norm_cell(r[i]))

    for hdr, rows in parse_md_tables(source_text):
        add(hdr, rows)
    for t in find_top_tables(source_text):
        grid = expand_grid(t)
        if len(grid) > 1:
            add(grid[0], grid[1:])
    return lits


def _fc_source_page_refs_and_columns(fx: "_FileCtx") -> Tuple[List[str], bool]:
    min_valid_pct, column_roles, text, src_literals = fx.min_valid_pct, fx.column_roles, fx.text, fx.src_literals
    report: List[str] = []
    ok = True
    # Отсылки к страницам источника в ТЕЛЕ карточки — запрещены (чистовик
    # без ссылок на Confluence/выгрузку; законный носитель page_id —
    # только frontmatter confluence_page_ids и матрица трассировки).
    # К-7 экзамена inkasso: «Статика и источники — по таблице полей
    # источника page 2169849859» ×40 — отсылка ВМЕСТО переноса
    # содержимого, словарь маркеров сокращения её не покрывал.
    body_wo_fm = _fm_body(text)
    # Исключение (решение владельца 2026-10-03, замечание 5 к MR 104):
    # заготовка регистрации потребителя в таблице «Потребители» карточки
    # контракта — `page_id:<ID страницы потребителя>` в колонке
    # «Локальный ID» с пометкой «до регистрации». Это не отсылка вместо
    # переноса, а ключ, по которому скрипт регистрации заменит заготовку
    # настоящей строкой; формат с двоеточием без пробела — только он.
    body_scan = re.sub(r"page_id:\d{4,}", "", body_wo_fm)
    page_refs = re.findall(r"(?i)confluence|page[ _]?id|page\s+\d{6,}",
                           body_scan)
    if page_refs:
        ok = False
        report.append(
            f"отсылки к страницам источника в теле карточки ×{len(page_refs)} "
            f"({', '.join(sorted(set(page_refs))[:3])}) ✗ НИЖЕ ПОРОГА — "
            "содержимое переносится, а не адресуется; page_id живёт только "
            "во frontmatter и матрице")
    tables = list(parse_md_tables(text))
    if not column_roles and tables:
        # README-реестры: навигационные таблицы, роли параметрических
        # колонок к ним неприменимы (К-4 экзамена inkasso: колонка
        # «Краткое название формы (элемент…)» ложно распознана «путём»);
        # полноту реестра держит сверка значений источника
        report.append("README-реестр: колонные роли к навигационным "
                      "таблицам не применяются")
        tables = []
    for i, (headers, rows) in enumerate(tables):
        low0 = _title_key(headers[0]) if headers else ""
        # «Код параметра» — каноническая колонка путей (XML через /, JSON
        # через .); именно «код параметра» — «Код отказа» путём не является.
        # Заголовок «Наименование …» — колонка ИМЕНИ, а не пути, даже когда
        # несёт слово «элемент»: у нормативных справочников источника
        # (формат выписки ЕГРЮЛ ФНС, таблица 4.1 — «Наименование элемента»
        # с русскими названиями, технический код во ВТОРОЙ колонке) роль
        # «путь» давала ложный брак. Тот же класс, что К-4 экзамена
        # inkasso («Краткое название формы (элемент…)»), закрытый там
        # только для README-реестров.
        path_index = 0 if (("xml" in low0 or "элемент" in low0
                            or "путь" in low0
                            or ("код" in low0 and "параметр" in low0))
                           and not ("наимен" in low0 or "назван" in low0)
                           ) else None
        # Целостность строк: число ячеек = ширине шапки. Разорванная строка
        # (перенос строки ВНУТРИ ячейки вместо <br>) выглядит как короткая
        # строка + голый текст вне таблицы — инцидент 6-дец, 2026-08-09:
        # агент разнёс название и разрезал строку таблицы переносом.
        torn = [r for r in rows if len(r) != len(headers)]
        if torn and path_index is not None:
            ok = False
            report.append(
                f"таблица {i}: {len(torn)} строк с числом ячеек ≠ ширине шапки "
                f"({len(headers)}) — разорванная строка (перенос внутри ячейки "
                f"должен быть <br>) ✗ НИЖЕ ПОРОГА")
            for r in torn[:2]:
                report.append(f"      пример: {(' | '.join(r))[:90]!r}")
        h0 = headers[0] if headers else ""
        if len(headers) >= 4 and "/" in h0 and " " not in h0.strip():
            # Шапка «таблицы» — строка данных (XML-путь): хвост разорванной
            # таблицы, отделённый вывалившимся текстом (бэктики оформления
            # parse_md_tables уже снял — детектим по форме пути).
            ok = False
            report.append(
                f"таблица {i}: шапка выглядит строкой данных ({h0[:40]!r}) "
                f"— хвост разорванной таблицы ✗ НИЖЕ ПОРОГА")
            continue
        cols = validate_columns(headers, rows, path_index=path_index,
                                source_literals=src_literals)
        if not cols:
            report.append(f"таблица {i} ({len(rows)} строк): ролей не распознано — пропущена")
            continue
        report.append(f"таблица {i} ({len(rows)} строк):")
        for col in cols:
            mark = "✓" if col["valid_pct"] >= min_valid_pct else "✗ НИЖЕ ПОРОГА"
            report.append(
                f"   колонка «{col['column'][:28]}» (роль: {col['role']}): "
                f"валидных {col['valid_pct']}% [{col['total'] - col['bad']}/{col['total']}] {mark}")
            if col["valid_pct"] < min_valid_pct:
                ok = False
                for s in col["samples"]:
                    report.append(f"      пример брака: {s[:80]!r}")
            if col.get("pardoned_count"):
                report.append(
                    f"      вне словаря роли, но дословно из источника — "
                    f"принято ({col['pardoned_count']}): "
                    + ", ".join(repr(s[:30]) for s in col["pardoned"]))
            if col.get("suspicious_pardoned_count"):
                report.append(
                    f"      «Название» — словарный тип как имя, дословно из "
                    f"источника — принято ({col['suspicious_pardoned_count']}): "
                    + ", ".join(repr(s[:30]) for s in col["suspicious_pardoned"]))
            if col.get("suspicious_count"):
                # В ГОТОВОЙ карточке подозрительное название — брак: проход 2
                # обязан был разнести (название дословно, пояснения — в правила).
                ok = False
                report.append(
                    f"   «Название» несёт пояснения/значения/тип "
                    f"({col['suspicious_count']} строк) — разнесите: имя дословно, "
                    f"остальное в «Правила заполнения» ✗ НИЖЕ ПОРОГА")
                for s in col["suspicious"][:3]:
                    report.append(f"      пример: {s[:80]!r}")
    return report, ok


# Подраздел «Из источника, вне разделов шаблона» (норма канона 2026-10-26: шаблон function §6,
# чек-лист п. 11): сведения источника без слота в шаблоне — дословно, с лейблом источника, H2 в
# конце карточки. Прибор только показывает приёмке, что такой перенос в карточке есть (строка i,
# видна и у ✓). Форму подраздела (пустота, положение) не проверяет: норма делает его «переносом
# как есть», ревьюеру форму замечанием считать не велено — второй источник правды не заводим
# (решение владельца канона 2026-10-26); пустой виден по «0 строк». Дословность сверяется по
# странице целиком, дубли слотов — дело ревью. Карточка без подраздела — ни одной строки.
_OUTSIDE_TPL_TITLE = "из источника, вне разделов шаблона"


def _h2_key(title: str) -> str:
    """Имя H2 для сравнения: без номера раздела, конечной точки, регистра и «ё»."""
    t = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+", "", title.strip())
    return re.sub(r"\s+", " ", t.rstrip(" .:")).lower().replace("ё", "е")


def check_outside_template_section(card_text: str) -> Tuple[List[str], bool]:
    """Подраздел «Из источника, вне разделов шаблона»: строка i с числом строк. Без подраздела —
    пусто."""
    lines = card_text.splitlines()
    code = _fence.code_flags(lines)
    h2 = [(i, ln[3:]) for i, ln in enumerate(lines)
          if not code[i] and ln.startswith("## ") and not ln.startswith("###")]
    hits = [k for k, (_i, t) in enumerate(h2) if _h2_key(t) == _OUTSIDE_TPL_TITLE]
    if not hits:
        return [], True
    k = hits[0]
    start = h2[k][0] + 1
    end = h2[k + 1][0] if k + 1 < len(h2) else len(lines)
    body = re.sub(r"<!--.*?-->", " ", "\n".join(lines[start:end]), flags=re.S)
    n = sum(1 for ln in body.splitlines() if ln.strip())
    return [f"i подраздел вне шаблона: {n} строк"], True
