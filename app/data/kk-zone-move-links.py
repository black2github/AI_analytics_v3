# kk-zone-move-links.py
"""Перенос мини-комплекта зоны «вне Экосистемы» под docs/ (Д-49 п. 4, 2026-10-23).

ЗАЧЕМ. Гейт переноса несёт в репозиторий документации только docs/. Мини-комплект, который
лежит рядом с docs/ (modules/<имя>/), при переносе теряется, а ссылки на него из карточек
ведут за пределы репозитория. Норма теперь — docs/modules/<имя>/.

ЧТО ДЕЛАЕТ (из корня клона src-репозитория):
  1. Находит мини-комплекты modules/<имя>/ рядом с docs/ (или только указанный --name).
  2. Пересчитывает относительные markdown-ссылки вида [текст](путь) ПО ФАКТИЧЕСКОЙ ЦЕЛИ, а не
     заменой строки, в обоих направлениях:
       - из docs/ в мини-комплект (карточки CALL-MOD, README contract-call, матрица и т. п.);
       - из мини-комплекта в docs/ (паспорт границы, контракты интерфейса, spec/).
     Ссылки внутри мини-комплекта не меняются — его внутренняя структура переезжает целиком.
     Внешние адреса (http…), якоря (#…) и абсолютные пути не трогаются.
  3. Переносит каталог: git mv modules/<имя> docs/modules/<имя> (вне git — обычный перенос).
  4. Удаляет опустевший modules/ в корне и пустой каталог <имя>/ в корне, если он есть.

БАЙТЫ. В изменённых файлах меняется только текст пути внутри скобок ссылки: переводы строк
(CRLF/LF), BOM и всё остальное сохраняются. Файлы без изменений не перезаписываются.

ЗАПУСК (PowerShell, из корня клона):
  python <путь>\\kk-zone-move-links.py --dry-run      # план: что и где поменяется, ничего не пишет
  python <путь>\\kk-zone-move-links.py                # выполнить
  python <путь>\\kk-zone-move-links.py --name widgets-rtl --root C:\\doc-as-code\\EAS\\src-business-cards

После выполнения: git status (ожидание — переименования modules/… → docs/modules/… и правки
файлов из плана), прибор selfcheck (строки «⚠ мини-комплект вне docs/» больше нет, есть
«i мини-комплектов зоны: N»), гейт формы transfer_gate.py --after-step; коммит — как обычно.

ОГРАНИЧИТЕЛИ. Если docs/modules/<имя>/ уже существует — отказ без изменений. Ссылка, цель
которой не существует ни до, ни после, сообщается строкой «битая до переноса» и не меняется.
Ссылка из мини-комплекта на файл корня рабочего репозитория (open-questions.md и т. п.) —
служебный файл: глубина пересчитывается (ссылка в src не ломается), но в docs-репозиторий файл
не переезжает — такие ссылки перечисляются отдельно, их нужно убрать или заменить (гейт формы
даёт по ним ✗).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

LINK = re.compile(r"(\]\()([^)\s#]+)((?:#[^)\s]*)?\))")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="Перенос modules/<имя>/ в docs/modules/<имя>/ с "
                                             "пересчётом относительных ссылок (Д-49)")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="корень клона (по умолчанию — текущий каталог)")
    ap.add_argument("--name", action="append", default=None,
                    help="имя мини-комплекта (можно несколько раз); без ключа — все из modules/")
    ap.add_argument("--dry-run", action="store_true", help="только план, файлы не меняются")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    root = a.root.resolve()
    docs = root / "docs"
    old_base = root / "modules"
    new_base = docs / "modules"
    if not docs.is_dir() or not old_base.is_dir():
        print(f"нечего переносить: нет {docs} или {old_base}")
        return 1
    names = a.name or sorted(d.name for d in old_base.iterdir() if d.is_dir())
    kits = [(old_base / n, new_base / n) for n in names]
    for old, new in kits:
        if not old.is_dir():
            print(f"✗ нет мини-комплекта {old.relative_to(root)}")
            return 1
        if new.exists():
            print(f"✗ {new.relative_to(root)} уже существует — перенос отменён, изменений нет")
            return 1

    def moved(p: Path) -> Path:
        for old, new in kits:
            try:
                return new / p.relative_to(old)
            except ValueError:
                continue
        return p

    def in_kits(p: Path) -> bool:
        return any(p == old or old in p.parents for old, _ in kits)

    files = sorted(p for p in root.rglob("*.md")
                   if ".git" not in p.relative_to(root).parts
                   and (docs in p.parents or in_kits(p)))
    plan: Dict[Path, bytes] = {}
    counts = {"из docs/ в мини-комплект": 0, "из мини-комплекта в docs/": 0,
              "из мини-комплекта на служебные файлы корня": 0}
    changed_lines: List[str] = []
    service_links: List[str] = []
    broken: List[str] = []
    for f in files:
        raw = f.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
        new_f = moved(f)
        src_kit = in_kits(f)

        def fix(m: "re.Match[str]") -> str:
            tgt = m.group(2)
            if "://" in tgt or tgt.startswith(("mailto:", "/")) or re.match(r"^[A-Za-z]:", tgt):
                return m.group(0)
            old_abs = Path(os.path.normpath(f.parent / tgt))
            dst_kit = in_kits(old_abs)
            if src_kit and dst_kit:
                return m.group(0)               # внутри мини-комплекта — структура та же
            if not src_kit and not dst_kit:
                return m.group(0)               # обычная ссылка комплекта — не трогаем
            where = f"{f.relative_to(root).as_posix()}: {tgt}"
            if not old_abs.exists():
                broken.append(where)
                return m.group(0)
            service = src_kit and docs not in old_abs.parents
            if service:
                # из зоны — на файл корня рабочего репозитория: цель сохраняется (ссылка не
                # ломается в src), но в docs-репозиторий файл не переезжает — в перечень
                service_links.append(where)
            rel = Path(os.path.relpath(moved(old_abs), new_f.parent)).as_posix()
            if rel == tgt:
                return m.group(0)
            counts["из мини-комплекта на служебные файлы корня" if service else
                   "из мини-комплекта в docs/" if src_kit else "из docs/ в мини-комплект"] += 1
            changed_lines.append(f"  {f.relative_to(root).as_posix()}: {tgt} → {rel}")
            return m.group(1) + rel + m.group(3)

        new_text = LINK.sub(fix, text)
        if new_text != text:
            plan[f] = (b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8")

    total = sum(counts.values())
    print(("ПЛАН (--dry-run, файлы не меняются)" if a.dry_run else "ВЫПОЛНЕНИЕ") + ":")
    for old, new in kits:
        print(f"  перенос: {old.relative_to(root).as_posix()}/ → {new.relative_to(root).as_posix()}/")
    print(f"ссылок пересчитать: {total} — " + ", ".join(f"{k} {v}" for k, v in counts.items())
          + f"; файлов {len(plan)}")
    for ln in changed_lines:
        print(ln)
    if service_links:
        print(f"⚠ ссылки из мини-комплекта на служебные файлы рабочего репозитория ({len(service_links)}) "
              "— цель сохранена, но в docs-репозиторий файл не переезжает: убрать или заменить "
              "(гейт формы даёт по ним ✗)")
        for ln in service_links:
            print("  " + ln)
    if broken:
        print(f"⚠ битые до переноса ({len(broken)}) — не меняются:")
        for ln in broken:
            print("  " + ln)
    if a.dry_run:
        return 0

    for f, b in plan.items():
        f.write_bytes(b)
    is_git = _git(root, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    new_base.mkdir(parents=True, exist_ok=True)
    for old, new in kits:
        if is_git:
            r = _git(root, "mv", str(old.relative_to(root)), str(new.relative_to(root)))
            if r.returncode != 0:
                print(f"✗ git mv не выполнен: {r.stderr.strip()} — правки ссылок записаны, "
                      "каталог не перенесён; перенесите вручную и проверьте git status")
                return 2
        else:
            shutil.move(str(old), str(new))
        stray = root / new.name
        if stray.is_dir() and not any(stray.iterdir()):
            stray.rmdir()
            print(f"  удалён пустой {new.name}/ в корне")
    if old_base.is_dir() and not any(old_base.iterdir()):
        old_base.rmdir()
        print("  удалён опустевший modules/ в корне")
    print("готово: проверьте git status, selfcheck и transfer_gate.py --after-step")
    return 0


if __name__ == "__main__":
    sys.exit(main())
