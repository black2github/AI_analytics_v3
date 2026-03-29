# tests/test_context_retrieval_agent.py

"""
Тесты и примеры использования Context Retrieval Agent.

Запуск тестов:
    pytest tests/test_context_retrieval_agent.py -v

Запуск примеров:
    python tests/test_context_retrieval_agent.py
"""

import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.context_retrieval_agent import (
    ContextRetrievalAgent,
    ContextMap,
    PageContext,
    create_context_agent
)


# ============================================================================
# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ
# ============================================================================

def example_basic_usage():
    """Базовый пример использования агента"""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic Usage")
    print("=" * 80)

    # Создаём агента для сервиса "CC" (Корпоративные карты)
    agent = create_context_agent("CC")

    # Извлекаем контекст для бизнес-требования
    business_req = "Добавить поле 'Комментарий' в заявку на выпуск корпоративной карты"
    print(f"Требование = {business_req}")

    context_map = agent.retrieve_context(
        business_requirements=business_req,
        top_k=20
    )

    # Выводим сводку
    print(agent.format_context_summary(context_map))

    print("\nTop 5 most relevant pages:")
    for i, page in enumerate(context_map.potentially_affected_pages[:5], 1):
        conflict_mark = " [CONFLICT]" if page.has_pending_changes else ""
        print(f"{i}. [{page.page_id}] {page.title}{conflict_mark}")
        print(f"   Type: {page.requirement_type}, Score: {page.relevance_score:.4f}, "
              f"MV: T={page.mv_title_rank or '-'} S={page.mv_summary_rank or '-'} C={page.mv_content_rank or '-'}")


def example_filter_by_type():
    """Пример с фильтрацией по типам требований"""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Filter by Requirement Types")
    print("=" * 80)

    agent = create_context_agent("CC")

    # Ищем только страницы с моделями данных и функциями
    context_map = agent.retrieve_context(
        business_requirements="Добавление поля статус блокировки карты",
        requirement_types=["dataModel", "function"],
        top_k=10
    )
    print(f"Требования = 'Добавление поля статус блокировки карты' с поиском по dataModel и function")

    print(f"\nFound {context_map.total_confirmed_pages} pages with requirements")
    print(f"Pages with data models: {len(context_map.pages_by_type.get('dataModel', []))}")
    print(f"Pages with functions: {len(context_map.pages_by_type.get('function', []))}")

    # Работа с конкретным типом
    data_model_pages = agent.get_pages_by_type(context_map, "dataModel")
    print(f"\nData Model pages:")
    for page in data_model_pages[:3]:
        print(f"  - [{page.page_id}] {page.title} (score={page.relevance_score:.4f})")


def example_filter_by_system():
    """Пример с фильтрацией по смежной системе"""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Filter by Target System")
    print("=" * 80)

    agent = create_context_agent("CC")

    # Ищем только интеграции с АБС Ф1
    context_map = agent.retrieve_context(
        business_requirements="Получение списка карт клиента",
        requirement_types=["integration"],
        target_system="ABS_F1",
        top_k=10
    )
    print("Требования = Получение списка карт клиента target_system=ABS_F1 requirement_types=integration")

    print(f"\nFound {context_map.total_confirmed_pages} integration pages with ABS_F1")
    print(f"Related systems: {context_map.related_systems}")

    # Получаем интеграции для конкретной системы
    abs_integrations = agent.get_integration_pages_by_system(context_map, "ABS_F1")
    print(f"\nABS_F1 integration pages ({len(abs_integrations)}):")
    for page in abs_integrations[:5]:
        print(f"  - [{page.page_id}] {page.title} (score={page.relevance_score:.4f})")


def example_detect_conflicts():
    """Пример обнаружения конфликтов"""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Detect Conflicts")
    print("=" * 80)

    agent = create_context_agent("CC")

    context_map = agent.retrieve_context(
        business_requirements="Изменение процесса создания заявки",
        requirement_types=["process", "function"],
        top_k=15
    )

    print(f"\nTotal pages: {context_map.total_confirmed_pages}")
    print(f"Potentially affected: {len(context_map.potentially_affected_pages)}")
    print(f"With conflicts (pending changes): {context_map.total_pages_with_conflicts}")

    if context_map.pages_with_conflicts:
        print(f"\n  CONFLICTS DETECTED:")
        for page in context_map.pages_with_conflicts:
            print(f"  - [{page.page_id}] {page.title}")
            print(f"    Type: {page.requirement_type}, Score: {page.relevance_score:.4f}")
            if page.pending_content:
                preview = page.pending_content[:100]
                print(f"    Pending: {preview}...")


def example_work_with_pending():
    """Пример работы с незавершёнными изменениями"""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Work with Pending Changes")
    print("=" * 80)

    agent = create_context_agent("CC")

    context_map = agent.retrieve_context(
        business_requirements="Статусы корпоративных карт",
        top_k=20
    )

    print(f"\nTotal confirmed pages: {context_map.total_confirmed_pages}")
    print(f"Pages with pending changes: {context_map.total_pages_with_pending}")

    if context_map.pages_with_pending_changes:
        print(f"\n   Pages with pending changes:")
        for page in context_map.pages_with_pending_changes[:5]:
            print(f"\n  [{page.page_id}] {page.title}")
            print(f"  Type: {page.requirement_type}")
            print(f"  Status: {page.status}")

            # Показываем превью незавершённых изменений
            if page.pending_content:
                preview = page.pending_content[:150]
                print(f"  Pending content preview:")
                print(f"    {preview}...")


def example_full_workflow():
    """Полный workflow для Process Architect"""
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Full Workflow for Process Architect")
    print("=" * 80)

    # Бизнес-требование
    business_req = """
    Необходимо добавить возможность блокировки корпоративной карты 
    по инициативе клиента. Должна быть кнопка "Заблокировать" в списке карт,
    после нажатия карта переходит в статус "Заблокирована по инициативе клиента".
    """
    print(f"Требования = {business_req}")

    agent = create_context_agent("CC")

    # Шаг 1: Получаем широкий контекст
    print("\nStep 1: Retrieving broad context...")
    context_map = agent.retrieve_context(
        business_requirements=business_req,
        top_k=30
    )

    print(f"Found {context_map.total_confirmed_pages} relevant pages")

    # Шаг 2: Анализируем смежные системы
    print(f"\nStep 2: Analyzing related systems...")
    print(f"Systems involved: {', '.join(context_map.related_systems)}")

    # Проверяем интеграции с каждой системой
    for system in context_map.related_systems:
        integrations = agent.get_integration_pages_by_system(context_map, system)
        print(f"  - {system}: {len(integrations)} integration pages")

    # Шаг 3: Проверяем конфликты
    print(f"\nStep 3: Checking for conflicts...")
    if context_map.total_pages_with_conflicts > 0:
        print(f"  WARNING: {context_map.total_pages_with_conflicts} pages have pending changes")
        print(f"Review these before creating new requirements!")

        for page in context_map.pages_with_conflicts[:3]:
            print(f"  - [{page.page_id}] {page.title}")
    else:
        print(f"✓ No conflicts detected")

    # Шаг 4: Группируем по типам для декомпозиции
    print(f"\nStep 4: Grouping by requirement types...")
    for req_type, pages in sorted(context_map.pages_by_type.items()):
        if len(pages) > 0:
            print(f"  - {req_type}: {len(pages)} pages")

    # Шаг 5: Формируем структурированное резюме
    print(f"\nStep 5: Context summary for Process Architect:")
    print(agent.format_context_summary(context_map))


def example_understanding_chunking():
    """Пример понимания работы с chunking"""
    print("\n" + "=" * 80)
    print("EXAMPLE 7: Understanding Chunking")
    print("=" * 80)

    agent = create_context_agent("CC")

    context_map = agent.retrieve_context(
        business_requirements="модель данных карты",
        requirement_types=["dataModel"],
        top_k=20
    )

    print(f"\nTotal page contexts returned: {len(context_map.confirmed_pages)}")

    # Группируем по page_id для понимания chunking
    from collections import defaultdict
    pages_grouped = defaultdict(list)

    for page in context_map.confirmed_pages:
        pages_grouped[page.page_id].append(page)

    print(f"Unique pages: {len(pages_grouped)}")

    # Показываем примеры chunking
    print("\nExamples of chunking:")
    for page_id, chunks in list(pages_grouped.items())[:3]:
        print(f"\n  Page ID: {page_id}")
        print(f"  Title: {chunks[0].title}")
        print(f"  Number of chunks returned: {len(chunks)}")

        if len(chunks) > 1:
            print(f"  This page was chunked in ChromaDB")
            for i, chunk in enumerate(chunks):
                is_full = chunk.metadata.get('is_full_page', False)
                chunk_idx = chunk.metadata.get('chunk_index', 'N/A')
                print(f"    Chunk {i + 1}: index={chunk_idx}, is_full_page={is_full}")
        else:
            is_full = chunks[0].metadata.get('is_full_page', True)
            print(f"  This page is stored as: {'full page' if is_full else 'single chunk'}")


# ============================================================================
# UNIT TESTS
# ============================================================================

def test_agent_initialization():
    """Тест инициализации агента"""
    agent = ContextRetrievalAgent("CC")
    assert agent.service_code == "CC"
    assert agent.vectorstore is not None
    print("✓ Agent initialization test passed")


def test_context_map_creation():
    """Тест создания карты контекста"""
    agent = ContextRetrievalAgent("CC")
    context_map = agent.retrieve_context("тестовый запрос", top_k=5)

    assert isinstance(context_map, ContextMap)
    assert context_map.service_code == "CC"
    assert isinstance(context_map.confirmed_pages, list)
    assert isinstance(context_map.related_systems, list)
    print("✓ Context map creation test passed")


def test_filter_by_type():
    """Тест фильтрации по типу"""
    agent = ContextRetrievalAgent("CC")
    context_map = agent.retrieve_context(
        "интеграция",
        requirement_types=["integration"],
        top_k=5
    )

    # Все результаты должны быть интеграциями
    for page in context_map.confirmed_pages:
        assert page.requirement_type == "integration" or page.requirement_type is None

    print("✓ Filter by type test passed")


def test_factory_function():
    """Тест фабричной функции"""
    agent = create_context_agent("SBP")
    assert isinstance(agent, ContextRetrievalAgent)
    assert agent.service_code == "SBP"
    print("✓ Factory function test passed")


def test_page_context_structure():
    """Тест структуры PageContext"""
    agent = ContextRetrievalAgent("CC")
    context_map = agent.retrieve_context("карта", top_k=1)

    if context_map.confirmed_pages:
        page = context_map.confirmed_pages[0]

        # Проверяем обязательные поля
        assert page.page_id is not None
        assert page.title is not None
        assert page.source in ["chromadb", "confluence"]
        assert page.status in ["confirmed", "pending", "modified"]
        assert isinstance(page.has_pending_changes, bool)

        print("✓ PageContext structure test passed")
    else:
        print("!  PageContext structure test skipped (no pages found)")


def test_deduplication():
    """Тест дедупликации по page_id при chunking"""
    agent = ContextRetrievalAgent("CC")
    context_map = agent.retrieve_context("модель данных", top_k=20)

    # Собираем уникальные page_id из pending_changes
    pending_page_ids = {page.page_id for page in context_map.pages_with_pending_changes}

    # Количество pending должно равняться количеству уникальных page_id
    assert len(context_map.pages_with_pending_changes) == len(pending_page_ids)

    print(f"✓ Deduplication test passed ({len(pending_page_ids)} unique pages with pending)")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Context Retrieval Agent Examples and Tests')
    parser.add_argument('--test', action='store_true', help='Run unit tests')
    parser.add_argument('--examples', action='store_true', help='Run all examples')
    parser.add_argument('--example', type=int, help='Run specific example (1-7)')

    args = parser.parse_args()

    if args.test:
        print("\n" + "=" * 80)
        print("RUNNING UNIT TESTS")
        print("=" * 80)
        test_agent_initialization()
        test_context_map_creation()
        test_filter_by_type()
        test_factory_function()
        test_page_context_structure()
        test_deduplication()
        print("\n✓ All tests passed!\n")

    elif args.example:
        examples = {
            1: example_basic_usage,
            2: example_filter_by_type,
            3: example_filter_by_system,
            4: example_detect_conflicts,
            5: example_work_with_pending,
            6: example_full_workflow,
            7: example_understanding_chunking
        }
        if args.example in examples:
            examples[args.example]()
        else:
            print(f"Example {args.example} not found. Available: 1-7")

    elif args.examples:
        example_basic_usage()
        example_filter_by_type()
        example_filter_by_system()
        example_detect_conflicts()
        example_work_with_pending()
        example_full_workflow()
        example_understanding_chunking()

    else:
        # По умолчанию запускаем базовый пример
        example_basic_usage()
        print("\nFor more examples: python tests/test_context_retrieval_agent.py --examples")
        print("For unit tests: python tests/test_context_retrieval_agent.py --test")