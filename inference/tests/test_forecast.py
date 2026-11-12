"""Inference end to end with a random-backbone checkpoint (no download needed)."""

import importlib
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
ML = ROOT / "Long-term_Forecasting"
for p in (ML, ML / "flower_app", ROOT / "inference"):
    sys.path.insert(0, str(p))


@pytest.fixture
def client(tmp_path, monkeypatch):
    sys.path.insert(0, str(ML / "tests"))
    from conftest import write_nasa_csv

    monkeypatch.setenv("FEDWIND_ML_ROOT", str(ML))
    from my_flower_app.experiment import build_model_configs
    from my_flower_app.task import Net, trainable_state_dict

    data, models = tmp_path / "data", tmp_path / "models"
    write_nasa_csv(data / "nasa_almaty.csv", hours=24 * 120)
    rc = {"pred-len": 24, "seq-len": 48, "model": "gpt4ts_linear", "llm-layers": 1, "is-pretrained": False}
    net = Net(device=torch.device("cpu"), configs=build_model_configs(rc))
    (models / "wind" / "h24").mkdir(parents=True)
    torch.save({"trainable_state": trainable_state_dict(net), "run_config": rc, "round": 1, "metrics": {}},
               models / "wind" / "h24" / "current.pt")

    monkeypatch.setenv("SITE_ID", "almaty")
    monkeypatch.setenv("DATA_ROOT", str(data))
    monkeypatch.setenv("MODELS_ROOT", str(models))
    import app as app_module
    importlib.reload(app_module)
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def test_forecast_default_issue_time(client):
    r = client.post("/forecast", json={"horizon": 24, "model_path": "wind/h24/current.pt"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["forecast"]) == 24 and body["unit"] == "m/s"
    assert all(p["wind_speed"] >= 0 and p["wind_power_kw"] >= 0 for p in body["forecast"])
    assert body["forecast"][0]["timestamp"] > body["as_of"]
    assert any(a["timestamp"] > body["as_of"] for a in body["actual"])  # actuals after the issue time


def test_forecast_errors(client):
    assert client.post("/forecast", json={"horizon": 72, "model_path": "wind/h24/current.pt"}).status_code == 422
    assert client.post("/forecast", json={"horizon": 24, "model_path": "wind/h72/current.pt"}).status_code == 503
    assert client.post("/forecast", json={"horizon": 24, "model_path": "../../etc/passwd"}).status_code == 503
    r = client.post("/forecast", json={"horizon": 24, "as_of": "2030-01-01T00:00:00Z", "model_path": "wind/h24/current.pt"})
    assert r.status_code == 422


def test_forecast_at_given_time(client):
    r = client.post("/forecast", json={"horizon": 24, "as_of": "2024-03-01T05:00:00Z", "model_path": "wind/h24/current.pt"})
    assert r.status_code == 200, r.text
    assert r.json()["as_of"] == "2024-03-01T05:00:00Z"
