# 🚀 Quick Start для langchain 1.1.2 (LangGraph)

## ⚡ Запуск агента за 5 минут

### Ваша ситуация
- ✅ У вас langchain 1.1.2
- ✅ У вас есть LangGraph
- ⚠️ AgentExecutor **не работает** (удалён в 1.1.2)
- ✅ Используем **LangGraph** вместо AgentExecutor

---

## 📦 Шаг 1: Файлы (2 минуты)

### Создайте структуру
```bash
mkdir -p app/agents
touch app/agents/__init__.py
```

### Скопируйте файлы в таком порядке

| Артефакт | → | Путь | Примечание |
|----------|---|------|------------|
| **#1** | → | `app/agents/agent_config.py` | Без изменений |
| **#12** | → | `app/agents/agent_tools.py` | Переименуйте из `agent_tools_fixed.py` |
| **#17** | → | `app/agents/requirements_agent.py` | ⚠️ **LangGraph версия!** |
| **#4** | → | `app/routes/agent.py` | Без изменений |

### ⚠️ ВАЖНО!
Используйте **Артефакт #17** (с LangGraph), а НЕ #13 (с AgentExecutor)!

---

## 🔗 Шаг 2: Регистрация (1 минута)

В `app/main.py`:
```python
from app.routes import agent

app.include_router(agent.router, prefix="/api")
```

---

## ✅ Шаг 3: Проверка (30 секунд)

```bash
# Проверка импортов
python -c "from app.agents.requirements_agent import RequirementsAgent; print('✅ OK')"
```

**Ожидается:** `✅ OK` (без ошибок!)

Если ошибки - вы используете неправильную версию файла. Нужен **#17**!

---

## 🚀 Шаг 4: Запуск (30 секунд)

```bash
uvicorn app.main:app --reload
```

**Ожидается в логах:**
```
INFO:     Application startup complete.
[RequirementsAgent] LangGraph agent created successfully
```

---

## 🧪 Шаг 5: Тест (1 минута)

### Тест 1: Статус агента
```bash
curl http://localhost:8000/api/agent/info
```

**Ожидается:**
```json
{
  "status": "active",
  "session": {
    "tools_available": [
      "search_requirements",
      "analyze_page",
      "check_template_compliance"
    ],
    "agent_type": "LangGraph ReAct Agent"
  }
}
```

### Тест 2: Простой запрос
```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет! Что ты умеешь?", "reset_history": true}'
```

**Ожидается:** Агент описывает свои возможности

---

## ✅ Готово!

Если всё работает - агент успешно интегрирован! 🎉

---

## 🐛 Если что-то не так

### Ошибка: "Cannot find reference 'AgentExecutor'"
**Причина:** Вы используете старую версию (#13)
**Решение:** Замените на **Артефакт #17**

### Ошибка: "No module named 'langgraph'"
**Причина:** LangGraph не установлен
**Решение:** 
```bash
pip install langgraph
# Или полный requirements.txt:
pip install -r requirements.txt
```

### Агент не отвечает
**Проверьте логи:**
```bash
tail -f app.log | grep "RequirementsAgent"
```

Ищите:
- ✅ `LangGraph agent created successfully`
- ❌ Ошибки создания агента

---

## 📚 Дальнейшие действия

1. ✅ Импортируйте **Артефакт #5** в Postman для удобного тестирования
2. ✅ Прочитайте **Артефакт #18** (LANGGRAPH_MIGRATION) для понимания изменений
3. ✅ Изучите **Артефакт #9** (ARCHITECTURE) для глубокого понимания

---

## 🎯 Чеклист

- [ ] Создана директория `app/agents/`
- [ ] Скопированы 4 файла (артефакты #1, #4, #12, #17)
- [ ] Использован **#17** (LangGraph версия), а не #13
- [ ] Роутер зарегистрирован в main.py
- [ ] Импорты работают без ошибок
- [ ] Приложение запускается
- [ ] `/api/agent/info` возвращает "active"
- [ ] Тестовый запрос работает

**Если все ✅ - готово к использованию!**

---

## 🆘 Дополнительная помощь

### Полная документация:
- **#18** - LANGGRAPH_MIGRATION.md (детали миграции)
- **#9** - ARCHITECTURE.md (архитектура)
- **#16** - ARTIFACTS_REFERENCE.md (справочник)

### Проверка системы:
```bash
# Проверка версий
pip show langchain langchain-core langgraph

# Должно быть:
# langchain==1.1.2
# langchain-core==1.1.1
# langgraph==1.0.4 (или выше)
```

### Тестирование:
```bash
# Полный тест
python -c "
from langgraph.prebuilt import create_react_agent
from app.agents.requirements_agent import RequirementsAgent
print('✅ All OK')
"
```

---

**Удачи!** 🚀

Если остались вопросы - читайте **Артефакт #18** (LANGGRAPH_MIGRATION.md)