import json

from app.services.federation_client import get_federation
from tests.conftest import FakeFederation, write_csv, write_finished_run

SITES = ["almaty", "zhezkazgan", "aktau", "taraz", "aktobe"]


def _start(client, config=None, files=None):
    return client.post("/api/runs", data={"config": json.dumps(config or {"rounds": 3})}, files=files or {})


def _connect(fake=None):
    from main import app

    fake = fake or FakeFederation()
    app.dependency_overrides[get_federation] = lambda: fake
    return fake


def test_no_runs_and_federation_not_connected(client, data_dir):
    assert client.get("/api/runs").json() == {"runs": [], "active_run_id": None}
    assert client.get("/api/federation").json()["connected"] is False
    r = _start(client)
    assert r.status_code == 503 and "not connected" in r.json()["detail"]
    assert not (data_dir / "runs").exists() or not any((data_dir / "runs").iterdir())


def test_config_validation(client):
    _connect()
    assert _start(client, {"horizon": 6}).status_code == 422
    assert _start(client, {"strategy": "statavg"}).status_code == 422
    assert _start(client, {"sites": ["almaty", "atlantis"], "min_train_clients": 1}).status_code == 422
    assert _start(client, {"unknown_field": 1}).status_code == 422
    assert _start(client, {"model": "informer"}).status_code == 422
    assert client.post("/api/runs", data={"config": "{not json"}).status_code == 422


def test_start_run_then_409_then_stop(client, data_dir):
    fake = _connect()
    r = _start(client, {"rounds": 3, "horizon": 432})
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "running" and run["flower_run_id"] == "1001"
    assert run["total_rounds"] == 3 and run["horizon"] == 432 and run["history"] == []
    assert fake.started == [run["run_id"]]
    assert (data_dir / "runs" / run["run_id"] / "config.yaml").is_file()

    r2 = _start(client)
    assert r2.status_code == 409
    assert client.get("/api/runs").json()["active_run_id"] == run["run_id"]

    stopped = client.post(f"/api/runs/{run['run_id']}/stop").json()
    assert stopped["status"] == "stopped" and fake.stopped == ["1001"]
    assert client.post(f"/api/runs/{run['run_id']}/stop").status_code == 409
    assert _start(client).status_code == 201


def test_too_few_clients_is_503(client):
    _connect(FakeFederation(nodes=2))
    r = _start(client, {"min_train_clients": 4})
    assert r.status_code == 503 and "Only 2 clients" in r.json()["detail"]


def test_uploads_go_to_each_site_folder(client, data_dir):
    _connect()
    files = {f"file_{s}": (f"{s}.csv", write_csv(), "text/csv") for s in SITES}
    r = _start(client, {"rounds": 2}, files)
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]
    assert r.json()["config"]["data_source"] == "upload"
    for s in SITES:
        assert (data_dir / "sites" / s / "uploads" / f"{run_id}.csv").is_file()


def test_upload_errors(client):
    _connect()
    some = {f"file_{s}": (f"{s}.csv", write_csv(), "text/csv") for s in SITES[:3]}
    r = _start(client, {}, some)
    assert r.status_code == 422 and "Missing" in r.json()["detail"]

    bad = {f"file_{s}": (f"{s}.csv", write_csv(header="YEAR,MO,DY,HR,T2M"), "text/csv") for s in SITES}
    r = _start(client, {}, bad)
    assert r.status_code == 422 and "WS50M" in r.json()["detail"]

    short = {f"file_{s}": (f"{s}.csv", write_csv(rows=10, nasa_block=False), "text/csv") for s in SITES}
    r = _start(client, {}, short)
    assert r.status_code == 422 and "data rows" in r.json()["detail"]


def test_finished_run_detail_from_files(client, data_dir):
    write_finished_run(data_dir)
    run = client.get("/api/runs/wind-fedavg-h72-20261101T000000Z").json()
    assert run["status"] == "done"  # result.json wins over run.json
    assert [m["round"] for m in run["history"]] == [1, 2]  # half-written line skipped
    assert run["current_round"] == 2 and run["total_rounds"] == 2
    assert {c["site"]: c["status"] for c in run["clients"]} == {"almaty": "replied", "aktau": "replied"}
    assert client.get("/api/runs").json()["active_run_id"] is None


def test_finished_in_flower_without_result_is_failed(client):
    fake = _connect()
    run_id = _start(client).json()["run_id"]
    fake.state = "finished:completed"
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "failed" and "no result.json" in run["error"]


def test_bad_run_ids_are_404(client):
    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fetc").status_code == 404


def test_stopped_run_stays_stopped_after_server_failure(client, data_dir):
    fake = _connect()
    run_id = _start(client).json()["run_id"]
    client.post(f"/api/runs/{run_id}/stop")
    (data_dir / "runs" / run_id / "result.json").write_text(
        json.dumps({"status": "failed", "error": "RunNotRunningException: "}))
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "stopped" and run["error"] is None
