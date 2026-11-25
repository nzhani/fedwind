"""
FedWind site agent (DEMO_SIMULATION_PLAN.md §4, SITE_NETWORK_PLAN.md §5–6).

One program for real plants and for the demo simulation; only the data source differs:
  DATA_SOURCE=csv_inbox   a real plant: hourly exports dropped into /data/inbox
  DATA_SOURCE=nasa_power  simulation: NASA POWER weather at the plant's coordinates

What it does:
  1. First start: make the plant's keys in /secrets (keys.py; private keys never leave), then
     redeem the one-time token from the kit (/kit/enrollment.token) with a CSR and the Flower
     public key -> client certificate (/secrets/site.crt), and in token mode also a site key
     (/secrets/site.key, 0600). Later starts reuse them.
  2. Every heartbeat_s: report status (last data hour, rows and gaps today); the answer says
     whether the site is active or suspended.
  3. Once per UTC day: data-quality counts for the 7 newest data days.
  4. If the plant consented to central forecasting: whenever new data arrives, the newest
     WINDOW_HOURS hours of the forecast variable (wind speed or GHI) for the server's forecasts.
  5. Keeps the training store (store.py: /data/store/nasa_<site>.csv) that the kit's Flower
     SuperNode trains on, and reports only its size (hours) in the heartbeat.
  6. Serves a read-only status page on STATUS_PORT (8080; 0 = off), see status.py.
Only status, counts and (with consent) that one recent window leave the plant; never the history.

Environment (from the kit's .env): SITE_ID, ENERGY_TYPE, LAT, LON, SITE_API_URL, DATA_SOURCE,
HEARTBEAT_S, SITE_AUTH_MODE (token: bearer site key, development; mtls: the client certificate);
optional SECRETS_DIR (/secrets), TOKEN_FILE (/kit/enrollment.token), DATA_DIR (/data),
SITE_API_CA_FILE (extra CA bundle to trust the server, e.g. a private test gateway).
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

from site_agent import __version__, keys
from site_agent.store import TrainingStore
from site_agent.sources import make_source

log = logging.getLogger("fedwind.agent")

WINDOW_HOURS = 336   # 14 days: enough for every model input length the platform uses


class Revoked(Exception):
    """The platform no longer accepts this site's key."""


class Agent:
    def __init__(self, env: Optional[dict] = None, session: Optional[requests.Session] = None):
        env = dict(os.environ if env is None else env)
        self.site_id = env["SITE_ID"]
        self.api = env["SITE_API_URL"].rstrip("/")
        self.data_source = env.get("DATA_SOURCE", "csv_inbox")
        # Simulation is a property of the data source, never a separate code path
        self.kind = "simulated" if self.data_source == "nasa_power" else "kit"
        self.secrets = Path(env.get("SECRETS_DIR", "/secrets"))
        self.token_file = Path(env.get("TOKEN_FILE", "/kit/enrollment.token"))
        self.heartbeat_s = int(env.get("HEARTBEAT_S", "30"))
        self.mtls = env.get("SITE_AUTH_MODE", "token").lower() == "mtls"
        self.server_ca = env.get("SITE_API_CA_FILE") or True
        self.http = session or requests.Session()
        self.source = make_source(self.data_source, env)
        self.store = TrainingStore(Path(env.get("DATA_DIR", "/data")), self.site_id,
                                   float(env.get("LAT", "0") or 0), float(env.get("LON", "0") or 0))
        self.status_port = int(env.get("STATUS_PORT", "8080") or 0)
        self.last_heartbeat: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.status = "unknown"
        self.last_quality_day: Optional[str] = None
        self.last_window_end = None
        self._stop = False

    # -- credentials ---------------------------------------------------------------------------

    @property
    def key_file(self) -> Path:
        return self.secrets / "site.key"

    def site_key(self) -> Optional[str]:
        return self.key_file.read_text().strip() if self.key_file.is_file() else None

    def enrolled(self) -> bool:
        if self.mtls:
            return all((self.secrets / f).is_file() for f in (keys.CERT, keys.TLS_KEY, keys.TUNNEL_CERT))
        return self.site_key() is not None

    def site_config(self) -> dict:
        """What the platform said at enrollment (consents, heartbeat interval, ...)."""
        try:
            return json.loads((self.secrets / "site.json").read_text())
        except (OSError, ValueError):
            return {}

    def enroll(self) -> Optional[str]:
        """Make fresh keys and redeem the kit's one-time token; returns the site key (token mode)."""
        if not self.token_file.is_file():
            raise RuntimeError(f"Not enrolled and no enrollment token at {self.token_file}")
        token = self.token_file.read_text().strip()
        # Fresh keys every attempt: a key Flower has seen once can't be registered again
        csr, flower_pub = keys.new_enrollment_keys(self.secrets, self.site_id)
        r = self.http.post(f"{self.api}/site-api/enroll", timeout=60, **self._tls(client_cert=False),
                           json={"token": token, "agent": {"kind": self.kind, "version": __version__},
                                 "csr": csr, "flower_public_key": flower_pub})
        if r.status_code == 401:
            raise RuntimeError("The enrollment token is invalid, used or expired: download a new kit "
                               "(or ask the FedWind team to re-issue it)")
        if r.status_code in (409, 422):
            raise RuntimeError(f"Enrollment refused: {self._detail(r)}")
        r.raise_for_status()
        body = r.json()
        if body["site_id"] != self.site_id:
            raise RuntimeError(f"The token belongs to site {body['site_id']}, this kit is {self.site_id}")
        if body.get("certificate"):
            keys.save_certificate(self.secrets, body["certificate"], body.get("ca_certificate"))
            keys.make_local_tls(self.secrets)          # for the kit's tunnel + SuperNode
        elif self.mtls:
            raise RuntimeError("The platform returned no certificate; this kit needs one (SITE_AUTH_MODE=mtls)")
        if body.get("site_key"):
            keys.write_file(self.key_file, (body["site_key"] + "\n").encode())
        keys.write_file(self.secrets / "site.json", json.dumps(body["config"], indent=2).encode(), 0o644)
        self.heartbeat_s = int(body["config"].get("heartbeat_s", self.heartbeat_s))
        log.info("enrolled as %s (%s agent %s)%s%s", self.site_id, self.kind, __version__,
                 ", certificate valid %.0f days" % keys.certificate_days_left(self.secrets) if body.get("certificate") else "",
                 f", Flower node {body['flower_node_id']}" if body.get("flower_node_id") else "")
        return body.get("site_key")

    @staticmethod
    def _detail(r) -> str:
        try:
            return str(r.json().get("detail") or r.status_code)
        except ValueError:
            return str(r.status_code)

    def _tls(self, client_cert: bool = True) -> dict:
        """requests options in mtls mode: the plant certificate (except for enrollment) and the
        server's CA if a private one is configured. Token mode sends nothing extra."""
        if not self.mtls:
            return {}
        opts = {"verify": self.server_ca}
        if client_cert:
            opts["cert"] = (str(self.secrets / keys.CERT), str(self.secrets / keys.TLS_KEY))
        return opts

    def _post(self, path: str, payload: dict) -> dict:
        headers = {} if self.mtls else {"Authorization": f"Bearer {self.site_key()}"}
        r = self.http.post(f"{self.api}{path}", json=payload, timeout=30, headers=headers, **self._tls())
        if r.status_code == 401 or (self.mtls and r.status_code == 400):
            # nginx answers a revoked or unknown client certificate with 400 after the handshake
            raise Revoked("The platform rejected this site's credentials (revoked or re-issued)")
        r.raise_for_status()
        return r.json()

    # -- reports -------------------------------------------------------------------------------

    def heartbeat(self) -> dict:
        stats = self.source.today()
        answer = self._post("/site-api/heartbeat", {
            "agent_kind": self.kind,
            "agent_version": __version__,
            "last_data_hour": stats.last_hour.isoformat() if stats.last_hour else None,
            "rows_today": stats.rows,
            "gaps_today": stats.gaps,
            "train_hours": self.store.hours,
        })
        self.last_heartbeat = datetime.now(timezone.utc)
        if answer.get("status") != self.status:
            log.info("site status: %s", answer.get("status"))
        self.status = answer.get("status", self.status)
        self.heartbeat_s = int(answer.get("heartbeat_s", self.heartbeat_s))
        return answer

    def daily_quality(self, now: Optional[datetime] = None) -> list:
        """Once per UTC day (and at start): counts for the 7 days ending at the newest data day.
        The platform upserts per day, so resending a day is harmless; counting from the newest data
        (not the wall clock) keeps sources that lag, like NASA POWER, meaningful."""
        today = (now or datetime.now(timezone.utc)).date().isoformat()
        last = self.source.last_hour()
        if self.last_quality_day == today or last is None:
            return []
        sent = []
        for back in range(6, -1, -1):
            d = last.date() - timedelta(days=back)
            q = self.source.day(d)
            self._post("/site-api/quality", {"day": d.isoformat(), "rows": q.rows, "gaps": q.gaps,
                                             "flagged": q.flagged, "curtailed": q.curtailed})
            sent.append({"day": d.isoformat(), "rows": q.rows, "gaps": q.gaps})
        self.last_quality_day = today
        return sent

    def forecast_window(self) -> Optional[dict]:
        """With the central-forecasting consent: send the newest window when new data arrived."""
        if not (self.site_config().get("consents") or {}).get("share_forecast_window") or self.status != "active":
            return None
        end, values = self.source.window(WINDOW_HOURS)
        if end is None or end == self.last_window_end:
            return None
        answer = self._post("/site-api/forecast-input", {"end_hour": end.isoformat(), "values": values})
        self.last_window_end = end
        log.info("shared forecast window: %s valid hours up to %s", answer.get("valid_hours"), end.isoformat())
        return answer

    # -- main loop ------------------------------------------------------------------------------

    def step(self) -> None:
        self.heartbeat()
        self.daily_quality()
        self.forecast_window()

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_stop", True))
        if self.status_port:
            from site_agent import status

            try:
                status.serve(self, self.status_port)
            except OSError as e:
                log.warning("status page off: %s", e)
        backoff = 10
        while not self._stop:
            try:
                if not self.enrolled():
                    self.enroll()
                    self._warn_expiry()
                self.source.refresh()
                if self.store.update(self.source):
                    log.info("training store: %d hours in %s", self.store.hours, self.store.path.name)
                self.step()
                self.last_error = None
                backoff = 10
                self._sleep(self.heartbeat_s)
            except Revoked as e:
                self.last_error = str(e)
                log.error("%s. Waiting for a new kit; nothing is sent meanwhile.", e)
                self._sleep(300)
            except Exception as e:  # network, platform down, data trouble: keep going, slower
                self.last_error = f"{type(e).__name__}: {e}"
                log.warning("%s: %s (retrying in %d s)", type(e).__name__, e, backoff)
                self._sleep(backoff)
                backoff = min(backoff * 2, 300)

    def _warn_expiry(self) -> None:
        days = keys.certificate_days_left(self.secrets) if self.mtls else None
        if days is not None and days < 30:
            log.warning("the site certificate expires in %.0f days; automatic renewal comes with the next "
                        "kit version, until then ask the ArqauQuat team to re-issue the kit", days)

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self._stop and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")
    Agent().run()


if __name__ == "__main__":
    main()
