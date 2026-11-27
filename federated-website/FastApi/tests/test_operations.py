"""Operations and hardening (SITE_NETWORK_PLAN.md M8): certificate renewal, kit update notices, rate
limits, data retention, the health report."""

import json
from datetime import datetime, timezone

import psycopg
from cryptography import x509

from app import ratelimit
from app.services import retention
from tests.test_accounts import csrf, login
from tests.test_site_connection import approved_plant, kit
from tests.test_site_pki import SECRET, enroll, flower_key, gateway_beat, make_csr


def test_certificate_renewal(db_client, pg_url, monkeypatch):
    monkeypatch.setenv("SITE_AUTH_MODE", "mtls")
    monkeypatch.setenv("GATEWAY_SHARED_SECRET", SECRET)
    site_id, op = approved_plant(db_client)
    body = enroll(db_client, kit(db_client, site_id, op), make_csr(site_id), flower_key()).json()
    old = format(x509.load_pem_x509_certificate(body["certificate"].encode()).serial_number, "X")

    def renew(serial, csr):
        return db_client.post("/site-api/renew", json={"csr": csr},
                              headers={"X-Gateway-Secret": SECRET, "X-Site-Id": site_id, "X-Client-Serial": serial})

    assert renew(old, make_csr("someone-else")).status_code == 422
    r = renew(old, make_csr(site_id))
    assert r.status_code == 200, r.text
    new = format(x509.load_pem_x509_certificate(r.json()["certificate"].encode()).serial_number, "X")
    assert new != old and r.json()["ca_certificate"]
    assert gateway_beat(db_client, site_id, new).status_code == 200
    assert gateway_beat(db_client, site_id, old).status_code == 401              # the old one is replaced
    assert renew(old, make_csr(site_id)).status_code == 401
    with psycopg.connect(pg_url) as conn:
        assert conn.execute("SELECT count(*) FROM audit_log WHERE action = 'site.renew'").fetchone()[0] == 1


def test_older_kits_are_told_to_update(db_client):
    site_id, op = approved_plant(db_client)
    key = enroll(db_client, kit(db_client, site_id, op), make_csr(site_id), flower_key()).json()["site_key"]
    beat = lambda v: db_client.post("/site-api/heartbeat", json={"agent_kind": "kit", "agent_version": v},
                                    headers={"Authorization": f"Bearer {key}"}).json()
    assert beat("0.2.0")["update"]["version"] == "0.3.0"
    assert db_client.get(f"/api/my/sites/{site_id}").json()["connection"]["update_available"] == "0.3.0"
    assert "update" not in beat("0.3.0")
    assert db_client.get(f"/api/my/sites/{site_id}").json()["connection"]["update_available"] is None


def test_rate_limits(db_client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT", "on")
    monkeypatch.setenv("RATE_LIMITS", "auth=3/60")
    ratelimit.limiter.hits.clear()
    codes = [db_client.post("/api/auth/login", json={"email": "x@y.kz", "password": "wrong-pass-123"}).status_code
             for _ in range(4)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429
    r = db_client.post("/api/auth/login", json={"email": "x@y.kz", "password": "wrong-pass-123"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert db_client.get("/api/sites").status_code == 200                       # other buckets unaffected
    assert ratelimit.limiter.check("t", "ip", 2, 10, now=0) is None
    assert ratelimit.limiter.check("t", "ip", 2, 10, now=1) is None
    assert ratelimit.limiter.check("t", "ip", 2, 10, now=2) == 9
    assert ratelimit.limiter.check("t", "ip", 2, 10, now=11) is None              # the window moved on
    ratelimit.limiter.hits.clear()


def test_retention_deletes_only_what_is_old(db_client, pg_url, monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "30")
    with psycopg.connect(pg_url) as conn:
        conn.execute("INSERT INTO audit_log (actor_type, action, at) VALUES ('system', 'old.thing', now() - interval '40 days'),"
                     " ('system', 'recent.thing', now() - interval '5 days')")
    out = retention.cleanup()
    assert out == {"audit_log": 1}
    with psycopg.connect(pg_url) as conn:
        actions = {a for (a,) in conn.execute("SELECT action FROM audit_log")}
    assert "old.thing" not in actions and {"recent.thing", "retention.cleanup"} <= actions
    assert retention.cleanup() == {}


def test_health_report(db_client, data_dir):
    from tests.test_site_registration import admin

    assert db_client.get("/api/admin/health").status_code == 401
    admin(db_client)
    r = db_client.get("/api/admin/health")
    assert r.status_code == 200
    checks = {c["name"]: c for c in r.json()["checks"]}
    assert checks["Database"]["status"] == "ok"
    assert checks["Backups"]["status"] == "warn" and checks["Promoted models"]["status"] == "warn"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "backups-status.json").write_text(json.dumps({
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "size_bytes": 5e7, "encrypted": True}))
    checks = {c["name"]: c for c in db_client.get("/api/admin/health").json()["checks"]}
    assert checks["Backups"]["status"] == "ok" and "50 MB" in checks["Backups"]["detail"]
    _, token = login(db_client, "admin@fedwind.kz")
    assert csrf(token)
