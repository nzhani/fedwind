"""
Sites Router - site registry (plan T1.8).

Endpoints:
  GET /api/sites?energy_type=wind     Sites for an energy type (all if omitted)
"""

from typing import Optional

from fastapi import APIRouter

from app.platform_schemas import EnergyType, SiteListResponse
from app.services.site_registry import list_sites
from app.settings import get_settings

router = APIRouter(prefix="/api")


@router.get("/sites", response_model=SiteListResponse, summary="List sites")
def get_sites(energy_type: Optional[EnergyType] = None):
    return SiteListResponse(sites=list_sites(get_settings(), energy_type))
