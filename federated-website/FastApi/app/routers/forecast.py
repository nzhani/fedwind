"""
Forecast Router - per-site forecast from the current global model (plan FR-22, FR-26).

Endpoints:
  GET /api/forecast?energy_type=wind&site=almaty&horizon=72[&as_of=ISO]

Wind points carry wind_speed (m/s) and wind_power_kw; solar points carry ghi and
clear_sky_ghi (W/m2) and pv_power_kw.

Lab sites: the site's own inference service (power of a reference 2 MW turbine / 1 MW PV).
Plants: the stored forecast (app/services/forecast_store.py): made centrally from the window the
plant shared, power from its registered capacity and equipment, or made at the plant itself (local
mode). A central one missing for the newest window and model is made now and stored. Private unless
the plant consented to public forecasts.
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
from app.services import forecast_store, forecast_summary, run_store, site_connection
from app.services.accounts import AccountError, Session
from app.services.inference_client import InferenceClient, InferenceUnavailable, get_inference
from app.services.model_registry import current_model, model_path
from app.services.site_registry import get_site
from app.settings import get_settings

router = APIRouter(prefix="/api")


# Lab sites have no registered capacity: power is shown for a reference unit, labelled as such
REFERENCE_CAPACITY_KW = {EnergyType.WIND: 2000.0, EnergyType.SOLAR: 1000.0}


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
        data_percent=model.data_percent if model.data_percent is not None else _data_percent(run),
        version=model.version,
    )


def _data_percent(run) -> Optional[float]:
    """Share of the training data the run used (small demo runs use 5-10 %)."""
    try:
        v = (run.config or {}).get("data_percent") if run else None
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


_with_power = forecast_store.with_power


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

    stored_at = None
    try:
        if plant:
            out, capacity, source, simulated, stored_at = _plant_forecast(settings, site, energy_type, model, inference)
            basis = "plant"
        else:
            out = inference.forecast(site, horizon, as_of, model.model_path or model_path(energy_type.value, horizon))
            capacity, basis, source, simulated = REFERENCE_CAPACITY_KW[energy_type], "reference", "site_inference", False
            out = {**out, "actual": _with_power(out.get("actual", []), energy_type, capacity),
                   "forecast": _with_power(out["forecast"], energy_type, capacity)}
    except AccountError as e:
        raise HTTPException(e.status, e.message)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except InferenceUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    forecast_points = out["forecast"]
    summary = forecast_summary.summarize((site, horizon, out["as_of"], model.run_id, model.version), forecast_points,
                                         energy_type.value, capacity, horizon)
    return ForecastResponse(
        summary=summary,
        energy_type=energy_type,
        site=site,
        horizon=horizon,
        unit=out.get("unit", "m/s"),
        as_of=out["as_of"],
        model=ref,
        actual=out.get("actual", []),
        forecast=out["forecast"],
        capacity_kw=capacity,
        power_basis=basis,
        source=source,
        simulated=simulated,
        stored_at=stored_at,
    )


def _iso(v) -> Optional[str]:
    return v.isoformat().replace("+00:00", "Z") if v is not None else None


def _plant_forecast(settings, site: str, energy_type: EnergyType, model: RegisteredModel, inference):
    """(output, capacity, source, simulated, stored_at) for a plant: the stored forecast for the newest
    shared window and the promoted model, made now if missing; or, for plants that keep their window,
    the newest forecast they made themselves."""
    consents = site_connection.plant_consents(site)
    if consents.get("share_forecast_window"):
        end = forecast_store.window_end(site)
        row = forecast_store.stored(site, model.horizon, "central", model.id, end) if end and model.id else None
        if row is None:
            out, req = forecast_store.compute_central(settings, site, energy_type, model, inference)
            if model.id is not None:
                row = forecast_store.save(site, model.horizon, "central", model.id, req["end_hour"],
                                          out.get("unit", "m/s"), float(req["capacity_kw"]), out.get("actual", []),
                                          out["forecast"])
            else:
                return out, float(req["capacity_kw"]), "central", req["simulated"], None
        simulated = site_connection.plant_is_simulated(site)
        return _from_row(row), float(row["capacity_kw"] or 0), "central", simulated, _iso(row["created_at"])
    row = forecast_store.stored(site, model.horizon, "local")
    if row is None:
        raise AccountError(409, "This plant forecasts on its own servers and hasn't sent a forecast yet")
    return _from_row(row), float(row["capacity_kw"] or 0), "local", False, _iso(row["created_at"])


def _from_row(row: dict) -> dict:
    return {"as_of": _iso(row["issued_at"]), "unit": row["unit"], "actual": row["actual"] or [],
            "forecast": row["forecast"]}
