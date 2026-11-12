from app.services.inference_client import get_inference
from tests.conftest import FakeInference, write_finished_run


def test_sites_filtered_by_energy_type(client):
    wind = client.get("/api/sites", params={"energy_type": "wind"}).json()["sites"]
    assert [s["id"] for s in wind] == ["almaty", "zhezkazgan", "aktau", "taraz", "aktobe"]
    solar = client.get("/api/sites", params={"energy_type": "solar"}).json()["sites"]
    assert solar and all(s["status"] == "coming_soon" for s in solar)
    assert client.get("/api/sites", params={"energy_type": "hydro"}).status_code == 422


def test_forecast_solar_is_501(client):
    r = client.get("/api/forecast", params={"energy_type": "solar", "site": "almaty-solar", "horizon": 72})
    assert r.status_code == 501


def test_forecast_validates_site_and_horizon(client):
    assert client.get("/api/forecast", params={"site": "nowhere", "horizon": 72}).status_code == 422
    r = client.get("/api/forecast", params={"site": "almaty", "horizon": 6})
    assert r.status_code == 422 and "1, 72, 432" in r.json()["detail"]
    assert client.get("/api/forecast", params={"site": "almaty", "horizon": 72, "as_of": "yesterday"}).status_code == 422


def test_forecast_without_model_is_503(client):
    r = client.get("/api/forecast", params={"site": "almaty", "horizon": 72})
    assert r.status_code == 503 and "No model is registered" in r.json()["detail"]


def test_forecast_with_model_but_no_inference_is_503(client, data_dir):
    write_finished_run(data_dir)
    assert client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"}).status_code == 200
    r = client.get("/api/forecast", params={"site": "almaty", "horizon": 72})
    assert r.status_code == 503 and "Inference not connected" in r.json()["detail"]


def test_forecast_through_inference(client, data_dir):
    from main import app

    write_finished_run(data_dir)
    client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"})
    fake = FakeInference()
    app.dependency_overrides[get_inference] = lambda: fake

    r = client.get("/api/forecast", params={"site": "aktau", "horizon": 72, "as_of": "2024-06-01T00:00:00Z"})
    assert r.status_code == 200
    body = r.json()
    assert body["model"]["run_id"] == "wind-fedavg-h72-20261101T000000Z"
    assert body["unit"] == "m/s" and len(body["forecast"]) == 3
    assert fake.calls == [("aktau", 72, "2024-06-01T00:00:00Z", "wind/h72/current.pt")]


def test_promote_copies_checkpoint(client, data_dir):
    write_finished_run(data_dir)
    r = client.post("/api/models/promote", json={"run_id": "wind-fedavg-h72-20261101T000000Z"})
    assert r.status_code == 200 and r.json()["horizon"] == 72
    assert (data_dir / "models" / "wind" / "h72" / "current.pt").read_bytes() == b"checkpoint-bytes"
    assert client.get("/api/models").json()["models"][0]["run_id"] == "wind-fedavg-h72-20261101T000000Z"
    assert client.post("/api/models/promote", json={"run_id": "missing"}).status_code == 404
