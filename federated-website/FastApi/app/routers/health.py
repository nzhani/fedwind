"""
Health Check Router - API status and readiness probe.
"""

from fastapi import APIRouter
from datetime import datetime
from app.schemas import HealthResponse


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns API status, version, and service readiness.",
)
async def health_check():
    return HealthResponse(
        status="ok",
        version="2.0.0",
        environment="development",
        timestamp=datetime.utcnow().isoformat() + "Z",
        services={
            "database": "file-system",
            "model": "ready",
            "flower_server": "standby",
        },
    )
