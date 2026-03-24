# app/main.py - обновленная версия

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.llm_interface import get_embeddings_model
from app.logging_config import setup_logging
from app.routes import (analyze, loader, info, services, health, test_context, analyze_external, load_external,
                        logging_control, jira, template_analysis, extractor, summary, storage, config_endpoint)
from app.routes import agent

# Инициализация логирования с уровнем INFO
setup_logging()

import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Requirements Analysis Service with AI Agent",
    description="""
    Сервис анализа требований к системе ДБО с интегрированным LLM-агентом.

    Возможности:
    - Загрузка и индексация требований из Confluence
    - Анализ требований через LLM
    - Проверка соответствия шаблонам
    - 🆕 Интерактивный AI-агент для консультации по требованиям

    AI-агент умеет:
    - Искать требования по ключевым словам
    - Анализировать страницы Confluence
    - Проверять соответствие шаблонам
    - Отвечать на вопросы о требованиях
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

logger.info("Starting Requirements Analyzer application")

# CORS (если необходимо)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение всех маршрутов
app.include_router(analyze.router)
app.include_router(loader.router)
app.include_router(services.router)
app.include_router(health.router)
app.include_router(info.router)
app.include_router(test_context.router)
app.include_router(logging_control.router)
app.include_router(jira.router)
app.include_router(template_analysis.router)
app.include_router(extractor.router)
app.include_router(summary.router)
app.include_router(storage.router)
app.include_router(config_endpoint.router, tags=["Configuration"])
app.include_router(analyze_external.router, tags=["Analysis"])
app.include_router(load_external.router, tags=["Loads"])
# ============================================================================
# НОВЫЙ РОУТЕР: AI-агент
# ============================================================================
app.include_router(
    agent.router,
    # prefix="/api",
    tags=["🤖 AI-агент"]
)

logger.info("✅ AI-агент зарегистрирован: /agent/chat")


@app.get("/")
async def root():
    """Корневой endpoint с информацией о сервисе"""
    return {
        "service": "Requirements Analysis Service",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "Confluence integration",
            "Requirements analysis",
            "Template compliance checking",
            "AI-powered agent for requirements consulting"
        ],
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "agent_chat": "/agent/chat",
            "agent_info": "/agent/info",
            "agent_tools": "/agent/tools"
        },
        "quick_start": {
            "test_agent": "POST /agent/chat with message='Привет!'",
            "get_agent_info": "GET /agent/info",
            "list_tools": "GET /agent/tools"
        }
    }


# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске приложения"""
    logger.info("=" * 60)
    logger.info("🚀 Starting Requirements Analysis Service v2.0")
    logger.info("=" * 60)

    # Проверяем доступность компонентов
    try:
        # Проверка векторного хранилища
        from app.embedding_store import get_vectorstore
        from app.config import UNIFIED_STORAGE_NAME

        vectorstore = get_vectorstore(UNIFIED_STORAGE_NAME)
        logger.info("✅ Vector store initialized: %s", vectorstore)

    except Exception as e:
        logger.warning("⚠️  Vector store initialization: %s", str(e))

    try:
        # Проверка агента
        from app.routes.agent import get_agent_instance
        agent = get_agent_instance()
        logger.info("✅ AI Agent initialized with %d tools", len(agent.tools))

    except Exception as e:
        logger.error("❌ AI Agent initialization failed: %s", str(e))

    logger.info("=" * 60)
    logger.info("📚 Documentation: http://localhost:8000/docs")
    logger.info("🤖 AI Agent: http://localhost:8000/agent/info")
    logger.info("=" * 60)


# ============================================================================
# SHUTDOWN EVENT
# ============================================================================

@app.on_event("shutdown")
async def shutdown_event():
    """Очистка ресурсов при остановке"""
    logger.info("🛑 Shutting down Requirements Analysis Service...")

    # Здесь можно добавить логику очистки
    # Например, сохранение истории диалогов агента

    logger.info("✅ Shutdown complete")


# ============================================================================
# ДОПОЛНИТЕЛЬНЫЕ УТИЛИТЫ ДЛЯ ОТЛАДКИ
# ============================================================================

@app.get("/debug/agent-status", tags=["Debug"])
async def debug_agent_status():
    """
    Отладочная информация о состоянии агента.
    Используйте для проверки работоспособности.
    """
    try:
        from app.routes.agent import get_agent_instance
        from app.agents.agent_config import AGENT_MODEL, AGENT_TEMPERATURE

        agent = get_agent_instance()
        summary = agent.get_conversation_summary()

        return {
            "agent_status": "active",
            "model": AGENT_MODEL,
            "temperature": AGENT_TEMPERATURE,
            "tools_count": len(agent.tools),
            "tools_list": [tool.name for tool in agent.tools],
            "session": summary,
            "ready": True
        }
    except Exception as e:
        return {
            "agent_status": "error",
            "error": str(e),
            "ready": False
        }


@app.post("/debug/agent-test", tags=["Debug"])
async def debug_agent_test():
    """
    Быстрый тест агента с предустановленным вопросом.
    Используйте для проверки после деплоя.
    """
    try:
        from app.routes.agent import agent_chat, ChatRequest

        test_request = ChatRequest(
            message="Привет! Это тестовый запрос. Ответь коротко что ты умеешь.",
            reset_history=True
        )

        response = await agent_chat(test_request)

        return {
            "test": "success",
            "response_length": len(response.response),
            "tools_used": response.tools_used,
            "agent_works": True
        }
    except Exception as e:
        logger.error("Agent test failed: %s", str(e))
        return {
            "test": "failed",
            "error": str(e),
            "agent_works": False
        }


# Прогрев модели эмбеддингов при старте приложения
try:
    get_embeddings_model()
    logger.info("Embedding model initialized successfully")
except Exception as e:
    logger.error("Failed to initialize embedding model: %s", str(e))

try:
    import chromadb

    chroma_version = chromadb.__version__
    logger.info(f"ChromaDB version: {chroma_version}")

    # Предупреждение для проблемных версий
    if chroma_version.startswith("0.4.") or chroma_version.startswith("0.5."):
        logger.warning("ChromaDB version %s may have issues with complex filters. Using simplified filtering.",
                       chroma_version)

except Exception as e:
    logger.warning("Could not determine ChromaDB version: %s", str(e))