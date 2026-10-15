---
title: Настройка gpb-manifest.json
order: 1
---

## Форматы файла

Файл представляет собой JSON‑документ и может иметь одну из двух структур:

- Проект с **одним артефактом**
- **Монорепозиторий** с несколькими артефактами

---

## Проект с одним артефактом

Используется, если репозиторий содержит один артефакт.

```json
{
  "automatedSystemCode": "ECO",
  "projectCodeDevOps": "ECO",
  "name": "product-offer-client",
  "title": "Сервис Динамических продуктовых предложений",
  "type": "application",
  "valueStreamMaintainer": "Департамент развития",
  "jiraDevProject": "DBOCORPESPLN",
  "jiraDevComponent": "product-offer-client",
  "confluenceUrl": "https://confluence.int.gazprombank.ru/display/DBOCORPES",
  "emailItLeader": "andrey.andreev@gazprombank.ru",
  "emailTechDevLeader": "sergey.sergeev@gazprombank.ru",
  "emailOperations": "eco_ops@gazprombank.ru",
  "description": "Сервис Динамических продуктовых предложений",
  "teamInfo": {
    "team": "team-delta",
    "projectType": "ECO_BE",
    "platform": false
  }
}
```

---

## Монорепозитории

Используется, если репозиторий содержит несколько артефактов. Модули описываются в массиве `monorepository`.

### Вариант A: teamInfo только в корне

Используется, если **все модули принадлежат одной команде**:

```json
{
  "automatedSystemCode": "ECO",
  "projectCodeDevOps": "ECO",
  "teamInfo": {
    "team": "core-team",
    "projectType": "ECO_BE",
    "platform": true
  },
  "monorepository": [
    {
      "name": "module-a",
      "type": "application",
      "modulePath": "./module-a",
      "description": "Описание модуля A"
    }
  ]
}
```

### Вариант B: teamInfo только в модулях

Используется, если **модули принадлежат разным командам**:

```json
{
  "automatedSystemCode": "ECO",
  "projectCodeDevOps": "ECO",
  "monorepository": [
    {
      "name": "module-a",
      "modulePath": "./module-a",
      "teamInfo": {
        "team": "team-a",
        "projectType": "ECO_BE",
        "platform": false
      }
    },
    {
      "name": "module-b",
      "modulePath": "./module-b",
      "teamInfo": {
        "team": "team-b",
        "projectType": "ECO_FE",
        "platform": false
      }
    }
  ]
}
```

### Вариант C: teamInfo в корне и в модулях

Используется, если нужно **задать значения по умолчанию и переопределять на уровне модуля**:

```json
{
  "automatedSystemCode": "ECO",
  "projectCodeDevOps": "ECO",
  "teamInfo": {
    "team": "default-team",
    "projectType": "ECO_BE",
    "platform": false
  },
  "monorepository": [
    {
      "name": "module-a",
      "modulePath": "./module-a"
    },
    {
      "name": "module-b",
      "modulePath": "./module-b",
      "teamInfo": {
        "team": "special-team",
        "platform": true
      }
    }
  ]
}
```

**Правила:**

- `teamInfo` модуля имеет приоритет над корневым
- Если поле отсутствует в модуле, используется значение из корня

---

## Классификация типов репозиториев

Корневой `type` (в корне манифеста или в элементе `monorepository`) определяет категорию артефакта в
отчётах и при валидации платформенных полей.

### Типы, отображаемые как микросервисы

- `application`
- `module`
- `ui`
- `static`

### Типы, отображаемые как библиотеки

- `configuration`
- `plugin`
- `library`
- `generic`
- `job`

**Важно:** Если тип репозитория не соответствует ни одному из перечисленных, репозиторий не попадёт ни в одну колонку отчёта.

---

## Платформенные backend-микросервисы

Для артефактов с `teamInfo.platform: true`, `teamInfo.projectType: ECO_BE` и корневым `type` из категории
**микросервисов** (см. выше) в секции `teamInfo` заполняются дополнительные поля:

| Поле                | Описание                                                                            |
| ------------------- | ----------------------------------------------------------------------------------- |
| `layer`             | Архитектурный уровень платформенного артефакта                                      |
| `deploymentSegment` | Сегмент размещения: `DMZ`, `LAN` или `DMZ/LAN`                                      |
| `externalSystem`    | Внешняя автоматизированная система (обязательно при `layer = Integration_Adapters`) |

В монорепозитории для проверки и отчётов используется `type` **первого** элемента `monorepository`
(при отсутствии — `type` в корне манифеста).

Эти поля используются при автоматическом формировании статьи
[Карта платформенных сервисов](../../architecture/backend/platform-service-map-new.md):
сервисы группируются по `layer`, в таблицах указываются `deploymentSegment` и `externalSystem`.

Подробнее о допустимых значениях и правилах заполнения — в
[стандарте gpb-manifest](../../standards/common/gpb-manifest.md#поля-платформенных-backend-микросервисов).

Пример для платформенного интеграционного адаптера:

```json
{
  "type": "application",
  "teamInfo": {
    "team": "team-whiskey",
    "projectType": "ECO_BE",
    "platform": true,
    "layer": "Integration_Adapters",
    "deploymentSegment": "LAN",
    "externalSystem": "АС ЕСК"
  }
}
```

---

## JSON-схемы

Для валидации и поддержки в IDE доступны следующие схемы:

- [meta_json_schema.json](./assets/gpb-manifest-setup/meta_json_schema.json) — схема для проекта с одним артефактом
- [meta_monorepo_json_schema.json](./assets/gpb-manifest-setup/meta_monorepo_json_schema.json) — схема для монорепозитория
- [teamInfo_section_schema.json](./assets/gpb-manifest-setup/teamInfo_section_schema.json) — схема секции teamInfo

---

## Связанные документы

- [Стандарт gpb-manifest](../../standards/common/gpb-manifest.md) — требования и правила
- [Карта платформенных сервисов](../../architecture/backend/platform-service-map-new.md) —
  формируется по полям `layer`, `deploymentSegment`, `externalSystem`
- [Настройка team-config](./team-config.md) — управление метаданными команд
