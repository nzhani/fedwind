"""
Models Router - promoted global models (plan T3.1).

Endpoints:
  GET  /api/models                          Promoted model per (energy_type, horizon)
  POST /api/models/promote                  Promote a finished run (registers it as a version first)
  GET  /api/models/versions                 admin: every version with its gate report (M7)
  POST /api/models/versions/{id}/promote    admin: promote any version (also the rollback)
  POST /api/models/versions/{id}/veto       admin: undo an automatic promotion within 24 h
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from typing import List, Optional

from pydantic import BaseModel, Field

from app.platform_schemas import ModelListResponse, PromoteRequest, RegisteredModel
from app.services import model_registry, run_store
from app.services.model_registry import PromoteError, list_models, promote
from app.settings import get_settings
from app.auth import client_ip, require_admin
from app.services import accounts
from app.services.accounts import User

router = APIRouter(prefix="/api")


@router.get("/models", response_model=ModelListResponse, summary="List current models")
def get_models():
    return ModelListResponse(models=list_models(get_settings()))


@router.post("/models/promote", response_model=RegisteredModel, summary="Promote a run's model")
def promote_model(body: PromoteRequest, request: Request, admin: User = Depends(require_admin)):
    settings = get_settings()
    run = run_store.get_run(settings, body.run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run '{body.run_id}' not found")
    try:
        model = promote(settings, run, promoted_by=admin.name)
    except PromoteError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    accounts.record("model.promote", admin, body.run_id, {"energy_type": model.energy_type.value, "horizon": model.horizon},
           client_ip(request))
    return model


class VersionDecision(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


def _registry_only():
    if not model_registry._db():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Model versions need the database")


@router.get("/models/versions", response_model=List[RegisteredModel], summary="All model versions")
def versions(energy_type: Optional[str] = None, horizon: Optional[int] = None, _: User = Depends(require_admin)):
    _registry_only()
    return model_registry.list_versions(get_settings(), energy_type, horizon)


@router.post("/models/versions/{version_id}/promote", response_model=RegisteredModel, summary="Promote a version")
def promote_version(version_id: int, body: VersionDecision, request: Request, admin: User = Depends(require_admin)):
    _registry_only()
    try:
        m = model_registry.promote_version(get_settings(), version_id, admin.name, note=body.note)
    except PromoteError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    accounts.record("model.promote", admin, m.run_id, {"energy_type": m.energy_type.value, "horizon": m.horizon,
                                                       "version": m.version, "note": body.note}, client_ip(request))
    return m


@router.post("/models/versions/{version_id}/veto", response_model=RegisteredModel, summary="Veto an automatic promotion")
def veto_version(version_id: int, body: VersionDecision, request: Request, admin: User = Depends(require_admin)):
    _registry_only()
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Say why")
    try:
        m = model_registry.veto(get_settings(), version_id, admin.name, note)
    except PromoteError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    accounts.record("model.veto", admin, str(version_id), {"note": note, "restored_version": m.version},
                    client_ip(request))
    return m
