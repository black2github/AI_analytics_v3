# app/scripts/CI/kitcheck/html.py
"""Примитивы разбора HTML и markdown, общие для нормализатора таблиц и проверок карточки:
сетка (`cell_text`, `expand_grid`), таблицы верхнего уровня, markdown-таблицы, шапка
документа, нормализация ячейки; конвертер ячейки паспорта для `--cell-to-md`.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена."""
import html
import re
import sys
from typing import Dict, List, Optional, Tuple
from . import fs as _fs
from .md import frontmatter_split, split_cells, strip_row

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:  # окружение команды: единственная сторонняя зависимость прибора
    sys.stderr.write(
        "Не установлен пакет beautifulsoup4 (модуль bs4) — он нужен "
        "инструментам проверки (normalize_tables, selfcheck).\n"
        "Установка: python -m pip install beautifulsoup4\n"
        "Офлайн (закрытый контур): на машине с доступом "
        "python -m pip download beautifulsoup4 -d <каталог>, затем "
        "python -m pip install --no-index --find-links <каталог> beautifulsoup4\n"
        "Список зависимостей: _meta/tools/requirements.txt\n")
    raise SystemExit(2)


def _fm_body(text: str) -> str:
    """Текст без шапки — общая граница прибора (`frontmatter_split`): BOM
    снимается, «---» внутри значения и сепаратор таблицы — не граница;
    шапки нет — текст целиком (прежнее `split("---", 2)` на странице без
    шапки резало по сепаратору таблицы и молча выбрасывало начало)."""
    return frontmatter_split(text)[1]


def _fm_head(text: str) -> str:
    """Текст шапки ('' — шапки нет или она не закрыта)."""
    return frontmatter_split(text)[0] or ""


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
        if m.group(1) == "S" and not m.group(2).strip():
            # прописной <S> без атрибутов — авторский размерный маркер
            # экрана (ряд S/XS/M/L/XL; STS-03 z03 2026-08-31: парсер
            # считал его зачёркиванием и глотал хвост ячейки). Строчный
            # <s> остаётся HTML-зачёркиванием
            return m.group(0).replace("<", "&lt;").replace(">", "&gt;")
        if m.group(1).lower() in _KNOWN_HTML_TAGS:
            return m.group(0)
        return m.group(0).replace("<", "&lt;").replace(">", "&gt;")
    return _TAGLIKE_RE.sub(esc, md_text)


@_fs.memoize(copy=list)
def find_top_tables(md_text: str) -> List[Tag]:
    """Верхнеуровневые сырые HTML-таблицы файла (вложенные обрабатываются
    в составе родительской ячейки текстом; их структура — отдельной таблицей
    при необходимости, через --table по индексу)."""
    soup = BeautifulSoup(protect_token_tags(md_text), "html.parser")
    return [t for t in soup.find_all("table") if not t.find_parent("table")]


_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _title_key(title: str) -> str:
    """Заголовок → ключ для распознавания роли: <br> внутри слова («Крат<br>ность»)
    снимается, регистр и пробелы нормализуются. Без этого роль не находилась и
    роли колонок съезжали (найдено при доработке 2026-08-06)."""
    return re.sub(r"\s+", " ", _BR_RE.sub("", title)).strip().lower()


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
                          for c in split_cells(strip_row(s))])
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
            # экранированные \[ и \] — текст, не скобки баланса:
            # конструкция выгрузки «[КК_ВК\] Банк: …](url)» иначе
            # рвалась на \] и URL оставался хвостом в эталоне сверки
            # (блокер z01-fix ISS-03, диагноз исполнителя)
            if v[j] in "[]" and j > 0 and v[j - 1] == "\\":
                j += 1
                continue
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
                label = v[i + 1:j]
                if "\\]" in label and not label.startswith("\\["):
                    # кривой формат выгрузки «[КК_ВК\] Банк: …](url)»:
                    # ведущая «[» — текст тега, не разметка ссылки
                    label = "[" + label
                out.append(label)
                i = url_end + 1
                continue
        out.append(v[i])
        i += 1
    return "".join(out)


@_fs.memoize()
def _norm_cell(v: str) -> str:
    """Нормальная форма значения для сверки наличия: без markdown-разметки,
    бэктиков, <br> и лишних пробелов, в нижнем регистре.

    Markdown-ссылки сводятся к тексту-названию: URL — навигация, не литерал.
    Иначе замена живого URL Confluence относительной ссылкой на карточку
    (правило шаблона контрактов) валила сверку паспорта §1 — агент был
    зажат между правилом и гейтом (OQ-029 file-storage, 2026-08-13)."""
    v = _BR_RE.sub(" ", _plain(v)).replace("`", "").replace("\\|", "|")
    # маркеры маркированного списка в начале строк — носители структуры,
    # не содержимое (принцип К-35): без вычистки разложение ячейки
    # источника markdown-списком в карточке рвало нормализованную
    # подстроку («- » внутри склейки), и исполнитель был зажат между
    # сторожем сплющивания и сверкой дословности (B-1 scr-bnk-02, z05:
    # обходная конструкция «пустой ярлык + абзац»). Нумерованные маркеры
    # НЕ трогаются — номера шагов сверяются как литералы.
    v = re.sub(r"(?m)^\s*[-*+]\s+", " ", v)
    v = _strip_markdown_links(v)
    # markdown-экранирование HTML→MD-конвертера выгрузки (\[ДСФ_ЭКО\] и т.п.):
    # карточка пишет чистый текст — сравниваем без обратных косых
    v = re.sub(r"\\([^\w\s])", r"\1", v)
    return re.sub(r"\s+", " ", v).strip().lower()


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
