# AI-docs-O2new — аналитика сервиса «Открытие дополнительного счета» (О2+)

Репозиторий для подготовки **чистового комплекта документов аналитики** по сервису открытия дополнительного счёта в АС Экосистема. Документы пишутся с нуля, структурированы для доработки **ИИ-агентами**.

## С чего начать

**Мигрируете свой сервис из Confluence этим каноном?** Единственная
точка входа: → [`_meta/migration/README.md`](_meta/migration/README.md)
(выбор варианта миграции, порядок чтения, инструкции треков, гид и
промпты — весь комплект в одном каталоге).

**Что из себя представляет сервис** (назначение, клиентская и банковская части, границы) — в концепции:

→ [`output/open-add-account/docs/service-vision.md`](output/open-add-account/docs/service-vision.md)

Навигация по комплекту, карта обозначений (**CL** / **BNK** / **SYS** и префиксы ID) — в:

→ [`output/open-add-account/docs/README.md`](output/open-add-account/docs/README.md)

## Где искать методологию (после разноса)

Этот репозиторий — **пилот**. Копии методологии перенесены в org-репозитории (канон для онбординга и новых docs-репо). Локальный [`_meta/`](_meta/) **остаётся** и не удаляется.

| Что нужно | Куда смотреть | GitLab |
| --- | --- | --- |
| Гайд аналитика, git-start, terms, окружение ПО | [eco-kb / analytics](https://gitlab.gboteam.ru/ED/eco-kb/-/tree/master/analytics) | `https://gitlab.gboteam.ru/ED/eco-kb` |
| Conventions, notation, repo-topology | [eco-techbook / standards/analytics](https://gitlab.gboteam.ru/ED/eco-techbook/-/tree/master/standards/analytics) | `https://gitlab.gboteam.ru/ED/eco-techbook` |
| Git-workflow, gitlab-settings, API First howto | [eco-techbook / cookbook/analytics](https://gitlab.gboteam.ru/ED/eco-techbook/-/tree/master/cookbook/analytics) | то же |
| Doc-as-code (концепт) | [eco-techbook / architecture/concepts/doc-as-code.md](https://gitlab.gboteam.ru/ED/eco-techbook/-/blob/master/architecture/concepts/doc-as-code.md) | то же |
| Скиллы и шаблоны (ещё не перенесены) | пока [`_meta/skills/`](_meta/skills/), [`_meta/templates/`](_meta/templates/); целевой дом — [drcs-ai-toolkit](https://gitlab.gboteam.ru/drcs/drcs-ai-toolkit) | фаза 2 плана |

Практика день за днём: [analyst-docs-guide.md](https://gitlab.gboteam.ru/ED/eco-kb/-/blob/master/analytics/analyst-docs-guide.md). Установка ПО: [environment-setup.md](https://gitlab.gboteam.ru/ED/eco-kb/-/blob/master/analytics/environment-setup.md).

## Версия сервиса, которую описываем

Документация в `output/` описывает **актуальную версию сервиса** — включая оплату комиссии за открытие счёта через QR-код / СБП (Систему быстрых платежей): шаг оплаты комиссии в клиентском пути, статусы `QRC_*`, связанные экраны и интеграции.

Код в `sources/code/` лежит по сервисам (`open-add-account/`, `inquiry/`). Для О2+ — два среза: **`with-qr/`** — актуальный (соответствует Confluence, включая QR/СБП; рабочий срез для сверки и выгрузки контрактов) и **`before-qr/`** — baseline до QR (историческая сверка). Контракты `docs/api/` пока выгружены из среза before-qr — их нужно перегенерировать из `with-qr/`.

## Структура репозитория

```
AI-docs-O2new/
├── README.md                 ← вы здесь
├── AGENTS.md                 # инструкции для ИИ-агентов (Cursor, Claude Code, OpenCode)
├── CLAUDE.md                 # обёртка AGENTS.md для Claude Code
├── _meta/                    # методология: конвенции, шаблоны, скиллы, AI SDLC
├── .cursor/                  # правила и команды агента для Cursor
├── .claude/                  # скиллы для Claude Code
├── output/                   # чистовая документация (целевые артефакты)
│   └── open-add-account/
│       └── docs/
│           ├── service-vision.md   # концепция сервиса (вход)
│           ├── glossary.md
│           ├── traceability-matrix.md
│           ├── brd/                # бизнес-требования
│           ├── srs/                # спецификация требований
│           └── api/                # контракты (REST, MQ)
└── sources/                  # черновые источники (read-only)
    ├── confluence/
    ├── code/
    ├── cleaned/
    └── Figma-screen-designs/
```

| Слой | Путь | Назначение |
|------|------|------------|
| **Output** | [`output/`](output/) | Готовая аналитика по сервисам |
| **Sources** | [`sources/`](sources/) | Исходные материалы для сверки; профиль — [`sources/README.md`](sources/README.md) (не редактировать выгрузки) |
| **Meta** | [`_meta/`](_meta/) | Пилотная копия: конвенции, git-workflow, шаблоны, скиллы, [`ai-sdlc.md`](_meta/ai-sdlc.md). **Канон правил/гайда** — в eco-techbook / eco-kb (см. [выше](#где-искать-методологию-после-разноса)) |

## Навигация по документации

| Уровень | README |
|---------|--------|
| Репозиторий | `README.md` (этот файл) |
| Output | [`output/README.md`](output/README.md) |
| Docs сервиса | [`output/open-add-account/docs/README.md`](output/open-add-account/docs/README.md) |
| Концепция сервиса | [`output/open-add-account/docs/service-vision.md`](output/open-add-account/docs/service-vision.md) |
| BRD | [`output/open-add-account/docs/brd/README.md`](output/open-add-account/docs/brd/README.md) |
| SRS | [`output/open-add-account/docs/srs/README.md`](output/open-add-account/docs/srs/README.md) |
| API | [`output/open-add-account/docs/api/README.md`](output/open-add-account/docs/api/README.md) |

## Источники (`sources/`)

Черновые материалы. Используются только для **сверки**, не копируются в output как есть.

| Путь | Содержание |
|------|------------|
| `sources/confluence/o2plus/` | **Актуальная выгрузка Confluence (от 15.07.2026)** — единственная используемая |
| `sources/confluence/` (остальные папки) | Устаревшие выгрузки — не использовать (см. [`sources/confluence/README.md`](sources/confluence/README.md)) |
| `sources/code/` | Архивы кода по сервисам (см. [`sources/code/README.md`](sources/code/README.md)) |
| `sources/code/open-add-account/` | О2+: срезы `with-qr/` и `before-qr/`; сводки из кода в `docs/` |
| `sources/code/inquiry/` | Запрос справок для ЮЛ (выгрузка кода) |
| `sources/cleaned/` | Предыдущий черновик комплекта |
| `sources/Figma-screen-designs/` | Макеты и UX-спецификация |

## Сервисы

| Сервис | Output | Статус |
|--------|--------|--------|
| Открытие дополнительного счета (О2+) | [`output/open-add-account/`](output/open-add-account/) | в работе |

Новые сервисы добавляются по шаблону: `output/{service-id}/docs/` (`service-vision.md`, `glossary.md`, `brd/`, `srs/`, `api/`).

## Комплект open-add-account (обзор)

| # | Раздел | Путь |
|---|--------|------|
| 1 | Service Vision | `docs/service-vision.md` |
| 2 | Глоссарий | `docs/glossary.md` |
| 3 | BRD | `docs/brd/` |
| 4 | SRS | `docs/srs/` |
| 5 | API | `docs/api/` |
| 6 | Матрица трассировки | `docs/traceability-matrix.md` |

Реестр открытых вопросов ведётся на уровне сервиса, вне переносимого комплекта `docs/`: `output/open-add-account/open-questions.md`.

## Принципы работы

1. **Output** — единственное целевое место для чистовой аналитики.
2. **Sources** — read-only; при расхождениях фиксируем в документах output.
3. **Один сервис** — одна папка в `output/`.
4. **Вход в комплект** — `docs/README.md` и `docs/service-vision.md`; детали — в профильных разделах BRD/SRS/API.
