---
title: Настройки GitLab
order: 5
---

Меню: **Settings → …** (названия чуть отличаются по версии GitLab).

## Оглавление

1. [Default branch](#1-default-branch)
2. [Доступ docs vs src](#2-доступ-docs-vs-src)
3. [Protected branches](#3-protected-branches)
4. [Approval rules](#4-approval-rules)
5. [Merge requests](#5-merge-requests)
6. [Push rules](#6-push-rules)
7. [Имя ветки и JIRA](#7-имя-ветки-и-jira)
8. [Labels](#8-labels)
9. [CI](#9-ci-по-мере-готовности)
10. [Чеклисты нового репо](#10-чеклисты-нового-репо)

## 1. Default branch

Общая ветка репозитория по умолчанию (Default branch) — **`trunk`**.

## 2. Доступ docs vs src

Кто входит в проект GitLab (Project members / группы) — **membership**, список
участников:

| Репо         | Кто имеет доступ (membership)                                          |
| ------------ | ---------------------------------------------------------------------- |
| **`docs-*`** | Группы аналитиков **и** backend **и** frontend **и** QA (тестирование) |
| **`src-*`**  | **Только** группа аналитиков                                           |

Чистовик и ревью со стороны разработки/QA — в **docs**. Сырьё и хронология в **src**
разработчикам и QA не открывают. Правило доступа —
[repo-topology § доступ](../../standards/analytics/repo-topology.md#доступ-к-репо).

## 3. Protected branches

### Settings → Repository → Protected branches

Или **Branch rules**. Защищённые ветки: кто может вливать MR и кто может пушить
напрямую.

<!-- markdownlint-disable MD013 -->
| Ветка (Branch)   | Кто может вливать MR (Allowed to merge) | Кто может пушить напрямую (Allowed to push and merge) | Force push  | Approve владельцев путей (Code owner approval) |
| ---------------- | --------------------------------------- | ----------------------------------------------------- | ----------- | ---------------------------------------------- |
| `trunk` (docs-*) | **Developers + Maintainers**            | Никто (No one)                                        | Выкл. (Off) | **Вкл. (On)** при наличии `CODEOWNERS`         |
| `master` (src-*) | Maintainers                             | **Maintainers**                                       | Выкл. (Off) | Выкл. (Off)                                    |
<!-- markdownlint-enable MD013 -->

В `src-*` ввод задач в ПРОМ и новые выгрузки коммитит утилита `run-history`
прямо в `master` (коммит + тег на задачу), поэтому MR в `src-*` не
используется, а прямой push в `master` разрешён мейнтейнерам — это
аналитики команды. Ветка хронологии `future` в `src-*` не защищается.

Feature-ветки (`docs/*`, `meta/*`, …) **не** защищают.

Важно: прямой push в `trunk` запрещён. Merge MR в `trunk` могут **Developers и
Maintainers** — после approve Code Owners (если включено) и при включённом
**Prevent approval by author** ([§5](#5-merge-requests)). Пока `CODEOWNERS` нет —
колонка Code owner approval остаётся Off.

## 4. Approval rules

Именованные Approval rules (Analyst / Backend / Frontend / QA / Methodology) **не
заводим.**

Обязательный approve — файл `CODEOWNERS` в корне репо и колонка **Code owner
approval = On** на защищённой `trunk` ([§3](#3-protected-branches)). GitLab
блокирует merge, пока апрувнули владельцы затронутых путей.

**Prevent approval by author** — **включить** ([§5](#5-merge-requests)): автор не
апрувит себя.

Пока `CODEOWNERS` нет — Code owner approval Off ([§3](#3-protected-branches)).

Копировать в корень docs-репо как `CODEOWNERS`. `[Имя][1]` — секция GitLab; `1` =
сколько approve нужно из этой секции. Для типичного `docs-<service>` достаточно
**Default** на `*`. Секции по путям — если в одном репо несколько экспертиз (как
eco-kb: `**/analytics/**`, `**/backend/**`, `**/frontend/**`, `**/qa/**`).
Совпавший glob из нескольких секций — approve из **каждой** такой секции.
[team-configs](https://gitlab.gboteam.ru/TEAM/team-configs) — репо состава команд.
**Пока CI нет** — `CODEOWNERS` кладёте в корень сами по шаблону ниже. Когда репо
в sync и CI кладёт файл — руками не править; шаблон — для заведения до sync
или если sync нет.
Плейсхолдеры `@REPLACE_*` заменить GitLab-логинами.

```text
[Default][1]
* @REPLACE_GITLAB_USER

[Analytics][1]
**/docs/** @REPLACE_ANALYTICS_USER

# [Backend][1]
# **/backend/** @REPLACE_BACKEND_USER
#
# [Frontend][1]
# **/frontend/** @REPLACE_FRONTEND_USER
#
# [QA][1]
# **/qa/** @REPLACE_QA_USER
```

Когда какую роль ревью отмечать в шаблоне MR — [git-workflow.md](git-workflow.md#8-ревью).
Чеклист ролей — подсказка автору, не отдельные правила в Settings.

## 5. Merge requests

### Settings → Merge requests

<!-- markdownlint-disable MD013 -->
| Настройка                       | Предложение                                                   | Зачем                                               |
| ------------------------------- | ------------------------------------------------------------- | --------------------------------------------------- |
| Merge method                    | **Squash** (влить MR одним коммитом; Encourage или Require)   | одна запись в истории; ключ JIRA в сообщении squash |
| Delete source branch by default | **включить**                                                  | не копятся feature-ветки                            |
| All threads must be resolved    | **включить**                                                  | не мержить с открытыми комментариями                |
| Pipelines must succeed          | структурный линтер и 10 зелёных pipeline подряд               | до выполнения критерия не включать                  |
| Code owner approval             | **On**, когда есть `CODEOWNERS` ([§3](#3-protected-branches)) | обязательный approve владельцев путей               |
| Prevent approval by author      | **включить**                                                  | автор не апрувит себя                               |
<!-- markdownlint-enable MD013 -->

Черновик (Draft) и явные Reviewers — в UI MR; подробнее —
[git-workflow](git-workflow.md#7-merge-request) и [ревью](git-workflow.md#8-ревью).

## 6. Push rules

### Settings → Repository → Push rules

**Уже сейчас** — **Reject expression in commit messages**: отклонять сообщения
с маркерами соавторства ИИ (regex ниже). Правило —
[git-workflow](git-workflow.md#3-общие-правила).

<!-- markdownlint-disable MD013 -->
```text
(?i)(co-authored-by:.*(cursor|claude|copilot|chatgpt|openai|anthropic|gemini|gpt-|cursoragent@)|signed-off-by:.*(cursor|claude|copilot|anthropic)|generated[- ]?(by|with).*(cursor|claude|copilot|chatgpt|ai\b)|assisted-by:.*(cursor|claude|copilot)|made-with:\s*cursor|сгенерировано\s*ии)
```

Остальное — следующий шаг после стартового набора:

| Правило                                | Предложение                                                                       |
| -------------------------------------- | --------------------------------------------------------------------------------- |
| Reject unsigned commits / secret files | по политике организации                                                           |
| Branch name                            | regex под `<prefix>/<topic>/<jiraid>` (исключения без задачи — по договорённости) |
| Commit message                         | ключ Jira в начале темы (кроме согласованных исключений без задачи)               |
<!-- markdownlint-enable MD013 -->

Пока regex имени ветки и ключа Jira в Push rules не включены — формат ветки,
ключ в коммитах и MR держатся дисциплиной + шаблоном MR.

## 7. Имя ветки и JIRA

Формат ветки и ключ JIRA — дисциплина + шаблон MR; при включённых Push rules — regex
имени ветки ([§6](#6-push-rules)). Интеграция Jira — по ключу в заголовке MR / имени ветки
([JIRA](git-workflow.md#4-jira-и-линковка-с-задачей)).

## 8. Labels

Labels `needs::*`, `reviewed::*`, `ready-to-merge` — **опциональны** (видимость на доске).
Не заменяют approve Code Owners.

## 9. CI (по мере готовности)

Целевой минимум на MR (по образцу
[CONTRIBUTING techbook](https://gitlab.gboteam.ru/ED/eco-techbook/-/blob/master/CONTRIBUTING.md)):
**markdownlint** + проверка **битых внутренних ссылок**. Далее по мере готовности:
эвристика матрицы. «Pipelines must succeed» — только после внедрения структурного
линтера и 10 подряд зелёных pipeline на MR (критерий из таблицы [§5](#5-merge-requests)).
Пайплайны разработки (lint / проверка типов / контракт / SemVer — правила версий API) на
docs-репо не переносим.

## 10. Чеклисты нового репо

### Чеклист нового docs-репо

1. Дерево remote по
   [repo-topology §3](../../standards/analytics/repo-topology.md#3-состав-целевого-docs-репо):
   `README.md`, `gpb-manifest.json`, `CODEOWNERS`, `.gitignore`,
   `<service-id>/` — **без** `output/` (не класть в remote; целевой путь
   `<service-id>/`), `sources/`, соседних открытых вопросов (OQ) / reports.
2. Список участников (membership): группы **аналитиков + backend + frontend + QA**
   ([§2](#2-доступ-docs-vs-src)).
3. Protected `trunk`: кто вливает MR = **Developers + Maintainers**; кто пушит
   напрямую = никто (No one); force push выкл.
4. `gpb-manifest.json` в корне (`name` = имя репо) —
   [`repo-topology.md`](../../standards/analytics/repo-topology.md#6-именование-репозиториев),
   образец [`gpb-manifest.json`](../../gpb-manifest.json); `REPLACE_*` заполнены.
5. `CODEOWNERS` в корне: **пока CI нет** — положить по шаблону [§4](#4-approval-rules)
   (регистрация в [team-configs](https://gitlab.gboteam.ru/TEAM/team-configs) не нужна).
   Когда CI появится — репо в team-configs, файл приедет сам. Затем Require
   code owner approval **On**.
6. Prevent approval by author — On.
7. Squash + delete source branch by default; threads must be resolved.
8. Шаблон MR с ролями и блоком перед merge.
9. Jira integration (если есть).
10. Push rules → **Reject expression in commit messages** — regex из [§6](#6-push-rules)
    (соавторство ИИ; **можно уже сейчас**).
11. Следующим шагом: Push rules на имя ветки и ключ в коммитах; CI-линт.

### Чеклист нового src-репо

1. Создать `src-<service-id>` или `src-<domain-slug>`
   ([именование](../../standards/analytics/repo-topology.md#6-именование-репозиториев)).
2. Список участников (membership): **только группа аналитиков** — разработку и QA не
   добавлять ([§2](#2-доступ-docs-vs-src)).
3. **`gpb-manifest.json` и `CODEOWNERS` не обязательны** (правила для src не
   требуют); team-configs как у docs — не обязателен.
4. Состав папок не нормируется; удобный профиль источников (часто корневой
   `README.md`) — по решению команды.
