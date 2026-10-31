# app/scripts/CI/normalize_tables.py
# Слой: миграция (нормализатор сырых HTML-таблиц); `--check` — проверки карточки ядра (`kitcheck/checks/card_*`), работает без выгрузки
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
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
try:
    from kitcheck import fs as _fs  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck import fs as _fs  # type: ignore  # noqa: E402
try:
    from kitcheck import fence as _fence  # noqa: E402
    from kitcheck.md import (  # noqa: E402
        blank_code, code_line_flags, count_cells, frontmatter_split,
        split_cells, strip_row, table_cells)
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck import fence as _fence  # type: ignore  # noqa: E402
    from .kitcheck.md import (  # type: ignore  # noqa: E402
        blank_code, code_line_flags, count_cells, frontmatter_split,
        split_cells, strip_row, table_cells)

try:
    from kitcheck.html import (  # noqa: E402,F401 — Д-50: механизмы ядра, имена сохранены
        _BR_RE, _KNOWN_HTML_TAGS, _TAGLIKE_RE, _fm_body, _fm_head, _norm_cell, _plain,
        _strip_markdown_links, _title_key, cell_text, expand_grid, find_top_tables,
        html_fragment_to_markdown, parse_md_tables, passport_cell_html, protect_token_tags
    )
    from kitcheck.columns import (  # noqa: E402,F401 — Д-50: механизмы ядра, имена сохранены
        _CARDINALITY_RE, _COLUMN_RULES, _LOGICAL_CARD_RE, _LOGICAL_CARD_TOKEN, _PATH_RE,
        _SENTENCE_RE, _STRUCT_LABEL_BARE_RE, _STRUCT_LABEL_RE, _TITLE_SUSPECT_RES, _TYPE_TOKENS,
        _XML_PATHISH_RE, _bare_type_name, _is_cardinality_title, _is_section_row,
        _looks_like_cardinality, _looks_like_cardinality_logical, _looks_like_obligation,
        _looks_like_obligation_pair, _looks_like_path, _no_xml_path, _title_suspicious,
        validate_columns
    )
    from kitcheck.branch_form import (  # noqa: E402,F401 — Д-50: механизмы ядра, имена сохранены
        _BRANCH_IF_RE, _BRANCH_INDENT_RE, _BRANCH_MARKER_RE, _BRANCH_OUT_RE, _BRANCH_PLAIN_IF_RE,
        _branch_fix_line, _branch_fix_segment, _branch_mention, _branch_protected,
        _guillemet_spans, normalize_branch_form
    )
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.html import (  # type: ignore  # noqa: E402,F401
        _BR_RE, _KNOWN_HTML_TAGS, _TAGLIKE_RE, _fm_body, _fm_head, _norm_cell, _plain,
        _strip_markdown_links, _title_key, cell_text, expand_grid, find_top_tables,
        html_fragment_to_markdown, parse_md_tables, passport_cell_html, protect_token_tags
    )
    from .kitcheck.columns import (  # type: ignore  # noqa: E402,F401
        _CARDINALITY_RE, _COLUMN_RULES, _LOGICAL_CARD_RE, _LOGICAL_CARD_TOKEN, _PATH_RE,
        _SENTENCE_RE, _STRUCT_LABEL_BARE_RE, _STRUCT_LABEL_RE, _TITLE_SUSPECT_RES, _TYPE_TOKENS,
        _XML_PATHISH_RE, _bare_type_name, _is_cardinality_title, _is_section_row,
        _looks_like_cardinality, _looks_like_cardinality_logical, _looks_like_obligation,
        _looks_like_obligation_pair, _looks_like_path, _no_xml_path, _title_suspicious,
        validate_columns
    )
    from .kitcheck.branch_form import (  # type: ignore  # noqa: E402,F401
        _BRANCH_IF_RE, _BRANCH_INDENT_RE, _BRANCH_MARKER_RE, _BRANCH_OUT_RE, _BRANCH_PLAIN_IF_RE,
        _branch_fix_line, _branch_fix_segment, _branch_mention, _branch_protected,
        _guillemet_spans, normalize_branch_form
    )


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
        data = json.loads(_fs.read_text(path, encoding="utf-8"))
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
    text = _fs.read_text(md_path, encoding="utf-8")
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


def run_branch_form(paths: List[Path], write: bool) -> int:
    """Режим --branch-form: по умолчанию сухой прогон (перечень файлов и число переносов),
    --write — запись (BOM и EOL сохраняются, неизменённый файл не перезаписывается)."""
    files: List[Path] = []
    for p in paths:
        if p.is_dir():
            try:
                from kitcheck.md import _kit_md
            except ImportError:  # импорт пакетом app.scripts.CI (тесты)
                from .kitcheck.md import _kit_md  # type: ignore
            files += _kit_md(p)
        else:
            files.append(p)
    n_files = n_total = 0
    skipped_all: Dict[str, int] = {}
    kinds_all: Dict[str, int] = {}
    for f in files:
        raw = f.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = (raw[3:] if bom else raw).decode("utf-8")
        new, cnt, skipped = normalize_branch_form(text, kinds_all)
        for k, v in skipped.items():
            skipped_all[k] = skipped_all.get(k, 0) + v
        if not cnt:
            continue
        n_files += 1
        n_total += cnt
        print(f"{f}: переносов {cnt}")
        if write:
            f.write_bytes((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
    mode = "записано" if write else "сухой прогон (--write — записать)"
    skip = ", ".join(f"{k} ×{v}" for k, v in sorted(skipped_all.items())) or "нет"
    by_kind = ", ".join(f"{k} {kinds_all.get(k, 0)}" for k in ("ячейки", "списки", "абзацы"))
    print(f"# форма ветвления: файлов {n_files} из {len(files)}, переносов {n_total} ({by_kind}); "
          f"пропущено (вручную): {skip} — {mode}")
    return 0


# Переходный реэкспорт (Д-50, 2026-10-30): проверки карточки переехали в
# kitcheck/checks/card_*.py; прежние имена normalize_tables.<проверка> отдаются
# лениво на один релиз (нормализатор при импорте гейт не грузит). Новый код
# импортирует проверки из kitcheck.
_CARD_MODULES = ('card_run', 'card_clean', 'card_controls', 'card_branch_form', 'card_notification', 'card_passport', 'card_steps', 'card_source', 'card_form', 'card_common')


def __getattr__(name: str):
    import importlib
    for m in _CARD_MODULES:
        # загружен пакетом (тесты) — тот же пакет, иначе модуль проверок грузился бы второй копией
        mod = (importlib.import_module(f".kitcheck.checks.{m}", __package__) if __package__
               else importlib.import_module(f"kitcheck.checks.{m}"))
        if name in vars(mod):
            return vars(mod)[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    ap.add_argument("--allow-sibling-docs", action="store_true",
                    help="разрешить относительные ссылки в sibling-пакеты "
                         "монорепо с srs/ или brd/ (топология ЦР)")
    ap.add_argument("--sidecar", action="store_true",
                    help="записать результат в <файл>.tables.md рядом (иначе stdout)")
    ap.add_argument("--min-valid", type=float, default=95.0,
                    help="порог валидности колонки в %% (ниже — результат не отдаётся)")
    ap.add_argument("--force", action="store_true",
                    help="отдать результат даже ниже порога (для разбора брака)")
    ap.add_argument("--branch-form", action="store_true",
                    help="форма ветвления (notation §1): «**Если** X, **то** Y» одной строкой → через "
                         "<br> — в ячейках, элементах списков и абзацах; аргументы — файлы или "
                         "корень комплекта; по умолчанию сухой прогон")
    ap.add_argument("--write", action="store_true",
                    help="для --branch-form: записать изменения")
    args = ap.parse_args()

    if args.branch_form:
        return run_branch_form(list(args.file), args.write)

    profile = Profile.load(args.profile) if args.profile else None
    main_file: Path = args.file[0]
    if len(args.file) > 1 and not args.check:
        print("# несколько файлов поддерживаются только в --check; "
              f"использую {main_file}", file=sys.stderr)

    if args.cell_to_md:
        text = _fs.read_text(main_file, encoding="utf-8")
        cell = passport_cell_html(text, args.cell_to_md)
        if cell is None:
            print(f"# ячейка с лейблом {args.cell_to_md!r} не найдена",
                  file=sys.stderr)
            return 2
        print(html_fragment_to_markdown(cell))
        return 0

    if args.check:
        try:  # Д-50: проверки карточки — в kitcheck
            from kitcheck.checks.card_run import run_check
        except ImportError:  # импорт пакетом app.scripts.CI (тесты)
            from .kitcheck.checks.card_run import run_check  # type: ignore
        report, ok = run_check(list(args.file), args.source,
                               min_valid_pct=args.min_valid,
                               docs_root=args.docs_root,
                               allow_sibling_docs=args.allow_sibling_docs)
        for line in report:
            print(f"# {line}", file=sys.stderr)
        if not ok:
            print("# БРАК: см. строки ✗ выше — исправьте карточку по "
                  "выходу утилиты.", file=sys.stderr)
            return 2
        print("# OK: все распознанные колонки выше порога.", file=sys.stderr)
        return 0

    if args.sample:
        text = _fs.read_text(main_file, encoding="utf-8")
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
