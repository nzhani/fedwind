"""
How long the platform keeps what (SITE_NETWORK_PLAN.md M8). Run daily by the platform jobs loop.

  audit log                   AUDIT_RETENTION_DAYS (730)
  expired sessions            7 days after they expired
  sent Telegram messages      90 days
  link codes, used / replaced / expired enrollment tokens   90 days
  schedule slots              180 days
  daily data-quality counts   400 days
  heartbeats, shared windows, stored forecasts: their own shorter limits (7 / 30 / 30 days), applied
  where they are written
"""

import os
from typing import Dict

from app.db import connect

RULES = [
    ("audit_log", "at < now() - make_interval(days => %s)", "AUDIT_RETENTION_DAYS", 730),
    ("sessions", "expires_at < now() - interval '7 days'", None, None),
    ("notifications", "sent_at IS NOT NULL AND sent_at < now() - interval '90 days'", None, None),
    ("telegram_link_codes", "expires_at < now() - interval '90 days'", None, None),
    ("enrollment_tokens", "(used_at IS NOT NULL OR superseded_at IS NOT NULL OR expires_at < now())"
                          " AND created_at < now() - interval '90 days'", None, None),
    ("training_schedule", "last_attempt_at < now() - interval '180 days'", None, None),
    ("site_quality", "day < (now() - interval '400 days')::date", None, None),
]


def cleanup() -> Dict[str, int]:
    """Delete what is past its retention; returns rows deleted per table."""
    out = {}
    with connect() as conn:
        for table, where, env, default in RULES:
            args = (int(os.environ.get(env, default)),) if env else ()
            n = conn.execute(f"DELETE FROM {table} WHERE {where}", args).rowcount
            if n:
                out[table] = n
        if out:
            from app.services.accounts import audit

            audit(conn, "retention.cleanup", details=out)
    return out
