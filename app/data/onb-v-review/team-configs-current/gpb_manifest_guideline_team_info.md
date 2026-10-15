# Регламент ведения файла метаданных проекта (`gpb-manifest.json`)

## 1. Назначение файла
Файл `gpb-manifest.json`, расположенный в корне репозитория, содержит структурированную информацию о проекте, его артефактах, контактных ролях и принадлежности команды. Он используется для автоматизации DevOps‑процессов, каталогизации сервисов и поддержки команд.

---
## 2. Корпоративные требования
При заполнении файла необходимо руководствоваться **обще‑корпоративными правилами ведения метаданных**, опубликованными в Confluence.

Ссылка на общий регламент: *[https://confluence.int.gazprombank.ru/pages/viewpage.action?spaceKey=devops&title=Application+manifest]*.

### 2.1. Стандартизированные значения
Во всех репозиториях должны использоваться следующие значения:
- **`automatedSystemCode` = "ECO"**
- **`projectCodeDevOps` = "ECO"**
- **`jiraDevProject`** — код проекта Jira стрима (переменная «Код проекта Jira стрима»)
- **`confluenceUrl`** — *[https://confluence.int.gazprombank.ru/display/DBOCORPES]*
- **`emailItLeader`** — ИТ‑лидер или руководитель проекта
- **`emailTechDevLeader`** — тимлид или ведущий FE/BE
- **`emailOperations` = "eco_ops@company.com"**

---
## 3. Форматы файла `meta.json`
Файл представляет собой JSON‑документ и может иметь одну из двух структур:
- проект с **одним артефактом**;
- **монорепозиторий** с несколькими модулями.

---
## 3.1. Проект с одним артефактом
Используется, если репозиторий содержит один сервис.

### Пример
```json
{
  "automatedSystemCode": "ECO",
  "projectCodeDevOps": "ECO",
  "name": "product-offer-client",
  "title": "Сервис Динамических продуктовых предложений",
  "type": "application",
  "valueStreamMaintainer": "Департамент развития",
  "jiraDevProject": "<Код проекта Jira стрима>",
  "jiraDevComponent": "product-offer-client",
  "confluenceUrl": "https://confluence.int.gazprombank.ru/display/DBOCORPES",
  "emailItLeader": "andrey.andreev@company.com",
  "emailTechDevLeader": "sergey.sergeev@company.com",
  "emailOperations": "eco_ops@company.com",
  "description": "Сервис Динамических продуктовых предложений",
  "teamInfo": {
    "team": "team-team",
    "projectType": "ECO_BE",
    "platform": false,
    "type": "microservice"
  }
}
```

### Обязательные поля
- обязательные поля из общего регламента
- секция `teamInfo`

---
## 3.2. Монорепозитории
Используется, если репозиторий содержит несколько модулей.

Модули описываются в массиве `monorepository`.

### Варианты размещения секции `teamInfo`

---
### Вариант A. `teamInfo` только в корне монорепозитория
Используется, если **все модули принадлежат одной команде и одному типу проекта**.

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
      "modulePath": "./module-a",
      "description": "Описание модуля A"
    }
  ]
}
```

**Правило:** значения `teamInfo` применяются ко всем модулям монорепозитория.

---
### Вариант B. `teamInfo` только в модулях
Используется, если **модули принадлежат разным командам или имеют разный тип проекта**.

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

**Правило:** корневая секция `teamInfo` отсутствует и не используется.

---
### Вариант C. `teamInfo` в корне и в модулях
Используется, если требуется **задать значения по умолчанию** и **переопределять их на уровне модуля**.

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
- `teamInfo` модуля имеет приоритет над корневым;
- если поле отсутствует в модуле, используется значение из корня.

---
## 4. Правила заполнения секции `teamInfo`
Секция `teamInfo` обязательна для формирования перечня команд и сервисов.

### 4.1. Обязательные поля
- **`team`** — ответственная команда
- **`projectType`**:
  - `ECO_BE` — backend
  - `ECO_FE` — frontend
  - `ECO_QA` — QA
  - `ECO_AN` — аналитика
- **`platform`** — является ли артефакт платформенным (`true / false`)

### 4.2. Дополнительные поля
- **`type`** (для `ECO_BE`):
  - `microservice` — микросервис
  - `library` — библиотека
  - `SPA` — веб‑приложение
  - `UI` — пользовательский интерфейс / агрегирующие решения
  - `application` — Node.js / standalone‑приложение

---
## 5. Общие правила ведения файла
### 5.1. Расположение
Файл `gpb_manifest.json` находится в корне репозитория.

### 5.2. Требования
- валидный JSON
- кодировка UTF‑8
- актуальные контактные данные

### 5.3. Обновление
Файл обновляется при изменении:
- контактных ролей;
- структуры модулей;
- путей документации;
- типа проекта;
- Jira‑компонентов.

---
## 6. Ответственность
- За актуальность данных отвечает команда‑владелец репозитория.
- Платформенная / DevOps‑команда обеспечивает контроль корректности структуры.

