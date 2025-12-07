@echo off
REM Установка имени лог-файла с датой и временем
set LOGFILE=run_app.log

REM Очистка старого лога (если нужно)
del "%LOGFILE%" >nul 2>&1

REM Активируем виртуальное окружение
call venv\Scripts\activate.bat >> "%LOGFILE%" 2>&1

REM Устанавливаем переменную окружения PYTHONPATH
set PYTHONPATH=app

REM Запуск FastAPI через uvicorn с выводом в лог
echo Запуск uvicorn... >> "%LOGFILE%"
uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%LOGFILE%" 2>&1

REM Завершение и пауза
echo Завершено. Нажмите любую клавишу для выхода... >> "%LOGFILE%"
pause
