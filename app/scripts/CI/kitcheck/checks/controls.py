# app/scripts/CI/kitcheck/checks/controls.py
"""Проверки selfcheck: controls — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
import re
try:
    from kitcheck import fs as _fs
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore


_GRP_ROW_RE = re.compile(r"^\|\s*\[?(CTL-GRP-\d+)\]?[^|]*\|\s*([^|]+)")


# формат с колонкой «Контур» (полигон 2026-08-29): | ID | FE/BE | Привязка |
_GRP_ROW_C_RE = re.compile(
    r"^\|\s*\[?(CTL-GRP-\d+)\]?[^|]*\|\s*(FE|BE)\s*\|\s*([^|]+)")


_QUOTE_TOKEN_RE = re.compile(r"«([^»]{3,60})»|`([A-Za-z_]{3,30})`")


_UI_MARK_RE = re.compile(
    r"кнопк|нажат|\bэф\b|экранн|вкладк|дровер|фокус", re.I)


_ST_MARK_RE = re.compile(r"статус|переход", re.I)


_OP_MARK_RE = re.compile(r"при выполнении|функц", re.I)


def check_group_contours(docs: Path) -> List[str]:
    """Согласованность контура групп контролей (решение владельца
    2026-08-29): контур — явная колонка FE/BE реестра групп, сторож
    сверяет её с формулировкой привязки. FE привязывается к UI-событию;
    BE — к переходу статусной модели или серверной операции, БЕЗ
    UI-мест (сервер не знает, откуда пришёл запрос, — API First;
    перечни триггеров заведомо неполны). Неоднозначность не угадывается
    — ⚠-вопрос аналитику (асимметрия). Реестр без колонки «Контур» —
    один ⚠ на файл (разметить при перегонке)."""
    report: List[str] = []
    for readme in sorted(docs.rglob("control/README.md")):
        try:
            text = _fs.read_text(readme, encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = readme.relative_to(docs)
        has_rows = any(_GRP_ROW_RE.match(ln.strip())
                       for ln in text.splitlines())
        if not has_rows:
            continue
        header_ok = re.search(r"^\|\s*ID\s*\|\s*Контур\s*\|", text, re.M)
        if not header_ok:
            report.append(
                f"⚠ {rel}: реестр групп без колонки «Контур» (FE/BE) — "
                "разметить при перегонке групп (шаблон controls §2, "
                "решение 2026-08-29)")
            continue
        for ln in text.splitlines():
            m = _GRP_ROW_C_RE.match(ln.strip())
            if not m:
                continue
            gid, contour, bind = m.group(1), m.group(2), m.group(3)
            ui = bool(_UI_MARK_RE.search(bind))
            st = bool(_ST_MARK_RE.search(bind))
            op = bool(_OP_MARK_RE.search(bind))
            if contour == "FE":
                if st:
                    report.append(
                        f"⚠ {rel}: {gid} (FE) — привязка содержит "
                        "статусные маркеры: контур/привязка ошибочны "
                        "либо событие двух контуров — расщепить на "
                        "FE- и BE-группы")
                elif not ui:
                    report.append(
                        f"⚠ {rel}: {gid} (FE) — привязка не называет "
                        "UI-событие; контур неопределим по формулировке "
                        "— вопрос аналитику")
            else:
                if ui:
                    report.append(
                        f"⚠ {rel}: {gid} (BE) — привязка содержит "
                        "UI-маркеры: сервер не знает мест инициирования "
                        "(API First) — убрать UI-места либо пересмотреть "
                        "контур")
                elif not (st or op):
                    report.append(
                        f"⚠ {rel}: {gid} (BE) — привязка не называет ни "
                        "переход статуса, ни серверную операцию — "
                        "неопределима, вопрос аналитику")
    return report


def check_similar_group_points(docs: Path) -> List[str]:
    """i-строки о парах групп с общим цитируемым литералом точки."""
    report: List[str] = []
    for readme in sorted(docs.rglob("control/README.md")):
        try:
            text = _fs.read_text(readme, encoding="utf-8", errors="replace")
        except OSError:
            continue
        toks: Dict[str, List[Tuple[str, str]]] = {}
        for ln in text.splitlines():
            # формат с колонкой «Контур»: описание привязки — третья
            # колонка; без неё — вторая (старый формат)
            mc = _GRP_ROW_C_RE.match(ln.strip())
            m = mc or _GRP_ROW_RE.match(ln.strip())
            if not m:
                continue
            gid = m.group(1)
            desc = (m.group(3) if mc else m.group(2)).strip()
            for qm in _QUOTE_TOKEN_RE.finditer(desc):
                tok = (qm.group(1) or qm.group(2)).strip().lower()
                toks.setdefault(tok, []).append((gid, desc[:50]))
        rel = readme.relative_to(docs)
        for tok, grps in sorted(toks.items()):
            ids = sorted({g for g, _ in grps})
            if len(ids) > 1:
                report.append(
                    f"i похожие точки применения [{rel}]: "
                    f"{' ↔ '.join(ids)} — общий литерал «{tok}»; "
                    "кандидат на консолидацию (решение владельца, "
                    "шаг консолидации этапа)")
    return report
