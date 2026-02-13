# 🚀 Requirements Analyzer API - Быстрая шпаргалка

## Установка

1. Импортируйте в Postman:
   - `Requirements_Analyzer_API.postman_collection.json`
   - `Requirements_Analyzer_Development.postman_environment.json`

2. Выберите окружение **"Requirements Analyzer - Development"**

3. Обновите переменные:
   - `BaseUrl` → ваш адрес API
   - `page1`, `page2` → реальные ID страниц
   - `service_code` → код вашего сервиса

## Первые шаги

```
1. GET /health                     ✓ Проверка доступности
2. GET /info                       ✓ Информация о версии
3. POST /extract_all_content       ✓ Тест извлечения контента
```

## Основные сценарии

### 📄 Извлечение контента

```http
# Весь контент
POST /extract_all_content
{ "page_ids": ["{{page1}}"] }

# Только одобренный
POST /extract_approved_content
{ "page_ids": ["{{page1}}"] }

# С кастомными credentials (Basic Auth required!)
POST /markdown
Headers: Authorization: Basic <base64(user:pass)>
{ "page_ids": ["{{page1}}"] }
```

### 📥 Загрузка в хранилище

```http
# Обычные страницы
POST /load_pages
{
  "page_ids": ["{{page1}}", "{{page2}}"],
  "service_code": "{{service_code}}"
}

# Внешние страницы (без обращения к Confluence)
POST /load_external_pages
{
  "pages": [
    {
      "page_id": "{{page1}}",
      "title": "Test Page",
      "content": "<html>...</html>"
    }
  ],
  "service_code": "{{service_code}}"
}
```

### 🔍 Анализ требований

```http
# Анализ страниц
POST /analyze_pages
{
  "page_ids": ["{{page1}}"],
  "service_code": "{{service_code}}",
  "check_templates": true
}

# Анализ с шаблонами
POST /analyze_with_templates
{
  "items": [
    { "requirement_type": "FR", "page_id": "{{page1}}" }
  ],
  "service_code": "{{service_code}}"
}

# Определение типов
POST /analyze_types
{ "page_ids": ["{{page1}}", "{{page2}}"] }
```

### 🤖 Работа с агентом

```http
# Вопрос агенту
POST /agent/chat
{
  "message": "Найди требования по СБП",
  "service_code": "{{service_code}}"
}

# Анализ страницы через агента
POST /agent/chat
{
  "message": "Проанализируй страницу {{page1}}"
}

# Сброс истории
POST /agent/reset
```

### 🎫 Jira интеграция

```http
POST /analyze-jira-task
{
  "jira_task_ids": ["{{jira_id1}}", "{{jira_id2}}"],
  "service_code": "{{service_code}}",
  "check_templates": true
}
```

### 📊 Генерация саммари

```http
# POST версия
POST /generate_service_summary
{
  "parent_page_id": "{{page1}}",
  "use_approved_only": true,
  "max_tokens": 50000
}

# GET версия (быстрая)
GET /service_summary/{{page1}}?use_approved_only=true
```

## ⚙️ Конфигурация

```http
# Текущая конфигурация
GET /config

# Изменить провайдера
POST /config
{
  "LLM_PROVIDER": "deepseek",
  "LLM_MODEL": "deepseek-chat",
  "LLM_TEMPERATURE": "0.0"
}

# Провайдеры: openai | anthropic | deepseek | ollama | 
#              kimi | gemini | grok | qwen | openrouter
```

## 🗑️ Управление данными

```http
# Удалить страницы
POST /remove_service_pages
{ "page_ids": ["{{page1}}"] }

# Удалить платформенные страницы
POST /remove_platform_pages
{
  "page_ids": ["{{page1}}"],
  "service_code": "PLATFORM"
}

# Очистить кеш
POST /clear_cache
POST /clear_embedding_cache
```

## 🧹 Кеш и отладка

```http
GET /cache_info                  # Информация о кеше страниц
GET /embedding_cache_info        # Информация о кеше эмбеддингов
POST /clear_cache               # Очистить кеш страниц
POST /clear_embedding_cache     # Очистить кеш эмбеддингов
GET /debug_collections          # Отладка хранилища
GET /storage/analyze-sizes      # Анализ размеров документов
```

## 📝 Логирование

```http
# Текущий уровень
GET /log_level

# Изменить уровень
POST /log_level
{ "level": "DEBUG" }
# Уровни: DEBUG | INFO | WARNING | ERROR | CRITICAL

# Тестовые сообщения
POST /log_test
```

## 🔍 Справочники

```http
GET /services                    # Все сервисы
GET /services?platform=true      # Платформенные сервисы
GET /child_pages/{{page1}}       # Дочерние страницы
```

## ⚠️ Важные моменты

### Basic Auth для /markdown
```
Headers:
  Authorization: Basic <base64(username:password)>

Пример (username=test, password=pass):
  Authorization: Basic dGVzdDpwYXNz
```

### Типы требований
```
FR              - Functional Requirement
NFR             - Non-Functional Requirement
process         - Процессное требование
dataModel       - Модель данных
function        - Функция
integration     - Интеграция
control         - Контроль
screenListForm  - Экраны/списки/формы
```

### Переменные для примеров
```
{{BaseUrl}}       → http://localhost:8000
{{page1}}         → 274628758
{{page2}}         → 274628759
{{service_code}}  → SBP
{{jira_id1}}      → GBO-123
{{jira_id2}}      → GBO-456
```

## 🐛 Решение проблем

| Проблема | Решение |
|----------|---------|
| 401 на /markdown | Проверьте Basic Auth заголовок |
| Token limit exceeded | Уменьшите количество страниц |
| Данные не обновляются | Очистите кеш (POST /clear_cache) |
| Агент не отвечает | Проверьте GET /agent/info |
| Ошибка конфигурации | Проверьте GET /config |

## 📞 Health Checks

```http
GET /health                      # Основной
GET /extract_health             # Модуль извлечения
GET /jira/health                # Jira модуль
GET /service_summary_health     # Модуль саммари
GET /agent/info                 # Состояние агента
```

## 🎯 Полный сценарий работы

```
1. GET /health                           # Проверка
2. GET /config                           # Текущая конфигурация
3. POST /extract_all_content             # Извлечение контента
4. POST /load_pages                      # Загрузка в хранилище
5. POST /analyze_pages                   # Анализ
6. POST /agent/chat                      # Вопрос агенту
7. POST /generate_service_summary        # Генерация саммари
```

---

**Документация:** См. POSTMAN_README.md  
**Версия:** 1.0
