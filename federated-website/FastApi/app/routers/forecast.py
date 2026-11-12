"""
Forecast Router - per-site forecast from the current global model (plan FR-22, FR-26).

Endpoints:
  GET /api/forecast?energy_type=wind&site=almaty&horizon=72[&as_of=ISO]

Errors: 422 unknown site / horizon not in {1, 72, 432}; 501 solar;
503 no promoted model for the horizon, or the site's inference service
isn't connected.  The API never computes or fills in a forecast itself.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.platform_schemas import HORIZONS, EnergyType, ForecastModelRef, ForecastResponse
from app.services.inference_client import InferenceClient, InferenceUnavailable, get_inference
from app.services.model_registry import current_model, model_path
from app.services.site_registry import get_site
from app.settings import get_settings

router = APIRouter(prefix="/api")


@router.get("/forecast", response_model=ForecastResponse, summary="Forecast for one site")
def get_forecast(
    site: str,
    horizon: int,
    energy_type: EnergyType = EnergyType.WIND,
    as_of: Optional[str] = None,
    inference: InferenceClient = Depends(get_inference),
):
    if energy_type == EnergyType.SOLAR:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Solar forecasting is not available yet")

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

    model = current_model(settings, energy_type.value, horizon)
    if model is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"No model is registered for {energy_type.value} horizon {horizon}. Promote a finished run first.",
        )

    try:
        out = inference.forecast(site, horizon, as_of, model_path(energy_type.value, horizon))
    except InferenceUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    return ForecastResponse(
        energy_type=energy_type,
        site=site,
        horizon=horizon,
        unit=out.get("unit", "m/s"),
        as_of=out["as_of"],
        model=ForecastModelRef(run_id=model.run_id),
        actual=out.get("actual", []),
        forecast=out["forecast"],
    )
