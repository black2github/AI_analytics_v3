# app/routes/services.py

from fastapi import APIRouter, Query
from typing import Optional
from app.service_registry import load_services, get_platform_services

router = APIRouter()


@router.get("/services", tags=["Справочники"])
async def list_services(platform: Optional[bool] = Query(None)):
    """
    Список сервисов. Можно фильтровать по platform=true.
    """
    if platform is True:
        return {"services": get_platform_services()}
    return {"services": load_services()}
