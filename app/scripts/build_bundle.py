# app/scripts/build_bundle.py
#
# Сборщик поставки confluence-tree-exporter из канона.
#
# Зачем. Бандл — та же кодовая база, но в другой упаковке: без тестов, с
# wheels и .bat, с парой отличий под закрытый контур. Пока копия делалась
# руками, она молча расходилась с каноном: на 2026-09-06 сверка нашла
# нормализатор таблиц месячной давности (272 строки против 4198 в каноне),
# и узнали об этом случайно — никакой механизм не сигналил. Отпечаток
# исходников этот класс не ловит по построению: он считается по СВОЕМУ
# дереву, а деревья разного состава (в каноне ~106 модулей, в поставке ~36),
# поэтому числа несравнимы и «совпадение отпечатков» тут ничего не значит.
#
# Решение: поставка — производное, а не копия. Здесь лежит манифест (что
# именно уезжает), перечень намеренных отличий контура и штамп источника:
# в version.py поставки прописывается коммит канона, из которого она собрана.
# Тогда у любого пакета на любом контуре можно спросить, откуда он.
#
# Асимметрия ошибок: лишний шум в отчёте сборки безобиден, молчаливое
# расхождение — нет. Поэтому сборщик ругается на всё необъяснённое: файл в
# поставке вне манифеста, файл манифеста, пропавший из канона, расхождение
# при --check.
#
# Использование:
#   python -m app.scripts.build_bundle --bundle <путь> --check   # только сверка
#   python -m app.scripts.build_bundle --bundle <путь>            # синхронизация
#   python -m app.scripts.build_bundle --bundle <путь> --zip      # + пересборка архива
#   ... --sync-data      # ещё и справочники app/data/*.json (по умолчанию не трогаются)

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------------------
# Манифест поставки.
# --------------------------------------------------------------------------------------

# Модули и справочники, которые уезжают в поставку. Пути — от корня репозитория,
# одинаковые в каноне и в бандле. Всё, что лежит в app/ поставки и НЕ перечислено
# здесь, сборщик считает самодеятельностью и называет вслух.
BUNDLE_FILES: Tuple[str, ...] = (
    "app/__init__.py",
    "app/attachment_migrator.py",
    "app/color_map.py",
    "app/config.py",
    "app/confluence_loader.py",
    "app/content_extractor.py",
    "app/data/card_sections.json",
    "app/data/features.json",
    "app/data/glossary.json",
    "app/data/master_systems.json",
    "app/data/page_exclusion_rules.json",
    "app/data/services.json",
    "app/data/templates.json",
    "app/filter_all_fragments.py",
    "app/filter_approved_fragments.py",
    "app/history_cleaner.py",
    "app/image_migrator.py",
    "app/page_cache.py",
    "app/page_exclusion_filter.py",
    "app/scripts/CI/__init__.py",
    "app/scripts/CI/critic.py",
    "app/scripts/CI/critic_manual.md",
    "app/scripts/__init__.py",
    "app/scripts/apply_history.py",
    "app/scripts/dump_confluence_page.py",
    "app/scripts/migrate_colors.py",
    "app/scripts/migrate_confluence_page.py",
    "app/scripts/migrate_confluence_tree.py",
    "app/scripts/repair_export.py",
    "app/service_registry.py",
    "app/services/__init__.py",
    "app/services/template_type_analysis.py",
    "app/unapproved_wrap.py",
    "app/utils/__init__.py",
    "app/utils/style_utils.py",
    "app/version.py",
)

# Справочники: настраиваются каждой командой под себя, поэтому расхождение копий —
# норма, а не дефект (решение владельца 2026-09-05). Сборщик их не перезаписывает
# без --sync-data, но о различиях сообщает всегда. В отпечаток исходников они не
# входят — значит, по баннеру запуска различие не видно, и назвать его должен отчёт.
SOFT_FILES: Tuple[str, ...] = tuple(f for f in BUNDLE_FILES if f.startswith("app/data/"))

# Намеренные отличия закрытого контура: подстановки, применяемые при копировании.
# Каждая — с причиной; сверка учитывает их и не считает расхождением.
CONTOUR_PATCHES: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    # Confluence контура стоит за самоподписанным сертификатом.
    "app/confluence_loader.py": (
        ("verify_ssl=True", "verify_ssl=False", "самоподписанный сертификат Confluence"),
    ),
}

# Файлы, которые живут ТОЛЬКО в поставке (README, .bat, wheels, requirements) —
# канон их не знает и не трогает. Перечислены каталогами/масками для проверки
# «лишнего в app/», в саму синхронизацию не входят.
BUNDLE_OWN_PREFIXES: Tuple[str, ...] = ("wheels/", "run-", "install.bat", "README.md",
                                        "requirements.txt", ".env.example", ".git")

# В архив не кладутся служебные файлы git — они нужны репозиторию, но не аналитику.
ZIP_EXCLUDE: Tuple[str, ...] = (".gitignore", ".gitattributes")

ZIP_NAME = "confluence-tree-exporter.zip"

# Заглядывание вперёд, а не якорь конца строки: файлы канона в CRLF, и `$` после
# закрывающей кавычки не срабатывал бы — штамп «некуда ставить» на ровном месте.
_STAMP_RE = re.compile(r'^BUILD_FROM = ".*?"(?=\r?$)', re.M)


# --------------------------------------------------------------------------------------
# Преобразования при копировании.
# --------------------------------------------------------------------------------------

def apply_patches(rel: str, text: str) -> str:
    """Подстановки контура. Отсутствие исходного фрагмента — ошибка манифеста."""
    for old, new, why in CONTOUR_PATCHES.get(rel, ()):
        if old not in text:
            raise ValueError(f"{rel}: не найден фрагмент для подстановки «{old}» ({why}) — "
                             f"канон изменился, манифест устарел")
        text = text.replace(old, new)
    return text


def stamp_source(text: str, commit: str) -> str:
    """Штамп источника в version.py поставки: из какого коммита канона собрано."""
    if not _STAMP_RE.search(text):
        raise ValueError("app/version.py: нет строки BUILD_FROM — штамп ставить некуда")
    return _STAMP_RE.sub(f'BUILD_FROM = "{commit}"', text)


def strip_stamp(text: str) -> str:
    """Текст без штампа — для сверки: старый штамп это не расхождение кода."""
    return _STAMP_RE.sub('BUILD_FROM = ""', text)


def render(rel: str, canon_text: str, commit: str) -> str:
    """Каким файл должен лечь в поставку: подстановки контура + штамп источника."""
    text = apply_patches(rel, canon_text)
    if rel == "app/version.py":
        text = stamp_source(text, commit)
    return text


def read_stamp(text: str) -> str:
    m = re.search(r'^BUILD_FROM = "(.*?)"(?=\r?$)', text, re.M)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------------------
# Сверка и синхронизация.
# --------------------------------------------------------------------------------------

def eol_norm(text: str) -> str:
    """Текст без разницы в переводах строк.

    Копии исторически разъехались по CRLF/LF, а смысла в этом нет: отпечаток
    исходников нормализует переводы строк перед хешированием, Python на них
    безразличен, .gitattributes поставки запрещает конверсию. Поэтому различие
    только в окончаниях строк — не расхождение: файл не переписывается (правило
    байт-в-байт) и в отчёт не попадает.
    """
    return text.replace("\r\n", "\n")


def _read(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def extra_bundle_files(bundle: Path) -> List[str]:
    """Файлы в app/ поставки вне манифеста — ровно тот случай, ради которого всё это."""
    listed = set(BUNDLE_FILES)
    found = []
    app = bundle / "app"
    if not app.is_dir():
        return found
    for p in sorted(app.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(bundle).as_posix()
        if rel not in listed:
            found.append(rel)
    return found


def compare(canon: Path, bundle: Path, commit: str) -> Dict[str, List[str]]:
    """Сверка без записи. Возвращает разбор по видам находок."""
    report: Dict[str, List[str]] = {"нет в каноне": [], "нет в поставке": [],
                                    "расходится": [], "справочники": [],
                                    "лишнее в поставке": extra_bundle_files(bundle)}
    for rel in BUNDLE_FILES:
        src, dst = canon / rel, bundle / rel
        if not src.is_file():
            report["нет в каноне"].append(rel)
            continue
        if not dst.is_file():
            report["нет в поставке"].append(rel)
            continue
        if rel in SOFT_FILES:
            if eol_norm(_read(src)) != eol_norm(_read(dst)):
                report["справочники"].append(rel)
            continue
        want, have = render(rel, _read(src), commit), _read(dst)
        if rel == "app/version.py":
            want, have = strip_stamp(want), strip_stamp(have)
        if eol_norm(want) != eol_norm(have):
            report["расходится"].append(rel)
    return report


def sync(canon: Path, bundle: Path, commit: str, sync_data: bool) -> List[str]:
    """Разложить поставку из канона. Возвращает список изменённых файлов."""
    changed = []
    for rel in BUNDLE_FILES:
        src, dst = canon / rel, bundle / rel
        if not src.is_file():
            raise FileNotFoundError(f"{rel}: файл манифеста пропал из канона")
        if rel in SOFT_FILES and not sync_data:
            continue
        want = render(rel, _read(src), commit)
        # Идемпотентность: неизменённый файл не перезаписываем (см. правила репозитория).
        # Различие только в переводах строк изменением не считается — см. eol_norm.
        if dst.is_file() and eol_norm(_read(dst)) == eol_norm(want):
            continue
        _write(dst, want)
        changed.append(rel)
    return changed


# --------------------------------------------------------------------------------------
# Архив.
# --------------------------------------------------------------------------------------

def zip_entries(tracked: List[str]) -> List[str]:
    """Что кладём в архив: всё под контролем версий, кроме служебного git."""
    return sorted(f for f in tracked if f not in ZIP_EXCLUDE)


def _tracked_files(bundle: Path) -> List[str]:
    out = subprocess.run(["git", "ls-files"], cwd=bundle, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git ls-files в поставке не отработал: {out.stderr.strip()}")
    return out.stdout.split()


def build_zip(bundle: Path) -> Tuple[Path, int]:
    """Пересобрать архив поставки. Возвращает (путь, число файлов)."""
    entries = zip_entries(_tracked_files(bundle))
    dirs = sorted({str(Path(e).parent.as_posix()) + "/" for e in entries
                   if Path(e).parent != Path(".")})
    target = bundle / ZIP_NAME
    tmp = bundle / (ZIP_NAME + ".new")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for d in dirs:
            z.writestr(zipfile.ZipInfo(d), b"")
        for e in entries:
            z.write(bundle / e, e)
    shutil.move(str(tmp), str(target))
    return target, len(entries)


# --------------------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------------------

def canon_commit(canon: Path) -> str:
    """Короткий хеш канона + пометка о незакоммиченных правках.

    Смотрим ТОЛЬКО файлы манифеста: в рабочем каталоге канона всегда лежит
    несвязанный untracked-мусор (рабочие заметки, выгрузки), и по нему сборка
    метилась бы +dirty всегда — признак, который срабатывает постоянно, ничего
    не значит. Помечать надо ровно то, что уехало в пакет неподтверждённым.
    """
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          cwd=canon, capture_output=True, text=True)
    if head.returncode != 0:
        return "unknown"
    commit = head.stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *BUNDLE_FILES],
                           cwd=canon, capture_output=True, text=True)
    return commit + ("+dirty" if dirty.stdout.strip() else "")


def _print_report(report: Dict[str, List[str]]) -> None:
    for kind in ("нет в каноне", "нет в поставке", "расходится", "лишнее в поставке"):
        for rel in report[kind]:
            print(f"  ✗ {kind}: {rel}")
    for rel in report["справочники"]:
        print(f"  ⚠ справочник различается (в отпечаток не входит): {rel}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Сборка поставки confluence-tree-exporter из канона")
    parser.add_argument("--bundle", required=True, help="путь к репозиторию поставки")
    parser.add_argument("--check", action="store_true",
                        help="только сверка, без записи (код 1 при расхождении)")
    parser.add_argument("--sync-data", action="store_true",
                        help="переносить и справочники app/data/*.json")
    parser.add_argument("--zip", action="store_true", help="пересобрать архив поставки")
    args = parser.parse_args(argv)

    canon = Path(__file__).resolve().parents[2]
    bundle = Path(os.path.expandvars(args.bundle)).expanduser().resolve()
    if not (bundle / "app").is_dir():
        print(f"ОШИБКА: {bundle} не похож на поставку (нет каталога app/)", file=sys.stderr)
        return 2

    commit = canon_commit(canon)
    print(f"канон: {canon} ({commit})")
    print(f"поставка: {bundle}")

    if args.check:
        report = compare(canon, bundle, commit)
        hard = sum(len(report[k]) for k in
                   ("нет в каноне", "нет в поставке", "расходится", "лишнее в поставке"))
        _print_report(report)
        version_py = bundle / "app/version.py"
        stamp = (read_stamp(_read(version_py)) if version_py.is_file() else "") or "не проставлен"
        print(f"штамп источника в поставке: {stamp}")
        print("сверка: расхождений нет" if hard == 0 else f"сверка: расхождений {hard}")
        return 1 if hard else 0

    changed = sync(canon, bundle, commit, args.sync_data)
    for rel in changed:
        print(f"  обновлён: {rel}")
    print(f"синхронизировано файлов: {len(changed)}")
    _print_report({**compare(canon, bundle, commit), "расходится": []})

    if args.zip:
        target, n = build_zip(bundle)
        size = target.stat().st_size / 1048576
        print(f"архив пересобран: {target.name}, файлов {n}, {size:.2f} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
