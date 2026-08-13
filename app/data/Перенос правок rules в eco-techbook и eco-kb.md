# Перенос правок _meta/rules в eco-techbook и eco-kb

Правки каталога _meta/rules из ветки meta/phase4-scope-rule (волна INTC,
коммит 0f8bdea), не попавшие в master из-за переезда канона (d5d5527:
rules вынесены в eco-techbook и eco-kb). Ниже — полные диффы от merge-base;
целевые файлы по README-указателю _meta/rules:
- conventions.md -> eco-techbook/standards/analytics/conventions.md
- terms.md -> eco-kb/analytics/terms.md
- analyst-docs-guide.md -> eco-kb/analytics/analyst-docs-guide.md

```diff
diff --git a/_meta/rules/analyst-docs-guide.md b/_meta/rules/analyst-docs-guide.md
index 44e8e77..899d099 100644
--- a/_meta/rules/analyst-docs-guide.md
+++ b/_meta/rules/analyst-docs-guide.md
@@ -82,6 +82,7 @@ docs-repo/                     # целевой remote — см. topology §3 с
             │   ├── controls/          # проверки
             │   ├── print-forms/       # печатные формы
             │   ├── contract-calls/         # вызовы контрактов: как сервис зовёт внешние АС
+            │   ├── internal-contracts/     # постановка контрактов СОБСТВЕННЫХ методов сервиса (внутренний контур Экосистемы; реализация — docs/api из кода)
             │   ├── platform-functions.md   # вызовы платформы ЭКО
             │   └── rbac.md            # роли и права
             └── api/                   # описание API для людей
diff --git a/_meta/rules/conventions.md b/_meta/rules/conventions.md
index da6cf04..9e34fc7 100644
--- a/_meta/rules/conventions.md
+++ b/_meta/rules/conventions.md
@@ -156,6 +156,7 @@ ID (границы скоупа; инцидент file-storage 2026-08-11: EXT-0
 | `PROC`   | Процессный артефакт (`process/`): процесс, статусная модель. Статусная модель сервиса — один документ с фиксированным именем `process/status-model.md` (без ID-префикса в имени, как `rbac.md`)                                                                                                                                      |
 | `RBAC`   | Документ ролевой модели сервиса (`docs/srs/rbac.md`); коды привилегий в каталоге **не** получают отдельных RBAC-NNN — на них ссылаются функции и экранные формы по строковому коду                                                                                                                                                   |
 | `PLT`    | Платформенная функция или проверка платформы ЭКО, вызываемая сервисом, но реализуемая **вне его контура** — карточка в реестре `docs/srs/platform-functions.md` (`PLT-000` — реестр). Не `EXTINT` (обмен с внешними банковскими АС) и не `CTL` (проверки данных заявки внутри сервиса). На `PLT` ссылаются экраны, функции, процессы |
+| `INTC`   | Контракт собственного метода сервиса — ПОСТАНОВОЧНЫЙ уровень (карточка в `docs/srs/internal-contracts/`, §5.1.3; реализация — YAML в `docs/api/` из кода). «Internal» — внутренний контур Экосистемы. На `INTC` ссылаются процессы и функции |
 
 
 **Общие документы корня `docs/`** (входные для обоих слоёв, §5.4) — однофайловые, фиксированный ID без нумерации:
@@ -231,6 +232,30 @@ ID (границы скоупа; инцидент file-storage 2026-08-11: EXT-0
 - **Записи — карточки-минимум** (назначение, где используется), пока постановка платформенной функции вне выгрузки; создаёт их только заход типа `platform-function` — из чужих заходов вместо записи остаётся долг (границы скоупа). Пробел — в open-questions (§6).
 - **Ссылки:** из экранов, функций, процессов — `[PLT-NNN <название>](platform-functions.md#…)` (всегда ID + название, §5).
 
+### 5.1.3. Слой internal-contracts (постановка контрактов собственных методов)
+
+- **Семантика имён:** internal/external — относительно границы ЭКОСИСТЕМЫ
+  ДБО, не сервиса. Все микросервисы ДБО — внутренний контур; «внешние»
+  системы — за пределами Экосистемы (смежные АС банка и внешний мир).
+- **Путь:** `output/<service-id>/docs/srs/internal-contracts/` — карточки
+  контрактов методов, которыми ВЛАДЕЕТ сервис (README-реестр `INTC-000`,
+  карточки `intc-NNN-<slug>.md`, sidecar-примеры в `examples/`).
+- **Два уровня, граница как у модели данных:** internal-contracts —
+  ПОСТАНОВКА (из Confluence, зона аналитика); `docs/api/` — РЕАЛИЗАЦИЯ
+  (YAML авто-выгрузкой из кода, зона разработки, §5.1). Расхождение
+  уровней — открытый вопрос команде; при переходе на api-first карточки —
+  источник description-полей контракта, не конкурент YAML.
+- **ID:** префикс `INTC` (схема ID §5). Ссылки SRS → `INTC-NNN` — штатные
+  (процессы и функции ссылаются на карточку метода вместо текстового
+  упоминания); карточка на процессы/функции не ссылается — трассировка
+  «метод ↔ SRS» в матрице (§5.3 п. 7: до появления YAML операции таблицы
+  «API ↔ SRS» — карточки INTC).
+- **Межсервисные вызовы внутри Экосистемы:** контракт — в
+  internal-contracts сервиса-ВЛАДЕЛЬЦА; потребление другим сервисом —
+  в точке вызова его комплекта (стиль отдельных карточек потребления —
+  в проработке).
+- Шаблон и правила переноса — [`internal-contracts.md`](../templates/internal-contracts.md).
+
 
 
 ## 5.2. Настраиваемые параметры
diff --git a/_meta/rules/terms.md b/_meta/rules/terms.md
index b5b899e..5d5c9b9 100644
--- a/_meta/rules/terms.md
+++ b/_meta/rules/terms.md
@@ -51,7 +51,8 @@
 
 | Термин | Расшифровка | Где встречается |
 | --- | --- | --- |
-| **тип артефакта** | Вид документа аналитики (data-model, process, function, screen-form, control, external-integration, …): поле `type` во frontmatter; определяет шаблон `_meta/templates/<тип>.md`, специализированный скилл (диспетчер `create-artifact`) и каталог в комплекте. Заход работает с ОДНИМ типом (границы скоупа) | [`conventions.md`](conventions.md) §5, [`skills/create-artifact.md`](../skills/create-artifact.md) |
+| **Экосистема (ЭКО)** | Совокупность микросервисов системы ДБО — внутренний контур. «Internal/external» в именах слоёв и репозиториев — относительно ЕЁ границы: internal — микросервисы ДБО, external — системы за пределами Экосистемы (смежные АС банка и внешний мир). «Платформа ЭКО» — общие сервисы Экосистемы (см. PLT, EXT) | [`conventions.md`](conventions.md) §5.1.1–5.1.3 |
+| **тип артефакта** | Вид документа аналитики (data-model, process, function, screen-form, control, external-integration, internal-contract, …): поле `type` во frontmatter; определяет шаблон `_meta/templates/<тип>.md`, специализированный скилл (диспетчер `create-artifact`) и каталог в комплекте. Заход работает с ОДНИМ типом (границы скоупа) | [`conventions.md`](conventions.md) §5, [`skills/create-artifact.md`](../skills/create-artifact.md) |
 | **BRD** | Business Requirements Document — бизнес-слой: business-rules, features, use-cases (`docs/brd/`).<br>Vision и glossary — общие входные в корне `docs/` | [`conventions.md`](conventions.md) §5.4 |
 | **SRS** | Software Requirements Specification — системный слой: модель данных, процессы, экраны, функции, контроли, RBAC, интеграции, ПФ (`docs/srs/`) | [`conventions.md`](conventions.md) §5.4 |
 | **матрица трассировки** | `traceability-matrix.md` — связи ID между артефактами BRD ↔ SRS; обновляется в том же MR | [`conventions.md`](conventions.md) §5.3 |
@@ -95,6 +96,7 @@
 | **EXT** | **Внешняя зависимость комплекта** — данные, которыми владеет другой сервис, а документируемый только читает (реестр `dictionaries.md`); роль относительно комплекта, нумерация локальна потребителю | [`conventions.md`](conventions.md) §5 |
 | **VIS** | Концепция сервиса — единственный документ `docs/service-vision.md` (`VIS-001`) | [`conventions.md`](conventions.md) §5.4 |
 | **EXTINT** | Точка обмена с **внешней** банковской АС.<br><br>**Базовый контракт** — `EXTINT-<AS>-NNN` в репо [`docs-external-contracts`](https://gitlab.gboteam.ru/EAN/docs-external-contracts) (папки по АС; в «Потребителях» — ссылка на usage без отдельной колонки локального ID).<br><br>**Usage в сервисе** — локальный `EXTINT-NNN` в `output/<service>/docs/srs/contract-calls/` со ссылкой на базовый ID | [`conventions.md`](conventions.md) §5.1.1 |
+| **INTC** | Контракт собственного метода сервиса — постановочный уровень (`docs/srs/internal-contracts/`); реализация — YAML в `docs/api/` из кода. «Internal» — внутренний контур Экосистемы | [`conventions.md`](conventions.md) §5.1.3 |
 | **FUN** | Функция системы:<br>`FUN-CL-NN` — клиент;<br>`FUN-BNK-NN` — банк;<br>`FUN-SYS-NN` — системная | `functions/` |
 | **SCR** | Экранная форма:<br>`SCR-CL-NN` — клиент;<br>`SCR-BNK-NN` — банк | `screen-forms/` |
 | **CTL** | Контроль (проверка данных/правил); группы — `CTL-GRP-N` | `controls/` |
```

## Статус переноса (2026-08-13)

ВЫПОЛНЕНО локальными ветками (push и MR — за пользователем):

- eco-techbook, ветка `meta/intc-conventions` (a1c14c3): §5.1.3 + строка
  INTC в схеме ID; текст адаптирован под топологию eco-techbook
  (`<service-id>/docs/srs/...`, ссылка на шаблон — URL docs-o2new).
- eco-kb, ветка `meta/intc-terms-guide` (worktree `ED/eco-kb-intc`):
  58c546b — ДОГОН переименований (contract-calls,
  docs-external-contracts: снапшот переезда канона отстал от master
  docs-o2new — 13 замен в terms/guide, включая якорь git-workflow);
  ab99e73 — INTC-волна (строка INTC в префиксах ID, термины
  «Экосистема (ЭКО)» и «тип артефакта», каталог в дереве гайда).

Находка для команды: перенос канона в eco-kb выполнен со снапшота
до 12.08 — переименования пакета 2 потерялись. Другие перенесённые
файлы (environment-setup, git-start) на отставание не проверялись.
