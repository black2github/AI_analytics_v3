# app/scripts/CI/normalize_tables.py
#
# Нормализатор сырых HTML-таблиц в markdown-файлах (проход 1
# двухпроходного разбора source-parsing).
#
# Архитектура — три слоя по критерию «понимание — LLM, массовое
# переписывание — скрипт»:
#   1. СЕТКА (этот скрипт): раскрытие rowspan/colspan в полную матрицу с
#      протяжкой объединённых значений — чистая грамматика HTML.
#   2. РОЛИ КОЛОНОК (вне скрипта): профиль таблицы — какие колонки образуют
#      иерархию пути, какие переносятся как есть. Профиль пишет LLM/аналитик
#      один раз на макет (--sample выдаёт шапку и строки-образцы как вход
#      для разметки); знакомый макет узнаётся без LLM.
#   3. СБОРКА (этот скрипт): плоская markdown-таблица по профилю, склейка
#      путей, счётный инвариант «строк в результате = строк сетки».
#
# Утилита класса critic: работает по локальным .md многократно, исходный
# файл НЕ изменяет (режимы: stdout / sidecar). Confluence не нужен —
# сырой HTML уже сохранён консервативной миграцией.
#
# Формат профиля (JSON):
#   {
#     "name": "integration-params",
#     "header_rows": 1,
#     "hierarchy_cols": [0, 1, 2],       # колонки, образующие путь (по порядку)
#     "path_title": "XML-элемент",       # заголовок колонки пути
#     "path_join": "/",
#     "keep_cols": [[3, "Тип"], [4, "Обяз."]]   # [индекс, целевой заголовок]
#   }
# Без профиля — passthrough: сетка выводится как есть (уже ценно: снята
# нерегулярность rowspan/colspan).

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag


# ---------- слой 1: сетка ----------

def cell_text(cell: Tag) -> str:
    """Текст ячейки для плоской таблицы: ссылки — markdown, переносы — <br>,
    вертикальная черта экранируется (не ломать pipe-таблицу)."""
    parts: List[str] = []

    def walk(node) -> None:
        if isinstance(node, NavigableString):
            parts.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        if node.name == "br":
            parts.append("\n")
            return
        if node.name in ("strong", "b"):
            inner = node.get_text(" ", strip=True)
            if inner:
                parts.append(f"**{inner}**")
            return
        if node.name in ("em", "i"):
            inner = node.get_text(" ", strip=True)
            if inner:
                parts.append(f"*{inner}*")
            return
        if node.name in ("s", "strike", "del"):
            inner = node.get_text(" ", strip=True)
            if inner:
                parts.append(f"~~{inner}~~")
            return
        if node.name == "u":
            inner = node.get_text(" ", strip=True)
            if inner:                      # у markdown нет подчёркивания —
                parts.append(f"<u>{inner}</u>")   # тег переносится литералом
            return
        if node.name == "img":
            src = node.get("src", "")
            alt = node.get("alt", "")
            parts.append(f"![{alt}]({src})" if src else f"[img: {alt}]")
            return
        if node.name == "a":
            text = node.get_text(" ", strip=True)
            href = node.get("href", "")
            parts.append(f"[{text}]({href})" if href else text)
            return
        if node.name in ("p", "li", "div", "tr"):
            for ch in node.children:
                walk(ch)
            parts.append("\n")
            return
        if node.name in ("ul", "ol"):
            # Перенос ПЕРЕД вложенным списком: в источнике «<strong>иначе:</strong>
            # <ul><li>Если…» текст слипался в «**иначе:**Если» — CommonMark не
            # закрывает жирный перед буквой, и в рендере жирность пропадала
            # (замечание пользователя, итерация 6-секст, 2026-08-09).
            if parts and not parts[-1].endswith("\n"):
                parts.append("\n")
            for ch in node.children:
                walk(ch)
            return
        for ch in node.children:
            walk(ch)

    for ch in cell.children:
        walk(ch)

    text = "".join(parts)
    lines = []
    for ln in text.split("\n"):
        # Ведущие NBSP — отступ вложенности если-то-иначе (нотация: 4 nbsp
        # на уровень): сохраняются как &nbsp;. Их потеря сплющивала вложенные
        # условия — замечание пользователя по итерации 5 (проход 1 отвечает
        # за структуру, включая отступы условий). NBSP внутри строки — пробел.
        stripped = ln.lstrip("  ")
        indent = "&nbsp;" * ln[: len(ln) - len(stripped)].count(" ")
        body = re.sub(r"\s+", " ", stripped.replace(" ", " ")).strip()
        if body:
            lines.append(indent + body)
    return "<br>".join(lines).replace("|", "\\|")


def expand_grid(table: Tag) -> List[List[str]]:
    """Раскрывает таблицу в полную матрицу: rowspan/colspan разворачиваются,
    значение объединённой ячейки протягивается на все накрытые позиции."""
    grid: List[List[Optional[str]]] = []
    # занятость будущих строк: col -> (оставшийся rowspan, значение)
    carry: Dict[int, List] = {}

    # только строки ЭТОЙ таблицы: tr вложенной таблицы (таблица полей в
    # ячейке шаговой таблицы «Логики») подмешивались в сетку внешней —
    # гейт полноты требовал их имена (storage_type, intc-035, 2026-08-14);
    # вложенная таблица остаётся текстом родительской ячейки
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        row: List[Optional[str]] = []
        col = 0

        def fill_carry() -> None:
            nonlocal col
            while col in carry:
                remaining, value = carry[col]
                row.append(value)
                remaining -= 1
                if remaining:
                    carry[col][0] = remaining
                else:
                    del carry[col]
                col += 1

        fill_carry()
        for cell in tr.find_all(["td", "th"], recursive=False):
            fill_carry()
            value = cell_text(cell)
            colspan = int(cell.get("colspan", 1) or 1)
            rowspan = int(cell.get("rowspan", 1) or 1)
            for _ in range(colspan):
                row.append(value)
                if rowspan > 1:
                    carry[col] = [rowspan - 1, value]
                col += 1
        fill_carry()
        grid.append(row)

    width = max((len(r) for r in grid), default=0)
    return [[("" if v is None else v) for v in r] + [""] * (width - len(r))
            for r in grid]


# Замкнутый словарь HTML: всё, что не входит сюда, — не разметка, а ДАННЫЕ
# (токены-имена вида <GUID>, <CardID>, <XS:…>). Парсер HTML съедал бы их
# молча как «теги» — правило треугольных скобок source-parsing.md. Принцип
# без перечисления случаев: HTML — конечный стандарт, незнакомый «тег» = токен.
_KNOWN_HTML_TAGS = frozenset({
    "a", "abbr", "b", "blockquote", "br", "caption", "code", "col",
    "colgroup", "dd", "del", "div", "dl", "dt", "em", "font", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "li", "mark", "ol",
    "p", "pre", "s", "small", "span", "strike", "strong", "sub", "sup",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "tt", "u", "ul",
})

_TAGLIKE_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9_:.-]*)((?:\s[^<>]*)?)(/?)>")


def protect_token_tags(md_text: str) -> str:
    """Экранирует «теги», не входящие в словарь HTML: <GUID> → &lt;GUID&gt;.
    Без защиты парсер разбирал их как элементы и токен пропадал из ячейки
    (тихая потеря данных). Кириллические токены (<ФИО …>) парсер и так
    считает текстом — правка их не касается."""
    def esc(m: "re.Match[str]") -> str:
        if m.group(1).lower() in _KNOWN_HTML_TAGS:
            return m.group(0)
        return m.group(0).replace("<", "&lt;").replace(">", "&gt;")
    return _TAGLIKE_RE.sub(esc, md_text)


def find_top_tables(md_text: str) -> List[Tag]:
    """Верхнеуровневые сырые HTML-таблицы файла (вложенные обрабатываются
    в составе родительской ячейки текстом; их структура — отдельной таблицей
    при необходимости, через --table по индексу)."""
    soup = BeautifulSoup(protect_token_tags(md_text), "html.parser")
    return [t for t in soup.find_all("table") if not t.find_parent("table")]


# ---------- слой 2: профиль ----------

@dataclass
class Profile:
    name: str = "passthrough"
    header_rows: int = 1
    hierarchy_cols: List[int] = field(default_factory=list)
    path_title: str = "Путь"
    path_join: str = "/"
    keep_cols: List[Tuple[int, str]] = field(default_factory=list)
    # Режим «лесенки»: уровень вложенности = стартовая колонка значения;
    # родитель объявлен строкой ВЫШЕ (у детей колонки слева пусты) — путь
    # наследует префикс предыдущей строки до уровня первой непустой колонки.
    ladder: bool = False
    # Режим «блоки шапки» (рекомендуемый): роли назначаются не абсолютными
    # индексами колонок, а блоками шапки — прогон значения привязывается к
    # блоку по стартовой колонке. Устойчив к нерегулярной нарезке colspan,
    # из-за которой режим индексов давал брак (~30 % строк: текст в пути,
    # пути в «Названии» — разжалование итерации 3, 2026-08-06).
    blocks: bool = False
    path_block: int = 0
    # Чистка wildcard-сегментов пути (2026-08-09, решение пользователя):
    # источник оформляет контейнеры как «ObjectBody/*», лесенка склеивает их в
    # «ObjectBody/*/Context/*/…» — в XML-пути «/*/» лишний. Ошибка тянется из
    # исходника и правится автоматом: сегменты «*» убираются при сборке пути.
    strip_path_wildcards: bool = False

    @staticmethod
    def load(path: Path) -> "Profile":
        data = json.loads(path.read_text(encoding="utf-8"))
        return Profile(
            name=data.get("name", path.stem),
            header_rows=int(data.get("header_rows", 1)),
            hierarchy_cols=list(data.get("hierarchy_cols", [])),
            path_title=data.get("path_title", "Путь"),
            path_join=data.get("path_join", "/"),
            keep_cols=[(int(i), str(t)) for i, t in data.get("keep_cols", [])],
            ladder=bool(data.get("ladder", False)),
            blocks=bool(data.get("blocks", False)),
            path_block=int(data.get("path_block", 0)),
            strip_path_wildcards=bool(data.get("strip_path_wildcards", False)),
        )


_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _title_key(title: str) -> str:
    """Заголовок → ключ для распознавания роли: <br> внутри слова («Крат<br>ность»)
    снимается, регистр и пробелы нормализуются. Без этого роль не находилась и
    роли колонок съезжали (найдено при доработке 2026-08-06)."""
    return re.sub(r"\s+", " ", _BR_RE.sub("", title)).strip().lower()


def row_runs(row: List[str]) -> List[Tuple[int, str]]:
    """Строка → прогоны (стартовая колонка, значение): подряд идущие одинаковые
    значения схлопываются. Протяжка colspan даёт повторы — они не данные, а
    геометрия; пустые значения отбрасываются."""
    runs: List[Tuple[int, str]] = []
    prev: Optional[str] = None
    for idx, value in enumerate(row):
        if value and value != prev:
            runs.append((idx, value))
        prev = value if value else None
    return runs


def header_blocks(grid: List[List[str]], header_rows: int = 1) -> List[Tuple[int, int, str]]:
    """Блоки шапки: (стартовая колонка, конечная колонка включительно, заголовок).

    Шапка обычно нарезана colspan'ами по смысловым колонкам — прогоны её строки
    и есть блоки. Многострочная шапка: берётся первая строка (остальные —
    подзаголовки, они уточняют, но границ не меняют)."""
    if not grid:
        return []
    runs = row_runs(grid[0])
    width = len(grid[0])
    blocks: List[Tuple[int, int, str]] = []
    for i, (start, title) in enumerate(runs):
        end = (runs[i + 1][0] - 1) if i + 1 < len(runs) else (width - 1)
        blocks.append((start, end, title))
    return blocks


# ---------- слой 3: сборка ----------

def _block_roles(blocks: List[Tuple[int, int, str]], path_index: int) -> List[str]:
    """Роли блоков по заголовку: якорные (кратность, обязательность),
    тип, название — и свободные."""
    roles: List[str] = []
    for i, (_s, _e, title) in enumerate(blocks):
        low = _title_key(title)
        if i == path_index:
            roles.append("path")
        elif "кратн" in low:
            roles.append("card")
        elif "обязат" in low:
            roles.append("obl")
        elif "тип" in low:
            roles.append("type")
        elif "назван" in low or "наимен" in low or "параметр" in low:
            # «Параметр» — синоним названия в плоских таблицах без XML-иерархии
            # (генерализационный тест «Метод-запроса-QR-кода», 2026-08-09)
            roles.append("name")
        else:
            roles.append("free")
    return roles


def blocks_profile_applies(grid: List[List[str]], profile: Profile) -> bool:
    """True — шапка таблицы несёт якорные роли, профиль собирает пути;
    False — таблица другой природы, выводится сеткой без сборки."""
    blocks = header_blocks(grid, profile.header_rows)
    if not blocks:
        return False
    p = min(profile.path_block, len(blocks) - 1)
    return any(r in ("card", "obl") for r in _block_roles(blocks, p))


def build_flat_blocks(grid: List[List[str]], profile: Profile) -> Tuple[List[str], List[List[str]]]:
    """Сборка по блокам шапки (рекомендуемый режим, см. Profile.blocks).

    Каждый прогон строки привязывается к блоку шапки по СТАРТОВОЙ колонке;
    несколько прогонов в одном блоке склеиваются. Блок пути (path_block)
    собирает иерархию: прогоны внутри него — уровни, при ladder=True префикс
    наследуется от предыдущей строки до уровня первого прогона.
    """
    blocks = header_blocks(grid, profile.header_rows)
    if not blocks:
        return [], []

    def block_of(col: int) -> int:
        for i, (start, end, _t) in enumerate(blocks):
            if start <= col <= end:
                return i
        return len(blocks) - 1

    p = min(profile.path_block, len(blocks) - 1)
    roles = _block_roles(blocks, p)

    # Применимость профиля к КОНКРЕТНОЙ таблице: сборка путей имеет смысл
    # только там, где шапка несёт якорные роли (кратность/обязательность).
    # Файл может содержать таблицы другой природы (перечень кодов отказов,
    # свойства обмена) — применение к ним профиля XML-структуры склеивало
    # колонки в псевдо-путь «1/EIO1» (брак итерации 6-тер, 2026-08-07).
    # Такие таблицы выводятся сеткой как есть: rowspan/colspan раскрыты,
    # колонки на местах, ничего не теряется и не переносится.
    if not any(r in ("card", "obl") for r in roles):
        plain_headers = [title for _s, _e, title in blocks]
        plain_out: List[List[str]] = []
        for row in grid[profile.header_rows:]:
            buckets: List[List[str]] = [[] for _ in blocks]
            for c, v in row_runs(row):
                buckets[block_of(c)].append(v)
            plain_out.append([" ".join(b) for b in buckets])
        return plain_headers, plain_out

    headers = [profile.path_title if i == p else title for i, (_s, _e, title) in enumerate(blocks)]
    idx_card = roles.index("card") if "card" in roles else None
    idx_obl = roles.index("obl") if "obl" in roles else None
    idx_type = roles.index("type") if "type" in roles else None
    idx_name = roles.index("name") if "name" in roles else None

    out: List[List[str]] = []
    stack: List[Tuple[int, str]] = []   # лесенка: (стартовая колонка, значение)
    for row in grid[profile.header_rows:]:
        runs = row_runs(row)
        # ЯКОРЕНИЕ С КОНЦА: хвостовые блоки разбираются справа налево, при этом
        # блок с валидатором (кратность, обязательность) забирает прогон, только
        # если тот проходит проверку — иначе колонка пуста, а прогон достаётся
        # соседу слева. Границы блоков шапки не совпадают с геометрией глубоких
        # строк (colspan режет их иначе), поэтому привязка по стартовой колонке
        # затягивала текст названий в путь — брак итерации 3 (2026-08-06).
        buckets: List[List[Tuple[int, str]]] = [[] for _ in blocks]
        last = len(runs)          # граница «ещё не разобранного» слева

        # 0) хвостовые прогоны, СТАРТУЮЩИЕ в границах последнего блока
        # (правила/комментарий), снимаются ДО якорей. Два инцидента одного
        # класса: (а) строка без якорей — текст правил уезжал в «Название»
        # (итерация 6-секст, «Описание документа»); (б) таблица БЕЗ колонки
        # кратности — правила на хвосте ослепляли якорь обязательности, и все
        # значения склеивались в псевдо-путь (генерализационный тест на
        # «Метод-запроса-QR-кода», 2026-08-09). Привязка по стартовой колонке
        # безопасна: последний блок правее всех якорных.
        last_block_start = blocks[-1][0]
        while last > 0 and runs[last - 1][0] >= last_block_start:
            # разбор справа налево — insert(0) сохраняет исходный порядок прогонов
            buckets[len(blocks) - 1].insert(0, runs[last - 1])
            last -= 1

        # 1) якорь-кратность: самый правый прогон вида [N]/[0..1] — в пределах
        # ещё не разобранного (шаг 0 уже снял хвост последнего блока; поиск по
        # всем runs дублировал снятые прогоны — регресс перестановки 2026-08-09)
        pos_card = next((j for j in range(last - 1, -1, -1)
                         if _looks_like_cardinality_strict(runs[j][1])), None)
        if pos_card is not None and idx_card is not None:
            buckets[idx_card].append(runs[pos_card])
            # правее кратности, до снятого хвоста — комментарий (prepend:
            # эти прогоны в исходнике стоят ДО хвостовых)
            buckets[len(blocks) - 1][0:0] = runs[pos_card + 1:last]
            last = pos_card

        # 2) якорь-обязательность: ближайший слева прогон вида О/Н/У
        if idx_obl is not None and last > 0 and _looks_like_obligation_strict(runs[last - 1][1]):
            buckets[idx_obl].append(runs[last - 1])
            last -= 1

        # 3) тип — короткий токен слева от обязательности
        if idx_type is not None and last > 0 and _looks_like_type(runs[last - 1][1]):
            buckets[idx_type].append(runs[last - 1])
            last -= 1

        # 4) название — следующий свободный текст слева
        if idx_name is not None and last > 1:      # минимум один прогон должен остаться пути
            buckets[idx_name].append(runs[last - 1])
            last -= 1

        # 5) всё оставшееся слева — иерархия пути
        for r in runs[:last]:
            buckets[p].append(r)

        # Проза внутри блока пути — не уровень иерархии, а пояснение исходника
        # («1 Вариант — Успешный …», «все поля внутри блока передаются …»).
        # В путь её пускать нельзя (она станет префиксом всех потомков), терять
        # тоже нельзя — место пояснений «Правила заполнения» (замечание
        # пользователя по 6-окт, 2026-08-09: раньше проза уводилась в
        # «Название» и читалась как имя параметра).
        path_runs = [r for r in buckets[p] if _looks_like_path(_plain(r[1]))]
        prose = [r for r in buckets[p] if not _looks_like_path(_plain(r[1]))]

        # Строка-пояснение: в зоне пути НЕТ ни одного пути (только проза).
        # Такая строка описывает блок целиком (пояснение + пример, пример
        # часто стартует в зоне «Названия» — «{ "CL_ORG": … }»): ВЕСЬ её
        # контент уходит в последний блок в исходном порядке, путь и
        # название остаются пустыми, лесенка не наследуется.
        if prose and not path_runs:
            note_runs = list(prose)
            if idx_name is not None and buckets[idx_name]:
                note_runs += buckets[idx_name]
                buckets[idx_name] = []
            note_runs.sort(key=lambda r: r[0])      # исходный порядок колонок
            buckets[p] = []
            buckets[len(blocks) - 1][0:0] = note_runs
            out.append([("" if i == p else
                         " ".join((_plain(v) if roles[i] in ("card", "obl", "type", "name")
                                   else v) for _c, v in bucket))
                        for i, bucket in enumerate(buckets)])
            continue

        if prose:
            buckets[len(blocks) - 1] = list(prose) + buckets[len(blocks) - 1]
        # Строка-секция: единственный прогон, и тот — не путь, а фраза
        # («1 Вариант — Успешный …»). Такие строки в исходнике играют роль
        # подзаголовка; в лесенку их пускать нельзя — иначе фраза становится
        # префиксом пути у всех потомков (брак итерации 3).
        is_section = len(runs) == 1 and not _looks_like_path(_plain(runs[0][1]))
        if profile.ladder and not is_section:
            if path_runs:
                first = path_runs[0][0]
                stack = [e for e in stack if e[0] < first] + list(path_runs)
            parts = [_plain(v) for _c, v in stack]
        elif profile.ladder:
            parts = [_plain(v) for _c, v in path_runs]  # секция выводится как есть
        else:
            parts = [_plain(v) for _c, v in path_runs]
        path = profile.path_join.join(parts)
        if profile.path_join == "/":
            path = re.sub(r"/{2,}", "/", path)
        if profile.strip_path_wildcards:
            # «ObjectBody/*/Context/*/X» → «ObjectBody/Context/X» (лишние «/*/»
            # из оформления контейнеров исходника; решение пользователя 2026-08-09)
            path = re.sub(r"/\*(?=/|$)", "", path)

        cells: List[str] = []
        for i, bucket in enumerate(buckets):
            if i == p:
                cells.append(path)
            elif roles[i] in ("card", "obl", "type", "name"):
                # якорные колонки — чистые значения (О, [1] без «**»)
                cells.append(" ".join(_plain(v) for _c, v in bucket))
            else:       # свободные (правила, комментарий) — с форматированием
                cells.append(" ".join(v for _c, v in bucket))
        out.append(cells)
    return headers, out


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


def _looks_like_type(v: str) -> bool:
    """Короткий токен типа данных (string, GUID, Varchar100, дата…).

    Якорь мягкий: длинные фразы и предложения типом не считаются — они уходят
    в «Название», иначе описание контейнера («Блок с телом запроса») заняло бы
    колонку типа и сдвинуло все роли.
    """
    v = _plain(v).strip().rstrip(".")
    # «string (30)», «Varchar (100)» — тип с пробелом перед скобками размера;
    # без нормализации якорь не срабатывал и тип уезжал в «Название»
    # (замечание пользователя по 6-нон, строка /RelType, 2026-08-09)
    v = re.sub(r"\s+\(", "(", v)
    if not v or len(v) > 24 or " " in v:
        return False
    base = re.sub(r"[\d()\[\]]+$", "", v).lower()
    return base in _TYPE_TOKENS or bool(re.match(r"^[a-z][a-z0-9_]*\d*$", v.lower()))


def _plain(v: str) -> str:
    """Значение без markdown-разметки (**жирный**, *курсив*) — для путей и
    якорных проверок. После сохранения форматирования в cell_text жирное
    «**О**» переставало распознаваться якорем обязательности и вместе с
    названием утекало в путь — брак итерации 6-бис (2026-08-07).
    Форматирование остаётся только в свободных колонках (правила, комментарий).
    Одиночная «*» НЕ трогается — в путях это wildcard-сегмент (ObjectBody/*)."""
    v = v.replace("**", "").replace("~~", "")
    v = re.sub(r"</?u>", "", v)
    return re.sub(r"\*([^*\s][^*]*)\*", r"\1", v)


def _anchor_key(v: str) -> str:
    """Значение → форма для якорной проверки: <br>, markdown-разметка и
    краевые точки/пробелы снимаются. Без нормализации «[1]<br>» или «О.» не
    распознавались, якорь не срабатывал, и хвост строки утекал в путь."""
    return _BR_RE.sub(" ", _plain(v)).strip().strip(".").strip()


def _looks_like_cardinality_strict(v: str) -> bool:
    """Строгий якорь для разбора справа: пустое значение НЕ считается кратностью
    (иначе блок «съел» бы чужой прогон)."""
    return bool(_CARDINALITY_RE.match(_anchor_key(v)))


def _looks_like_obligation_strict(v: str) -> bool:
    return _anchor_key(v).upper() in {
        "-", "—", "О", "Н", "У", "O", "H", "Y", "ДА", "НЕТ", "M", "М"}


def _looks_like_obligation(v: str) -> bool:
    # О/Н/У в кириллице и латинские омоглифы O/H/Y; «Да/Нет/Усл.» (словарь
    # карточек, режим --check); прочерк; пусто
    return v.strip().strip(".").upper() in {
        "", "-", "—", "О", "Н", "У", "O", "H", "Y", "ДА", "НЕТ", "УСЛ", "M", "М"}


def _looks_like_cardinality(v: str) -> bool:
    return not v.strip() or bool(_CARDINALITY_RE.match(v.strip()))


def _looks_like_path(v: str) -> bool:
    v = v.strip()
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
    return _looks_like_type(v)          # чистый тип данных — не название


def validate_columns(headers: List[str], rows: List[List[str]],
                     path_index: Optional[int] = 0,
                     source_literals: Optional[Dict[str, set]] = None) -> List[dict]:
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
    for i, title in enumerate(headers):
        low = _title_key(title)
        check = None
        role = None
        if path_index is not None and i == path_index:
            role, check = "путь", _looks_like_path
        else:
            for key, fn in _COLUMN_RULES:
                # key[:4] — сокращённые заголовки карточек («Обяз.», «Крат.»)
                if key in low or key[:4] in low:
                    role, check = key, fn
                    break
            if check is None and ("назван" in low or "наимен" in low
                                  or "параметр" in low):
                role, check = "название", _no_xml_path
        if check is None:
            continue
        bad = [r[i] for r in rows if i < len(r) and not check(r[i])]
        wl = (source_literals or {}).get(role) or set()
        pardoned = [v for v in bad if _norm_cell(v) and _norm_cell(v) in wl]
        bad = [v for v in bad if not (_norm_cell(v) and _norm_cell(v) in wl)]
        total = len(rows) or 1
        suspicious = ([r[i] for r in rows if i < len(r) and r[i].strip()
                       and _title_suspicious(r[i])]
                      if role == "название" else [])
        report.append({
            "column": title, "role": role, "index": i,
            "bad": len(bad), "total": len(rows),
            "valid_pct": round(100 * (len(rows) - len(bad)) / total, 1),
            "suspicious": suspicious[:5], "suspicious_count": len(suspicious),
            "samples": bad[:3],
            "pardoned": pardoned[:3], "pardoned_count": len(pardoned),
        })
    return report


def build_flat(grid: List[List[str]], profile: Profile) -> Tuple[List[str], List[List[str]]]:
    """Собирает плоскую таблицу по профилю. Возвращает (заголовки, строки).
    Инвариант нулевых потерь: len(строк) == len(grid) - header_rows —
    проверяется вызывающим кодом (assert_invariant)."""
    if profile.blocks:
        return build_flat_blocks(grid, profile)

    data_rows = grid[profile.header_rows:]

    if not profile.hierarchy_cols and not profile.keep_cols:
        headers = grid[0] if grid else []
        return list(headers), [list(r) for r in data_rows]

    headers = [profile.path_title] + [t for _, t in profile.keep_cols]
    out: List[List[str]] = []
    # стек лесенки: (стартовая колонка, значение) — живёт между строками
    stack: List[Tuple[int, str]] = []
    for row in data_rows:
        # непустые значения иерархических колонок с их стартовой позицией;
        # протяжка colspan даёт повтор в соседних колонках — дубли подряд не клеим
        entries: List[Tuple[int, str]] = []
        prev: Optional[str] = None
        for idx in profile.hierarchy_cols:
            value = row[idx] if idx < len(row) else ""
            if value and value != prev:
                entries.append((idx, value))
            prev = value or None
        if profile.ladder:
            if entries:
                first = entries[0][0]
                stack = [e for e in stack if e[0] < first] + entries
            path_parts = [_plain(v) for _, v in stack]
        else:
            path_parts = [_plain(v) for _, v in entries]
        path = profile.path_join.join(path_parts)
        if profile.path_join == "/":
            # значения лесенки часто сами несут слэши («/MessageId», «Body/*») —
            # схлопываем дубли разделителя до одного
            path = re.sub(r"/{2,}", "/", path)
        if profile.strip_path_wildcards:
            path = re.sub(r"/\*(?=/|$)", "", path)
        out.append([path] + [(row[i] if i < len(row) else "") for i, _ in profile.keep_cols])
    return headers, out


def assert_invariant(grid: List[List[str]], profile: Profile,
                     rows: List[List[str]]) -> str:
    expected = len(grid) - profile.header_rows
    got = len(rows)
    status = "✓" if expected == got else "✗ ПОТЕРЯ СТРОК"
    return (f"инвариант строк: сетка {expected} → выход {got} {status}; "
            f"колонок сетки: {len(grid[0]) if grid else 0}")


def render_markdown(headers: List[str], rows: List[List[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "---|" * len(headers)]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def render_sample(grid: List[List[str]], header_rows: int = 1, n: int = 3) -> str:
    """Вход для LLM-разметки ролей: пронумерованные колонки шапки +
    первые строки сетки. Маленький выход — читается целиком."""
    lines = ["Колонки сетки (для разметки ролей — какие образуют иерархию пути):"]
    for r in grid[:header_rows]:
        lines.append("  шапка: " + " ; ".join(f"[{i}] {v}" for i, v in enumerate(r)))
    for j, r in enumerate(grid[header_rows:header_rows + n]):
        lines.append(f"  строка {j + 1}: " + " ; ".join(f"[{i}] {v[:40]}" for i, v in enumerate(r)))
    return "\n".join(lines)


# ---------- CLI ----------

def normalize_file(md_path: Path, profile: Optional[Profile],
                   table_index: Optional[int],
                   min_valid_pct: float = 95.0) -> Tuple[str, List[str], bool]:
    """Возвращает (markdown-выход, отчёт-строки, ok).

    ok=False — хотя бы одна колонка с распознанной ролью не дотянула до
    порога min_valid_pct: результат считается браком и НЕ отдаётся
    (профиль не подходит таблице). Брак не должен покидать утилиту —
    иначе он утекает в прогон агента и размножается (разжалование
    итерации 3, 2026-08-06).
    """
    text = md_path.read_text(encoding="utf-8")
    tables = find_top_tables(text)
    report: List[str] = [f"файл: {md_path.name}; верхнеуровневых таблиц: {len(tables)}"]
    chunks: List[str] = []
    prof = profile or Profile()
    ok = True

    for i, t in enumerate(tables):
        if table_index is not None and i != table_index:
            continue
        grid = expand_grid(t)
        headers, rows = build_flat(grid, prof)
        applied = not prof.blocks or blocks_profile_applies(grid, prof)
        note = "" if applied else "; профиль не применён (нет якорных колонок) — сетка как есть"
        report.append(f"таблица {i}: {assert_invariant(grid, prof, rows)}{note}")

        if prof.blocks:
            path_index = min(prof.path_block, max(len(headers) - 1, 0)) if applied else None
        else:
            path_index = 0
        for col in validate_columns(headers, rows, path_index=path_index):
            mark = "✓" if col["valid_pct"] >= min_valid_pct else "✗ НИЖЕ ПОРОГА"
            report.append(
                f"   колонка «{col['column'][:28]}» (роль: {col['role']}): "
                f"валидных {col['valid_pct']}% [{col['total'] - col['bad']}/{col['total']}] {mark}")
            if col["valid_pct"] < min_valid_pct:
                ok = False
                for s in col["samples"]:
                    report.append(f"      пример брака: {s[:80]!r}")
            if col.get("suspicious_count"):
                # Не отказ нормализации: содержимое лежит так У АВТОРА источника.
                # Разнесение (название дословно / пояснения в правила) — работа
                # прохода 2; --check карточки этот долг превращает в брак.
                report.append(
                    f"   ⚠ подозрительных названий: {col['suspicious_count']} — "
                    f"пояснения/значения/тип в колонке названия, разнести на проходе 2")
                for s in col["suspicious"][:3]:
                    report.append(f"      кандидат: {s[:80]!r}")
        caption = prof.name if applied else f"{prof.name}; сетка без сборки путей"
        chunks.append(f"## Таблица {i} (профиль: {caption})\n\n"
                      + render_markdown(headers, rows))
    return "\n\n".join(chunks), report, ok


def parse_md_tables(md_text: str) -> List[Tuple[List[str], List[List[str]]]]:
    """Готовые pipe-таблицы markdown-файла → (заголовки, строки).
    Обратные кавычки вокруг значений (`ObjectBody/*`) снимаются: это
    оформление карточки, а не содержимое."""
    tables: List[Tuple[List[str], List[List[str]]]] = []
    block: List[List[str]] = []

    def flush() -> None:
        nonlocal block
        if len(block) >= 2:
            tables.append((block[0], block[1:]))
        block = []

    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            if set(s.replace("|", "").replace(" ", "")) <= {"-", ":"}:
                continue                        # строка-разделитель шапки
            block.append([c.strip().strip("`").strip()
                          for c in s.strip("|").split("|")])
        else:
            flush()
    flush()
    return tables


def _strip_markdown_links(v: str) -> str:
    """Снять [text](url), в т.ч. когда text содержит внутренние «[…]»
    (названия Confluence вида «[Файловый сервис] Клиент: …»).

    Закрывающая скобка ищется БАЛАНСОМ, а не первым «](»: непарный «[»
    раньше по тексту (например кратность [1]) склеивал чужой текст в
    "текст ссылки" и валил сверку правильной карточки (инцидент
    intc-014, 2026-08-14 — агент из-за этого убирал ссылки)."""
    out: List[str] = []
    i = 0
    n = len(v)
    while i < n:
        if v[i] != "[":
            out.append(v[i])
            i += 1
            continue
        depth = 0
        j = i
        while j < n:
            if v[j] == "[":
                depth += 1
            elif v[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j < n and j + 1 < n and v[j + 1] == "(":
            url_end = v.find(")", j + 2)
            if url_end != -1:
                out.append(v[i + 1:j])
                i = url_end + 1
                continue
        out.append(v[i])
        i += 1
    return "".join(out)


def _norm_cell(v: str) -> str:
    """Нормальная форма значения для сверки наличия: без markdown-разметки,
    бэктиков, <br> и лишних пробелов, в нижнем регистре.

    Markdown-ссылки сводятся к тексту-названию: URL — навигация, не литерал.
    Иначе замена живого URL Confluence относительной ссылкой на карточку
    (правило шаблона контрактов) валила сверку паспорта §1 — агент был
    зажат между правилом и гейтом (OQ-029 file-storage, 2026-08-13)."""
    v = _BR_RE.sub(" ", _plain(v)).replace("`", "").replace("\\|", "|")
    v = _strip_markdown_links(v)
    # markdown-экранирование HTML→MD-конвертера выгрузки (\[ДСФ_ЭКО\] и т.п.):
    # карточка пишет чистый текст — сравниваем без обратных косых
    v = re.sub(r"\\([^\w\s])", r"\1", v)
    return re.sub(r"\s+", " ", v).strip().lower()


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
        for row in grid[1:]:
            for cell in row[:2]:
                v = _plain(_BR_RE.sub(" ", cell)).strip().strip("`").strip()
                if (2 < len(v) <= 64 and " " not in v
                        and _NAME_TOKEN_RE.match(v)
                        and v.lower() not in _TOKEN_STOP):
                    names.add(v)
    return names


_FM_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.M)


def _frontmatter_title(text: str) -> Optional[str]:
    """Значение title из YAML frontmatter (до второго ---); None, если нет."""
    body = text.lstrip("﻿")
    if not body.startswith("---"):
        return None
    end = body.find("\n---", 3)
    m = _FM_TITLE_RE.search(body[:end if end != -1 else 4000])
    if not m:
        return None
    v = m.group(1)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1].replace("''", "'") if v[0] == "'" else v[1:-1]
    return v


def check_title(card_text: str, source_text: str) -> Tuple[List[str], bool]:
    """Дословный перенос title источника во frontmatter карточки.

    title — постоянный атрибут (наименование в языке предметной области;
    у функций отражён в ролевой модели): при переименовании файлов в слаги
    он единственный носитель исходного наименования — тихая потеря хуже
    шумного отказа. Источник без title сверке не подлежит."""
    src = _frontmatter_title(source_text)
    if src is None:
        return [], True
    card = _frontmatter_title(card_text)
    if card == src:
        return [f"title: дословно перенесён ({src!r}) ✓"], True
    if card is None:
        return [f"title: ОТСУТСТВУЕТ в карточке — у источника {src!r} "
                "✗ ПОТЕРЯ НАИМЕНОВАНИЯ"], False
    return [f"title: расходится с источником ✗ (карточка {card!r}, "
            f"источник {src!r} — перенос дословный)"], False


def check_source_tables(card_text: str, source_text: str) -> Tuple[List[str], bool]:
    """Сверка с источником: каждая ГОТОВАЯ markdown-таблица источника (вне
    сырого HTML — например «Коды банковских продуктов») обязана присутствовать
    в карточке значениями ВСЕХ колонок.

    Агент четырежды ужимал справочник (итерации 6-секст…6-нон, 2026-08-09),
    в том числе обойдя словесный гейт «фрагмент» — сторожим содержимое, а не
    слова. Таблицы из 1 колонки или <2 строк не сверяются (служебные)."""
    report: List[str] = []
    ok = True
    card_norm = _norm_cell(card_text)
    for hdr, rows in parse_md_tables(source_text):
        if len(hdr) < 2 or len(rows) < 2:
            continue
        hdr_norm = " ".join(_norm_cell(h) for h in hdr)
        # Служебная секция «Документация» страницы (реестр док-файлов) —
        # в контракт не переносится, сверке не подлежит.
        if "документ" in hdr_norm and "дата" in hdr_norm:
            continue
        missing: List[str] = []
        for row in rows:
            # Строка с вложением (пример Запрос.xml/Ответ.xml) — целиком в
            # sidecar examples/, в карточке её значений законно нет.
            if any(_ATTACHMENT_RE.search(c) for c in row):
                continue
            for cell in row:
                cv = _norm_cell(cell)
                if cv and cv not in card_norm:
                    missing.append(cell.strip()[:60])
        if missing:
            ok = False
            title = " | ".join(h.strip() for h in hdr[:3])
            report.append(
                f"таблица источника «{title}» ({len(rows)} строк): в карточке "
                f"отсутствуют {len(missing)} значений ✗ НИЖЕ ПОРОГА")
            for v in missing[:3]:
                report.append(f"      пример потери: {v!r}")
    # Полнота HTML-таблиц источника: каждое имя параметра из раскрытых
    # сеток обязано присутствовать в карточке (инцидент 2026-08-12:
    # file_id/upload_token потеряны при зелёном гейте).
    html_names = html_param_names(source_text)
    lost = sorted(n for n in html_names if _norm_cell(n) not in card_norm)
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
            for key, _fn in _COLUMN_RULES:
                if key in low or key[:4] in low:
                    vals = lits.setdefault(key, set())
                    for r in rows:
                        if i < len(r) and _norm_cell(r[i]):
                            vals.add(_norm_cell(r[i]))
                    break

    for hdr, rows in parse_md_tables(source_text):
        add(hdr, rows)
    for t in find_top_tables(source_text):
        grid = expand_grid(t)
        if len(grid) > 1:
            add(grid[0], grid[1:])
    return lits


def check_file(md_path: Path, min_valid_pct: float = 95.0,
               source_text: Optional[str] = None) -> Tuple[List[str], bool]:
    """Режим --check: колонные валидаторы поверх ГОТОВОЙ карточки.

    Ловит класс «якорная колонка переписана при перекладке» (регресс
    кратности [1] → 1, итерация 6-кватер, 2026-08-07): утилита выдала
    валидную таблицу, а в карточку она попала с искажённым литералом.
    Роли распознаются по заголовкам; таблицы без ролей пропускаются
    (перечень кодов отказов, свойства обмена — им валидаторы не нужны).

    Дополнительно ловит МАРКЕРЫ СОКРАЩЕНИЯ («фрагмент», «см. источник»,
    «и т.д.»): агент трижды ужимал справочник «Коды банковских продуктов»
    до одной колонки с пометкой «(фрагмент из источника)», игнорируя
    правило, сверку и образец (итерации 6-секст/6-септ/6-окт, 2026-08-09) —
    текстовая доставка не доехала, ловим инструментом. В честных переносах
    этих слов нет (проверено по источнику и чистым прогонам)."""
    text = md_path.read_text(encoding="utf-8")
    report: List[str] = [f"проверка карточки: {md_path.name}"]
    ok = True
    src_literals = source_role_literals(source_text) if source_text else None

    # Голый текст, зажатый МЕЖДУ строками таблицы, — разорванная ячейка:
    # перенос строки внутри ячейки (вместо <br>) выталкивает её хвост из
    # таблицы (инцидент 6-дец: агент разнёс название и разрезал строку).
    lines = text.splitlines()
    for k, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("|") or s.startswith("#"):
            continue
        prev_is_pipe = k > 0 and lines[k - 1].strip().startswith("|")
        nxt = next((lines[j].strip() for j in range(k + 1, len(lines))
                    if lines[j].strip()), "")
        if prev_is_pipe and nxt.startswith("|"):
            ok = False
            report.append(
                f"строка {k + 1}: голый текст между строками таблицы — "
                f"разорванная ячейка (перенос внутри ячейки должен быть <br>) "
                f"✗ НИЖЕ ПОРОГА: {s[:70]!r}")

    # Порядок колонок справочников НЕ проверяется: решение пользователя
    # 2026-08-09 — переносится как в источнике (дословность; целевое
    # переформатирование — работа поздних слоёв, не миграции).
    for marker in ("фрагмент", "см. источник", "и т.д.", "и т. д."):
        cnt = text.lower().count(marker)
        if cnt:
            ok = False
            report.append(
                f"маркер сокращения «{marker}» ×{cnt}: справочники и перечни "
                f"источника переносятся ЦЕЛИКОМ, без «фрагментов» ✗ НИЖЕ ПОРОГА")
    for i, (headers, rows) in enumerate(parse_md_tables(text)):
        low0 = _title_key(headers[0]) if headers else ""
        # «Код параметра» — каноническая колонка путей (XML через /, JSON
        # через .); именно «код параметра» — «Код отказа» путём не является
        path_index = 0 if ("xml" in low0 or "элемент" in low0 or "путь" in low0
                           or ("код" in low0 and "параметр" in low0)) else None
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Нормализатор сырых HTML-таблиц в .md (проход 1). "
                    "Исходный файл не изменяется.")
    ap.add_argument("file", type=Path, help="markdown-файл с сырыми HTML-таблицами")
    ap.add_argument("--table", type=int, default=None, help="индекс таблицы (по умолчанию все)")
    ap.add_argument("--profile", type=Path, default=None, help="JSON-профиль ролей колонок")
    ap.add_argument("--sample", action="store_true",
                    help="выдать шапку и строки-образцы для LLM-разметки ролей")
    ap.add_argument("--check", action="store_true",
                    help="проверить ГОТОВУЮ карточку: колонные валидаторы по "
                         "pipe-таблицам (исходник не нужен); код 2 при браке")
    ap.add_argument("--source", type=Path, default=None,
                    help="для --check: файл-источник — markdown-таблицы "
                         "источника сверяются с карточкой по значениям "
                         "(потеря справочника = брак)")
    ap.add_argument("--sidecar", action="store_true",
                    help="записать результат в <файл>.tables.md рядом (иначе stdout)")
    ap.add_argument("--min-valid", type=float, default=95.0,
                    help="порог валидности колонки в %% (ниже — результат не отдаётся)")
    ap.add_argument("--force", action="store_true",
                    help="отдать результат даже ниже порога (для разбора брака)")
    args = ap.parse_args()

    profile = Profile.load(args.profile) if args.profile else None

    if args.check:
        src_text = (args.source.read_text(encoding="utf-8")
                    if args.source is not None else None)
        report, ok = check_file(args.file, min_valid_pct=args.min_valid,
                                source_text=src_text)
        if src_text is not None:
            card_text = args.file.read_text(encoding="utf-8")
            src_report, src_ok = check_source_tables(card_text, src_text)
            ttl_report, ttl_ok = check_title(card_text, src_text)
            report.extend(src_report)
            report.extend(ttl_report)
            ok = ok and src_ok and ttl_ok
        for line in report:
            print(f"# {line}", file=sys.stderr)
        if not ok:
            print("# БРАК: колонка ниже порога — литералы якорных колонок "
                  "(кратность, обязательность) переписаны при переносе. "
                  "Исправьте карточку по выходу утилиты.", file=sys.stderr)
            return 2
        print("# OK: все распознанные колонки выше порога.", file=sys.stderr)
        return 0

    if args.sample:
        text = args.file.read_text(encoding="utf-8")
        tables = find_top_tables(text)
        for i, t in enumerate(tables):
            if args.table is not None and i != args.table:
                continue
            grid = expand_grid(t)
            print(f"--- таблица {i} ({len(grid)} строк сетки) ---")
            print(render_sample(grid))
        return 0

    out, report, ok = normalize_file(args.file, profile, args.table,
                                     min_valid_pct=args.min_valid)
    for line in report:
        print(f"# {line}", file=sys.stderr)
    if not ok and not args.force:
        print("# ОТКАЗ: качество ниже порога — профиль не подходит этой таблице.",
              file=sys.stderr)
        print("#        Поправьте профиль (роли колонок) или запустите с --force "
              "для разбора брака.", file=sys.stderr)
        return 2
    if args.sidecar:
        target = args.file.with_suffix(args.file.suffix + ".tables.md")
        target.write_text(out + "\n", encoding="utf-8")
        print(f"# записано: {target}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
