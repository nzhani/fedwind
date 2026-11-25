"""
Site connection routes (DEMO_SIMULATION_PLAN.md §2).

User side (session + CSRF):
  POST /api/my/sites/{id}/kit                  owner operator / admin: download the site kit (new one-time token)
  POST /api/admin/sites/{id}/reissue-kit       admin: revoke credentials, back to approved
  GET  /api/admin/overview                     admin: tiles, needs attention, recent activity

Site agents (/site-api, identity per SITE_AUTH_MODE, see app/site_auth.py):
  POST /site-api/enroll        one-time token + CSR + Flower public key -> certificate (+ site key in token mode)
  POST /site-api/heartbeat     status in, {status, heartbeat_s} out
  POST /site-api/quality       daily counts
  POST /site-api/forecast-input  newest hours of the forecast variable (central forecasting consent only)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import client_ip, require_admin, require_user
from app.db import DatabaseUnavailable
from app.platform_schemas import EnrollRequest, ForecastInputRequest, HeartbeatRequest, QualityRequest, SiteDecision
from app.services import run_store, site_connection
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
