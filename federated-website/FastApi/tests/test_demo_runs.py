"""Demo runs (DEMO_RUNS=1): played back from a real finished run, never sent to the federation."""

import json
import time

from app.services.federation_client import get_federation
from tests.conftest import FakeFederation, write_finished_run


def _wait_done(client, run_id, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("demo run did not finish")


def test_demo_run_plays_back_rounds_and_reuses_the_checkpoint(client, data_dir, monkeypatch):
    from main import app

    monkeypatch.setenv("DEMO_RUNS", "1")
    monkeypatch.setenv("DEMO_ROUND_SECONDS", "0.05")
    fake = FakeFederation(nodes=0)                  # not connected enough: demo mode doesn't ask
    app.dependency_overrides[get_federation] = lambda: fake
    source = write_finished_run(data_dir, "solar-fedavg-h72-20261119T150357Z", 72, "solar")

    r = client.post("/api/runs", data={"config": json.dumps(
        {"energy_type": "solar", "sites": ["kyzylorda", "saran"], "min_train_clients": 2, "rounds": 3,
         "horizon": 72, "data_percent": 5})})
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]
    assert r.json()["status"] == "running" and fake.started == []

    run = _wait_done(client, run_id)
    assert run["status"] == "done" and run["current_round"] == 3
    assert [h["round"] for h in run["history"]] == [1, 2, 3]
    assert all(c["status"] == "replied" for h in run["history"] for c in h["clients"])
    assert [c["site"] for c in run["clients"]] == ["kyzylorda", "saran"]
    assert run["result"]["model"]["checkpoint"] == "checkpoints/best.pt"
    folder = data_dir / "runs" / run_id
    assert (folder / "checkpoints" / "best.pt").read_bytes() == (source / "checkpoints" / "best.pt").read_bytes()
    record = json.loads((folder / "run.json").read_text())
    assert record["demo"] is True and record["demo_source"] == source.name


def test_demo_run_can_be_stopped(client, data_dir, monkeypatch):
    from main import app

    monkeypatch.setenv("DEMO_RUNS", "1")
    monkeypatch.setenv("DEMO_ROUND_SECONDS", "5")
    app.dependency_overrides[get_federation] = lambda: FakeFederation()
    write_finished_run(data_dir, "solar-fedavg-h72-20261119T150357Z", 72, "solar")
    run_id = client.post("/api/runs", data={"config": json.dumps(
        {"energy_type": "solar", "sites": ["konaev", "saran"], "min_train_clients": 2, "rounds": 2,
         "horizon": 72})}).json()["run_id"]
    assert client.post(f"/api/runs/{run_id}/stop").json()["status"] == "stopped"
    time.sleep(1.2)
    assert not (data_dir / "runs" / run_id / "result.json").exists()


def test_without_demo_mode_runs_go_to_the_federation(client, monkeypatch):
    from main import app

    monkeypatch.delenv("DEMO_RUNS", raising=False)
    fake = FakeFederation()
    app.dependency_overrides[get_federation] = lambda: fake
    r = client.post("/api/runs", data={"config": json.dumps({"rounds": 2})})
    assert r.status_code == 201 and fake.started == [r.json()["run_id"]]
