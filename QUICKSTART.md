# 🚀 Quick Start: Запуск агента за 5 минут

## Шаг 1: Подготовка файлов (2 минуты)

### 1.1 Создайте структуру директорий
```bash
mkdir -p app/agents
touch app/agents/__init__.py
```

### 1.2 Скопируйте файлы
Разместите созданные файлы:
```
app/
├── agents/
│   ├── __init__.py                  ✅ (пустой файл)
│   ├── agent_config.py              ✅ (артефакт #1)
│   ├── requirements_agent.py        ✅ (артефакт #13 - ИСПРАВЛЕННАЯ версия!)
│   └── agent_tools.py               ✅ (артефакт #12 - ИСПРАВЛЕННАЯ версия!)
└── routes/
    └── agent.py                     ✅ (артефакт #4)
```

⚠️ **ВАЖНО:** Используйте ИСПРАВЛЕННЫЕ версии файлов:
- `requirements_agent_fixed.py` (артефакт #13) → сохраните как `requirements_agent.py`
- `agent_tools_fixed.py` (артефакт #12) → сохраните как `agent_tools.py`

Эти версии содержат правильные импорты для **langchain 1.1.2** из вашего requirements.txt.

## Шаг 2: Установка зависимостей (1 минута)

```bash
pip install langchain langchain-openai langchain-community
```

## Шаг 3: Регистрация роутера (1 минута)

В вашем главном файле приложения (например, `app/main.py`):

```python
from app.routes import agent

# Добавьте эту строку к существующим роутерам
app.include_router(agent.router, prefix="/api")
```

Пример полного main.py:
```python
from fastapi import FastAPI
from app.routes import loader, analyze_external, agent  # добавили agent

app = FastAPI(title="Requirements Analysis Service")

# Регистрируем все роутеры
app.include_router(loader.router, prefix="/api")
app.include_router(analyze_external.router, prefix="/api")
app.include_router(agent.router, prefix="/api")  # ← НОВЫЙ РОУТЕР
```

## Шаг 4: Запуск и проверка (1 минута)

### 4.1 Запустите приложение
```bash
uvicorn app.main:app --reload
```

### 4.2 Проверьте статус агента
```bash
curl http://localhost:8000/api/agent/info
```

**Ожидаемый ответ:**
```json
{
  "status": "active",
  "model": "gpt-4",
  "temperature": 0.3,
  "session": {
    "messages_count": 0,
    "service_code": null,
    "tools_available": [
      "search_requirements",
      "analyze_page",
      "check_template_compliance"
    ]
  },
  "capabilities": [...]
}
```

✅ Если видите этот ответ - агент работает!

## Шаг 5: Первый запрос (30 секунд)

### Через curl:
```bash
curl -X POST "http://localhost:8000/api/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет! Расскажи что ты умеешь?",
    "reset_history": true
  }'
```

### Через Postman:
1. Импортируйте коллекцию `agent_postman_collection.json`
2. Запустите запрос **"3. Chat - Simple Question"**

---

## 🎯 Готовые примеры запросов

### Пример 1: Поиск требований
```json
POST /api/agent/chat
{
  "message": "Найди требования по авторизации",
  "service_code": "SBP"
}
```

### Пример 2: Анализ страницы
```json
POST /api/agent/chat
{
  "message": "Проанализируй страницу 274628758"
}
```

### Пример 3: Проверка шаблона
```json
POST /api/agent/chat
{
  "message": "Проверь соответствие страницы 123456 шаблону FR"
}
```

---

## ⚠️ Решение типичных проблем

### Проблема: ModuleNotFoundError: No module named 'langchain'
**Решение:**
```bash
pip install langchain langchain-openai langchain-community
```

### Проблема: Agent не находит требования
**Решение:**
1. Убедитесь что векторное хранилище заполнено:
```bash
curl http://localhost:8000/api/debug_collections
```

2. Если пусто - загрузите требования:
```bash
curl -X POST "http://localhost:8000/api/load_pages" \
  -H "Content-Type: application/json" \
  -d '{
    "page_ids": ["274628758"],
    "service_code": "SBP"
  }'
```

### Проблема: 500 Internal Server Error
**Решение:**
1. Проверьте логи приложения
2. Убедитесь что OpenAI API key настроен:
```bash
echo $OPENAI_API_KEY
```

---

## 📊 Проверка работоспособности

Выполните эти команды для полной проверки:

```bash
# 1. Статус агента
curl http://localhost:8000/api/agent/info

# 2. Список инструментов
curl http://localhost:8000/api/agent/tools

# 3. Тестовый вопрос
curl -X POST "http://localhost:8000/api/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет!", "reset_history": true}'

# 4. Поиск требований (если векторное хранилище заполнено)
curl -X POST "http://localhost:8000/api/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Найди требования", "service_code": "SBP"}'
```

---

## ✅ Чеклист готовности

- [ ] Файлы размещены в правильных директориях
- [ ] `__init__.py` создан в `app/agents/`
- [ ] Зависимости установлены (`langchain`, `langchain-openai`)
- [ ] Роутер зарегистрирован в `main.py`
- [ ] Приложение запускается без ошибок
- [ ] `/api/agent/info` возвращает статус "active"
- [ ] `/api/agent/tools` показывает 3 инструмента
- [ ] Тестовый запрос в `/api/agent/chat` работает
- [ ] (Опционально) Векторное хранилище заполнено требованиями

---

## 🎉 Готово!

Теперь вы можете:
- Задавать вопросы агенту через API
- Искать требования по ключевым словам
- Анализировать страницы Confluence
- Проверять соответствие шаблонам

### Следующие шаги:
1. Изучите примеры в Postman коллекции
2. Попробуйте разные типы запросов
3. Настройте параметры агента в `.env` (опционально)
4. Интегрируйте с вашим UI (если планируется)

---

## 📚 Полезные ссылки

- **Детальная документация:** см. `AGENT_INTEGRATION.md`
- **Тесты:** см. `test_agent.py`
- **Postman коллекция:** см. `agent_postman_collection.json`
- **Конфигурация:** см. `app/agents/agent_config.py`

---

## 🆘 Нужна помощь?

1. Проверьте логи: `tail -f app.log | grep "Agent"`
2. Проверьте статус: `curl http://localhost:8000/api/agent/info`
3. Запустите тесты: `pytest tests/test_agent.py -v`

Удачи! 🚀