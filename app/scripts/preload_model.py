# scripts/download_model.py

"""
Для ручной загрузки модели эмбеддингов в кэш ~/.cache/huggingface/ для дальнейшего копирования в docker_cache/huggingface.
Ориентир на то, что загрузка эмбеддингов из docker образа будет недоступна (внутренняя сеть).
"""

import os
import time
from sentence_transformers import SentenceTransformer

from app.config import EMBEDDING_MODEL

print("=" * 60)
print("Downloading embedding model...")
print("=" * 60)

# Показываем, куда будет сохранена модель
cache_dir = os.path.expanduser("~/.cache/huggingface/")
print(f"Cache directory: {cache_dir}")

try:
    start = time.time()
    # model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    model = SentenceTransformer(EMBEDDING_MODEL)
    elapsed = time.time() - start

    print(f"\n✓ Model downloaded successfully in {elapsed:.2f} seconds!")
    print(f"✓ Model cached at: {cache_dir}")

    # Тест
    test_embedding = model.encode("test sentence")
    print(f"✓ Test embedding dimension: {len(test_embedding)}")

except Exception as e:
    print(f"\n✗ Download failed: {e}")
    import traceback

    traceback.print_exc()