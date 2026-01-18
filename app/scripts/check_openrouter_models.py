# app/scripts/check_openrouter_models.py

"""
Скрипт для проверки доступных моделей на OpenRouter.
Использует ваш OPENROUTER_API_KEY из переменных окружения.
"""

import os
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


def get_openrouter_models(
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1"
) -> List[Dict]:
    """
    Получает список доступных моделей с OpenRouter.

    Args:
        api_key: API ключ OpenRouter (если None - берется из env)
        base_url: Базовый URL OpenRouter API

    Returns:
        Список словарей с информацией о моделях
    """
    # Получаем API ключ
    if api_key is None:
        api_key = os.getenv('OPENROUTER_API_KEY')

    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY не найден! "
            "Установите переменную окружения или передайте ключ напрямую."
        )

    # Формируем запрос
    url = f"{base_url}/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",  # Опционально, для статистики
        "X-Title": "Requirements Analyzer"  # Опционально, для статистики
    }

    print(f"🔍 Запрашиваю список моделей с {url}...")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        models = data.get('data', [])

        print(f"✅ Получено {len(models)} моделей")
        return models

    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP ошибка: {e}")
        print(f"Response: {e.response.text if e.response else 'No response'}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        raise


def filter_models(
        models: List[Dict],
        search: Optional[str] = None,
        min_context: Optional[int] = None,
        max_price: Optional[float] = None
) -> List[Dict]:
    """
    Фильтрует модели по критериям.

    Args:
        models: Список моделей
        search: Поисковая строка (в названии модели)
        min_context: Минимальный размер контекста
        max_price: Максимальная цена за 1M токенов

    Returns:
        Отфильтрованный список моделей
    """
    filtered = models

    if search:
        search_lower = search.lower()
        filtered = [m for m in filtered if search_lower in m.get('id', '').lower()]

    if min_context:
        filtered = [m for m in filtered if m.get('context_length', 0) >= min_context]

    if max_price:
        filtered = [
            m for m in filtered
            if float(m.get('pricing', {}).get('prompt', 999)) <= max_price
        ]

    return filtered


def print_models_table(models: List[Dict], limit: int = 20):
    """
    Выводит таблицу с информацией о моделях.

    Args:
        models: Список моделей
        limit: Максимальное количество моделей для вывода
    """
    if not models:
        print("❌ Модели не найдены")
        return

    print(f"\n{'=' * 120}")
    print(f"{'ID модели':<50} {'Контекст':<12} {'Цена $/1M tok':<20} {'Доступна'}")
    print(f"{'=' * 120}")

    for i, model in enumerate(models[:limit], 1):
        model_id = model.get('id', 'Unknown')
        context = model.get('context_length', 0)
        pricing = model.get('pricing', {})
        prompt_price = float(pricing.get('prompt', 0)) * 1_000_000  # Конвертируем в $/1M
        completion_price = float(pricing.get('completion', 0)) * 1_000_000

        # Проверяем доступность (некоторые модели могут быть недоступны)
        available = "✅" if not model.get('disabled', False) else "❌"

        print(f"{model_id:<50} {context:<12,} ${prompt_price:.2f}/${completion_price:.2f}      {available}")

    if len(models) > limit:
        print(f"\n... и ещё {len(models) - limit} моделей")

    print(f"{'=' * 120}\n")


def check_specific_model(models: List[Dict], model_id: str) -> Optional[Dict]:
    """
    Проверяет доступность конкретной модели.

    Args:
        models: Список всех моделей
        model_id: ID модели для проверки

    Returns:
        Информация о модели или None
    """
    for model in models:
        if model.get('id') == model_id:
            return model
    return None


def main():
    """Основная функция скрипта"""
    print("=" * 120)
    print("🤖 OpenRouter Models Checker")
    print("=" * 120)

    # Проверяем API ключ
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("\n❌ OPENROUTER_API_KEY не найден в переменных окружения!")
        print("\nДобавьте в .env:")
        print("OPENROUTER_API_KEY=your_key_here")
        return

    print(f"✅ API ключ найден: {api_key[:20]}...")

    # Получаем список моделей
    try:
        all_models = get_openrouter_models()
    except Exception as e:
        print(f"\n❌ Не удалось получить список моделей: {e}")
        return

    # Показываем топ-20 моделей
    print("\n📊 ТОП-20 ДОСТУПНЫХ МОДЕЛЕЙ:")
    print_models_table(all_models, limit=20)

    # Проверяем вашу модель
    your_model = os.getenv('AGENT_MODEL', 'qwen/qwen2.5-32b-instruct')
    print(f"\n🔍 Проверяем вашу модель: {your_model}")

    model_info = check_specific_model(all_models, your_model)

    if model_info:
        print(f"✅ Модель НАЙДЕНА и доступна!")
        print(f"\nДетали:")
        print(f"  ID: {model_info.get('id')}")
        print(f"  Название: {model_info.get('name', 'N/A')}")
        print(f"  Контекст: {model_info.get('context_length', 0):,} токенов")
        pricing = model_info.get('pricing', {})
        print(f"  Цена prompt: ${float(pricing.get('prompt', 0)) * 1_000_000:.4f}/1M токенов")
        print(f"  Цена completion: ${float(pricing.get('completion', 0)) * 1_000_000:.4f}/1M токенов")
        print(f"  Статус: {'✅ Активна' if not model_info.get('disabled') else '❌ Отключена'}")
    else:
        print(f"❌ Модель НЕ НАЙДЕНА!")
        print(f"\n💡 Возможные причины:")
        print(f"  1. Неправильное написание ID модели")
        print(f"  2. Модель недоступна на OpenRouter")
        print(f"  3. Модель требует специального доступа")

        # Показываем похожие модели
        print(f"\n🔍 Похожие модели с 'qwen':")
        qwen_models = filter_models(all_models, search="qwen")
        print_models_table(qwen_models, limit=50)

    # Рекомендации по моделям для агента
    print("\n💡 РЕКОМЕНДУЕМЫЕ МОДЕЛИ ДЛЯ АГЕНТА:")
    print("\n1. Лучшее качество (дорого):")
    good_models = filter_models(all_models, search="gpt-4")
    print_models_table(good_models, limit=5)

    print("\n2. Баланс цена/качество:")
    balanced = [
        check_specific_model(all_models, "anthropic/claude-3.5-sonnet"),
        check_specific_model(all_models, "google/gemini-pro-1.5"),
        check_specific_model(all_models, "openai/gpt-3.5-turbo"),
    ]
    balanced = [m for m in balanced if m]
    print_models_table(balanced, limit=5)

    print("\n3. Бюджетные (дешево):")
    cheap = filter_models(all_models, max_price=0.5)  # До $0.5 за 1M токенов
    print_models_table(cheap, limit=10)

    print("\n" + "=" * 120)
    print("✅ Проверка завершена!")
    print("\nДля использования модели добавьте в .env:")
    print(f"AGENT_MODEL=<model_id>")
    print(f"OPENROUTER_API_KEY={api_key[:20]}...")
    print(f"OPENROUTER_BASE_URL=https://openrouter.ai/api/v1")
    print("=" * 120)


if __name__ == "__main__":
    main()