# app/scripts/CI/accept_canon.py
#
# Утилита ВЛАДЕЛЬЦА: принять текущий срез канона для стенда одной
# командой — обновить строку «Срез канона» в профиле источников и
# зафиксировать веху точечным коммитом профиля (П-5b, 2026-08-27).
#
# Схлопывает шаги B.2–B.4 сценария обновления канона: rev-parse HEAD →
# правка ячейки профиля → git add README.md + commit с основанием.
# `git pull` канона НЕ выполняет сознательно: обновление клона —
# отдельное осознанное действие (владелец сначала смотрит, что
# приехало).
#
# Исполнителю запрещена протоколом (step-protocol §3: разрешены только
# selfcheck, normalize_tables и read-only диагностика) — отдельная
# утилита, а не флаг selfcheck, чтобы сохранить его read-only инвариант.
#
# Основание вехи: --reason опционален — по умолчанию собирается
# АВТОМАТИЧЕСКИ из тем принимаемых коммитов канона (git log old..new):
# причина обновления уже записана в каноне, дублировать её руками —
# лишняя работа команд (10 команд параллельно принимают один и тот же
# фикс). Фолбэк, когда диапазон не вычислить, — «обновление канона до
# <hash> от <дата коммита>» (дата коммита, не «сегодня»).
#
# Ограничители:
#   - коммитится ТОЛЬКО файл профиля; профиль с незакоммиченными
#     правками до запуска — отказ (чистая веха, чужое не захватывается);
#   - HEAD канона не определился — отказ, не угадывание;
#   - хэш уже актуален — «уже актуально», без пустого коммита.
#
# Приём среза = докатка норм (2026-10-22): после строки «✓ срез канона»
# печатается дельта норм между принятым и новым срезом — файлы шаблонов,
# скиллов, протокола, комплекта миграции и AGENTS.md с заголовками
# затронутых разделов; прибор (_meta/tools/*.py) — одной строкой числом
# файлов. В комплект ничего не пишется: это перечень для записи
# координатора «докатка / не применимо» в журнале (протокол §1).

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selfcheck import _CANON_CUT_RE  # noqa: E402  (единый формат строки)

_ROW_TEMPLATE = ("| **Срез канона** | `{h}` (обновляет владелец при "
                 "приёмке правок канона; сверяет selfcheck) |")
_ANCHOR_RE = re.compile(r"^\|\s*\*{0,2}service-id\*{0,2}\s*\|.*$", re.M)


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=30)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def canon_head(canon_root: Path) -> Optional[str]:
    return _git(canon_root, "rev-parse", "--short", "HEAD")


# что считается нормами для дельты при приёме среза
NORM_PATHS = ("_meta/templates", "_meta/skills", "_meta/tools/step-protocol.md",
              "_meta/migration", "AGENTS.md")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)
_HEAD_RE = re.compile(r"^(#{2,4}) +(.+?)\s*$")


def _touched_sections(canon_root: Path, old: str, new: str, path: str) -> List[str]:
    """Заголовки ##–#### нового файла, под которыми есть изменённые строки
    диффа old..new (удаление без добавления — по месту удаления)."""
    diff = _git(canon_root, "diff", "-U0", f"{old}..{new}", "--", path) or ""
    lines_new: List[int] = []
    for m in _HUNK_RE.finditer(diff):
        start, cnt = int(m.group(1)), int(m.group(2) or "1")
        lines_new.extend(range(start, start + cnt) if cnt else [max(start, 1)])
    body = _git(canon_root, "show", f"{new}:{path}") or ""
    heads: List[Tuple[int, str]] = []
    in_code = False
    for i, ln in enumerate(body.splitlines(), 1):
        if ln.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        hm = None if in_code else _HEAD_RE.match(ln)
        if hm:
            heads.append((i, hm.group(2)))
    out: List[str] = []
    for n in lines_new:
        h = next((t for i, t in reversed(heads) if i <= n), "(до первого раздела)")
        if h not in out:
            out.append(h)
    return out


def norm_delta(canon_root: Path, old: str, new: str) -> List[str]:
    """Строки блока «Дельта норм old→new» для отчёта приёма среза."""
    names = _git(canon_root, "diff", "--name-status", f"{old}..{new}", "--",
                 *NORM_PATHS)
    tools = _git(canon_root, "diff", "--name-only", f"{old}..{new}", "--",
                 "_meta/tools/*.py")
    if names is None:
        return [f"дельта норм {old}→{new}: не вычислена (срез {old} не найден в клоне канона)"]
    rows = [ln.split("\t") for ln in names.splitlines() if ln.strip()]
    n_tools = len([t for t in (tools or "").splitlines() if t.strip()])
    if not rows and not n_tools:
        return [f"дельта норм {old}→{new} пуста"]
    out = [f"Дельта норм {old}→{new} (по каждой — «докатка» или «не применимо» в журнал):"]
    for row in rows:
        status, path = row[0][:1], row[-1]
        if status == "D":
            out.append(f"  {path} — удалён")
            continue
        secs = _touched_sections(canon_root, old, new, path) if path.endswith(".md") else []
        tail = ("новый файл" if status == "A"
                else "разделы: " + ", ".join(f"«{t}»" for t in secs) if secs
                else "изменён")
        out.append(f"  {path} — {tail}")
    if n_tools:
        out.append(f"  прибор: {n_tools} файлов")
    return out


def _auto_reason(canon_root: Path, old: Optional[str],
                 head: str) -> str:
    """Основание вехи из истории канона: темы коммитов old..head;
    фолбэк — дата коммита HEAD."""
    if old:
        log = _git(canon_root, "log", "--oneline", "--no-decorate",
                   f"{old}..{head}")
        if log:
            subjects = [ln.split(" ", 1)[-1][:70]
                        for ln in log.splitlines() if ln.strip()]
            shown = "; ".join(subjects[:3])
            more = (f"; и ещё {len(subjects) - 3} правок"
                    if len(subjects) > 3 else "")
            return f"принято из канона: {shown}{more}"
    date = _git(canon_root, "show", "-s", "--format=%cs", head) or "?"
    return f"обновление канона до {head} от {date}"


def accept(profile: Path, canon_root: Path,
           reason: Optional[str] = None) -> Tuple[str, bool]:
    """Обновить срез в профиле и закоммитить. (сообщение, ok)."""
    head = canon_head(canon_root)
    if not head:
        return (f"отказ: HEAD канона не определён ({canon_root} — не "
                "git-репозиторий или git недоступен)", False)
    if not profile.is_file():
        return f"отказ: профиль не найден: {profile}", False
    src_root = profile.parent
    dirty = _git(src_root, "status", "--porcelain", "--", profile.name)
    if dirty is None:
        return (f"отказ: {src_root} — не git-репозиторий (веха среза "
                "фиксируется коммитом)", False)
    if dirty:
        return ("отказ: профиль имеет незакоммиченные правки — "
                "зафиксируй или отмени их до приёмки среза (веха "
                "должна быть чистой)", False)
    with open(profile, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    m = _CANON_CUT_RE.search(text)
    if m:
        if m.group(1).lower() == head.lower():
            return f"уже актуально: срез канона {head}, коммит не нужен", True
        new_text = text[:m.start(1)] + head + text[m.end(1):]
    else:
        a = _ANCHOR_RE.search(text)
        if not a:
            return ("отказ: в профиле нет ни строки «срез канона», ни "
                    "строки service-id для вставки — добавь строку "
                    "вручную по шаблону sources-readme", False)
        eol = "\r\n" if "\r\n" in text else "\n"
        new_text = (text[:a.end()] + eol + _ROW_TEMPLATE.format(h=head)
                    + text[a.end():])
    with open(profile, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    if _git(src_root, "add", "--", profile.name) is None:
        return "отказ: git add профиля не удался", False
    if not reason:
        reason = _auto_reason(canon_root, m.group(1) if m else None,
                              head)
    msg = f"Срез канона обновлён на {head}: {reason}"
    if _git(src_root, "commit", "-m", msg) is None:
        return "отказ: git commit профиля не удался", False
    old = m.group(1) if m else "(строки не было)"
    report = (f"✓ срез канона: {old} → {head}; профиль закоммичен "
              f"({msg!r})")
    if m:
        report += "\n" + "\n".join(norm_delta(canon_root, m.group(1), head))
    return report, True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Принять текущий срез канона для стенда "
                    "(утилита владельца; исполнителю запрещена "
                    "протоколом)")
    ap.add_argument("--profile", type=Path, required=True,
                    help="путь к профилю источников (README.md "
                         "src-репозитория)")
    ap.add_argument("--reason", default=None,
                    help="основание вехи; по умолчанию собирается из "
                         "тем принимаемых коммитов канона "
                         "(git log old..new)")
    ap.add_argument("--canon", type=Path, default=None,
                    help="корень клона канона (по умолчанию — "
                         "репозиторий, в котором лежит утилита)")
    args = ap.parse_args()
    canon_root = args.canon
    if canon_root is None:
        tool_dir = Path(__file__).resolve().parent
        if tool_dir.name == "tools" and tool_dir.parent.name == "_meta":
            canon_root = tool_dir.parent.parent
        else:
            print("отказ: утилита запущена не из канона — укажи "
                  "--canon <корень клона>", file=sys.stderr)
            return 2
    msg, ok = accept(args.profile.resolve(), canon_root.resolve(),
                     args.reason)
    print(msg)
    # сторож реестра структурных фактов (2026-10-09): отчёт печатается
    # при каждом приёме среза, приём не блокирует — расхождение видно
    # владельцу в тот день, когда файл с сигнатурой попал в канон
    try:
        from app.scripts.CI.structural_facts import check as _sf_check
    except ImportError:  # копия в канонe лежит рядом, без пакета app
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from structural_facts import check as _sf_check  # type: ignore
        except ImportError:
            _sf_check = None
    if _sf_check is not None and (canon_root / "_meta" /
                                  "structural-facts.md").is_file():
        for ln in _sf_check(canon_root.resolve())[0]:
            print(f"  {ln}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
