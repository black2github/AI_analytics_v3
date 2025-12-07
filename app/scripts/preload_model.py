# scripts/download_model.py
import os
import time
from sentence_transformers import SentenceTransformer

print("=" * 60)
print("Downloading embedding model...")
print("=" * 60)

# Показываем, куда будет сохранена модель
cache_dir = os.path.expanduser("~/.cache/huggingface/")
print(f"Cache directory: {cache_dir}")

try:
    start = time.time()
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
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