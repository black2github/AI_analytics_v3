# app/routes/logging_control.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
from app.utils.logging_utils import set_log_level, get_current_log_level, log_sample_messages

router = APIRouter()
logger = logging.getLogger(__name__)


class LogLevelRequest(BaseModel):
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL


@router.get("/log_level", tags=["Управление логированием"])
async def get_log_level():
    """Получает текущий уровень логирования"""
    logger.debug("[get_log_level] <-.")
    return {"current_level": get_current_log_level()}


@router.post("/log_level", tags=["Управление логированием"])
async def change_log_level(request: LogLevelRequest):
    """Изменяет уровень логирования"""
    logger.debug("[change_log_level] <- level='%s'", request.level)
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

    if request.level.upper() not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid log level. Must be one of: {valid_levels}"
        )

    try:
        # Сохраняем предыдущий уровень ДО изменения
        previous_level = get_current_log_level()

        # Изменяем уровень
        set_log_level(request.level)

        return {
            "message": f"Log level changed to {request.level.upper()}",
            "previous_level": previous_level,  # Теперь возвращаем реальный предыдущий уровень
            "current_level": request.level.upper()  # Опционально: добавляем текущий уровень для ясности
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/log_test", tags=["Управление логированием"])
async def test_logging():
    """Выводит тестовые сообщения разных уровней"""
    logger.debug("[test_logging] <-.")
    try:
        log_sample_messages()
        return {"message": "Test log messages sent. Check logs for output."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))