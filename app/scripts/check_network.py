# app/utils/check_network.py

import time
import requests

print("Checking network access to HuggingFace...")

urls_to_check = [
    "https://huggingface.co",
    "https://cdn-lfs.huggingface.co",
]

for url in urls_to_check:
    try:
        start = time.time()
        response = requests.get(url, timeout=10)
        elapsed = time.time() - start
        print(f"✓ {url}: {response.status_code} ({elapsed:.2f}s)")
    except Exception as e:
        print(f"✗ {url}: FAILED - {e}")

print("\nTrying to download model info...")
try:
    from huggingface_hub import model_info
    start = time.time()
    info = model_info("sentence-transformers/all-MiniLM-L6-v2")
    elapsed = time.time() - start
    print(f"✓ Model info retrieved in {elapsed:.2f}s")
except Exception as e:
    print(f"✗ Failed: {e}")