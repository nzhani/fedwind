"""
Accounts API (SITE_NETWORK_PLAN.md §3, §10).

  POST /api/auth/register      operator self-registration: account + new organization (ALLOW_REGISTRATION)
  POST /api/auth/login         email + password -> session cookie
  POST /api/auth/logout
  GET  /api/auth/me            current user + CSRF token (401 if not logged in)

  GET   /api/admin/users       admin
  POST  /api/admin/users       admin: create an admin, operator or viewer
  PATCH /api/admin/users/{id}  admin: change role, enable/disable
  GET   /api/admin/audit       admin: recent audit log
"""

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.auth import (
    COOKIE,
    clear_session_cookie,
    client_ip,
    current_session,
    http_error,
    require_admin,
    require_user,
    set_session_cookie,
)
from app.db import DatabaseUnavailable
from app.services import accounts
from app.services.accounts import AccountError, User

router = APIRouter(prefix="/api")


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class RegisterRequest(LoginRequest):
    name: str = Field(max_length=200)
    organization: str = Field(max_length=200)


class CreateUserRequest(LoginRequest):
    name: str = Field(max_length=200)
    role: Literal["admin", "operator", "viewer"]
    organization: Optional[str] = Field(None, max_length=200)


class UpdateUserRequest(BaseModel):
    role: Optional[Literal["admin", "operator", "viewer"]] = None
    active: Optional[bool] = None


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AccountError as e:
        raise http_error(e)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


def _session_body(session: accounts.Session) -> dict:
    return {"user": session.user.public(), "csrf_token": session.csrf_token,
            "expires_at": session.expires_at.isoformat()}


def _registration_open() -> bool:
    return os.environ.get("ALLOW_REGISTRATION", "true").lower() not in ("0", "false", "no")


@router.post("/auth/register", status_code=status.HTTP_201_CREATED, summary="Register as a plant operator")
def register(body: RegisterRequest, request: Request, response: Response):
    if not _registration_open():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is closed; contact the ArqauQuat team")
    ip = client_ip(request)
    _call(accounts.create_user, body.email, body.password, body.name, "operator", body.organization, ip=ip)
    token, session = _call(accounts.login, body.email, body.password, ip=ip,
                           user_agent=request.headers.get("user-agent"))
    set_session_cookie(response, token)
    return _session_body(session)


@router.post("/auth/login", summary="Log in")
def login(body: LoginRequest, request: Request, response: Response):
    token, session = _call(accounts.login, body.email, body.password, ip=client_ip(request),
                           user_agent=request.headers.get("user-agent"))
    set_session_cookie(response, token)
    return _session_body(session)


@router.post("/auth/logout", summary="Log out")
def logout(request: Request, response: Response, user: User = Depends(require_user)):
    _call(accounts.logout, request.cookies.get(COOKIE), user, client_ip(request))
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/auth/me", summary="Current user and CSRF token")
def me(session: Optional[accounts.Session] = Depends(current_session)):
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return _session_body(session)


@router.get("/admin/users", summary="List users (admin)")
def list_users(_: User = Depends(require_admin)):
    return {"users": [u.public() for u in _call(accounts.list_users)]}


@router.post("/admin/users", status_code=status.HTTP_201_CREATED, summary="Create a user (admin)")
def create_user(body: CreateUserRequest, request: Request, admin: User = Depends(require_admin)):
    user = _call(accounts.create_user, body.email, body.password, body.name, body.role, body.organization,
                 actor=admin, ip=client_ip(request))
    return user.public()


@router.patch("/admin/users/{user_id}", summary="Change a user's role or status (admin)")
def update_user(user_id: int, body: UpdateUserRequest, request: Request, admin: User = Depends(require_admin)):
    user = _call(accounts.update_user, user_id, role=body.role, active=body.active, actor=admin, ip=client_ip(request))
    return user.public()


@router.get("/admin/audit", summary="Recent audit log (admin)")
def audit_log(limit: int = 200, action: Optional[str] = None, target: Optional[str] = None,
              actor: Optional[str] = None, before: Optional[int] = None, _: User = Depends(require_admin)):
    """Filters: action prefix (e.g. "site."), exact target, actor id; `before` = next_before of the previous page."""
    return _call(accounts.list_audit, limit, action, target, actor, before)
