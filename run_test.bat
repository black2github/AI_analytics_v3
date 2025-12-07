@echo off
REM Установка имени лог-файла с датой и временем
set LOGFILE=run_test.log

REM Очистка старого лога (если нужно)
del "%LOGFILE%" >nul 2>&1

REM Активируем виртуальное окружение
call venv\Scripts\activate.bat >> "%LOGFILE%" 2>&1

REM Запуск FastAPI через uvicorn с выводом в лог
REM echo Запуск uvicorn... >> "%LOGFILE%"
REM uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%LOGFILE%" 2>&1

REM # Установка зависимостей для тестирования
REM pip install -r requirements-test.txt

REM # Запуск всех тестов
python run_tests.py >> "%LOGFILE%" 2>&1

REM # Запуск конкретной группы тестов
REM python run_tests.py test_history_cleaner.py
REM python run_tests.py test_rag_pipeline.py

REM # Запуск тестов с покрытием
REM pytest tests/ --cov=app --cov-report=html

REM # Запуск только быстрых тестов
REM pytest tests/ -m "not slow"

REM # Запуск в verbose режиме
REM pytest tests/ -v -s