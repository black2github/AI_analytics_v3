@echo off
set LOGFILE=run_app.log
del "%LOGFILE%" >nul 2>&1

set PYTHONPATH=.

echo Запуск uvicorn... >> "%LOGFILE%"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%LOGFILE%" 2>&1

echo Завершено. >> "%LOGFILE%"
pause

