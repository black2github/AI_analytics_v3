# app/scripts/CI/kitcheck/columns.py
"""Валидаторы колонок (роли «путь», «тип», «обязательность», «кардинальность»), общие для
нормализатора таблиц и проверок карточки.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена."""
import re
from typing import Dict, List, Optional
from .html import _BR_RE, _norm_cell, _plain, _title_key


# Валидаторы колонок: подпись — (имя_роли, распознаватель заголовка, проверка значения).
# разделитель диапазона в источниках встречается и как «..», и как «-»
_CARDINALITY_RE = re.compile(r"^\[\s*\d+\s*(([.]{2}|-)\s*(\d+|[*]|[nNмМ]))?\s*\]$")
_PATH_RE = re.compile("^[\\w@\\[\\]{}().*/:#=+«»'\"-]+$", re.UNICODE)
_SENTENCE_RE = re.compile(r"[а-яё]+\s+[а-яё]+\s+[а-яё]+", re.IGNORECASE)


_TYPE_TOKENS = {
    "string", "int", "integer", "long", "boolean", "bool", "guid", "uuid",
    "date", "datetime", "time", "decimal", "double", "float", "number",
    "varchar", "text", "blob", "clob", "base64", "xml", "json",
    "строка", "число", "дата", "логический", "контейнер", "блок",
}


def _looks_like_obligation(v: str) -> bool:
    # О/Н/У в кириллице и латинские омоглифы O/H/Y; «Да/Нет/Усл.» (словарь
    # карточек, режим --check); прочерк; пусто. Расширение по нотации
    # эталона docs-account-opening-request (разбор ✗ эталона 2026-08-21):
    # «обязателен»/«необязателен» и «Да/Нет (вход|исход)» — направление
    # параметра автор пишет в скобках той же ячейки. Строгий якорь
    # раскроя HTML (_strict) не трогаем — он держит сетки.
    # разметка снимается (_plain): авторы КК_ВК пишут «**Да**» жирным —
    # словарь сверяется с содержимым, не с оформлением (ISS-01 2026-08-27)
    # «НМ»/«ОМ» — нотация обязательности нормативных форматов ФНС
    # (необязательный/обязательный множественный): встречается в
    # справочниках-приложениях источника, переносимых дословно.
    u = _plain(v).strip().strip(".").upper()
    if u in {"", "-", "—", "О", "Н", "У", "O", "H", "Y", "ДА", "НЕТ",
             "УСЛ", "M", "М", "НМ", "ОМ", "ОБЯЗАТЕЛЕН", "НЕОБЯЗАТЕЛЕН"}:
        return True
    if re.match(r"^(ДА|НЕТ)\s*,\s*ЕСЛИ\b", u):
        # условная обязательность авторским текстом («Да, если не
        # заполнен Адрес пребывания» — КК_ВК, ISS-01 2026-08-27)
        return True
    return bool(re.match(r"^(ДА|НЕТ)\s*\((ВХОД|ИСХОД)\)$", u))


def _looks_like_obligation_pair(v: str) -> bool:
    """КОМБИНИРОВАННАЯ колонка «Обязательность / Уникальность» (источники
    Корпоративных Карт; блокер COM-01 2026-08-27: «Да / Да» давало 0%
    валидности и отказ нормализатора): значение — пара токенов через «/»,
    каждый по словарю обязательности; одиночный токен тоже легален.
    Валидатор выбирается ТОЛЬКО по комбинированной шапке (оба ключа) —
    в обычной колонке «Обязательность» пара остаётся браком (защита от
    съехавших ролей). Скобочное пояснение хвостом («Да / Да<br>(код ЭФ +
    Наименование)» — автор уточняет состав ключа уникальности) валидности
    не ломает: перенос всё равно дословный, валидатор лишь узнаёт роль."""
    v = _BR_RE.sub(" ", v)
    v = re.sub(r"\([^()]*\)\s*$", "", v.strip())
    return all(_looks_like_obligation(p) for p in v.split("/"))


# Логическая кратность связей модели данных (шаблон data-model, раздел
# «Связи»): «1 : N», «1 : 1», «0..1», «N : M». Расширение словаря, а не
# замена (--check; строгий якорь разбора HTML _strict не трогаем — он
# держит раскрой сеток). Инцидент src-locks 2026-08-14: агент переписал
# шаблонную нотацию под гейт ([1..N]) — конфликт правило↔гейт.
_LOGICAL_CARD_TOKEN = r"(?:\d+|[nNмМmM*])(?:\s*\.\.\s*(?:\d+|[nNмМmM*]))?"
_LOGICAL_CARD_RE = re.compile(
    rf"^{_LOGICAL_CARD_TOKEN}(?:\s*:\s*{_LOGICAL_CARD_TOKEN})?$")


def _looks_like_cardinality(v: str) -> bool:
    v = _plain(v).strip()
    return not v or bool(_CARDINALITY_RE.match(v))


def _looks_like_cardinality_logical(v: str) -> bool:
    """Роль кратн в ТАБЛИЦЕ СВЯЗЕЙ модели данных и при нормализации
    ИСТОЧНИКА: допускает и скобочную, и логическую нотацию (КК_ВК пишет
    кратность голой: «1», «0..1», бывает жирной — разметка снимается).
    В --check таблиц параметров карточки НЕ применяется — раскавычивание
    [1] → 1 там остаётся браком (защита литералов)."""
    v = _plain(v).strip()
    return (not v or bool(_CARDINALITY_RE.match(v))
            or bool(_LOGICAL_CARD_RE.match(v)))


# Ярлык структурного ряда ЭФ-таблицы полей (протяжка в колонку
# обязательности при нормализации источника)
_STRUCT_LABEL_RE = re.compile(
    r'^(раздел|блок|вкладка|кнопка|шаг|секция)\s*["«№]', re.I)
# Ярлык без кавычек: «Блок подтверждение» (2166860586, STS-03 z03 —
# ложный отказ полноты 93.8%). Ограничитель: ≤2 слова после ключевого
# и конец строки — фраза с запятой/продолжением («Блок отображается,
# если…») ярлыком не считается
_STRUCT_LABEL_BARE_RE = re.compile(
    r'^(раздел|блок|вкладка|секция)\s+[\w«»"-]+(?:\s+[\w«»"-]+)?\s*$',
    re.I)


def _is_cardinality_title(low: str) -> bool:
    """Заголовок роли кратность: «Кратность», «Крат.» — но НЕ «Краткое
    описание» (ложный матч по префиксу, справочник продуктов КК_ВК)."""
    return "кратн" in low or ("крат" in low and "кратк" not in low)


def _looks_like_path(v: str) -> bool:
    v = v.strip()
    # внутренний сегмент «*» («BSDocument/*/DOCUMENTDATE») — оформление
    # контейнеров исходника в пути листа: не XML-путь, брак (intc-002
    # src-locks, 2026-08-15); контейнерная строка «X/*» — наследие, терпима
    if "/*/" in v:
        return False
    if not v:
        return True
    if _SENTENCE_RE.search(v):        # три слова подряд — это предложение, не путь
        return False
    return bool(_PATH_RE.match(v.replace(" ", "")))


_XML_PATHISH_RE = re.compile(r"^[A-Za-z0-9_*/\[\]@.:#-]+$")


def _no_xml_path(v: str) -> bool:
    """В колонке названия не должно быть XML-пути (признак съехавших ролей).

    Слэш сам по себе законен в бизнес-именах («ОГРН/ОГРНИП», «Адрес рег./факт.»),
    поэтому браком считается только ПУТЬ: латиница со слэшем и без кириллицы.
    """
    v = v.strip()
    if not v or "/" not in v:
        return True
    return not _XML_PATHISH_RE.match(v.replace(" ", ""))


_COLUMN_RULES = (
    ("обязат", _looks_like_obligation),
    ("кратн", _looks_like_cardinality),
)

# Маркеры «в названии не только название» (замечания пользователя по 6-нон,
# 2026-08-09: пояснения и допустимые значения автор источника пишет прямо в
# ячейку названия). Детектор МЕХАНИЧЕСКИЙ, разнесение — работа прохода 2
# (LLM/аналитик): скрипт не решает, где кончается имя и начинается пояснение.
_TITLE_SUSPECT_RES = (
    re.compile(r"допустимые значения", re.IGNORECASE),
    re.compile(r"возможные значения", re.IGNORECASE),
    re.compile(r"[–—-]\s*обязателен", re.IGNORECASE),
    re.compile(r"пример\s*:", re.IGNORECASE),
    # Вторая строка в ячейке названия: у имени не бывает второго абзаца —
    # это пояснение (замечания 2/4 по 6-дец: «Проверка ЕИО … выполняется
    # всегда», «Время должно быть указано …», 2026-08-09)
    re.compile(r"<br", re.IGNORECASE),
    # Глагольность = предложение, не имя (замечания 1/5: «допускается
    # передача…», «Секция для связи…» — описания поведения)
    re.compile(r"\b(допускается|заполняется|передаётся|передается|выполняется|"
               r"формируется|указывается|используется|должн[оаы])\b",
               re.IGNORECASE),
    # Описания назначения (замечание 5 по 6-ундец: единственные два случая,
    # не покрытые мандатом прохода 2, — добавлены как маркеры по инциденту)
    re.compile(r"\b(секция для|ссылка на)\b", re.IGNORECASE),
)


def _title_suspicious(v: str) -> bool:
    """True — содержимое колонки «Название» несёт пояснения/значения/правила,
    которые надо разнести (название — дословно, остальное — в «Правила
    заполнения»), НЕЗАВИСИМО от заполненности остальных колонок строки."""
    v = _plain(v).strip()
    if v.startswith("="):               # «=Код должности …» — правило-присвоение
        return True
    if any(rx.search(v) for rx in _TITLE_SUSPECT_RES):
        return True
    # чистый СЛОВАРНЫЙ тип данных — не название; одиночный латинский
    # идентификатор (TraceID, SessionID) — легитимное имя параметра
    # (К-3 экзамена inkasso: generic-латиница ложно бракавала имена)
    return _bare_type_name(v)


def _bare_type_name(v: str) -> bool:
    """Ячейка названия — голый словарный тип данных («Дата», «Строка»),
    без пояснений. Единственный класс подозрительных названий, который
    милуется дословным совпадением с источником (OQ-128 «Корпоративных
    карт», 2026-10-07: поле скроллера по имени «Дата»); пояснения и
    правила в ячейке названия не милуются — их разносят."""
    vv = re.sub(r"\s+\(", "(", _plain(v).strip())
    if not vv or " " in vv or len(vv) > 24:
        return False
    return re.sub(r"[\d()\[\]]+$", "", vv).lower() in _TYPE_TOKENS


def _is_section_row(row: List[str]) -> bool:
    """Строка-раздел внутри таблицы («<td colspan=5>Реквизиты операции»):
    протяжка colspan повторяет одно значение на всю ширину сетки. Из СЕТКИ
    такие строки не удаляются (содержимое автора), но в подсчёт валидности
    ролей не входят — это заголовок группы, а не данные (блокер COM-01
    Корпкарт 2026-08-27: заголовки групп 2FA считались строками данных).
    Признак — доминирующее БУКВЕННОЕ значение, занявшее ≥3 ячеек и не
    меньше половины ширины строки (след протяжки colspan); кроме него
    допустима максимум одна непустая ячейка — авторский номер раздела
    (2FA: «1 | Реквизиты операции ×5 | пусто»). Ограничители (все — с
    тестами на НЕсрабатывание): строка с единственным заполненным
    значением — данные, не раздел (иначе маскировался бы съехавший
    профиль — гейт test_refuses_below_threshold); повторы токенов
    обязательности («Нет» в булевых колонках) и небуквенных значений
    (прочерки, числа) — данные."""
    if len(row) < 3:
        return False
    non_empty = [_norm_cell(v) for v in row if _norm_cell(v)]
    if len(non_empty) < 3:
        return False
    val = max(set(non_empty), key=non_empty.count)
    cnt = non_empty.count(val)
    if cnt < 3 or 2 * cnt < len(row):
        return False
    if len(non_empty) - cnt > 1:
        return False
    if _looks_like_obligation(val) or not re.search(r"[а-яёa-z]", val):
        return False
    return True


def validate_columns(headers: List[str], rows: List[List[str]],
                     path_index: Optional[int] = 0,
                     source_literals: Optional[Dict[str, set]] = None,
                     source_mode: bool = False) -> List[dict]:
    """Проверка СМЫСЛА колонок (инвариант строк её не заменяет — урок
    разжалования итерации 3): для каждой колонки с распознанной ролью считает
    долю валидных значений. Возвращает список отчётов по колонкам.

    source_literals (роль → дословные значения той же роли в ИСТОЧНИКЕ):
    значение вне словаря роли, но дословно совпадающее с ячейкой источника,
    браком не считается — дословность переноса сильнее словаря (ложный БРАК
    жанра 3 file-storage, 2026-08-10: автор постановки написал «[1]» в
    колонке обязательности). Совпадение ищется ТОЛЬКО в колонке той же роли:
    «[1] где-то в источнике» переписанную кратность не оправдывает."""
    report: List[dict] = []
    # сигнатура таблицы связей МД («Связь | Сущность | Кратность …»):
    # роль кратн допускает логическую нотацию «1 : N» (шаблон data-model);
    # в таблицах параметров послабления нет (src-locks, 2026-08-14)
    hdr_keys = [_title_key(h) for h in headers]
    links_table = any("связ" in h for h in hdr_keys) and any(
        "сущност" in h for h in hdr_keys)
    # строки-разделы (протяжка colspan на всю ширину) — не данные:
    # исключаются из подсчёта валидности, из сетки не удаляются
    data_rows = [r for r in rows if not _is_section_row(r)]
    for i, title in enumerate(headers):
        low = _title_key(title)
        check = None
        role = None
        if path_index is not None and i == path_index:
            role, check = "путь", _looks_like_path
        elif "обяз" in low and "уник" in low:
            # комбинированная шапка «Обязательность / Уникальность»
            role, check = "обязат", _looks_like_obligation_pair
        else:
            # сокращённые заголовки карточек («Обяз.», «Крат.») — по
            # префиксу; «Краткое описание» кратностью НЕ является
            if "обяз" in low:
                role, check = "обязат", _looks_like_obligation
            elif _is_cardinality_title(low):
                role, check = "кратн", _looks_like_cardinality
            if role == "обязат" and source_mode:
                # структурный ряд ЭФ-таблицы полей («Раздел "…"»,
                # «Блок "…"», «Вкладка "…"») протягивается источником
                # в колонку обязательности — это ярлык ряда, не
                # значение (отказы z01/z03 ISS-03 на 2166860242 и
                # 2166860176); в --check карточек послабления нет
                base_obl = check
                check = (lambda v, _b=base_obl:
                         _b(v) or bool(_STRUCT_LABEL_RE.match(
                             _plain(v).strip()))
                         or bool(_STRUCT_LABEL_BARE_RE.match(
                             _plain(v).strip())))
            if role == "кратн" and (links_table or source_mode):
                # source_mode (нормализация ИСТОЧНИКА, ISS-01 2026-08-27):
                # авторская нотация кратности КК_ВК — голая логическая
                # («1», «0..1»); защита от раскавычивания [1] → 1 живёт
                # в --check КАРТОЧКИ (source_mode=False) и не ослаблена
                check = _looks_like_cardinality_logical
            if check is None and ("назван" in low or "наимен" in low
                                  or "параметр" in low) \
                    and "бд" not in low and "dev" not in low:
                # «[DEV] Название поля в таблице БД» — колонка физимён,
                # роль «название» ей не назначается (ложные
                # «подозрительные названия» на путях eco_*, ISS-01)
                role, check = "название", _no_xml_path
        if check is None:
            continue
        bad = [r[i] for r in data_rows if i < len(r) and not check(r[i])]
        wl = (source_literals or {}).get(role) or set()
        pardoned = [v for v in bad if _norm_cell(v) and _norm_cell(v) in wl]
        bad = [v for v in bad if not (_norm_cell(v) and _norm_cell(v) in wl)]
        total = len(data_rows) or 1
        suspicious = ([r[i] for r in data_rows if i < len(r) and r[i].strip()
                       and _title_suspicious(r[i])]
                      if role == "название" else [])
        # OQ-128: голый словарный тип как имя, дословно стоящий в колонке
        # названий ИСТОЧНИКА, — его содержимое, не дефект переноса
        susp_pardoned = [v for v in suspicious
                         if _bare_type_name(v) and _norm_cell(v) in wl]
        suspicious = [v for v in suspicious if v not in susp_pardoned]
        report.append({
            "column": title, "role": role, "index": i,
            "bad": len(bad), "total": len(data_rows),
            "valid_pct": round(100 * (len(data_rows) - len(bad)) / total, 1),
            "suspicious": suspicious[:5], "suspicious_count": len(suspicious),
            "suspicious_pardoned": susp_pardoned[:3],
            "suspicious_pardoned_count": len(susp_pardoned),
            "samples": bad[:3],
            "pardoned": pardoned[:3], "pardoned_count": len(pardoned),
        })
    return report
