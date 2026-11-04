# app/scripts/CI/kitcheck/checks/zone.py
"""Зона «вне Экосистемы» — мини-комплекты `docs/modules/<имя>/` (Д-49 п. 4, 2026-10-23):
перенос в репозиторий документации несёт `docs/` целиком, поэтому мини-комплект живёт под
`docs/`, а не рядом. Сводная i-строка зоны, переходный сторож старого места `modules/` рядом
с `docs/` и сторож паспорта границы. Только ⚠ и i, вердикт не меняют."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict, List, Optional
try:
    from kitcheck import fs as _fs
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
from .card_source import _frontmatter_title, check_title


def check_zone_card(p: Path, rel: str, pids: List[str], idx: Dict[str, Path]) -> List[str]:
    """Карточка зоны с confluence_page_ids (кроме spec/) — сверка с выгрузкой по первой
    странице (2026-11-04; шаблоны module-interface.md и module-kit-readme.md обещают её, до
    правки прибор молчал). Первая страница в выгрузке — title дословно, как у карточек
    комплекта; расхождение — ⚠; первой нет в выгрузке — ⚠; доп. страницы — спецификации
    чужого контура: строка i, без сверки. Только ⚠ и i: зона вне переносимого состояния, вердикт не меняют."""
    rep: List[str] = []
    src = idx.get(pids[0])
    if src is None:
        rep.append(f"⚠ {rel}: источник первой страницы не найден в выгрузке (page_id "
                   f"{pids[0]}) — title не сверен; зона вне переносимого состояния, "
                   "вердикт не меняется")
    else:
        card_text = _fs.read_text(p, encoding="utf-8", errors="replace")
        src_text = _fs.read_text(src, encoding="utf-8", errors="replace")
        _lines, ok = check_title(card_text, src_text, zone=True)
        if not ok:
            rep.append(f"⚠ {rel}: title расходится с наименованием первой страницы-источника "
                       f"{src.name} (карточка {_frontmatter_title(card_text)!r}, источник "
                       f"{_frontmatter_title(src_text)!r}) — перенос дословный; зона вне "
                       "переносимого состояния, вердикт не меняется")
    if len(pids) > 1:
        outside = [x for x in pids[1:] if x not in idx]
        inside = [x for x in pids[1:] if x in idx]
        parts = ([f"вне выгрузки, без сверки: {', '.join(outside)}"] if outside else []) + (
            [f"в выгрузке, без сверки: {', '.join(inside)}"] if inside else [])
        rep.append(f"i {rel}: доп. страницы-источники ({len(pids) - 1}) — спецификации "
                   f"чужого контура; {'; '.join(parts)}")
    return rep


def check_module_zone(docs: Path, card_lines: Optional[List[str]] = None) -> List[str]:
    """Комплект без зоны и без старого каталога — пусто (ни одной строки зоны).
    card_lines — строки сверки карточек зоны с выгрузкой (check_zone_card): сводная строка
    со счётчиками и сами строки — после строк мини-комплектов."""
    rep: List[str] = []
    zroot = docs / "modules"
    kits = sorted(d for d in zroot.iterdir() if d.is_dir()) if zroot.is_dir() else []
    if kits:
        parts = [f"docs/modules/{d.name}, файлов {sum(1 for f in d.rglob('*') if f.is_file())}"
                 for d in kits]
        rep.append(f"i мини-комплектов зоны: {len(kits)} ({'; '.join(parts)})")
        for d in kits:
            if not (d / "README.md").is_file():
                rep.append(f"⚠ мини-комплект без паспорта границы (module-kit-readme.md): "
                           f"docs/modules/{d.name}/ — нет README.md")
    if card_lines:
        n_w = sum(1 for ln in card_lines if ln.startswith("⚠"))
        n_i = sum(1 for ln in card_lines if ln.startswith("i "))
        n_f = len({ln.split(":", 1)[0][2:] for ln in card_lines})
        rep.append(f"i карточки зоны — сверка с выгрузкой по первой странице: файлов {n_f}, "
                   f"⚠ {n_w}, i {n_i} (только ⚠ и i, вердикт не меняют)")
        rep.extend(card_lines)
    # переходный сторож: старое место рядом с docs/ (норма Д-46 до 2026-10-23). Каталог
    # modules/ в корне остаётся штатным для сторожа корня, иначе до переезда — ✗
    # «посторонний каталог» (асимметрия ошибок)
    old = docs.parent / "modules"
    if docs.name == "docs" and old.is_dir() and old.resolve() != zroot.resolve():
        names = sorted(d.name for d in old.iterdir() if d.is_dir()) or ["(пусто)"]
        rep.append("⚠ мини-комплект вне docs/ — переносом не переезжает (Д-49), перенести в "
                   f"docs/modules/<имя>/: modules/{', modules/'.join(names)}")
    return rep
