# tests/quick_test_hybrid.py
"""
Быстрый тест Hybrid Search для Context Retrieval Agent.

Использование:
    python quick_test_hybrid.py
"""

import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.context_retrieval_agent import ContextRetrievalAgent


def test_hybrid_vs_semantic():
    """Сравнение Hybrid Search vs Semantic Search."""

    print("\n" + "=" * 80)
    print("ТЕСТ: Hybrid Search vs Semantic Search")
    print("=" * 80)

    # Создаём агента
    agent = ContextRetrievalAgent("CC")

    # Тестовый запрос с точным названием
    query = "Заявка на выпуск карты и открытие счета"

    print(f"\nЗапрос: '{query}'")
    print(f"\n{'─' * 80}")

    # 1. С Hybrid Search
    print("\n1. HYBRID SEARCH (BM25 + Semantic):")
    print("   Веса: BM25=0.5, Semantic=0.5")

    context_hybrid = agent.retrieve_context(
        query,
        use_hybrid_search=True,
        top_k=10
    )

    print(f"\n   Найдено страниц: {len(context_hybrid.confirmed_pages)}")
    print(f"\n   Топ-5:")
    for i, page in enumerate(context_hybrid.confirmed_pages[:5], 1):
        print(f"   {i}. [{page.page_id}] {page.title}")
        print(f"      Score: {page.relevance_score:.4f}")

    # 2. Только Semantic
    print(f"\n{'─' * 80}")
    print("\n2. SEMANTIC SEARCH ONLY:")

    context_semantic = agent.retrieve_context(
        query,
        use_hybrid_search=False,
        top_k=10
    )

    print(f"\n   Найдено страниц: {len(context_semantic.confirmed_pages)}")
    print(f"\n   Топ-5:")
    for i, page in enumerate(context_semantic.confirmed_pages[:5], 1):
        print(f"   {i}. [{page.page_id}] {page.title}")
        print(f"      Score: {page.relevance_score:.4f}")

    # 3. Анализ результатов
    print(f"\n{'═' * 80}")
    print("АНАЛИЗ:")

    # Ищем целевую страницу
    target_id = "42672659"
    target_title = "[КК_ВК] Заявка на выпуск карты и открытие счета"

    # Позиция в Hybrid
    hybrid_pos = None
    for i, page in enumerate(context_hybrid.confirmed_pages, 1):
        if page.page_id == target_id:
            hybrid_pos = i
            break

    # Позиция в Semantic
    semantic_pos = None
    for i, page in enumerate(context_semantic.confirmed_pages, 1):
        if page.page_id == target_id:
            semantic_pos = i
            break

    print(f"\nЦелевая страница: {target_id}")
    print(f"Название: {target_title}")
    print(f"\nПозиция в Hybrid Search: {hybrid_pos or 'Не найдена'}")
    print(f"Позиция в Semantic Search: {semantic_pos or 'Не найдена'}")

    if hybrid_pos and semantic_pos:
        improvement = semantic_pos - hybrid_pos
        if improvement > 0:
            print(f"\n✅ Hybrid Search ЛУЧШЕ на {improvement} позиций!")
        elif improvement < 0:
            print(f"\n⚠️  Semantic Search лучше на {abs(improvement)} позиций")
        else:
            print(f"\n➡️  Результаты одинаковые")
    elif hybrid_pos:
        print(f"\n✅ Hybrid Search нашёл, Semantic НЕ нашёл!")
    elif semantic_pos:
        print(f"\n⚠️  Semantic нашёл, Hybrid НЕ нашёл!")
    else:
        print(f"\n❌ Оба метода НЕ нашли целевую страницу")


def test_different_weights():
    """Тест разных весов BM25/Semantic."""

    print("\n" + "=" * 80)
    print("ТЕСТ: Разные веса BM25 / Semantic")
    print("=" * 80)

    agent = ContextRetrievalAgent("CC")
    query = "Заявка на выпуск карты"

    # Разные комбинации весов
    weight_combos = [
        (1.0, 0.0, "Только BM25"),
        (0.7, 0.3, "70% BM25, 30% Semantic"),
        (0.5, 0.5, "50% BM25, 50% Semantic"),
        (0.3, 0.7, "30% BM25, 70% Semantic"),
        (0.0, 1.0, "Только Semantic"),
    ]

    target_id = "42672659"

    results = []

    for bm25_w, sem_w, label in weight_combos:
        print(f"\n{label}:")

        context = agent.retrieve_context(
            query,
            bm25_weight=bm25_w,
            semantic_weight=sem_w,
            top_k=10
        )

        # Ищем позицию целевой страницы
        position = None
        for i, page in enumerate(context.confirmed_pages, 1):
            if page.page_id == target_id:
                position = i
                break

        results.append((label, position))

        # Показываем топ-3
        print(f"  Топ-3:")
        for i, page in enumerate(context.confirmed_pages[:3], 1):
            marker = " ← ЦЕЛЕВАЯ" if page.page_id == target_id else ""
            print(f"    {i}. {page.title[:60]}{marker}")

        if position:
            print(f"  → Целевая страница на позиции: {position}")
        else:
            print(f"  → Целевая страница НЕ НАЙДЕНА в топ-10")

    # Итоги
    print(f"\n{'═' * 80}")
    print("ИТОГИ:")
    print(f"\n{'Конфигурация':<40} {'Позиция':<10}")
    print("─" * 50)

    for label, position in results:
        pos_str = str(position) if position else "НЕ НАЙДЕНА"
        print(f"{label:<40} {pos_str:<10}")

    # Определяем лучшую конфигурацию
    valid_results = [(label, pos) for label, pos in results if pos is not None]
    if valid_results:
        best = min(valid_results, key=lambda x: x[1])
        print(f"\n✅ Лучший результат: {best[0]} (позиция {best[1]})")


def test_query_expansion_with_hybrid():
    """Тест Query Expansion + Hybrid Search."""

    print("\n" + "=" * 80)
    print("ТЕСТ: Query Expansion + Hybrid Search")
    print("=" * 80)

    agent = ContextRetrievalAgent("CC")

    # Бизнес-требование, которое будет разбито на 11 запросов
    business_req = "Добавить поле 'Комментарий' в заявку на выпуск корпоративной карты"

    print(f"\nБизнес-требование: '{business_req}'")
    print(f"\nLLM сгенерирует специализированные запросы по типам требований...")

    context = agent.retrieve_context(
        business_req,
        use_query_expansion=True,  # LLM создаст 11 запросов
        use_hybrid_search=True,  # Каждый запрос использует Hybrid Search
        top_k=50
    )

    print(f"\n✅ Найдено {len(context.confirmed_pages)} уникальных страниц")
    print(f"\nГруппировка по типам:")

    for req_type, pages in sorted(context.pages_by_type.items()):
        print(f"  - {req_type}: {len(pages)} страниц")

    # Проверяем наличие модели данных заявки
    if "dataModel" in context.pages_by_type:
        print(f"\n📄 Модели данных (топ-5):")
        for i, page in enumerate(context.pages_by_type["dataModel"][:5], 1):
            print(f"  {i}. {page.title}")


if __name__ == "__main__":
    try:
        # Проверяем наличие BM25 библиотек
        from rank_bm25 import BM25Okapi
        import pymorphy2

        print("\n✅ BM25 библиотеки установлены")

        # Запускаем тесты
        test_hybrid_vs_semantic()
        test_different_weights()
        test_query_expansion_with_hybrid()

        print(f"\n{'═' * 80}")
        print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        print("=" * 80 + "\n")

    except ImportError as e:
        print("\n❌ ОШИБКА: BM25 библиотеки не установлены")
        print("\nУстановите зависимости:")
        print("  pip install -r requirements_hybrid.txt")
        print("\nили")
        print("  pip install rank-bm25 pymorphy2 pymorphy2-dicts-ru\n")
        sys.exit(1)