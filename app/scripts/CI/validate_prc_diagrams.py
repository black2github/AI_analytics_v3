#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка PlantUML activity-диаграмм в карточках процессов (prc-/proc-*.md).

Выявляет пустые if/else-развилки (типичный артефакт миграции).
Только чтение docs; отчёт в ``--out``. Код выхода 2 при находках P0.

Пример::

    python _meta/tools/validate_prc_diagrams.py --docs <корень комплекта> --out reports/validate-prc.md
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

SCRIPT_REF = "_meta/tools/validate_prc_diagrams.py"

PLANTUML_RE = re.compile(r"```plantuml\s*\n(.*?)```", re.S | re.I)
ACTION_OR_STOP = re.compile(r"(?:^|\n)\s*(?::[^;]+;|stop)\b", re.M)


def collect_prc_files(docs_roots: list[Path]) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for root in docs_roots:
        if not root.exists():
            continue
        for pat in ("**/process/prc-*.md", "**/process/proc-*.md", "**/prc-*.md"):
            for f in root.glob(pat):
                if not f.is_file():
                    continue
                rp = f.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                files.append((f, root))
    return files


def branch_has_action(branch: str) -> bool:
    if not branch or not branch.strip():
        return False
    return bool(ACTION_OR_STOP.search(branch))


def find_stub_empty_ifs(body: str) -> list[str]:
    """P0: if/else, где обе ветки без action/stop (stub gateway)."""
    findings: list[str] = []
    for m in re.finditer(
        r"if\s*\(([^)]*)\)\s*then\s*\(([^)]*)\)\s*\n\s*else\s*\(([^)]*)\)\s*\n",
        body,
    ):
        start = m.start()
        rest = body[m.end() :]
        # endif с отступом (развилка внутри repeat / вложенная): без [ \t]* не находился,
        # тело else считалось пустым — ложный P0 (PROC-032 КК, 2026-11-01)
        end_m = re.search(r"(?:^|\n)[ \t]*endif\b", rest)
        between = rest[: end_m.start()] if end_m else ""
        if not between.strip():
            findings.append(f"stub_empty_if: if ({m.group(1).strip()})")
            continue
        else_body = between
        then_body = ""
        if not branch_has_action(then_body) and not branch_has_action(else_body):
            if not re.search(r"(?:^|\n)\s*(?::|stop|if |switch )", else_body):
                findings.append(f"stub_empty_if: if ({m.group(1).strip()})")

    for m in re.finditer(
        r"if\s*\(([^)]*)\)\s*then\s*\(([^)]*)\)\s*\n(?:[ \t]*\n)*"
        r"else\s*\(([^)]*)\)\s*\n(?:[ \t]*\n)*endif",
        body,
    ):
        label = m.group(1).strip()
        msg = f"stub_empty_if: if ({label})"
        if msg not in findings:
            findings.append(msg)

    return findings


def find_broken_action_nl(body: str) -> list[str]:
    findings: list[str] = []
    for m in re.finditer(r":([^;\n]+)\n([^:;\n@][^;]*);", body):
        findings.append(f"broken_action_nl: :{m.group(1)[:40]}…")
    return findings


def analyze_file(path: Path, docs_root: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        rel = str(path.relative_to(docs_root)).replace("\\", "/")
    except ValueError:
        rel = path.name

    issues: list[dict] = []
    blocks = PLANTUML_RE.findall(text)
    if not blocks and "@startuml" not in text:
        issues.append(
            {
                "file": rel,
                "code": "no_plantuml",
                "severity": "P0",
                "detail": "нет блока ```plantuml / @startuml",
            }
        )
        return issues

    bodies = blocks if blocks else [text]
    for bi, body in enumerate(bodies):
        prefix = f"diag#{bi + 1} " if len(bodies) > 1 else ""
        for msg in find_stub_empty_ifs(body):
            issues.append(
                {
                    "file": rel,
                    "code": "stub_empty_if",
                    "severity": "P0",
                    "detail": prefix + msg,
                }
            )
        for msg in find_broken_action_nl(body):
            issues.append(
                {
                    "file": rel,
                    "code": "broken_action_nl",
                    "severity": "P1",
                    "detail": prefix + msg,
                }
            )
        if "ActivityBackgroundColor" not in body or "ActivityBorderColor" not in body:
            issues.append(
                {
                    "file": rel,
                    "code": "no_skinparam",
                    "severity": "P1",
                    "detail": prefix + "нет skinparam ActivityBackgroundColor/BorderColor",
                }
            )
    return issues


def write_report(
    out: Path, docs_roots: list[Path], issues: list[dict], file_count: int
) -> None:
    by_sev: dict[str, list[dict]] = defaultdict(list)
    for i in issues:
        by_sev[i["severity"]].append(i)
    p0 = len(by_sev["P0"])
    p1 = len(by_sev["P1"])
    roots_str = ", ".join(str(p) for p in docs_roots)
    lines = [
        "---",
        "title: PRC diagram validation",
        f"date: {date.today().isoformat()}",
        "---",
        "",
        "# Валидация PlantUML activity в процессах",
        "",
        f"Скрипт: `{SCRIPT_REF}`. Дата: {date.today().isoformat()}.",
        "",
        "## Сводка",
        "",
        "| Метрика | Значение |",
        "| - | - |",
        f"| docs roots | {roots_str} |",
        f"| Файлов prc/proc | {file_count} |",
        f"| P0 | {p0} |",
        f"| P1 | {p1} |",
        f"| Вердикт | {'PASS' if p0 == 0 else 'FAIL'} |",
        "",
        "## Находки",
        "",
        "| Severity | Code | Файл | Деталь |",
        "| - | - | - | - |",
    ]
    if not issues:
        lines.append("| — | — | — | нет |")
    else:
        for sev in ("P0", "P1"):
            for i in by_sev[sev]:
                detail = i["detail"].replace("|", "\\|")
                lines.append(
                    f"| {i['severity']} | `{i['code']}` | `{i['file']}` | {detail} |"
                )
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--docs",
        type=Path,
        nargs="+",
        required=True,
        help="Корень(и) docs/ комплекта",
    )
    ap.add_argument("--out", type=Path, required=True, help="Путь к markdown-отчёту")
    args = ap.parse_args()

    docs_roots = [p.resolve() for p in args.docs]
    for root in docs_roots:
        if not root.is_dir():
            print(f"не каталог: {root}", file=sys.stderr)
            return 1
    files = collect_prc_files(docs_roots)
    all_issues: list[dict] = []
    for f, root in files:
        all_issues.extend(analyze_file(f, root))

    out = args.out
    write_report(out, docs_roots, all_issues, len(files))
    p0 = sum(1 for i in all_issues if i["severity"] == "P0")
    print(
        f"wrote {out}: files={len(files)} P0={p0} "
        f"P1={sum(1 for i in all_issues if i['severity'] == 'P1')}"
    )
    return 2 if p0 else 0


if __name__ == "__main__":
    sys.exit(main())
