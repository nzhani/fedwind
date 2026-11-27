"""
Local status page of the site kit (SITE_NETWORK_PLAN.md §1 "status"): http://localhost:8080 on the
plant's server (the kit publishes it on 127.0.0.1 only). Read-only; no internet needed to view it.
Shows what the agent knows: enrollment, platform status, last heartbeat, data, training store,
certificate. Never shows keys or measurements.
"""

import html
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("fedwind.status")


def snapshot(agent) -> dict:
    from site_agent import __version__, keys

    days = keys.certificate_days_left(agent.secrets) if (agent.secrets / keys.CERT).is_file() else None
    last = agent.source.last_hour()
    return {
        "site_id": agent.site_id,
        "agent": f"{agent.kind} {__version__}",
        "auth_mode": "certificate (mTLS)" if agent.mtls else "site key (development)",
        "enrolled": agent.enrolled(),
        "platform_status": agent.status,
        "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
        "last_error": agent.last_error,
        "last_data_hour": last.isoformat() if last else None,
        "training_store_hours": agent.store.hours,
        "training_store_file": str(agent.store.path) if agent.store.path.is_file() else None,
        "certificate_days_left": round(days, 1) if days is not None else None,
        "shares_forecast_window": bool((agent.site_config().get("consents") or {}).get("share_forecast_window")),
        "update_available": (agent.update or {}).get("version"),
    }


def _page(s: dict) -> bytes:
    ok = s["enrolled"] and s["platform_status"] == "active" and not s["last_error"]
    rows = "".join(f"<tr><th>{html.escape(k.replace('_', ' '))}</th><td>{html.escape(str(v) if v is not None else '—')}</td></tr>"
                   for k, v in s.items())
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ArqauQuat site {html.escape(s['site_id'])}</title>
<style>body{{font:15px system-ui,sans-serif;margin:2rem auto;max-width:640px;padding:0 16px;color:#222}}
h1{{font-weight:500}}.pill{{display:inline-block;padding:2px 10px;border-radius:99px;background:{'#e3f5e8' if ok else '#fde8e1'}}}
th{{text-align:left;font-weight:500;color:#666;padding:6px 16px 6px 0;vertical-align:top}}td{{padding:6px 0;word-break:break-all}}</style>
</head><body><h1>ArqauQuat site kit</h1><p><span class="pill">{'Working' if ok else 'Needs attention'}</span></p>
<table>{rows}</table><p style="color:#666">Refreshes every 30 s. JSON: <a href="/status.json">/status.json</a></p></body></html>""".encode()


def serve(agent, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                s = snapshot(agent)
            except Exception as e:  # never take the agent down
                s = {"site_id": agent.site_id, "error": f"{type(e).__name__}: {e}", "enrolled": False,
                     "platform_status": None, "last_error": str(e)}
            if self.path.startswith("/status.json"):
                body, ctype = json.dumps(s, indent=2).encode(), "application/json"
            elif self.path in ("/", "/index.html"):
                body, ctype = _page(s), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="status-page", daemon=True).start()
    log.info("status page on port %d", port)
    return server
