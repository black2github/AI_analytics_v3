# app/scripts/CI/structural_facts.py
#
# Сторож реестра структурных фактов канона (решение владельца 2026-10-06:
# один дом у факта, сигнатура, список потребителей под сторожем).
#
# Повод: при смене модели «контракты API живут в docs/api/» руководитель
# насчитал десять мест, поиск по тексту дал около тридцати. Факт живёт
# в каноне не одной нормой, а десятками формулировок; где ещё он записан,
# узнаётся только поиском — и поиск делают не всегда. Этот сторож делает
# поиск всегда: реестр `_meta/structural-facts.md` держит у каждого
# факта дом, текстовые сигнатуры и список файлов-потребителей, а
# проверка ищет сигнатуры по всему канону и сверяет с реестром.
#
# Реестр существует ТОЛЬКО со сторожем: список потребителей не ведётся
# руками, а проверяется полнотекстовым поиском при каждом прогоне,
# поэтому полон по построению. Частичность допустима: факт вне реестра
# — как раньше (поиск руками), факт в реестре защищён целиком.
#
# Формат записи реестра (markdown, разбирается этим модулем):
#
#   ## SF-01. <название факта>
#   - Факт: <формулировка в одну-две строки>
#   - Дом: <путь от корня репозитория> [; <путь>]
#   ```сигнатуры
#   api-specification
#   docs/api/
#   ```
#   ```потребители
#   _meta/ai-sdlc.md
#   _meta/skills/create-docs-readme.md
#   ```
#   ```вне-учёта
#   _meta/references/*
#   ```
#
# Сигнатура — буквальная подстрока (регистр важен), по одной в строке.
# Потребители и дом — пути от корня репозитория. «Вне учёта» — шаблоны
# fnmatch для файлов, где сигнатура законна, но файл не потребитель
# нормы (чужие материалы, снимки).
#
# Что проверяется, по каждому факту:
#   • файл в зоне сканирования с сигнатурой, не названный ни домом, ни
#     потребителем, ни «вне учёта» — ⚠ «вне реестра» (тот самый
#     тридцать первый файл);
#   • дом или потребитель, в котором ни одной сигнатуры нет, — ⚠
#     «сигнатур больше не содержит» (запись протухла);
#   • дом или потребитель, которого нет на диске, — ⚠ «файла нет».
# Сторож не отличает норму от упоминания — это ревью; он лишь не даёт
# местам размножаться незаметно.
#
# Зона сканирования: `_meta/`, `AGENTS.md`, `README.md`, `.cursor/`,
# `.claude/`; текстовые файлы (.md .mdc .py .json .bat .yaml .yml .txt).
# Комплекты (`output/`, `sources/`) — не нормы, не сканируются.
#
# Использование:
#   python -m app.scripts.CI.structural_facts --repo <корень канона> [--strict]
# Код возврата: 0 — ⚠ нет (или не --strict); 1 — есть ⚠ при --strict;
# 2 — реестр не найден или не разобран.
import argparse
import fnmatch
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REGISTRY_REL = Path("_meta") / "structural-facts.md"
SCAN_ROOTS = ("_meta", ".cursor", ".claude")
SCAN_FILES = ("AGENTS.md", "README.md")
TEXT_SUFFIXES = {".md", ".mdc", ".py", ".json", ".bat", ".yaml", ".yml", ".txt"}

_FACT_HEAD_RE = re.compile(r"^##\s+(SF-\d+)\.\s*(.+?)\s*$", re.M)
_HOME_RE = re.compile(r"^-\s*Дом:\s*(.+?)\s*$", re.M)
_BLOCK_RE = re.compile(r"^```(сигнатуры|потребители|вне-учёта)[ \t]*\n(.*?)^```[ \t]*$",
                       re.M | re.S)


@dataclass
class Fact:
    sid: str
    title: str
    homes: List[str] = field(default_factory=list)
    signatures: List[str] = field(default_factory=list)
    consumers: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)


def parse_registry(text: str) -> List[Fact]:
    """Записи реестра по заголовкам `## SF-NN.`; блоки — до следующей записи."""
    heads = list(_FACT_HEAD_RE.finditer(text))
    facts: List[Fact] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end]
        f = Fact(sid=m.group(1), title=m.group(2))
        hm = _HOME_RE.search(body)
        if hm:
            f.homes = [_strip_path(p) for p in hm.group(1).split(";") if p.strip()]
        for bm in _BLOCK_RE.finditer(body):
            items = [ln.strip() for ln in bm.group(2).splitlines() if ln.strip()
                     and not ln.strip().startswith("#")]
            kind = bm.group(1)
            if kind == "сигнатуры":
                f.signatures = items
            elif kind == "потребители":
                f.consumers = [_strip_path(p) for p in items]
            else:
                f.excluded = [_strip_path(p) for p in items]
        facts.append(f)
    return facts


def _strip_path(p: str) -> str:
    """Путь из реестра: без обратных кавычек, в прямых слэшах; хвост
    в скобках («(§2, §5.2)») — пояснение, не часть пути."""
    p = p.strip().split(" (", 1)[0].split("(", 1)[0].strip().strip("`").strip()
    return p.replace("\\", "/")


def scan_files(repo: Path) -> List[Path]:
    out: List[Path] = []
    for name in SCAN_FILES:
        p = repo / name
        if p.is_file():
            out.append(p)
    for root in SCAN_ROOTS:
        d = repo / root
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES \
                    and "__pycache__" not in p.parts:
                out.append(p)
    return out


def _rel(p: Path, repo: Path) -> str:
    return p.relative_to(repo).as_posix()


def _excluded(rel: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) or rel.startswith(pat.rstrip("*"))
               for pat in patterns)


def check(repo: Path, registry: Optional[Path] = None
          ) -> Tuple[List[str], bool]:
    """(строки отчёта, ok). ok=False — есть хотя бы одно ⚠."""
    reg = registry or repo / REGISTRY_REL
    if not reg.is_file():
        return [f"⚠ реестр структурных фактов: {reg.as_posix()} не найден"], False
    facts = parse_registry(reg.read_text(encoding="utf-8-sig"))
    if not facts:
        return [f"⚠ реестр структурных фактов: записей `## SF-NN.` не найдено"], False
    files = [p for p in scan_files(repo) if p.resolve() != reg.resolve()]
    texts: Dict[str, str] = {}
    for p in files:
        try:
            texts[_rel(p, repo)] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    lines: List[str] = []
    ok = True
    for f in facts:
        if not f.signatures:
            lines.append(f"⚠ {f.sid} «{f.title}»: сигнатуры не заданы — проверять нечего")
            ok = False
            continue
        listed = set(f.homes) | set(f.consumers)
        hits = {rel for rel, t in texts.items() if any(s in t for s in f.signatures)}
        unlisted = sorted(rel for rel in hits
                          if rel not in listed and not _excluded(rel, f.excluded))
        stale = sorted(rel for rel in listed if rel in texts and rel not in hits)
        missing = sorted(rel for rel in listed if rel not in texts
                         and not (repo / rel).is_file())
        if not (unlisted or stale or missing):
            counted = [rel for rel in hits if not _excluded(rel, f.excluded)]
            lines.append(f"✓ {f.sid} «{f.title}»: сигнатуры в {len(counted)} "
                         f"файлах, все в реестре (дом {len(f.homes)}, "
                         f"потребителей {len(f.consumers)})")
            continue
        ok = False
        for rel in unlisted:
            sig = next(s for s in f.signatures if s in texts[rel])
            lines.append(f"⚠ {f.sid}: сигнатура `{sig}` в файле {rel} — файла нет в "
                         "списке потребителей: внести в реестр либо убрать "
                         "упоминание (норма живёт в доме)")
        for rel in stale:
            lines.append(f"⚠ {f.sid}: потребитель {rel} сигнатур больше не содержит — "
                         "снять из реестра")
        for rel in missing:
            lines.append(f"⚠ {f.sid}: в реестре назван файл {rel}, которого нет")
    return lines, ok


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Сторож реестра структурных фактов канона "
                    "(_meta/structural-facts.md): сигнатуры фактов ищутся по "
                    "канону и сверяются со списком потребителей.")
    ap.add_argument("--repo", required=True, help="корень репозитория канона")
    ap.add_argument("--strict", action="store_true",
                    help="код возврата 1 при любом ⚠")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    if not (repo / REGISTRY_REL).is_file():
        print(f"отказ: {REGISTRY_REL.as_posix()} не найден в {repo}")
        return 2
    lines, ok = check(repo)
    for ln in lines:
        print(ln)
    return 0 if ok or not args.strict else 1


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
