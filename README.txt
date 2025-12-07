RAG-based Requirements Analyzer
Сервис для анализа и валидации требований аналитики с использованием RAG-инфраструктуры (Retrieval-Augmented Generation).
🎯 Описание проекта
Система предназначена для автоматического анализа требований, размещенных на страницах Confluence, с использованием AI-технологий. Сервис поддерживает:

Анализ текстовых требований с контекстом из векторного хранилища
Анализ соответствия шаблонам требований различных типов
Интеграцию с Jira для анализа задач
Векторное хранилище для неизменных требований
Цветовую фильтрацию подтвержденных/неподтвержденных требований

📁 Структура проекта
Copy📁 requirements-analyzer/
├── 📁 app/                          # Основной модуль приложения
│   ├── 📁 data/                     # Конфигурационные файлы
│   │   ├── 📄 services.json         # Справочник сервисов
│   │   ├── 📄 templates.json        # Шаблоны требований
│   │   └── 📄 features.json         # Конфигурация типов шаблонов
│   ├── 📁 routes/                   # API маршруты
│   │   ├── 📄 __init__.py
│   │   ├── 📄 analyze.py            # Анализ требований
│   │   ├── 📄 health.py             # Проверка здоровья
│   │   ├── 📄 info.py               # Информация о сервисе
│   │   ├── 📄 jira.py               # Интеграция с Jira
│   │   ├── 📄 loader.py             # Загрузка документов
│   │   ├── 📄 logging_control.py    # Управление логированием
│   │   ├── 📄 services.py           # Управление сервисами
│   │   ├── 📄 template_analysis.py  # Анализ типов шаблонов
│   │   └── 📄 test_context.py       # Тестирование LLM
│   ├── 📁 services/                 # Бизнес-логика
│   │   ├── 📄 __init__.py
│   │   ├── 📄 analysis_service.py   # Сервис анализа требований
│   │   ├── 📄 context_builder.py    # Построение контекста
│   │   ├── 📄 document_service.py   # Управление документами
│   │   └── 📄 template_type_analysis.py # Анализ типов шаблонов
│   ├── 📄 __init__.py
│   ├── 📄 config.py                 # Конфигурация приложения
│   ├── 📄 confluence_loader.py      # Загрузка из Confluence
│   ├── 📄 content_extractor.py      # Извлечение контента из HTML
│   ├── 📄 embedding_store.py        # Работа с векторным хранилищем
│   ├── 📄 filter_all_fragments.py   # Фильтрация всех фрагментов
│   ├── 📄 filter_approved_fragments.py # Фильтрация подтвержденных фрагментов
│   ├── 📄 history_cleaner.py        # Очистка истории изменений
│   ├── 📄 jira_loader.py            # Загрузка из Jira
│   ├── 📄 llm_interface.py          # Интерфейс к LLM
│   ├── 📄 logging_config.py         # Конфигурация логирования
│   ├── 📄 logging_utils.py          # Утилиты логирования
│   ├── 📄 main.py                   # Точка входа FastAPI
│   ├── 📄 rag_pipeline.py           # RAG пайплайн
│   ├── 📄 semantic_search.py        # Семантический поиск
│   ├── 📄 service_registry.py       # Реестр сервисов
│   ├── 📄 style_utils.py            # Утилиты для стилей
│   └── 📄 template_registry.py      # Реестр шаблонов
├── 📄 page_prompt_template.txt      # Шаблон промпта для анализа страниц
├── 📄 template-analysis-prompt.txt  # Шаблон промпта для анализа шаблонов
├── 📄 requirements.txt              # Python зависимости
├── 📄 .env                          # Переменные окружения
└── 📄 README.md                     # Документация проекта
📋 Сводная таблица файлов по категориям
КатегорияФайлыОписаниеAPI-интерфейсapp/main.py<br>app/routes/analyze.py<br>app/routes/jira.py<br>app/routes/loader.py<br>app/routes/template_analysis.py<br>app/routes/services.py<br>app/routes/health.py<br>app/routes/info.py<br>app/routes/test_context.py<br>app/routes/logging_control.pyFastAPI приложение и все API эндпоинтыКонфигурацияapp/config.py<br>app/data/services.json<br>app/data/templates.json<br>app/data/features.json<br>.env<br>requirements.txtНастройки приложения, справочники и зависимостиРабота с эмбеддингами и хранилищемapp/embedding_store.py<br>app/semantic_search.py<br>app/services/context_builder.py<br>app/services/document_service.pyВекторное хранилище, поиск и управление документамиИнтеграция с Confluenceapp/confluence_loader.py<br>app/content_extractor.py<br>app/filter_all_fragments.py<br>app/filter_approved_fragments.py<br>app/history_cleaner.py<br>app/style_utils.pyЗагрузка и обработка контента из ConfluenceИнтеграция с Jiraapp/jira_loader.pyИзвлечение данных из задач JiraLLM-анализapp/llm_interface.py<br>app/rag_pipeline.py<br>app/services/analysis_service.py<br>app/services/template_type_analysis.py<br>page_prompt_template.txt<br>template-analysis-prompt.txtИнтерфейсы к LLM и алгоритмы анализаСервисы и реестрыapp/service_registry.py<br>app/template_registry.pyУправление сервисами и шаблонамиУтилитыapp/logging_config.py<br>app/logging_utils.pyВспомогательные функции и настройка логирования
🔗 Диаграмма зависимостей между модулями
mermaidCopygraph TB
    %% API Layer
    main[main.py] --> routes[routes/*]
    
    %% Routes
    routes --> analyze[analyze.py]
    routes --> jira[jira.py] 
    routes --> loader[loader.py]
    routes --> template_analysis[template_analysis.py]
    
    %% Services Layer
    analyze --> analysis_service[analysis_service.py]
    jira --> analysis_service
    template_analysis --> template_type_analysis[template_type_analysis.py]
    loader --> document_service[document_service.py]
    
    %% Core Analysis
    analysis_service --> context_builder[context_builder.py]
    analysis_service --> rag_pipeline[rag_pipeline.py]
    analysis_service --> confluence_loader[confluence_loader.py]
    
    %% Content Processing
    confluence_loader --> content_extractor[content_extractor.py]
    content_extractor --> filter_all[filter_all_fragments.py]
    content_extractor --> filter_approved[filter_approved_fragments.py]
    content_extractor --> style_utils[style_utils.py]
    confluence_loader --> history_cleaner[history_cleaner.py]
    
    %% Template Analysis
    template_type_analysis --> confluence_loader
    template_type_analysis --> filter_all
    
    %% Context & Search
    context_builder --> semantic_search[semantic_search.py]
    context_builder --> embedding_store[embedding_store.py]
    semantic_search --> embedding_store
    
    %% Document Management
    document_service --> embedding_store
    document_service --> confluence_loader
    
    %% LLM Integration
    rag_pipeline --> llm_interface[llm_interface.py]
    analysis_service --> llm_interface
    template_type_analysis --> llm_interface
    
    %% Registries
    analysis_service --> service_registry[service_registry.py]
    analysis_service --> template_registry[template_registry.py]
    document_service --> service_registry
    
    %% External Integrations
    jira --> jira_loader[jira_loader.py]
    
    %% Configuration
    config[config.py] --> llm_interface
    config --> confluence_loader
    config --> embedding_store
    config --> jira_loader
    
    %% Data Files
    services_json[services.json] --> service_registry
    templates_json[templates.json] --> template_registry
    features_json[features.json] --> template_type_analysis
    
    %% Logging
    logging_config[logging_config.py] --> main
    logging_utils[logging_utils.py] --> routes
    
    %% Templates
    page_prompt[page_prompt_template.txt] --> analysis_service
    template_prompt[template-analysis-prompt.txt] --> analysis_service

    %% Styling
    classDef api fill:#e1f5fe
    classDef service fill:#f3e5f5
    classDef data fill:#e8f5e8
    classDef llm fill:#fff3e0
    classDef config fill:#fce4ec
    
    class main,routes,analyze,jira,loader,template_analysis api
    class analysis_service,document_service,template_type_analysis,context_builder service
    class services_json,templates_json,features_json,page_prompt,template_prompt data
    class llm_interface,rag_pipeline llm
    class config,logging_config,logging_utils config
📝 Детальное описание файлов
🚀 API-интерфейс
app/main.py
Основная точка входа FastAPI приложения. Настраивает CORS, подключает все роутеры, инициализирует логирование и эмбеддинги.
app/routes/analyze.py
Основные эндпоинты анализа требований:

POST /analyze - анализ текстовых требований
POST /analyze_pages - анализ страниц Confluence
POST /analyze_service_pages/{code} - анализ страниц конкретного сервиса
POST /analyze_with_templates - анализ соответствия шаблонам

app/routes/jira.py
Интеграция с Jira:

POST /analyze-jira-task - анализ задач Jira с извлечением страниц Confluence
GET /jira/health - проверка состояния Jira модуля

app/routes/loader.py
Управление загрузкой документов:

POST /load_pages - загрузка страниц в векторное хранилище
POST /load_templates - загрузка шаблонов
GET /child_pages/{page_id} - получение дочерних страниц
POST /remove_service_pages - удаление фрагментов страниц

app/routes/template_analysis.py
Анализ типов шаблонов:

POST /analyze_types - определение типов шаблонов для страниц

🔧 Сервисы и бизнес-логика
app/services/analysis_service.py
Основной сервис анализа требований. Содержит функции:

analyze_text() - анализ текстовых требований
analyze_pages() - анализ страниц с опциональной проверкой шаблонов
analyze_with_templates() - детальный анализ соответствия шаблонам

app/services/context_builder.py
Построение контекста для LLM на основе векторного поиска:

Поиск релевантных документов по сущностям
Семантический поиск по платформенным и сервисным требованиям
Исключение анализируемых страниц из контекста

app/services/document_service.py
Управление документами в векторном хранилище:

Загрузка подтвержденных требований
Загрузка шаблонов
Удаление фрагментов страниц
Проверка наличия одобренных фрагментов

app/services/template_type_analysis.py
Анализ соответствия страниц типам шаблонов на основе features.json:

Проверка названия страницы
Проверка заголовков
Проверка содержимого

📊 Работа с данными
app/confluence_loader.py
Загрузка данных из Confluence:

Получение содержимого страниц по ID
Извлечение подтвержденных фрагментов
Получение дочерних страниц
Загрузка шаблонов

app/content_extractor.py
Универсальный экстрактор контента из HTML с поддержкой:

Цветовой фильтрации (подтвержденные/неподтвержденные фрагменты)
Обработки таблиц, списков, ссылок
Сохранения структуры и пробелов
Исключения зачеркнутого текста

app/filter_all_fragments.py
Извлечение всех фрагментов из HTML без учета цвета.
app/filter_approved_fragments.py
Извлечение только подтвержденных (черных) фрагментов из HTML.
app/history_cleaner.py
Удаление разделов "История изменений" из HTML контента Confluence.
🤖 LLM и AI
app/llm_interface.py
Интерфейсы к различным LLM провайдерам:

OpenAI (GPT-3.5, GPT-4)
Anthropic (Claude)
DeepSeek
HuggingFace эмбеддинги

app/rag_pipeline.py
RAG пайплайн для анализа требований:

Построение цепочек LangChain
Подсчет токенов
Извлечение JSON из ответов LLM

app/semantic_search.py
Семантический поиск в векторном хранилище:

Извлечение ключевых запросов
Поиск по названиям сущностей
Извлечение цепочек сущность.атрибут

💾 Хранилище и эмбеддинги
app/embedding_store.py
Работа с векторным хранилищем Chroma:

Создание векторных индексов
Подготовка документов с метаданными
Управление коллекциями

🔗 Интеграции
app/jira_loader.py
Интеграция с Jira Server:

Аутентификация через веб-сессию
Извлечение описаний задач
Парсинг ссылок на страницы Confluence

⚙️ Конфигурация
app/config.py
Центральная конфигурация приложения с переменными окружения для всех сервисов.
app/data/services.json
Справочник сервисов с указанием платформенности:
jsonCopy{
  "code": "UAA", 
  "name": "[UAA] Сервис аутентификации", 
  "platform": true
}
app/data/templates.json
Соответствие типов требований и ID шаблонов в Confluence.
app/data/features.json
Конфигурация для определения типов шаблонов по содержимому страниц.
🔧 Утилиты
app/style_utils.py
Утилиты для работы со стилями CSS:

Определение цветных элементов
Проверка черного цвета

app/service_registry.py
Реестр сервисов с функциями:

Загрузка справочника сервисов
Определение платформенности
Резолв кода сервиса

app/template_registry.py
Управление шаблонами требований в векторном хранилище.
🚀 Запуск проекта

Установка зависимостей:

bashCopypip install -r requirements.txt

Настройка переменных окружения в .env:

envCopyOPENAI_API_KEY=your_openai_key
CONFLUENCE_BASE_URL=https://confluence.company.com
CONFLUENCE_USER=username
CONFLUENCE_PASSWORD=password
LLM_PROVIDER=openai
LLM_MODEL=gpt-4

Запуск сервиса:

bashCopyuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Документация API: http://localhost:8000/docs

📡 Основные API эндпоинты
МетодЭндпоинтОписаниеPOST/analyzeАнализ текстовых требованийPOST/analyze_pagesАнализ страниц ConfluencePOST/analyze_with_templatesАнализ соответствия шаблонамPOST/analyze-jira-taskАнализ задач JiraPOST/analyze_typesОпределение типов шаблоновPOST/load_pagesЗагрузка страниц в хранилищеGET/servicesСписок сервисовGET/healthПроверка состояния
🛠 Технологический стек

FastAPI - веб-фреймворк
LangChain - фреймворк для LLM
ChromaDB - векторное хранилище
BeautifulSoup - парсинг HTML
HuggingFace - эмбеддинги
OpenAI/Anthropic - LLM провайдеры
Pydantic - валидация данных