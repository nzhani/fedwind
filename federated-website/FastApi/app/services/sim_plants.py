"""
Many simulated plants for scale and security tests (SITE_NETWORK_PLAN.md M9).

spawn() registers N plants through the same service functions the website uses (an operator of the
organization "Simulated plants (M9)", an admin approval, a kit download with a one-time token) at
approximate locations of real Kazakh wind and solar regions, and writes their kits to a folder.
deploy/dev/spawn_sites.sh then installs each kit with deploy/sim/run_site.sh: every plant runs the
real site kit, only its data source is NASA POWER.

Never on a production server: refused when ENV=production.
"""

import os
import random
import secrets
from pathlib import Path
from typing import List

from app.platform_schemas import SiteRegistration
from app.services import accounts, site_connection, site_registry
from app.services.accounts import AccountError

ORG = "Simulated plants (M9)"
OPERATOR = "sim-ops@arqauquat.test"

# Approximate regions with wind farms or solar parks (lat, lon); a small jitter keeps plants apart
REGIONS = {
    "wind": [("Ereymentau", 51.62, 73.10), ("Zhanatas", 43.57, 69.73), ("Kordai", 43.05, 74.71),
             ("Shokpar", 43.70, 74.95), ("Shelek", 43.60, 78.25), ("Fort-Shevchenko", 44.51, 50.26),
             ("Arkalyk", 50.25, 66.90), ("Astana", 51.10, 71.60), ("Taldykorgan", 45.00, 78.40),
             ("Mangystau", 43.40, 52.20), ("Karaganda", 49.90, 73.10), ("Aktobe", 50.30, 57.20)],
    "solar": [("Burnoye", 42.93, 71.06), ("Kapchagay", 43.88, 77.08), ("Saran", 49.79, 72.84),
              ("Shymkent", 42.30, 69.60), ("Turkistan", 43.30, 68.27), ("Kyzylorda", 44.85, 65.50),
              ("Balkhash", 46.84, 74.98), ("Aral", 46.80, 61.67), ("Taraz", 42.90, 71.37),
              ("Zhezkazgan", 47.78, 67.71), ("Almaty region", 43.40, 77.00), ("Atyrau", 47.10, 51.90)],
}


def _refuse_production() -> None:
    if os.environ.get("ENV", "").lower() == "production":
        raise AccountError(409, "Simulated plants are for test servers only (ENV=production)")


def _operator() -> accounts.User:
    for u in accounts.list_users():
        if u.email == OPERATOR:
            return u
    # Nobody logs in as this operator: its password is random and never shown
    return accounts.create_user(OPERATOR, secrets.token_urlsafe(24), "Simulated plants operator", "operator",
                                org_name=ORG, via_cli=True)


def _admin() -> accounts.User:
    admins = [u for u in accounts.list_users() if u.role == "admin" and u.active]
    if not admins:
        raise AccountError(409, "Create an admin first (python -m app.cli create-admin)")
    return admins[0]


def spawn(count: int, energy: str, out_dir: Path, share_window: bool = True, seed: int = 0) -> List[dict]:
    """Register, approve and issue kits for `count` plants; returns [{site_id, name, kit}]."""
    _refuse_production()
    rnd = random.Random(seed or None)
    operator, admin = _operator(), _admin()
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    existing = sum(1 for s in site_registry.list_my_sites(operator) if s.energy_type.value == energy)
    for i in range(count):
        region, lat, lon = REGIONS[energy][(existing + i) % len(REGIONS[energy])]
        n = existing + i + 1
        equipment = ({"turbine_model": "Generic 2.5 MW", "turbine_count": 20, "hub_height_m": 100,
                      "rated_power_kw": 2500} if energy == "wind"
                     else {"module_type": "Mono PERC", "tilt_deg": 35, "azimuth_deg": 180, "tracking": "fixed"})
        req = SiteRegistration(
            name=f"Sim {energy} {n:02d} {region}", energy_type=energy,
            lat=round(lat + rnd.uniform(-0.05, 0.05), 4), lon=round(lon + rnd.uniform(-0.05, 0.05), 4),
            capacity_kw=50_000 if energy == "wind" else 20_000, equipment=equipment,
            contact="sim-ops@arqauquat.test",
            consents={"train": True, "share_forecast_window": share_window, "public_forecasts": False})
        site = site_registry.register_site(operator, req)
        site_registry.decide(admin, site.id, "approve", None)
        data, name = site_connection.issue_kit(operator, site.id)
        path = out_dir / name
        path.write_bytes(data)
        os.chmod(path, 0o600)                       # the kit holds a one-time token
        made.append({"site_id": site.id, "name": req.name, "kit": str(path)})
    return made


def status() -> List[dict]:
    """The simulated plants with connection and training eligibility."""
    operator = _operator()
    return [{"site_id": s.id, "energy": s.energy_type.value, "status": s.status,
             "connection": s.connection.state if s.connection else None,
             "train_hours": s.connection.train_hours if s.connection else None,
             "can_train": s.can_train, "why_not": s.train_note}
            for s in site_registry.list_my_sites(operator)]


DEV_NODE = "dev-local"


def set_joined(site_id: str, joined: bool) -> dict:
    """Development mode only (no Flower node registration, e.g. the laptop's lab stack): record that a
    Flower client for this plant runs on this computer (deploy/sim/join_training.sh), so it can be
    selected for training runs. With node registration on, the real enrollment does this instead."""
    from app.db import connect
    from app.services import flower_nodes
    from app.services.accounts import audit

    _refuse_production()
    if flower_nodes.enabled():
        raise AccountError(409, "Flower node registration is on: plants join through their certificate kit")
    with connect() as conn:
        row = conn.execute("UPDATE site_credentials SET flower_node_id = %s WHERE site_id = %s AND revoked_at IS NULL"
                           " AND (flower_node_id IS NULL OR flower_node_id = %s) RETURNING site_id",
                           (DEV_NODE if joined else None, site_id, DEV_NODE)).fetchone()
        if row is None:
            raise AccountError(404, f"{site_id}: no enrolled plant (install its kit first)")
        audit(conn, "site.dev_join" if joined else "site.dev_leave", target=site_id)
    return {"site_id": site_id, "joined": joined}
