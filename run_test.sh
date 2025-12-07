# Установка зависимостей для тестирования
pip install -r requirements-test.txt

# Запуск всех тестов
python run_tests.py

# Запуск конкретной группы тестов
python run_tests.py test_history_cleaner.py
python run_tests.py test_rag_pipeline.py

# Запуск тестов с покрытием
pytest tests/ --cov=app --cov-report=html

# Запуск только быстрых тестов
pytest tests/ -m "not slow"

# Запуск в verbose режиме
pytest tests/ -v -s