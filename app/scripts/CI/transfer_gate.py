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
#   Режим репозитория документации (2026-10-14): --src — целевой
#      docs-<service-id>, комплект в корне (docs/ нет, матрица в корне, либо
#      --docs .). Комплект проверяется на месте: CODEOWNERS и манифест — в
#      самом репозитории (в его корне, как их читает GitLab; комплект может
#      лежать в подкаталоге — 2026-10-28), журнал вопросов не ожидается, служебные файлы
#      миграции в корне — блокер, --out отклоняется. Отчёт — расстояние до
#      действующего стандарта, не проверка переноса.
#   4. Проверяет условия самого переноса, которых нет ни у прибора, ни у
#      валидатора:
#        - открытых вопросов в `open-questions.md` src-репозитория нет,
#          либо каждый открытый переведён в строку долга матрицы, несущую
#          вопрос целиком — формулировку, причину, ответственного, ограничение,
#          условие закрытия, источник OQ-NNN (решения владельца 2026-10-13 и
#          2026-10-14): платформа журнал src не увидит, а долг в матрице —
#          увидит — CORE-20;
#        - матрица трассировки несёт раздел «Покрытие: API ↔ SRS» (хоть
#          пустой: по нему планировщик платформы находит репозитории
#          кода; нет раздела — нет API-слоя в задачах) — SDLC-04;
#        - каталога `api/` и YAML OpenAPI/AsyncAPI в комплекте нет
#          (контракты живут в репозитории кода) — условие переноса;
#        - `README.md` комплекта есть (точка входа внешних читателей) —
#          SDLC-08; раздел «Условные обозначения» — предупреждение;
#        - `service-vision.md`, `glossary.md` — предупреждение, если нет
#          (у платформы обязательны только для нового сервиса) — SDLC-05;
#        - типы документов вне закрытого набора платформы перечисляются как
#          исключения к согласованию (TRF-04 / SDLC-01); пустой раздел API при
#          наличии описаний методов — предупреждение (SDLC-04); .txt-пример,
#          который разбирается, — предупреждение (FMT-01, защита от обхода);
#          каталоги карточек без README-реестра — предупреждение (SDLC-08);
#          внешние ссылки — перечень хостов для ручной проверки (CORE-09);
#          при --out — CODEOWNERS непустой (CORE-04, ✗) и gpb-manifest.json
#          разбирается, поля печатаются (SDLC-07); каталог tasks/ в
#          репозитории назначения — forward-развитие по постановкам уже
#          начато (Д-43), повторный перенос поверх запрещён (TRF-02, ✗);
#        - долги раздела матрицы «Долги по ссылкам» переезжают как есть;
#          README обязан объяснять, как читать строку долга как поручение
#          (подраздел «Долги по ссылкам» в «Условных обозначениях») —
#          иначе блокер: внешний читатель долгов не поймёт — CORE-20.
#   5. Печатает отчёт таблицей «Статус | Критерий | Проверка | Результат»:
#      критерий — из чек-листа DoR v1.2 (раздел 1), служебные метки —
#      TRF-01…05 (предложенный блок «Условия переноса»: корень без docs/,
#      служебные файлы не перенесены, нет контрактов в комплекте, типы
#      объявлены, межрепозиторные ссылки по стандарту), ПРИБОР
#      (сводка и несопоставленные находки прибора), ВАЛИДАТОР (то же для
#      валидатора платформы); легенда печатается под таблицей. Отчёт
#      прилагается к протоколу самопроверки как доказательство по
#      критериям. Итог — READY / NOT READY, код возврата 0 / 1 (2 — гейт
#      не смог отработать).
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
#   --questions <файл>  журнал открытых вопросов комплекта; без ключа ищется:
#                       <docs>/open-questions.md, <src>/open-questions.md,
#                       рядом с выгрузкой (родитель --sources, если это
#                       confluence/), sources/<имя комплекта>/open-questions.md
#                       (общий репозиторий нескольких комплектов, FB-04
#                       common-dictionary 2026-10-15). В рабочем репозитории
#                       ненайденный журнал — блокер CORE-20 (открытые вопросы
#                       не проверены — READY подтвердить нельзя)
#   --strict            полный профиль прибора (маркеры сокращения — ✗)
#   --log               журнал в порядке проверок вместо таблицы (по умолчанию —
#                       markdown-таблица «Статус | Критерий | Проверка | Результат»,
#                       строки сгруппированы: блокеры → предупреждения → причины →
#                       пройдено; под таблицей ИТОГ и легенда служебных меток)
#   --report <файл.md>  записать отчёт: шапка (вид допуска, коммит и ветка src,
#                       срез канона, источники, профиль прибора), таблица, раздел
#                       «Реестр долгов» (FROM-ID, цель, владелец, вопрос) и «Ручная
#                       часть протокола до подключения» — готовое приложение к
#                       протоколу чек-листа
#   --json              дополнительно вывести результат в JSON (вердикт, строки:
#                       знак, критерий, проверка, результат) — для CI
#   --after-step        лёгкий гейт после каждого захода (Д-49, 2026-10-23): та же
#                       сборка в целевой раскладке и валидатор платформы; прибор
#                       selfcheck НЕ гоняется (команда гоняет его сама, вердикт — в
#                       сдаче); критерии конца миграции понижены по закрытому
#                       списку: CORE-20 «открытые вопросы» ✗ → i, SDLC-05 ⚠ → i,
#                       SDLC-04 «раздела API ↔ SRS нет» ✗ → ⚠; остальные ✗
#                       (TRF-01…04, SDLC-08, FMT-01, CORE-06, CORE-09, ВАЛИДАТОР)
#                       остаются ✗; корень сборки проверяется самим гейтом
#                       (посторонний каталог или не-markdown файл — ✗ TRF-01:
#                       в полном режиме это делает selfcheck на сборке);
#                       --out отклоняется. Вердикт — «ФОРМА
#                       ПЕРЕНОСИМА / ФОРМА НЕ ПЕРЕНОСИМА: блокеров N (новых M)»,
#                       слово READY не печатается
#   --baseline <отчёт.md>  прошлый отчёт гейта (--report): строки ✗ сопоставляются
#                       по критерию, проверке и результату без отдельно стоящих
#                       чисел; под итогом — «новых блокеров M: …» и «ушло K».
#                       Работает в обоих режимах; без ключа — «(новых —)»
#
# ПРИМЕР.
#   python _meta/tools/transfer_gate.py --src C:\doc-as-code\EAS\src-business-cards
#   python _meta/tools/transfer_gate.py --src <src> --out C:\doc-as-code\EAN\docs-business-cards
#   python _meta/tools/transfer_gate.py --src <src> --after-step --report gate-z04.md --baseline gate-z03.md
#
# ОГРАНИЧИТЕЛИ. Асимметрия ошибок канона: сомнение трактуется в сторону
# NOT READY; гейт никогда не копирует при ненулевом числе ✗ или ошибок
# валидатора; крах любой проверки — NOT READY с текстом краха, не
# молчание.

import argparse
import fnmatch
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
from kitcheck.md import blank_code  # noqa: E402
from kitcheck.checks._common import domain_context  # noqa: E402
from kitcheck.checks.review_guards import OQ_STATUS_RE, oq_status_class  # noqa: E402

_HERE = Path(__file__).resolve().parent
_DEFAULT_VALIDATOR = _HERE / "platform" / "scripts" / "validate_analytics_docs.py"

# служебные файлы миграции — в docs-репозиторий не переезжают
_SKIP_NAMES = {"open-questions.md", "feedback.md", "coordination-log.md",
               "coordination-state.md"}
_SKIP_SUFFIXES = (".filled.md", ".tables.md")
_SKIP_DIRS = {"prompts", "sandbox", "sources", "confluence", "__pycache__",
              ".git"}
# файлы корня docs-репозитория, которые не являются комплектом (режим репозитория
# документации): владельцы и манифест проверяются на месте (CORE-04 / SDLC-07), а
# не копируются во временную сборку
_REPO_ROOT_FILES = {"CODEOWNERS", "gpb-manifest.json", ".gitignore", ".gitlab-ci.yml",
                    ".gitattributes"}

_OQ_ENTRY_RE = re.compile(r"^##\s+(OQ-\d+)\b.*$", re.M)
# строка статуса — обе формы, «- **Статус:**» и «- Статус:» (Д-49 п. 3); дом выражения —
# kitcheck/checks/review_guards.py (сторож B9 читает журнал тем же выражением)
_OQ_STATUS_RE = OQ_STATUS_RE
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
    ("матрица «API ↔ SRS»", "TRF-05"),
    ("контракты в комплекте", "TRF-03"),
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
    "E_KIT_DOCS_WRAPPER": "TRF-01",
}

# закрытый набор `type` платформы (канон платформы §8 / паспорт ЭКО §8); типы комплекта
# вне набора платформа читает «как документ без навыка» — их перечень идёт в отчёт как
# исключения к согласованию (комментарий платформы к SDLC-01, 13.10.2026)
_PLATFORM_TYPES = {"vision", "glossary", "feature", "use-case", "business-rules", "process",
                   "data-model", "function", "screen-form", "control", "print-form",
                   "contract-call", "notification", "rbac", "platform-function",
                   "external-integration"}
_SERVICE_DIRS = {"examples", "files", "img", "assets", "images",
                 "tasks"}  # постановки задач forward (type: task) — не карточки
_EXT_LINK_RE = re.compile(r"\]\((https?://[^)\s]+)")
_OQ_REF_RE = re.compile(r"\bOQ-\d+\b")
# критерии раздела 1, у которых автоматической проверки нет — ручная с доказательством
_MANUAL_SECTION1 = (
    ("SDLC-02", "внешние контракты в docs-external-contracts и обратные ссылки — наличие ссылок из "
                "карточек CALL-EXT и строки «Потребители» в контракте"),
    ("SDLC-03", "справочники в Git и связь в обе стороны — до решения канона о владельце общих "
                "справочников и обратном индексе"),
    ("CORE-09", "внешние ссылки (http) — доступность для платформы и агентов; гейт даёт только "
                "перечень хостов"),
    ("SDLC-07", "CODEOWNERS и gpb-manifest.json — проверяются гейтом только при --out; "
                "обязательные поля манифеста определяет владелец платформы"),
)
# ручные пункты протокола до технического подключения (комментарии платформы 13.10.2026),
# которые гейт закрыть не может
_MANUAL_BEFORE_CONNECT = (
    ("CORE-01, CORE-02", "назначение сервиса, потребители, перечень подключаемых возможностей и "
                         "исключения — разделы README «О сервисе» и «Границы комплекта» либо "
                         "service-vision.md; подтверждает владелец документации"),
    ("CORE-10", "термины назначения и границ определены (глоссарий или README)"),
    ("CORE-18", "происхождение правил — confluence_page_ids и дословность у мигрированного "
                "комплекта по построению; подтверждение правил задачи — до разработки, платформа"),
    ("SDLC-10", "оценка качества заявленного объёма по разделу 2 чек-листа и реестр долгов "
                "(приложен ниже) — отчёт, не READY"),
    ("SDLC-01", "типы и поля вне набора платформы (перечень в таблице гейта, TRF-04) — "
                "согласовать как исключения по стандарту платформы"),
)


# проверка по умолчанию для критерия (когда строка не задаёт свою)
_DEFAULT_CHECK = {
    "SDLC-04": "матрица трассировки", "SDLC-05": "концепция и глоссарий",
    "SDLC-08": "README комплекта", "SDLC-09": "идентификаторы и frontmatter",
    "CORE-06": "относительные ссылки", "CORE-09": "ссылки и артефакты",
    "CORE-20": "открытые вопросы и долги", "FMT-01": "структурные файлы",
    "TRF-01": "корень без обёртки docs/", "TRF-02": "служебные файлы миграции",
    "TRF-03": "контракты в комплекте", "TRF-04": "типы документов объявлены",
    "TRF-05": "межрепозиторные ссылки", "ПРИБОР": "прибор selfcheck",
    "ВАЛИДАТОР": "валидатор платформы",
}
_LEGEND = ("Критерии — чек-лист DoR v1.2, раздел «Технологическая совместимость»; проверка "
           "автоматическая там, где реализована, остальные критерии раздела — ручная с доказательством "
           "(перечень в отчёте). TRF-01…05 — предложенный блок «Условия переноса» (корень без docs/, "
           "служебные файлы не перенесены, нет контрактов в комплекте, типы объявлены, межрепозиторные "
           "ссылки по стандарту) — до решения рабочей группы коды предварительные. ПРИБОР — сводная "
           "строка прибора миграции selfcheck и его находки без сопоставленного критерия; ВАЛИДАТОР — "
           "то же для валидатора платформы AI Factory; РЕЖИМ — строка о раскладке, когда гейт "
           "проверяет репозиторий документации на месте (комплект в корне --src). Статусы: ✗ блокер и ⚠ предупреждение — проверено "
           "автоматически; i к сведению — автоматически НЕ проверено, нужна ручная проверка с "
           "доказательством (не считать пройденным); «не применяется» пишется словами с причиной.")
_STATUS_LABEL = {"✗": "✗ блокер", "⚠": "⚠ предупреждение", "i": "i к сведению", "✓": "✓ пройдено"}
_STATUS_ORDER = {"✗": 0, "⚠": 1, "i": 2, "✓": 3}


class Gate:
    """Записи гейта: (знак, критерий, проверка, результат). Таблица — по умолчанию,
    сгруппирована блокеры → предупреждения → к сведению → пройдено; журнал (--log) —
    в порядке выполнения проверок."""

    def __init__(self) -> None:
        self.lines: List[Tuple[str, str, str, str]] = []
        self.blockers = 0

    def add(self, mark: str, crit: str, text: str, check: Optional[str] = None) -> None:
        if mark == "✗":
            self.blockers += 1
        self.lines.append((mark, crit, check or _DEFAULT_CHECK.get(crit, crit.lower()), text))

    def render(self) -> List[str]:
        """Журнал: знак [критерий] результат — в порядке проверок."""
        return [f"{m} [{c}] {t}" for m, c, _, t in self.lines]

    def render_table(self) -> List[str]:
        esc = lambda x: x.replace("|", "\\|").replace("\n", " ")  # noqa: E731
        out = ["| Статус | Критерий | Проверка | Результат |", "|---|---|---|---|"]
        for m, c, k, t in sorted(self.lines, key=lambda r: _STATUS_ORDER.get(r[0], 9)):
            out.append(f"| {_STATUS_LABEL.get(m, m)} | {esc(c)} | {esc(k)} | {esc(t)} |")
        return out

    def as_dicts(self) -> List[dict]:
        return [{"mark": m, "criterion": c, "check": k, "text": t} for m, c, k, t in self.lines]

    def downgrade(self, rules: Tuple[Tuple[str, str, str, str], ...], note: str = "") -> None:
        """Понизить строки по закрытому списку (знак, критерий, проверка → новый знак):
        лёгкий режим --after-step (Д-49 п. 1). Строка вне списка не меняется."""
        out = []
        for m, c, k, t in self.lines:
            for frm, crit, check, to in rules:
                if m == frm and c == crit and k == check:
                    if m == "✗":
                        self.blockers -= 1
                    if to == "✗":
                        self.blockers += 1
                    m, t = to, t + note
                    break
            out.append((m, c, k, t))
        self.lines = out


# лёгкий режим --after-step (Д-49 п. 1): понижаются только критерии конца миграции —
# закрытый список (знак, критерий, проверка, новый знак); всё остальное — как в полном
# режиме, ✗ формы (TRF-01…04, SDLC-08, FMT-01, CORE-06, CORE-09, ВАЛИДАТОР) остаются ✗
_AFTER_STEP_NOTE = " (проверяется полным гейтом перед переносом)"
_AFTER_STEP_DOWNGRADE = (
    ("✗", "CORE-20", "открытые вопросы", "i"),
    ("⚠", "SDLC-05", "service-vision.md", "i"),
    ("⚠", "SDLC-05", "glossary.md", "i"),
    ("✗", "SDLC-04", "матрица: раздел «Покрытие: API ↔ SRS»", "⚠"),
)
# корень целевой раскладки (лёгкий режим, Д-49): штатные каталоги комплекта в корне
# репозитория документации. api/ — отдельный блокер TRF-03, здесь не дублируется; служебные
# каталоги вложений (files/, img/ …) — как у карточек корня
_TARGET_ROOT_DIRS = {"brd", "srs", "nfr", "tasks", "modules", "api"} | _SERVICE_DIRS


def check_staged_root(gate: "Gate", staged: Path) -> None:
    """Лёгкий режим: посторонние каталоги и не-markdown файлы в корне сборки — ✗ TRF-01.
    В полном режиме тот же дефект ловит сторож корня selfcheck на сборке (✗ ПРИБОР); лёгкий
    режим selfcheck не гоняет, поэтому проверяет корень сам — иначе `docs/archive/` уехал бы
    в корень репозитория документации незамеченным (КК, 2026-10-23)."""
    junk = sorted(
        p.name + ("/" if p.is_dir() else "") for p in staged.iterdir()
        if not p.name.startswith(".")
        and ((p.is_dir() and p.name not in _TARGET_ROOT_DIRS)
             or (p.is_file() and p.suffix.lower() not in (".md", ".markdown"))))
    if junk:
        gate.add("✗", "TRF-01", f"в корне целевой раскладки посторонние каталоги и файлы: "
                 f"{', '.join(junk[:8])}{'…' if len(junk) > 8 else ''} — в корне репозитория "
                 "документации только разделы комплекта (brd/, srs/, nfr/, tasks/, modules/) и "
                 "markdown; перенести внутрь раздела или удалить", check="корень целевой раскладки")
    else:
        gate.add("✓", "TRF-01", "в корне целевой раскладки только разделы комплекта и markdown",
                 check="корень целевой раскладки")


_NUM_RE = re.compile(r"(?<![\w.\-/])\d+(?:[.,]\d+)?(?![\w\-/])")


def _blocker_key(crit: str, check: str, text: str) -> Tuple[str, str, str]:
    """Ключ сопоставления строки ✗ с прошлым отчётом (--baseline): критерий, проверка и
    результат без отдельно стоящих чисел — «битые ссылки: 30 из 7263» и «…: 31 из 7270»
    один блокер. Числа в составе идентификаторов и имён (proc-001, OQ-55, v2) остаются —
    иначе новый блокер в соседнем файле спрятался бы за старым; номер строки «файл.md:12»
    — отдельное число, заменяется."""
    return (crit.strip(), check.strip(), _NUM_RE.sub("#", " ".join(text.split())))


def read_baseline(path: Path) -> Optional[List[Tuple[str, str, str]]]:
    """Строки ✗ прошлого отчёта гейта (его же таблица «Статус | Критерий | Проверка |
    Результат»); None — таблицы гейта в файле нет."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rows: List[Tuple[str, str, str]] = []
    seen_head = False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("| Статус | Критерий | Проверка | Результат |"):
            seen_head = True
            continue
        if not seen_head or not s.startswith("|"):
            continue
        cells = [c.replace("\\|", "|").strip()
                 for c in re.split(r"(?<!\\)\|", s.strip().strip("|"))]
        if len(cells) == 4 and cells[0].startswith("✗"):
            rows.append(_blocker_key(cells[1], cells[2], cells[3]))
    return rows if seen_head else None


def baseline_delta(gate: "Gate", base: List[Tuple[str, str, str]]
                   ) -> Tuple[List[Tuple[str, str, str]], int]:
    """(новые блокеры, ушло K) — сопоставление строк ✗ как мультимножеств ключей."""
    left: Dict[Tuple[str, str, str], int] = {}
    for k in base:
        left[k] = left.get(k, 0) + 1
    new: List[Tuple[str, str, str]] = []
    for m, c, k, t in gate.lines:
        if m != "✗":
            continue
        key = _blocker_key(c, k, t)
        if left.get(key):
            left[key] -= 1
        else:
            new.append((c, k, " ".join(t.split())))
    return new, sum(left.values())


# шапки собранного комплекта: условия переноса и «Затронуто» реестра долгов читают их четыре
# раза — кэш на прогон (очищается в run_gate); на КК ~1500 чтений → ~390
_FM_CACHE: Dict[Path, dict] = {}


def _fm(f: Path) -> dict:
    if f not in _FM_CACHE:
        _FM_CACHE[f] = sc.read_frontmatter(f) or {}
    return _FM_CACHE[f]


# --- шаг 1: сборка комплекта в целевой раскладке ---------------------------

def stage_kit(docs: Path, target: Path) -> Tuple[int, List[str]]:
    """Скопировать комплект без служебных файлов. (файлов, пропущено)."""
    copied = 0
    skipped: List[str] = []
    for p in sorted(docs.rglob("*")):
        rel = p.relative_to(docs)
        # точечные каталоги (.cursor, .claude, .vscode) — локальные обёртки IDE,
        # в комплект не входят (гид «Перенос комплекта», шаблон cursor/)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if p.is_dir():
            continue
        if p.name in _SKIP_NAMES or p.name.endswith(_SKIP_SUFFIXES):
            skipped.append(rel.as_posix())
            continue
        if len(rel.parts) == 1 and p.name in _REPO_ROOT_FILES:
            continue
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        copied += 1
    return copied, skipped


# --- шаг 4: условия переноса --------------------------------------------------

def question_candidates(src_root: Path, docs: Path,
                        sources: Optional[Path] = None,
                        explicit: Optional[Path] = None) -> List[Path]:
    """Где гейт ищет журнал open-questions.md, по порядку. Явный путь — первый;
    далее комплект и корень src; рядом с выгрузкой (sources/<service-id>/ —
    родитель каталога confluence/); sources/<имя комплекта>/ — общий
    репозиторий нескольких комплектов, где комплект лежит в
    output/<service-id>/, а журнал — в sources/<service-id>/ (FB-04
    common-dictionary 2026-10-15: оба прежних кандидата были пусты, гейт
    выдал READY при 13 открытых вопросах без долга)."""
    cands: List[Path] = []
    if explicit is not None:
        cands.append(explicit)
    cands += [docs / "open-questions.md", src_root / "open-questions.md"]
    if sources is not None:
        near = sources.parent if sources.name == "confluence" else sources
        cands.append(near / "open-questions.md")
    if docs.name and docs.name not in ("docs", "."):
        cands.append(src_root / "sources" / docs.name / "open-questions.md")
    out: List[Path] = []
    for c in cands:
        if c not in out:
            out.append(c)
    return out


def open_questions(src_root: Path, docs: Path, sources: Optional[Path] = None,
                   explicit: Optional[Path] = None) -> Tuple[Optional[Path], List[str]]:
    """Файл журнала и список открытых OQ (пусто — открытых нет)."""
    for cand in question_candidates(src_root, docs, sources, explicit):
        if cand.is_file():
            text = cand.read_text(encoding="utf-8", errors="replace")
            text = blank_code(text, repl="", inline=False)
            opened: List[str] = []
            entries = list(_OQ_ENTRY_RE.finditer(text))
            for i, m in enumerate(entries):
                end = entries[i + 1].start() if i + 1 < len(entries) else len(text)
                body = text[m.end():end]
                st = _OQ_STATUS_RE.search(body)
                status = st.group(1).strip().lower() if st else ""
                # класс — по первому слову статуса, как у сторожа B9: «закрыт (…; переоткрыть
                # при …)» — закрыт, подстрока «открыт» внутри пояснения не открывает вопрос (КК,
                # 7 записей); «частично» — открыт (асимметрия ошибок)
                cls = oq_status_class(status) if st else ""
                if not st or cls in ("открыт", "частично") or (
                        cls == "прочие" and any(w in status for w in _OPEN_WORDS)):
                    opened.append(m.group(1) + ("" if st else " (без строки «Статус»)"))
            return cand, opened
    return None, []


def check_transfer_conditions(gate: Gate, src_root: Path, docs: Path,
                              staged: Path, docs_repo: bool = False,
                              sources: Optional[Path] = None,
                              questions: Optional[Path] = None) -> None:
    matrix = staged / "traceability-matrix.md"
    mtext = matrix.read_text(encoding="utf-8", errors="replace") if matrix.is_file() else ""
    # правило переноса (решение владельца 2026-10-13): открытый вопрос либо
    # закрыт, либо переведён в строку долга матрицы, которая ссылается на
    # вопрос (OQ-NNN) и называет владельца; такой вопрос платформе виден
    # две формы перевода (решение 2026-10-14): (а) ответ на вопрос — отсутствующая
    # цель → строка «нет целевого артефакта…» с упоминанием OQ-NNN; (б) иначе →
    # строка «долг открытый вопрос: «…» … источник: OQ-NNN» с обязательными полями
    # ответственный / ограничение / закрытие — журнал в docs-репозиторий не
    # переезжает, вопрос должен жить в строке целиком (комментарий платформы 13.10)
    translated: set = set()
    incomplete: dict = {}
    unrecognized: List[str] = []
    if mtext:
        _reg, _debts, unrecognized = ld.parse_matrix_full(mtext)
        for _from, typ, _name, _owner, row in _debts:
            if typ.startswith("долг:"):
                f = ld.issue_fields(row) or {}
                if f.get("source"):
                    if f.get("missing"):
                        incomplete[f["source"]] = f["missing"]
                    else:
                        translated.add(f["source"])
            else:
                translated.update(_OQ_REF_RE.findall(row))
    heading = ld.debts_heading(mtext) if mtext else None
    if heading is not None and heading.lower() != ld._DEBTS_HEADING.lower():
        gate.add("✗", "CORE-20",
                 f"раздел долгов назван «{heading}» — норма «{ld._DEBTS_HEADING}»: по этому "
                 "имени раздел читают гейт и платформа (правило чтения долгов в README)",
                 check="имя раздела долгов")
    if unrecognized:
        # нераспознанный долг — непроверенное обязательство: READY с ним
        # подтвердить нельзя (ЗК-29 ОНБ-В; в самопроверке это ⚠, здесь ✗)
        gate.add("✗", "CORE-20",
                 f"строк раздела «Долги по ссылкам» не распознано: {len(unrecognized)} — "
                 "каждая строка раздела обязана быть одного из форматов долга "
                 "(см. link_debts); первая: " + unrecognized[0][:100],
                 check="нераспознанные долги")
    oq_file, opened = open_questions(src_root, docs, sources, questions)
    if oq_file is None and docs_repo:
        gate.add("i", "CORE-20", "режим репозитория документации: журнал open-questions.md "
                 "сюда не переезжает (TRF-02), открытые вопросы комплекта — строки долга вида "
                 "«открытый вопрос» в матрице (реестр долгов отчёта)",
                 check="открытые вопросы")
    elif oq_file is None:
        # FB-04 common-dictionary (2026-10-15): предупреждение давало READY
        # при 13 открытых вопросах без долга — журнал просто лежал в
        # sources/<service-id>/. Непроверенные вопросы — не подтверждённый
        # CORE-20, READY подтвердить нельзя (асимметрия ошибок)
        looked = ", ".join(
            c.relative_to(src_root).as_posix() if c.is_relative_to(src_root)
            else c.as_posix()
            for c in question_candidates(src_root, docs, sources, questions))
        gate.add("✗", "CORE-20", "журнал open-questions.md не найден — открытые "
                 f"вопросы не проверены, READY подтвердить нельзя (искали: {looked}); "
                 "укажите --questions <файл> или положите журнал в одно из этих мест",
                 check="открытые вопросы")
    else:
        still_open = [o for o in opened if o.split(" ")[0] not in translated
                      and o.split(" ")[0] not in incomplete]
        moved = [o for o in opened if o.split(" ")[0] in translated]
        partial = [o.split(" ")[0] for o in opened if o.split(" ")[0] in incomplete]
        if partial:
            gate.add("✗", "CORE-20", "строки долга из вопроса неполны: "
                     + "; ".join(f"{q} — нет полей {', '.join(incomplete[q])}" for q in partial[:6])
                     + " — вопрос должен жить в строке целиком: формулировка, причина, "
                       "ответственный, ограничение, закрытие (журнал в docs-репозиторий не переезжает)",
                     check="открытые вопросы")
        if still_open:
            gate.add("✗", "CORE-20", f"открытые вопросы без долга в матрице: {len(still_open)} "
                     f"({', '.join(still_open[:8])}{'…' if len(still_open) > 8 else ''}) — "
                     "платформа журнал src не читает; закрыть либо перевести в строку долга "
                     "матрицы, которая несёт вопрос целиком: формулировку, причину, ответственного, "
                     "ограничение, условие закрытия и источник OQ-NNN (если ответ — отсутствующий "
                     "документ, допустима строка долга по ссылке с упоминанием OQ-NNN)",
                     check="открытые вопросы")
        elif not partial:
            gate.add("✓", "CORE-20", f"открытых вопросов без долга нет ({oq_file.name})",
                     check="открытые вопросы")
        if moved:
            gate.add("i", "CORE-20", f"переведены в долги матрицы: {len(moved)} "
                     f"({', '.join(moved[:8])}{'…' if len(moved) > 8 else ''}) — вопрос не решён, "
                     "но виден платформе целиком, с ответственным и ограничением",
                     check="открытые вопросы")
    if matrix.is_file():
        am = sc._API_SECTION_RE.search(mtext)
        if am:
            tail = mtext[am.end():]
            nxt = re.search(r"^#{1,2}\s", tail, re.M)
            sect = tail[:nxt.start()] if nxt else tail
            rows = [ln for ln in sect.splitlines()
                    if ln.strip().startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", ln.strip())]
            ops = max(0, len(rows) - 1)  # минус шапка
            intc = sum(1 for f in staged.rglob("*.md")
                       if _fm(f).get("type") == "internal-contract")
            if ops == 0 and intc:
                gate.add("⚠", "SDLC-04", f"раздел есть, но пуст, а в комплекте {intc} описаний "
                         "собственных методов (internal-contract) — проверьте, есть ли у сервиса "
                         "API-операции и указаны ли их связи с требованиями: описание метода ещё не "
                         "означает, что для него есть API-контракт (пустой раздел допустим только при "
                         "отсутствии операций)",
                         check="матрица: раздел «Покрытие: API ↔ SRS»")
            else:
                gate.add("✓", "SDLC-04", "раздел есть" + (f", операций {ops}" if ops else
                                                        " (пуст — API-слой не ведётся)"),
                         check="матрица: раздел «Покрытие: API ↔ SRS»")
        else:
            gate.add("✗", "SDLC-04", "раздела нет — "
                     "планировщик платформы определяет по нему репозитории кода; "
                     "раздел обязателен даже пустым (шаблон матрицы)",
                     check="матрица: раздел «Покрытие: API ↔ SRS»")
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
        gate.add("✗", "TRF-03", f"контракты в комплекте ({what}) — OpenAPI/AsyncAPI "
                 "живут в api-specification/ репозитория кода, копии в "
                 "docs-репозиторий не переносятся", check="контракты в комплекте")
    else:
        gate.add("✓", "TRF-03", "каталога api/ и YAML-контрактов нет", check="контракты в комплекте")

    readme = staged / "README.md"
    rtext = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
    if not readme.is_file():
        gate.add("✗", "SDLC-08", "README.md комплекта отсутствует — точка входа "
                 "внешних читателей (шаблон docs-readme.md)", check="README комплекта")
    else:
        if sc._LEGEND_HEAD_RE.search(rtext):
            gate.add("✓", "SDLC-08", "README.md есть, раздел «Условные обозначения» есть",
                     check="README комплекта")
        else:
            gate.add("⚠", "SDLC-08", "README.md без раздела «Условные обозначения» — "
                     "внешние читатели не узнают контуры, части и типы комплекта",
                     check="README комплекта")
    # домен (решение владельца 2026-10-12): при режиме «Глоссарий: доменный»,
    # объявленном в README домена (в docs-репо — корень, в src — профиль),
    # глоссария в комплекте нет по правилу, не по недосмотру
    gmode = (sc.domain_glossary_mode(docs.parent / "README.md")
             or sc.domain_glossary_mode(src_root / "README.md"))
    for name, crit in (("service-vision.md", "SDLC-05"), ("glossary.md", "SDLC-05")):
        if (staged / name).is_file():
            gate.add("✓", crit, f"{name} есть", check=name)
        elif name == "glossary.md" and gmode == "domain":
            gate.add("✓", crit, "glossary.md в комплекте нет по правилу: режим "
                     "«Глоссарий: доменный» объявлен в README домена", check=name)
        else:
            gate.add("⚠", crit, f"{name} отсутствует (у платформы обязателен только "
                     "для нового сервиса; чек-лист DoR требует)", check=name)
    nested = [p for p in staged.rglob("docs") if p.is_dir()]
    if nested:
        gate.add("✗", "TRF-01", "внутри комплекта есть каталог docs/ — обёртка "
                 "недопустима (валидатор платформы: E_KIT_DOCS_WRAPPER)", check="обёртка docs/")
    # TRF-04 / SDLC-01: типы документов вне закрытого набора платформы — перечень
    # исключений к согласованию (комментарий платформы: объявление в README не равно
    # согласованию, если стандарт требует согласования)
    types: Dict[str, int] = {}
    for f in staged.rglob("*.md"):
        t = _fm(f).get("type")
        if t:
            types[t] = types.get(t, 0) + 1
    outside = {t: n for t, n in types.items() if t not in _PLATFORM_TYPES}
    if outside:
        prefix_of = {"internal-contract": "INTC", "lib-contract": "LIBC", "agent": "CHD",
                     "platform-function": "PLT", "status-model": "SM", "instruction": "INS",
                     "script": "SCRP"}
        declared = bool(rtext) and all(
            t in rtext or f"**{prefix_of.get(t, '')}**" in rtext for t in outside)
        gate.add("i", "TRF-04", "типы вне закрытого набора платформы: "
                 + ", ".join(f"{t} ×{n}" for t, n in sorted(outside.items()))
                 + (" — объявлены в README комплекта; согласование исключений — по стандарту "
                    "платформы (SDLC-01)" if declared else
                    " — в README комплекта не описаны (таблица типов «Условных обозначений»)"),
                 check="типы документов")
    elif types:
        gate.add("✓", "TRF-04", "все типы комплекта в закрытом наборе платформы",
                 check="типы документов")
    # SDLC-08: каталоги карточек без README-реестра
    no_readme: List[str] = []
    for d in sorted({f.parent for f in staged.rglob("*.md") if _fm(f).get("id")}):
        if d == staged or d.name in _SERVICE_DIRS:
            continue
        # мини-комплект зоны modules/<имя>/ (Д-49 п. 4): не каталог карточек комплекта —
        # состав ведёт его README (паспорт границы), у spec/ и interface/ реестра нет по шаблону
        if d.relative_to(staged).parts[0] == "modules":
            continue
        if not (d / "README.md").is_file():
            no_readme.append(d.relative_to(staged).as_posix())
    if no_readme:
        gate.add("⚠", "SDLC-08", f"каталоги с карточками без README-реестра: {len(no_readme)} "
                 f"({', '.join(no_readme[:6])}{'…' if len(no_readme) > 6 else ''}) — подключению не "
                 "мешает (обязателен README корня); реестр может быть общим в родительском каталоге, "
                 "тогда укажите это в README комплекта",
                 check="README каталогов")
    # FMT-01: защита от обхода — файл .txt в examples/, который разбирается как
    # JSON/YAML/XML, был рабочим примером, переименованным ради PASS
    parse_txt: List[str] = []
    for f in staged.rglob("*.txt"):
        if "examples" not in f.relative_to(staged).parts:
            continue
        raw = f.read_bytes()
        for ext in (".json", ".xml", ".yaml"):
            if raw.strip() and sc._parse_structured(raw.lstrip(b"\xef\xbb\xbf"), ext) is None \
                    and (ext != ".yaml" or raw.lstrip().startswith((b"{", b"[", b"<"))):
                parse_txt.append(f.relative_to(staged).as_posix())
                break
    if parse_txt:
        gate.add("⚠", "FMT-01", f"пример помечен фрагментом (.txt), но разбирается: "
                 f"{', '.join(parse_txt[:5])}{'…' if len(parse_txt) > 5 else ''} — проверьте "
                 "назначение файла, ожидаемый формат и источник: готовый рабочий пример несёт "
                 "расширение формата, .txt — только для фрагментов и примеров, невалидных в источнике",
                 check="структурные файлы")
    # CORE-09: внешние ссылки — доступность для платформы проверяется человеком
    hosts: Dict[str, int] = {}
    for f in staged.rglob("*.md"):
        text = f.read_text(encoding="utf-8", errors="replace")
        for u in _EXT_LINK_RE.findall(text):
            h = re.sub(r"^https?://([^/]+).*$", r"\1", u)
            hosts[h] = hosts.get(h, 0) + 1
    if hosts:
        gate.add("i", "CORE-09", "внешних ссылок " + str(sum(hosts.values())) + ": "
                 + ", ".join(f"{h} ×{n}" for h, n in sorted(hosts.items(), key=lambda x: -x[1])[:6])
                 + " — доступность для платформы и агентов проверяется вручную",
                 check="внешние ссылки")
    # долги, переживающие перенос (решение 2026-10-10, P-18): строки
    # раздела «Долги по ссылкам» едут как есть, а правило их чтения как
    # поручений объявляет README («Условные обозначения» → «Долги по
    # ссылкам»); есть долги без правила — внешний читатель их не поймёт
    if matrix.is_file():
        _, debts = ld.parse_matrix(mtext)
        if debts:
            cross = sum(1 for d in debts if d[3])
            n_issue = sum(1 for d in debts if d[1].startswith("долг:"))
            has_rule = readme.is_file() and "Долги по ссылкам" in rtext
            mark = "✓" if has_rule else "✗"
            gate.add(mark, "CORE-20",
                     f"перенесённые долги: {len(debts)}, из них межсервисных {cross}"
                     + (f", без отсутствующей цели {n_issue}" if n_issue else "")
                     + (" — правило чтения объявлено в README" if has_rule else
                        " — README не объясняет раздел «Долги по ссылкам» "
                        "(подраздел «Условных обозначений», шаблон docs-readme.md)"),
                     check="перенесённые долги")


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
    block: Optional[Tuple[str, str, str]] = None  # (знак подстрок, критерий, проверка)
    for ln in report:
        s = ln.rstrip()
        st = s.strip()
        if not st or st.startswith("ИТОГО") or st.startswith("i "):
            block = None
            continue
        if block is not None and s.startswith("   "):
            gate.add(block[0], block[1], st, check=block[2])  # подстроки — причины
            continue
        block = None
        if st.startswith(("✓", "✗", "⚠")):
            mark = st[0]
            crit = next((c for key, c in _SELFCHECK_CRITERIA if key in st), "ПРИБОР")
            if mark == "✗":
                gate.add(mark, crit, st[1:].strip())
                if st.endswith(":"):
                    block = ("i", crit, st[1:].strip().rstrip(":"))  # причины — информационно
            elif mark == "⚠" and "условные обозначения README" in st:
                block = ("⚠", "SDLC-08", "самоописание README")  # подстроки — сами сигналы
    total = next((ln for ln in report if ln.startswith("ИТОГО")), "")
    mode = ("полный профиль" if strict else "командный профиль") + (
        f", источники {sources.as_posix()}" if sources else ", БЕЗ источников")
    gate.add("✓" if ok else "✗", "ПРИБОР",
             f"{total.replace('ИТОГО: ', '')}", check=f"selfcheck ({mode})")


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
        gate.add("✗", crit, f"{where}: {f.get('detail', '')}"[:300], check=f"валидатор {code}")
    summary = data.get("summary", {})
    errors = summary.get("errors", len(findings))
    if errors == 0:
        gate.add("✓", "ВАЛИДАТОР", "ошибок нет", check="валидатор платформы")
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


# Репозиторий с несколькими комплектами (2026-10-28, docs-common-dictionary: двадцать
# справочников по подкаталогам, один CODEOWNERS в корне с правилами по каталогам). GitLab
# читает CODEOWNERS только из корня репозитория, docs/ и .gitlab/ — файл в подкаталоге
# комплекта владельцев не назначает. Поэтому в режиме репозитория документации владельцы
# и манифест ищутся не в корне комплекта, а в корне домена (родитель с таблицей сервисов
# в README — тот же признак, что у selfcheck «i домен: корень …»), иначе в вершине
# git-репозитория; комплект в корне репозитория — поведение прежнее.
_CODEOWNERS_PLACES = ("CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS")
# шапка секции GitLab: «[Имя]», «^[Имя]», «[Имя][2]», за ней — владельцы секции по умолчанию
_CO_SECTION_RE = re.compile(r"^\^?\[([^\]]+)\](?:\[\d+\])?(.*)$")
# правило по умолчанию: покрывает весь репозиторий, владельца каталога комплекта не называет
_CO_DEFAULT_PATTERNS = {"*", "**", "/*", "/**"}


def repo_root_for(kit: Path) -> Path:
    """Корень, где GitLab читает CODEOWNERS для комплекта: корень домена, иначе
    вершина git-репозитория (git недоступен — подъём по родителям до каталога с .git);
    ничего не найдено — сам комплект (прежнее поведение)."""
    kit = kit.resolve()
    dom = domain_context(kit)
    if dom is not None:
        return dom[0].resolve()
    try:
        r = subprocess.run(["git", "-C", str(kit), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            top = Path(r.stdout.strip()).resolve()
            if kit == top or top in kit.parents:
                return top
    except (OSError, subprocess.SubprocessError):
        pass
    for d in (kit, *kit.parents):
        if (d / ".git").exists():
            return d
    return kit


def _co_rules(text: str) -> List[Tuple[str, str, str]]:
    """(шаблон, владельцы, секция) по строкам CODEOWNERS; правило без владельцев берёт
    владельцев секции по умолчанию."""
    rules: List[Tuple[str, str, str]] = []
    sec, sec_owners = "", ""
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        m = _CO_SECTION_RE.match(ln)
        if m:
            sec, sec_owners = m.group(1).strip(), m.group(2).strip()
            continue
        pat, _, owners = ln.partition(" ")
        rules.append((pat, owners.strip() or sec_owners, sec))
    return rules


def _co_covers(pat: str, rel: str) -> bool:
    """Шаблон CODEOWNERS покрывает каталог комплекта rel (путь от корня через «/»):
    правила gitignore в упрощённом виде — ведущий «/» или «/» внутри шаблона — от корня,
    завершающий «/» или «/**» — каталог и всё под ним; шаблон из одного имени без «/» —
    каталог с таким именем на любом уровне."""
    p = pat
    if p.endswith("/**"):
        p = p[:-3]
    p = p.rstrip("/")
    anchored = p.startswith("/") or "/" in p.lstrip("/")
    parts = [x for x in p.strip("/").split("/") if x]
    comps = rel.split("/")
    if not parts:
        return False
    if anchored:
        return (len(parts) <= len(comps)
                and all(fnmatch.fnmatchcase(c, x) for c, x in zip(comps, parts)))
    return any(fnmatch.fnmatchcase(c, parts[0]) for c in comps)


def _check_codeowners(gate: Gate, kit: Path, root: Path, where: str) -> None:
    """CORE-04: CODEOWNERS по правилам GitLab (корень, docs/, .gitlab/ корня)"""
    found: Optional[Tuple[str, str]] = None
    for place in _CODEOWNERS_PLACES:
        f = root / place
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="replace")
            if any(ln.strip() and not ln.strip().startswith("#") for ln in text.splitlines()):
                found = (place, text)
                break
    rel = kit.relative_to(root).as_posix()
    dead = kit / "CODEOWNERS"
    if found is None:
        tail = (f"; файл {rel}/CODEOWNERS GitLab не читает и не засчитывается"
                if dead.is_file() else "")
        gate.add("✗", "CORE-04", f"CODEOWNERS нет ни в одном месте, где его читает GitLab "
                 f"({', '.join(str(root / x) for x in _CODEOWNERS_PLACES)}) или он пуст — "
                 f"владелец документации комплекта {rel} не назначен (чек-лист: обязательно до "
                 f"подключения){tail}", check="владельцы документации")
        return
    place, text = found
    rules = _co_rules(text)
    specific = [(p, o) for p, o, _s in rules
                if p not in _CO_DEFAULT_PATTERNS and _co_covers(p, rel)]
    if specific:
        pat, owners = specific[-1]
        gate.add("✓", "CORE-04", f"CODEOWNERS {where} ({place} корня репозитория): комплект "
                 f"{rel} покрыт правилом «{pat}» — {owners or 'владельцы секции не указаны'}",
                 check="владельцы документации")
    else:
        # секции GitLab действуют все сразу — правило «*» каждой секции показывается
        dflt = [f"«{p} {o}»".replace(" »", "»") + (f" [{sc}]" if sc else "")
                for p, o, sc in rules if p in _CO_DEFAULT_PATTERNS]
        shown = "; ".join(dflt) if dflt else "по умолчанию"
        gate.add("⚠", "CORE-04", f"владельцы комплекта {rel} назначены только правилом по "
                 f"умолчанию {shown} — добавить строку для каталога комплекта «/{rel}/» в "
                 f"{place} корня репозитория", check="владельцы документации")
    if dead.is_file():
        gate.add("i", "CORE-04", f"{rel}/CODEOWNERS GitLab не читает (владельцев назначает только "
                 "файл в корне репозитория, docs/ или .gitlab/) — можно удалить",
                 check="владельцы документации")


def _manifest_fields(mf: Path) -> str:
    try:
        data = json.loads(mf.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return f"не разбирается как JSON: {e}"
    if not isinstance(data, dict):
        return type(data).__name__
    named = [f"{k}={data[k]}" for k in ("name", "title") if k in data]
    return ", ".join(named) if named else "поля: " + ", ".join(sorted(data.keys()))


def check_target_repo(gate: Gate, out: Optional[Path], in_place: bool = False) -> None:
    """CORE-04 / SDLC-07: владельцы и манифест живут в репозитории назначения —
    проверяются при --out либо на месте (in_place: режим репозитория документации,
    когда --src и есть репозиторий назначения; комплект может лежать в подкаталоге —
    тогда ищутся в корне домена или git-репозитория); поля манифеста определяет владелец
    платформы, поэтому они печатаются для ручной сверки, а не сверяются."""
    if out is None:
        gate.add("i", "SDLC-07", "CODEOWNERS и gpb-manifest.json проверяются в репозитории "
                 "назначения — запустите гейт с --out <клон docs-репозитория>",
                 check="CODEOWNERS и манифест")
        return
    if not out.is_dir():
        gate.add("✗", "TRF-01", f"--out: каталог назначения не существует: {out}",
                 check="репозиторий назначения")
        return
    if not in_place and (out / "tasks").is_dir():
        # сторож forward (Д-43, 2026-10-15): после закрытия миграции правки
        # делаются в docs-репозитории задачами по постановкам tasks/<JIRA-ID>.md;
        # повторный перенос комплекта поверх затёр бы их — блокер, копирования нет
        gate.add("✗", "TRF-02", "в репозитории назначения есть каталог tasks/ — "
                 "forward-развитие уже начато, повторный перенос поверх запрещён "
                 "(правило: после закрытия миграции правки делаются в docs-репозитории)",
                 check="репозиторий назначения")
    where = "в репозитории документации" if in_place else "в репозитории назначения"
    kit = out
    if in_place:
        root = repo_root_for(out)
        if root != out.resolve():
            kit = out.resolve()
            out = root
    if kit is out:
        co = out / "CODEOWNERS"
        if co.is_file() and any(ln.strip() and not ln.strip().startswith("#")
                                for ln in co.read_text(encoding="utf-8",
                                                       errors="replace").splitlines()):
            gate.add("✓", "CORE-04", f"CODEOWNERS {where} есть и непустой",
                     check="владельцы документации")
        else:
            gate.add("✗", "CORE-04", f"CODEOWNERS в {out} отсутствует или пуст — владелец "
                     "документации не назначен (чек-лист: обязательно до подключения)",
                     check="владельцы документации")
    else:
        _check_codeowners(gate, kit, out, where)
        kit_mf = kit / "gpb-manifest.json"
        if kit_mf.is_file():
            # нужен ли платформе манифест на комплект внутри репозитория — вопрос к
            # платформе, гейт его не решает: печать без требования
            gate.add("i", "SDLC-07", f"манифест комплекта {kit.relative_to(out).as_posix()}/"
                     f"gpb-manifest.json: {_manifest_fields(kit_mf)}", check="манифест")
    mf = out / "gpb-manifest.json"
    if not mf.is_file():
        gate.add("⚠", "SDLC-07", f"gpb-manifest.json в {out} нет — обязателен по стандарту "
                 "repo-topology §3; поля — по требованиям платформы", check="манифест")
        return
    try:
        data = json.loads(mf.read_text(encoding="utf-8-sig"))
        keys = ", ".join(sorted(data.keys())) if isinstance(data, dict) else type(data).__name__
        gate.add("✓", "SDLC-07", f"gpb-manifest.json разбирается; поля: {keys} — обязательный "
                 "состав сверить вручную по требованиям платформы", check="манифест")
    except (OSError, ValueError) as e:
        gate.add("✗", "SDLC-07", f"gpb-manifest.json не разбирается как JSON: {e}", check="манифест")


# --- оркестровка ----------------------------------------------------------------

def detect_layout(src_root: Path, docs_name: str) -> Tuple[Optional[Path], bool]:
    """(каталог комплекта, режим репозитория документации). Рабочий репозиторий
    миграции несёт комплект в `docs/`; репозиторий документации (целевой,
    `docs-<service-id>`) — в корне: там есть матрица трассировки, а `docs/` нет.
    Ключ --docs . включает режим явно."""
    docs = src_root / docs_name
    if docs_name in (".", "") or docs.resolve() == src_root.resolve():
        return src_root, True
    if docs.is_dir():
        return docs, False
    if (src_root / "traceability-matrix.md").is_file():
        return src_root, True
    return None, False


def run_gate(src_root: Path, docs_name: str = "docs", out: Optional[Path] = None,
             keep: Optional[Path] = None, validator: Optional[Path] = None,
             layout: Optional[Path] = None, no_validator: bool = False,
             sources: Optional[Path] = None, strict: bool = False,
             fmt: str = "log",
             questions: Optional[Path] = None, after_step: bool = False,
             baseline: Optional[Path] = None) -> Tuple[List[str], bool, dict]:
    """fmt: "log" — журнал в порядке проверок (по умолчанию для вызова из кода и
    тестов); "table" — markdown-таблица с группировкой и легендой меток.

    Режим репозитория документации (2026-10-14): если комплект лежит в корне
    --src (целевой `docs-<service-id>`), гейт проверяет его на месте — без
    сборки «из docs/», без ожидания журнала вопросов, с проверкой CODEOWNERS и
    манифеста в самом репозитории; --out в этом режиме не имеет смысла и
    отклоняется. Отчёт читается как расстояние комплекта до действующего
    стандарта, а не как проверка переноса.

    Лёгкий режим after_step (Д-49 п. 1): та же сборка и валидатор платформы, прибор
    selfcheck не гоняется (вердикт прибора — в сдаче захода), критерии конца миграции
    понижены по закрытому списку _AFTER_STEP_DOWNGRADE, --out отклоняется; вердикт —
    «ФОРМА ПЕРЕНОСИМА / ФОРМА НЕ ПЕРЕНОСИМА», слово READY не печатается. baseline —
    прошлый отчёт гейта (--report): под итогом новые и ушедшие блокеры (оба режима)."""
    _FM_CACHE.clear()
    gate = Gate()
    docs, docs_repo = detect_layout(src_root, docs_name)
    if docs is None:
        gate.add("✗", "TRF-01", f"каталог комплекта не найден: {src_root / docs_name} "
                 "(рабочий репозиторий несёт комплект в docs/; у репозитория документации "
                 "матрица трассировки лежит в корне — тогда гейт сам включает режим "
                 "репозитория документации)")
        lines = gate.render() + [f"ИТОГ: {_verdict(False, after_step)}"]
        return lines, False, {"verdict": _verdict(False, after_step), "lines": gate.lines}
    if docs_repo and out is not None:
        gate.add("✗", "TRF-01", "--out не применим в режиме репозитория документации: "
                 "--src уже является репозиторием назначения")
        lines = gate.render() + [f"ИТОГ: {_verdict(False, after_step)}"]
        return lines, False, {"verdict": _verdict(False, after_step), "lines": gate.lines}
    if after_step and out is not None:
        gate.add("✗", "TRF-01", "--out не применим в режиме --after-step: лёгкий гейт "
                 "проверяет форму после захода, перенос — только полным гейтом")
        lines = gate.render() + [f"ИТОГ: {_verdict(False, after_step)}"]
        return lines, False, {"verdict": _verdict(False, after_step), "lines": gate.lines}
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
        if docs_repo:
            gate.add("i", "РЕЖИМ", "репозиторий документации: комплект проверяется на месте "
                     "(в корне --src); условия переноса читаются как соответствие действующей "
                     "раскладке, а не как проверка переноса", check="раскладка")
            gate.add("✓", "TRF-01", f"комплект в корне репозитория документации: {copied} файлов",
                     check="комплект в целевой раскладке")
            if skipped:
                gate.add("✗", "TRF-02", f"служебные файлы миграции лежат в репозитории "
                         f"документации: {', '.join(skipped[:6])}{'…' if len(skipped) > 6 else ''} "
                         "— удалить (журналы и черновики остаются в рабочем репозитории)",
                         check="служебные файлы миграции")
            else:
                gate.add("✓", "TRF-02", "служебных файлов миграции в репозитории нет",
                         check="служебные файлы миграции")
        else:
            gate.add("✓", "TRF-01", f"собран в корне без обёртки docs/: {copied} файлов",
                     check="комплект в целевой раскладке")
            gate.add("✓", "TRF-02", f"служебных файлов миграции не перенесено: {len(skipped)}"
                     + (f" ({', '.join(skipped[:4])}{'…' if len(skipped) > 4 else ''})" if skipped
                        else " (в docs/ их не было)"),
                     check="служебные файлы миграции")
        if sources is None:
            sources = find_sources(src_root)
        if after_step:
            gate.add("i", "ПРИБОР", "selfcheck не гонялся (режим --after-step), вердикт "
                     "прибора — в сдаче", check="прибор selfcheck")
            check_staged_root(gate, staged)
        elif sources is None and docs_repo:
            gate.add("i", "ПРИБОР", "режим репозитория документации: выгрузки источников здесь "
                     "нет по построению — прибор идёт по внутренним сторожам; сверка с "
                     "источником — в рабочем репозитории (--sources, если нужна)")
        elif sources is None:
            gate.add("⚠", "ПРИБОР", "каталог выгрузки источников не найден "
                     "(sources/confluence, confluence) — прибор идёт без сверки "
                     "с источником; задайте --sources")
        if not after_step:
            run_selfcheck(gate, staged, sources, strict)
        check_transfer_conditions(gate, src_root, docs, staged, docs_repo,
                                  sources, questions)
        if after_step:
            gate.downgrade(_AFTER_STEP_DOWNGRADE, _AFTER_STEP_NOTE)
        check_target_repo(gate, src_root if docs_repo else out, in_place=docs_repo)
        if no_validator:
            gate.add("⚠", "ВАЛИДАТОР", "валидатор платформы отключён ключом "
                     "--no-validator — структурная половина гейта не выполнена")
        else:
            run_validator(gate, staged, validator or _DEFAULT_VALIDATOR, layout)
        ready = gate.blockers == 0
        n_warn = sum(1 for m, _, _, _ in gate.lines if m == "⚠")
        lines = gate.render_table() if fmt == "table" else gate.render()
        if fmt == "table":
            lines.append("")
        delta: Optional[Tuple[List[Tuple[str, str, str]], int]] = None
        base_err = ""
        if baseline is not None:
            base = read_baseline(baseline)
            if base is None:
                base_err = (f"✗ --baseline: в {baseline} нет таблицы гейта «Статус | Критерий | "
                            "Проверка | Результат» — дельта не посчитана")
            else:
                delta = baseline_delta(gate, base)
        new_txt = "—" if delta is None else str(len(delta[0]))
        if after_step:
            lines.append(f"ИТОГ: {_verdict(ready, True)}" + ("" if ready else
                         f": блокеров {gate.blockers}") + f" (новых {new_txt}), "
                         f"предупреждений {n_warn}")
        else:
            lines.append(f"ИТОГ: {'READY' if ready else 'NOT READY'} — блокеров {gate.blockers}"
                         + (f" (новых {new_txt})" if baseline is not None else "")
                         + f", предупреждений {n_warn}")
        if base_err:
            lines.append(base_err)
        if delta is not None:
            new, gone = delta
            lines.append(f"новых блокеров {len(new)}" + (": " if new else "")
                         + "; ".join(f"[{c}] {t[:160]}" for c, _, t in new[:20])
                         + ("…" if len(new) > 20 else ""))
            lines.append(f"ушло {gone} (относительно {baseline.name})")
        if fmt == "table":
            lines.append("")
            lines.append(_LEGEND)
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
        debts_rows: List[dict] = []
        mpath = staged / "traceability-matrix.md"
        if mpath.is_file():
            _, debts = ld.parse_matrix(mpath.read_text(encoding="utf-8", errors="replace"))
            referrers = card_referrers(staged) if debts else {}
            for from_ids, typ, name, owner, row in debts:
                oq = ", ".join(sorted(set(_OQ_REF_RE.findall(row))))
                issue = ld.issue_fields(row) if typ.startswith("долг:") else None
                kind = issue["kind"] if issue else "нет цели"
                affected = sorted({r for fid in from_ids for r in referrers.get(fid, ())})
                debts_rows.append({
                    "from": ", ".join(from_ids) or "—", "type": typ,
                    "name": name or "—",
                    "owner": (issue.get("responsible") if issue else owner) or "аналитик сервиса",
                    "cross": bool(owner), "oq": oq or "—", "kind": kind,
                    "affected": affected,
                    "closure": (issue.get("closure") if issue else None) or _CLOSURE_BY_KIND[kind]})
        return lines, ready, {"verdict": _verdict(ready, after_step),
                              "after_step": after_step,
                              "new_blockers": None if delta is None else len(delta[0]),
                              "blockers": gate.blockers, "warnings": n_warn,
                              "lines": gate.as_dicts(),
                              "src": str(src_root), "sources": str(sources) if sources else None,
                              "strict": strict, "debts": debts_rows, "docs_repo": docs_repo,
                              "src_git": src_git_state(src_root),
                              "validator": validator_origin(validator or _DEFAULT_VALIDATOR,
                                                            layout, no_validator)}
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


# условие закрытия долга по виду (решение 2026-10-14; дом правила — README комплекта,
# «Долги по ссылкам»); поле «закрытие:» строки второго формата уточняет его для долга
_CLOSURE_BY_KIND = {
    "нет цели": "цель появилась, имя заменено ссылкой, содержание цели проверено (не заглушка)",
    "открытый вопрос": "ответ записан ответственным в карточке FROM-ID, строка снята",
    "противоречие": "осталась одна формулировка, вторая исправлена ответственным",
    "правило на изображении": "правило записано текстом в карточке по подтверждению владельца",
    "источник недоступен": "доступ получен либо материал перенесён с указанием источника",
}
_MD_LINK_RE = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)]*)?\)")


def _verdict(ready: bool, after_step: bool) -> str:
    if after_step:
        return "ФОРМА ПЕРЕНОСИМА" if ready else "ФОРМА НЕ ПЕРЕНОСИМА"
    return "READY" if ready else "NOT READY"


def card_referrers(staged: Path) -> Dict[str, List[str]]:
    """ID карточки → ID карточек, ссылающихся на неё относительной ссылкой («Затронуто»
    долгом шире FROM-ID — комментарий платформы 13.10; считает прибор, не человек).
    Матрица и README-реестры не считаются: они ссылаются на всё."""
    id_of: Dict[Path, str] = {}
    for f in staged.rglob("*.md"):
        fid = _fm(f).get("id")
        if fid and f.name.lower() != "readme.md":
            id_of[f.resolve()] = str(fid)
    out: Dict[str, set] = {}
    for f in staged.rglob("*.md"):
        if f.name.lower() in ("readme.md", "traceability-matrix.md"):
            continue
        src_id = id_of.get(f.resolve())
        if not src_id:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for rel in _MD_LINK_RE.findall(text):
            try:
                target = (f.parent / rel).resolve()
            except OSError:
                continue
            tid = id_of.get(target)
            if tid and tid != src_id:
                out.setdefault(tid, set()).add(src_id)
    return {k: sorted(v) for k, v in out.items()}


def validator_origin(validator: Path, layout: Optional[Path], disabled: bool) -> str:
    """Происхождение копии валидатора для шапки отчёта (ответ платформы 13.10: отчёту
    нужны версии инструмента и раскладки). Берётся из README рядом с копией; режим —
    временный git-репозиторий от пустого коммита, поэтому все находки считаются новыми."""
    if disabled:
        return "отключён ключом --no-validator"
    readme = validator.parent.parent / "README.md"
    origin = "копия без README о происхождении"
    if readme.is_file():
        txt = readme.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"снимок[^\n]*?от (\d{4}-\d{2}-\d{2})", txt)
        sha = re.search(r"коммит\s+`([0-9a-f]{7,40})`", txt)
        ver = re.search(r"artifact-consistency`?\s*v(\d+(?:\.\d+)*)", txt)
        origin = ("копия от " + (m.group(1) if m else "?")
                  + (f", eco-config `{sha.group(1)[:7]}`" if sha else "")
                  + (f", artifact-consistency v{ver.group(1)}" if ver else ""))
    lay = f"раскладка `{layout}`" if layout else "раскладка — умолчания валидатора (ЭКО)"
    return f"{origin}; {lay}; режим — временный git-репозиторий от пустого коммита, все находки новые"


def src_git_state(src_root: Path) -> dict:
    """Коммит, ветка и признак незакоммиченных изменений src-репозитория (CORE-05/07):
    отчёт фиксирует, какая версия документации проверена."""
    def g(*args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(src_root), *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=30)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:  # noqa: BLE001
            return ""
    commit = g("rev-parse", "--short", "HEAD")
    return {"commit": commit or "не git-репозиторий",
            "branch": g("rev-parse", "--abbrev-ref", "HEAD") or "—",
            "dirty": bool(g("status", "--porcelain")) if commit else False,
            # автор проверки — из git-конфигурации того, кто запустил гейт
            # (комментарий платформы 13.10: отчёту нужны автор, дата, версии)
            "author": g("config", "user.name") or "не указан"}


def canon_cut_of(src_root: Path) -> str:
    """Срез канона из строки профиля источников (README.md src-репозитория)."""
    for cand in (src_root / "README.md", src_root / "sources" / "README.md"):
        if cand.is_file():
            m = sc._CANON_CUT_RE.search(cand.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m.group(1)
    return "не указан"


def run_gate_table_lines(data: dict) -> List[str]:
    """Таблица из уже собранных данных (когда на экран печатался журнал)."""
    g = Gate()
    for r in data.get("lines", []):
        g.add(r["mark"], r["criterion"], r["text"], r.get("check"))
    lines = g.render_table()
    nb = data.get("new_blockers")
    new_txt = "—" if nb is None else str(nb)
    if data.get("after_step"):
        itog = (f"ИТОГ: {data.get('verdict')}" + ("" if not data.get("blockers") else
                f": блокеров {data.get('blockers', 0)}") + f" (новых {new_txt}), "
                f"предупреждений {data.get('warnings', 0)}")
    else:
        itog = (f"ИТОГ: {data.get('verdict')} — блокеров {data.get('blockers', 0)}"
                + (f" (новых {new_txt})" if nb is not None else "")
                + f", предупреждений {data.get('warnings', 0)}")
    lines += ["", itog, "", _LEGEND]
    return lines


def write_report(path: Path, src_root: Path, table_lines: List[str], data: dict) -> None:
    import datetime as _dt
    git = data.get("src_git") or {}
    repo_kind = ("Репозиторий документации (режим проверки на месте: комплект в корне, перенос не "
                 "выполняется)" if data.get("docs_repo") else "Рабочий репозиторий")
    head = [f"# Гейт переноса: {src_root.name}", ""]
    if data.get("after_step"):
        head += ["Режим: после захода (--after-step) — форма комплекта в целевой раскладке; "
                 "прибор selfcheck не гонялся, критерии конца миграции понижены; перенос — "
                 "только полным гейтом.", ""]
    head += [
            f"Дата: {_dt.date.today().isoformat()}. Вид допуска: **техническое подключение сервиса** "
            "(допуск задач к разработке — платформа). "
            f"{repo_kind}: `{src_root}`, коммит `{git.get('commit', '?')}`, ветка "
            f"`{git.get('branch', '?')}`"
            + (", **есть незакоммиченные изменения** — проверено рабочее дерево, не коммит"
               if git.get("dirty") else "") + ". "
            f"Автор проверки: {git.get('author', 'не указан')}. "
            f"Срез канона по профилю: `{canon_cut_of(src_root)}`. "
            f"Источники: `{data.get('sources') or 'не найдены'}`; профиль прибора: "
            f"{'полный' if data.get('strict') else 'командный'}. Валидатор платформы: "
            f"{data.get('validator') or 'не запускался'}. Инструмент — `transfer_gate.py`; "
            "таблица — приложение к протоколу самопроверки чек-листа DoR (раздел «Технологическая "
            "совместимость»).", ""]
    body = list(table_lines)
    # реестр долгов (комментарии платформы 13.10: до подключения обязателен реестр долгов с
    # владельцем; долг ограничивает использование карточки FROM-ID до закрытия)
    debts = data.get("debts") or []
    body += ["", "## Реестр долгов", ""]
    if debts:
        n_issue = sum(1 for d in debts if d.get("kind", "нет цели") != "нет цели")
        body += [f"Строк в разделе матрицы «Долги по ссылкам»: {len(debts)}, из них межсервисных "
                 f"{sum(1 for d in debts if d['cross'])}, без отсутствующей цели {n_issue} (имя раздела "
                 "историческое: раздел содержит все долги комплекта). Правило чтения — README комплекта, "
                 "«Условные обозначения» → «Долги по ссылкам». Долг ограничивает использование затронутых "
                 "карточек: карточки FROM-ID и карточек, которые на неё ссылаются; до закрытия задача, "
                 "реализующая или меняющая их поведение, допускается к разработке только по записанному "
                 "решению владельца документации. Условие закрытия — по виду долга; поле «закрытие» строки "
                 "уточняет его.", "",
                 "| FROM-ID | Вид | Цель или формулировка | Ответственный | Затронуто (ссылаются на FROM-ID) "
                 "| Условие закрытия | Из вопроса |", "|---|---|---|---|---|---|---|"]
        esc = lambda x: str(x).replace("|", "\\|")  # noqa: E731
        for d in debts:
            kind = d.get("kind", "нет цели")
            kind_txt = f"нет цели: {d['type']}" if kind == "нет цели" else kind
            aff = d.get("affected") or []
            aff_txt = (f"{len(aff)}: " + ", ".join(aff[:6]) + ("…" if len(aff) > 6 else "")) if aff else "—"
            body.append(f"| {esc(d['from'])} | {esc(kind_txt)} | {esc(d['name'])} | {esc(d['owner'])} | "
                        f"{esc(aff_txt)} | {esc(d.get('closure', ''))} | {esc(d['oq'])} |")
    else:
        body.append("Долгов в матрице нет.")
    body += ["", "## Ручная часть протокола до подключения", "",
             "Гейт закрывает автоматические критерии раздела 1. До технического подключения человек "
             "дополнительно подтверждает (комментарии платформы к DoR v1.2, 13.10.2026):", ""]
    body += [f"- **{c}** — {t}" for c, t in _MANUAL_BEFORE_CONNECT]
    body += ["", "Критерии раздела 1 без автоматической проверки (ручная с доказательством):", ""]
    body += [f"- **{c}** — {t}" for c, t in _MANUAL_SECTION1]
    body += ["", "Поля решения (заполняет владелец): разрешённый объём разработки; запрещённый или "
             "непроверенный объём; решение и подтвердивший владелец."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(head + body) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Гейт переноса комплекта src-<service> → docs-<service>: READY / NOT READY; "
                    "--after-step — форма после захода: ФОРМА ПЕРЕНОСИМА / НЕ ПЕРЕНОСИМА")
    ap.add_argument("--src", required=True, type=Path, help="корень клона src-репозитория")
    ap.add_argument("--docs", default="docs",
                    help="каталог комплекта внутри src (docs); «.» — комплект в корне (режим "
                         "репозитория документации; включается и сам, если docs/ нет, а матрица "
                         "трассировки лежит в корне)")
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
    ap.add_argument("--questions", type=Path, default=None,
                    help="журнал открытых вопросов комплекта (по умолчанию ищется: "
                         "<docs>/, <src>/, рядом с выгрузкой, sources/<имя комплекта>/)")
    ap.add_argument("--strict", action="store_true",
                    help="полный профиль прибора (маркеры сокращения — брак)")
    ap.add_argument("--log", action="store_true",
                    help="журнал в порядке проверок вместо таблицы (терминал, CI)")
    ap.add_argument("--report", type=Path, default=None,
                    help="записать таблицу с шапкой в markdown-файл (приложение к протоколу)")
    ap.add_argument("--json", action="store_true", help="дополнительно вывести JSON")
    ap.add_argument("--after-step", action="store_true",
                    help="лёгкий гейт после захода (Д-49): без повторного selfcheck, критерии конца "
                         "миграции понижены, вердикт «ФОРМА ПЕРЕНОСИМА / НЕ ПЕРЕНОСИМА», --out отклоняется")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="прошлый отчёт гейта (--report): под итогом новые и ушедшие блокеры")
    a = ap.parse_args()
    fmt = "log" if a.log else "table"
    try:
        lines, ready, data = run_gate(a.src.resolve(), a.docs, a.out, a.keep,
                                      a.validator, a.layout, a.no_validator,
                                      a.sources.resolve() if a.sources else None,
                                      a.strict, fmt,
                                      a.questions.resolve() if a.questions else None,
                                      a.after_step, a.baseline)
    except Exception as e:  # noqa: BLE001
        print(f"✗ гейт не отработал: {e!r}")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for ln in lines:
        print(ln)
    if a.report is not None:
        write_report(a.report, a.src.resolve(), lines if fmt == "table" else
                     run_gate_table_lines(data), data)
        print(f"i отчёт записан: {a.report}")
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
