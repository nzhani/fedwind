"""
Rate limits per client address (SITE_NETWORK_PLAN.md M8). The gateway limits login and enrollment
too (nginx limit_req); this protects every public route, also where the API is reached without it.

  RATE_LIMIT=off                          switch off (tests)
  RATE_LIMITS="auth=30/60,forecast=120/60"  override requests / seconds per bucket

Buckets (first match wins): auth (/api/auth/), enroll (/site-api/enroll), site (/site-api/),
forecast (/api/forecast), api (any other /api/ route). Over the limit: 429 with Retry-After.
"""

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse

DEFAULTS: Dict[str, Tuple[int, int]] = {
    "auth": (30, 60),
    "enroll": (20, 60),
    "site": (600, 60),
    "forecast": (120, 60),
    "api": (600, 60),
}
PREFIXES = (("/api/auth/", "auth"), ("/site-api/enroll", "enroll"), ("/site-api/", "site"),
            ("/api/forecast", "forecast"), ("/api/", "api"))


def limits() -> Dict[str, Tuple[int, int]]:
    out = dict(DEFAULTS)
    for part in filter(None, (p.strip() for p in os.environ.get("RATE_LIMITS", "").split(","))):
        name, _, spec = part.partition("=")
        n, _, per = spec.partition("/")
        out[name.strip()] = (int(n), int(per or 60))
    return out


class Limiter:
    def __init__(self):
        self.hits: Dict[Tuple[str, str], Deque[float]] = {}
        self.lock = threading.Lock()
        self.calls = 0

    def check(self, bucket: str, key: str, n: int, per: int, now: Optional[float] = None) -> Optional[int]:
        """None when allowed, else seconds until the next request is allowed."""
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.hits.setdefault((bucket, key), deque())
            while q and q[0] <= now - per:
                q.popleft()
            if len(q) >= n:
                return max(1, int(q[0] + per - now) + 1)
            q.append(now)
            self.calls += 1
            if self.calls % 10_000 == 0:       # forget idle clients now and then
                for k in [k for k, v in self.hits.items() if not v or v[-1] <= now - 3600]:
                    del self.hits[k]
        return None


limiter = Limiter()


async def middleware(request: Request, call_next):
    if os.environ.get("RATE_LIMIT", "on").lower() == "off":
        return await call_next(request)
    path = request.url.path
    bucket = next((b for prefix, b in PREFIXES if path.startswith(prefix)), None)
    if bucket is None:
        return await call_next(request)
    from app.auth import client_ip

    n, per = limits()[bucket]
    wait = limiter.check(bucket, client_ip(request) or "unknown", n, per)
    if wait is not None:
        return JSONResponse({"detail": f"Too many requests; try again in {wait} s"}, status_code=429,
                            headers={"Retry-After": str(wait)})
    return await call_next(request)
