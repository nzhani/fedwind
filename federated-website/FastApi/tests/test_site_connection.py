"""Kit, enrollment, heartbeat, quality, re-issue, overview (DEMO_SIMULATION_PLAN.md §2, Tier 1)."""

import io
import json
import zipfile

import psycopg

from app.services.federation_client import get_federation
from app.services.inference_client import get_inference
from tests.conftest import FakeFederation, FakeInference, write_finished_run
from tests.test_accounts import csrf, login
from tests.test_site_registration import WIND, admin, operator


def approved_plant(client):
    """Operator registers Zhanatas, admin approves; returns (site_id, operator csrf)."""
    op = operator(client)
    site_id = client.post("/api/sites", json=WIND, headers=csrf(op)).json()["id"]
    t = admin(client)
    assert client.post(f"/api/admin/sites/{site_id}/approve", json={}, headers=csrf(t)).status_code == 200
    client.cookies.clear()
    _, op = login(client, "op@plant.kz")
    return site_id, op


def kit(client, site_id, token):
    r = client.post(f"/api/my/sites/{site_id}/kit", headers=csrf(token))
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = f"fedwind-site-{site_id}"
    return {n.removeprefix(root + "/"): z.read(n).decode() for n in z.namelist()}


def enroll(client, kit_files, kind="simulated"):
    return client.post("/site-api/enroll", json={"token": kit_files["enrollment.token"].strip(),
                                                 "agent": {"kind": kind, "version": "0.1.0"}})


def beat(client, key, **body):
    return client.post("/site-api/heartbeat", json={"agent_kind": "simulated", "agent_version": "0.1.0", **body},
                       headers={"Authorization": f"Bearer {key}"})


def test_kit_contents_and_who_may_download(db_client):
    op = operator(db_client)
    site_id = db_client.post("/api/sites", json=WIND, headers=csrf(op)).json()["id"]
    assert db_client.post(f"/api/my/sites/{site_id}/kit", headers=csrf(op)).status_code == 409  # not approved yet
    assert db_client.post(f"/api/my/sites/{site_id}/kit").status_code == 403                   # no CSRF token

    t = admin(db_client)
    db_client.post(f"/api/admin/sites/{site_id}/approve", json={}, headers=csrf(t))
    assert db_client.post("/api/my/sites/almaty/kit", headers=csrf(t)).status_code == 409       # lab sites have none
    db_client.cookies.clear()
    other = operator(db_client, email="b@other.kz", org="Other LLP")
    assert db_client.post(f"/api/my/sites/{site_id}/kit", headers=csrf(other)).status_code == 404

    db_client.cookies.clear()
    _, op = login(db_client, "op@plant.kz")
    files = kit(db_client, site_id, op)
    assert {"README.md", "docker-compose.yml", ".env", "enrollment.token", "data/README.md"} <= set(files)
    assert f"SITE_ID={site_id}" in files[".env"] and "DATA_SOURCE=csv_inbox" in files[".env"]
    assert files["enrollment.token"].startswith("fwe_") and "fwe_" not in files[".env"] + files["README.md"]
    detail = db_client.get(f"/api/my/sites/{site_id}").json()
    assert detail["kit"]["can_download"] and detail["kit"]["token_expires_at"]
    assert detail["connection"]["state"] == "never" and detail["can_train"] is False


def test_enroll_once_and_newest_kit_wins(db_client, pg_url):
    site_id, op = approved_plant(db_client)
    first, second = kit(db_client, site_id, op), kit(db_client, site_id, op)
    assert enroll(db_client, first).status_code == 401           # superseded by the second download
    r = enroll(db_client, second)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["site_id"] == site_id and body["site_key"].startswith("fws_")
    assert body["config"]["heartbeat_s"] == 30 and body["config"]["energy_type"] == "wind"
    assert enroll(db_client, second).status_code == 401          # one use only
    assert db_client.post(f"/api/my/sites/{site_id}/kit", headers=csrf(op)).status_code == 409  # installed

    with psycopg.connect(pg_url) as conn:  # only hashes are stored
        stored = [r[0] for r in conn.execute("SELECT secret_hash FROM site_credentials")]
    assert body["site_key"] not in stored and len(stored) == 1

    d = db_client.get(f"/api/my/sites/{site_id}").json()
    assert d["status"] == "active" and d["kit"]["installed"] and d["progress"]["enrolled_at"]
    actions = [h["action"] for h in d["history"]]
    assert "enroll" in actions and actions.count("enroll_failed") == 2   # the superseded kit and the reuse


def test_expired_token_is_refused(db_client, pg_url):
    site_id, op = approved_plant(db_client)
    files = kit(db_client, site_id, op)
    with psycopg.connect(pg_url) as conn:
        conn.execute("UPDATE enrollment_tokens SET expires_at = now() - interval '1 minute'")
    assert enroll(db_client, files).status_code == 401
    assert db_client.post("/site-api/enroll", json={"token": "fwe_" + "x" * 40}).status_code == 401


def test_heartbeat_quality_and_connection(db_client):
    site_id, op = approved_plant(db_client)
    key = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    assert beat(db_client, "fws_wrong").status_code == 401
    assert db_client.post("/site-api/heartbeat", json={}).status_code == 401
    r = beat(db_client, key, last_data_hour="2026-11-19T21:00:00Z", rows_today=21, gaps_today=0)
    assert {k: r.json()[k] for k in ("status", "heartbeat_s")} == {"status": "active", "heartbeat_s": 30}
    assert r.json()["update"]["version"] == "0.3.0"                      # agent 0.1.0 is told to update
    beat(db_client, key)
    q = db_client.post("/site-api/quality", json={"day": "2026-11-19", "rows": 24, "gaps": 0},
                       headers={"Authorization": f"Bearer {key}"})
    assert q.status_code == 200

    d = db_client.get(f"/api/my/sites/{site_id}").json()
    c = d["connection"]
    assert c["state"] == "online" and c["agent_kind"] == "simulated" and c["rows_today"] is None  # latest beat
    assert c["last_data_hour"] is None or c["last_data_hour"].startswith("2026-11-19")
    assert d["progress"]["online_at"]
    assert [h["action"] for h in d["history"]].count("online") == 1      # first heartbeat only
    listed = db_client.get("/api/my/sites").json()["sites"][0]
    assert listed["connection"]["state"] == "online"
    # Online, but not in training until the Flower connection exists (M6)
    assert d["can_train"] is False
    public = {s["id"]: s for s in db_client.get("/api/sites").json()["sites"]}
    assert public[site_id]["can_train"] is False and public["almaty"]["can_train"] is True


def test_suspend_revoke_and_reissue(db_client):
    site_id, op = approved_plant(db_client)
    key = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    db_client.cookies.clear()
    _, t = login(db_client, "admin@fedwind.kz")
    db_client.post(f"/api/admin/sites/{site_id}/suspend", json={"note": "Maintenance"}, headers=csrf(t))
    assert beat(db_client, key).json()["status"] == "suspended"    # the agent learns it is paused

    assert db_client.post(f"/api/admin/sites/{site_id}/reissue-kit", json={}, headers=csrf(t)).status_code == 422
    r = db_client.post(f"/api/admin/sites/{site_id}/reissue-kit", json={"note": "Server replaced"}, headers=csrf(t))
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["kit"]["can_download"]
    assert beat(db_client, key).status_code == 401                    # old key revoked

    db_client.cookies.clear()
    _, op = login(db_client, "op@plant.kz")
    key2 = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    assert beat(db_client, key2).json()["status"] == "active"
    db_client.cookies.clear()
    _, t = login(db_client, "admin@fedwind.kz")
    db_client.post(f"/api/admin/sites/{site_id}/revoke", json={"note": "Left"}, headers=csrf(t))
    assert beat(db_client, key2).status_code == 401


def test_runs_only_use_sites_that_can_train(db_client):
    from main import app

    site_id, op = approved_plant(db_client)
    enroll(db_client, kit(db_client, site_id, op))
    db_client.cookies.clear()
    _, t = login(db_client, "admin@fedwind.kz")
    app.dependency_overrides[get_federation] = lambda: FakeFederation()
    r = db_client.post("/api/runs", data={"config": json.dumps({"sites": ["almaty", site_id], "min_train_clients": 1})},
                       headers=csrf(t))
    assert r.status_code == 422 and f"{site_id}: Flower node not registered" in r.json()["detail"]
    run = db_client.post("/api/runs", data={"config": json.dumps({"rounds": 1})}, headers=csrf(t)).json()
    assert site_id not in run["sites"] and len(run["sites"]) == 5


def test_admin_overview_and_audit_filters(db_client):
    op = operator(db_client)
    waiting = db_client.post("/api/sites", json=WIND, headers=csrf(op)).json()["id"]
    admin(db_client)
    assert db_client.get("/api/admin/overview").status_code == 200
    o = db_client.get("/api/admin/overview").json()
    assert o["tiles"]["waiting"] == 1 and o["tiles"]["active_sites"] == 10 and o["tiles"]["online_now"] == 0
    assert o["attention"][0]["kind"] == "approval" and o["attention"][0]["site_id"] == waiting
    assert o["recent"] and o["tiles"]["run"] is None

    a = db_client.get("/api/admin/audit", params={"action": "site.", "target": waiting}).json()
    assert [e["action"] for e in a["entries"]] == ["site.register"]
    page1 = db_client.get("/api/admin/audit", params={"limit": 3}).json()
    page2 = db_client.get("/api/admin/audit", params={"limit": 3, "before": page1["next_before"]}).json()
    assert len(page1["entries"]) == 3 and page1["next_before"]
    assert page2["entries"][0]["id"] < page1["entries"][-1]["id"]

    db_client.cookies.clear()
    _, op = login(db_client, "op@plant.kz")
    assert db_client.get("/api/admin/overview").status_code == 403


def test_production_refuses_token_mode(db_client, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    assert db_client.post("/site-api/heartbeat", json={}, headers={"Authorization": "Bearer fws_x"}).status_code == 503
    monkeypatch.setenv("SITE_AUTH_MODE", "mtls")
    monkeypatch.setenv("GATEWAY_SHARED_SECRET", "s3cret")
    assert db_client.post("/site-api/heartbeat", json={}, headers={"X-Site-Id": "x"}).status_code == 401
    assert db_client.post("/site-api/enroll", json={"token": "fwe_" + "x" * 40}).status_code == 422  # mtls needs a CSR


def window(client, key, n=336, end="2026-11-17T23:00:00Z"):
    return client.post("/site-api/forecast-input", json={"end_hour": end, "values": [6.0] * n},
                       headers={"Authorization": f"Bearer {key}"})


def test_forecast_input_needs_consent_and_an_active_site(db_client):
    from tests.test_site_registration import SOLAR

    site_id, op = approved_plant(db_client)                       # WIND consents to central forecasting
    key = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    r = window(db_client, key)
    assert r.status_code == 200 and r.json() == {"stored_hours": 336, "window_end": "2026-11-17T23:00:00+00:00",
                                                 "valid_hours": 336}
    bad = db_client.post("/site-api/forecast-input", json={"end_hour": "2026-11-17T23:00:00Z", "values": [99.0, 5.0]},
                         headers={"Authorization": f"Bearer {key}"})
    assert bad.json()["valid_hours"] == 1                           # 99 m/s is implausible, stored as missing

    solar_id = db_client.post("/api/sites", json=SOLAR, headers=csrf(op)).json()["id"]  # no central consent
    db_client.cookies.clear()
    _, t = login(db_client, "admin@fedwind.kz")
    db_client.post(f"/api/admin/sites/{solar_id}/approve", json={}, headers=csrf(t))
    db_client.post(f"/api/admin/sites/{site_id}/suspend", json={"note": "Maintenance"}, headers=csrf(t))
    assert window(db_client, key).status_code == 409                # suspended: paused
    db_client.cookies.clear()
    _, op = login(db_client, "op@plant.kz")
    skey = enroll(db_client, kit(db_client, solar_id, op)).json()["site_key"]
    r = db_client.post("/site-api/forecast-input", json={"end_hour": "2026-11-17T23:00:00Z", "values": [300.0]},
                       headers={"Authorization": f"Bearer {skey}"})
    assert r.status_code == 403 and "consent" in r.json()["detail"]


def test_plant_forecast_from_the_newest_model_with_power(db_client, data_dir):
    from main import app

    site_id, op = approved_plant(db_client)
    key = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    fake = FakeInference()
    app.dependency_overrides[get_inference] = lambda: fake
    params = {"site": site_id, "horizon": 72}

    db_client.cookies.clear()
    _, t = login(db_client, "admin@fedwind.kz")
    write_finished_run(data_dir)
    assert db_client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"},
                          headers=csrf(t)).status_code == 200
    assert db_client.get("/api/forecast", params=params).status_code == 503        # no data shared yet
    window(db_client, key)

    r = db_client.get("/api/forecast", params=params)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["source"] == "central" and b["simulated"] is True and b["power_basis"] == "plant"
    assert b["capacity_kw"] == 100000 and b["forecast"][0]["power_kw"] == 50000.0
    assert b["forecast"][0]["capacity_factor"] == 0.5
    m = b["model"]
    assert m["run_id"] == "wind-fedavg-h72-20261101T000000Z" and m["promoted_by"] == "Ada Admin"
    assert m["sites"] == ["almaty", "aktau"]
    sent = fake.window_calls[-1]
    assert len(sent["values"]) == 336 and sent["measured_at_m"] == 50.0 and sent["equipment"]["turbine_count"] == 40

    # Private plant: the owner sees it, others get "unknown site"
    db_client.cookies.clear()
    assert db_client.get("/api/forecast", params=params).status_code == 422
    operator(db_client, email="b@other.kz", org="Other LLP")
    assert db_client.get("/api/forecast", params=params).status_code == 422
    db_client.cookies.clear()
    login(db_client, "op@plant.kz")
    assert db_client.get("/api/forecast", params=params).status_code == 200


def test_lab_site_forecast_gets_reference_power(client, data_dir):
    from main import app

    write_finished_run(data_dir)
    client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"})
    fake = FakeInference()
    app.dependency_overrides[get_inference] = lambda: fake
    b = client.get("/api/forecast", params={"site": "aktau", "horizon": 72}).json()
    assert b["power_basis"] == "reference" and b["capacity_kw"] == 2000 and b["source"] == "site_inference"
    assert b["model"]["run_id"] == "wind-fedavg-h72-20261101T000000Z" and b["model"]["sites"] == ["almaty", "aktau"]


def test_public_list_says_whose_forecasts_anyone_may_see(db_client):
    site_id, op = approved_plant(db_client)
    enroll(db_client, kit(db_client, site_id, op))                      # active: now in the public list
    sites = {s["id"]: s for s in db_client.get("/api/sites").json()["sites"]}
    assert sites["almaty"]["forecast_public"] is True
    assert sites[site_id]["forecast_public"] is False                    # WIND did not consent to public forecasts


def test_kit_connects_on_its_own(db_client, monkeypatch):
    """A kit started with plain `docker compose up -d` reaches a server on the same computer, and uses
    published images when the server names them."""
    site_id, op = approved_plant(db_client)
    files = kit(db_client, site_id, op)
    assert "SITE_API_URL=http://host.docker.internal:8001" in files[".env"]          # not localhost
    assert "host.docker.internal:host-gateway" in files["docker-compose.yml"]
    assert "AGENT_IMAGE=fedwind-site-agent:0.3.0" in files[".env"] and "#   nasa_power" in files[".env"]

    monkeypatch.setenv("SITE_API_PUBLIC_URL", "https://arqauquat.example.kz")
    monkeypatch.setenv("KIT_AGENT_IMAGE", "ghcr.io/team/arqauquat-site-agent:0.3.0")
    files = kit(db_client, site_id, op)
    assert "SITE_API_URL=https://arqauquat.example.kz" in files[".env"]
    assert "AGENT_IMAGE=ghcr.io/team/arqauquat-site-agent:0.3.0" in files[".env"]
