# app/scripts/CI/kitcheck/checks/zone.py
"""Зона «вне Экосистемы» — мини-комплекты `docs/modules/<имя>/` (Д-49 п. 4, 2026-10-23):
перенос в репозиторий документации несёт `docs/` целиком, поэтому мини-комплект живёт под
`docs/`, а не рядом. Сводная i-строка зоны, переходный сторож старого места `modules/` рядом
с `docs/` и сторож паспорта границы. Только ⚠ и i, вердикт не меняют."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import List


def check_module_zone(docs: Path) -> List[str]:
    """Комплект без зоны и без старого каталога — пусто (ни одной строки зоны)."""
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
    # переходный сторож: старое место рядом с docs/ (норма Д-46 до 2026-10-23). Каталог
    # modules/ в корне остаётся штатным для сторожа корня, иначе до переезда — ✗
    # «посторонний каталог» (асимметрия ошибок)
    old = docs.parent / "modules"
    if docs.name == "docs" and old.is_dir() and old.resolve() != zroot.resolve():
        names = sorted(d.name for d in old.iterdir() if d.is_dir()) or ["(пусто)"]
        rep.append("⚠ мини-комплект вне docs/ — переносом не переезжает (Д-49), перенести в "
                   f"docs/modules/<имя>/: modules/{', modules/'.join(names)}")
    return rep
