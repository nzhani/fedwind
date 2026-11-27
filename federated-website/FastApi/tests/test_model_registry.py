"""Model registry, promotion gates, stored and local forecasts (SITE_NETWORK_PLAN.md M7)."""

import json

import psycopg

from app.services import forecast_store, model_registry
from app.services.inference_client import get_inference
from app.settings import get_settings
from tests.conftest import FakeInference, write_finished_run
from tests.test_accounts import csrf, login
from tests.test_site_connection import enroll, kit, window
from tests.test_site_registration import WIND


def finished(data_dir, run_id, skill=0.2, maes=None, data_percent=None, payload=b"weights"):
    """A finished wind 72 h run with chosen metrics."""
    folder = write_finished_run(data_dir, run_id)
    (folder / "checkpoints" / "best.pt").write_bytes(payload)
    maes = maes or {"almaty": 1.0, "aktau": 1.2}
    (folder / "result.json").write_text(json.dumps({
        "run_id": run_id, "status": "done", "best_round": 2, "horizon": 72, "rounds_completed": 2,
        "metrics": {"real": {"mae": 1.1, "skill_vs_persistence": skill},
                    "per_site": {s: {"mae": v} for s, v in maes.items()}},
        "model": {"checkpoint": "checkpoints/best.pt"}}))
    if data_percent is not None:
        cfg = folder / "config.yaml"
        cfg.write_text(cfg.read_text() + f"data_percent: {data_percent}\n")
    return run_id


def admin_token(client):
    from tests.test_site_registration import admin

    return admin(client)


def test_promoting_runs_creates_versions_and_rollback(db_client, data_dir):
    t = admin_token(db_client)
    a = finished(data_dir, "wind-fedavg-h72-20261101T000000Z", payload=b"A")
    b = finished(data_dir, "wind-fedavg-h72-20261102T000000Z", payload=b"B")
    assert db_client.post("/api/models/promote", json={"run_id": a}, headers=csrf(t)).json()["version"] == 1
    m2 = db_client.post("/api/models/promote", json={"run_id": b}, headers=csrf(t)).json()
    assert m2["version"] == 2 and m2["status"] == "promoted" and len(m2["sha256"]) == 64
    models = get_settings().models_dir / "wind" / "h72"
    assert (models / "v1.pt").read_bytes() == b"A" and (models / "current.pt").read_bytes() == b"B"

    versions = db_client.get("/api/models/versions", headers=csrf(t)).json()
    assert [(v["version"], v["status"]) for v in versions] == [(2, "promoted"), (1, "retired")]
    served = db_client.get("/api/models").json()["models"]
    assert len(served) == 1 and served[0]["version"] == 2 and served[0]["model_path"] == "wind/h72/v2.pt"

    # Rollback = promote the old version again
    v1 = next(v for v in versions if v["version"] == 1)
    r = db_client.post(f"/api/models/versions/{v1['id']}/promote", json={"note": "v2 looked wrong"}, headers=csrf(t))
    assert r.status_code == 200 and r.json()["status"] == "promoted"
    assert (models / "current.pt").read_bytes() == b"A"
    db_client.cookies.clear()
    assert db_client.get("/api/models/versions").status_code == 401                 # admin only


def test_gates_and_automatic_promotion_of_scheduled_runs(db_client, data_dir, pg_url, monkeypatch):
    t = admin_token(db_client)
    base = finished(data_dir, "wind-fedavg-h72-20261101T000000Z", skill=0.10)
    db_client.post("/api/models/promote", json={"run_id": base}, headers=csrf(t))

    good = finished(data_dir, "wind-fedavg-h72-20261108T000000Z", skill=0.15, maes={"almaty": 1.05, "aktau": 1.1})
    worse_site = finished(data_dir, "wind-fedavg-h72-20261109T000000Z", skill=0.2, maes={"almaty": 1.3, "aktau": 1.0})
    manual = finished(data_dir, "wind-fedavg-h72-20261110T000000Z", skill=0.3)
    small = finished(data_dir, "wind-fedavg-h72-20261111T000000Z", skill=0.4, data_percent=10)
    with psycopg.connect(pg_url) as conn:
        for i, run_id in enumerate((good, worse_site, small)):
            conn.execute("INSERT INTO training_schedule (slot, energy_type, run_id) VALUES (%s, 'wind', %s)",
                         (f"wind@slot{i}", run_id))

    events = {e["run_id"]: e for e in model_registry.sync(get_settings())}
    assert events[worse_site]["status"] == "candidate" and not events[worse_site]["gates"]      # almaty +30 %
    assert events[manual]["status"] == "candidate" and events[manual]["gates"]                  # manual: never automatic
    assert events[small]["status"] == "candidate" and not events[small]["gates"]                # 10 % of the data
    assert model_registry.sync(get_settings()) == []                                           # nothing new

    # good was registered before the others; its gates compared with v1 and it was promoted
    assert events[good]["status"] == "promoted"
    current = model_registry.current_model(get_settings(), "wind", 72)
    assert current.run_id == good and current.veto_until and current.promoted_by.startswith("automatic")
    gates = {g["name"]: g["passed"] for g in current.gates["gates"]}
    assert gates == {"Trained on all data": True, "Beats persistence": True, "Beats v1": True,
                     "No site more than 10% worse": True}

    # Veto: back to v1, the vetoed version is rejected
    assert db_client.post(f"/api/models/versions/{current.id}/veto", json={}, headers=csrf(t)).status_code == 422
    r = db_client.post(f"/api/models/versions/{current.id}/veto", json={"note": "odd forecasts at aktau"},
                       headers=csrf(t))
    assert r.status_code == 200 and r.json()["run_id"] == base
    assert model_registry.get_version(current.id).status == "rejected"
    assert db_client.post(f"/api/models/versions/{r.json()['id']}/veto", json={"note": "x"},
                          headers=csrf(t)).status_code == 409                             # manual promotion

    monkeypatch.setenv("AUTO_PROMOTE", "off")
    later = finished(data_dir, "wind-fedavg-h72-20261115T000000Z", skill=0.5)
    with psycopg.connect(pg_url) as conn:
        conn.execute("INSERT INTO training_schedule (slot, energy_type, run_id) VALUES ('wind@x', 'wind', %s)", (later,))
    assert model_registry.sync(get_settings())[0]["status"] == "candidate"


def test_models_promoted_before_the_registry_are_imported(db_client, data_dir, monkeypatch):
    import os

    url = os.environ["DATABASE_URL"]
    monkeypatch.delenv("DATABASE_URL")
    finished(data_dir, "wind-fedavg-h72-20261101T000000Z")
    from app.services.run_store import get_run

    model_registry.promote(get_settings(), get_run(get_settings(), "wind-fedavg-h72-20261101T000000Z"), "old admin")
    monkeypatch.setenv("DATABASE_URL", url)
    m = model_registry.current_model(get_settings(), "wind", 72)
    assert m.version == 1 and m.origin == "import" and m.promoted_by == "old admin"


def plant_with_model(db_client, data_dir, body=WIND):
    from main import app
    from tests.test_site_registration import operator, admin

    op = operator(db_client)
    site_id = db_client.post("/api/sites", json=body, headers=csrf(op)).json()["id"]
    t = admin(db_client)
    db_client.post(f"/api/admin/sites/{site_id}/approve", json={}, headers=csrf(t))
    finished(data_dir, "wind-fedavg-h72-20261101T000000Z")
    db_client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"}, headers=csrf(t))
    db_client.cookies.clear()
    _, op = login(db_client, "op@plant.kz")
    key = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    fake = FakeInference()
    app.dependency_overrides[get_inference] = lambda: fake
    return site_id, key, fake


def test_plant_forecasts_are_stored_and_refreshed(db_client, data_dir):
    site_id, key, fake = plant_with_model(db_client, data_dir)
    window(db_client, key, end="2026-11-17T23:00:00Z")
    params = {"site": site_id, "horizon": 72}

    first = db_client.get("/api/forecast", params=params).json()
    assert first["source"] == "central" and first["stored_at"] and first["model"]["version"] == 1
    assert db_client.get("/api/forecast", params=params).json()["stored_at"] == first["stored_at"]
    assert len(fake.window_calls) == 1                                       # the second request read the stored one
    assert forecast_store.refresh_due(get_settings(), fake) == []            # nothing new

    window(db_client, key, end="2026-11-18T05:00:00Z")                      # newer data from the plant
    made = forecast_store.refresh_due(get_settings(), fake)
    assert [m["site"] for m in made] == [site_id] and len(fake.window_calls) == 2
    assert db_client.get("/api/forecast", params=params).json()["as_of"].startswith("2026-11-18T05")


def test_local_mode_download_and_forecast(db_client, data_dir):
    body = {**WIND, "consents": {"train": True, "share_forecast_window": False, "public_forecasts": False}}
    site_id, key, fake = plant_with_model(db_client, data_dir, body)
    auth = {"Authorization": f"Bearer {key}"}
    params = {"site": site_id, "horizon": 72}
    assert db_client.get("/api/forecast", params=params).status_code == 409          # nothing sent yet

    cur = db_client.get("/site-api/models/current", params={"horizon": 72}, headers=auth).json()
    assert cur["version"] == 1 and cur["download"] == f"/site-api/models/{cur['id']}/file"
    f = db_client.get(cur["download"], headers=auth)
    assert f.status_code == 200 and f.content == b"weights" and f.headers["x-model-sha256"] == cur["sha256"]
    assert db_client.get(cur["download"]).status_code == 401
    assert db_client.get("/site-api/models/current", params={"horizon": 1}, headers=auth).status_code == 404

    from datetime import datetime, timedelta, timezone

    issued = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:00:00Z")
    send = lambda **kw: db_client.post("/site-api/forecasts", headers=auth, json={
        "model_version_id": cur["id"], "horizon": 72, "issued_at": issued, "values": [7.0] * 72,
        "power_kw": [60000.0] + [200000.0] * 71, **kw})
    assert send(values=[7.0] * 10).status_code == 422                                  # one value per hour
    assert send(values=[99.0] * 72).status_code == 422                                 # implausible wind speed
    assert send(issued_at="2020-01-01T00:00:00Z").status_code == 422
    r = send()
    assert r.status_code == 200 and r.json()["stored"] == 72

    b = db_client.get("/api/forecast", params=params).json()
    assert b["source"] == "local" and b["actual"] == [] and len(fake.window_calls) == 0
    assert b["forecast"][0]["power_kw"] == 60000.0 and b["forecast"][1]["power_kw"] == 100000.0   # capped at capacity
