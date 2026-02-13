# Requirements Analyzer API - Postman Collection

Полная коллекция для тестирования и работы с Requirements Analyzer API - RAG-based AI сервисом для валидации и анализа требований.

## 📦 Содержимое

Данная поставка включает два файла:

1. **Requirements_Analyzer_API.postman_collection.json** - основная коллекция запросов
2. **Requirements_Analyzer_Development.postman_environment.json** - переменные окружения для разработки

## 🚀 Быстрый старт

### 1. Импорт в Postman

1. Откройте Postman
2. Нажмите **Import** в верхнем левом углу
3. Перетащите оба JSON файла или выберите их через диалог
4. Коллекция и окружение будут импортированы

### 2. Настройка окружения

1. В Postman выберите окружение **"Requirements Analyzer - Development"**
2. Обновите переменные под вашу среду:
   - `BaseUrl` - адрес API (по умолчанию: `http://localhost:8000`)
   - `page1`, `page2` - реальные ID страниц Confluence
   - `service_code` - код вашего сервиса
   - `jira_id1`, `jira_id2` - ID задач Jira
   - `basic_auth_username`, `basic_auth_password` - для эндпоинта `/markdown`

### 3. Начало работы

Рекомендуемая последовательность для первого запуска:

1. **Health Check** - проверьте доступность API
2. **Get Application Info** - получите информацию о версии
3. **Get Current Configuration** - проверьте текущую конфигурацию
4. **Extract All Content** - протестируйте извлечение контента

## 📁 Структура коллекции

### 01 - Info & Health
Базовые эндпоинты для проверки работоспособности сервиса.

- `GET /info` - информация о приложении
- `GET /health` - health check
- `GET /extract_health` - health check модуля извлечения
- `GET /jira/health` - health check Jira модуля
- `GET /service_summary_health` - health check модуля саммари

### 02 - Configuration
Управление конфигурацией сервиса.

- `GET /config` - текущая конфигурация
- `POST /config` - обновление конфигурации

**Пример запроса:**
```json
{
  "LLM_PROVIDER": "deepseek",
  "LLM_MODEL": "deepseek-chat",
  "LLM_TEMPERATURE": "0.0",
  "IS_ENTITY_NAMES_CONTEXT": true,
  "IS_SERVICE_DOCS_CONTEXT": true,
  "IS_PLATFORM_DOCS_CONTEXT": true,
  "IS_SERVICE_LINKS_CONTEXT": true
}
```

**Поддерживаемые провайдеры:**
- `openai`
- `anthropic`
- `deepseek`
- `ollama`
- `kimi`
- `gemini`
- `grok`
- `qwen`
- `openrouter`

### 03 - Logging Control
Управление уровнем логирования.

- `GET /log_level` - текущий уровень
- `POST /log_level` - изменить уровень (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `POST /log_test` - тестовые сообщения

### 04 - Content Extraction
Извлечение контента из страниц Confluence.

- `POST /extract_all_content` - весь контент (с кешированием)
- `POST /extract_approved_content` - только одобренный контент
- `POST /markdown` - с кастомными credentials (требует Basic Auth)

**⚠️ Важно для /markdown:**
- Требуется Basic Authentication
- Заголовок: `Authorization: Basic <base64(username:password)>`
- Не использует кеширование
- Создает отдельное соединение для каждого запроса

### 05 - Load & Remove Pages
Загрузка и удаление страниц из векторного хранилища.

- `POST /load_pages` - загрузка страниц
- `POST /load_external_pages` - загрузка внешних страниц
- `POST /load_templates` - загрузка шаблонов
- `GET /child_pages/{page_id}` - получение дочерних страниц
- `POST /remove_service_pages` - удаление страниц сервиса
- `POST /remove_platform_pages` - удаление платформенных страниц

### 06 - Analysis
Анализ требований различными способами.

- `POST /analyze` - анализ текста
- `POST /analyze_pages` - анализ существующих страниц
- `POST /analyze_service_pages/{code}` - анализ по коду сервиса
- `POST /analyze_with_templates` - анализ с проверкой шаблонов
- `POST /analyze_external_pages` - анализ внешних страниц
- `POST /analyze_types` - определение типов шаблонов

**Пример analyze_with_templates:**
```json
{
  "items": [
    {
      "requirement_type": "FR",
      "page_id": "274628758"
    },
    {
      "requirement_type": "NFR",
      "page_id": "274628759"
    }
  ],
  "service_code": "SBP"
}
```

### 07 - Jira Integration
Интеграция с Jira.

- `POST /analyze-jira-task` - анализ задач Jira

**Пример:**
```json
{
  "jira_task_ids": ["GBO-123", "GBO-456"],
  "service_code": "SBP",
  "check_templates": true
}
```

### 08 - Agent
LLM-агент аналитик требований.

- `POST /agent/chat` - чат с агентом
- `POST /agent/reset` - сброс истории
- `GET /agent/info` - информация об агенте
- `GET /agent/tools` - доступные инструменты

**Примеры вопросов агенту:**
- "Найди требования по СБП"
- "Проанализируй страницу 274628758"
- "Какие есть функциональные требования к авторизации?"
- "Проверь соответствие страницы 123456 шаблону FR"

**Возможности агента:**
- Поиск требований в базе знаний
- Анализ конкретных страниц Confluence
- Проверка соответствия шаблонам
- Диалоговое взаимодействие с памятью

### 09 - Service Summary
Генерация саммари сервиса.

- `POST /generate_service_summary` - генерация (POST)
- `GET /service_summary/{parent_page_id}` - генерация (GET)

**Параметры:**
- `parent_page_id` - ID родительской страницы
- `use_approved_only` - только одобренные требования
- `max_tokens` - максимум токенов (по умолчанию 50000)
- `max_pages` - максимум страниц (по умолчанию 500)

### 10 - Services & Storage
Работа со справочниками и хранилищем.

- `GET /services` - список всех сервисов
- `GET /services?platform=true` - только платформенные сервисы
- `GET /debug_collections` - отладочная информация
- `GET /storage/analyze-sizes` - анализ размеров документов

### 11 - Cache Management
Управление кешем.

- `GET /cache_info` - информация о кеше страниц
- `POST /clear_cache` - очистка кеша страниц
- `GET /embedding_cache_info` - информация о кеше эмбеддингов
- `POST /clear_embedding_cache` - очистка кеша эмбеддингов

### 12 - Testing
Тестовые эндпоинты.

- `GET /test_context_size?context_size=1000` - тест размера контекста LLM

## 🔑 Переменные окружения

### Обязательные
- `BaseUrl` - базовый URL API

### Для примеров
- `page1`, `page2` - ID страниц Confluence
- `service_code` - код сервиса (SBP, PLATFORM и т.д.)
- `jira_id1`, `jira_id2` - ID задач Jira

### Для аутентификации
- `basic_auth_username` - имя пользователя для /markdown
- `basic_auth_password` - пароль для /markdown

## 🔐 Аутентификация

**Большинство эндпоинтов** не требуют аутентификации.

**Исключение:** `POST /markdown`
- Требует HTTP Basic Authentication
- Формат заголовка: `Authorization: Basic <base64(username:password)>`
- Пример для username=test, password=pass123:
  ```
  Authorization: Basic dGVzdDpwYXNzMTIz
  ```

## 📊 Примеры использования

### Пример 1: Полный цикл анализа страницы

1. **Загрузить страницу в хранилище:**
   ```
   POST /load_pages
   {
     "page_ids": ["274628758"],
     "service_code": "SBP"
   }
   ```

2. **Проанализировать страницу:**
   ```
   POST /analyze_pages
   {
     "page_ids": ["274628758"],
     "service_code": "SBP",
     "check_templates": true
   }
   ```

3. **Проверить соответствие шаблону:**
   ```
   POST /analyze_with_templates
   {
     "items": [
       {
         "requirement_type": "FR",
         "page_id": "274628758"
       }
     ],
     "service_code": "SBP"
   }
   ```

### Пример 2: Работа с агентом

1. **Задать вопрос:**
   ```
   POST /agent/chat
   {
     "message": "Найди требования по авторизации",
     "service_code": "SBP"
   }
   ```

2. **Попросить анализ:**
   ```
   POST /agent/chat
   {
     "message": "Проанализируй страницу 274628758"
   }
   ```

3. **Сбросить историю:**
   ```
   POST /agent/reset
   ```

### Пример 3: Генерация саммари сервиса

```
POST /generate_service_summary
{
  "parent_page_id": "274628758",
  "use_approved_only": true,
  "max_tokens": 50000,
  "max_pages": 500
}
```

### Пример 4: Анализ задач Jira

```
POST /analyze-jira-task
{
  "jira_task_ids": ["GBO-123", "GBO-456"],
  "service_code": "SBP",
  "check_templates": true
}
```

## 🐛 Отладка

### Проверка работоспособности

1. Проверьте все health check эндпоинты в папке "01 - Info & Health"
2. Проверьте конфигурацию: `GET /config`
3. Проверьте логи: установите уровень DEBUG через `POST /log_level`

### Проблемы с кешем

Если данные не обновляются:
1. Очистите кеш страниц: `POST /clear_cache`
2. Очистите кеш эмбеддингов: `POST /clear_embedding_cache`
3. Проверьте информацию о кеше: `GET /cache_info`

### Проблемы с токенами

Если получаете ошибку "token limit exceeded":
1. Уменьшите количество страниц в запросе
2. Используйте параметр `max_tokens` в summary эндпоинтах
3. Проверьте размеры документов: `GET /storage/analyze-sizes`

## 📝 Типы требований

Поддерживаемые типы шаблонов:
- `FR` - Functional Requirement
- `NFR` - Non-Functional Requirement
- `process` - Процессное требование
- `dataModel` - Модель данных
- `function` - Функция
- `integration` - Интеграция
- `control` - Контроль
- `screenListForm` - Экраны/списки/формы

## ⚡ Оптимизация производительности

### Параллельная обработка

Следующие эндпоинты используют параллельную обработку:
- `/extract_all_content`
- `/extract_approved_content`
- `/markdown`
- `/analyze_pages`
- `/analyze_external_pages`
- `/analyze-jira-task`

### Кеширование

Кешируются:
- Данные страниц Confluence (TTL настраивается)
- Эмбеддинги модели (LRU cache)

**Не кешируются:**
- Запросы к `/markdown` (использует кастомные credentials)

## 🔧 Кастомизация

### Кастомные промпты

Многие эндпоинты анализа поддерживают параметр `prompt_template`:
```json
{
  "page_ids": ["274628758"],
  "prompt_template": "Проанализируй требование с фокусом на безопасность..."
}
```

### Фильтрация сервисов

При запросе сервисов можно фильтровать по типу:
- `GET /services` - все сервисы
- `GET /services?platform=true` - только платформенные

## 📚 Дополнительная информация

### Форматы ответов

Все эндпоинты возвращают JSON в следующем формате:

**Успешный ответ:**
```json
{
  "success": true,
  "data": {...}
}
```

**Ошибка:**
```json
{
  "error": "Описание ошибки"
}
```

### HTTP коды ответов

- `200` - Успех (даже для бизнес-ошибок)
- `400` - Некорректный запрос
- `401` - Требуется аутентификация (только /markdown)
- `404` - Эндпоинт не найден
- `500` - Внутренняя ошибка сервера

## 🤝 Поддержка

При возникновении проблем:

1. Проверьте health check эндпоинты
2. Установите уровень логирования DEBUG
3. Проверьте переменные окружения
4. Убедитесь, что API доступен по указанному BaseUrl

## 📄 Лицензия

Данная коллекция предназначена для использования с Requirements Analyzer API.

---

**Версия коллекции:** 1.0  
**Дата создания:** 2024  
**Совместимость:** Postman v10+
