"""
Health of the central server for the admin Health page (SITE_NETWORK_PLAN.md M8).
Every check returns {name, status: ok | warn | error, detail}; nothing here changes state.
Background loops call beat() each pass, so a stopped loop shows up.
"""

import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List

_beats: Dict[str, float] = {}
LOOP_LIMITS_S = {"platform jobs": 900, "site maintenance": 2 * 3600, "scheduler": 900, "notifications": 300}


def beat(name: str) -> None:
    _beats[name] = time.time()


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _age(dt) -> str:
    s = (datetime.now(timezone.utc) - dt).total_seconds()
    return f"{s / 60:.0f} min" if s < 5400 else f"{s / 3600:.1f} h" if s < 172800 else f"{s / 86400:.0f} days"


def report(settings) -> dict:
    checks: List[dict] = []
    now = datetime.now(timezone.utc)

    # Database and migrations
    try:
        from app.db import connect

        with connect() as conn:
            v = conn.execute("SELECT max(version) AS v FROM schema_migrations").fetchone()["v"]
            plants = conn.execute(
                "SELECT s.id, s.consents, c.last_seen_at, c.agent_version, c.cert_not_after FROM sites s"
                " LEFT JOIN site_credentials c ON c.site_id = s.id AND c.revoked_at IS NULL"
                " WHERE s.kind = 'plant' AND s.status = 'active'").fetchall()
            newest = {r["site_id"]: r["t"] for r in conn.execute(
                "SELECT site_id, max(created_at) AS t FROM forecasts GROUP BY site_id").fetchall()}
            promoted = conn.execute("SELECT energy_type, horizon, version, promoted_at FROM model_versions"
                                    " WHERE status = 'promoted' ORDER BY energy_type, horizon").fetchall()
        checks.append(_check("Database", "ok", f"migrations up to {v}"))
    except Exception as e:
        checks.append(_check("Database", "error", f"{type(e).__name__}: {e}"))
        plants, newest, promoted = [], {}, []

    # Federation and inference
    try:
        from app.services.federation_client import get_federation

        fed = get_federation().status()
        checks.append(_check("Federation (SuperLink)", "ok" if fed.connected else "error",
                             f"{fed.detail}" + (f"; {fed.connected_nodes} nodes online" if fed.connected_nodes is not None else "")))
    except Exception as e:
        checks.append(_check("Federation (SuperLink)", "error", str(e)))
    url = os.environ.get("INFERENCE_CENTRAL_URL", "")
    if url:
        try:
            import requests

            r = requests.get(url.rstrip("/") + "/health", timeout=3)
            checks.append(_check("Central inference", "ok" if r.ok else "error", f"HTTP {r.status_code}"))
        except Exception as e:
            checks.append(_check("Central inference", "error", f"{type(e).__name__}"))

    # Models and forecasts
    if promoted:
        checks.append(_check("Promoted models", "ok", ", ".join(
            f"{p['energy_type']} {p['horizon']} h v{p['version']} ({_age(p['promoted_at'])} ago)" for p in promoted)))
    else:
        checks.append(_check("Promoted models", "warn", "none: plants get no forecasts until a run is promoted"))
    sharing = [p for p in plants if (p["consents"] or {}).get("share_forecast_window")]
    stale = [p["id"] for p in sharing if p["id"] not in newest or now - newest[p["id"]] > timedelta(hours=3)]
    checks.append(_check("Stored forecasts", "ok" if not stale else "warn",
                         f"{len(sharing) - len(stale)} of {len(sharing)} sharing plants forecast in the last 3 h"
                         + (f"; behind: {', '.join(stale[:5])}" if stale else "")))

    # Plants: online, certificates, kit versions
    from app.services.site_connection import kit_update

    online = sum(1 for p in plants if p["last_seen_at"] and now - p["last_seen_at"] < timedelta(minutes=10))
    checks.append(_check("Plants online", "ok" if online == len(plants) else "warn", f"{online} of {len(plants)} active plants"))
    expiring = [p["id"] for p in plants if p["cert_not_after"] and p["cert_not_after"] - now < timedelta(days=20)]
    checks.append(_check("Plant certificates", "ok" if not expiring else "warn",
                         "none expire within 20 days" if not expiring else f"expiring soon: {', '.join(expiring[:5])} "
                         "(agents renew 30 days ahead; these didn't)"))
    old = [p["id"] for p in plants if kit_update(p["agent_version"])]
    checks.append(_check("Site kit versions", "ok" if not old else "warn",
                         "all current" if not old else f"{len(old)} plant(s) on an older kit"))

    # Site CA and CRL
    try:
        from app.services import site_ca

        crl = site_ca.read_crl()
        if crl is None:
            checks.append(_check("Site CA", "warn", "no CA yet"))
        else:
            nxt = crl.next_update_utc
            checks.append(_check("Site CA revocation list", "ok" if nxt - now > timedelta(days=1) else "error",
                                 f"{len(list(crl))} revoked; valid until {nxt:%Y-%m-%d %H:%M} UTC"))
    except Exception as e:
        checks.append(_check("Site CA", "error", str(e)))

    # Backups (deploy/central/backup.sh writes this file)
    status_file = settings.data_dir / "backups-status.json"
    try:
        b = json.loads(status_file.read_text())
        at = datetime.fromisoformat(b["finished_at"].replace("Z", "+00:00"))
        ok = now - at < timedelta(hours=36)
        checks.append(_check("Backups", "ok" if ok else "error",
                             f"last {_age(at)} ago, {b.get('size_bytes', 0) / 1e6:.0f} MB"
                             + ("" if b.get("encrypted") else ", not encrypted")))
    except (OSError, ValueError, KeyError):
        checks.append(_check("Backups", "warn", "no backup recorded (deploy/central/backup.sh)"))

    # Background loops and disk
    for name, limit in LOOP_LIMITS_S.items():
        if name in _beats:
            age = time.time() - _beats[name]
            checks.append(_check(f"Loop: {name}", "ok" if age < limit else "error", f"last pass {age / 60:.0f} min ago"))
    usage = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else "/")
    free = usage.free / 1e9
    checks.append(_check("Disk (data folder)", "ok" if free > 10 else "warn" if free > 3 else "error",
                         f"{free:.0f} GB free of {usage.total / 1e9:.0f} GB"))

    worst = "error" if any(c["status"] == "error" for c in checks) else "warn" if any(
        c["status"] == "warn" for c in checks) else "ok"
    return {"status": worst, "checked_at": now.isoformat(), "checks": checks}
