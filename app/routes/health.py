# app/routes/health.py
import logging

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)  # Лучше использовать __name__ для именованных логгеров

@router.get("/health")
async def health_check():
    """Health check endpoint для мониторинга"""
    try:
        # Проверяем доступность агента
        from app.routes.agent import get_agent_instance
        agent = get_agent_instance()

        return {
            "status": "healthy",
            "service": "requirements-analysis",
            "agent": "active",
            "agent_tools": len(agent.tools) if agent else 0
        }
    except Exception as e:
        logger.error("Health check failed: %s", str(e))
        return {
            "status": "degraded",
            "error": str(e)
        }


