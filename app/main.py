# app/main.py - обновленная версия

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.embedding_store import get_embedding_model
from app.logging_config import setup_logging
from app.routes import (analyze, loader, info, services, health, test_context,
                        logging_control, jira, template_analysis, extractor, summary, storage, config_endpoint)

# Инициализация логирования с уровнем INFO
setup_logging()

import logging
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Requirements Analyzer",
    description="Анализ и проверка требований на основе контекста и шаблонов",
    version="1.0.0",
)

logger.info("Starting Requirements Analyzer application")

# CORS (если необходимо)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Welcome to RAG Pipeline API"}

# Для отладки
try:
    get_embedding_model()
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