"""python -m app.cli demo-reset: back to the start of the demo (DEMO_DAY_PLAN.md §2 F)."""

import psycopg
import pytest

from app import cli
from tests.conftest import write_finished_run
from tests.test_accounts import login
from tests.test_site_connection import approved_plant, enroll, kit


def counts(pg_url):
    with psycopg.connect(pg_url) as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "plants": q("SELECT count(*) FROM sites WHERE kind = 'plant'"),
            "lab": q("SELECT count(*) FROM sites WHERE kind = 'builtin'"),
            "users": q("SELECT count(*) FROM users WHERE role <> 'admin'"),
            "admins": q("SELECT count(*) FROM users WHERE role = 'admin'"),
            "orgs": q("SELECT count(*) FROM organizations"),
            "credentials": q("SELECT count(*) FROM site_credentials"),
            "reset_logged": q("SELECT count(*) FROM audit_log WHERE action = 'demo.reset'"),
        }


def test_dry_run_changes_nothing_then_reset_keeps_admins_lab_and_runs(db_client, pg_url, data_dir, capsys):
    site_id, op = approved_plant(db_client)
    enroll(db_client, kit(db_client, site_id, op))
    write_finished_run(data_dir)
    before = counts(pg_url)
    assert before["plants"] == 1 and before["users"] == 1 and before["orgs"] == 1 and before["credentials"] == 1

    cli.main(["demo-reset"])
    assert counts(pg_url) == before and "dry run" in capsys.readouterr().out

    cli.main(["demo-reset", "--yes", "--promote", "wind-fedavg-h72-20261101T000000Z"])
    after = counts(pg_url)
    assert after == {"plants": 0, "lab": 10, "users": 0, "admins": 1, "orgs": 0, "credentials": 0, "reset_logged": 1}
    assert (data_dir / "runs" / "wind-fedavg-h72-20261101T000000Z").is_dir()
    model = db_client.get("/api/models").json()["models"][0]
    assert model["run_id"] == "wind-fedavg-h72-20261101T000000Z" and model["promoted_by"] == "ArqauQuat team"

    # The operator's session went with the account; the admin still logs in
    db_client.cookies.clear()
    assert login(db_client, "admin@fedwind.kz")[0].status_code == 200


def test_refused_in_production(db_client, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(SystemExit, match="local demo database only"):
        cli.main(["demo-reset", "--yes"])


def test_keep_an_example_plant_with_its_organization(db_client, pg_url):
    from tests.test_site_registration import WIND, operator
    from tests.test_accounts import csrf

    kept_id, _ = approved_plant(db_client)                                   # op@plant.kz, Plant One LLP
    other = operator(db_client, email="op2@other.kz", org="Other LLP")
    other_id = db_client.post("/api/sites", json={**WIND, "name": "Other Wind"}, headers=csrf(other)).json()["id"]

    with pytest.raises(SystemExit, match="No such plant to keep"):
        cli.main(["demo-reset", "--yes", "--keep", "nope"])
    cli.main(["demo-reset", "--yes", "--keep", kept_id])
    with psycopg.connect(pg_url) as conn:
        plants = [r[0] for r in conn.execute("SELECT id FROM sites WHERE kind = 'plant'")]
        users = [r[0] for r in conn.execute("SELECT email FROM users WHERE role <> 'admin'")]
        orgs = [r[0] for r in conn.execute("SELECT name FROM organizations")]
    assert plants == [kept_id] and other_id not in plants
    assert users == ["op@plant.kz"] and orgs == ["Plant One LLP"]
