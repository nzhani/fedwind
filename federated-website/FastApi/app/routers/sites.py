"""
Sites Router - site registry and registration (SITE_NETWORK_PLAN.md §4, M2).

Endpoints:
  GET  /api/sites?energy_type=wind            Active sites (public; no owners, contacts or pending sites)
  POST /api/sites                             Operator: register a site for their organization
  GET  /api/my/sites                          Operator: their organization's sites; admin: all sites
  GET  /api/my/sites/{id}                     Detail + history (owner organization or admin; else 404)
  PUT  /api/my/sites/{id}                     Operator: edit while the site waits for approval
  POST /api/admin/sites/{id}/{action}         Admin: approve | reject | suspend | resume | revoke
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import client_ip, require_admin, require_role, require_user
from app.db import DatabaseUnavailable
from app.platform_schemas import (
    EnergyType,
    ConsentUpdate,
    SiteDecision,
    SiteDetail,
    SiteDetailListResponse,
    SiteListResponse,
    SiteRegistration,
)
from app.services import site_registry
from app.services.accounts import AccountError, User
from app.settings import get_settings

router = APIRouter(prefix="/api")
require_operator = require_role("operator")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AccountError as e:
        raise HTTPException(e.status, e.message)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


@router.get("/sites", response_model=SiteListResponse, summary="List active sites")
def get_sites(energy_type: Optional[EnergyType] = None):
    return SiteListResponse(sites=_call(site_registry.list_sites, get_settings(), energy_type, {"active"}))


@router.post("/sites", response_model=SiteDetail, status_code=status.HTTP_201_CREATED, summary="Register a site")
def register_site(body: SiteRegistration, request: Request, user: User = Depends(require_operator)):
    return _call(site_registry.register_site, user, body, client_ip(request))


@router.get("/my/sites", response_model=SiteDetailListResponse, summary="My organization's sites (admin: all)")
def my_sites(user: User = Depends(require_user)):
    return SiteDetailListResponse(sites=_call(site_registry.list_my_sites, user))


@router.get("/my/sites/{site_id}", response_model=SiteDetail, summary="Site detail and history")
def site_detail(site_id: str, user: User = Depends(require_user)):
    return _call(site_registry.get_site_detail, user, site_id)


@router.put("/my/sites/{site_id}", response_model=SiteDetail, summary="Edit a site waiting for approval")
def edit_site(site_id: str, body: SiteRegistration, request: Request, user: User = Depends(require_user)):
    return _call(site_registry.update_registration, user, site_id, body, client_ip(request))


@router.put("/my/sites/{site_id}/consents", response_model=SiteDetail, summary="Pause training or change consents")
def consents(site_id: str, body: ConsentUpdate, request: Request, user: User = Depends(require_user)):
    return _call(site_registry.update_consents, user, site_id, body, client_ip(request))


@router.post("/my/sites/{site_id}/leave", response_model=SiteDetail, summary="Take the plant out of the federation")
def leave(site_id: str, request: Request, body: Optional[SiteDecision] = None, user: User = Depends(require_user)):
    return _call(site_registry.leave, user, site_id, body.note if body else None, client_ip(request))


@router.post("/admin/sites/{site_id}/{action}", response_model=SiteDetail, summary="Approve, reject, suspend, resume or revoke")
def decide(site_id: str, action: str, request: Request, body: Optional[SiteDecision] = None,
           admin: User = Depends(require_admin)):
    return _call(site_registry.decide, admin, site_id, action, body.note if body else None, client_ip(request))
