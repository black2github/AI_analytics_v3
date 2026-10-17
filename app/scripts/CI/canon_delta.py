# app/scripts/CI/canon_delta.py
#
# Утилита ВЛАДЕЛЬЦА канона: дельта среза для ревью чужого вливания
# (решение владельца 2026-10-15 после инцидента 14.10 — слияние ветки
# коллеги разрешило конфликт в _meta/tools/link_debts.py «в пользу своей»
# и молча убрало формат долга без цели; заодно из шаблона фичи исчез
# раздел «Нефункциональные требования»). Ни accept_canon, ни сторож
# структурных фактов такого не показывают: accept_canon — команда
# синхронизации команд с контрактом «одна строка ✓», сторож ловит только
# зарегистрированные факты. Дельта среза — отдельная утилита владельца,
# в протоколах команд не появляется.
#
# Что печатает между двумя ревизиями канона по зоне (по умолчанию
# _meta, AGENTS.md, README.md, .cursor, .claude):
#   1. файлы: удалённые, переименованные, добавленные, изменённые;
#   2. удалённые заголовки разделов (строки `#…`) в изменённых .md —
#      раздел, исчезнувший из шаблона/скилла/гида, виден сразу;
#      добавленные заголовки — к сведению;
#   3. изменённые утилиты _meta/tools/*.py с числом строк +/−: любая
#      правка прибора вне репозитория прибора — повод сверить копию
#      с requirements-analyzer-v3 (tests живут там);
#   4. итог «к ревью: …» — счётчики удалений и правок утилит.
# Это не вердикт: удаление может быть правильным (перенос раздела в
# другой дом). Ключ --strict даёт код возврата 1, если есть что смотреть
# (удалённые файлы/заголовки или правки утилит), — для своего чек-листа
# перед MR.
#
# Запуск: python canon_delta.py --repo <клон канона> <старая ревизия> [<новая, по умолчанию HEAD>]
#         [--path <путь> …] [--strict]
# Ревизии — любые ссылки git (хэш среза из профиля стенда, origin/master,
# ветка MR). Сетевых команд не выполняет: fetch — отдельное действие.

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))  # каталог утилит прибора
try:
    from kitcheck.fence import blocks, code_flags  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.fence import blocks, code_flags  # type: ignore  # noqa: E402

DEFAULT_PATHS = ("_meta", "AGENTS.md", "README.md", ".cursor", ".claude")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def headings(text: str) -> Tuple[List[str], List[str]]:
    """Заголовки markdown с уровнем (`## Имя`): (разделы документа,
    заголовки внутри блоков кода). Второй список — структура образца:
    шаблоны держат тело карточки в ````markdown, и раздел, исчезнувший
    из образца (14.10 — «Нефункциональные требования» шаблона фичи),
    так же важен, как раздел самого документа. Границы блоков — общее
    правило прибора (kitcheck/fence.py): вложенные блоки (```gherkin
    внутри ````markdown) закрываются только ограждением того же вида и
    не короче (CommonMark)."""
    outside: List[str] = []
    inside: List[str] = []
    lines = [ln.rstrip("\r") for ln in text.splitlines()]
    code = code_flags(lines)
    fences = set()
    for b in blocks(lines):
        fences.add(b.start)
        if b.closed:
            fences.add(b.end)
    for k, ln in enumerate(lines):
        if k in fences:
            continue
        m = _HEADING_RE.match(ln)
        if m:
            (inside if code[k] else outside).append(f"{m.group(1)} {m.group(2)}")
    return outside, inside


def _show(root: Path, rev: str, path: str) -> str:
    try:
        return _git(root, "show", f"{rev}:{path}")
    except RuntimeError:
        return ""


def delta(root: Path, old: str, new: str = "HEAD",
          paths: Tuple[str, ...] = DEFAULT_PATHS) -> Tuple[List[str], dict]:
    """Строки отчёта и сводка: removed_files, renamed, added, modified,
    removed_headings {файл: [заголовки]}, added_headings, tools {файл: (+, −)}."""
    status = _git(root, "diff", "--name-status", "-M", f"{old}..{new}", "--", *paths)
    removed: List[str] = []
    renamed: List[Tuple[str, str]] = []
    added: List[str] = []
    modified: List[str] = []
    for ln in status.splitlines():
        parts = ln.split("\t")
        if not parts or not parts[0]:
            continue
        code = parts[0][0]
        if code == "D":
            removed.append(parts[1])
        elif code == "R":
            renamed.append((parts[1], parts[2]))
        elif code == "A":
            added.append(parts[1])
        elif code == "M":
            modified.append(parts[1])
    numstat: Dict[str, Tuple[int, int]] = {}
    for ln in _git(root, "diff", "--numstat", f"{old}..{new}", "--", *paths).splitlines():
        p = ln.split("\t")
        if len(p) == 3 and p[0].isdigit() and p[1].isdigit():
            numstat[p[2]] = (int(p[0]), int(p[1]))

    removed_h: Dict[str, List[str]] = {}
    removed_sample_h: Dict[str, List[str]] = {}
    added_h: Dict[str, List[str]] = {}
    for f in modified + [n for _o, n in renamed]:
        if not f.endswith(".md"):
            continue
        old_name = next((o for o, n in renamed if n == f), f)
        oh, oh_in = headings(_show(root, old, old_name))
        nh, nh_in = headings(_show(root, new, f))
        gone = [h for h in oh if h not in nh]
        gone_in = [h for h in oh_in if h not in nh_in and h not in nh]
        came = [h for h in nh if h not in oh]
        if gone:
            removed_h[f] = gone
        if gone_in:
            removed_sample_h[f] = gone_in
        if came:
            added_h[f] = came
    tools: Dict[str, Tuple[int, int]] = {
        f: numstat.get(f, (0, 0)) for f in modified
        if f.startswith("_meta/tools/") and f.endswith(".py")}

    rep: List[str] = [f"Дельта среза канона {old} → {new} (зона: {', '.join(paths)})"]
    rep.append("")
    rep.append("## Файлы")
    if removed:
        rep.append(f"- удалено ×{len(removed)}:")
        rep += [f"  - {f}" for f in removed]
    if renamed:
        rep.append(f"- переименовано ×{len(renamed)}:")
        rep += [f"  - {o} → {n}" for o, n in renamed]
    rep.append(f"- добавлено ×{len(added)}" + (": " + ", ".join(added) if added else ""))
    rep.append(f"- изменено ×{len(modified)}" + (": " + ", ".join(modified) if modified else ""))
    rep.append("")
    rep.append("## Удалённые заголовки разделов (изменённые .md)")
    if removed_h:
        for f, hs in removed_h.items():
            rep.append(f"- {f}:")
            rep += [f"  - {h}" for h in hs]
    else:
        rep.append("- нет")
    rep.append("")
    rep.append("## Удалённые заголовки в блоках-образцах (структура шаблона)")
    if removed_sample_h:
        for f, hs in removed_sample_h.items():
            rep.append(f"- {f}:")
            rep += [f"  - {h}" for h in hs]
    else:
        rep.append("- нет")
    if added_h:
        rep.append("")
        rep.append("## Добавленные заголовки (к сведению)")
        for f, hs in added_h.items():
            rep.append(f"- {f}: " + "; ".join(hs))
    rep.append("")
    rep.append("## Утилиты _meta/tools (сверить копию с репозиторием прибора)")
    if tools:
        for f, (plus, minus) in tools.items():
            rep.append(f"- {f}: +{plus} −{minus}")
    else:
        rep.append("- изменений нет")
    n_del_h = sum(len(v) for v in removed_h.values())
    n_del_s = sum(len(v) for v in removed_sample_h.values())
    attention = len(removed) + len(renamed) + n_del_h + n_del_s + len(tools)
    rep.append("")
    rep.append(f"ИТОГ к ревью: удалённых файлов {len(removed)}, переименованных {len(renamed)}, "
               f"удалённых заголовков {n_del_h} (в образцах {n_del_s}), правок утилит {len(tools)}"
               + (" — есть что смотреть" if attention else " — удалений и правок прибора нет"))
    summary = {"removed_files": removed, "renamed": renamed, "added": added,
               "modified": modified, "removed_headings": removed_h,
               "removed_sample_headings": removed_sample_h,
               "added_headings": added_h, "tools": tools, "attention": attention}
    return rep, summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Дельта среза канона между двумя ревизиями — для ревью владельца")
    ap.add_argument("old", help="старая ревизия (хэш среза, origin/master, ветка)")
    ap.add_argument("new", nargs="?", default="HEAD", help="новая ревизия (по умолчанию HEAD)")
    ap.add_argument("--repo", type=Path, default=Path("."), help="корень клона канона")
    ap.add_argument("--path", action="append", default=None,
                    help="путь зоны (можно несколько; по умолчанию _meta, AGENTS.md, "
                         "README.md, .cursor, .claude)")
    ap.add_argument("--strict", action="store_true",
                    help="код возврата 1, если есть удаления или правки утилит")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    try:
        rep, summary = delta(a.repo.resolve(), a.old, a.new,
                             tuple(a.path) if a.path else DEFAULT_PATHS)
    except RuntimeError as e:
        print(f"✗ {e}")
        return 2
    for ln in rep:
        print(ln)
    return 1 if (a.strict and summary["attention"]) else 0


if __name__ == "__main__":
    sys.exit(main())
