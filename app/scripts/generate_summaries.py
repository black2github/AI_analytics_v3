# Путь: app/scripts/generate_summaries.py
"""
Скрипт предварительной генерации LLM summary для страниц из ChromaDB.

Назначение:
    Разделяет двухфазный пайплайн миграции:
    Фаза 1 (этот скрипт) — генерация summary через LLM на дешёвом CPU.
        Запускается локально или на бесплатном Colab CPU.
        Результат сохраняется в JSON файл {page_id: summary_text}.
    Фаза 2 (migrate_to_multi_vector.py --summaries-file) — миграция на GPU.
        L4 GPU занят только векторизацией, не ждёт LLM.

Чекпоинтинг:
    Скрипт сохраняет прогресс после каждого батча.
    При прерывании — перезапуск продолжит с того места где остановился.
    Уже обработанные page_id пропускаются автоматически.

Использование:

    # Сгенерировать summary для всех страниц:
    python app/scripts/generate_summaries.py \\
        --source-dir ./store/chroma_db \\
        --output ./summaries.json

    # Только для конкретного сервиса:
    python app/scripts/generate_summaries.py \\
        --source-dir ./store/chroma_db \\
        --output ./summaries.json \\
        --service CC

    # Параллельных LLM-запросов (default: 10):
    python app/scripts/generate_summaries.py \\
        --source-dir ./store/chroma_db \\
        --output ./summaries.json \\
        --batch-size 20

    # Только для страниц крупнее порога (экономия токенов):
    python app/scripts/generate_summaries.py \\
        --source-dir ./store/chroma_db \\
        --output ./summaries.json \\
        --min-tokens 200
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.config import CHROMA_PERSIST_DIR, UNIFIED_STORAGE_NAME

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s,%(msecs)03d [%(levelname)s] %(filename)s:%(lineno)d %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('generate_summaries.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# =============================================================================
# ЗАГРУЗКА СТРАНИЦ ИЗ LEGACY ХРАНИЛИЩА
# =============================================================================

def load_pages_from_store(
    source_dir: str,
    service_code: Optional[str] = None,
    min_tokens: int = 0,
) -> List[Dict]:
    """
    Читает страницы из legacy ChromaDB хранилища.

    Возвращает уникальные страницы (по page_id) с их контентом и заголовками.
    Legacy хранилище содержит по одному документу на страницу (или чанки).
    Для чанков берём первый чанк — он содержит начало текста, достаточное для summary.

    Args:
        source_dir: Путь к ChromaDB (legacy формат)
        service_code: Код сервиса для фильтрации (None = все)
        min_tokens: Минимальный размер страницы в токенах (0 = все)

    Returns:
        Список словарей [{id, title, approved_content}, ...]
    """
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    from app.config import LEGACY_EMBEDDING_MODEL
    from app.utils.text_processing import estimate_tokens

    logger.info(
        "[load_pages] Opening legacy store: %s",
        source_dir
    )

    # Legacy хранилище использует all-MiniLM-L6-v2
    embeddings = HuggingFaceEmbeddings(
        model_name=LEGACY_EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    vs = Chroma(
        collection_name=UNIFIED_STORAGE_NAME,
        embedding_function=embeddings,
        persist_directory=source_dir,
    )

    # Строим фильтр
    conditions = [{"doc_type": {"$eq": "requirement"}}]
    if service_code:
        conditions.append({"service_code": {"$eq": service_code}})

    where = {"$and": conditions} if len(conditions) > 1 else conditions[0]

    logger.info("[load_pages] Fetching documents from store...")
    results = vs.get(
        where=where,
        include=["documents", "metadatas"],
    )

    if not results or not results.get("ids"):
        logger.warning("[load_pages] No documents found")
        return []

    total_docs = len(results["ids"])
    logger.info("[load_pages] Found %d raw documents", total_docs)

    # Дедупликация по page_id — берём документ с наибольшим контентом
    pages_map: Dict[str, Dict] = {}
    for doc, meta in zip(results["documents"], results["metadatas"]):
        page_id = meta.get("page_id")
        if not page_id or not doc:
            continue
        existing = pages_map.get(page_id)
        if existing is None or len(doc) > len(existing["approved_content"]):
            pages_map[page_id] = {
                "id": page_id,
                "title": meta.get("title", ""),
                "approved_content": doc,
            }

    pages = list(pages_map.values())
    logger.info("[load_pages] Deduplicated to %d unique pages", len(pages))

    # Фильтрация по минимальному размеру
    if min_tokens > 0:
        before = len(pages)
        pages = [
            p for p in pages
            if estimate_tokens(p["approved_content"]) >= min_tokens
        ]
        logger.info(
            "[load_pages] After min_tokens=%d filter: %d pages (filtered %d small)",
            min_tokens, len(pages), before - len(pages)
        )

    return pages


# =============================================================================
# ГЕНЕРАЦИЯ SUMMARY
# =============================================================================

async def generate_summaries(
    pages: List[Dict],
    output_file: str,
    batch_size: int = 10,
    existing: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Генерирует LLM summary для списка страниц с чекпоинтингом.

    Уже обработанные page_id (из existing) пропускаются.
    После каждого батча результаты записываются в output_file —
    при прерывании прогресс сохраняется.

    Args:
        pages: Список страниц [{id, title, approved_content}, ...]
        output_file: Путь к JSON файлу для сохранения результатов
        batch_size: Максимальное число параллельных LLM-запросов
        existing: Уже готовые summary (для продолжения после прерывания)

    Returns:
        Словарь {page_id: summary_text}
    """
    from app.services.page_summary_generator import create_summary_generator

    summaries: Dict[str, str] = dict(existing or {})
    generator = create_summary_generator()

    # Фильтруем уже обработанные страницы
    pending = [p for p in pages if p["id"] not in summaries]

    if not pending:
        logger.info("[generate_summaries] All pages already processed, nothing to do")
        return summaries

    total = len(pending)
    logger.info(
        "[generate_summaries] Processing %d pages (batch_size=%d, skipping %d already done)",
        total, batch_size, len(summaries)
    )

    semaphore = asyncio.Semaphore(batch_size)
    processed = 0
    start_time = time.time()

    async def summarize_one(page: Dict) -> tuple:
        page_id = page["id"]
        content = page["approved_content"]
        async with semaphore:
            try:
                summary = await generator.generate_llm(content, max_tokens=500)
                logger.debug(
                    "[summarize_one] OK: page_id=%s (%d chars -> %d chars summary)",
                    page_id, len(content), len(summary)
                )
                return page_id, summary, None
            except Exception as e:
                logger.warning(
                    "[summarize_one] LLM failed for page_id=%s: %s. Using extractive.",
                    page_id, str(e)
                )
                fallback = generator.generate_extractive(content, max_length=500)
                return page_id, fallback, str(e)

    # Обрабатываем батчами с чекпоинтингом
    checkpoint_every = max(batch_size, 50)
    batch_tasks = []

    for i, page in enumerate(pending):
        batch_tasks.append(summarize_one(page))

        # Запускаем батч и сохраняем чекпоинт
        if len(batch_tasks) >= checkpoint_every or i == len(pending) - 1:
            results = await asyncio.gather(*batch_tasks)

            for page_id, summary, error in results:
                summaries[page_id] = summary
                processed += 1

            # Чекпоинт — сохраняем после каждого батча
            _save_summaries(summaries, output_file)

            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta_sec = (total - processed) / rate if rate > 0 else 0

            logger.info(
                "[generate_summaries] Progress: %d/%d (%.0f%%) | "
                "%.1f pages/sec | ETA: %.0f min",
                processed, total,
                100 * processed / total,
                rate,
                eta_sec / 60,
            )

            batch_tasks = []

    logger.info(
        "[generate_summaries] Done. %d summaries generated in %.1f min",
        len(summaries),
        (time.time() - start_time) / 60,
    )

    return summaries


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def _save_summaries(summaries: Dict[str, str], path: str) -> None:
    """Сохраняет summary в JSON файл атомарно (через временный файл)."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    logger.debug("[_save_summaries] Saved %d summaries to %s", len(summaries), path)


def _load_existing_summaries(path: str) -> Dict[str, str]:
    """Загружает существующие summary из JSON файла (для продолжения после прерывания)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(
            "[_load_existing] Loaded %d existing summaries from %s",
            len(data), path
        )
        return data
    except Exception as e:
        logger.warning("[_load_existing] Could not load %s: %s", path, e)
        return {}


def _print_stats(pages: List[Dict], summaries: Dict[str, str]) -> None:
    """Выводит статистику генерации."""
    from app.utils.text_processing import estimate_tokens

    total_pages = len(pages)
    done = sum(1 for p in pages if p["id"] in summaries)
    pending = total_pages - done

    sizes = [estimate_tokens(p["approved_content"]) for p in pages]
    avg_tokens = sum(sizes) / len(sizes) if sizes else 0

    logger.info("=" * 60)
    logger.info("SUMMARY GENERATION STATS")
    logger.info("  total pages    : %d", total_pages)
    logger.info("  already done   : %d", done)
    logger.info("  pending        : %d", pending)
    logger.info("  avg tokens     : %.0f", avg_tokens)
    logger.info("=" * 60)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pre-generate LLM summaries for ChromaDB pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate summaries for all pages:
  python app/scripts/generate_summaries.py \\
      --source-dir ./store/chroma_db \\
      --output ./summaries.json

  # Only for service CC:
  python app/scripts/generate_summaries.py \\
      --source-dir ./store/chroma_db \\
      --output ./summaries_cc.json \\
      --service CC

  # With larger batch for faster processing:
  python app/scripts/generate_summaries.py \\
      --source-dir ./store/chroma_db \\
      --output ./summaries.json \\
      --batch-size 20

  # Skip pages smaller than 200 tokens (save LLM tokens):
  python app/scripts/generate_summaries.py \\
      --source-dir ./store/chroma_db \\
      --output ./summaries.json \\
      --min-tokens 200

  # Show stats without generating:
  python app/scripts/generate_summaries.py \\
      --source-dir ./store/chroma_db \\
      --output ./summaries.json \\
      --dry-run
        """
    )
    parser.add_argument(
        '--source-dir', type=str, default=None,
        help='Legacy ChromaDB directory. Defaults to CHROMA_PERSIST_DIR from config.'
    )
    parser.add_argument(
        '--output', type=str, required=True,
        help='Output JSON file path for summaries (e.g. ./summaries.json)'
    )
    parser.add_argument(
        '--service', type=str, default=None,
        help='Process only this service code (default: all services)'
    )
    parser.add_argument(
        '--batch-size', type=int, default=10,
        help='Max parallel LLM requests (default: 10)'
    )
    parser.add_argument(
        '--min-tokens', type=int, default=0,
        help='Skip pages smaller than this many tokens (default: 0 = process all)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show stats without generating any summaries'
    )

    args = parser.parse_args()

    source_dir = (
        os.path.abspath(args.source_dir)
        if args.source_dir
        else os.path.abspath(CHROMA_PERSIST_DIR)
    )
    output_file = os.path.abspath(args.output)

    if not os.path.exists(source_dir):
        logger.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("GENERATE SUMMARIES")
    logger.info("  source_dir : %s", source_dir)
    logger.info("  output     : %s", output_file)
    logger.info("  service    : %s", args.service or "all")
    logger.info("  batch_size : %d", args.batch_size)
    logger.info("  min_tokens : %d", args.min_tokens)
    logger.info("  dry_run    : %s", args.dry_run)
    logger.info("  started    : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    # Загружаем страницы из хранилища
    pages = load_pages_from_store(
        source_dir=source_dir,
        service_code=args.service,
        min_tokens=args.min_tokens,
    )

    if not pages:
        logger.warning("No pages to process. Exiting.")
        sys.exit(0)

    # Загружаем уже готовые summary (чекпоинт)
    existing = _load_existing_summaries(output_file)

    pending_count = sum(1 for p in pages if p["id"] not in existing)
    logger.info(
        "Pages: total=%d, already done=%d, pending=%d",
        len(pages), len(existing), pending_count
    )

    if args.dry_run:
        _print_stats(pages, existing)
        logger.info("DRY RUN — no summaries generated")
        logger.info("Would process %d pages via LLM", pending_count)
        sys.exit(0)

    if pending_count == 0:
        logger.info("All pages already have summaries. Nothing to do.")
        sys.exit(0)

    # Генерируем summary
    summaries = asyncio.run(
        generate_summaries(
            pages=pages,
            output_file=output_file,
            batch_size=args.batch_size,
            existing=existing,
        )
    )

    logger.info("=" * 60)
    logger.info("COMPLETED")
    logger.info("  summaries saved : %d", len(summaries))
    logger.info("  output file     : %s", output_file)
    logger.info("  finished        : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)


if __name__ == '__main__':
    main()