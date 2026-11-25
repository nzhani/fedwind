"""Accounts, sessions, roles and CSRF against a real Postgres (SITE_NETWORK_PLAN.md M1)."""

import json

import pytest

from app.services.federation_client import get_federation
from tests.conftest import FakeFederation, write_finished_run

PW = "correct horse battery"


def register(client, email="op@plant.kz", org="Plant One LLP", password=PW, name="Op Erator"):
    return client.post("/api/auth/register", json={"email": email, "password": password, "name": name,
                                                    "organization": org})


def login(client, email, password=PW):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r, (r.json().get("csrf_token") if r.status_code == 200 else None)


def make_admin(email="admin@fedwind.kz"):
    from app.services import accounts

    return accounts.create_user(email, PW, "Ada Admin", "admin")


def csrf(token):
    return {"X-CSRF-Token": token}


# --- registration and login ---------------------------------------------------------------------

def test_register_logs_in_as_operator_with_new_organization(db_client):
    r = register(db_client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == "operator" and body["user"]["organization"]["name"] == "Plant One LLP"
    cookie = r.headers["set-cookie"]
    assert "fedwind_session=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    me = db_client.get("/api/auth/me").json()
    assert me["user"]["email"] == "op@plant.kz" and me["csrf_token"] == body["csrf_token"]


def test_registration_rules(db_client, monkeypatch):
    assert register(db_client).status_code == 201
    db_client.cookies.clear()
    assert register(db_client, org="Other LLP").status_code == 409            # same email
    assert register(db_client, email="b@plant.kz").status_code == 409         # same organization (any case)
    assert register(db_client, email="c@plant.kz", org="plant one llp").status_code == 409
    assert register(db_client, email="d@plant.kz", org="D LLP", password="short").status_code == 422
    assert register(db_client, email="not-an-email", org="E LLP").status_code == 422
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    assert register(db_client, email="f@plant.kz", org="F LLP").status_code == 403


def test_login_errors_do_not_reveal_which_part_was_wrong(db_client):
    register(db_client)
    db_client.cookies.clear()
    wrong_pw, _ = login(db_client, "op@plant.kz", "wrong password!!")
    unknown, _ = login(db_client, "nobody@plant.kz")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()
    ok, token = login(db_client, "OP@Plant.kz")                                 # email is case-insensitive
    assert ok.status_code == 200 and token


def test_failed_logins_are_throttled(db_client):
    register(db_client)
    db_client.cookies.clear()
    for _ in range(10):
        assert login(db_client, "op@plant.kz", "wrong password!!")[0].status_code == 401
    r, _ = login(db_client, "op@plant.kz")                                      # even the right password
    assert r.status_code == 429


def test_secrets_are_not_stored_in_clear(db_client, pg_url):
    import psycopg

    r = register(db_client)
    token = r.cookies.get("fedwind_session")
    with psycopg.connect(pg_url) as conn:
        pw_hash = conn.execute("SELECT password_hash FROM users").fetchone()[0]
        session_ids = [row[0] for row in conn.execute("SELECT id_hash FROM sessions")]
    assert pw_hash.startswith("$argon2id$") and PW not in pw_hash
    assert token and token not in session_ids and len(session_ids) == 1


# --- sessions and CSRF ----------------------------------------------------------------------------

def test_logout_needs_csrf_and_ends_the_session(db_client):
    token = register(db_client).json()["csrf_token"]
    assert db_client.post("/api/auth/logout").status_code == 403
    assert db_client.post("/api/auth/logout", headers=csrf("wrong")).status_code == 403
    assert db_client.post("/api/auth/logout", headers=csrf(token)).status_code == 200
    assert db_client.get("/api/auth/me").status_code == 401


def test_anonymous_is_401(db_client):
    assert db_client.get("/api/auth/me").status_code == 401
    assert db_client.get("/api/admin/users").status_code == 401
    assert db_client.post("/api/runs", data={"config": "{}"}).status_code == 401
    assert db_client.post("/api/models/promote", json={"run_id": "x"}).status_code == 401
    assert db_client.delete("/api/feedback/abc").status_code == 401
    assert db_client.post("/api/feedback/telegram/set-webhook", json={"public_base_url": "https://x"}).status_code == 401


# --- roles ------------------------------------------------------------------------------------------

def test_operator_cannot_do_admin_actions(db_client, data_dir):
    token = register(db_client).json()["csrf_token"]
    write_finished_run(data_dir)
    h = csrf(token)
    assert db_client.post("/api/runs", data={"config": "{}"}, headers=h).status_code == 403
    assert db_client.post("/api/runs/x/stop", headers=h).status_code == 403
    assert db_client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"},
                          headers=h).status_code == 403
    assert db_client.get("/api/admin/users").status_code == 403
    assert db_client.get("/api/admin/audit").status_code == 403
    assert db_client.delete("/api/feedback/abc", headers=h).status_code == 403
    # Reading stays open
    assert db_client.get("/api/runs").status_code == 200
    assert db_client.get("/api/sites").status_code == 200


def test_admin_runs_promotes_and_everything_is_audited(db_client, data_dir):
    from main import app

    make_admin()
    _, token = login(db_client, "admin@fedwind.kz")
    app.dependency_overrides[get_federation] = lambda: FakeFederation()
    r = db_client.post("/api/runs", data={"config": json.dumps({"rounds": 2})}, headers=csrf(token))
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]
    assert db_client.post(f"/api/runs/{run_id}/stop", headers=csrf(token)).status_code == 200
    write_finished_run(data_dir)
    assert db_client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"},
                          headers=csrf(token)).status_code == 200
    actions = [e["action"] for e in db_client.get("/api/admin/audit").json()["entries"]]
    assert {"login.success", "run.start", "run.stop", "model.promote"} <= set(actions)


def test_admin_manages_users(db_client):
    admin = make_admin()
    register(db_client)
    db_client.cookies.clear()
    _, op_token = login(db_client, "op@plant.kz")
    op_cookie = db_client.cookies.get("fedwind_session")
    db_client.cookies.clear()
    _, token = login(db_client, "admin@fedwind.kz")

    users = db_client.get("/api/admin/users").json()["users"]
    op = next(u for u in users if u["email"] == "op@plant.kz")
    assert db_client.patch(f"/api/admin/users/{op['id']}", json={"role": "viewer"}).status_code == 403  # no CSRF
    r = db_client.patch(f"/api/admin/users/{op['id']}", json={"role": "viewer"}, headers=csrf(token))
    assert r.status_code == 200 and r.json()["role"] == "viewer"
    # Can't lock yourself out
    assert db_client.patch(f"/api/admin/users/{admin.id}", json={"role": "operator"}, headers=csrf(token)).status_code == 422
    assert db_client.patch(f"/api/admin/users/{admin.id}", json={"active": False}, headers=csrf(token)).status_code == 422
    # Disabling ends the user's sessions
    assert db_client.patch(f"/api/admin/users/{op['id']}", json={"active": False}, headers=csrf(token)).status_code == 200
    db_client.cookies.clear()
    db_client.cookies.set("fedwind_session", op_cookie)
    assert db_client.get("/api/auth/me").status_code == 401
    assert login(db_client, "op@plant.kz")[0].status_code == 401
    # Admin creates a viewer
    db_client.cookies.clear()
    _, token = login(db_client, "admin@fedwind.kz")
    r = db_client.post("/api/admin/users", json={"email": "prof@nu.edu.kz", "password": PW, "name": "Prof",
                                                 "role": "viewer"}, headers=csrf(token))
    assert r.status_code == 201 and r.json()["role"] == "viewer"


# --- the open legacy endpoints are gone -----------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("post", "/model-update"),
    ("post", "/model-update/aggregate"),
    ("post", "/api/upload"),
    ("post", "/api/train"),
])
def test_legacy_endpoints_are_not_mounted(db_client, method, path):
    assert getattr(db_client, method)(path).status_code in (404, 405)


def test_cli_creates_admin(db_client, monkeypatch, capsys):
    from app import cli

    monkeypatch.setenv("FEDWIND_NEW_PASSWORD", PW)
    cli.main(["create-admin", "--email", "boss@fedwind.kz", "--name", "Boss"])
    assert "admin boss@fedwind.kz created" in capsys.readouterr().out
    r, _ = login(db_client, "boss@fedwind.kz")
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
