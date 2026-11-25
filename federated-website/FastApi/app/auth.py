"""
Request authentication for the user API (SITE_NETWORK_PLAN.md §2.1 L5, §3).

  require_user     a live session cookie; state-changing requests also need X-CSRF-Token
  require_admin    require_user + role admin (start/stop runs, promote, approve, revoke, ...)
  require_role()   any set of roles

Cookie: fedwind_session, httpOnly, SameSite=Lax, Secure unless SESSION_COOKIE_SECURE=false (local
http development). The CSRF token comes from GET /api/auth/me and is kept in page memory.
"""

import hmac
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status

from app.db import DatabaseUnavailable
from app.services import accounts
from app.services.accounts import AccountError, Session, User

COOKIE = "fedwind_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def cookie_secure() -> bool:
    return os.environ.get("SESSION_COOKIE_SECURE", "true").lower() not in ("0", "false", "no")


def client_ip(request: Request) -> Optional[str]:
    # Behind our own proxies (the web server's /api forwarding, a Cloudflare tunnel, the gateway) the
    # visitor's address is in the headers. Cloudflare's CF-Connecting-IP can't be set by the visitor,
    # so it wins over X-Forwarded-For.
    if os.environ.get("TRUST_PROXY_HEADERS", "").lower() in ("1", "true", "yes"):
        cf = request.headers.get("cf-connecting-ip")
        if cf:
            return cf.strip()[:64]
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE, token, httponly=True, secure=cookie_secure(), samesite="lax",
        max_age=int(accounts.SESSION_TTL.total_seconds()), path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=cookie_secure(), samesite="lax")


def http_error(e: AccountError) -> HTTPException:
    return HTTPException(e.status, e.message)


def current_session(request: Request) -> Optional[Session]:
    """The session of this request, or None. 503 if the database is down."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        return accounts.session_from_token(token)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


def require_user(request: Request, session: Optional[Session] = Depends(current_session)) -> User:
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in first")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, session.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token; reload the page")
    return session.user


def require_role(*roles: str):
    def dependency(user: User = Depends(require_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This needs the {' or '.join(roles)} role")
        return user

    dependency.__name__ = f"require_{'_or_'.join(roles)}"
    return dependency


require_admin = require_role("admin")
