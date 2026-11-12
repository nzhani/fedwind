"""
Health Check Router - API status and readiness probe.
"""

from fastapi import APIRouter
from datetime import datetime
from app.schemas import HealthResponse
from app.settings import get_settings


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns API status, version, and whether the federation and inference are configured.",
)
async def health_check():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version="2.0.0",
        environment="development",
        timestamp=datetime.utcnow().isoformat() + "Z",
        services={
            # Cheap on purpose (Compose polls it); GET /api/federation does the real check.
            "federation": "configured" if settings.federation_address else "not_connected",
            "inference": "configured" if settings.inference_url_template else "not_connected",
            "runs_dir": "present" if settings.runs_dir.is_dir() else "empty",
        },
    )
