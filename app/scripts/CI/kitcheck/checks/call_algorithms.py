# app/scripts/CI/kitcheck/checks/call_algorithms.py
"""Сторож «в карточке вызова нет алгоритмов» (шаблон contract-call.md, раздел B, норма влита
11.11.2026; постановка прибору 2026-11-11, правило признака 1 принято постановщиком 11.11,
вариант B). Карточка вызова (`type: contract-call`, README реестров не в счёт) отвечает на три
вопроса: кто и где вызывает метод, чем сервис заполняет запрос, куда кладёт ответ. Шаги,
ветвления, повторы и обработка ошибок — в функции или процессе.

Строки ⚠ уровня комплекта с числом карточек (полный перечень — в файле --out); вердикт не
меняют: в комплектах наследие, ошибкой проверка станет отдельным решением владельца после
захода по карточкам.

1. Раздел вне состава карточки — по структуре: состав заголовков — из шаблона. Прибор смысл
   заголовка не различает, поэтому текст строки нейтральный и подсказка — в три адреса.
   Прежнее имя раздела шаблона — отдельная строка со своим счётчиком.
2. Раздел «Процессы» — не указатель: больше двух колонок, ветвление нотацией (**Если** /
   **то** / **иначе**) в ячейке, текст сверх ссылки и места вызова, проза вместо таблицы.
3. Шаги в тексте карточки, в том числе в разделах привязки, — объявленная словарная эвристика
   («Шаг N» в начале строки, ячейки или пункта; «переход на шаг N»), строка в реестре
   словарных эвристик README прибора канона. В «Процессах» номер шага — место вызова.

Информационно (i): карточки с разделом «Из источника, вне разделов шаблона» (признаком не
считается, но туда алгоритм без нумерованных шагов ложится молча) и карточки без раздела
«Процессы».

Привязка данных — строки таблицы и строки-присваивания «<имя> = <значение>» (отдельной строкой
или пунктом списка; условие значения «**Если** …, **то** = …» — тоже присваивание): такая
инициализация равноценна таблице (уточнение владельца 11.11). Перед таблицей или списком
допустима одна вводная строка. Строка с ярлыком шага или переходом на шаг — не присваивание.
Тело раздела привязки судится так же, как подраздел: иное — признак 1 вида «текст в разделе
привязки» (лазейка «шаги присваиваниями», закрыта 11.11).

Вне проверки: блоки кода и HTML-комментарии, раздел «Временный снимок контракта» (состав
запроса и ответа владельца), карточки других типов (`internal-contract`,
`external-integration` — у них свои правила).

Слой — ядро: проверка читает только комплект и без выгрузки работает полностью (строка таблицы
«Слои прибора» README прибора канона; ядро пометки в шапке файла не несёт)."""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, code_line_flags, read_frontmatter, table_cells
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, code_line_flags, read_frontmatter, table_cells  # type: ignore

# строки, которые selfcheck пишет только в файл отчёта --out (тот же префикс, что
# selfcheck.OUT_ONLY): полный перечень под сводной строкой комплекта
_OUT_ONLY = "   · "
_CUT = "вырезать из карточки только при подтверждённом доме-приёмнике"
_HINT = f"перенести в вызывающую функцию или процесс; {_CUT}"

# --- состав карточки вызова: «Шаблон карточки вызова» contract-call.md ---
# Коды разделов: N — «Назначение», U — «Использование в сервисе …», S — временный снимок,
# P — «Процессы», T — «Транспорт», B — две таблицы привязки данных, A/X — общие для всех
# типов разделы «Приложенные артефакты» (attachments-block.md) и «Из источника, вне разделов
# шаблона» (гид миграции: «для других типов — тот же подраздел в конце карточки»).
_USE_PREFIX = "использование в сервисе"
_H2 = {"назначение": "N", "приложенные артефакты": "A", "из источника, вне разделов шаблона": "X"}
_H3_UNDER_USE = {"процессы": "P", "транспорт": "T",
                 "правила заполнения исходящего сообщения": "B",
                 "сопоставление входящего сообщения": "B"}
_SNAPSHOT = "временный снимок контракта"
# прежние имена раздела шаблона (до 02.11.2026 — «Обработка входящих ответов», 02.11 —
# «Сопоставление входящего ответа»): раздел назван до того, как получил определение, — в него
# попадал пересказ алгоритма функции. Отдельная строка; для признака 3 таблицей привязки не
# считается.
_OLD_NAMES = {"обработка входящих ответов": "Сопоставление входящего сообщения",
              "сопоставление входящего ответа": "Сопоставление входящего сообщения"}
# «Где используется» — не прежнее имя (в истории шаблона карточки вызова такого раздела нет):
# вне состава, подсказка — куда указатель
_USED_WHERE = "где используется"

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
LF = chr(10)
_HEAD_RE = re.compile(r"^(#{2,6})\s+(.*?)\s*#*\s*$")
_LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
_SEP_CELL_RE = re.compile(r"^:?-{1,}:?$")
_BRANCH_RE = re.compile(r"\*\*\s*(?:если|иначе|то)\s*\*\*", re.I)
# строка-присваивание: «<имя> = <значение>» отдельной строкой или пунктом списка, с «;»/«.» на
# конце или без; знак «=» не входит в «==», «!=», «<=», «>=», «=>»
_LIST_MARK_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_ASSIGN_RE = re.compile(r"^\S.*?(?<![=!<>])=(?![=>])\s*\S")
# граница предложения: знак конца после слова от трёх букв или заглавной аббревиатуры от двух
# знаков с буквой («АС.», «Ф1.»); сокращения «п.», «см.» и номер шага «Шаг 12. Название»
# границей не считаются; следом — заглавная буква или кавычка
_SENTENCE_RE = re.compile(
    r"(?:[А-Яа-яЁёA-Za-z]{3}|\b(?=\w*[А-ЯЁA-Z])[А-ЯЁA-Z0-9]{2,})[.!?]\s+[А-ЯЁA-Z«\"]")
# признак 3 (объявленная эвристика): ярлык шага в начале строки, ячейки, пункта списка или
# после <br>; переход к шагу по номеру
_STEP_LABEL_RE = re.compile(
    r"(?:^|\||<br\s*/?>)\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*)?\s*Шаг\s*№?\s*\d", re.I)
_STEP_JUMP_RE = re.compile(
    r"(?:переход\w*|перейти|возврат\w*|вернуться)\s+(?:к|на)\s+шаг\w*\s*№?\s*\d", re.I)


def _norm(title: str) -> str:
    t = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+", "", title.strip())
    t = re.sub(r"\s+", " ", t).rstrip(" .:").strip()
    return t.lower().replace("ё", "е")


def _is_call_card(md: Path) -> bool:
    if md.name.lower() == "readme.md":
        return False
    fm = read_frontmatter(md) or {}
    return str(fm.get("type", "")).strip().strip("'\"") == "contract-call"


def _card_id(md: Path) -> str:
    fm = read_frontmatter(md) or {}
    return str(fm.get("id", "")).strip().strip("'\"") or md.stem


def is_assignment(line: str) -> bool:
    """Строка-присваивание «<имя> = <значение>» (пунктом списка или отдельной строкой). Строка с
    ярлыком шага или переходом на шаг присваиванием не считается, даже если в ней есть «=»:
    в таблицах привязки нет ссылок на номера шагов и пересказа алгоритма (шаблон)."""
    if _STEP_LABEL_RE.search(line) or _STEP_JUMP_RE.search(line):
        return False
    return bool(_ASSIGN_RE.match(_LIST_MARK_RE.sub("", line).strip()))


_ASSIGN_SPLIT_RE = re.compile(r"^(.*?)(?<![=!<>])=(?![=>])\s*(.*)$")


def assignment_parts(line: str) -> Optional[Tuple[str, str]]:
    """(левая часть, значение) строки-присваивания по тому же определению, что is_assignment;
    не присваивание — None. Левая часть — как в тексте (разметку не снимает)."""
    if not is_assignment(line):
        return None
    m = _ASSIGN_SPLIT_RE.match(_LIST_MARK_RE.sub("", line).strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else None


# формула канона «данных в источнике нет» (conventions §6 п. 5) — допустимая строка привязки
_NOT_SET_RE = re.compile(r"^\s*в постановке не задано\.?\s*$", re.I)


def _is_binding_line(line: str) -> bool:
    return line.lstrip().startswith("|") or is_assignment(line) or bool(_NOT_SET_RE.match(line))


# вводная часть перед таблицей, списком или подразделом: не больше двух строк, в каждой одно
# предложение, без нотации ветвления и без ярлыка шага (правка постановщика 11.11: мерить строками
# нельзя — две дословные фразы источника не алгоритм, а одна строка из двух предложений бывает
# пересказом алгоритма)
_INTRO_MAX = 2


def _is_intro_line(line: str) -> bool:
    plain = _LINK_RE.sub(" ", line)
    return not (_SENTENCE_RE.search(plain) or _BRANCH_RE.search(line)
                or _STEP_LABEL_RE.search(line) or _STEP_JUMP_RE.search(line))


def binding_only(body: List[str], before_subsection: bool = False) -> Optional[bool]:
    """Содержимое раздела или подраздела привязки — только привязка данных: строки таблицы,
    присваивания, «В постановке не задано»; перед каждой таблицей, списком или подразделом —
    вводная часть до двух однофразных строк (before_subsection: тело раздела кончается вводной
    частью перед подразделом). None — своих строк нет (только вложенные подразделы): судят
    вложенные."""
    content = [ln for ln in body if ln.strip()]
    if not content:
        return None
    flags = [_is_binding_line(ln) for ln in content]
    if before_subsection:
        flags.append(True)
    if not any(flags):
        return False
    run: List[str] = []  # текущая серия строк не-привязки
    for k, ok in enumerate(flags):
        if not ok:
            run.append(content[k])
            continue
        if run and (len(run) > _INTRO_MAX or not all(_is_intro_line(x) for x in run)):
            return False
        run = []
    return not run  # серия в конце, без таблицы или списка после неё, — текст


def analyse(text: str) -> Dict[str, List[Tuple[int, str]]]:
    """Находки одной карточки по ключам: s1 — вне состава, s1old — прежнее имя раздела,
    s2 — «Процессы» не указатель, s3 — шаги, i_src — раздел «Из источника…», i_noproc — нет
    раздела «Процессы». Значение — [(строка с 1 по исходному тексту, текст)]."""
    # комментарий гасится с сохранением переводов строк: номера строк — по исходному тексту
    lines = _COMMENT_RE.sub(lambda m: LF * m.group(0).count(LF), text).splitlines()
    code = code_line_flags(lines)
    out: Dict[str, List[Tuple[int, str]]] = {k: [] for k in
                                             ("s1", "s1old", "s2", "s3", "i_src", "i_noproc")}
    h2: Optional[str] = None
    h3: Optional[str] = None
    region: List[str] = []  # код раздела по строке (для признаков 2–3)
    subs: List[Tuple[int, str, List[str]]] = []  # подразделы привязки: (строка, имя, тело)
    bsecs: List[List] = []  # разделы привязки: [строка, имя, тело, есть подразделы]
    in_sub = False
    has_proc = False
    in_frontmatter = bool(lines) and lines[0].strip() == "---"
    for i, ln in enumerate(lines):
        if in_frontmatter:
            region.append("FM")
            if i > 0 and ln.strip() == "---":
                in_frontmatter = False
            continue
        if code[i]:
            region.append("CODE")
            continue
        m = _HEAD_RE.match(ln)
        if m:
            lvl, raw = len(m.group(1)), m.group(2)
            name = _norm(raw)
            if lvl == 2:
                h3, in_sub = None, False
                if name.startswith(_USE_PREFIX):
                    h2 = "U"
                elif name == _SNAPSHOT:
                    h2 = "S"
                elif name in _H2:
                    h2 = _H2[name]
                    if h2 == "X":
                        out["i_src"].append((i + 1, raw))
                else:
                    h2 = "OUT"
                    out["s1"].append((i + 1, f"«{raw}» — раздел вне состава"))
            elif lvl == 3:
                in_sub = False
                if h2 == "U" and name in _H3_UNDER_USE:
                    h3 = _H3_UNDER_USE[name]
                    has_proc = has_proc or h3 == "P"
                    if h3 == "B":
                        bsecs.append([i + 1, raw, [], False])
                elif h2 == "U" and name in _OLD_NAMES:
                    h3 = "OLD"
                    out["s1old"].append((i + 1, f"«{raw}» — теперь «{_OLD_NAMES[name]}»"))
                elif name == _SNAPSHOT and h2 in ("N", "U", "S"):
                    h3 = "S"
                elif h2 in ("OUT", "A", "X", "S"):
                    h3 = h2  # внутри раздела вне состава или общего — отдельно не считается
                else:
                    h3 = "OUT"
                    tail = "; указатель мест вызова — в «Процессы»" if name == _USED_WHERE else ""
                    out["s1"].append((i + 1, f"«{raw}» — раздел вне состава{tail}"))
            else:
                par = h3 or h2
                if par == "B":
                    in_sub = True
                    subs.append((i + 1, raw, []))
                    if bsecs:
                        bsecs[-1][3] = True
                elif par in ("P", "T", "N", "U", None):
                    out["s1"].append((i + 1, f"«{raw}» — подраздел вне состава"))
            region.append("HEAD")
            continue
        par = h3 or h2 or "TOP"
        if par == "B" and in_sub:
            region.append("BSUB")
            subs[-1][2].append(ln)
        else:
            region.append(par)
            if par == "B" and bsecs:
                bsecs[-1][2].append(ln)
    for n, raw, body, has_subs in bsecs:
        if binding_only(body, before_subsection=has_subs) is False:
            out["s1"].append((n, f"«{raw}» — текст в разделе привязки сверх таблицы и присваиваний"))
    for n, raw, body in subs:
        if binding_only(body) is False:
            out["s1"].append((n, f"«{raw}» — подраздел таблицы привязки: текст сверх таблицы "
                                 "и присваиваний"))
    out["s1"].sort()
    out["s2"] = _processes(lines, region)
    out["s3"] = _steps(lines, region)
    if not has_proc:
        out["i_noproc"].append((0, "нет раздела «Процессы»"))
    return out


def _processes(lines: List[str], region: List[str]) -> List[Tuple[int, str]]:
    """Признак 2: раздел «Процессы» — не указатель."""
    found: List[Tuple[int, str]] = []
    idx = [i for i, r in enumerate(region) if r == "P"]
    if not idx:
        return found
    table_rows = [i for i in idx if lines[i].lstrip().startswith("|")]
    prose = [i for i in idx if lines[i].strip() and not lines[i].lstrip().startswith("|")]
    header_seen = False
    for i in table_rows:
        cells = table_cells(lines[i])
        if all(_SEP_CELL_RE.match(c) for c in cells if c):
            continue
        if not header_seen:
            header_seen = True
            if len(cells) > 2:
                found.append((i + 1, f"таблица в {len(cells)} колонки — указатель в две: "
                                     "функция или процесс и место вызова"))
            continue
        kinds = []
        if any(_BRANCH_RE.search(c) for c in cells):
            kinds.append("ветвление в ячейке")
        # текст в ячейке — у таблицы любой ширины: перенос строки или больше одного предложения;
        # в колонках после места вызова — ещё ярлык шага и переход на шаг (эвристика признака 3)
        if any(re.search(r"<br\s*/?>", c) or _SENTENCE_RE.search(_LINK_RE.sub(" ", c)) for c in cells) \
                or any(_STEP_LABEL_RE.search("|" + c) or _STEP_JUMP_RE.search(c) for c in cells[2:]):
            kinds.append("текст сверх ссылки и места вызова")
        if kinds:
            found.append((i + 1, ", ".join(kinds)))
        if i + 1 < len(lines) and not lines[i + 1].lstrip().startswith("|"):
            header_seen = False  # следующая таблица раздела — со своей шапкой
    if prose:
        # проза: строка без ссылки и не присваивание. Без таблицы допустимы строки-указатели
        # со ссылкой (одна фраза или список ссылок); при таблице текст рядом — сверх указателя
        bare = [i for i in prose if not _LINK_RE.search(lines[i]) and not is_assignment(lines[i])]
        if not table_rows and bare:
            found.append((bare[0] + 1, "проза вместо таблицы-указателя"))
        elif table_rows and bare:
            found.append((bare[0] + 1, "текст рядом с таблицей сверх указателя"))
        if not table_rows and not bare and len(prose) == 1 and \
                len(_SENTENCE_RE.findall(_LINK_RE.sub(" ", lines[prose[0]]))) > 1:
            found.append((prose[0] + 1, "проза вместо таблицы-указателя"))
    return sorted(found)


def _steps(lines: List[str], region: List[str]) -> List[Tuple[int, str]]:
    """Признак 3: нумерованные шаги во всех разделах, кроме «Процессов» (у них признак 2 — номер
    шага там место вызова), временного снимка, кода и шапки. В разделах привязки — тоже: в них
    нет ссылок на номера шагов (шаблон; лазейка закрыта 11.11)."""
    skip = {"P", "S", "CODE", "FM", "HEAD"}
    found: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        if region[i] in skip:
            continue
        m = _STEP_LABEL_RE.search(ln) or _STEP_JUMP_RE.search(ln)
        if m:
            frag = re.sub(r"\s+", " ", ln[m.start():m.start() + 60].lstrip("|< br/>")).strip()
            found.append((i + 1, f"«{frag}…»"))
    return found


# (ключ, уровень, что, подсказка)
_SIGNS = (
    ("s1", "⚠", "раздел вне состава карточки вызова",
     "шаги и ветвления — в вызывающую функцию или процесс; формат метода, коды, примеры — в "
     "контракт владельца или раздел «Временный снимок контракта»; места вызова — в «Процессы»; "
     + _CUT),
    ("s1old", "⚠", "прежнее имя раздела шаблона",
     "переименовать в «Сопоставление входящего сообщения»; в разделе — только привязка данных, "
     "шаги и ветвления — в вызывающую функцию или процесс; " + _CUT),
    ("s2", "⚠", "раздел «Процессы» не указатель (больше двух колонок, ветвление, текст сверх "
                "ссылки и места вызова, проза)", _HINT),
    ("s3", "⚠", "шаги в тексте карточки, в том числе в разделах привязки («Шаг N», «переход на "
                "шаг N» — объявленная эвристика; номер шага в «Процессах» — место вызова)", _HINT),
    ("i_src", "i", "раздел «Из источника, вне разделов шаблона»",
     "признаком не считается; проверить, что в нём нет шагов и ветвлений"),
    ("i_noproc", "i", "нет раздела «Процессы»", "места вызова не указаны"),
)


def check_call_algorithms(docs: Path) -> List[str]:
    """Строки комплекта по признакам, где есть находки: уровень, число карточек, первые три ID;
    полный перечень «файл:строка — что» — в --out."""
    per: Dict[str, List[Tuple[str, str, List[Tuple[int, str]]]]] = {k: [] for k, *_ in _SIGNS}
    for md in _kit_md(docs):
        if not _is_call_card(md):
            continue
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        res = analyse(text)
        rel = md.relative_to(docs).as_posix()
        for k, *_ in _SIGNS:
            if res[k]:
                per[k].append((_card_id(md), rel, res[k]))
    report: List[str] = []
    for k, mark, label, hint in _SIGNS:
        rows = per[k]
        if not rows:
            continue
        head = ", ".join(cid for cid, _, _ in rows[:3])
        more = f", и ещё {len(rows) - 3}" if len(rows) > 3 else ""
        split = ""
        if k == "s2":
            # третья колонка без содержания и алгоритм в ячейке — разные объёмы работы
            n_body = sum(1 for _c, _r, hits in rows if any(not w.startswith("таблица в ") for _n, w in hits))
            split = f", из них с ветвлением или текстом в ячейке либо прозой — {n_body}"
        report.append(f"{mark} карточка вызова — {label}: {len(rows)} карточек ({head}{more}){split} — {hint}")
        report.extend(f"{_OUT_ONLY}{rel}" + (f":{n} — {what}" if n else "")
                      for _cid, rel, hits in rows for n, what in hits)
    return report
