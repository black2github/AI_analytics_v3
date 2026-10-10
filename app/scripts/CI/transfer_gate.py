# app/scripts/CI/transfer_gate.py
#
# ГЕЙТ ПЕРЕНОСА комплекта документации из рабочего репозитория миграции
# `src-<service-id>` (группа EAS) в репозиторий документации
# `docs-<service-id>` (группа EAN). Решение владельца канона 2026-10-10
# (гармонизация с платформой AI Factory, предложение P-02; чек-лист DoR
# v1.2, раздел 1 «Технологическая совместимость»).
#
# ЗАЧЕМ. Перенос — момент, после которого комплект читают не аналитики
# миграции, а внешние потребители: команда сервиса и агенты платформы.
# Платформа у себя структурную проверку гарантированно не запускает
# (ответы 07.10.2026: её валидатор — самопроверка автора «при
# необходимости»), рабочий репозиторий и журнал открытых вопросов она не
# читает. Поэтому единственное место, где техническая пригодность
# комплекта проверяется наверняка, — здесь, до переноса. Гейт даёт один
# ответ: READY (переносить можно) или NOT READY (с перечнем причин).
#
# ЧТО ДЕЛАЕТ.
#   1. Собирает комплект в ЦЕЛЕВОЙ раскладке во временном каталоге:
#      содержимое `docs/` ложится в корень (в docs-репозитории обёртки
#      `docs/` нет); служебные файлы миграции не копируются —
#      `open-questions.md`, `feedback.md`, `coordination-*.md`,
#      `*.filled.md`, `*.tables.md`, каталоги `prompts/`, `sandbox/`,
#      `sources/`, `confluence/`, `__pycache__`. Служебные файлы живут в
#      src-репозитории и остаются там.
#   2. Прогоняет на собранном комплекте прибор миграции `selfcheck.py`
#      С ИСТОЧНИКАМИ src-репозитория (каталог выгрузки находится сам:
#      `sources/confluence` или `confluence`) — тот же гейт, что гоняет
#      команда на стенде: дословность и полнота против источника, реестры
#      ID, матрица, слоты частей, структурные файлы, относительные
#      ссылки, самоописание README. Профиль командный; --strict включает
#      полный профиль держателей канона (маркеры сокращения — брак).
#      Любой ✗ прибора — NOT READY. Источники не найдены — прибор идёт
#      без них, об этом говорится в отчёте.
#   3. Прогоняет валидатор платформы AI Factory (копия
#      `platform/scripts/validate_analytics_docs.py`) на временном
#      git-репозитории с собранным комплектом от пустого коммита, чтобы
#      увидеть ВСЕ находки, а не дельту. Любая ошибка `E_*` — NOT READY.
#      Валидатор не найден или не запустился — NOT READY с объяснением
#      (ключ --no-validator осознанно отключает эту половину гейта).
#   4. Проверяет условия самого переноса, которых нет ни у прибора, ни у
#      валидатора:
#        - открытых вопросов в `open-questions.md` src-репозитория нет
#          (запись со статусом «открыт» блокирует: платформа этот журнал
#          не увидит, нерешённый вопрос переедет молча) — CORE-20;
#        - матрица трассировки несёт раздел «Покрытие: API ↔ SRS» (хоть
#          пустой: по нему планировщик платформы находит репозитории
#          кода; нет раздела — нет API-слоя в задачах) — SDLC-04;
#        - каталога `api/` и YAML OpenAPI/AsyncAPI в комплекте нет
#          (контракты живут в репозитории кода) — условие переноса;
#        - `README.md` комплекта есть (точка входа внешних читателей) —
#          SDLC-08; раздел «Условные обозначения» — предупреждение;
#        - `service-vision.md`, `glossary.md` — предупреждение, если нет
#          (у платформы обязательны только для нового сервиса) — SDLC-05;
#        - долги раздела матрицы «Долги по ссылкам» переезжают как есть;
#          README обязан объяснять, как читать строку долга как поручение
#          (подраздел «Долги по ссылкам» в «Условных обозначениях») —
#          иначе блокер: внешний читатель долгов не поймёт — CORE-20.
#   5. Печатает отчёт, где каждая строка помечена критерием чек-листа
#      DoR v1.2 (раздел 1) — отчёт прилагается к протоколу самопроверки
#      как доказательство по этим критериям. Итог — READY / NOT READY,
#      код возврата 0 / 1 (2 — гейт не смог отработать).
#   6. По ключу --out при READY копирует собранный комплект в клон
#      docs-репозитория (существующие файлы перезаписываются, чужие не
#      удаляются); коммит и MR делает человек. При NOT READY --out
#      игнорируется — переносить брак гейт отказывается.
#
# ЧЕГО НЕ ДЕЛАЕТ. Не правит комплект (сторож обнаруживает, не лечит).
# Не оценивает качество аналитики — это раздел 2 чек-листа DoR, отдельный
# шаг с другим исполнителем. Не коммитит и не пушит. Не трогает
# src-репозиторий.
#
# КЛЮЧИ.
#   --src <путь>        корень клона src-репозитория (обязателен)
#   --docs <имя>        каталог комплекта внутри src (по умолчанию docs)
#   --out <путь>        клон docs-репозитория: при READY сюда копируется
#                       собранный комплект; каталог должен существовать
#   --keep <путь>       оставить собранный комплект в этом каталоге
#                       (для просмотра; иначе временный каталог удаляется)
#   --validator <путь>  скрипт валидатора платформы (по умолчанию копия
#                       рядом: platform/scripts/validate_analytics_docs.py)
#   --layout <yaml>     машинная раскладка комплекта для валидатора
#                       (docs-kit-layout.yaml проекта); без ключа —
#                       умолчания валидатора, совпадающие с раскладкой ЭКО
#   --no-validator      не запускать валидатор платформы (половина гейта
#                       отключена осознанно; в отчёте это отмечается)
#   --sources <путь>    каталог выгрузки источников для прибора (по
#                       умолчанию ищется в src: sources/confluence, confluence)
#   --strict            полный профиль прибора (маркеры сокращения — ✗)
#   --json              дополнительно вывести результат в JSON (вердикт,
#                       строки по критериям) — для протокола и CI
#
# ПРИМЕР.
#   python _meta/tools/transfer_gate.py --src C:\doc-as-code\EAS\src-business-cards
#   python _meta/tools/transfer_gate.py --src <src> --out C:\doc-as-code\EAN\docs-business-cards
#
# ОГРАНИЧИТЕЛИ. Асимметрия ошибок канона: сомнение трактуется в сторону
# NOT READY; гейт никогда не копирует при ненулевом числе ✗ или ошибок
# валидатора; крах любой проверки — NOT READY с текстом краха, не
# молчание.

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import selfcheck as sc  # noqa: E402
import link_debts as ld  # noqa: E402

_HERE = Path(__file__).resolve().parent
_DEFAULT_VALIDATOR = _HERE / "platform" / "scripts" / "validate_analytics_docs.py"

# служебные файлы миграции — в docs-репозиторий не переезжают
_SKIP_NAMES = {"open-questions.md", "feedback.md", "coordination-log.md",
               "coordination-state.md"}
_SKIP_SUFFIXES = (".filled.md", ".tables.md")
_SKIP_DIRS = {"prompts", "sandbox", "sources", "confluence", "__pycache__",
              ".git"}

_OQ_ENTRY_RE = re.compile(r"^##\s+(OQ-\d+)\b.*$", re.M)
_OQ_STATUS_RE = re.compile(r"^\s*-\s*\*\*Статус:?\*\*:?\s*([^\n]+)$", re.M)
_OPEN_WORDS = ("открыт", "в работе", "ждёт", "ожидает", "уточня")

# соответствие строк отчёта критериям чек-листа DoR v1.2 (раздел 1)
_SELFCHECK_CRITERIA = (
    ("реестр ID матрицы", "SDLC-09"),
    ("traceability-matrix.md", "SDLC-04"),
    ("долги ссылок", "CORE-09"),
    ("слот части", "SDLC-09"),
    ("структурный файл", "FMT-01"),
    ("структурные файлы", "FMT-01"),
    ("относительные ссылки", "CORE-06"),
    ("условные обозначения README", "SDLC-08"),
    ("матрица «API ↔ SRS»", "SDLC-04"),
    ("контракты в комплекте", "ПЕРЕНОС"),
    ("файл-артефакт", "CORE-09"),
    ("битая ссылка на files", "CORE-09"),
    ("frontmatter", "SDLC-09"),
)
_VALIDATOR_CRITERIA = {
    "E_FRONTMATTER_INVALID": "SDLC-09", "E_FRONTMATTER_EMPTY_FIELD": "SDLC-09",
    "E_FRONTMATTER_DUPLICATE_KEY": "SDLC-09", "E_DOCUMENT_IDENTITY_MISSING": "SDLC-09",
    "E_DECLARED_ID_DUPLICATE": "SDLC-09", "E_LOCAL_LINK_MISSING": "CORE-06",
    "E_LOCAL_LINK_OUTSIDE_REPOSITORY": "CORE-09", "E_LOCAL_REF_UNRESOLVED": "FMT-01",
    "E_STRUCTURED_FILE_INVALID": "FMT-01", "E_OPERATION_ID_DUPLICATE": "SDLC-04",
    "E_PATH_PARAMETER_UNBOUND": "SDLC-04", "E_PATH_OUTSIDE_REPOSITORY": "CORE-09",
    "E_TRACEABILITY_MISSING": "SDLC-04", "E_TRACEABILITY_DUPLICATE": "SDLC-04",
    "E_KIT_DOCS_WRAPPER": "ПЕРЕНОС",
}


class Gate:
    def __init__(self) -> None:
        self.lines: List[Tuple[str, str, str]] = []  # (знак, критерий, текст)
        self.blockers = 0

    def add(self, mark: str, crit: str, text: str) -> None:
        if mark == "✗":
            self.blockers += 1
        self.lines.append((mark, crit, text))

    def render(self) -> List[str]:
        return [f"{m} [{c}] {t}" for m, c, t in self.lines]


# --- шаг 1: сборка комплекта в целевой раскладке ---------------------------

def stage_kit(docs: Path, target: Path) -> Tuple[int, List[str]]:
    """Скопировать комплект без служебных файлов. (файлов, пропущено)."""
    copied = 0
    skipped: List[str] = []
    for p in sorted(docs.rglob("*")):
        rel = p.relative_to(docs)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if p.is_dir():
            continue
        if p.name in _SKIP_NAMES or p.name.endswith(_SKIP_SUFFIXES):
            skipped.append(rel.as_posix())
            continue
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        copied += 1
    return copied, skipped


# --- шаг 4: условия переноса --------------------------------------------------

def open_questions(src_root: Path, docs: Path) -> Tuple[Optional[Path], List[str]]:
    """Файл журнала и список открытых OQ (пусто — открытых нет)."""
    for cand in (docs / "open-questions.md", src_root / "open-questions.md"):
        if cand.is_file():
            text = cand.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.S | re.M)
            opened: List[str] = []
            entries = list(_OQ_ENTRY_RE.finditer(text))
            for i, m in enumerate(entries):
                end = entries[i + 1].start() if i + 1 < len(entries) else len(text)
                body = text[m.end():end]
                st = _OQ_STATUS_RE.search(body)
                status = st.group(1).strip().lower() if st else ""
                if not st or any(w in status for w in _OPEN_WORDS):
                    opened.append(m.group(1) + ("" if st else " (без строки «Статус»)"))
            return cand, opened
    return None, []


def check_transfer_conditions(gate: Gate, src_root: Path, docs: Path,
                              staged: Path) -> None:
    oq_file, opened = open_questions(src_root, docs)
    if oq_file is None:
        gate.add("⚠", "CORE-20", "журнал open-questions.md не найден — открытые "
                 "вопросы не проверены (у комплекта без журнала это норма)")
    elif opened:
        gate.add("✗", "CORE-20", f"открытые вопросы: {len(opened)} "
                 f"({', '.join(opened[:8])}{'…' if len(opened) > 8 else ''}) — "
                 "платформа журнал src не читает, нерешённый вопрос переедет "
                 "молча; закрыть или перевести в долг матрицы")
    else:
        gate.add("✓", "CORE-20", f"открытых вопросов нет ({oq_file.name})")

    matrix = staged / "traceability-matrix.md"
    mtext = matrix.read_text(encoding="utf-8", errors="replace") if matrix.is_file() else ""
    if matrix.is_file():
        if sc._API_SECTION_RE.search(mtext):
            gate.add("✓", "SDLC-04", "матрица: раздел «Покрытие: API ↔ SRS» есть")
        else:
            gate.add("✗", "SDLC-04", "матрица без раздела «Покрытие: API ↔ SRS» — "
                     "планировщик платформы определяет по нему репозитории кода; "
                     "раздел обязателен даже пустым (шаблон матрицы)")
    # (отсутствие матрицы — ✗ прибора, здесь не дублируем)

    api_dirs = [p for p in staged.rglob("api") if p.is_dir()]
    yamls = []
    for f in staged.rglob("*.y*ml"):
        if f.suffix.lower() in (".yaml", ".yml"):
            head = f.read_text(encoding="utf-8", errors="replace")[:2000]
            if re.search(r"^(openapi|asyncapi):", head, re.M):
                yamls.append(f.relative_to(staged).as_posix())
    if api_dirs or yamls:
        what = ", ".join([d.relative_to(staged).as_posix() + "/" for d in api_dirs]
                         + yamls[:3])
        gate.add("✗", "ПЕРЕНОС", f"контракты в комплекте ({what}) — OpenAPI/AsyncAPI "
                 "живут в api-specification/ репозитория кода, копии в "
                 "docs-репозиторий не переносятся")
    else:
        gate.add("✓", "ПЕРЕНОС", "каталога api/ и YAML-контрактов в комплекте нет")

    readme = staged / "README.md"
    rtext = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
    if not readme.is_file():
        gate.add("✗", "SDLC-08", "README.md комплекта отсутствует — точка входа "
                 "внешних читателей (шаблон docs-readme.md)")
    else:
        if sc._LEGEND_HEAD_RE.search(rtext):
            gate.add("✓", "SDLC-08", "README.md с разделом «Условные обозначения»")
        else:
            gate.add("⚠", "SDLC-08", "README.md без раздела «Условные обозначения» — "
                     "внешние читатели не узнают контуры, части и типы комплекта")
    for name, crit in (("service-vision.md", "SDLC-05"), ("glossary.md", "SDLC-05")):
        if (staged / name).is_file():
            gate.add("✓", crit, f"{name} есть")
        else:
            gate.add("⚠", crit, f"{name} отсутствует (у платформы обязателен только "
                     "для нового сервиса; чек-лист DoR требует)")
    nested = [p for p in staged.rglob("docs") if p.is_dir()]
    if nested:
        gate.add("✗", "ПЕРЕНОС", "внутри комплекта есть каталог docs/ — обёртка "
                 "недопустима (валидатор платформы: E_KIT_DOCS_WRAPPER)")
    # долги, переживающие перенос (решение 2026-10-10, P-18): строки
    # раздела «Долги по ссылкам» едут как есть, а правило их чтения как
    # поручений объявляет README («Условные обозначения» → «Долги по
    # ссылкам»); есть долги без правила — внешний читатель их не поймёт
    if matrix.is_file():
        _, debts = ld.parse_matrix(mtext)
        if debts:
            cross = sum(1 for d in debts if d[3])
            has_rule = readme.is_file() and "Долги по ссылкам" in rtext
            mark = "✓" if has_rule else "✗"
            gate.add(mark, "CORE-20",
                     f"перенесённые долги: {len(debts)}, из них межсервисных {cross}"
                     + (" — правило чтения объявлено в README" if has_rule else
                        " — README не объясняет раздел «Долги по ссылкам» "
                        "(подраздел «Условных обозначений», шаблон docs-readme.md)"))


# --- шаг 2: прибор миграции -----------------------------------------------------

def find_sources(src_root: Path) -> Optional[Path]:
    for rel in ("sources/confluence", "confluence"):
        if (src_root / rel).is_dir():
            return src_root / rel
    return None


def run_selfcheck(gate: Gate, staged: Path, sources: Optional[Path],
                  strict: bool) -> None:
    try:
        report, ok = sc.run(staged, sources, strict=strict)
    except Exception as e:  # noqa: BLE001
        gate.add("✗", "ПРИБОР", f"selfcheck упал: {e!r} — комплект не проверен")
        return
    block: Optional[Tuple[str, str]] = None  # (знак для подстрок, критерий)
    for ln in report:
        s = ln.rstrip()
        st = s.strip()
        if not st or st.startswith("ИТОГО") or st.startswith("i "):
            block = None
            continue
        if block is not None and s.startswith("   "):
            gate.add(block[0], block[1], st)  # подстроки заголовка — причины
            continue
        block = None
        if st.startswith(("✓", "✗", "⚠")):
            mark = st[0]
            crit = next((c for key, c in _SELFCHECK_CRITERIA if key in st), "ПРИБОР")
            if mark == "✗":
                gate.add(mark, crit, st[1:].strip())
                if st.endswith(":"):
                    block = ("i", crit)  # причины ниже — информационно, не второй ✗
            elif mark == "⚠" and "условные обозначения README" in st:
                block = ("⚠", "SDLC-08")  # подстроки ниже — сами сигналы
    total = next((ln for ln in report if ln.startswith("ИТОГО")), "")
    mode = ("полный профиль" if strict else "командный профиль") + (
        f", источники {sources.as_posix()}" if sources else ", БЕЗ источников")
    gate.add("✓" if ok else "✗", "ПРИБОР",
             f"selfcheck ({mode}): {total.replace('ИТОГО: ', '')}")


# --- шаг 3: валидатор платформы -------------------------------------------------

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def run_validator(gate: Gate, staged: Path, validator: Path,
                  layout: Optional[Path]) -> Optional[dict]:
    if not validator.is_file():
        gate.add("✗", "ВАЛИДАТОР", f"валидатор платформы не найден: {validator} — "
                 "половина гейта не выполнена (осознанный пропуск — --no-validator)")
        return None
    # временный git-репозиторий: пустой коммит → комплект, чтобы валидатор
    # показал все находки, а не дельту относительно базы
    try:
        for args in (("init", "-q"), ("config", "user.email", "gate@local"),
                     ("config", "user.name", "transfer-gate"),
                     ("commit", "-q", "--allow-empty", "-m", "empty")):
            r = _git(staged, *args)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[:200])
        base = _git(staged, "rev-parse", "HEAD").stdout.strip()
        _git(staged, "add", "-A")
        r = _git(staged, "commit", "-q", "-m", "kit")
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[:200])
    except Exception as e:  # noqa: BLE001
        gate.add("✗", "ВАЛИДАТОР", f"не удалось подготовить git-репозиторий для "
                 f"валидатора: {e} — половина гейта не выполнена")
        return None
    cmd = [sys.executable, "-I", str(validator), "--repo", str(staged), "--role", "SA",
           "--base-ref", base, "--head-ref", "HEAD", "--format", "json",
           "--max-findings", "200"]
    if layout is not None:
        cmd += ["--layout", str(layout)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
    except Exception as e:  # noqa: BLE001
        gate.add("✗", "ВАЛИДАТОР", f"валидатор не запустился: {e!r}")
        return None
    if r.returncode == 2 or not r.stdout.strip():
        gate.add("✗", "ВАЛИДАТОР", "валидатор не смог завершить проверку: "
                 + (r.stderr.strip().splitlines() or ["(без вывода)"])[-1][:200])
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        gate.add("✗", "ВАЛИДАТОР", "валидатор вернул не JSON: " + r.stdout[:120])
        return None
    findings = data.get("findings", [])
    for f in findings:
        code = f.get("code", "E_?")
        crit = _VALIDATOR_CRITERIA.get(code, "ВАЛИДАТОР")
        where = f.get("path", "?") + (f":{f['line']}" if f.get("line") else "")
        gate.add("✗", crit, f"{code} {where}: {f.get('detail', '')}"[:300])
    summary = data.get("summary", {})
    errors = summary.get("errors", len(findings))
    if errors == 0:
        gate.add("✓", "ВАЛИДАТОР", "валидатор платформы: ошибок нет")
    elif summary.get("truncated"):
        gate.add("✗", "ВАЛИДАТОР", f"валидатор платформы: ошибок {errors}, показаны "
                 f"первые {len(findings)}")
    return data


# --- шаг 6: копирование при READY ----------------------------------------------

def copy_out(staged: Path, out: Path) -> Tuple[int, str]:
    if not out.is_dir():
        return 0, f"--out: каталог не существует: {out}"
    n = 0
    for p in sorted(staged.rglob("*")):
        rel = p.relative_to(staged)
        if ".git" in rel.parts or p.is_dir():
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        n += 1
    return n, ""


# --- оркестровка ----------------------------------------------------------------

def run_gate(src_root: Path, docs_name: str = "docs", out: Optional[Path] = None,
             keep: Optional[Path] = None, validator: Optional[Path] = None,
             layout: Optional[Path] = None, no_validator: bool = False,
             sources: Optional[Path] = None, strict: bool = False
             ) -> Tuple[List[str], bool, dict]:
    gate = Gate()
    docs = src_root / docs_name
    if not docs.is_dir():
        gate.add("✗", "ПЕРЕНОС", f"каталог комплекта не найден: {docs}")
        lines = gate.render() + ["ИТОГ: NOT READY"]
        return lines, False, {"verdict": "NOT READY", "lines": gate.lines}
    tmp = None
    if keep is not None:
        staged = keep
        if staged.exists():
            shutil.rmtree(staged)
        staged.mkdir(parents=True)
    else:
        tmp = tempfile.mkdtemp(prefix="transfer-gate-")
        staged = Path(tmp)
    try:
        copied, skipped = stage_kit(docs, staged)
        gate.add("✓", "ПЕРЕНОС", f"комплект собран в целевой раскладке: {copied} файлов; "
                 f"служебных пропущено {len(skipped)}"
                 + (f" ({', '.join(skipped[:4])})" if skipped else ""))
        if sources is None:
            sources = find_sources(src_root)
        if sources is None:
            gate.add("⚠", "ПРИБОР", "каталог выгрузки источников не найден "
                     "(sources/confluence, confluence) — прибор идёт без сверки "
                     "с источником; задайте --sources")
        run_selfcheck(gate, staged, sources, strict)
        check_transfer_conditions(gate, src_root, docs, staged)
        if no_validator:
            gate.add("⚠", "ВАЛИДАТОР", "валидатор платформы отключён ключом "
                     "--no-validator — структурная половина гейта не выполнена")
        else:
            run_validator(gate, staged, validator or _DEFAULT_VALIDATOR, layout)
        ready = gate.blockers == 0
        lines = gate.render()
        n_warn = sum(1 for m, _, _ in gate.lines if m == "⚠")
        lines.append(f"ИТОГ: {'READY' if ready else 'NOT READY'} — блокеров {gate.blockers}, "
                     f"предупреждений {n_warn}")
        if out is not None:
            if ready:
                n, err = copy_out(staged, out)
                lines.append(f"✗ --out: {err}" if err else
                             f"✓ перенесено в {out}: {n} файлов; коммит и MR — человек")
                if err:
                    ready = False
            else:
                lines.append("✗ --out пропущен: при NOT READY гейт не переносит")
        if keep is not None:
            lines.append(f"i собранный комплект оставлен в {keep}")
        return lines, ready, {"verdict": "READY" if ready else "NOT READY",
                              "blockers": gate.blockers, "warnings": n_warn,
                              "lines": [{"mark": m, "criterion": c, "text": t}
                                        for m, c, t in gate.lines]}
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Гейт переноса комплекта src-<service> → docs-<service>: READY / NOT READY")
    ap.add_argument("--src", required=True, type=Path, help="корень клона src-репозитория")
    ap.add_argument("--docs", default="docs", help="каталог комплекта внутри src (docs)")
    ap.add_argument("--out", type=Path, default=None,
                    help="клон docs-репозитория: при READY сюда копируется комплект")
    ap.add_argument("--keep", type=Path, default=None,
                    help="оставить собранный комплект в этом каталоге")
    ap.add_argument("--validator", type=Path, default=None,
                    help="скрипт валидатора платформы (по умолчанию копия рядом)")
    ap.add_argument("--layout", type=Path, default=None,
                    help="docs-kit-layout.yaml проекта для валидатора")
    ap.add_argument("--no-validator", action="store_true",
                    help="не запускать валидатор платформы (осознанно)")
    ap.add_argument("--sources", type=Path, default=None,
                    help="каталог выгрузки источников (по умолчанию ищется в src)")
    ap.add_argument("--strict", action="store_true",
                    help="полный профиль прибора (маркеры сокращения — брак)")
    ap.add_argument("--json", action="store_true", help="дополнительно вывести JSON")
    a = ap.parse_args()
    try:
        lines, ready, data = run_gate(a.src.resolve(), a.docs, a.out, a.keep,
                                      a.validator, a.layout, a.no_validator,
                                      a.sources.resolve() if a.sources else None,
                                      a.strict)
    except Exception as e:  # noqa: BLE001
        print(f"✗ гейт не отработал: {e!r}")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for ln in lines:
        print(ln)
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
