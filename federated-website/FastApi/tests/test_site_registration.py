"""Site registry in Postgres: registration, visibility, approval lifecycle (SITE_NETWORK_PLAN.md M2)."""

import copy
import json

from app.services.federation_client import get_federation
from tests.conftest import FakeFederation
from tests.test_accounts import PW, csrf, login, make_admin, register

WIND = {
    "name": "Zhanatas Wind",
    "energy_type": "wind",
    "lat": 43.57,
    "lon": 69.75,
    "timezone": "Asia/Almaty",
    "capacity_kw": 100000,
    "equipment": {"turbine_model": "Envision EN-156", "turbine_count": 40, "hub_height_m": 100, "rated_power_kw": 2500},
    "data_source": "csv",
    "contact": "+7 700 000 0000",
    "consents": {"train": True, "share_forecast_window": True, "public_forecasts": False},
}
SOLAR = {
    "name": "Сарань Күн",
    "energy_type": "solar",
    "lat": 49.79,
    "lon": 72.84,
    "capacity_kw": 100000,
    "equipment": {"module_type": "mono-Si", "tilt_deg": 35, "azimuth_deg": 180, "tracking": "fixed"},
    "contact": "ops@saran.kz",
    "consents": {"train": True},
}


def operator(client, email="op@plant.kz", org="Plant One LLP"):
    client.cookies.clear()
    return register(client, email=email, org=org).json()["csrf_token"]


def admin(client):
    client.cookies.clear()
    make_admin()
    return login(client, "admin@fedwind.kz")[1]


def test_builtin_sites_are_imported_and_public_list_shows_only_active(db_client):
    sites = db_client.get("/api/sites").json()["sites"]
    assert len(sites) == 10 and all(s["kind"] == "builtin" and s["status"] == "active" for s in sites)
    assert sorted(s["partition_id"] for s in sites) == list(range(10))
    # A registered plant stays private until it is active
    token = operator(db_client)
    assert db_client.post("/api/sites", json=WIND, headers=csrf(token)).status_code == 201
    assert len(db_client.get("/api/sites").json()["sites"]) == 10


def test_operator_registers_sites_with_validation(db_client):
    token = operator(db_client)
    r = db_client.post("/api/sites", json=WIND, headers=csrf(token))
    assert r.status_code == 201, r.text
    site = r.json()
    assert site["id"].startswith("zhanatas-wind-") and site["status"] == "registered" and site["kind"] == "plant"
    assert site["org_name"] == "Plant One LLP" and site["equipment"]["turbine_count"] == 40
    assert [h["action"] for h in site["history"]] == ["register"]
    # Cyrillic/Kazakh names get a Latin id; defaults fill in
    s = db_client.post("/api/sites", json=SOLAR, headers=csrf(token)).json()
    assert s["id"].startswith("saran-kun-") and s["timezone"] == "Asia/Almaty" and s["data_source"] == "csv"
    assert db_client.post("/api/sites", json=WIND, headers=csrf(token)).status_code == 409  # same name, same org

    bad = []
    for patch in (
        {"lat": 60.0},                                              # outside Kazakhstan
        {"lon": 40.0},
        {"capacity_kw": 0},
        {"timezone": "Europe/Moscow"},
        {"consents": {"train": False}},                             # training consent is required
        {"equipment": {"turbine_model": "x"}},                      # wind fields missing
        {"equipment": {**WIND["equipment"], "tilt_deg": 30}},       # solar field on a wind site
        {"energy_type": "hydro"},
    ):
        body = {**copy.deepcopy(WIND), "name": f"Bad {len(bad)}", **patch}
        bad.append(db_client.post("/api/sites", json=body, headers=csrf(token)).status_code)
    assert bad == [422] * len(bad)


def test_who_may_register_and_see(db_client):
    assert db_client.post("/api/sites", json=WIND).status_code == 401
    token_a = operator(db_client)
    site_id = db_client.post("/api/sites", json=WIND, headers=csrf(token_a)).json()["id"]
    assert [s["id"] for s in db_client.get("/api/my/sites").json()["sites"]] == [site_id]

    # Another organization can't see or edit it, and can't tell it exists
    token_b = operator(db_client, email="b@other.kz", org="Other LLP")
    assert db_client.get("/api/my/sites").json()["sites"] == []
    assert db_client.get(f"/api/my/sites/{site_id}").status_code == 404
    assert db_client.put(f"/api/my/sites/{site_id}", json=WIND, headers=csrf(token_b)).status_code == 404

    # Admins can't register plants for someone, viewers can't register at all
    token = admin(db_client)
    assert db_client.post("/api/sites", json=WIND, headers=csrf(token)).status_code == 403
    assert len(db_client.get("/api/my/sites").json()["sites"]) == 11  # 10 builtin + 1 plant
    r = db_client.post("/api/admin/users", json={"email": "v@nu.kz", "password": PW, "name": "V", "role": "viewer"},
                       headers=csrf(token))
    assert r.status_code == 201
    db_client.cookies.clear()
    _, vtoken = login(db_client, "v@nu.kz")
    assert db_client.post("/api/sites", json=WIND, headers=csrf(vtoken)).status_code == 403


def test_edit_only_while_waiting_for_approval(db_client):
    token = operator(db_client)
    site_id = db_client.post("/api/sites", json=WIND, headers=csrf(token)).json()["id"]
    r = db_client.put(f"/api/my/sites/{site_id}", json={**WIND, "capacity_kw": 120000}, headers=csrf(token))
    assert r.status_code == 200 and r.json()["capacity_kw"] == 120000
    assert db_client.put(f"/api/my/sites/{site_id}", json={**SOLAR}, headers=csrf(token)).status_code == 422

    atoken = admin(db_client)
    assert db_client.post(f"/api/admin/sites/{site_id}/approve", json={}, headers=csrf(atoken)).status_code == 200
    db_client.cookies.clear()
    _, token = login(db_client, "op@plant.kz")
    assert db_client.put(f"/api/my/sites/{site_id}", json=WIND, headers=csrf(token)).status_code == 409


def test_approval_lifecycle_and_history(db_client):
    token = operator(db_client)
    a = db_client.post("/api/sites", json=WIND, headers=csrf(token)).json()["id"]
    b = db_client.post("/api/sites", json=SOLAR, headers=csrf(token)).json()["id"]
    # Operators can't decide
    assert db_client.post(f"/api/admin/sites/{a}/approve", json={}, headers=csrf(token)).status_code == 403

    t = admin(db_client)
    post = lambda sid, action, note=None: db_client.post(  # noqa: E731
        f"/api/admin/sites/{sid}/{action}", json={"note": note} if note else {}, headers=csrf(t))
    assert post(a, "reject").status_code == 422                           # reject needs a reason
    assert post(a, "resume").status_code == 409                           # not suspended
    assert post(a, "explode").status_code == 404
    r = post(a, "approve", "Welcome")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert post(a, "approve").status_code == 409                          # once
    r = post(b, "reject", "Coordinates are in the sea")
    assert r.json()["status"] == "rejected" and r.json()["decision_note"] == "Coordinates are in the sea"
    assert post(a, "revoke", "Plant sold").json()["status"] == "revoked"

    # The operator sees the decisions and who made them
    db_client.cookies.clear()
    login(db_client, "op@plant.kz")
    hist = db_client.get(f"/api/my/sites/{a}").json()["history"]
    assert [h["action"] for h in hist] == ["register", "approve", "revoke"]
    assert hist[1]["actor"] == "Ada Admin" and hist[2]["note"] == "Plant sold"


def test_suspended_site_leaves_runs_and_forecasts(db_client):
    from main import app

    t = admin(db_client)
    assert db_client.post("/api/admin/sites/aktau/suspend", json={}, headers=csrf(t)).status_code == 422  # needs a note
    r = db_client.post("/api/admin/sites/aktau/suspend", json={"note": "Maintenance"}, headers=csrf(t))
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert "aktau" not in [s["id"] for s in db_client.get("/api/sites").json()["sites"]]
    assert db_client.get("/api/forecast", params={"site": "aktau", "horizon": 72}).status_code == 422

    app.dependency_overrides[get_federation] = lambda: FakeFederation()
    run = db_client.post("/api/runs", data={"config": json.dumps({"rounds": 1})}, headers=csrf(t)).json()
    assert run["sites"] == ["almaty", "zhezkazgan", "taraz", "aktobe"]
    r = db_client.post("/api/runs", data={"config": json.dumps({"sites": ["aktau"], "min_train_clients": 1})},
                       headers=csrf(t))
    assert r.status_code == 422 and "aktau" in r.json()["detail"]  # checked before the busy lock

    assert db_client.post("/api/admin/sites/aktau/resume", json={}, headers=csrf(t)).json()["status"] == "active"
