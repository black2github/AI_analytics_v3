# app/scripts/dev/golden_master.py
"""Эталон отчётов прибора для рефакторинга без изменения функционала
(план «Прибор — анализ структуры и план рефакторинга», этап 0, 2026-10-17).

Инвариант рефакторинга: на одних и тех же входах полный вывод каждой утилиты
прибора — до байта тот же. Входы замораживаются снимком (локальные клоны
комплектов на зафиксированных коммитах), прибор берётся из указанного
каталога (`main` или ветка рефакторинга), вывод сравнивается побайтно после
замены путей прибора и снимка метками.

    python golden_master.py snapshot --root <каталог эталона>
    python golden_master.py run --root <каталог эталона> --ci <каталог прибора> --out <имя прогона> [--seed N]
    python golden_master.py diff --root <каталог эталона> <прогон A> <прогон B>
    python golden_master.py tests-diff <junit эталона> <junit прогона>

Утилита для разработки прибора; в канон не копируется.
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

PY = sys.executable

# Комплекты: репозиторий-источник, каталог комплекта, выгрузка (относительно корня клона)
KITS: Dict[str, Dict[str, Optional[str]]] = {
    "kk": {"repo": "C:/doc-as-code/EAS/src-business-cards", "docs": "docs", "sources": "sources"},
    "lkmp": {"repo": "C:/doc-as-code/EAS/src-lk-mp", "docs": "docs", "sources": "sources"},
    "ul": {"repo": "C:/doc-as-code/EAS/src-common-dictionary", "docs": "output/authorized-person",
           "sources": "sources/authorized-person/confluence"},
    "stand": {"repo": "C:/doc-as-code/ext-sandbox/src-business-cards", "docs": "docs",
              "sources": "confluence"},
    "etalon": {"repo": "C:/doc-as-code/ext-sandbox/docs-o2new", "docs": "output/open-add-account/docs",
               "sources": None},
    "onbv": {"repo": "C:/doc-as-code/EAS/src-onb-v", "docs": ".", "sources": "confluence"},
}
CANON_KIT = "etalon"  # клон канона — он же источник для утилит уровня канона


def snapshot(root: Path) -> None:
    inputs = root / "inputs"
    if inputs.exists():
        sys.exit(f"снимок уже есть: {inputs} — новый снимок только в пустой каталог")
    inputs.mkdir(parents=True)
    manifest = {}
    for name, k in KITS.items():
        dest = inputs / name
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", k["repo"], str(dest)], check=True)
        head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
        manifest[name] = {**k, "commit": head}
        print(f"{name}: {k['repo']} @ {head[:9]}")
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                        encoding="utf-8")


def commands(root: Path, ci: Path, work: Path) -> List[Dict]:
    """(имя, cwd, argv) прогонов. Порядок фиксирован."""
    inputs = root / "inputs"
    out: List[Dict] = []
    for name, k in KITS.items():
        base = inputs / name
        docs = base / k["docs"] if k["docs"] != "." else base
        src = base / k["sources"] if k["sources"] else None
        sargs = ["--sources", str(src)] if src else []
        out.append({"name": f"{name}__selfcheck", "cwd": base,
                    "argv": [PY, str(ci / "selfcheck.py"), "--docs", str(docs), *sargs]})
        out.append({"name": f"{name}__selfcheck_strict", "cwd": base,
                    "argv": [PY, str(ci / "selfcheck.py"), "--docs", str(docs), *sargs, "--strict"]})
        matrix = docs / "traceability-matrix.md"
        if matrix.is_file():
            out.append({"name": f"{name}__link_debts", "cwd": base,
                        "argv": [PY, str(ci / "link_debts.py"), "--matrix", str(matrix), "--docs", str(docs)]})
            out.append({"name": f"{name}__matrix_sync", "cwd": base,
                        "argv": [PY, str(ci / "matrix_sync.py"), "--docs", str(docs)]})
        if src:
            out.append({"name": f"{name}__source_coverage", "cwd": base,
                        "argv": [PY, str(ci / "source_coverage.py"), "--sources", str(src), "--output", str(docs)]})
        out.append({"name": f"{name}__transfer_gate", "cwd": base,
                    "argv": [PY, str(ci / "transfer_gate.py"), "--src", str(base),
                             "--docs", k["docs"], "--no-validator", "--log", *sargs]})
    # редкие ключи: файл отчёта и сравнение с ним, журнал, строгие профили, JSON
    kk = inputs / "kk"
    kk_docs, kk_src = kk / "docs", kk / "sources"
    out.append({"name": "kk__selfcheck_out", "cwd": kk,
                "argv": [PY, str(ci / "selfcheck.py"), "--docs", str(kk_docs), "--sources", str(kk_src),
                         "--out", str(work / "kk_report.txt")],
                "extra_file": work / "kk_report.txt"})
    out.append({"name": "kk__selfcheck_baseline", "cwd": kk,
                "argv": [PY, str(ci / "selfcheck.py"), "--docs", str(kk_docs), "--sources", str(kk_src),
                         "--strict", "--baseline", str(work / "kk_report.txt")]})
    lk = inputs / "lkmp"
    out.append({"name": "lkmp__selfcheck_journal", "cwd": lk,
                "argv": [PY, str(ci / "selfcheck.py"), "--docs", str(lk / "docs"), "--sources", str(lk / "sources"),
                         "--journal", str(work / "journal.md")],
                "extra_file": work / "journal.md"})
    out.append({"name": "kk__link_debts_strict", "cwd": kk,
                "argv": [PY, str(ci / "link_debts.py"), "--matrix", str(kk_docs / "traceability-matrix.md"),
                         "--docs", str(kk_docs), "--strict"]})
    out.append({"name": "kk__source_coverage_strict", "cwd": kk,
                "argv": [PY, str(ci / "source_coverage.py"), "--sources", str(kk_src),
                         "--output", str(kk_docs), "--strict"]})
    out.append({"name": "lkmp__transfer_gate_json_report", "cwd": lk,
                "argv": [PY, str(ci / "transfer_gate.py"), "--src", str(lk), "--docs", "docs",
                         "--no-validator", "--strict", "--json", "--report", str(work / "gate.md")],
                "extra_file": work / "gate.md"})
    canon = inputs / CANON_KIT
    out.append({"name": "canon__structural_facts", "cwd": canon,
                "argv": [PY, str(ci / "structural_facts.py"), "--repo", str(canon)]})
    out.append({"name": "canon__passport_build", "cwd": canon,
                "argv": [PY, str(ci / "passport_sync.py"), "--canon", str(canon),
                         "--build", str(work / "passport.yaml")],
                "extra_file": work / "passport.yaml"})
    return out


def normalize(text: str, root: Path, ci: Path, work: Optional[Path] = None) -> str:
    pairs = [(ci, "<CI>"), (root / "inputs", "<INPUTS>")]
    if work is not None:
        pairs.insert(0, (work, "<WORK>"))
    for p, mark in pairs:
        for form in {str(p), p.as_posix(), str(p).replace("\\", "\\\\")}:
            text = text.replace(form, mark)
    # временные каталоги (tempfile) — случайные имена
    text = re.sub(r"(?i)(?:[A-Z]:)?[\\/][^\s'\"]*?[\\/](?:Temp|tmp)[\\/]tmp[\w]+", "<TMP>", text)
    # штамп времени, который ставит прибор (журнал --journal, шапка отчёта гейта)
    text = re.sub(r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:[+-]\d\d:?\d\d|Z)?", "<TS>", text)
    return text


def run(root: Path, ci: Path, label: str, seed: str = "0") -> None:
    dest = root / "runs" / label
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    work = dest / "_work"
    work.mkdir()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONHASHSEED=seed, PYTHONUTF8="1")
    t0 = time.time()
    for c in commands(root, ci.resolve(), work):
        t = time.time()
        r = subprocess.run(c["argv"], cwd=str(c["cwd"]), env=env, capture_output=True)
        body = (r.stdout or b"").decode("utf-8", "replace") + "\n--- stderr ---\n" + \
            (r.stderr or b"").decode("utf-8", "replace")
        if c.get("extra_file") and Path(c["extra_file"]).is_file():
            body += "\n--- file ---\n" + Path(c["extra_file"]).read_text(encoding="utf-8")
        body = f"exit: {r.returncode}\n" + normalize(body, root.resolve(), ci.resolve(), work.resolve())
        (dest / f"{c['name']}.txt").write_text(body, encoding="utf-8", newline="\n")
        print(f"{c['name']:32} код {r.returncode:2}  {time.time() - t:5.1f} с")
    shutil.rmtree(work)
    print(f"всего {time.time() - t0:.0f} с → {dest}")


def diff(root: Path, a: str, b: str) -> int:
    da, db = root / "runs" / a, root / "runs" / b
    names = sorted({p.name for p in da.glob("*.txt")} | {p.name for p in db.glob("*.txt")})
    bad = 0
    for n in names:
        pa, pb = da / n, db / n
        if not pa.is_file() or not pb.is_file():
            print(f"✗ {n}: нет в {'A' if not pa.is_file() else 'B'}")
            bad += 1
            continue
        if pa.read_bytes() != pb.read_bytes():
            bad += 1
            la = pa.read_text(encoding="utf-8").splitlines()
            lb = pb.read_text(encoding="utf-8").splitlines()
            d = list(difflib.unified_diff(la, lb, a, b, n=0, lineterm=""))
            print(f"✗ {n}: отличий строк {sum(1 for x in d if x[:1] in '+-') - 2}")
            for x in d[2:12]:
                print("    " + x[:200])
        else:
            print(f"= {n}")
    print(f"ИТОГО: файлов {len(names)}, отличается {bad}")
    return 1 if bad else 0


def _junit(path: Path) -> Dict[str, str]:
    import xml.etree.ElementTree as ET
    out: Dict[str, str] = {}
    for tc in ET.parse(str(path)).iter("testcase"):
        st = "passed"
        for k in ("failure", "error", "skipped"):
            if tc.find(k) is not None:
                st = k
        out[f"{tc.get('classname')}::{tc.get('name')}"] = st
    return out


def tests_diff(a: Path, b: Path) -> int:
    """Исходы тестов поимённо: эталон (junit A) против прогона (junit B)."""
    ra, rb = _junit(a), _junit(b)
    changed = sorted(k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k))
    for k in changed:
        print(f"✗ {k}: {ra.get(k, 'нет')} → {rb.get(k, 'нет')}")
    print(f"ИТОГО: тестов {len(set(ra) | set(rb))}, исход сменился у {len(changed)}")
    return 1 if changed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Эталон отчётов прибора для рефакторинга.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("snapshot"); s.add_argument("--root", type=Path, required=True)
    r = sp.add_parser("run"); r.add_argument("--root", type=Path, required=True)
    r.add_argument("--ci", type=Path, required=True); r.add_argument("--out", required=True)
    r.add_argument("--seed", default="0", help="PYTHONHASHSEED прогона (проверка устойчивости порядка)")
    d = sp.add_parser("diff"); d.add_argument("--root", type=Path, required=True)
    d.add_argument("a"); d.add_argument("b")
    td = sp.add_parser("tests-diff"); td.add_argument("a", type=Path); td.add_argument("b", type=Path)
    args = ap.parse_args()
    if args.cmd == "snapshot":
        snapshot(args.root)
        return 0
    if args.cmd == "run":
        run(args.root, args.ci, args.out, args.seed)
        return 0
    if args.cmd == "tests-diff":
        return tests_diff(args.a, args.b)
    return diff(args.root, args.a, args.b)


if __name__ == "__main__":
    sys.exit(main())
