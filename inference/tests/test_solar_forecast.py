"""Solar inference end to end with a random-backbone checkpoint (no download needed)."""

import importlib
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
ML = ROOT / "Long-term_Forecasting"
for p in (ML, ML / "flower_app", ROOT / "inference", ML / "tests"):
    sys.path.insert(0, str(p))

RC = {"pred-len": 24, "seq-len": 48, "model": "gpt4ts_linear", "llm-layers": 1, "is-pretrained": False,
      "energy-type": "solar", "solar-target": "kstar", "min-elevation": 5.0, "kstar-max": 1.2}


def _client(tmp_path, monkeypatch, energy_type="solar"):
    from test_solar import write_solar_csv

    monkeypatch.setenv("FEDWIND_ML_ROOT", str(ML))
    from my_flower_app.experiment import build_model_configs
    from my_flower_app.task import Net, trainable_state_dict

    data, models = tmp_path / "data", tmp_path / "models"
    write_solar_csv(data / "nasa_konaev.csv", days=60)
    net = Net(device=torch.device("cpu"), configs=build_model_configs(RC))
    (models / "solar" / "h24").mkdir(parents=True)
    torch.save({"trainable_state": trainable_state_dict(net), "run_config": RC, "round": 1, "metrics": {}},
               models / "solar" / "h24" / "current.pt")

    monkeypatch.setenv("SITE_ID", "konaev")
    monkeypatch.setenv("ENERGY_TYPE", energy_type)
    monkeypatch.setenv("DATA_ROOT", str(data))
    monkeypatch.setenv("MODELS_ROOT", str(models))
    monkeypatch.setenv("PV_CAPACITY_KW", "1000")
    import app as app_module
    importlib.reload(app_module)
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return _client(tmp_path, monkeypatch)


def test_solar_forecast_is_zero_at_night_and_capped(client):
    r = client.post("/forecast", json={"horizon": 24, "model_path": "solar/h24/current.pt"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unit"] == "W/m2" and len(body["forecast"]) == 24
    for p in body["forecast"]:
        assert 0 <= p["ghi"] <= 1.2 * p["clear_sky_ghi"] + 0.1        # k* clipped to [0, 1.2]
        assert 0 <= p["pv_power_kw"] <= 1000
        if p["clear_sky_ghi"] == 0:
            assert p["ghi"] == 0 and p["pv_power_kw"] == 0             # DR-02
    assert any(p["clear_sky_ghi"] == 0 for p in body["forecast"])      # a 24 h window has a night
    assert {"ghi", "clear_sky_ghi", "pv_power_kw"} <= set(body["actual"][0])


def test_solar_model_refused_on_a_wind_site(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, energy_type="wind")
    r = c.post("/forecast", json={"horizon": 24, "model_path": "solar/h24/current.pt"})
    assert r.status_code == 422 and "solar model" in r.text
