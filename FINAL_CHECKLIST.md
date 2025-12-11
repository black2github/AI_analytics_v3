# ✅ Финальный чек-лист интеграции агента

## 📋 Перед началом

- [ ] У вас есть requirements.txt с langchain 1.1.2
- [ ] Python 3.8+ установлен
- [ ] FastAPI приложение уже работает
- [ ] OpenAI API key настроен (если используете GPT)

---

## 🔧 Шаг 1: Подготовка структуры (2 минуты)

```bash
# Создайте директорию
mkdir -p app/agents

# Создайте пустой __init__.py
touch app/agents/__init__.py
```

**Чек-лист:**
- [ ] Директория `app/agents/` создана
- [ ] Файл `app/agents/__init__.py` существует (может быть пустым)

---

## 📦 Шаг 2: Копирование файлов (3 минуты)

### ⚠️ ВАЖНО: Используйте правильные версии!

Скопируйте файлы из артефактов в следующем порядке:

1. **agent_config.py**
   - Артефакт: `#1` (agent_config.py)
   - Путь: `app/agents/agent_config.py`
   - [ ] Файл скопирован

2. **requirements_agent.py** ⚠️ ИСПРАВЛЕННАЯ ВЕРСИЯ
   - Артефакт: `#13` (requirements_agent_fixed.py)
   - Путь: `app/agents/requirements_agent.py`
   - **Переименуйте:** `requirements_agent_fixed.py` → `requirements_agent.py`
   - [ ] Файл скопирован и переименован

3. **agent_tools.py** ⚠️ ИСПРАВЛЕННАЯ ВЕРСИЯ
   - Артефакт: `#12` (agent_tools_fixed.py)
   - Путь: `app/agents/agent_tools.py`
   - **Переименуйте:** `agent_tools_fixed.py` → `agent_tools.py`
   - [ ] Файл скопирован и переименован

4. **agent.py** (API routes)
   - Артефакт: `#4` (agent.py)
   - Путь: `app/routes/agent.py`
   - [ ] Файл скопирован

### Итоговая структура:
```
app/
├── agents/
│   ├── __init__.py              ✅
│   ├── agent_config.py          ✅ (артефакт #1)
│   ├── requirements_agent.py    ✅ (артефакт #13)
│   └── agent_tools.py           ✅ (артефакт #12)
└── routes/
    └── agent.py                 ✅ (артефакт #4)
```

- [ ] Все 5 файлов на месте
- [ ] Использованы ИСПРАВЛЕННЫЕ версии (#12 и #13)

---

## 📚 Шаг 3: Зависимости (1 минута)

### Проверка существующих пакетов

Ваш `requirements.txt` уже содержит всё необходимое! Проверьте:

```bash
# Проверка установленных версий
pip show langchain langchain-core langchain-openai

# Должны быть установлены:
# langchain==1.1.2
# langchain-core==1.1.1
# langchain-openai==1.1.0
```

**Если пакеты не установлены или версии отличаются:**
```bash
pip install -r requirements.txt
```

**Чек-лист:**
- [ ] `langchain==1.1.2` установлен
- [ ] `langchain-core==1.1.1` установлен
- [ ] `langchain-openai==1.1.0` установлен
- [ ] Нет ошибок при импорте

---

## 🔗 Шаг 4: Регистрация роутера (2 минуты)

В файле `app/main.py` добавьте импорт и регистрацию:

```python
# В начале файла, к другим импортам роутеров
from app.routes import loader, analyze_external, agent  # ← добавьте agent

# В раздел регистрации роутеров
app.include_router(loader.router, prefix="/api")
app.include_router(analyze_external.router, prefix="/api")
app.include_router(agent.router, prefix="/api")  # ← добавьте эту строку
```

**Чек-лист:**
- [ ] Импорт `agent` добавлен
- [ ] Роутер зарегистрирован с `app.include_router()`
- [ ] Нет ошибок при запуске приложения

---

## 🚀 Шаг 5: Первый запуск (1 минута)

### 5.1 Запустите приложение
```bash
uvicorn app.main:app --reload
```

**Ожидаемый вывод в логах:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
✅ AI Agent initialized with 3 tools
```

- [ ] Приложение запустилось без ошибок
- [ ] В логах есть сообщение об инициализации агента

### 5.2 Проверьте endpoints
```bash
# 1. Проверка документации
curl http://localhost:8000/docs
# Должен открыться Swagger UI с новыми endpoints

# 2. Проверка статуса агента
curl http://localhost:8000/api/agent/info
```

**Ожидаемый ответ от /agent/info:**
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
  }
}
```

- [ ] `/docs` открывается и показывает endpoints агента
- [ ] `/api/agent/info` возвращает статус "active"
- [ ] В ответе 3 доступных инструмента

---

## 🧪 Шаг 6: Тестирование (2 минуты)

### Тест 1: Простой вопрос
```bash
curl -X POST "http://localhost:8000/api/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет! Расскажи что ты умеешь?",
    "reset_history": true
  }'
```

**Ожидается:**
- [ ] Статус: 200 OK
- [ ] В ответе есть поле `"response"` с текстом
- [ ] Агент описывает свои возможности

### Тест 2: Проверка инструментов (если векторное хранилище заполнено)
```bash
curl -X POST "http://localhost:8000/api/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Найди требования по авторизации",
    "service_code": "SBP"
  }'
```

**Ожидается:**
- [ ] Статус: 200 OK
- [ ] В `tools_used` есть запись о `search_requirements`
- [ ] Агент нашёл требования или сообщил об их отсутствии

---

## 🔍 Шаг 7: Диагностика (если что-то не работает)

### Проверка 1: Импорты
```bash
python -c "
from app.agents.requirements_agent import RequirementsAgent
from app.agents.agent_tools import search_requirements_tool
print('✅ Imports OK')
"
```

- [ ] Импорты работают без ошибок

### Проверка 2: Логи
```bash
# Запустите приложение и проверьте логи
uvicorn app.main:app --reload --log-level debug
```

Ищите в логах:
- [ ] `[RequirementsAgent] Initializing agent`
- [ ] `[RequirementsAgent] Agent initialized with 3 tools`
- [ ] Нет ошибок типа `ModuleNotFoundError` или `ImportError`

### Проверка 3: Векторное хранилище
```bash
curl http://localhost:8000/api/debug_collections
```

- [ ] Векторное хранилище доступно
- [ ] Есть хотя бы несколько документов (если планируете тестировать поиск)

---

## 📊 Финальная проверка работоспособности

### Обязательные тесты:
- [ ] ✅ Приложение запускается
- [ ] ✅ `/api/agent/info` возвращает корректный ответ
- [ ] ✅ `/api/agent/tools` показывает 3 инструмента
- [ ] ✅ Простой тестовый запрос работает
- [ ] ✅ Нет ошибок в логах

### Опциональные тесты (если векторное хранилище заполнено):
- [ ] Поиск требований работает
- [ ] Анализ страницы работает
- [ ] Проверка шаблона работает

---

## 🎯 Готовность к продакшену (опционально)

Для использования в продакшене дополнительно:

- [ ] Настроен мониторинг и алерты
- [ ] Добавлен rate limiting
- [ ] Настроена аутентификация
- [ ] Логирование настроено на production уровень
- [ ] Проведено нагрузочное тестирование
- [ ] Настроено сохранение истории диалогов (если нужно)

---

## 🐛 Частые проблемы и решения

### Проблема: `Cannot find reference 'AgentExecutor'`
**Решение:** Вы используете старую версию файла. Убедитесь что используете:
- `requirements_agent_fixed.py` (артефакт #13)
- `agent_tools_fixed.py` (артефакт #12)

### Проблема: `ModuleNotFoundError: No module named 'langchain'`
**Решение:**
```bash
pip install -r requirements.txt
```

### Проблема: Агент не находит требования
**Решение:** Загрузите тестовые данные:
```bash
curl -X POST "http://localhost:8000/api/load_pages" \
  -H "Content-Type: application/json" \
  -d '{"page_ids": ["274628758"], "service_code": "SBP"}'
```

### Проблема: 500 Internal Server Error
**Решение:** 
1. Проверьте логи приложения
2. Убедитесь что `OPENAI_API_KEY` установлен
3. Проверьте что все файлы скопированы правильно

---

## ✅ Итоговый чек-лист

Перед тем как закрыть эту инструкцию, убедитесь:

### Структура:
- [ ] Все 5 файлов скопированы
- [ ] Используются ИСПРАВЛЕННЫЕ версии (#12, #13)
- [ ] `__init__.py` создан

### Зависимости:
- [ ] langchain 1.1.2 установлен
- [ ] Все импорты работают

### Интеграция:
- [ ] Роутер зарегистрирован в main.py
- [ ] Приложение запускается

### Тестирование:
- [ ] `/api/agent/info` работает
- [ ] Базовый чат работает
- [ ] Нет ошибок в логах

---

## 🎉 Поздравляем!

Если все пункты отмечены ✅ - ваш агент полностью интегрирован и готов к работе!

### Следующие шаги:
1. Протестируйте на реальных данных
2. Импортируйте Postman коллекцию для удобного тестирования
3. Изучите архитектуру в `ARCHITECTURE.md`
4. Начните планировать расширение функциональности

**Удачи с вашим AI-агентом!** 🚀