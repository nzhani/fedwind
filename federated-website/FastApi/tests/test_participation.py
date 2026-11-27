"""Operators pause training, change consents and leave (SITE_NETWORK_PLAN.md §4 step 6)."""

import psycopg

from tests.test_accounts import csrf, login
from tests.test_site_connection import approved_plant, beat, enroll, kit, window
from tests.test_site_registration import operator


def test_pause_share_and_leave(db_client, pg_url):
    site_id, op = approved_plant(db_client)
    key = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    url = f"/api/my/sites/{site_id}/consents"

    r = db_client.put(url, json={"train": False, "share_forecast_window": True, "public_forecasts": False},
                      headers=csrf(op))
    assert r.status_code == 200, r.text
    assert r.json()["consents"]["train"] is False and r.json()["can_train"] is False
    assert r.json()["train_note"] == "No consent to train"
    assert beat(db_client, key).json()["consents"]["share_forecast_window"] is True   # the agent learns it

    assert window(db_client, key).status_code == 200
    db_client.put(url, json={"train": True, "share_forecast_window": False, "public_forecasts": False}, headers=csrf(op))
    with psycopg.connect(pg_url) as conn:                    # shared windows are deleted when sharing stops
        assert conn.execute("SELECT count(*) FROM forecast_inputs").fetchone()[0] == 0
    assert window(db_client, key).status_code == 403

    db_client.cookies.clear()
    other = operator(db_client, email="b@other.kz", org="Other LLP")
    assert db_client.put(url, json={"train": True, "share_forecast_window": False, "public_forecasts": False},
                         headers=csrf(other)).status_code == 404
    assert db_client.post(f"/api/my/sites/{site_id}/leave", json={}, headers=csrf(other)).status_code == 404

    db_client.cookies.clear()
    _, op = login(db_client, "op@plant.kz")
    r = db_client.post(f"/api/my/sites/{site_id}/leave", json={"note": "Plant sold"}, headers=csrf(op))
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    assert beat(db_client, key).status_code == 401                                   # credentials revoked
    assert db_client.put(url, json={"train": True, "share_forecast_window": False, "public_forecasts": False},
                         headers=csrf(op)).status_code == 409
    actions = [h["action"] for h in db_client.get(f"/api/my/sites/{site_id}").json()["history"]]
    assert "consents" in actions and "leave" in actions
