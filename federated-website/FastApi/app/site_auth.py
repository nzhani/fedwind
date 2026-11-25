"""
Who is calling the site API (DEMO_SIMULATION_PLAN.md §2.2). The one place that changes when plant
certificates arrive (SITE_NETWORK_PLAN.md M3/M4).

  SITE_AUTH_MODE=token   Authorization: Bearer fws_<key>, issued once at enrollment (development, demo).
                         Refused when ENV=production.
  SITE_AUTH_MODE=mtls    The gateway verified the client certificate (site CA + CRL) and forwards its CN
                         as X-Site-Id and its serial as X-Client-Serial; the API trusts them only
                         together with X-Gateway-Secret = GATEWAY_SHARED_SECRET, and only if they match
                         the site's live certificate credential (SITE_NETWORK_PLAN.md §2.1 L4).
"""

import hmac
import os
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.db import DatabaseUnavailable


@dataclass(frozen=True)
class SiteCaller:
    site_id: str
    credential_id: int
    status: str            # the site's status now (active, suspended, ...)
    energy_type: str
    agent_kind: str


def auth_mode() -> str:
    mode = os.environ.get("SITE_AUTH_MODE", "token").lower()
    if mode not in ("token", "mtls"):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Unknown SITE_AUTH_MODE '{mode}'")
    if mode == "token" and os.environ.get("ENV", "").lower() == "production":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "SITE_AUTH_MODE=token is for development only; production needs mtls")
    return mode


_UNAUTHORIZED = HTTPException(status.HTTP_401_UNAUTHORIZED, "Site credential missing, unknown or revoked",
                              headers={"WWW-Authenticate": "Bearer"})


def current_site(request: Request) -> SiteCaller:
    from app.services import site_connection  # avoid an import cycle at module load

    mode = auth_mode()
    try:
        if mode == "token":
            header = request.headers.get("authorization", "")
            scheme, _, key = header.partition(" ")
            if scheme.lower() != "bearer" or not key.startswith("fws_"):
                raise _UNAUTHORIZED
            caller = site_connection.caller_from_key(key.strip())
        else:
            secret = os.environ.get("GATEWAY_SHARED_SECRET", "")
            sent = request.headers.get("x-gateway-secret", "")
            site_id = request.headers.get("x-site-id", "")
            serial = request.headers.get("x-client-serial", "")
            if not secret or not hmac.compare_digest(sent, secret) or not site_id or not serial:
                raise _UNAUTHORIZED
            caller = site_connection.caller_from_certificate(site_id, serial)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    if caller is None:
        raise _UNAUTHORIZED
    return caller
