# Реестр структурных фактов канона

Структурный факт — утверждение о раскладке, адресах, именах и
идентификаторах, которое по необходимости повторяется во многих файлах
канона: шаблон обязан показать каталог, скилл — назвать путь, по которому
пишет. У такого факта один нормативный **дом**; остальные файлы —
**потребители**: упоминают факт в объёме, нужном для действия, и числятся
здесь. Реестр существует только вместе со сторожем
(`_meta/tools/structural_facts.py`): он ищет **сигнатуры** факта по всему
канону и сверяет найденные файлы со списком — список не ведётся руками,
а проверяется при каждом прогоне, поэтому полон по построению.

Что считается: файл с сигнатурой вне списка — предупреждение «внести в
реестр либо убрать упоминание»; потребитель без сигнатур — «снять из
реестра». Сторож не отличает норму от упоминания — свести формулировки к
одной остаётся делом ревью. Факт вне реестра живёт как раньше: при
изменении — поиск руками. Запись заводится, когда факт меняется и его всё
равно приходится искать.

Формат записи: заголовок `## SF-NN. <название>`; строка `- Факт:`; строка
`- Дом:` (пути от корня репозитория через `;`, пояснение в скобках); блоки
` ```сигнатуры ` (буквальные подстроки, регистр важен, по одной в строке),
` ```потребители ` (пути от корня репозитория), ` ```вне-учёта ` (шаблоны
файлов, где сигнатура законна, но файл не потребитель нормы: чужие
материалы, снимки). Зона сканирования сторожа — `_meta/`, `AGENTS.md`,
`README.md`, `.cursor/`, `.claude/`; комплекты (`output/`) не нормы.

Запуск: `python _meta/tools/structural_facts.py --repo <корень клона>`
(`--strict` — код возврата 1 при предупреждениях). Сторож также печатает
свой отчёт при приёме среза канона (`accept_canon.py`).

---

## SF-01. Контракты API живут в репозитории кода

- Факт: контракты OpenAPI/AsyncAPI сервиса — в `api-specification/`
  репозитория кода `ECO_BE/ms-<service-id>`; в комплекте копий YAML нет,
  каталог `api/` не создаётся; адрес контрактов чужого сервиса строится по
  коду сервиса (решение руководителя 2026-10-06).
- Дом: `_meta/migration/cross-service-addressing.md` (§2 термин API First, §5.2 адрес по коду сервиса)
- Стандарт: eco-techbook `standards/analytics/conventions.md` §5.1 (вне зоны сканирования).

```сигнатуры
api-specification
docs/api/
`api/`
```

```потребители
AGENTS.md
README.md
_meta/ai-sdlc.md
_meta/migration/prompt-plan.md
_meta/skills/create-artifact.md
_meta/skills/create-contract-call.md
_meta/skills/create-docs-readme.md
_meta/skills/create-internal-contracts.md
_meta/skills/validate-sync-contracts.md
_meta/skills/verify-vs-sources.md
_meta/templates/contract-call.md
_meta/templates/docs-readme.md
_meta/templates/internal-contracts.md
_meta/tools/selfcheck.py
_meta/migration/reference.md
_meta/tools/README.md
_meta/tools/transfer_gate.py
_meta/tools/passport_sync.py
```

```вне-учёта
_meta/references/*
_meta/skills/api-first-*
_meta/tools/structural_facts.py
```

## SF-02. Разделы README комплекта, читаемые внешними потребителями

- Факт: раздел README комплекта «Условные обозначения» с подразделами
  «Контуры», «Подсервисы» (таблица кодов частей: «Код», «Каталог»,
  «Название»), «Типы артефактов» и «Поля frontmatter» — самоописание
  комплекта; по этим именам его читают инструменты и агенты вне
  комплекта (прибор: сторож слота части и сторож самоописания; платформа
  AI Factory — паспорт ЭКО «Как читать» п. 2, раздел 3). Имена
  подразделов стабильны; переименование — согласованное изменение с
  внешним потребителем.
- Дом: `_meta/templates/docs-readme.md` (раздел «Условные обозначения»)
- Внешний потребитель: платформа AI Factory (вне зоны сканирования).

```сигнатуры
Условные обозначения
Подсервисы
Поля frontmatter
Долги по ссылкам
```

```потребители
_meta/migration/cross-service-addressing.md
_meta/skills/create-docs-readme.md
_meta/tools/selfcheck.py
_meta/tools/transfer_gate.py
_meta/tools/passport_sync.py
_meta/migration/reference.md_meta/skills/create-nfr.md
_meta/templates/nfr.md
```

```вне-учёта
_meta/references/*
_meta/tools/structural_facts.py
```

## SF-03. Домен сервисов: рамка, слот сервиса, запись каталога на сервис

- Факт: несколько сервисов одной команды ведутся одним docs-репозиторием с рамкой
  домена в корне (`README.md` с таблицей сервисов, `domain-vision.md` `VIS-000`,
  `glossary.md` `GLO-000`); каждый сервис — комплект `<service-id>/` со своей
  записью каталога; идентификаторы комплекта несут слот сервиса сразу после
  префикса (решение владельца 2026-10-11). Уточнения 2026-10-12: таблица
  сервисов `service-id | Слот | Название | Вход` (`service-id` — каталог
  комплекта, слот сервиса — буквы в ID); концепция домена — свой шаблон
  `domain-vision.md`; глоссарий в режиме «доменный» либо «доменный +
  указатели» по объявлению в README домена; запись каталога — на комплект.
- Дом: `_meta/migration/cross-service-addressing.md` (§4.3 «Подсервисы и домены»)
- Стандарт: eco-techbook `standards/analytics/repo-topology.md` §3 «Рамка домена», `conventions.md` §3.2 и §5 «Слоты сервиса и части» (вне зоны сканирования).

```сигнатуры
domain-vision.md
сервис <service-id>
VIS-000
GLO-000
таблица сервисов
таблицей сервисов
таблице сервисов
слот сервиса
```

```потребители
AGENTS.md
_meta/migration/cross-service-addressing.md
_meta/migration/reference.md
_meta/migration/prompt-plan.md
_meta/migration/prompt-coordinator.md
_meta/migration/track-coordinator.md
_meta/migration/track-manual.md
_meta/templates/docs-readme.md
_meta/templates/service-vision.md
_meta/templates/domain-vision.md
_meta/templates/glossary.md
_meta/templates/sources-readme.md
_meta/skills/create-docs-readme.md
_meta/skills/create-service-vision.md
_meta/skills/create-glossary.md
_meta/skills/create-artifact.md
_meta/tools/selfcheck.py
```

```вне-учёта
_meta/references/*
_meta/tools/structural_facts.py
```
