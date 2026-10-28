# -*- coding: utf-8 -*-
"""Сборка зеркала skill-core-cloud для облачной сессии трека skillCore.

Состав и назначение — «Опись зеркала для облачной сессии…» (2026-10-28) в этом каталоге. Скрипт копирует компоненты
из git-объектов (не из рабочих деревьев), пишет MANIFEST.md, requirements.txt, корневые README/CLAUDE/.gitignore,
затем в собранном каталоге гоняет базовые проверки и складывает их вывод в skillCore/baseline/.

Запуск (из любого места, системным Python 3.12):

    python build_mirror.py --out C:/tmp/skill-core-cloud [--force] [--no-check]
        [--site-packages <путь к site-packages с beautifulsoup4 и pytest для проверок>]

Отклонение от описи (решение 2026-10-29): полигон берётся на базе ветки-эталона (67ab4e3), а не на trunk 42dadc1 —
после базы trunk занял CTL-054…057 (TEAMRKOUL-22052), эталон задачи TEAMTB-4567890 тоже создаёт CTL-054; прогон плеча
на trunk дал бы другие ID и несравнимый дифф. Вход плеча и эталон должны стоять на одной базе.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

CANON = Path("C:/doc-as-code/EAN/docs-o2new")
CANON_REF = "master"
CANON_EXPECT = "a1190f2"
CANON_PATHS = [
    "_meta", "AGENTS.md", "CLAUDE.md", "README.md", "CODEOWNERS", ".gitignore", ".claude", ".cursor", "examples",
    "output/open-add-account", "output/README.md", "sources/README.md", "sources/confluence/o2plus",
]

POLY = Path("C:/doc-as-code/EAN/docs-account-opening-request")
POLY_BASE = "67ab4e3"                      # база ветки-эталона (merge-base trunk..forward/TEAMTB-4567890)
POLY_REF = "forward/TEAMTB-4567890"        # эталон исполнения задачи (14105af)
POLY_REF_EXPECT = "14105af"
POLY_TASK = "tasks/TEAMTB-4567890.md"

ANALYZER = Path("C:/Users/alexe/PycharmProjects/requirements-analyzer-v3")
ANALYZER_REF = "HEAD"
TOOL_PATHS = ["app/__init__.py", "app/scripts/__init__.py", "app/scripts/CI"]
TEST_FILES = [
    "tests/test_structural_facts.py", "tests/test_canon_delta.py", "tests/test_selfcheck.py",
    "tests/test_accept_canon.py", "tests/test_transfer_gate.py",
]
# tests/conftest.py analyzer тянет fastapi/langchain — в зеркало не берётся, тестам он не нужен (только tmp_path).

ROOT_README = """# skill-core-cloud — зеркало для облачной сессии трека skillCore

Частная рабочая копия для переворота структуры скиллов канона Doc-as-Code (один набор скиллов с режимами:
«Вход reverse / Вход forward → общий Порядок»). Собрано скриптом `skillCore/build_mirror.py` из git-объектов
источников; какие именно — `MANIFEST.md`.

Что здесь лежит:

| Каталог | Что это | Можно править |
| --- | --- | --- |
| `canon/` | копия канона (`_meta`, обёртки, эталонный комплект `output/open-add-account` и его источники `sources/confluence/o2plus`) | только `_meta/skills/*.md` из объёма SC-01 и `_meta/skills/create-skill.md`; реестр структурных фактов — точечно при намеренной переформулировке сигнатуры |
| `canon-base/_meta/` | та же `_meta` базового среза, для `canon_delta` («что увидит координатор») | нет |
| `polygon/` | полигон режима C на базе `67ab4e3` (`docs-account-opening-request`) | нет (копии — в `skillCore/ab/`) |
| `polygon-ref/` | постановка `tasks/TEAMTB-4567890.md` и принятый результат её исполнения (дифф, список файлов, файлы) | нет |
| `app/scripts/CI/`, `tests/` | прибор (сторожа, selfcheck, canon_delta, accept_canon) и его тесты | нет |
| `skillCore/` | трек: README, постановка, файл решений, журнал вопросов, сдачи срезов, baseline, A/B-материалы | да |

Порядок работы сессии — `CLAUDE.md` в корне и `skillCore/README.md`.

## Окружение

```
pip install -r requirements.txt
set PYTHONIOENCODING=utf-8      (или export)
```

## Проверки после каждого среза (из корня)

```
python -m app.scripts.CI.structural_facts --repo canon --strict
python -m app.scripts.CI.selfcheck --docs canon/output/open-add-account/docs --sources canon/sources/confluence/o2plus --out skillCore/selfcheck-etalon-<срез>.txt
python -m app.scripts.CI.selfcheck --docs polygon --out skillCore/selfcheck-polygon-<срез>.txt
python -m pytest tests -q -o addopts=""
```

Базовые выводы тех же команд до любых правок — `skillCore/baseline/`. Ожидание по обоим selfcheck: вывод байт в
байт как в baseline (прибор скиллы не читает; отличие значит, что задет комплект).
"""

ROOT_CLAUDE = """# Инструкции облачной сессии (трек skillCore)

Ты работаешь в зеркале канона Doc-as-Code над переворотом структуры скиллов. Порядок чтения перед любой правкой:

1. `skillCore/README.md` — что такое трек и где что лежит.
2. `skillCore/Постановка для облачной сессии — срез 0 …md` — текущая задача.
3. `skillCore/Файл решений для облачной сессии …md` — решения владельца SC-01…SC-12. Это единственный источник
   решений: пустое поле «Решение владельца» = решения нет → вопрос в `skillCore/questions.md`, срез останавливается.
4. `skillCore/Опись зеркала …md` — состав, команды проверки, возврат результата.
5. `canon/_meta/skills/create-skill.md` — дом каркаса скилла; `canon/AGENTS.md` — как устроен канон;
   `canon/_meta/structural-facts.md` — реестр структурных фактов (сигнатуры сторожа).

Правила, которые не обсуждаются (SC-07, SC-12):

- Правишь только файлы объёма SC-01 (13 скиллов), `canon/_meta/skills/create-skill.md`, реестр структурных фактов
  точечно, и каталог `skillCore/`. Всё остальное — только чтение. Дифф с файлом вне объёма = остановка.
- Не трогаешь код прибора (`app/`, `tests/`), шаблоны `canon/_meta/templates`, `canon/_meta/migration`, комплекты
  `canon/output` и `polygon/` (исполнители плеч A/B пишут в копии `skillCore/ab/…`).
- Не добавляешь зависимости, не меняешь файл решений (кроме отметок, которые ставит владелец), не выдумываешь
  решения за владельца.
- Срезы последовательно; к следующему переходишь только после отметки владельца «срез N принят» в SC-09.
- Остановка — это сдача «НЕ ГОТОВО» с причиной, не тихий откат и не обход.
- Коммиты: по путям `canon/…` — отдельно от коммитов по `skillCore/…`; сообщения — для всех команд канона (сначала
  проблема, потом что меняется), без AI-трейлеров и упоминаний модели: они поедут в канон как есть. Ветка среза —
  `skill-core/<N>-<имя>` от `main`; push в этот репозиторий разрешён (он и есть канал сдачи).
- Числа в сдаче — из прогонов, не по памяти; выводы A/B — только «не хуже / хуже по метрикам …».

Проверки после каждого среза и baseline — `README.md` в корне, раздел «Проверки».
"""

GITIGNORE = "__pycache__/\n*.pyc\n.pytest_cache/\n"
REQUIREMENTS = "beautifulsoup4\npytest\n"


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} в {repo}: {r.stderr.decode('utf-8', 'replace')}")
    return r.stdout.decode("utf-8") if text else r.stdout


def short(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--short=7", ref).strip()


def expect(repo: Path, ref: str, want: str, allow_drift: bool) -> str:
    got = short(repo, ref)
    if not got.startswith(want) and not want.startswith(got):
        msg = f"{repo.name}: {ref} = {got}, ожидался {want} (опись 28.10)"
        if not allow_drift:
            raise SystemExit(msg + "; обновите константы скрипта и опись или запустите с --allow-drift")
        print("ВНИМАНИЕ:", msg)
    return got


def archive(repo: Path, ref: str, dest: Path, paths: list[str]) -> int:
    """git archive <ref> -- <paths> → распаковка в dest. Возвращает число файлов."""
    for p in paths:
        if not git(repo, "ls-tree", ref, "--", p).strip():
            raise SystemExit(f"{repo.name}@{ref}: пути {p} нет в дереве")
    data = git(repo, "archive", "--format=tar", ref, "--", *paths, text=False)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:", encoding="utf-8") as tar:
        members = [m for m in tar.getmembers() if "__pycache__" not in m.name]
        tar.extractall(dest, members=members, filter="data")
        n = sum(1 for m in members if m.isfile())
    return n


def count_files(root: Path) -> tuple[int, int]:
    n = b = 0
    for p in root.rglob("*"):
        if p.is_file():
            n += 1
            b += p.stat().st_size
    return n, b


def run_check(out: Path, name: str, cmd: list[str], env: dict) -> int:
    base = out / "skillCore" / "baseline"
    base.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, cwd=str(out), env=env, capture_output=True)
    txt = r.stdout.decode("utf-8", "replace") + ("\n--- stderr ---\n" + r.stderr.decode("utf-8", "replace") if r.stderr else "")
    (base / f"{name}.txt").write_text(txt, encoding="utf-8", newline="\n")
    tail = "\n".join(txt.strip().splitlines()[-3:])
    print(f"[{name}] код {r.returncode}\n  {tail.replace(chr(10), chr(10) + '  ')}")
    return r.returncode


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("C:/tmp/skill-core-cloud"))
    ap.add_argument("--force", action="store_true", help="очистить существующий каталог (кроме .git)")
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--allow-drift", action="store_true", help="не останавливаться, если коммиты источников не те")
    ap.add_argument("--site-packages", type=Path, default=ANALYZER / ".venv/Lib/site-packages",
                    help="откуда брать beautifulsoup4/pytest для проверок")
    a = ap.parse_args()
    out: Path = a.out

    if out.exists() and any(p.name != ".git" for p in out.iterdir()):
        if not a.force:
            raise SystemExit(f"{out} не пуст; --force очистит всё, кроме .git")
        for p in out.iterdir():
            if p.name == ".git":
                continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    canon_c = expect(CANON, CANON_REF, CANON_EXPECT, a.allow_drift)
    poly_b = expect(POLY, POLY_BASE, POLY_BASE, a.allow_drift)
    poly_r = expect(POLY, POLY_REF, POLY_REF_EXPECT, a.allow_drift)
    mb = short(POLY, git(POLY, "merge-base", POLY_BASE, POLY_REF).strip())
    if mb != poly_b:
        raise SystemExit(f"полигон: merge-base {POLY_BASE}..{POLY_REF} = {mb}, а не {poly_b}")
    tool_c = short(ANALYZER, ANALYZER_REF)
    if git(ANALYZER, "status", "--porcelain", "--", *TOOL_PATHS, *TEST_FILES).strip():
        print("ВНИМАНИЕ: в analyzer есть незакоммиченные правки прибора/тестов — в зеркало идёт", ANALYZER_REF)

    rows = []
    n = archive(CANON, CANON_REF, out / "canon", CANON_PATHS)
    rows.append(("canon/", f"{CANON} @ {CANON_REF}", canon_c, n))
    n = archive(CANON, CANON_REF, out / "canon-base", ["_meta"])
    rows.append(("canon-base/_meta/", f"{CANON} @ {CANON_REF}", canon_c, n))

    n = archive(POLY, POLY_BASE, out / "polygon", ["."])
    rows.append(("polygon/", f"{POLY} @ {POLY_BASE} (база ветки-эталона)", poly_b, n))
    ref_dir = out / "polygon-ref"
    ref_dir.mkdir()
    affected = [ln for ln in git(POLY, "diff", "--name-only", POLY_BASE, POLY_REF).splitlines() if ln.strip()]
    (ref_dir / "affected-files.txt").write_text("\n".join(affected) + "\n", encoding="utf-8", newline="\n")
    (ref_dir / "result.diff").write_bytes(git(POLY, "diff", POLY_BASE, POLY_REF, text=False))
    n = archive(POLY, POLY_REF, ref_dir / "result", affected)
    log = git(POLY, "log", "--format=%h %s", f"{POLY_BASE}..{POLY_REF}")
    (ref_dir / "README.md").write_text(
        "# Эталон плеча режима C — задача TEAMTB-4567890\n\n"
        f"Полигон `polygon/` стоит на `{poly_b}` — базе ветки `{POLY_REF}` ({poly_r}). Здесь — принятый результат\n"
        "исполнения постановки на этой же базе:\n\n"
        f"- `result/{POLY_TASK}` — постановка (вход плеча; в `polygon/` её нет, исполнителю передаётся копия);\n"
        "- `affected-files.txt` — файлы, которые изменил эталонный заход;\n"
        "- `result.diff` — дифф база → эталон;\n"
        "- `result/` — те же файлы в состоянии эталона.\n\n"
        f"Коммиты эталона:\n\n```\n{log}```\n\n"
        "Почему не `trunk` (42dadc1): после базы trunk занял CTL-054…057 (TEAMRKOUL-22052), эталон тоже создаёт CTL-054;\n"
        "прогон на trunk дал бы другие ID и несравнимый дифф. Сравнение плеч — по `delta_report` и построчно к `result/`.\n",
        encoding="utf-8", newline="\n")
    rows.append(("polygon-ref/", f"{POLY} @ {POLY_REF}", poly_r, n + 3))

    n = archive(ANALYZER, ANALYZER_REF, out, TOOL_PATHS)
    rows.append(("app/scripts/CI/", f"{ANALYZER} @ {ANALYZER_REF}", tool_c, n))
    n = archive(ANALYZER, ANALYZER_REF, out, TEST_FILES)
    rows.append(("tests/", f"{ANALYZER} @ {ANALYZER_REF} (без conftest.py: он тянет fastapi/langchain)", tool_c, n))

    sk = out / "skillCore"
    sk.mkdir(exist_ok=True)
    n = 0
    for p in sorted(HERE.iterdir()):
        if p.is_file():
            shutil.copy2(p, sk / p.name)
            n += 1
    rows.append(("skillCore/", f"{HERE} (рабочая копия analyzer)", tool_c, n))

    (out / "README.md").write_text(ROOT_README, encoding="utf-8", newline="\n")
    (out / "CLAUDE.md").write_text(ROOT_CLAUDE, encoding="utf-8", newline="\n")
    (out / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
    (out / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8", newline="\n")

    total_n, total_b = count_files(out)
    man = ["# MANIFEST — источники зеркала skill-core-cloud", "",
           f"Собрано: {dt.date.today().isoformat()} скриптом `skillCore/build_mirror.py` (analyzer {tool_c}).", "",
           "| Компонент | Источник | Коммит | Файлов |", "| --- | --- | --- | --- |"]
    man += [f"| `{c}` | `{s}` | `{h}` | {k} |" for c, s, h, k in rows]
    man += ["", f"Всего файлов: {total_n}, объём: {total_b / 1e6:.1f} МБ (без `.git`).", "",
            "Отклонение от описи 28.10: полигон на базе ветки-эталона, не на trunk — см. `polygon-ref/README.md`.", "",
            "Возврат результата: опись, раздел «Возврат результата в контур» (`format-patch` → `git am -p2` в клон канона).", ""]
    (out / "MANIFEST.md").write_text("\n".join(man), encoding="utf-8", newline="\n")
    print(f"собрано: {total_n} файлов, {total_b / 1e6:.1f} МБ → {out}")

    if a.no_check:
        return
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(out) + os.pathsep + str(a.site_packages))
    py = sys.executable
    codes = [
        run_check(out, "sf-base", [py, "-m", "app.scripts.CI.structural_facts", "--repo", "canon", "--strict"], env),
        run_check(out, "selfcheck-etalon-base", [py, "-m", "app.scripts.CI.selfcheck", "--docs",
                  "canon/output/open-add-account/docs", "--sources", "canon/sources/confluence/o2plus",
                  "--out", "skillCore/baseline/selfcheck-etalon-base.out.txt"], env),
        run_check(out, "selfcheck-polygon-base", [py, "-m", "app.scripts.CI.selfcheck", "--docs", "polygon",
                  "--out", "skillCore/baseline/selfcheck-polygon-base.out.txt"], env),
        run_check(out, "pytest-base", [py, "-m", "pytest", "tests", "-q", "-o", "addopts="], env),
    ]
    for p in out.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    shutil.rmtree(out / ".pytest_cache", ignore_errors=True)
    print("коды проверок (SF, selfcheck эталона, selfcheck полигона, pytest):", codes)


if __name__ == "__main__":
    main()
