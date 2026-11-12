"""
Models Router - promoted global models (plan T3.1).

Endpoints:
  GET  /api/models            Current model per (energy_type, horizon)
  POST /api/models/promote    Make a finished run's best checkpoint current
"""

from fastapi import APIRouter, HTTPException, status

from app.platform_schemas import ModelListResponse, PromoteRequest, RegisteredModel
from app.services import run_store
from app.services.model_registry import PromoteError, list_models, promote
from app.settings import get_settings

router = APIRouter(prefix="/api")


@router.get("/models", response_model=ModelListResponse, summary="List current models")
def get_models():
    return ModelListResponse(models=list_models(get_settings()))


@router.post("/models/promote", response_model=RegisteredModel, summary="Promote a run's model")
def promote_model(body: PromoteRequest):
    settings = get_settings()
    run = run_store.get_run(settings, body.run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run '{body.run_id}' not found")
    try:
        return promote(settings, run)
    except PromoteError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
