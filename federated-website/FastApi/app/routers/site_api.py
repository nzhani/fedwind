"""
Site connection routes (DEMO_SIMULATION_PLAN.md §2).

User side (session + CSRF):
  POST /api/my/sites/{id}/kit                  owner operator / admin: download the site kit (new one-time token)
  POST /api/admin/sites/{id}/reissue-kit       admin: revoke credentials, back to approved
  GET  /api/admin/overview                     admin: tiles, needs attention, recent activity
  GET  /api/admin/health                       admin: services, models, forecasts, certificates, backups (M8)

Site agents (/site-api, identity per SITE_AUTH_MODE, see app/site_auth.py):
  POST /site-api/enroll        one-time token + CSR + Flower public key -> certificate (+ site key in token mode)
  POST /site-api/heartbeat     status in, {status, heartbeat_s} out
  POST /site-api/quality       daily counts
  POST /site-api/forecast-input  newest hours of the forecast variable (central forecasting consent only)
  GET  /site-api/models/current?horizon=  local mode: the promoted model for this plant's energy type
  GET  /site-api/models/{id}/file         local mode: download it (check the SHA-256)
  POST /site-api/forecasts                local mode: the forecast the plant made; nothing else is sent
  POST /site-api/renew                    a new certificate before the current one expires (M8)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.auth import client_ip, require_admin, require_user
from app.db import DatabaseUnavailable
from app.platform_schemas import (EnrollRequest, ForecastInputRequest, HeartbeatRequest, LocalForecastRequest,
                                  QualityRequest, RenewRequest, SiteDecision)
from app.services import forecast_store, model_registry, run_store, site_connection
from app.services.accounts import AccountError, User
from app.settings import get_settings
from app.site_auth import SiteCaller, auth_mode, current_site

router = APIRouter()


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AccountError as e:
        raise HTTPException(e.status, e.message)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


@router.post("/api/my/sites/{site_id}/kit", summary="Download the site kit (issues a new one-time token)")
def download_kit(site_id: str, request: Request, user: User = Depends(require_user)):
    data, name = _call(site_connection.issue_kit, user, site_id, client_ip(request))
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/api/admin/sites/{site_id}/reissue-kit", summary="Revoke a site's credentials and allow a new kit")
def reissue_kit(site_id: str, body: SiteDecision, request: Request, admin: User = Depends(require_admin)):
    _call(site_connection.reissue_kit, admin, site_id, body.note, client_ip(request))
    from app.services import site_registry

    return _call(site_registry.get_site_detail, admin, site_id)


@router.get("/api/admin/health", summary="Admin: health of the central server (M8)")
def health_report(_: User = Depends(require_admin)):
    from app.services import health

    return health.report(get_settings())


@router.get("/api/admin/overview", summary="Admin overview")
def overview(_: User = Depends(require_admin)):
    return _call(site_connection.admin_overview, run_store.list_runs(get_settings()))


@router.post("/site-api/enroll", summary="Site agent: redeem the one-time token")
def enroll(body: EnrollRequest, request: Request):
    return _call(site_connection.enroll, body.token.strip(), body.agent.kind, body.agent.version,
                 body.flower_public_key, client_ip(request), csr=body.csr, require_cert=auth_mode() == "mtls")


@router.post("/site-api/heartbeat", summary="Site agent: status")
def heartbeat(body: HeartbeatRequest, caller: SiteCaller = Depends(current_site)):
    return _call(site_connection.heartbeat, caller, body)


@router.post("/site-api/quality", summary="Site agent: daily data-quality counts")
def quality(body: QualityRequest, caller: SiteCaller = Depends(current_site)):
    return _call(site_connection.record_quality, caller, body)


@router.post("/site-api/forecast-input", summary="Site agent: recent window for central forecasting")
def forecast_input(body: ForecastInputRequest, caller: SiteCaller = Depends(current_site)):
    return _call(site_connection.record_forecast_input, caller, body)


def _active(caller: SiteCaller) -> None:
    if caller.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"The site is {caller.status}")


@router.get("/site-api/models/current", summary="Site agent: the promoted model (local mode)")
def current_model_for_site(horizon: int, caller: SiteCaller = Depends(current_site)):
    _active(caller)
    m = _call(model_registry.current_model, get_settings(), caller.energy_type, horizon)
    if m is None or m.id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No promoted {caller.energy_type} model for {horizon} h")
    return {"id": m.id, "version": m.version, "energy_type": m.energy_type.value, "horizon": m.horizon,
            "run_id": m.run_id, "sha256": m.sha256, "size_bytes": m.size_bytes, "promoted_at": m.promoted_at,
            "download": f"/site-api/models/{m.id}/file"}


@router.get("/site-api/models/{version_id}/file", summary="Site agent: download a model version (local mode)")
def model_file(version_id: int, caller: SiteCaller = Depends(current_site)):
    _active(caller)
    m = _call(model_registry.get_version, version_id)
    # The promoted one, or the one it just replaced (a download may cross a promotion)
    if m is None or m.energy_type.value != caller.energy_type or m.status not in ("promoted", "retired"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model version not found")
    path = get_settings().models_dir / m.model_path
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model file missing")
    return FileResponse(path, media_type="application/octet-stream", filename=f"{m.energy_type.value}-h{m.horizon}"
                        f"-v{m.version}.pt", headers={"X-Model-SHA256": m.sha256 or ""})


@router.post("/site-api/forecasts", summary="Site agent: a forecast made at the plant (local mode)")
def local_forecast(body: LocalForecastRequest, caller: SiteCaller = Depends(current_site)):
    return _call(forecast_store.save_local, caller, body, get_settings())


@router.post("/site-api/renew", summary="Site agent: renew the client certificate")
def renew(body: RenewRequest, request: Request, caller: SiteCaller = Depends(current_site)):
    return _call(site_connection.renew_certificate, caller, body.csr, client_ip(request))
