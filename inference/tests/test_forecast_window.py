"""Central forecasting endpoint: forecasts from a window in the request, no site files."""

import importlib
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
ML = ROOT / "Long-term_Forecasting"
for p in (ML, ML / "flower_app", ROOT / "inference", ML / "tests"):
    sys.path.insert(0, str(p))

BASE = {"pred-len": 24, "seq-len": 48, "model": "gpt4ts_linear", "llm-layers": 1, "is-pretrained": False}
WIND_EQ = {"turbine_model": "EN-156", "turbine_count": 40, "hub_height_m": 100, "rated_power_kw": 2500}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FEDWIND_ML_ROOT", str(ML))
    from my_flower_app.experiment import build_model_configs
    from my_flower_app.task import Net, trainable_state_dict

    models = tmp_path / "models"
    for energy, extra in (("wind", {}), ("solar", {"energy-type": "solar", "solar-target": "kstar"})):
        rc = {**BASE, **extra}
        net = Net(device=torch.device("cpu"), configs=build_model_configs(rc))
        (models / energy / "h24").mkdir(parents=True)
        torch.save({"trainable_state": trainable_state_dict(net), "run_config": rc, "round": 1, "metrics": {}},
                   models / energy / "h24" / "current.pt")
    monkeypatch.setenv("MODELS_ROOT", str(models))
    monkeypatch.delenv("SITE_ID", raising=False)  # the central service has no site of its own
    import app as app_module
    importlib.reload(app_module)
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def wind_body(**over):
    return {"energy_type": "wind", "horizon": 24, "model_path": "wind/h24/current.pt",
            "end_hour": "2026-11-17T23:00:00Z", "values": [6 + (i % 5) for i in range(60)],
            "lat": 43.57, "lon": 69.75, "capacity_kw": 100000, "equipment": WIND_EQ, **over}


def test_wind_plant_power_from_its_own_turbines(client):
    r = client.post("/forecast-window", json=wind_body(measured_at_m=50))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["unit"] == "m/s" and len(b["forecast"]) == 24 and b["as_of"] == "2026-11-17T23:00:00Z"
    assert b["forecast"][0]["timestamp"] == "2026-11-18T00:00:00Z"
    assert b["hub_height_factor"] == pytest.approx((100 / 50) ** (1 / 7), rel=1e-3)   # 50 m -> 100 m hub
    assert all(0 <= p["wind_power_kw"] <= 100000 for p in b["forecast"] + b["actual"])
    assert len(b["actual"]) == 48
    # Real plants send hub-height values: no adjustment
    assert client.post("/forecast-window", json=wind_body()).json()["hub_height_factor"] == 1.0


def test_solar_plant_is_dark_at_night(client):
    from test_solar import write_solar_csv  # noqa: F401  (same helpers as the ML tests)
    from my_flower_app import solar
    import pandas as pd

    times = pd.date_range("2026-06-01", periods=60, freq="h")
    cs, _ = solar.clear_sky_hourly(times, 43.87, 77.07)
    body = {"energy_type": "solar", "horizon": 24, "model_path": "solar/h24/current.pt",
            "end_hour": times[-1].isoformat() + "Z", "values": [float(c) * 0.7 for c in cs],
            "lat": 43.87, "lon": 77.07, "capacity_kw": 50000}
    r = client.post("/forecast-window", json=body)
    assert r.status_code == 200, r.text
    f = r.json()["forecast"]
    assert any(p["clear_sky_ghi"] == 0 for p in f)
    for p in f:
        assert 0 <= p["pv_power_kw"] <= 50000
        if p["clear_sky_ghi"] == 0:
            assert p["ghi"] == 0 and p["pv_power_kw"] == 0


def test_window_errors(client):
    assert client.post("/forecast-window", json=wind_body(values=[5.0] * 20)).status_code == 422       # too short
    gappy = [None if i % 2 else 5.0 for i in range(60)]
    assert client.post("/forecast-window", json=wind_body(values=gappy)).status_code == 422            # too many gaps
    assert client.post("/forecast-window", json=wind_body(model_path="solar/h24/current.pt")).status_code == 422
    assert client.post("/forecast-window", json=wind_body(horizon=72)).status_code == 422
    few_gaps = [None if i in (3, 4) else 5.0 for i in range(60)]
    assert client.post("/forecast-window", json=wind_body(values=few_gaps)).status_code == 200
