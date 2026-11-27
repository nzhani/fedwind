"""
Stored plant forecasts (SITE_NETWORK_PLAN.md M7, §8).

  central   every plant that shares its recent window gets a forecast for every horizon with a
            promoted model, made as soon as a newer window or a newer model exists (refresh_due,
            run by the platform jobs loop every few minutes). The website reads the stored one.
  local     plants that don't share a window download the model, forecast at the plant and post only
            the forecast (POST /site-api/forecasts); the website shows it the same way.

Kept 30 days. Lab sites keep their per-request forecasts from their own inference service.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.db import connect
from app.platform_schemas import EnergyType, RegisteredModel
from app.services import model_registry, run_store, site_connection
from app.services.accounts import AccountError
from app.settings import Settings

log = logging.getLogger("fedwind.forecasts")

RETENTION = timedelta(days=30)
DEFAULT_WINDOW_H = 336
VALUE_RANGES = {"wind": (0.0, 40.0), "solar": (0.0, 1400.0)}


def with_power(points: list, energy_type: EnergyType, capacity_kw: float) -> list:
    """Every point gets power_kw and capacity_factor, whatever the energy type."""
    out = []
    for p in points:
        power = p.get("pv_power_kw") if energy_type == EnergyType.SOLAR else p.get("wind_power_kw")
        out.append({**p, "power_kw": power,
                    "capacity_factor": round(power / capacity_kw, 4) if power is not None and capacity_kw else None})
    return out


def _window_hours(settings: Settings, model: RegisteredModel) -> int:
    run = run_store.get_run(settings, model.run_id)
    return int((run.config or {}).get("seq_len", DEFAULT_WINDOW_H)) if run else DEFAULT_WINDOW_H


def compute_central(settings: Settings, site_id: str, energy_type: EnergyType, model: RegisteredModel,
                    inference) -> Tuple[dict, dict]:
    """(inference output with power, the request facts). Raises AccountError (409 no consent, 503 not
    enough data) or the inference client's error."""
    req = site_connection.central_forecast_request(site_id, _window_hours(settings, model))
    out = inference.forecast_window({
        "energy_type": energy_type.value, "horizon": model.horizon,
        "model_path": model.model_path or model_registry.model_path(energy_type.value, model.horizon),
        **{k: req[k] for k in ("end_hour", "values", "lat", "lon", "capacity_kw", "equipment", "measured_at_m")},
    })
    cap = float(req["capacity_kw"])
    out = {**out, "actual": with_power(out.get("actual", []), energy_type, cap),
           "forecast": with_power(out["forecast"], energy_type, cap)}
    return out, req


def save(site_id: str, horizon: int, source: str, model_id: Optional[int], issued_at: str, unit: str,
         capacity_kw: Optional[float], actual: list, forecast: list) -> dict:
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO forecasts (site_id, horizon, source, model_version_id, issued_at, unit, capacity_kw, actual,"
            " forecast) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (site_id, horizon, source, issued_at, model_version_id) DO UPDATE SET"
            " forecast = EXCLUDED.forecast, actual = EXCLUDED.actual, created_at = now() RETURNING *",
            (site_id, horizon, source, model_id, issued_at, unit, capacity_kw, json.dumps(actual),
             json.dumps(forecast))).fetchone()
        conn.execute("DELETE FROM forecasts WHERE site_id = %s AND issued_at < %s",
                     (site_id, datetime.now(timezone.utc) - RETENTION))
    return row


def stored(site_id: str, horizon: int, source: str, model_id: Optional[int] = None,
           issued_at: Optional[datetime] = None) -> Optional[dict]:
    """Newest stored forecast of this source (optionally for one model version and window end)."""
    sql = "SELECT * FROM forecasts WHERE site_id = %s AND horizon = %s AND source = %s"
    args: list = [site_id, horizon, source]
    if model_id is not None:
        sql, args = sql + " AND model_version_id = %s", args + [model_id]
    if issued_at is not None:
        sql, args = sql + " AND issued_at = %s", args + [issued_at]
    with connect() as conn:
        return conn.execute(sql + " ORDER BY issued_at DESC, created_at DESC LIMIT 1", args).fetchone()


def window_end(site_id: str) -> Optional[datetime]:
    with connect() as conn:
        return conn.execute("SELECT max(hour) AS h FROM forecast_inputs WHERE site_id = %s AND ok",
                            (site_id,)).fetchone()["h"]


def refresh_due(settings: Settings, inference) -> List[dict]:
    """Make the central forecasts that are missing: per consenting active plant and promoted model,
    one for the newest shared window. Plants without enough data yet are skipped quietly."""
    models = {(m.energy_type.value, m.horizon): m for m in model_registry.list_models(settings) if m.id is not None}
    if not models:
        return []
    with connect() as conn:
        plants = conn.execute("SELECT id, energy_type, consents FROM sites WHERE kind = 'plant' AND status = 'active'"
                              " AND (consents ->> 'share_forecast_window')::boolean IS TRUE").fetchall()
    made = []
    for p in plants:
        end = window_end(p["id"])
        if end is None:
            continue
        for (energy, horizon), m in models.items():
            if energy != p["energy_type"] or stored(p["id"], horizon, "central", m.id, end):
                continue
            try:
                out, req = compute_central(settings, p["id"], EnergyType(energy), m, inference)
            except AccountError as e:
                log.info("no forecast for %s h%d yet: %s", p["id"], horizon, e.message)
                continue
            except Exception as e:  # inference down: the next pass tries again
                log.warning("forecast for %s h%d failed: %s: %s", p["id"], horizon, type(e).__name__, e)
                continue
            save(p["id"], horizon, "central", m.id, req["end_hour"], out.get("unit", "m/s"),
                 float(req["capacity_kw"]), out.get("actual", []), out["forecast"])
            made.append({"site": p["id"], "horizon": horizon, "version": m.version, "issued_at": req["end_hour"]})
    return made


def save_local(caller, body, settings: Settings) -> dict:
    """A forecast a plant made itself with a downloaded model (local mode)."""
    if caller.status != "active":
        raise AccountError(409, f"The site is {caller.status}; forecasts are paused")
    m = model_registry.get_version(body.model_version_id)
    if m is None or m.energy_type.value != caller.energy_type or m.horizon != body.horizon:
        raise AccountError(422, "Unknown model version for this plant's energy type and horizon")
    if len(body.values) != body.horizon:
        raise AccountError(422, f"Expected {body.horizon} hourly values, got {len(body.values)}")
    try:
        issued = datetime.fromisoformat(body.issued_at.replace("Z", "+00:00"))
    except ValueError:
        raise AccountError(422, "issued_at is not an ISO timestamp")
    issued = (issued if issued.tzinfo else issued.replace(tzinfo=timezone.utc)).replace(minute=0, second=0, microsecond=0)
    now = datetime.now(timezone.utc)
    if not now - timedelta(days=7) <= issued <= now + timedelta(hours=1):
        raise AccountError(422, "issued_at must lie within the last 7 days")
    lo, hi = VALUE_RANGES[caller.energy_type]
    if any(v is None or not lo <= v <= hi for v in body.values):
        raise AccountError(422, f"Values must lie in [{lo:g}, {hi:g}]")
    with connect() as conn:
        cap = conn.execute("SELECT capacity_kw FROM sites WHERE id = %s", (caller.site_id,)).fetchone()["capacity_kw"]
    powers = body.power_kw if body.power_kw is not None else [None] * body.horizon
    if len(powers) != body.horizon:
        raise AccountError(422, "power_kw must have one value per hour")
    solar = caller.energy_type == "solar"
    points = []
    for i, (v, pw) in enumerate(zip(body.values, powers)):
        pw = None if pw is None else min(max(float(pw), 0.0), float(cap or pw))      # DR-03
        ts = (issued + timedelta(hours=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        points.append({"timestamp": ts, "ghi" if solar else "wind_speed": round(float(v), 3),
                       "pv_power_kw" if solar else "wind_power_kw": pw})
    points = with_power(points, EnergyType(caller.energy_type), float(cap or 0))
    row = save(caller.site_id, body.horizon, "local", m.id, issued.isoformat(), "W/m2" if solar else "m/s",
               cap, [], points)
    return {"stored": len(points), "issued_at": issued.isoformat(), "model_version": m.version, "id": row["id"]}
