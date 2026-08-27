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
    # «*» в путях — оформление контейнеров исходника, не данные: чистка
    # по умолчанию ВКЛЮЧЕНА (решение 2026-08-09 жило опцией профиля и не
    # дотиражировалось: intc-002 src-locks собрал BSDocument/*/… без
    # профиля, 2026-08-15)
    strip_path_wildcards: bool = True

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
            strip_path_wildcards=bool(data.get("strip_path_wildcards", True)),
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
    # карточек, режим --check); прочерк; пусто. Расширение по нотации
    # эталона docs-account-opening-request (разбор ✗ эталона 2026-08-21):
    # «обязателен»/«необязателен» и «Да/Нет (вход|исход)» — направление
    # параметра автор пишет в скобках той же ячейки. Строгий якорь
    # раскроя HTML (_strict) не трогаем — он держит сетки.
    # разметка снимается (_plain): авторы КК_ВК пишут «**Да**» жирным —
    # словарь сверяется с содержимым, не с оформлением (ISS-01 2026-08-27)
    u = _plain(v).strip().strip(".").upper()
    if u in {"", "-", "—", "О", "Н", "У", "O", "H", "Y", "ДА", "НЕТ",
             "УСЛ", "M", "М", "ОБЯЗАТЕЛЕН", "НЕОБЯЗАТЕЛЕН"}:
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
    vv = re.sub(r"\s+\(", "(", v)
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
        report.append({
            "column": title, "role": role, "index": i,
            "bad": len(bad), "total": len(data_rows),
            "valid_pct": round(100 * (len(data_rows) - len(bad)) / total, 1),
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
        # таблица без якорных ролей в шапке (свойства страницы, мета-строки
        # над атрибутной шапкой, справочники продуктов) — валидаторы не
        # применяются: их защита — от съехавшего профиля атрибутных таблиц,
        # а сетку и здесь держит инвариант строк (ISS-01 КК_ВК, 2026-08-27)
        _hdr_low = [_title_key(h) for h in headers]
        if not any("обяз" in h or _is_cardinality_title(h)
                   for h in _hdr_low):
            report.append("   таблица без якорных ролей (обязательность/"
                          "кратность) — колонные валидаторы не "
                          "применяются, сетка отдана как есть")
            chunks.append(f"## Таблица {i} (профиль: {prof.name}; сетка "
                          "без сборки путей)\n\n"
                          + render_markdown(headers, rows))
            continue
        for col in validate_columns(headers, rows, path_index=path_index,
                                    source_mode=True):
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
            # закрывающая скобка URL — тоже БАЛАНСОМ: пути и имена
            # файлов Confluence несут внутренние скобки («(исходящее)»,
            # «(2).xsd») — поиск первой «)» резал URL и оставлял хвосты
            # в тексте ячейки (К-11 экзамена inkasso, OQ-033: EXTINT-001)
            pdepth = 0
            k = j + 1
            url_end = -1
            while k < n:
                if v[k] == "(":
                    pdepth += 1
                elif v[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        url_end = k
                        break
                k += 1
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

# Строка макетов ЭФ в паспорте («Макеты ЭФ | <вложенная таблица Figma>»):
# шаблон screen-form запрещает Figma/Confluence-URL в чистовике, макеты
# живут в src — строка сверке не подлежит (иначе гейт заставлял включать
# сырой HTML с живыми URL в карточку; src-locks, 2026-08-14).
_LAYOUT_ROW_RE = re.compile(r"figma\.com|размерность экрана", re.IGNORECASE)


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
    if frag in corpus or frag.replace(" ", "") in corpus_ns:
        return True
    if _COVER_REF_HEAD_RE.match(frag):
        rest = [t for t in re.findall(r"[\wёа-я-]+", frag)
                if len(t) >= 3 and t not in _COVER_REF_STOP]
        if rest and all(t in corpus for t in rest):
            return True
    if _window_covered(frag, corpus):
        return True
    # фрагмент из запятых-частей: каждая часть — подстрокой, парой
    # «код - расшифровка» (разложено в таблицу справочника) или
    # латинским перечнем значений (разложено по строкам)
    for part in (p.strip(" .,;:-") for p in frag.split(",")):
        if len(part) < _COVER_MIN or part in corpus \
                or part.replace(" ", "") in corpus_ns:
            continue
        m = _COVER_PAIR_RE.match(part)
        if m and _cover_norm(m.group(1)) in corpus \
                and _cover_norm(m.group(2)) in corpus:
            continue
        if _COVER_LATIN_RE.match(part) and all(
                t in corpus for t in part.split() if len(t) >= 2):
            continue
        if _window_covered(part, corpus):
            continue
        return False
    return True


def check_cell_coverage(source_text: str,
                        corpus_text: str) -> Tuple[List[str], bool]:
    """Каждый фрагмент непустых ячеек «Тип»/«Описание»/«Комментарии»
    строк данных источника должен быть покрыт текстом комплекта в
    нормальной форме. Секционные строки и повторы шапки — не данные."""
    corpus = _cover_norm(corpus_text)
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
    segs = _example_value_segments(source_text.split("---", 2)[-1])
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
    body = source_text.split("---", 2)[-1]
    headings = _source_headings(body)
    flk_cells = _flk_example_cells(body)
    seen, out = set(), []
    for m in _QUOTED_RE.finditer(body):
        v = m.group(1).strip()
        if (not v or _QUOTED_SKIP_RE.search(v)
                or _QUOTED_MARKUP_RE.search(v)):
            continue
        # значение HTML-атрибута ВНУТРИ открытого тега (class="critic-del",
        # data-task="GBO-104711") — разметка, не текст источника: контекст
        # «<тег … attr=» перед кавычкой без закрывающей «>» (финальный
        # прогон locks 2026-08-15: CriticMarkup-атрибуты ложно требовались
        # в карточке; содержимое-присваивание `= "O2PLUS"` вне тега — текст)
        pre = body[:m.start()]
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
        if re.search(r"(?:раздел[еа]?|см\.)\s*$", body[:m.start()][-24:],
                     re.IGNORECASE):
            continue
        # захват должен быть словом, а не межкавычечным обрезком («, то …»)
        if not re.match(r"^[\wА-Яа-яЁё]", v) or not re.search(
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
                          source_text: str) -> Tuple[List[str], bool]:
    """Каждый кавычечный литерал источника обязан присутствовать в карточке
    (сравнение нормализованное, кавычки не требуются)."""
    lits = quoted_literals(source_text)
    if not lits:
        return [], True
    norm_card = _norm_cell(card_text)
    lost = [v for v in lits if _norm_cell(v) not in norm_card]
    if lost:
        return [f"кавычечные литералы источника: в карточке отсутствуют "
                f"{len(lost)} из {len(lits)} ✗ НИЖЕ ПОРОГА (тексты сообщений, "
                "кнопок и значений переносятся дословно); примеры: "
                + "; ".join(repr(v[:50]) for v in lost[:4])], False
    return [f"кавычечные литералы источника: все {len(lits)} на месте ✓"], True


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


# К-25 (2026-08-18): конвертация HTML-фрагмента (структурная ячейка
# паспорта) в markdown — ЧИСТАЯ ГРАММАТИКА, работа прибора, не LLM
# (архитектура нормализатора: «понимание — LLM, массовое переписывание —
# скрипт»). Кривые ручные конвертеры исполнителей теряли чередование
# абзацев и принадлежность уровней (fun-bnk-08, три итерации дозаходов).
def html_fragment_to_markdown(html: str) -> str:
    """Детерминированная конвертация содержимого ячейки/фрагмента:
    <p> — абзацы, <ul>/<ol>/<li> — списки с уровнями (пустые li-обёртки
    Confluence углубляют уровень без печати), <strong> — **жирный**."""
    soup = BeautifulSoup(protect_token_tags(html), "html.parser")
    lines: List[str] = []

    def text_of(el) -> str:
        # инлайн-узлы клеятся БЕЗ принудительных пробелов: пробельность
        # несёт сам текст источника (иначе «700_<strong>13_9</strong>_1»
        # разваливался в «700_ **13_9** _1» — имена файлов дословны)
        parts: List[str] = []
        for c in el.children:
            name = getattr(c, "name", None)
            if name in ("ul", "ol"):
                continue
            if name == "strong":
                t = c.get_text(" ", strip=True)
                if t:
                    parts.append(f"**{t}**")
            elif name == "br":
                parts.append(" ")
            elif hasattr(c, "get_text"):
                t = c.get_text(" ")
                if t:
                    parts.append(t)
            else:
                t = str(c)
                if t:
                    parts.append(t)
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    def blank() -> None:
        if lines and lines[-1] != "":
            lines.append("")

    def walk_list(lst, depth: int) -> None:
        for li in lst.find_all("li", recursive=False):
            t = text_of(li)
            if t:
                lines.append("  " * depth + "- " + t)
                child_depth = depth + 1
            else:
                child_depth = depth + 1  # пустая обёртка: уровень растёт
            for sub in li.find_all(["ul", "ol"], recursive=False):
                walk_list(sub, child_depth)

    def p_level(el) -> int:
        # Confluence выражает вложенность АБЗАЦЕВ инлайн-стилем
        # margin-left (40px = уровень); markdown-представление —
        # blockquote «>» на уровень (отступ пробелами дал бы code-блок).
        # Находка пользователя: «Выполнение функции возможно» (пилот 5.5)
        m = re.search(r"margin-left:\s*([\d.]+)px",
                      el.get("style", "") or "")
        return round(float(m.group(1)) / 40) if m else 0

    for el in soup.children:
        name = getattr(el, "name", None)
        if name == "p":
            t = text_of(el)
            if t:
                blank()
                lines.append("> " * p_level(el) + t)
                blank()
        elif name in ("ul", "ol"):
            walk_list(el, 0)
        elif name in ("td", "div", "span", "body"):
            # обёртка: рекурсивно тем же правилом
            inner = html_fragment_to_markdown(el.decode_contents())
            if inner:
                blank()
                lines.append(inner)
                blank()
        elif hasattr(el, "get_text"):
            t = el.get_text(" ", strip=True)
            if t:
                blank()
                lines.append(t)
                blank()
        else:
            t = str(el).strip()
            if t:
                blank()
                lines.append(t)
                blank()
    return "\n".join(lines).strip("\n")


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


def passport_cell_html(src_text: str,
                       label: str = "Что делает функция") -> Optional[str]:
    """HTML-содержимое ячейки паспорта по лейблу. К-25c: макеты команд
    различаются — лейбл живёт в <th> ИЛИ <td><strong>…:</strong>
    (системные функции inkasso: td + двоеточие; банковские: th без) —
    единый детект для К-24b/К-25/CLI."""
    m = re.search(re.escape(label)
                  + r"\s*:?\s*(?:</strong>)?\s*</t[hd]>\s*"
                  r"<td[^>]*>(.*?)</td>", src_text, re.S)
    return m.group(1) if m else None


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
            r"<tr[^>]*>\s*<t[hd][^>]*>(?:(?!</?t[dr]).)*?</t[hd]>\s*"
            r"<td[^>]*>((?:(?!</td>).)*)</td>\s*</tr>",
            src_text, re.S):
        cell = m.group(1)
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
        if not matched:
            bad += 1
            sample = probes[0]
    if bad:
        return ([f"содержимое/структура тяжёлых пар расходится с эталоном "
                 f"конвертера ×{bad} (пример: …{sample[:45]!r}…) — "
                 "содержимое ячейки раскладывается в соответствующий "
                 "раздел шаблона с абзацами и уровнями КАК В ЭТАЛОНЕ "
                 "(--cell-to-md «<лейбл>») ✗ НИЖЕ ПОРОГА"], False)
    return [], True


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
    (ширины отступов нормализуются в ранги: 0/4/8 и 0/2/4 сравнимы)."""
    raw: List[Tuple[str, int]] = []
    widths = set()
    for ln in lines:
        s = ln.strip()
        if not s:
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


def check_step_body_structure(card_text: str,
                              source_text: str) -> Tuple[List[str], bool]:
    """К-26: ранговый профиль тела КАЖДОГО шага карточки обязан
    совпадать с телом того же шага источника (md-источники; HTML-тела
    без md-разметки дают пустые профили — честный skip). Замены текстов
    ссылок профиль не меняют."""
    src_bodies = _step_bodies(
        source_text.split("---", 2)[-1].splitlines())
    if len(src_bodies) < 2:
        return [], True
    card_bodies = _step_bodies(card_text.splitlines())
    bad: List[str] = []
    for num, body in src_bodies.items():
        prof_src = _ranked_profile(body)
        if num not in card_bodies or not prof_src:
            continue  # полноту шагов держит К-23
        prof_card = _ranked_profile(card_bodies[num])
        if prof_src != prof_card:
            bad.append(num)
    if bad:
        return [f"структура тел шагов расходится с источником "
                f"(уровни/принадлежность): шаги №{', №'.join(bad[:5])}"
                + ("…" if len(bad) > 5 else "")
                + " — тело шага переносится КАК ЕСТЬ с ранговыми "
                "уровнями отступов ✗ НИЖЕ ПОРОГА"], False
    return [], True


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
    src_w = _list_indent_widths(source_text.split("---", 2)[-1].splitlines())
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


# Нотификации (тип notification): внутренняя согласованность карточки.
# Составной ключ «канал, получатели»: подраздел канала у события
# (#### <ключ>) обязан иметь карточку канала (### <ключ>) в разделе
# «Каналы и адреса доставки» — инцидент [КК_ВК]: канал «Уведомление в
# Экосистеме» использовался событиями, но в разделе каналов страницы
# отсутствовал. Плюс: упомянутый общий шаблон M-NN обязан существовать,
# E-номера событий монотонны (append-only, как OQ).
_NTF_EVENT_H_RE = re.compile(r"^###\s+NTF-\d+\.E(\d+)\.", re.M)
_NTF_TMPL_REF_RE = re.compile(r"общ\w+\s+шаблон\w*\s+(M-\d+)", re.I)
_NTF_TMPL_H_RE = re.compile(r"^###\s+(M-\d+)\.", re.M)
# заголовок-ключ — с фиксированным префиксом (решение пользователя
# 2026-08-15: префикс — «привязка к местности», показывает, что карточка
# разворачивает строку реестра; в ячейках реестров ключи без префикса)
_NTF_KEY_PREFIX_RE = re.compile(r"^Канал и получатели:\s*")


def _ntf_key(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def check_notification_structure(card_text: str) -> Tuple[List[str], bool]:
    """Согласованность карточки нотификаций; на прочих типах молчит
    (срабатывает только при обоих обязательных разделах шаблона)."""
    sections: Dict[str, List[str]] = {}
    current = ""
    for ln in card_text.splitlines():
        if ln.startswith("## ") and not ln.startswith("###"):
            current = _ntf_key(ln[3:])
            sections.setdefault(current, [])
        elif current:
            sections[current].append(ln)
    chan_lines = sections.get("Каналы и адреса доставки")
    evt_lines = sections.get("Сообщения нотификации")
    if chan_lines is None or evt_lines is None:
        return [], True
    report: List[str] = []
    ok = True
    unprefixed: List[str] = []

    def _keys(lines: List[str], marker: str) -> List[str]:
        out = []
        for ln in lines:
            if not ln.startswith(marker):
                continue
            raw = _ntf_key(ln[len(marker):])
            m = _NTF_KEY_PREFIX_RE.match(raw)
            if m:
                out.append(_ntf_key(raw[m.end():]))
            else:
                unprefixed.append(raw)
        return out

    chan_keys = set(_keys(chan_lines, "### "))
    evt_keys = _keys(evt_lines, "#### ")
    if unprefixed:
        report.append("нотификации: заголовок-ключ без префикса "
                      "«Канал и получатели: »: "
                      + "; ".join(unprefixed[:5]) + " ✗")
        ok = False
    missing = sorted({k for k in evt_keys if k not in chan_keys})
    if missing:
        report.append("нотификации: ключ «канал, получатели» события без "
                      "карточки в «Каналы и адреса доставки»: "
                      + "; ".join(missing[:5])
                      + " ✗ — карточку не синтезировать, нужен открытый "
                        "вопрос по источнику")
        ok = False
    tmpl_defined = set(_NTF_TMPL_H_RE.findall(card_text))
    tmpl_missing = sorted({m for m in _NTF_TMPL_REF_RE.findall(card_text)
                           if m not in tmpl_defined})
    if tmpl_missing:
        report.append("нотификации: упомянутый общий шаблон отсутствует: "
                      + ", ".join(tmpl_missing[:5]) + " ✗")
        ok = False
    e_raw = _NTF_EVENT_H_RE.findall(card_text)
    e_nums = [int(m) for m in e_raw]
    bad = [(a, b) for a, b in zip(e_nums, e_nums[1:]) if b <= a]
    if bad:
        report.append("нотификации: E-номера событий не монотонны "
                      "(append-only): "
                      + ", ".join(f"E{b:02d} после E{a:02d}"
                                  for a, b in bad[:3]) + " ✗")
        ok = False
    narrow = sorted({m for m in e_raw if len(m) < 2})
    if narrow:
        report.append("нотификации: формат E-номера — минимум две цифры "
                      "(E01…): " + ", ".join(f"E{m}" for m in narrow[:5])
                      + " ✗")
        ok = False
    # ссылка-заглушка [текст](#): суррогатный href вместо правила трёх
    # случаев (карточка в комплекте → относительная ссылка; иначе голый
    # текст + долг); финальный прогон locks 2026-08-15
    stubs = card_text.count("](#)")
    if stubs:
        report.append(f"нотификации: ссылка-заглушка «](#)» ({stubs} шт.) "
                      "✗ — по правилу трёх случаев: относительная ссылка "
                      "на карточку комплекта или голый текст + долг")
        ok = False
    # <br>-простыня: текст сообщения перенесён одной строкой из ячейки
    # источника вместо построчного разворачивания (рендеримость; в
    # таблицах (строки на «|») <br> легален — реестр событий)
    flat = [ln for ln in evt_lines
            if "<br>" in ln and not ln.lstrip().startswith("|")]
    if flat:
        report.append(f"нотификации: <br> вне таблиц в «Сообщения "
                      f"нотификации» ({len(flat)} строк) ✗ — тексты "
                      "разворачиваются построчно (правило шаблона)")
        ok = False
    if ok:
        report.append(f"нотификации: ключи каналов ({len(chan_keys)}), "
                      f"шаблоны, порядок событий ({len(e_nums)}) "
                      "согласованы ✓")
    return report, ok


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
        if (len(hdr) == 2
                and re.fullmatch(r"\*\*[^*]+\*\*", hdr[0].strip())
                and all(re.fullmatch(r"\*\*[^*]+\*\*", r[0].strip())
                        for r in rows
                        if r and any(c.strip() for c in r))):
            skip_cols.add(0)
        missing: List[str] = []
        for row in rows:
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


_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|?\s*$")


def blank_table_breaks(lines: List[str]) -> List[int]:
    """Номера (1-based) пустых строк, разрывающих pipe-таблицу: markdown
    рендерит хвост плоским текстом, содержимое при этом цело и сверка
    значений молчит (К-16: ent-002 «Привязка к реализации»; матрица
    exam-run1 — разрыв внесён LLM-исполнителем захода 4 при дописывании
    блока строк реестра с ведущей пустой строкой). Легальна пустая
    строка МЕЖДУ соседними таблицами — следующий блок начинается своей
    шапкой (строка + разделитель |---|)."""
    out: List[int] = []
    for k in range(1, len(lines) - 1):
        if lines[k].strip():
            continue
        prev = lines[k - 1].strip()
        nxt = next((lines[j].strip() for j in range(k + 1, len(lines))
                    if lines[j].strip()), "")
        if not (prev.startswith("|") and nxt.startswith("|")):
            continue
        j = next(j for j in range(k + 1, len(lines)) if lines[j].strip())
        nxt2 = lines[j + 1].strip() if j + 1 < len(lines) else ""
        if _TABLE_SEP_RE.match(nxt2):
            continue  # новая таблица с собственной шапкой — легально
        out.append(k + 1)
    return out


_OQ_PAGE_WORD_RE = re.compile(r"page[_ ]?id|confluence", re.I)
_OQ_PAGE_NUM_RE = re.compile(r"(?<![-\w.])\d{9,10}(?![-\w.])")


def check_oq_page_refs(md_path: Path) -> Tuple[List[str], bool]:
    """К-17 (2026-08-17): page_id в ТЕКСТАХ open-questions — носители
    page_id только frontmatter карточек и матрица; страница источника в
    OQ именуется title дословно + файлом выгрузки. ПРЕДУПРЕЖДЕНИЕ, не
    брак: легаси-фон старых записей (locks 23, file-storage 18 строк)
    вычищается при будущих касаниях, жёсткий брак заставил бы
    переписывать историю реестров разом (ужесточение — после вычистки
    фона, по механике серой зоны волны D)."""
    if not md_path.is_file():
        return [], True
    warns: List[str] = []
    for i, ln in enumerate(
            md_path.read_text(encoding="utf-8",
                              errors="replace").splitlines(), 1):
        if _OQ_PAGE_WORD_RE.search(ln) or _OQ_PAGE_NUM_RE.search(ln):
            warns.append(
                f"предупреждение: строка {i}: page_id/отсылка к Confluence "
                "в тексте реестра — страница источника именуется title + "
                f"файлом выгрузки: {ln.strip()[:60]!r}")
    return warns[:20], True


def check_service_table_integrity(md_path: Path) -> Tuple[List[str], bool]:
    """Структурная целостность таблиц СЛУЖЕБНОГО реестра (матрица,
    open-questions): только К-16 (разрывы пустой строкой) — колонные
    роли и литералы к реестрам не применяются (К-4)."""
    lines = md_path.read_text(encoding="utf-8").splitlines()
    breaks = blank_table_breaks(lines)
    if not breaks:
        return [], True
    return [f"строка {k}: пустая строка разрывает таблицу реестра — "
            "хвост рендерится плоским текстом ✗ НИЖЕ ПОРОГА"
            for k in breaks], False


# --- Сторож чистовика (волна D, Э-6) ---------------------------------
# Карточка комплекта не должна нести: битые относительные ссылки, ссылки
# вне docs/ (в т.ч. на выгрузку sources/), изображения, critic-маркеры,
# ссылки-заглушки «](#)». Внешние http(s) вне белого списка — ПРЕДУПРЕЖДЕНИЕ
# (софт-сигнал; решение аналитика 2026-08-17: фон не промерен — жёсткий
# брак спровоцировал бы агента «чинить» легитимные ссылки; ужесточение —
# после описи кросс-стендового прогона D4).
_HTTP_WHITELIST = ("https://gitlab.gboteam.ru/ED/eco-techbook",)


def _md_link_targets(text: str) -> List[Tuple[int, str]]:
    """Адреса markdown-ссылок [текст](адрес) с позициями; скобки текста и
    адреса — балансом (те же инциденты, что у _strip_markdown_links)."""
    out: List[Tuple[int, str]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                out.append((i, text[j + 2:k].strip()))
                i = k + 1
                continue
        i = j + 1
    return out


def check_clean_document(md_path: Path,
                         docs_root: Optional[Path] = None
                         ) -> Tuple[List[str], bool]:
    """Сторож чистовика: (а) битые относительные ссылки, (б) цели вне
    docs/, (в) изображения, (г) critic-маркеры — брак; внешние http(s)
    вне белого списка — предупреждение (видимо и при ✓)."""
    from urllib.parse import unquote
    text = md_path.read_text(encoding="utf-8")
    report: List[str] = []
    ok = True
    # (г) critic-маркеры в чистовике — разметка правок источника
    for pat in ("{++", "{--", "{~~", 'class="critic-'):
        cnt = text.count(pat)
        if cnt:
            ok = False
            report.append(
                f"critic-маркер «{pat}» ×{cnt} в чистовике: разметка правок "
                "в карточку не переносится — переносится ЦЕЛЕВОЙ текст "
                "(правило create-artifact) ✗ НИЖЕ ПОРОГА")
    # (в) изображения: бинарники в комплект не переносятся
    cnt = len(re.findall(r"<img\b", text)) + len(re.findall(r"!\[", text))
    if cnt:
        ok = False
        report.append(
            f"изображение (<img>/![…]) ×{cnt} в чистовике: изображения в "
            "комплект не переносятся (факт макетов — строкой паспорта) "
            "✗ НИЖЕ ПОРОГА")
    # (а)/(б) ссылки
    warns: List[str] = []
    root = docs_root.resolve() if docs_root is not None else None
    for pos, target in _md_link_targets(text):
        if not target or target == "#":
            ok = False
            report.append(
                f"ссылка-заглушка «](#)» (позиция {pos}): цель обязана "
                "существовать или ссылка снимается ✗ НИЖЕ ПОРОГА")
            continue
        if target.startswith("#"):
            continue  # внутрифайловый якорь: файловая часть отсутствует
        if target.startswith(("http://", "https://")):
            if not target.startswith(_HTTP_WHITELIST):
                warns.append(
                    f"предупреждение: внешняя ссылка вне белого списка — "
                    f"{target[:80]} (опись серой зоны; решение об "
                    "ужесточении — после кросс-стендового прогона)")
            continue
        if target.startswith("mailto:"):
            continue
        fpath = unquote(target.split("#", 1)[0])
        if not fpath:
            continue
        try:
            resolved = (md_path.parent / fpath).resolve()
        except OSError:
            resolved = None
        if resolved is None or not resolved.exists():
            ok = False
            report.append(
                f"битая относительная ссылка: {target[:80]} — цель не "
                "существует ✗ НИЖЕ ПОРОГА")
            continue
        if root is not None:
            try:
                resolved.relative_to(root)
            except ValueError:
                ok = False
                report.append(
                    f"ссылка ведёт ВНЕ docs/: {target[:80]} — карточки "
                    "ссылаются только внутрь комплекта (выгрузка/sources — "
                    "источник, не цель) ✗ НИЖЕ ПОРОГА")
    return report + warns, ok


# --- сторож формулы ТУЗ (решение аналитика 2026-08-19) ---
#
# Правило и образец — шаблон function §2 «Доступность»; здесь третий
# элемент триады (правило+образец+сторож): без него правка шаблона не
# персистентна для дозаходов (прецедент rbac → К-27).

_TUZ_BOLD_RE = re.compile(r"\*\*[^*\n]*вызов с ТУЗ[^*\n]*\*\*", re.I)


def check_tuz_formula(card_text: str) -> Tuple[List[str], bool]:
    hits = _TUZ_BOLD_RE.findall(card_text)
    if not hits:
        return [], True
    return [f"формула ТУЗ обёрнута в жирный ×{len(hits)}: фиксированная "
            "формула доступности FUN-SYS пишется ОБЫЧНЫМ шрифтом "
            "(шаблон function §2, решение 2026-08-19) ✗ НИЖЕ ПОРОГА"], False


# --- сторож упоминаний целей (кандидат волны E, вытянут 2026-08-19) ---
#
# Инвариант контура: титул Confluence-страницы несёт квадратно-скобочный
# тег сервиса («[РРКО_ИПИ] …», «[ПЭД] …») — маркер упоминания цели сам
# ТЕГ, а не перечень известных имён (имена заранее не перечислимы).
# Требование: упоминание в теле карточки — ЛИБО markdown-ссылка на
# существующую карточку комплекта, ЛИБО долг в матрице трассировки.
# Слепые зоны (честно): упоминания без тега; коллективные долги матрицы
# со свободной формулировкой могут не совпасть с иглой — потому уровень
# ПРЕДУПРЕЖДЕНИЕ (⚠, вердикт не трогает): по асимметрии ошибок шум
# лучше молчаливой потери; ужесточение — после боевой статистики.

_MENTION_TAG_RE = re.compile(
    r"\[(?=[^\]\n]*[А-ЯЁA-Z])[А-ЯЁA-Z0-9_]{2,20}\]\s+(?=[«\"(А-ЯЁA-Z])")
# границы хвоста упоминания: конец строки/ячейки, жирный, кавычки,
# точка с пробелом, запятая, точка с запятой (внутренние скобки —
# часть титулов: «…(стейт-машина)» — НЕ граница)
_MENTION_END_RE = re.compile(r"\n|\||\*\*|[»\"”;,]|\.\s")

_TARGET_INDEX_CACHE: Dict[str, List[Tuple[str, str]]] = {}


def _blank_md_links(text: str) -> str:
    """Заменить спаны [текст](адрес) ЦЕЛИКОМ пробелами: ссылочное
    упоминание уже оформлено и сторожу не видно (в отличие от
    _strip_markdown_links, сохраняющего текст-название). Скобки —
    балансом (инциденты intc-014 / К-11)."""
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            out.append(text[i])
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                out.append(" " * (k + 1 - i))
                i = k + 1
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def _docs_card_titles(docs_root: Path) -> List[Tuple[str, str]]:
    """[(title, отн. путь)] карточек комплекта с ТЕГОВЫМ титулом из
    frontmatter (без тега прозовые коллизии неизбежны — слепая зона).
    Кэш на процесс: селфчек зовёт по каждой карточке."""
    key = str(docs_root.resolve())
    if key in _TARGET_INDEX_CACHE:
        return _TARGET_INDEX_CACHE[key]
    out: List[Tuple[str, str]] = []
    for p in sorted(docs_root.rglob("*.md")):
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if not head.lstrip("﻿").startswith("---"):
            continue
        m = re.search(r"^title:\s*(.+)$", head, re.M)
        if not m:
            continue
        title = m.group(1).strip().strip("'\"").strip()
        if re.match(r"^\[[^\]]+\]\s+\S", title):
            out.append((title, str(p.relative_to(docs_root)).replace(
                "\\", "/")))
    _TARGET_INDEX_CACHE[key] = out
    return out


def check_target_mentions(card_text: str, md_path: Path,
                          docs_root: Path) -> Tuple[List[str], bool]:
    """Софт-сторож: теговые упоминания целей вне markdown-ссылок.
    Существующая карточка → «оформить ссылкой»; неизвестная цель без
    следа в матрице → «ссылка или долг». Вердикт не меняет (⚠)."""
    body = card_text
    if body.lstrip("﻿").startswith("---"):
        m = re.search(r"\n---\s*\n", body)
        if m:
            body = body[m.end():]
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = _blank_md_links(body)
    warns: List[str] = []
    # (а) дословные титулы существующих карточек вне ссылок
    try:
        self_rel = str(md_path.resolve().relative_to(
            docs_root.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        self_rel = ""
    # регистр и переносы строк СОХРАНЯЮТСЯ: теговый регекс различает
    # регистр, а \n — граница упоминания (схлопывание пробелов до скана
    # протаскивало хвост упоминания через заголовки соседних разделов);
    # титулы поперёк переносов ловятся паттерном с \s+ между словами
    flat = body
    titles = sorted(_docs_card_titles(docs_root),
                    key=lambda t: -len(t[0]))  # длинный титул раньше:
    # вложенный короткий не двоит счёт (вычёркивание по месту)
    for title, rel in titles:
        if rel == self_rel:
            continue
        pat = re.compile(
            r"\s+".join(re.escape(w) for w in title.split()), re.I)
        cnt = 0
        m = pat.search(flat)
        while m:
            cnt += 1
            flat = (flat[:m.start()] + " " * (m.end() - m.start())
                    + flat[m.end():])
            m = pat.search(flat)
        if cnt:
            warns.append(
                f"предупреждение: имя существующей карточки без ссылки — "
                f"«{title[:70]}» ×{cnt} → {rel} (упоминание оформляется "
                "markdown-ссылкой на карточку; ссылка НЕ конфликтует со "
                "сторожем теговых упоминаний — дефейс только у слов без "
                "тега ВНЕ ссылки)")
    # (б) остальные теговые упоминания: след в матрице обязателен
    matrix = docs_root / "traceability-matrix.md"
    try:
        mtext = _norm_ws(matrix.read_text(encoding="utf-8",
                                          errors="replace"))
    except OSError:
        mtext = ""
    seen: Dict[str, Tuple[str, int]] = {}
    for m in _MENTION_TAG_RE.finditer(flat):
        tail = flat[m.end():m.end() + 120]
        e = _MENTION_END_RE.search(tail)
        core = (tail[:e.start()] if e else tail).strip().rstrip(".,;:")
        if not core:
            continue
        # игла — БЕЗ тега, первые ≤3 слова: реестр ID и долги матрицы
        # пишут имена без тегов; свободные формулировки длиннее иглы
        words = core.split()
        needle = " ".join(words[:3]).casefold()
        mention = re.sub(r"\s+", " ",
                         flat[m.start():m.end()] + core)[:70]
        if needle in mtext:
            continue
        key, (mm, cnt) = needle, seen.get(needle, (mention, 0))
        seen[key] = (mm, cnt + 1)
    for needle, (mention, cnt) in sorted(seen.items()):
        warns.append(
            f"предупреждение: упоминание цели «{mention}» ×{cnt} — "
            "карточки в комплекте нет и следа в матрице не найдено: "
            "либо markdown-ссылка на карточку, либо долг в матрице "
            "(правило долгов канона)")
    return warns, True


# --- К-33 (2026-08-19): вложенные/обёрнутые markdown-ссылки ---
#
# След генераторных правок дозахода 5.5: скрипт массовой простановки
# ссылок оборачивал уже олинкованные упоминания второй раз
# («[[[[…] …](fun-cl-08…)]](fun-cl-08…)» в fun-sys-02 прошло ВСЕ
# сторожа — цели валидны, К-32 доволен) и вкладывал ссылку внутрь
# title. Инвариант: внутри текста-названия ссылки не бывает другой
# ссылки; ссылка не оборачивается в дополнительные квадратные скобки.
# Легитимно: скобочный ТЕГ в дисплее («[[РРКО_ИПИ] Имя](file.md)») —
# внешняя скобка там принадлежит самой ссылке, сосед-скобок нет.


def _link_spans(text: str) -> List[Tuple[int, int, str]]:
    """(начало, конец, текст-название) каждой ссылки [текст](адрес);
    скобки балансом; шаг на 1 символ при не-ссылке — иначе внутренняя
    ссылка в «[[x](y)]» пропускается."""
    out: List[Tuple[int, int, str]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                out.append((i, k, text[i + 1:j]))
                i = k + 1
                continue
        i += 1
    return out


def check_nested_links(card_text: str) -> Tuple[List[str], bool]:
    bad: List[str] = []
    for start, end, disp in _link_spans(card_text):
        nested = bool(_link_spans(disp))
        wrapped = ((start > 0 and card_text[start - 1] == "[")
                   or (end + 1 < len(card_text)
                       and card_text[end + 1] == "]"))
        if nested or wrapped:
            frag = re.sub(r"\s+", " ", card_text[
                max(0, start - 1):end + 2])[:60]
            bad.append(frag)
    if not bad:
        return [], True
    return [f"К-33 вложенная/обёрнутая markdown-ссылка ×{len(bad)} "
            f"(фрагмент: …{bad[0]!r}…) — след генераторной правки: "
            "ссылка не вкладывается в текст другой ссылки и не "
            "оборачивается в скобки; оставить ОДНУ ссылку с дословным "
            "текстом ✗ НИЖЕ ПОРОГА"], False


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


# --- К-32 (2026-08-19): анти-дефейс теговых упоминаний источника ---
#
# Пилот-2: агент «погасил» предупреждения сторожа упоминаний удалением
# тегов из дословного текста («см в [РРКО_ИПИ] Методы» → «см в Методы»)
# — упоминание ушло из зоны видимости, дословность и трассировка
# потеряны, долгов ноль. Закон обходов: инвариант — теговое упоминание
# ИСТОЧНИКА (целевой вид) сохраняется в карточке: тег на месте ЛИБО
# упоминание внутри markdown-ссылки (в ссылке тег легитимно заменяется
# на ID карточки: «[ENT-001 Инкассовое…](…)»). Слова без тега вне
# ссылки = дефейс, брак (доказуем текстом карточки). Полное отсутствие
# упоминания — предупреждение (зона могла легитимно не переноситься).


def _md_link_texts(text: str) -> str:
    """Конкатенация текстов-названий всех markdown-ссылок (балансом,
    как _strip_markdown_links)."""
    parts: List[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                parts.append(text[i + 1:j])
                i = k + 1
                continue
        i = j + 1
    return "\n".join(parts)


def check_source_tag_mentions(card_text: str, src_text: str,
                              docs_root: Optional[Path] = None
                              ) -> Tuple[List[str], bool]:
    """К-32: каждое теговое упоминание источника — в карточке с тегом
    или ссылкой; слова без тега вне ссылки = дефейс (✗), отсутствие —
    предупреждение (⚠, вердикт не трогает).

    Исключение (реестровая конвенция, прецедент README функций и
    матрицы): имя СУЩЕСТВУЮЩЕЙ карточки без тега легитимно, когда файл
    ссылается на файл этой карточки (реестры пишут имена без тегов со
    ссылкой рядом; ссылка с ID-переименованием «[FUN-CL-05 …]» дисплеем
    иглу не несёт). Цели БЕЗ карточки исключения не имеют."""
    plain = re.sub(r"<[^>]+>", " ", src_text)
    mentions: Dict[str, str] = {}  # игла (норм.) -> «[ТЕГ] ядро» для отчёта
    for m in _MENTION_TAG_RE.finditer(plain):
        tail = plain[m.end():m.end() + 120]
        e = _MENTION_END_RE.search(tail)
        core = (tail[:e.start()] if e else tail).strip().rstrip(".,;:")
        if not core:
            continue
        needle = _norm_ws(" ".join(core.split()[:3]))
        tag = plain[m.start():m.end()].strip()
        mentions.setdefault(needle, re.sub(r"\s+", " ", f"{tag} {core}")[:70])
    if not mentions:
        return [], True
    card_nolinks = _norm_ws(_blank_md_links(card_text))
    card_links = _norm_ws(_md_link_texts(card_text))
    # реестровое исключение: базовые имена файлов, на которые ссылается
    # карточка, и титулы существующих карточек без тега
    linked_names = {t.split("#", 1)[0].replace("\\", "/").rsplit("/", 1)[-1]
                    for _, t in _md_link_targets(card_text)}
    titled_cards = ([(t, r) for t, r in _docs_card_titles(docs_root)]
                    if docs_root is not None else [])
    report: List[str] = []
    ok = True
    for needle, shown in sorted(mentions.items()):
        if any(_norm_ws(t.split("]", 1)[-1]).startswith(needle)
               and r.rsplit("/", 1)[-1] in linked_names
               for t, r in titled_cards):
            continue  # имя существующей карточки, файл на неё ссылается
        # тег на месте: «[тег] игла» встречается вне ссылок или в ссылке
        tagged = _norm_ws(shown.split("]")[0] + "] " + needle)
        if tagged in card_nolinks or tagged in card_links:
            continue
        if needle in card_links:
            continue  # оформлено ссылкой (тег в ссылке легитимно → ID)
        if needle in card_nolinks:
            ok = False
            report.append(
                f"К-32 дефейс тегового упоминания источника: «{shown}» — "
                "в карточке те же слова БЕЗ тега вне ссылки: тег — часть "
                "дословного текста и трассировка; возврат тега + ссылка "
                "на карточку или долг в матрице ✗ НИЖЕ ПОРОГА")
        else:
            report.append(
                f"предупреждение: теговое упоминание источника «{shown}» "
                "в карточке не найдено — если зона переносилась, "
                "упоминание обязано сохраниться (тег/ссылка)")
    return report, ok


def check_file(md_path: Path, min_valid_pct: float = 95.0,
               source_text: Optional[str] = None,
               column_roles: bool = True,
               soft_markers: bool = False) -> Tuple[List[str], bool]:
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
    # Fenced-блоки — вне зоны действия (notation §«вне зоны»): PlantUML
    # activity внутри ``` несёт свимлейны «|Система|» и шаги «:6 …;» —
    # для сторожа они выглядели таблицей с зажатым текстом (4 ложняка
    # process-файлов эталона, разбор ✗ 2026-08-21).
    lines = text.splitlines()
    _in_fence = False
    _fenced = set()
    for k, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            _in_fence = not _in_fence
            _fenced.add(k)
        elif _in_fence:
            _fenced.add(k)
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
    # Порядок колонок справочников НЕ проверяется: решение пользователя
    # 2026-08-09 — переносится как в источнике (дословность; целевое
    # переформатирование — работа поздних слоёв, не миграции).
    # Р-8 (2026-08-22): в командном профиле (selfcheck по умолчанию)
    # маркеры — предупреждение: на эталоне детектор дал 3/3 ложняков
    # («и т. д.» в описании колонки README, «фрагмент текста ПФ»,
    # scope-примечание). В полном профиле (--strict, наши прогоны) — ✗.
    for marker in ("фрагмент", "см. источник", "и т.д.", "и т. д."):
        cnt = text.lower().count(marker)
        if cnt:
            if soft_markers:
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
    if mixed:
        ok = False
        report.append(
            f"гомоглифы/смешанное письмо в словах ×{len(mixed)} "
            f"({', '.join(repr(w) for w in mixed[:5])}) — латиница внутри "
            "кириллического слова (или наоборот) невидима читателю и "
            "выключает распознавание — класс невидимых подмен К-30 "
            "✗ НИЖЕ ПОРОГА")
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
    # К-33 (2026-08-19): вложенные/обёрнутые ссылки — след генераторных
    # правок (двойная обёртка проходила все сторожа: цели валидны)
    nl_report, nl_ok = check_nested_links(text)
    report.extend(nl_report)
    ok = ok and nl_ok
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
    # К-21 (2026-08-18): отсылка к OQ в ТЕЛЕ карточки — брак (правило
    # create-artifact «отсылок к OQ в документах не делай» было без
    # сторожа: дозаход 3.1 inkasso-run1 создал rbac-заглушку со
    # «см. OQ-014»; в экзамене такие снимали руками).
    oq_refs = re.findall(r"\bOQ-\d+\b", text)
    if oq_refs:
        ok = False
        report.append(
            f"отсылка к открытым вопросам в теле карточки ×{len(oq_refs)} "
            f"({', '.join(sorted(set(oq_refs))[:3])}) — судьба вопроса живёт "
            "в open-questions.md, документ на него не ссылается "
            "✗ НИЖЕ ПОРОГА")
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
    # Отсылки к страницам источника в ТЕЛЕ карточки — запрещены (чистовик
    # без ссылок на Confluence/выгрузку; законный носитель page_id —
    # только frontmatter confluence_page_ids и матрица трассировки).
    # К-7 экзамена inkasso: «Статика и источники — по таблице полей
    # источника page 2169849859» ×40 — отсылка ВМЕСТО переноса
    # содержимого, словарь маркеров сокращения её не покрывал.
    body_wo_fm = text.split("---", 2)[-1] if text.lstrip("﻿")\
        .startswith("---") else text
    page_refs = re.findall(r"(?i)confluence|page[ _]?id|page\s+\d{6,}",
                           body_wo_fm)
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


def apply_critic(text: str) -> str:
    """ЦЕЛЕВОЙ текст источника: CriticMarkup-правки применяются —
    добавления остаются содержимым (без маркеров и префикса задачи
    «GBO-NNNNN: »), удаления выпадают, замены — новым текстом; обе
    формы разметки (текстовая и HTML-span). К-5 экзамена inkasso:
    гейт, требующий сырую разметку, провоцировал перенос маркеров в
    чистовик (fun-sys-08 — «markup сохранён для прохождения гейта»)."""
    # префикс задачи: «GBO-NNNNN:» и экспортёрский «UNKNOWN-<hex-цвет>:»
    # (правка без номера задачи; К-15 дозахода-3: префикс не снимался и
    # агент вписал его текстом в карточку ent-002 ради гейта значений)
    text = re.sub(r"\{\+\+\s*(?:(?:[A-ZА-Я]+-\d+(?:/\d+)*"
                  r"|UNKNOWN-[0-9a-fA-F]{6}):?\s*)?(.*?)\+\+\}",
                  r"\1", text, flags=re.S)
    text = re.sub(r"\{--.*?--\}", "", text, flags=re.S)
    text = re.sub(r"\{~~.*?~>(.*?)~~\}", r"\1", text, flags=re.S)
    text = re.sub(r"<span[^>]*critic-del[^>]*>.*?</span>", "", text,
                  flags=re.S | re.I)
    text = re.sub(r"<span[^>]*critic-ins[^>]*>(.*?)</span>", r"\1", text,
                  flags=re.S | re.I)
    return text


_HISTORY_TABLE_RE = re.compile(
    r"<table\b(?:(?!</table>).)*?<th[^>]*>\s*(?:Дата|Автор)\b"
    r"(?:(?!</table>).)*?</table>", re.S | re.I)


def strip_history(text: str) -> str:
    """Вырезает HTML-таблицы истории изменений страницы (шапка с
    «Дата»/«Автор») до всех сверок: история по канону не переносится,
    а её кавычечные литералы («исключен реквизит "X"») ложно
    требовались в карточках (К-9 экзамена inkasso, страница контролей).
    Md-таблицы истории режет фильтр check_source_tables."""
    return _HISTORY_TABLE_RE.sub("", text)


def run_check(files: List[Path], source_path: Optional[Path],
              min_valid_pct: float = 95.0,
              docs_root: Optional[Path] = None,
              soft_markers: bool = False) -> Tuple[List[str], bool]:
    """Полная связка режима --check одной функцией — ЕДИНАЯ точка
    подключения проверок для CLI и selfcheck-диспетчера (двойной
    монтаж проверок расходится). Первая карточка — основная (title,
    поведение, колонки); значения источника ищутся в объединении.
    Источник сверяется в ЦЕЛЕВОМ виде (strip_history + apply_critic)."""
    main_file = files[0]
    src_text = (apply_critic(strip_history(
        source_path.read_text(encoding="utf-8")))
                if source_path is not None else None)
    report, ok = check_file(main_file, min_valid_pct=min_valid_pct,
                            source_text=src_text,
                            column_roles=main_file.name.lower() != "readme.md",
                            soft_markers=soft_markers)
    card_text = main_file.read_text(encoding="utf-8")
    # межтиповая страница-источник: значения ищутся в ОБЪЕДИНЕНИИ
    # карточек (пример: каталог статусов в dictionaries + переходы в
    # status-model); title/поведение/колонки — по первой (основной).
    # HTML-комменты вырезаются ДО поиска значений (К-13): содержимое
    # коммента невидимо читателю — «найденное» там значение не перенесено.
    combined = re.sub(
        r"<!--.*?-->", " ",
        "\n\n".join(f.read_text(encoding="utf-8") for f in files),
        flags=re.S)
    # сторож чистовика (волна D): по КАЖДОЙ карточке вызова, не только
    # главной (неглавные в selfcheck прогоняются отдельными вызовами,
    # здесь files>1 встречается в CLI)
    cl_report, cl_ok = check_clean_document(main_file, docs_root)
    report.extend(cl_report)
    ok = ok and cl_ok
    # формула ТУЗ обычным шрифтом (решение 2026-08-19, шаблон §2)
    tz_report, tz_ok = check_tuz_formula(card_text)
    report.extend(tz_report)
    ok = ok and tz_ok
    # полнота ячеек источника — reverse-карточки модели данных
    # (COM-01 Корпкарт 2026-08-27: хвосты ячеек Тип/Описание терялись
    # при выносе перечислений в справочник); корпус поиска — группа
    # карточек + весь каталог модели данных (фрагмент вправе уехать
    # в dictionaries/README по шаблону)
    if src_text is not None and re.search(
            r"^type:\s*data-model\s*$", card_text[:500], re.M):
        sib = "\n\n".join(
            f.read_text(encoding="utf-8")
            for f in sorted(main_file.parent.glob("*.md"))
            if f not in files)
        corpus_txt = combined + "\n\n" + re.sub(r"<!--.*?-->", " ", sib,
                                                flags=re.S)
        cov_rep, cov_ok = check_cell_coverage(src_text, corpus_txt)
        report.extend(cov_rep)
        ok = ok and cov_ok
    # теговые упоминания целей: ссылка или долг (софт, вердикт не трогает)
    if docs_root is not None:
        tm_report, _ = check_target_mentions(card_text, main_file,
                                             docs_root)
        report.extend(tm_report)
    num_report, num_ok = check_behavior_numbering(card_text)
    report.extend(num_report)
    ok = ok and num_ok
    ntf_report, ntf_ok = check_notification_structure(card_text)
    report.extend(ntf_report)
    ok = ok and ntf_ok
    if src_text is not None:
        # сторож маркеров шагов — только для типов с таблицей шагов /
        # поведением (process, agent, function, notification): на
        # страницах прочих типов составные номера — нумерация секций и
        # строк, не шаги (экзамен inkasso 2026-08-16: сущности МД с
        # секциями 1.1… дали ложные «отсутствуют 72 из 72»). Тип не
        # распознан — консервативно применяем.
        m_type = re.search(r"^type:\s*([\w-]+)", card_text[:2000], re.M)
        steps_apply = (m_type is None or m_type.group(1) in
                       {"process", "agent", "function", "notification"})
        src_report, src_ok = check_source_tables(combined, src_text)
        # title сверяется и у README-реестров: он дословный из главной
        # страницы-оглавления, раз она есть (решение 2026-08-16 v2:
        # title — трассировка к источнику, «собственный» — только у
        # файлов БЕЗ страницы-источника, а такие сюда не попадают;
        # расширенное наименование реестра живёт в H1)
        ttl_report, ttl_ok = check_title(card_text, src_text)
        bh_report, bh_ok = check_behavior_nesting(card_text, src_text)
        st_report, st_ok = (check_step_markers(combined, src_text)
                            if steps_apply else ([], True))
        # К-34: лейбл-секции паспорта — только функции (у data-model
        # паспорт-таблица — легитимный слот шаблона)
        if m_type is not None and m_type.group(1) == "function":
            ls_report, ls_ok = check_label_sections(combined, src_text)
            report.extend(ls_report)
            ok = ok and ls_ok
        # К-32: анти-дефейс теговых упоминаний источника (пилот-2:
        # теги удалялись, чтобы увести упоминания от сторожа)
        sm_report, sm_ok = check_source_tag_mentions(combined, src_text,
                                                     docs_root)
        report.extend(sm_report)
        ok = ok and sm_ok
        # К-29: инвариант тяжёлых ячеек — лейбло- и макето-независимый
        hc_report, hc_ok = check_heavy_cells(combined, src_text)
        report.extend(hc_report)
        ok = ok and hc_ok
        # К-25d: профили вынесенных лейбл-секций против эталона
        hp_report, hp_ok = check_heavy_pair_structure(combined, src_text)
        report.extend(hp_report)
        ok = ok and hp_ok
        # К-26: по-шаговая структура тел (типы с поведением)
        if steps_apply:
            sb_report, sb_ok = check_step_body_structure(combined, src_text)
            report.extend(sb_report)
            ok = ok and sb_ok
        # К-24: уплощение вложенности + потеря паспортного слоя «Что
        # делает функция» (типы с поведением — как у маркеров шагов)
        if steps_apply:
            nd_report, nd_ok = check_nesting_depth(combined, src_text)
            report.extend(nd_report)
            ok = ok and nd_ok
            # К-24-лейбл и лейбл-секции СНЯТЫ (2026-08-18, аудит
            # fun-sys-03 с аналитиком): шаблон function не имеет слота
            # «паспорт» — содержимое ячеек раскладывается по разделам
            # шаблона (Поведение/Вызов/Доступность); требование
            # дословного лейбла толкало исполнителей в двойную
            # структуру. Содержимое и структуру ячеек держат К-29
            # (не в |-строке) и check_heavy_pair_structure (профиль +
            # потеря), лейбло-независимо.
        # К-19: анти-присутствие значений примеров — ТОЛЬКО data-model
        # (в screen-form/function примеры форматов переносятся легитимно)
        ex_report, ex_ok = (check_example_values_absent(combined, src_text)
                            if m_type is not None
                            and m_type.group(1) == "data-model"
                            else ([], True))
        report.extend(ex_report)
        ok = ok and ex_ok
        ql_report, ql_ok = check_quoted_literals(combined, src_text)
        report.extend(src_report)
        report.extend(ttl_report)
        report.extend(bh_report)
        report.extend(st_report)
        report.extend(ql_report)
        ok = ok and src_ok and ttl_ok and bh_ok and st_ok and ql_ok
    return report, ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Нормализатор сырых HTML-таблиц в .md (проход 1). "
                    "Исходный файл не изменяется.")
    ap.add_argument("file", type=Path, nargs="+",
                    help="markdown-файл; в --check допускается НЕСКОЛЬКО "
                         "карточек (межтиповая страница-источник: значения "
                         "сверяются с ОБЪЕДИНЕНИЕМ, первая карточка — "
                         "основная: title, поведение, колонки)")
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
    ap.add_argument("--cell-to-md", metavar="ЛЕЙБЛ", default=None,
                    help="напечатать эталонную markdown-конвертацию "
                         "содержимого ячейки паспорта с данным лейблом "
                         "(например «Что делает функция») из файла-"
                         "источника — для лейбл-секций карточек (К-25)")
    ap.add_argument("--docs-root", type=Path, default=None,
                    help="для --check: корень docs/ комплекта — включает "
                         "проверку «ссылка ведёт вне docs/» сторожа "
                         "чистовика (selfcheck передаёт сам)")
    ap.add_argument("--sidecar", action="store_true",
                    help="записать результат в <файл>.tables.md рядом (иначе stdout)")
    ap.add_argument("--min-valid", type=float, default=95.0,
                    help="порог валидности колонки в %% (ниже — результат не отдаётся)")
    ap.add_argument("--force", action="store_true",
                    help="отдать результат даже ниже порога (для разбора брака)")
    args = ap.parse_args()

    profile = Profile.load(args.profile) if args.profile else None
    main_file: Path = args.file[0]
    if len(args.file) > 1 and not args.check:
        print("# несколько файлов поддерживаются только в --check; "
              f"использую {main_file}", file=sys.stderr)

    if args.cell_to_md:
        text = main_file.read_text(encoding="utf-8")
        cell = passport_cell_html(text, args.cell_to_md)
        if cell is None:
            print(f"# ячейка с лейблом {args.cell_to_md!r} не найдена",
                  file=sys.stderr)
            return 2
        print(html_fragment_to_markdown(cell))
        return 0

    if args.check:
        report, ok = run_check(list(args.file), args.source,
                               min_valid_pct=args.min_valid,
                               docs_root=args.docs_root)
        for line in report:
            print(f"# {line}", file=sys.stderr)
        if not ok:
            print("# БРАК: см. строки ✗ выше — исправьте карточку по "
                  "выходу утилиты.", file=sys.stderr)
            return 2
        print("# OK: все распознанные колонки выше порога.", file=sys.stderr)
        return 0

    if args.sample:
        text = main_file.read_text(encoding="utf-8")
        tables = find_top_tables(text)
        for i, t in enumerate(tables):
            if args.table is not None and i != args.table:
                continue
            grid = expand_grid(t)
            print(f"--- таблица {i} ({len(grid)} строк сетки) ---")
            print(render_sample(grid))
        return 0

    out, report, ok = normalize_file(main_file, profile, args.table,
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
        target = main_file.with_suffix(main_file.suffix + ".tables.md")
        target.write_text(out + "\n", encoding="utf-8")
        print(f"# записано: {target}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
