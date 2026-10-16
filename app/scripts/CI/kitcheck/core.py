# app/scripts/CI/kitcheck/core.py
"""Ядро прибора: находка, проверка, реестр, прогон реестра.

Проверка — объект с единым интерфейсом: `run(ctx) -> (строки отчёта, ok)`.
Строки — готовый текст отчёта в прежней форме (заголовок, отступы, отметки
✓/✗/⚠/i); `ok` — нет ли нарушения, влияющего на вердикт. Реестр — упорядоченный
список проверок: порядок реестра — порядок строк отчёта. Прогон реестра
складывает строки и считает вердикт в одном месте; влияет ли проверка на
вердикт, решает её поле `affects_verdict`, а не код прогона.

Сбой проверки изолирует сама проверка (обёртка `_safe` в selfcheck — как и
до переноса): ядро исключений не перехватывает, чтобы текст отчёта при сбое
остался прежним.

Новые проверки могут возвращать находки (`Finding`) — `render()` переводит их в
строки и признак вердикта по уровню находки, без разбора текста.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

Lines = List[str]
CheckResult = Tuple[Lines, bool]

FAIL, WARN, INFO, OK = "fail", "warn", "info", "ok"
_MARK = {FAIL: "✗", WARN: "⚠", INFO: "i", OK: "✓"}


@dataclass(frozen=True)
class Finding:
    """Находка проверки: уровень, заголовок, строки деталей (с отступом)."""
    level: str
    title: str
    details: Tuple[str, ...] = ()

    def lines(self) -> Lines:
        return [f"{_MARK[self.level]} {self.title}"] + [f"   {d}" for d in self.details]


def render(findings: Iterable[Finding]) -> CheckResult:
    """Находки → (строки отчёта, ok): ok ложен, если есть находка уровня fail."""
    out: Lines = []
    ok = True
    for f in findings:
        out.extend(f.lines())
        ok = ok and f.level != FAIL
    return out, ok


@dataclass(frozen=True)
class Check:
    """Проверка реестра.

    id — стабильное имя; scope — область (file / group / kit / repo);
    run(ctx) -> (строки, ok); affects_verdict — учитывается ли ok в вердикте;
    applies(ctx) — запускать ли проверку в этом прогоне (по умолчанию — всегда).
    """
    id: str
    run: Callable[[Any], CheckResult]
    affects_verdict: bool = True
    scope: str = "kit"
    applies: Optional[Callable[[Any], bool]] = field(default=None, compare=False)


def run_checks(checks: Sequence[Check], ctx: Any) -> CheckResult:
    """Прогон реестра: строки — по порядку реестра, вердикт — конъюнкция ok
    проверок, влияющих на вердикт."""
    lines: Lines = []
    ok = True
    for c in checks:
        if c.applies is not None and not c.applies(ctx):
            continue
        out, c_ok = c.run(ctx)
        lines.extend(out)
        if c.affects_verdict:
            ok = ok and c_ok
    return lines, ok
