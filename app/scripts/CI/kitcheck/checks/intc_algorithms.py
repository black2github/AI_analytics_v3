# app/scripts/CI/kitcheck/checks/intc_algorithms.py
"""Сторож «в карточке внутреннего контракта нет алгоритма» (скилл create-internal-contracts, пункт
«Алгоритм в паспорте метода»; шаблон internal-contracts.md; постановка прибору 2026-11-13, решения
постановщика по замеру 13.11). Карточка контракта (`type: internal-contract`, README реестров не в
счёт) описывает метод — паспорт, параметры, коды результата, примеры, потребителей. Алгоритм с шагами
и ветвлениями в неё не переносится: его дом — функция метода (заход create-function), в карточке —
одна ссылка на функцию: строкой паспорта, где источник держал алгоритм или отсылку к нему, иначе
строкой под таблицей паспорта «Поведение метода — <ссылка>» (шаблон, правка канона 13.11). Такая
ссылка и ячейка «Что делает» метода js-api со ссылкой на функцию части — не признак.

Строки ⚠ уровня комплекта с числом карточек (полный перечень — в файле --out); вердикт не меняют:
в комплектах наследие (замер 13.11: шаги — КК и два комплекта справочников), ошибкой проверка станет
отдельным решением владельца после захода команд.

1. Шаги в тексте карточки — объявленная словарная эвристика сторожа карточек вызова
   (`call_algorithms`, признак 3: «Шаг N» в начале строки, ячейки или пункта; «переход на шаг N»),
   та же строка реестра словарных эвристик README прибора канона, расширенная на второй тип. Здесь
   же — заголовок, который начинается с «Шаг N». Известный пропуск: таблица шагов с номером в
   колонке «№» и без единого перехода на шаг — эвристика её не видит (раздел виден признаком 2).
2. Раздел вне состава карточки — по структуре: заголовок второго уровня, которого нет в шаблоне
   типа, и заголовок первого уровня сверх заголовка карточки. Прибор смысл заголовка не различает:
   текст строки нейтральный, в строке — имена разделов с числом карточек, чтобы читатель видел,
   алгоритм это, указатель или имя не по шаблону.
3. Карточка вне своего каталога — по структуре: карточка лежит в `srs/internal-contract/` комплекта
   или `srs/<слаг>/internal-contract/` части; подкаталог не судится.

Вне проверки: блоки кода и HTML-комментарии, шапка документа, sidecar-примеры (не .md и без типа),
карточки других типов.

Слой — ядро: проверка читает только комплект и без выгрузки работает полностью."""
import re
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md, code_line_flags, read_frontmatter
    from kitcheck.checks.call_algorithms import (_COMMENT_RE, _STEP_JUMP_RE, _STEP_LABEL_RE, _card_id,
                                                  _norm)
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md, code_line_flags, read_frontmatter  # type: ignore
    from .call_algorithms import (_COMMENT_RE, _STEP_JUMP_RE, _STEP_LABEL_RE, _card_id,  # type: ignore
                                  _norm)

# строки, которые selfcheck пишет только в файл отчёта --out (тот же префикс, что selfcheck.OUT_ONLY)
_OUT_ONLY = "   · "
LF = chr(10)
_CUT = "вырезать из карточки только при подтверждённом доме-приёмнике"
_TOP = 5  # имён разделов и каталогов в строке комплекта

# состав карточки: «Шаблон карточки метода» internal-contracts.md (номера разделов снимаются) и
# общие для всех типов разделы «Приложенные артефакты» (attachments-block.md) и «Из источника, вне
# разделов шаблона» (гид миграции)
_H2 = {"краткое описание", "входные параметры", "исходящие параметры и коды результата",
       "обработка ошибок и повторные вызовы", "примеры обмена", "потребители",
       "приложенные артефакты", "из источника, вне разделов шаблона"}
_DIR = "internal-contract"

_HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HEAD_STEP_RE = re.compile(r"^(?:\*\*)?\s*Шаг\s*№?\s*\d", re.I)


def _is_intc_card(md: Path) -> bool:
    if md.name.lower() == "readme.md":
        return False
    fm = read_frontmatter(md) or {}
    return str(fm.get("type", "")).strip().strip("'\"") == "internal-contract"


def _title(raw: str) -> str:
    """Имя раздела для строки отчёта: без номера раздела и выделения."""
    t = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+", "", raw.replace("*", "").strip())
    return re.sub(r"\s+", " ", t).rstrip(" .:").strip()


def analyse(text: str) -> Dict[str, List[Tuple[int, str]]]:
    """Находки одной карточки: steps — [(строка с 1, фрагмент)], sections — [(строка с 1, имя
    раздела)] вне состава. Номера строк — по исходному тексту."""
    lines = _COMMENT_RE.sub(lambda m: LF * m.group(0).count(LF), text).splitlines()
    code = code_line_flags(lines)
    body = 0
    if lines and lines[0].strip() == "---":
        body = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    steps: List[Tuple[int, str]] = []
    sections: List[Tuple[int, str]] = []
    h1_seen = False
    for i, ln in enumerate(lines):
        if i < body or code[i]:
            continue
        m = _HEAD_RE.match(ln)
        if m:
            lvl, raw = len(m.group(1)), m.group(2)
            if lvl == 1:
                if h1_seen:
                    sections.append((i + 1, _title(raw)))
                h1_seen = True
            elif lvl == 2 and _norm(raw) not in _H2:
                sections.append((i + 1, _title(raw)))
            if _HEAD_STEP_RE.match(raw):
                steps.append((i + 1, f"«{raw.strip()[:60]}» — заголовок"))
            continue
        hit = _STEP_LABEL_RE.search(ln) or _STEP_JUMP_RE.search(ln)
        if hit:
            frag = re.sub(r"\s+", " ", ln[hit.start():hit.start() + 60].lstrip("|< br/>")).strip()
            steps.append((i + 1, f"«{frag}…»"))
    return {"steps": steps, "sections": sections}


def home_ok(rel: str) -> bool:
    """Карточка лежит в каталоге `srs/internal-contract/` или `srs/<слаг>/internal-contract/`
    (rel — путь от корня комплекта); глубже — любой подкаталог."""
    parts = rel.split("/")[:-1]
    if "srs" not in parts:
        return False
    i = len(parts) - 1 - parts[::-1].index("srs")
    return _DIR in parts[i + 1:i + 3]


def _ids(rows: List[Tuple[str, str]]) -> str:
    head = ", ".join(cid for cid, _ in rows[:3])
    return head + (f", и ещё {len(rows) - 3}" if len(rows) > 3 else "")


def _top(counter: Dict[str, int]) -> str:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    head = ", ".join(f"«{k}» ×{v}" for k, v in items[:_TOP])
    return head + (f", и ещё {len(items) - _TOP}" if len(items) > _TOP else "")


def check_intc_algorithms(docs: Path) -> List[str]:
    """Строки комплекта по признакам, где есть находки: ⚠, число карточек, первые три ID (у
    разделов и каталогов — ещё самые частые имена с числом карточек); перечень «файл:строка — что» —
    в --out."""
    steps: List[Tuple[str, str, List[Tuple[int, str]]]] = []
    secs: List[Tuple[str, str, List[Tuple[int, str]]]] = []
    homes: List[Tuple[str, str]] = []
    for md in _kit_md(docs):
        if not _is_intc_card(md):
            continue
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        res = analyse(text)
        rel = md.relative_to(docs).as_posix()
        cid = _card_id(md)
        if res["steps"]:
            steps.append((cid, rel, res["steps"]))
        if res["sections"]:
            secs.append((cid, rel, res["sections"]))
        if not home_ok(rel):
            homes.append((cid, rel))
    rep: List[str] = []
    if steps:
        rep.append(f"⚠ карточка внутреннего контракта — шаги в тексте карточки («Шаг N», «переход на "
                   f"шаг N» — объявленная эвристика): {len(steps)} карточек "
                   f"({_ids([(c, r) for c, r, _ in steps])}) — алгоритм метода — в функцию метода "
                   "(заход create-function), в карточке — одна ссылка на неё; " + _CUT)
        rep += [f"{_OUT_ONLY}{rel}:{n} — {w}" for _c, rel, hits in steps for n, w in hits]
    if secs:
        names: Dict[str, int] = {}
        for _c, _r, hits in secs:
            for k in {t for _n, t in hits}:
                names[k] = names.get(k, 0) + 1
        rep.append(f"⚠ карточка внутреннего контракта — раздел вне состава карточки: {len(secs)} "
                   f"карточек ({_ids([(c, r) for c, r, _ in secs])}); разделы: {_top(names)} — шаги "
                   "и ветвления — в функцию метода, ссылка на неё — строкой паспорта или строкой "
                   "«Поведение метода — …» под паспортом; формат, параметры, коды, примеры — в "
                   "разделы шаблона internal-contracts.md; " + _CUT)
        rep += [f"{_OUT_ONLY}{rel}:{n} — «{t}» — раздел вне состава"
                for _c, rel, hits in secs for n, t in hits]
    if homes:
        dirs: Dict[str, int] = {}
        for _c, rel in homes:
            d = "/".join(rel.split("/")[:-1][:4])
            dirs[d + "/"] = dirs.get(d + "/", 0) + 1
        rep.append(f"⚠ карточка внутреннего контракта — карточка вне каталога internal-contract/: "
                   f"{len(homes)} карточек ({_ids(homes)}); каталоги: {_top(dirs)} — место карточки — "
                   "srs/internal-contract/ комплекта или srs/<слаг>/internal-contract/ части "
                   "(шаблон internal-contracts.md, «Состав каталога»)")
        rep += [f"{_OUT_ONLY}{rel}" for _c, rel in homes]
    return rep
