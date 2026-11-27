"""
Site connection (DEMO_SIMULATION_PLAN.md §2–4, SITE_NETWORK_PLAN.md §4–6).

  kit          an approved site's operator downloads a zip with a one-time enrollment token (72 h)
               and the site CA certificate; each new kit supersedes the previous unused token (only
               token hashes are stored)
  enroll       the site agent redeems the token with a CSR and its Flower public key (keys made at the
               plant, never sent): the CA signs a 90-day client certificate (CN = site id), the
               SuperNode key is registered with Flower (FLOWER_NODE_AUTH=on), the site becomes active.
               In token mode (development) it also gets a site key for the bearer header.
  heartbeat    every HEARTBEAT_S seconds; the answer tells the agent if it was suspended
  quality      daily counts (rows, gaps, flagged, curtailed); never measurements
  re-issue     admin: revoke the site's credentials and let the operator download a new kit
  revoke       credentials revoked in the database at once; after the commit the certificate goes into
               the CRL and the Flower node is unregistered (retried by the maintenance loop until done)

Only the plant is simulated in the demo (site agent with a NASA POWER source); this module is the
real platform side.
"""

import fcntl
import hashlib
import io
import json
import logging
import os
import re
import secrets
import textwrap
import threading
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import urlparse

from app.db import connect
from app.platform_schemas import SiteConnection, SiteKitState, SiteProgress
from app.services import flower_nodes as node_registry, site_ca
from app.services.accounts import AccountError, User, audit
from app.services.federation_client import FederationUnavailable
from app.site_auth import SiteCaller

log = logging.getLogger("fedwind.sites")

KIT_DIR = Path(__file__).resolve().parents[1] / "kit"   # compose, GPU override and tunnel templates
TOKEN_TTL = timedelta(hours=72)
MAX_FAILED_ENROLLS = 20          # per IP in 15 minutes
HEARTBEAT_HISTORY = timedelta(days=7)


def heartbeat_seconds() -> int:
    return max(5, int(os.environ.get("HEARTBEAT_S", "30")))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


# ---------------------------------------------------------------------------
# Kit
# ---------------------------------------------------------------------------

def _may_manage(user: User, row: dict) -> bool:
    return user.role == "admin" or (row["org_id"] is not None and row["org_id"] == user.org_id and user.role == "operator")


def issue_kit(user: User, site_id: str, ip: Optional[str] = None) -> tuple[bytes, str]:
    """(zip bytes, file name). Only while the site is approved and has no live credential."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM sites WHERE id = %s FOR UPDATE", (site_id,)).fetchone()
        if row is None or not _may_manage(user, row):
            raise AccountError(404, "Site not found")
        if row["kind"] != "plant":
            raise AccountError(409, "Lab sites run inside the lab; they have no site kit")
        live = conn.execute("SELECT 1 FROM site_credentials WHERE site_id = %s AND revoked_at IS NULL",
                            (site_id,)).fetchone()
        if live:
            raise AccountError(409, "The kit is already installed; ask an admin to re-issue it if the plant lost it")
        if row["status"] != "approved":
            raise AccountError(409, f"The site is {row['status']}; the kit is available once it is approved")
        conn.execute("UPDATE enrollment_tokens SET superseded_at = now() WHERE site_id = %s"
                     " AND used_at IS NULL AND superseded_at IS NULL", (site_id,))
        token = "fwe_" + secrets.token_urlsafe(32)
        expires = _now() + TOKEN_TTL
        conn.execute("INSERT INTO enrollment_tokens (site_id, token_hash, created_by, expires_at) VALUES (%s, %s, %s, %s)",
                     (site_id, _hash(token), user.id, expires))
        audit(conn, "site.kit", actor_type="user", actor_id=user.id, target=site_id,
              details={"expires_at": expires.isoformat()}, ip=ip)
        return build_kit_zip(row, token, expires), f"fedwind-site-{site_id}.zip"


def kit_site_api_url() -> str:
    """The site API address written into kits. A server on the same computer (localhost) is reached
    from inside the kit's containers as host.docker.internal, which the kit maps to this computer."""
    url = os.environ.get("SITE_API_PUBLIC_URL", "http://localhost:8001").rstrip("/")
    parsed = urlparse(url)
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        url = parsed._replace(netloc=parsed.netloc.replace(parsed.hostname, "host.docker.internal", 1)).geturl()
    return url


def build_kit_zip(site: dict, token: str, expires: datetime) -> bytes:
    """The final kit layout (SITE_NETWORK_PLAN.md §5.1). The tunnel and SuperNode join it in M4–M6."""
    sid = site["id"]
    site_api = kit_site_api_url()
    portal = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    gateway_host = urlparse(site_api).hostname or "localhost"
    root = f"fedwind-site-{sid}"
    env = "\n".join([
        "# ArqauQuat site kit settings (no secrets here; the token is in enrollment.token)",
        f"SITE_ID={sid}",
        f"SITE_NAME={site['name']}",
        f"ENERGY_TYPE={site['energy_type']}",
        f"LAT={site['lat']}",
        f"LON={site['lon']}",
        f"TIMEZONE={site['timezone']}",
        f"CAPACITY_KW={site['capacity_kw'] or ''}",
        f"SITE_API_URL={site_api}",
        f"PORTAL_URL={portal}",
        "# token: development (bearer site key); mtls: the client certificate from enrollment",
        f"SITE_AUTH_MODE={os.environ.get('SITE_AUTH_MODE', 'token').lower()}",
        "# federation: also start the tunnel and the Flower SuperNode (needs the mTLS gateway)",
        f"COMPOSE_PROFILES={'federation' if os.environ.get('SITE_AUTH_MODE', 'token').lower() == 'mtls' else ''}",
        f"GATEWAY_HOST={gateway_host}",
        "# Images: downloaded by `docker compose up` when published to a registry (KIT_AGENT_IMAGE /",
        "# KIT_SUPERNODE_IMAGE on the server); otherwise built locally from the repository",
        f"AGENT_IMAGE={os.environ.get('KIT_AGENT_IMAGE') or 'fedwind-site-agent:0.3.0'}",
        f"SUPERNODE_IMAGE={os.environ.get('KIT_SUPERNODE_IMAGE') or 'fedwind-flower:latest'}",
        "# The GPT-2 cache folder the Flower client reads (training only)",
        "HF_CACHE=./hf-cache",
        "# Where the plant's data comes from:",
        "#   csv_inbox   a real plant: hourly exports dropped into data/inbox (data/README.md)",
        "#   nasa_power  a demo plant: NASA POWER weather at this plant's coordinates (needs internet)",
        "DATA_SOURCE=csv_inbox",
        f"HEARTBEAT_S={heartbeat_seconds()}",
        "",
    ])
    mtls = os.environ.get("SITE_AUTH_MODE", "token").lower() == "mtls"
    values = {"SITE_ID": sid, "SITE_NAME": site["name"].replace("\n", " "), "ENERGY_TYPE": site["energy_type"],
              "GATEWAY_HOST": gateway_host}
    compose = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], (KIT_DIR / "docker-compose.yml.tmpl").read_text())
    if mtls:
        training = textwrap.fill(
            "Once the plant is enrolled two more containers start (COMPOSE_PROFILES=federation in .env): "
            f"`tunnel`, which holds the plant certificate and connects to {gateway_host}:443, and `supernode`, "
            "the Flower client, which trains here when a run comes and sends only model updates. On a GPU "
            "server start with `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`. "
            "Put the GPT-2 model cache into `hf-cache/` (the ArqauQuat team provides it).",
            98, subsequent_indent=" " * 8, break_on_hyphens=False, break_long_words=False)   # the README below is dedented by 8
    else:
        training = ("This platform runs in development mode: only the agent starts. Training through the "
                    "gateway starts when the platform switches to certificates.")
    readme = textwrap.dedent(f"""\
        # ArqauQuat site kit: {site['name']}

        Site id: `{sid}` · {site['energy_type']} · {(site['capacity_kw'] or 0) / 1000:g} MW
        Enrollment token valid until **{expires.strftime('%Y-%m-%d %H:%M UTC')}** (one use).

        ## Install
        1. Copy this folder to a Linux server or VM at the plant with Docker Engine and Compose v2.
           It needs outbound HTTPS to {site_api}. No inbound ports.
        2. Put hourly exports into `data/inbox/` (format in `data/README.md`). No data yet? The plant
           still connects and shows Online; for a demo, set `DATA_SOURCE=nasa_power` in `.env`.
        3. Start: `docker compose up -d` (the first start downloads the images if they are published)
        4. Check: `docker compose logs -f agent` shows "enrolled as {sid}", and the plant page at
           {portal}/sites/{sid} turns **Online** within a minute. Local status page: http://localhost:8080

        The token is used once. If the kit is lost or the server is replaced, ask the ArqauQuat team to
        re-issue it; the old credentials stop working.

        ## Training (Flower)
        {training}

        ## Keys and certificate
        At the first start the agent makes two private keys in `secrets/` (they never leave this
        server): one for the plant's certificate, one for its Flower node. It sends only a signing
        request and the public key; the ArqauQuat site CA (`ca.crt`) returns a certificate valid for
        90 days. Keep `secrets/` private and backed up with the server; a re-issued kit makes new keys.

        ## What leaves the plant
        - Status every {heartbeat_seconds()} s (online, last data hour, counts of rows and gaps).
        - Daily data-quality counts.
        - If you consented to central forecasting: the last 14 days of the forecast variable, hourly.
        - Later, during training runs: model updates only (never the measurement history).
        """)
    data_readme = textwrap.dedent("""\
        # Data contract (hourly, UTC)

        CSV with a header row; one row per hour; finer data is averaged by the agent.

        | column | wind | solar | unit |
        |---|---|---|---|
        | timestamp_utc | yes | yes | ISO 8601, hour start, UTC |
        | wind_speed_ms | yes | - | m/s at hub height |
        | ghi_wm2 | - | yes | W/m2, hour average |
        | power_kw | yes | yes | AC export, hour average |
        | available | yes | yes | 0-1 share of capacity available |
        | curtailed | yes | yes | 1 if output was limited |
        """)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{root}/README.md", readme)
        z.writestr(f"{root}/docker-compose.yml", compose)
        z.writestr(f"{root}/docker-compose.gpu.yml", (KIT_DIR / "docker-compose.gpu.yml").read_text())
        z.writestr(f"{root}/tunnel.conf.template", (KIT_DIR / "tunnel.conf.template").read_text())
        reload = zipfile.ZipInfo(f"{root}/tunnel-reload.sh")
        reload.external_attr = 0o755 << 16           # executable after unzip (nginx runs only executable hooks)
        z.writestr(reload, (KIT_DIR / "tunnel-reload.sh").read_text())
        z.writestr(f"{root}/.env", env)
        z.writestr(f"{root}/enrollment.token", token + "\n")
        z.writestr(f"{root}/ca.crt", site_ca.ca_cert_pem())
        z.writestr(f"{root}/data/README.md", data_readme)
        z.writestr(f"{root}/data/inbox/.keep", "")
        z.writestr(f"{root}/secrets/.keep", "")
        z.writestr(f"{root}/outputs/.keep", "")
        z.writestr(f"{root}/hf-cache/.keep", "")
    return buf.getvalue()


def revoke_credentials(conn, site_id: str) -> int:
    """Revoke the live credential and every unused token of a site; returns credentials revoked.
    Certificates and Flower nodes are queued in site_revocations; call apply_revocations() after the
    transaction commits to publish the CRL and unregister the nodes."""
    conn.execute("UPDATE enrollment_tokens SET superseded_at = now() WHERE site_id = %s"
                 " AND used_at IS NULL AND superseded_at IS NULL", (site_id,))
    rows = conn.execute("UPDATE site_credentials SET revoked_at = now() WHERE site_id = %s AND revoked_at IS NULL"
                        " RETURNING id, cert_serial, cert_not_after, flower_node_id, revoked_at", (site_id,)).fetchall()
    for r in rows:
        if r["cert_serial"] or r["flower_node_id"]:
            conn.execute(
                "INSERT INTO site_revocations (site_id, credential_id, cert_serial, cert_not_after, flower_node_id,"
                " revoked_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (cert_serial) DO NOTHING",
                (site_id, r["id"], r["cert_serial"], r["cert_not_after"], r["flower_node_id"], r["revoked_at"]))
    return len(rows)


_crl_lock = threading.Lock()


def apply_revocations() -> dict:
    """Publish the CRL (revoked certificates that haven't expired) and unregister revoked Flower
    nodes still pending. Safe to call any time; never raises (the maintenance loop retries)."""
    out = {"crl_entries": None, "unregistered": 0, "failed": 0}
    try:
        with connect() as conn:
            revoked = [(r["cert_serial"], r["revoked_at"]) for r in conn.execute(
                "SELECT cert_serial, revoked_at FROM site_revocations WHERE cert_serial IS NOT NULL"
                " AND (cert_not_after IS NULL OR cert_not_after > now()) ORDER BY id").fetchall()]
            pending = conn.execute("SELECT id, flower_node_id FROM site_revocations WHERE flower_node_id IS NOT NULL"
                                   " AND flower_unregistered_at IS NULL ORDER BY id").fetchall()
        if revoked or site_ca.exists():
            # One writer at a time (threads here, processes via the lock file), always from the newest rows
            with _crl_lock:
                site_ca.ca_dir().mkdir(parents=True, exist_ok=True)
                with open(site_ca.ca_dir() / "crl.lock", "w") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    site_ca.write_crl(revoked)
            out["crl_entries"] = len(revoked)
        if pending:
            nodes = node_registry.get_flower_nodes()
            if nodes is None:
                log.warning("%d revoked Flower node(s) wait for FLOWER_NODE_AUTH=on to be unregistered", len(pending))
            for p in pending if nodes else []:
                try:
                    nodes.unregister(p["flower_node_id"])
                    error = None
                except FederationUnavailable as e:
                    # Already gone counts as done
                    error = None if "not found" in str(e).lower() else str(e)[:500]
                with connect() as conn:
                    if error is None:
                        conn.execute("UPDATE site_revocations SET flower_unregistered_at = now(), flower_error = NULL"
                                     " WHERE id = %s", (p["id"],))
                        out["unregistered"] += 1
                    else:
                        conn.execute("UPDATE site_revocations SET flower_error = %s WHERE id = %s", (error, p["id"]))
                        out["failed"] += 1
                        log.warning("unregistering Flower node %s failed: %s", p["flower_node_id"], error)
    except Exception as e:  # never break the request that revoked; the loop tries again
        log.warning("applying revocations failed: %s: %s", type(e).__name__, e)
        out["error"] = str(e)
    return out


MAINTENANCE_S = 3600


def start_maintenance() -> bool:
    """Hourly: re-publish the CRL before it expires and retry Flower unregistrations.
    Off with SITE_MAINTENANCE_LOOP=off (tests)."""
    if os.environ.get("SITE_MAINTENANCE_LOOP", "on").lower() == "off":
        return False

    def loop():
        wait = threading.Event()  # never set: an interruptible sleep
        while True:
            apply_revocations()
            from app.services.health import beat

            beat("site maintenance")
            wait.wait(MAINTENANCE_S)

    threading.Thread(target=loop, name="site-maintenance", daemon=True).start()
    return True


def reissue_kit(admin: User, site_id: str, note: Optional[str], ip: Optional[str] = None) -> None:
    """Lost kit or replaced server: old credentials stop working, the operator downloads a new kit."""
    note = (note or "").strip() or None
    if not note:
        raise AccountError(422, "Say why (the operator sees it)")
    with connect() as conn:
        row = conn.execute("SELECT * FROM sites WHERE id = %s FOR UPDATE", (site_id,)).fetchone()
        if row is None:
            raise AccountError(404, "Site not found")
        if row["kind"] != "plant" or row["status"] not in ("approved", "active", "suspended"):
            raise AccountError(409, f"Can't re-issue a kit for a site that is {row['status']}")
        revoked = revoke_credentials(conn, site_id)
        conn.execute("UPDATE sites SET status = 'approved', decision_note = %s, decided_by = %s, decided_at = now(),"
                     " updated_at = now() WHERE id = %s", (note, admin.id, site_id))
        audit(conn, "site.reissue", actor_type="user", actor_id=admin.id, target=site_id,
              details={"from": row["status"], "to": "approved", "credentials_revoked": revoked, "note": note}, ip=ip)
    apply_revocations()


# ---------------------------------------------------------------------------
# Site API
# ---------------------------------------------------------------------------

def enroll(token: str, agent_kind: str, agent_version: str, flower_public_key: Optional[str],
           ip: Optional[str] = None, csr: Optional[str] = None, require_cert: bool = False) -> dict:
    """Redeem a one-time token. With a CSR the site gets a client certificate; with node auth on, its
    Flower key is registered. Any failure after the token check rolls everything back, so the plant
    can fix it and retry with the same token."""
    if require_cert and not csr:
        raise AccountError(422, "This platform enrolls with certificates: the agent must send a CSR (agent 0.2+)")
    try:
        nodes = node_registry.get_flower_nodes()
        pubkey = node_registry.check_public_key(flower_public_key) if flower_public_key else None
    except node_registry.FlowerKeyError as e:
        raise AccountError(422, str(e))
    except FederationUnavailable as e:
        raise AccountError(503, str(e))
    if nodes is not None and not pubkey:
        raise AccountError(422, "This federation registers SuperNodes: send the Flower public key")

    error = None
    result = None
    with connect() as conn:
        failed = conn.execute("SELECT count(*) AS n FROM audit_log WHERE action = 'site.enroll_failed' AND ip = %s"
                              " AND at > now() - interval '15 minutes'", (ip,)).fetchone()["n"]
        if failed >= MAX_FAILED_ENROLLS:
            error = AccountError(429, "Too many failed enrollments from this address; try again later")
        else:
            row = conn.execute(
                "SELECT t.id AS token_id, t.expires_at, t.used_at, t.superseded_at, s.* FROM enrollment_tokens t"
                " JOIN sites s ON s.id = t.site_id WHERE t.token_hash = %s FOR UPDATE OF t, s",
                (_hash(token),)).fetchone()
            if (row is None or row["used_at"] or row["superseded_at"] or row["expires_at"] <= _now()
                    or row["status"] != "approved"):
                audit(conn, "site.enroll_failed", actor_type="anonymous", target=row["id"] if row else None, ip=ip,
                      details={"reason": "unknown" if row is None else "used" if row["used_at"] else
                               "superseded" if row["superseded_at"] else "expired" if row["expires_at"] <= _now()
                               else f"site {row['status']}"})
                error = AccountError(401, "Invalid or expired enrollment token")
            else:
                # From here on a raise rolls back: the token stays unused
                if pubkey and conn.execute("SELECT 1 FROM site_credentials WHERE flower_pubkey = %s",
                                           (pubkey,)).fetchone():
                    raise AccountError(409, "This Flower key was enrolled before; the agent must make new keys")
                issued = None
                if csr:
                    try:
                        issued = site_ca.sign_csr(csr, row["id"])
                    except site_ca.CsrError as e:
                        raise AccountError(422, str(e))
                node_id = None
                if nodes is not None:
                    try:
                        node_id = nodes.register(pubkey)
                    except FederationUnavailable as e:
                        raise AccountError(503, f"Couldn't register the plant's Flower node: {e}")
                try:
                    key = None if require_cert else "fws_" + secrets.token_urlsafe(32)
                    conn.execute("UPDATE enrollment_tokens SET used_at = now() WHERE id = %s", (row["token_id"],))
                    conn.execute(
                        "INSERT INTO site_credentials (site_id, kind, secret_hash, cert_serial, cert_not_after,"
                        " flower_pubkey, flower_node_id, agent_kind, agent_version)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (row["id"], "cert" if issued else "token", _hash(key) if key else None,
                         issued.serial if issued else None, issued.not_after if issued else None,
                         pubkey, node_id, agent_kind, agent_version))
                    conn.execute("UPDATE sites SET status = 'active', updated_at = now() WHERE id = %s", (row["id"],))
                    audit(conn, "site.enroll", actor_type="site", actor_id=row["id"], target=row["id"], ip=ip,
                          details={"agent_kind": agent_kind, "agent_version": agent_version,
                                   **({"cert_serial": issued.serial} if issued else {}),
                                   **({"flower_node_id": node_id} if node_id else {})})
                except Exception:
                    if node_id is not None:  # don't leave a registered node behind a failed enrollment
                        try:
                            nodes.unregister(node_id)
                        except FederationUnavailable as e:
                            log.warning("rollback: unregistering Flower node %s failed: %s", node_id, e)
                    raise
                result = {
                    "site_id": row["id"],
                    "config": {"heartbeat_s": heartbeat_seconds(), "energy_type": row["energy_type"],
                               "lat": row["lat"], "lon": row["lon"], "timezone": row["timezone"],
                               "capacity_kw": row["capacity_kw"], "equipment": row["equipment"],
                               "consents": row["consents"]},
                }
                if key:
                    result["site_key"] = key
                if issued:
                    result.update(certificate=issued.pem, ca_certificate=site_ca.ca_cert_pem(),
                                  certificate_expires_at=issued.not_after.isoformat())
                if node_id is not None:
                    result["flower_node_id"] = node_id
    if error:
        raise error
    return result


RENEW_BEFORE = timedelta(days=30)


def renew_certificate(caller: SiteCaller, csr: str, ip: Optional[str] = None) -> dict:
    """A plant renews its client certificate before it expires (SITE_NETWORK_PLAN.md M8, §6), calling
    with its current, still valid credential. The new certificate replaces the old one on the
    credential at once, so the API accepts only the new serial; the old one runs out on its own
    (and Flower still needs the registered node key)."""
    if caller.status not in ("active", "suspended"):
        raise AccountError(409, f"The site is {caller.status}; it can't renew its certificate")
    with connect() as conn:
        cred = conn.execute("SELECT * FROM site_credentials WHERE id = %s AND revoked_at IS NULL FOR UPDATE",
                            (caller.credential_id,)).fetchone()
        if cred is None or not cred["cert_serial"]:
            raise AccountError(409, "This site has no certificate to renew; enroll with a new kit")
        try:
            issued = site_ca.sign_csr(csr, caller.site_id)
        except site_ca.CsrError as e:
            raise AccountError(422, str(e))
        conn.execute("UPDATE site_credentials SET cert_serial = %s, cert_not_after = %s WHERE id = %s",
                     (issued.serial, issued.not_after, cred["id"]))
        audit(conn, "site.renew", actor_type="site", actor_id=caller.site_id, target=caller.site_id, ip=ip,
              details={"old_serial": cred["cert_serial"], "new_serial": issued.serial,
                       "not_after": issued.not_after.isoformat()})
    return {"certificate": issued.pem, "ca_certificate": site_ca.ca_cert_pem(),
            "certificate_expires_at": issued.not_after.isoformat()}


def _caller(row: Optional[dict]) -> Optional[SiteCaller]:
    if row is None:
        return None
    return SiteCaller(site_id=row["site_id"], credential_id=row["id"], status=row["status"],
                      energy_type=row["energy_type"], agent_kind=row["agent_kind"])


def caller_from_key(key: str) -> Optional[SiteCaller]:
    with connect() as conn:
        row = conn.execute(
            "SELECT c.id, c.site_id, c.agent_kind, s.status, s.energy_type FROM site_credentials c"
            " JOIN sites s ON s.id = c.site_id WHERE c.secret_hash = %s AND c.revoked_at IS NULL", (_hash(key),)).fetchone()
    return _caller(row)


def caller_from_certificate(site_id: str, serial: str) -> Optional[SiteCaller]:
    """mtls mode: the gateway verified the certificate (CA + CRL) and forwards its CN and serial. Both
    must match the site's live credential, so an old certificate (re-issued kit, CRL not reloaded
    yet) is refused here too."""
    serial = site_ca.normalize_serial(serial)
    if not serial:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT c.id, c.site_id, c.agent_kind, s.status, s.energy_type FROM site_credentials c"
            " JOIN sites s ON s.id = c.site_id WHERE c.site_id = %s AND c.kind = 'cert' AND c.cert_serial = %s"
            " AND c.revoked_at IS NULL AND c.cert_not_after > now()",
            (site_id, serial)).fetchone()
    return _caller(row)


def heartbeat(caller: SiteCaller, body) -> dict:
    last_hour = None
    if body.last_data_hour:
        try:
            last_hour = datetime.fromisoformat(body.last_data_hour.replace("Z", "+00:00"))
        except ValueError:
            raise AccountError(422, "last_data_hour is not an ISO timestamp")
    with connect() as conn:
        conn.execute(
            "INSERT INTO site_heartbeats (site_id, agent_kind, agent_version, last_data_hour, rows_today, gaps_today, payload)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (caller.site_id, body.agent_kind, body.agent_version, last_hour, body.rows_today, body.gaps_today,
             json.dumps({"disk_free_gb": body.disk_free_gb, "gpu": body.gpu, "train_hours": body.train_hours})))
        first = conn.execute(
            "UPDATE site_credentials SET last_seen_at = now(), agent_version = %s,"
            " first_seen_at = COALESCE(first_seen_at, now()) WHERE id = %s RETURNING (first_seen_at = last_seen_at) AS first",
            (body.agent_version, caller.credential_id)).fetchone()["first"]
        if first:
            audit(conn, "site.online", actor_type="site", actor_id=caller.site_id, target=caller.site_id,
                  details={"agent_kind": body.agent_kind, "agent_version": body.agent_version})
        conn.execute("DELETE FROM site_heartbeats WHERE site_id = %s AND at < now() - %s",
                     (caller.site_id, HEARTBEAT_HISTORY))
    with connect() as conn:
        consents = conn.execute("SELECT consents FROM sites WHERE id = %s", (caller.site_id,)).fetchone()["consents"]
    # The agent follows consent changes made on the website (sharing the window, training paused)
    answer = {"status": caller.status, "heartbeat_s": heartbeat_seconds(), "consents": consents or {}}
    update = kit_update(body.agent_version)
    if update:
        answer["update"] = update
    return answer


def latest_agent_version() -> str:
    """The newest site kit; set KIT_LATEST_VERSION when a new agent image is published."""
    return os.environ.get("KIT_LATEST_VERSION", "0.3.0")


def kit_update(agent_version: Optional[str]) -> Optional[dict]:
    """Update notice for an older agent (M8): shown on the plant page, sent in the heartbeat answer."""
    latest = latest_agent_version()
    if not agent_version or _version(agent_version) >= _version(latest):
        return None
    return {"version": latest, "how": "in the kit folder: docker compose pull && docker compose up -d "
                                      "(set AGENT_IMAGE in .env if the image name changed)"}


def record_quality(caller: SiteCaller, body) -> dict:
    day = date.fromisoformat(body.day)
    with connect() as conn:
        conn.execute(
            "INSERT INTO site_quality (site_id, day, rows, gaps, flagged, curtailed) VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (site_id, day) DO UPDATE SET rows = EXCLUDED.rows, gaps = EXCLUDED.gaps,"
            " flagged = EXCLUDED.flagged, curtailed = EXCLUDED.curtailed, received_at = now()",
            (caller.site_id, day, body.rows, body.gaps, body.flagged, body.curtailed))
    return {"ok": True}


FORECAST_INPUT_RETENTION = timedelta(days=30)
VALUE_RANGES = {"wind": (0.0, 40.0), "solar": (0.0, 1400.0)}


def record_forecast_input(caller: SiteCaller, body) -> dict:
    """Store the window a consenting site shares for central forecasting (kept 30 days)."""
    try:
        end = datetime.fromisoformat(body.end_hour.replace("Z", "+00:00"))
    except ValueError:
        raise AccountError(422, "end_hour is not an ISO timestamp")
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    end = end.replace(minute=0, second=0, microsecond=0)
    if caller.status != "active":
        raise AccountError(409, f"The site is {caller.status}; forecast inputs are paused")
    lo, hi = VALUE_RANGES[caller.energy_type]
    with connect() as conn:
        consents = conn.execute("SELECT consents FROM sites WHERE id = %s", (caller.site_id,)).fetchone()["consents"] or {}
        if not consents.get("share_forecast_window"):
            raise AccountError(403, "This site did not consent to central forecasting; it forecasts locally (M7)")
        n = len(body.values)
        rows = []
        for i, v in enumerate(body.values):
            ok = v is not None and lo <= v <= hi
            rows.append((caller.site_id, end - timedelta(hours=n - 1 - i), v if ok else None, ok))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO forecast_inputs (site_id, hour, value, ok) VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (site_id, hour) DO UPDATE SET value = EXCLUDED.value, ok = EXCLUDED.ok, received_at = now()",
                rows)
        conn.execute("DELETE FROM forecast_inputs WHERE site_id = %s AND hour < %s",
                     (caller.site_id, end - FORECAST_INPUT_RETENTION))
    return {"stored_hours": n, "window_end": end.isoformat(), "valid_hours": sum(1 for r in rows if r[3])}


def forecast_window(conn, site_id: str, hours: int) -> tuple[Optional[datetime], list]:
    """(end hour, values oldest first, None where missing) of the newest stored window."""
    last = conn.execute("SELECT max(hour) AS h FROM forecast_inputs WHERE site_id = %s AND ok", (site_id,)).fetchone()["h"]
    if last is None:
        return None, []
    rows = conn.execute("SELECT hour, value FROM forecast_inputs WHERE site_id = %s AND ok AND hour > %s AND hour <= %s",
                        (site_id, last - timedelta(hours=hours), last)).fetchall()
    by_hour = {r["hour"]: r["value"] for r in rows}
    return last, [by_hour.get(last - timedelta(hours=hours - 1 - i)) for i in range(hours)]


def central_forecast_request(site_id: str, hours: int) -> dict:
    """What central inference needs for a plant: its stored window plus location, capacity and equipment.
    Raises AccountError 409 (no consent) or 503 (not enough data yet)."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM sites WHERE id = %s", (site_id,)).fetchone()
        consents = row["consents"] or {}
        if not consents.get("share_forecast_window"):
            raise AccountError(409, "This plant forecasts locally and hasn't shared a window (local mode comes with M7)")
        cred = conn.execute("SELECT agent_kind FROM site_credentials WHERE site_id = %s AND revoked_at IS NULL",
                            (site_id,)).fetchone()
        end, values = forecast_window(conn, site_id, hours)
    have = sum(v is not None for v in values)
    if end is None or have < hours * 0.75:
        raise AccountError(503, f"Waiting for the plant's data: {have} of {hours} hours received")
    return {
        "end_hour": end.isoformat(),
        "values": values,
        "lat": row["lat"],
        "lon": row["lon"],
        "capacity_kw": row["capacity_kw"],
        "equipment": row["equipment"] or {},
        # NASA POWER wind is at 50 m; real plants send hub-height values (data contract)
        "measured_at_m": 50.0 if cred and cred["agent_kind"] == "simulated" and row["energy_type"] == "wind" else None,
        "simulated": bool(cred and cred["agent_kind"] == "simulated"),
        "public": bool(consents.get("public_forecasts")),
        "org_id": row["org_id"],
    }


def plant_consents(site_id: str) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT consents FROM sites WHERE id = %s", (site_id,)).fetchone()
    return (row["consents"] or {}) if row else {}


def plant_is_simulated(site_id: str) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT agent_kind FROM site_credentials WHERE site_id = %s AND revoked_at IS NULL",
                           (site_id,)).fetchone()
    return bool(row and row["agent_kind"] == "simulated")


def plant_visibility(site_id: str) -> tuple[Optional[int], bool]:
    """(owner org id, forecasts public?) for access checks."""
    with connect() as conn:
        row = conn.execute("SELECT org_id, consents FROM sites WHERE id = %s", (site_id,)).fetchone()
    return (row["org_id"], bool((row["consents"] or {}).get("public_forecasts"))) if row else (None, False)


# ---------------------------------------------------------------------------
# What the pages show
# ---------------------------------------------------------------------------

def can_train(row: dict, train: Optional[tuple] = None) -> tuple:
    """(can train now, why not). Lab sites: active with a SuperNode (partition id). Plants: the
    result of training_status()."""
    if row["kind"] == "plant":
        return train if train is not None else (False, "No training status")
    if row["status"] != "active":
        return False, f"Site is {row['status']}"
    return (True, None) if row.get("partition_id") is not None else (False, "No SuperNode")


TRAIN_ONLINE_WINDOW = timedelta(minutes=10)
MIN_AGENT_VERSION = (0, 2, 0)


def min_train_hours() -> int:
    """Training history a plant needs before it joins runs (default 90 days)."""
    return int(os.environ.get("TRAIN_MIN_HOURS", str(24 * 90)))


def _version(v: Optional[str]) -> tuple:
    try:
        return tuple(int(x) for x in (v or "0").split("+")[0].split(".")[:3])
    except ValueError:
        return (0,)


def training_status(conn, rows: Iterable[dict]) -> Dict[str, tuple]:
    """Eligibility of plants for a training run (SITE_NETWORK_PLAN.md §7.2): {site id: (ok, why not)}.
    Active, consented to training, Flower node registered, online in the last 10 minutes, agent
    0.2+ and at least TRAIN_MIN_HOURS hours in its training store."""
    rows = [r for r in rows if r["kind"] == "plant"]
    ids = [r["id"] for r in rows]
    if not ids:
        return {}
    creds = {c["site_id"]: c for c in conn.execute(
        "SELECT site_id, flower_node_id, last_seen_at, agent_version FROM site_credentials"
        " WHERE site_id = ANY(%s) AND revoked_at IS NULL", (ids,)).fetchall()}
    beats = {b["site_id"]: b for b in conn.execute(
        "SELECT DISTINCT ON (site_id) site_id, payload FROM site_heartbeats WHERE site_id = ANY(%s)"
        " ORDER BY site_id, at DESC", (ids,)).fetchall()}
    need, now = min_train_hours(), _now()
    out = {}
    for r in rows:
        c, b = creds.get(r["id"]), beats.get(r["id"])
        hours = ((b["payload"] or {}).get("train_hours") if b else None) or 0
        if r["status"] != "active":
            why = f"Plant is {r['status']}"
        elif not (r["consents"] or {}).get("train"):
            why = "No consent to train"
        elif c is None:
            why = "Site kit not installed"
        elif not c["flower_node_id"]:
            why = "Flower node not registered (needs certificate enrollment with node auth)"
        elif c["last_seen_at"] is None or now - c["last_seen_at"] > TRAIN_ONLINE_WINDOW:
            why = "Offline"
        elif _version(c["agent_version"]) < MIN_AGENT_VERSION:
            why = f"Agent {c['agent_version']} is too old (0.2.0+ keeps a training store)"
        elif hours < need:
            why = f"{hours} of {need} hours of training data"
        else:
            why = None
        out[r["id"]] = (why is None, why)
    return out


def connections(conn, rows: Iterable[dict], with_quality: bool = False) -> Dict[str, SiteConnection]:
    rows = list(rows)
    ids = [r["id"] for r in rows if r["kind"] == "plant"]
    hb_s = heartbeat_seconds()
    creds, beats, quality = {}, {}, {}
    if ids:
        for c in conn.execute("SELECT DISTINCT ON (site_id) * FROM site_credentials WHERE site_id = ANY(%s)"
                              " ORDER BY site_id, (revoked_at IS NULL) DESC, created_at DESC", (ids,)).fetchall():
            creds[c["site_id"]] = c
        for b in conn.execute("SELECT DISTINCT ON (site_id) * FROM site_heartbeats WHERE site_id = ANY(%s)"
                              " ORDER BY site_id, at DESC", (ids,)).fetchall():
            beats[b["site_id"]] = b
        if with_quality:
            # The 7 newest days each site reported (sources like NASA POWER lag the wall clock)
            for q in conn.execute("SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY site_id ORDER BY day DESC) AS n"
                                  " FROM site_quality WHERE site_id = ANY(%s)) q WHERE n <= 7 ORDER BY day",
                                  (ids,)).fetchall():
                quality.setdefault(q["site_id"], []).append(
                    {"day": q["day"].isoformat(), "rows": q["rows"], "gaps": q["gaps"],
                     "flagged": q["flagged"], "curtailed": q["curtailed"]})
    out = {}
    for r in rows:
        if r["kind"] != "plant":
            out[r["id"]] = SiteConnection(state="lab", heartbeat_s=hb_s)
            continue
        c, b = creds.get(r["id"]), beats.get(r["id"])
        live = c is not None and c["revoked_at"] is None
        if not live or c["last_seen_at"] is None:
            state = "never" if not live else "offline"
        else:
            state = "online" if _now() - c["last_seen_at"] < timedelta(seconds=3 * hb_s) else "offline"
        out[r["id"]] = SiteConnection(
            state=state,
            last_heartbeat_at=_iso(c["last_seen_at"]) if c else None,
            agent_kind=c["agent_kind"] if c else None,
            agent_version=c["agent_version"] if c else None,
            last_data_hour=_iso(b["last_data_hour"]) if b else None,
            rows_today=b["rows_today"] if b else None,
            gaps_today=b["gaps_today"] if b else None,
            heartbeat_s=hb_s,
            train_hours=(b["payload"] or {}).get("train_hours") if b else None,
            update_available=(kit_update(c["agent_version"]) or {}).get("version") if c else None,
            quality_7d=quality.get(r["id"], []),
        )
    return out


def progress(conn, row: dict) -> SiteProgress:
    events = {}
    for a in conn.execute("SELECT action, min(at) AS at FROM audit_log WHERE target = %s AND action = ANY(%s)"
                          " GROUP BY action", (row["id"], ["site.register", "site.import", "site.approve",
                                                           "site.enroll", "site.online"])).fetchall():
        events[a["action"]] = a["at"]
    if row["kind"] == "builtin":
        t = events.get("site.import") or row["created_at"]
        return SiteProgress(registered_at=_iso(t), approved_at=_iso(t), enrolled_at=_iso(t), online_at=_iso(t))
    # The newest enrollment counts after a re-issue
    latest = conn.execute("SELECT created_at, first_seen_at FROM site_credentials WHERE site_id = %s"
                          " ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
    return SiteProgress(
        registered_at=_iso(events.get("site.register") or row["created_at"]),
        approved_at=_iso(events.get("site.approve")),
        enrolled_at=_iso(latest["created_at"]) if latest else None,
        online_at=_iso(latest["first_seen_at"]) if latest else None,
    )


def kit_state(conn, row: dict) -> SiteKitState:
    if row["kind"] != "plant":
        return SiteKitState()
    live = conn.execute("SELECT 1 FROM site_credentials WHERE site_id = %s AND revoked_at IS NULL", (row["id"],)).fetchone()
    tok = conn.execute("SELECT expires_at FROM enrollment_tokens WHERE site_id = %s AND used_at IS NULL"
                       " AND superseded_at IS NULL AND expires_at > now() ORDER BY created_at DESC LIMIT 1",
                       (row["id"],)).fetchone()
    return SiteKitState(can_download=row["status"] == "approved" and not live, installed=bool(live),
                        token_expires_at=_iso(tok["expires_at"]) if tok else None)


# ---------------------------------------------------------------------------
# Admin overview
# ---------------------------------------------------------------------------

def admin_overview(runs: list) -> dict:
    """Tiles, things that need attention, recent activity. `runs` comes from the run store."""
    with connect() as conn:
        counts = conn.execute(
            "SELECT count(*) FILTER (WHERE status = 'registered') AS waiting,"
            " count(*) FILTER (WHERE status = 'active') AS active FROM sites").fetchone()
        users = conn.execute("SELECT count(*) AS n FROM users WHERE active").fetchone()["n"]
        plants = conn.execute("SELECT * FROM sites WHERE kind = 'plant' AND status IN ('active', 'registered')"
                              " ORDER BY created_at").fetchall()
        conns = connections(conn, plants)
        recent = conn.execute("SELECT a.id, a.at, a.actor_type, a.actor_id, u.name AS actor_name, a.action, a.target,"
                              " a.details FROM audit_log a LEFT JOIN users u"
                              " ON a.actor_type = 'user' AND u.id::text = a.actor_id"
                              " ORDER BY a.id DESC LIMIT 8").fetchall()
    attention = []
    for p in plants:
        c = conns[p["id"]]
        if p["status"] == "registered":
            attention.append({"kind": "approval", "site_id": p["id"],
                              "title": f"{p['name']} is waiting for approval", "since": _iso(p["created_at"]),
                              "link": f"/sites/{p['id']}"})
        elif c.state == "offline":
            attention.append({"kind": "offline", "site_id": p["id"], "title": f"{p['name']} is offline",
                              "since": c.last_heartbeat_at, "link": f"/sites/{p['id']}"})
    week_ago = (_now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in runs:
        if r.status == "failed" and r.created_at >= week_ago:
            attention.append({"kind": "failed_run", "run_id": r.run_id, "title": f"Run {r.run_id} failed",
                              "since": r.created_at, "link": f"/training/{r.run_id}"})
    active_run = next((r for r in runs if r.status in ("queued", "running")), None)
    return {
        "tiles": {
            "waiting": counts["waiting"],
            "active_sites": counts["active"],
            "online_now": sum(1 for c in conns.values() if c.state == "online"),
            "users": users,
            "run": {"run_id": active_run.run_id, "status": active_run.status, "current_round": active_run.current_round,
                    "total_rounds": active_run.total_rounds} if active_run else None,
        },
        "attention": sorted(attention, key=lambda a: a.get("since") or "", reverse=True),
        "recent": [{**r, "at": r["at"].isoformat()} for r in recent],
    }
