# Можете выполнить и показать результат:
from app.config import (
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    OPENAI_API_KEY,
    UNIFIED_STORAGE_NAME,
    CHUNK_MAX_PAGE_SIZE,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_MODE
)
from app.embedding_store import get_vectorstore
a = CHUNK_MODE
store = get_vectorstore("unified_requirements")
docs = store.similarity_search("интеграция", k=1)
print(docs[0].metadata)  # <- вот это