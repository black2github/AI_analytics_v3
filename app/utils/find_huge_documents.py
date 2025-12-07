# app/utils/find_huge_documents_fixed.py

import logging
from app.config import UNIFIED_STORAGE_NAME
from app.embedding_store import get_vectorstore
from app.llm_interface import get_embeddings_model
from app.utils.tokens_budget_utils import count_tokens

logger = logging.getLogger(__name__)


def find_huge_documents(
        min_chars: int = 10000,  # Минимум символов для отчета
        show_token_estimate: bool = True,
        top_n: int = 20
):
    """
    Находит и выводит информацию о больших документах

    Args:
        min_chars: Минимальный размер документа в символах для включения в отчет
        show_token_estimate: Показывать оценку токенов
        top_n: Сколько документов показать
    """
    print("\n" + "=" * 80)
    print("(?) ПОИСК БОЛЬШИХ ДОКУМЕНТОВ В ХРАНИЛИЩЕ")
    print("=" * 80 + "\n")

    embeddings_model = get_embeddings_model()
    store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

    data = store.get()

    if not data.get('documents'):
        print("(X) Документы не найдены в хранилище")
        return []

    print(f"(=) Всего документов в хранилище: {len(data['documents'])}\n")

    # Собираем информацию о всех документах
    all_docs_info = []

    for doc_content, metadata in zip(data['documents'], data['metadatas']):
        size_chars = len(doc_content)

        # Оценка токенов
        if show_token_estimate:
            try:
                tokens = count_tokens(doc_content)
            except Exception as e:
                # Fallback: грубая оценка
                tokens = size_chars // 3  # для русского текста
                logger.debug(f"Token count fallback: {e}")
        else:
            tokens = size_chars // 3

        doc_info = {
            'page_id': metadata.get('page_id'),
            'title': metadata.get('title', 'Без названия'),
            'size_chars': size_chars,
            'size_tokens': tokens,
            'service_code': metadata.get('service_code', 'unknown'),
            'doc_type': metadata.get('doc_type', 'unknown'),
            'is_full_page': metadata.get('is_full_page', True),
            'chunk_index': metadata.get('chunk_index'),
            'total_chunks': metadata.get('total_chunks')
        }

        all_docs_info.append(doc_info)

    # Фильтруем большие документы
    large_docs = [d for d in all_docs_info if d['size_chars'] >= min_chars]

    # Сортируем по размеру
    large_docs.sort(key=lambda x: x['size_chars'], reverse=True)

    print(f"($) Документов больше {min_chars:,} символов: {len(large_docs)}\n")

    if not large_docs:
        print("(V) Проблемных больших документов не найдено!")

        # Показываем статистику распределения
        print("\n(=) Распределение по размерам (все документы):")
        size_ranges = [
            (0, 1000, "Очень маленькие"),
            (1000, 3000, "Маленькие"),
            (3000, 10000, "Средние"),
            (10000, 50000, "Большие"),
            (50000, float('inf'), "Огромные")
        ]

        for min_s, max_s, label in size_ranges:
            count = len([d for d in all_docs_info if min_s <= d['size_chars'] < max_s])
            if count > 0:
                print(
                    f"  {label:20s} ({min_s:>6,} - {max_s if max_s != float('inf') else '∞':>6} chars): {count:>5} docs")

        return []

    # Показываем топ-N больших документов
    print(f"(!!!) ТОП-{min(top_n, len(large_docs))} САМЫХ БОЛЬШИХ ДОКУМЕНТОВ:\n")
    print("-" * 80)

    for i, doc in enumerate(large_docs[:top_n], 1):
        print(f"\n#{i}")
        print(f"(ID) Page ID:     {doc['page_id']}")
        print(f"(M) Title:       {doc['title'][:70]}{'...' if len(doc['title']) > 70 else ''}")
        print(f"($) Size:        {doc['size_chars']:,} chars  (~{doc['size_tokens']:,} tokens)")
        print(f"(S)  Service:     {doc['service_code']}")
        print(f"(T) Type:        {doc['doc_type']}")

        if not doc['is_full_page']:
            print(f"(C)  Chunk:       {doc['chunk_index'] + 1}/{doc['total_chunks']}")
        else:
            print(f"(ID) Full page:   Yes")

        # Оценка проблемности
        if doc['size_tokens'] > 100000:
            print(f"(!)  STATUS:      (!!!) КРИТИЧНО! Не влезет ни в одну LLM!")
        elif doc['size_tokens'] > 10000:
            print(f"(!)  STATUS:      (!!) Проблема для маленьких моделей (Llama 3.2 3B)")
        elif doc['size_tokens'] > 5000:
            print(f"(!)  STATUS:      (!) Большой, но управляемый")
        else:
            print(f"(!)  STATUS:      (V) Нормальный размер")

        print("-" * 80)

    # Рекомендации
    print("\n РЕКОМЕНДАЦИИ:\n")

    critical_docs = [d for d in large_docs if d['size_tokens'] > 100000]
    if critical_docs:
        print(f"(!!!) КРИТИЧНО: {len(critical_docs)} документов > 100k токенов")
        print(f"   Действие: Немедленно удалить или переиндексировать с chunking")
        print(f"   Команда: DocumentService.remove_page_fragments([page_ids])\n")

    problem_docs = [d for d in large_docs if 10000 < d['size_tokens'] <= 100000]
    if problem_docs:
        print(f"(!!) ПРОБЛЕМА: {len(problem_docs)} документов > 10k токенов")
        print(f"   Действие: Переиндексировать с adaptive chunking")
        print(f"   Параметры: max_full_page_size=3000, chunk_size=1500\n")

    large_but_ok = [d for d in large_docs if 5000 < d['size_tokens'] <= 10000]
    if large_but_ok:
        print(f"(!) ПРИЕМЛЕМО: {len(large_but_ok)} документов 5k-10k токенов")
        print(f"   Действие: Можно оставить как есть или применить chunking\n")

    return large_docs


def analyze_document_distribution():
    """Анализ распределения размеров документов"""
    print("\n" + "=" * 80)
    print("(=) ДЕТАЛЬНЫЙ АНАЛИЗ РАСПРЕДЕЛЕНИЯ РАЗМЕРОВ")
    print("=" * 80 + "\n")

    embeddings_model = get_embeddings_model()
    store = get_vectorstore(UNIFIED_STORAGE_NAME, embedding_model=embeddings_model)

    data = store.get()

    if not data.get('documents'):
        print("(X) Документы не найдены")
        return

    sizes = [len(doc) for doc in data['documents']]
    tokens = [count_tokens(doc) for doc in data['documents']]

    print(f"Всего документов: {len(sizes):,}")
    print(f"\n($) СТАТИСТИКА ПО СИМВОЛАМ:")
    print(f"  Минимум:    {min(sizes):>10,} chars")
    print(f"  Медиана:    {sorted(sizes)[len(sizes) // 2]:>10,} chars")
    print(f"  Среднее:    {sum(sizes) // len(sizes):>10,} chars")
    print(f"  Максимум:   {max(sizes):>10,} chars")

    print(f"\n(S) СТАТИСТИКА ПО ТОКЕНАМ:")
    print(f"  Минимум:    {min(tokens):>10,} tokens")
    print(f"  Медиана:    {sorted(tokens)[len(tokens) // 2]:>10,} tokens")
    print(f"  Среднее:    {sum(tokens) // len(tokens):>10,} tokens")
    print(f"  Максимум:   {max(tokens):>10,} tokens")

    # Процентили
    sorted_tokens = sorted(tokens)
    print(f"\n(P) ПРОЦЕНТИЛИ (токены):")
    for p in [50, 75, 90, 95, 99]:
        idx = int(len(sorted_tokens) * p / 100)
        print(f"  {p}%:        {sorted_tokens[idx]:>10,} tokens")

    # Распределение по диапазонам
    print(f"\n(=) РАСПРЕДЕЛЕНИЕ ПО ДИАПАЗОНАМ:")
    ranges = [
        (0, 500, "Очень маленькие"),
        (500, 1500, "Маленькие"),
        (1500, 3000, "Средние"),
        (3000, 5000, "Выше среднего"),
        (5000, 10000, "Большие"),
        (10000, 50000, "Очень большие"),
        (50000, 100000, "Огромные"),
        (100000, float('inf'), "КРИТИЧНЫЕ")
    ]

    for min_t, max_t, label in ranges:
        count = len([t for t in tokens if min_t <= t < max_t])
        if count > 0:
            pct = count / len(tokens) * 100
            bar = "|" * int(pct / 2)
            print(
                f"  {label:20s} {min_t:>6,}-{max_t if max_t != float('inf') else '-':>6} tokens: {count:>5} ({pct:>5.1f}%) {bar}")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    # Полный анализ
    analyze_document_distribution()

    # Поиск больших документов (> 10k символов)
    large_docs = find_huge_documents(min_chars=10000, top_n=20)

    # Если хотите более низкий порог:
    # large_docs = find_huge_documents(min_chars=5000, top_n=30)