#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка карточек экранных форм на формат create-screen-form (anti-dump).

Только чтение docs; отчёт — в ``--out``. Код выхода 2 при любой находке P0.

Пример::

    python _meta/tools/validate_screen_forms.py --docs <корень комплекта> --out reports/validate-scr.md
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

SCRIPT_REF = "_meta/tools/validate_screen_forms.py"

FRONT_TYPE_RE = re.compile(r"^type:\s*screen-form\s*$", re.M)
ID_RE = re.compile(r"^id:\s*(\S+)", re.M)
TITLE_RE = re.compile(r"^title:\s*(.+)$", re.M)

CONFLUENCE_LAYOUT_HEADINGS = (
    r"#\s*Общие требования к ЭФ",
    r"#\s*Описание элементов ЭФ",
    r"#\s*Описание кнопок ЭФ",
    r"#\s*Описание ЭФ\b",
)
CONFLUENCE_LAYOUT_RE = re.compile("|".join(CONFLUENCE_LAYOUT_HEADINGS), re.M)
HAS_PURPOSE_RE = re.compile(r"^##\s+1\.\s*Назначение\b", re.M)
SKILL_MARKERS_RE = re.compile(r"\b(?:FLD-|EV-|B-)\d")
CONFLUENCE_HREF_RE = re.compile(
    r"\]\("
    r"(?:[^)]*(?:\.\./)+\[|"
    r"[^)]*/download/attachments/|"
    r"[^)]*\[[A-ZА-Я0-9_][^\]]*\])"
    r"[^)]*\)"
)
TITLE_SELF_LINK_RE = re.compile(r"\[SCR-[^\]]+\]\([^)]+\)")


def collect_scr_files(docs_roots: list[Path]) -> list[tuple[Path, Path]]:
    """Leaf-карточки SCR (не README / не *-000)."""
    out: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for root in docs_roots:
        if not root.exists():
            continue
        for f in root.rglob("*.md"):
            if "screen-form" not in str(f).replace("\\", "/"):
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if not FRONT_TYPE_RE.search(text[:800]):
                continue
            id_m = ID_RE.search(text[:800])
            sid = id_m.group(1) if id_m else ""
            if sid.endswith("-000") or f.name.lower() == "readme.md":
                continue
            rp = f.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            out.append((f, root))
    return out


def analyze_file(path: Path, docs_root: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        rel = str(path.relative_to(docs_root)).replace("\\", "/")
    except ValueError:
        rel = path.name

    issues: list[dict] = []
    has_purpose = bool(HAS_PURPOSE_RE.search(text))
    layout_hit = CONFLUENCE_LAYOUT_RE.search(text)

    if layout_hit and not has_purpose:
        issues.append(
            {
                "file": rel,
                "code": "confluence_layout",
                "severity": "P0",
                "detail": (
                    f"Confluence-layout заголовок «{layout_hit.group(0).strip()}» "
                    f"без «## 1. Назначение»"
                ),
            }
        )

    if not SKILL_MARKERS_RE.search(text):
        issues.append(
            {
                "file": rel,
                "code": "no_skill_markers",
                "severity": "P0",
                "detail": "нет маркеров FLD- / EV- / B- (формат create-screen-form)",
            }
        )

    hrefs = CONFLUENCE_HREF_RE.findall(text)
    if hrefs:
        sample = hrefs[0][:120]
        issues.append(
            {
                "file": rel,
                "code": "confluence_href",
                "severity": "P0",
                "detail": (
                    f"сырой Confluence path в ссылке ({len(hrefs)} шт.), "
                    f"пример: {sample}"
                ),
            }
        )

    title_m = TITLE_RE.search(text[:800])
    if title_m and TITLE_SELF_LINK_RE.search(title_m.group(1)):
        issues.append(
            {
                "file": rel,
                "code": "title_self_link",
                "severity": "P1",
                "detail": f"title — self-link: {title_m.group(1).strip()[:80]}",
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
        "title: Screen-form skill-shape validation",
        f"date: {date.today().isoformat()}",
        "---",
        "",
        "# Валидация экранных форм (create-screen-form)",
        "",
        f"Скрипт: `{SCRIPT_REF}`. Дата: {date.today().isoformat()}.",
        "",
        "## Сводка",
        "",
        "| Метрика | Значение |",
        "| - | - |",
        f"| docs roots | {roots_str} |",
        f"| Карточек SCR (leaf) | {file_count} |",
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
    lines += [
        "",
        "## Интерпретация",
        "",
        "- **PASS** — leaf SCR в формате скилла (§1–§8, FLD/EV/B, без Confluence-path).",
        "- **FAIL** — dump или частичный reverse; требуется доработка карточек.",
        "",
    ]
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
    files = collect_scr_files(docs_roots)
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
