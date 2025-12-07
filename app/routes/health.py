# app/routes/health.py
import logging

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)  # Лучше использовать __name__ для именованных логгеров

@router.get("/health")
def health_check():
    logger.info("[test_logging] <-.")
    return {"status": "ok"}
