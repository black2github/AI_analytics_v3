# app/scripts/CI/kitcheck/checks/function_placement.py
"""Сторож «контур функции: префикс идентификатора, каталог и имя файла» (шаблон function.md,
«Идентификация и размещение» и чек-лист п. 1–2; постановка прибору 2026-11-15, решение постановщика
по замеру 15.11). У карточки `type: function` (README каталогов не в счёт) контур по префиксу
идентификатора совпадает с подкаталогом каталога функций, имя файла начинается с идентификатора
строчными:

- FUN-CL-NN → function/client/, FUN-BNK-NN → function/bank/, FUN-SYS-NN → function/system/; слот
  сервиса или части в идентификаторе (FUN-<КОД>-SYS-NN) и суб-идентификатор с хвостом «.N»
  (FUN-DS-SYS-01.1) — тот же контур;
- имя файла — `<id строчными>-<короткое-название>.md` (или ровно `<id строчными>.md`).

Это внутренняя согласованность карточки, а не норма, менявшаяся со временем: ✗ строкой на карточку
(замер 15.11: одна карточка во всех комплектах). Часть вне контура Экосистемы проверяется как обычная —
шаблон даёт ей то же размещение (`docs/srs/<слаг>/function/<контур>/`).

Вне проверки: идентификатор без контура; карточка вне каталога функций; сама раскладка каталога —
старая раскладка `functions/` (множественное число) сверяется так же, как `function/`, но не судится:
дом типа — другой класс.

Слой — ядро: проверка читает только комплект и без выгрузки работает полностью."""
import re
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from kitcheck.md import _kit_md, read_frontmatter
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from ..md import _kit_md, read_frontmatter  # type: ignore

_ID_RE = re.compile(r"^FUN-(?:[A-Z0-9]+-)?(CL|BNK|SYS)-\d+(?:\.\d+)?$")
_DIRS = ("function", "functions")
_SUB = {"CL": "client", "BNK": "bank", "SYS": "system"}


def id_contour(fid: str) -> Optional[str]:
    """Контур функции по префиксу идентификатора: CL / BNK / SYS или None."""
    m = _ID_RE.match(fid)
    return m.group(1) if m else None


def placement_defects(fid: str, rel: str) -> Optional[List[str]]:
    """Расхождения карточки функции с идентификатором; None — вне проверки (идентификатор без
    контура или карточка вне каталога функций), [] — согласована."""
    cont = id_contour(fid)
    parts = rel.split("/")
    dirs = parts[:-1]
    idx = [i for i, p in enumerate(dirs) if p in _DIRS]
    if cont is None or not idx:
        return None
    i = idx[-1]
    sub = dirs[i + 1] if i + 1 < len(dirs) else ""
    want = _SUB[cont]
    out: List[str] = []
    if sub != want:
        where = f"{dirs[i]}/{sub}/" if sub else f"корне {dirs[i]}/"
        out.append(f"префикс идентификатора — контур {want}/, а карточка лежит в {where}")
    stem = Path(parts[-1]).stem.lower()
    low = fid.lower()
    if not (stem == low or stem.startswith(low + "-")):
        out.append(f"имя файла не начинается с идентификатора строчными («{low}-…»)")
    return out


def check_function_placement(docs: Path) -> Tuple[List[str], bool]:
    """✗ строкой на карточку функции, у которой префикс идентификатора не совпадает с подкаталогом или
    имя файла не начинается с идентификатора; ok = нет таких карточек."""
    rep: List[str] = []
    for md in _kit_md(docs):
        if md.name.lower() == "readme.md":
            continue
        fm = read_frontmatter(md) or {}
        if str(fm.get("type", "")).strip().strip("'\"") != "function":
            continue
        fid = str(fm.get("id", "")).strip().strip("'\"")
        rel = md.relative_to(docs).as_posix()
        bad = placement_defects(fid, rel)
        if bad:
            rep.append(f"✗ функция {fid} ({rel}): " + "; ".join(bad) + " — контур, каталог и имя файла "
                       "согласуются: переложить карточку или исправить идентификатор по контуру функции "
                       "вместе со ссылками на неё (шаблон function.md, «Идентификация и размещение»)")
    return rep, not rep
