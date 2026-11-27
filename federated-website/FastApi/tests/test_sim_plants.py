"""Simulated plants and run commands for the M9 scale test; rejected clients in run logs."""

import json
import zipfile

import pytest

from app.services import sim_plants
from app.services.accounts import AccountError
from tests.conftest import write_finished_run


def test_spawn_registers_approves_and_issues_kits(db_client, tmp_path, monkeypatch):
    from tests.test_site_registration import admin

    admin(db_client)
    made = sim_plants.spawn(3, "solar", tmp_path / "kits", seed=1)
    assert len(made) == 3 and len({m["site_id"] for m in made}) == 3
    for m in made:
        z = zipfile.ZipFile(m["kit"])
        token = next(n for n in z.namelist() if n.endswith("enrollment.token"))
        assert z.read(token).decode().startswith("fwe_")
        assert (tmp_path / "kits" / m["kit"].split("/")[-1]).stat().st_mode & 0o777 == 0o600
    rows = sim_plants.status()
    assert {r["status"] for r in rows} == {"approved"} and not any(r["can_train"] for r in rows)
    assert sim_plants.spawn(1, "solar", tmp_path / "kits")[0]["name"].startswith("Sim solar 04 ")   # numbering goes on

    monkeypatch.setenv("ENV", "production")
    with pytest.raises(AccountError):
        sim_plants.spawn(1, "wind", tmp_path / "kits")


def test_spawn_needs_an_admin(db_client, tmp_path):
    with pytest.raises(AccountError, match="admin"):
        sim_plants.spawn(1, "wind", tmp_path)


def test_rejected_clients_appear_in_the_run(client, data_dir, capsys):
    folder = write_finished_run(data_dir)
    (folder / "metrics.jsonl").write_text(json.dumps({
        "round": 1, "total_rounds": 2, "uplink_bytes": 1000,
        "clients": [{"site": "almaty", "status": "replied"},
                    {"site": "aktau", "status": "rejected", "reason": "non-finite values in w"},
                    {"site": "taraz", "status": "dropped"}]}) + "\n")
    run = client.get("/api/runs/wind-fedavg-h72-20261101T000000Z").json()
    statuses = {c["site"]: c["status"] for c in run["history"][0]["clients"]}
    assert statuses == {"almaty": "replied", "aktau": "rejected", "taraz": "dropped"}

    from app.cli import run_status_command

    run_status_command("wind-fedavg-h72-20261101T000000Z", as_json=True)
    out = json.loads(capsys.readouterr().out)
    assert out["rounds"][0]["rejected_sites"] == ["aktau"] and out["rounds"][0]["dropped_sites"] == ["taraz"]
