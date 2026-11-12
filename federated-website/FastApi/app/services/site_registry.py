"""
Site registry - read from deploy/seed/sites.json (plan T1.8).

Kept as a file for now; it moves into Postgres only if sites need editing
from the web app (cold start, FR-15).
"""

import json
from typing import List, Optional

from app.platform_schemas import EnergyType, Site
from app.settings import Settings


def list_sites(settings: Settings, energy_type: Optional[EnergyType] = None) -> List[Site]:
    with open(settings.sites_seed, encoding="utf-8") as f:
        raw = json.load(f)
    sites = [Site(**s) for s in raw["sites"]]
    if energy_type is not None:
        sites = [s for s in sites if s.energy_type == energy_type]
    return sites


def get_site(settings: Settings, site_id: str) -> Optional[Site]:
    return next((s for s in list_sites(settings) if s.id == site_id), None)


def active_site_ids(settings: Settings, energy_type: EnergyType) -> List[str]:
    return [s.id for s in list_sites(settings, energy_type) if s.status == "active"]
