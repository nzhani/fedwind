"""
Forecast Router - per-site forecast from the current global model (plan FR-22, FR-26).

Endpoints:
  GET /api/forecast?energy_type=wind&site=almaty&horizon=72[&as_of=ISO]

Wind points carry wind_speed (m/s) and wind_power_kw; solar points carry ghi and
clear_sky_ghi (W/m2) and pv_power_kw.

Lab sites: the site's own inference service (power of a reference 2 MW turbine / 1 MW PV).
Plants: central forecasting from the window the plant shared, power from its registered capacity
and equipment; private unless the plant consented to public forecasts.
Every response names the newest promoted model that made it (model card).

Errors: 422 unknown site / horizon not in {1, 72, 432}; 409 plant without central forecasting
consent; 503 no promoted model, not enough plant data yet, or inference not connected.
The API never computes or fills in a forecast itself.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import current_session
from app.db import DatabaseUnavailable
from app.platform_schemas import HORIZONS, EnergyType, ForecastModelRef, ForecastResponse, RegisteredModel
from app.services import run_store, site_connection
from app.services.accounts import AccountError, Session
from app.services.inference_client import InferenceClient, InferenceUnavailable, get_inference
from app.services.model_registry import current_model, model_path
from app.services.site_registry import get_site
from app.settings import get_settings

router = APIRouter(prefix="/api")


# Lab sites have no registered capacity: power is shown for a reference unit, labelled as such
REFERENCE_CAPACITY_KW = {EnergyType.WIND: 2000.0, EnergyType.SOLAR: 1000.0}
DEFAULT_WINDOW_H = 336


def _model_ref(model: RegisteredModel, settings) -> ForecastModelRef:
    """The model card: which promoted global model made the forecast, trained on what."""
    run = run_store.get_run(settings, model.run_id)
    real = (model.metrics or {}).get("real") or {}
    return ForecastModelRef(
        run_id=model.run_id,
        energy_type=model.energy_type,
        horizon=model.horizon,
        promoted_at=model.promoted_at,
        promoted_by=model.promoted_by,
        sites=model.sites or (run.sites if run else []),
        rounds_completed=model.rounds_completed or (run.current_round if run else None),
        strategy=model.strategy or (run.strategy if run else None),
        skill_vs_persistence=real.get("skill_vs_persistence"),
        skill_reference=(model.metrics or {}).get("reference"),
        data_percent=_data_percent(run),
    )


def _data_percent(run) -> Optional[float]:
    """Share of the training data the run used (small demo runs use 5-10 %)."""
    try:
        v = (run.config or {}).get("data_percent") if run else None
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _with_power(points: list, energy_type: EnergyType, capacity_kw: float) -> list:
    """Every point gets power_kw and capacity_factor, whatever the energy type."""
    out = []
    for p in points:
        power = p.get("pv_power_kw") if energy_type == EnergyType.SOLAR else p.get("wind_power_kw")
        out.append({**p, "power_kw": power,
                    "capacity_factor": round(power / capacity_kw, 4) if power is not None and capacity_kw else None})
    return out


def _check_plant_access(site_id: str, session: Optional[Session]) -> None:
    org_id, public = site_connection.plant_visibility(site_id)
    if public:
        return
    user = session.user if session else None
    if user is None or not (user.role == "admin" or (user.org_id is not None and user.org_id == org_id)):
        # Same answer as an unknown site: private plants don't reveal themselves
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown site '{site_id}'")


@router.get("/forecast", response_model=ForecastResponse, summary="Forecast for one site")
def get_forecast(
    request: Request,
    site: str,
    horizon: int,
    energy_type: EnergyType = EnergyType.WIND,
    as_of: Optional[str] = None,
    inference: InferenceClient = Depends(get_inference),
):
    settings = get_settings()
    found = get_site(settings, site)
    if found is None or found.energy_type != energy_type or found.status != "active":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown {energy_type.value} site '{site}'")
    if horizon not in HORIZONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"horizon must be one of {list(HORIZONS)}, got {horizon}"
        )
    if as_of is not None:
        try:
            datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"as_of is not an ISO timestamp: '{as_of}'")

    plant = found.kind == "plant"
    if plant:
        _check_plant_access(site, current_session(request))

    # Always the newest promoted global model for this energy type and horizon
    model = current_model(settings, energy_type.value, horizon)
    if model is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"No model is registered for {energy_type.value} horizon {horizon}. Promote a finished run first.",
        )
    ref = _model_ref(model, settings)

    try:
        if plant:
            run = run_store.get_run(settings, model.run_id)
            hours = int((run.config or {}).get("seq_len", DEFAULT_WINDOW_H)) if run else DEFAULT_WINDOW_H
            req = site_connection.central_forecast_request(site, hours)
            out = inference.forecast_window({
                "energy_type": energy_type.value, "horizon": horizon,
                "model_path": model_path(energy_type.value, horizon),
                **{k: req[k] for k in ("end_hour", "values", "lat", "lon", "capacity_kw", "equipment", "measured_at_m")},
            })
            capacity, basis, source, simulated = float(req["capacity_kw"]), "plant", "central", req["simulated"]
        else:
            out = inference.forecast(site, horizon, as_of, model_path(energy_type.value, horizon))
            capacity, basis, source, simulated = REFERENCE_CAPACITY_KW[energy_type], "reference", "site_inference", False
    except AccountError as e:
        raise HTTPException(e.status, e.message)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except InferenceUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    return ForecastResponse(
        energy_type=energy_type,
        site=site,
        horizon=horizon,
        unit=out.get("unit", "m/s"),
        as_of=out["as_of"],
        model=ref,
        actual=_with_power(out.get("actual", []), energy_type, capacity),
        forecast=_with_power(out["forecast"], energy_type, capacity),
        capacity_kw=capacity,
        power_basis=basis,
        source=source,
        simulated=simulated,
    )
