"""DR-06 power errors normalised by capacity; FR-06/DR-08 errors at 1, 6 and 24 h lead times."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from my_flower_app import evaluation
from my_flower_app.run_logging import RunLogger

INFERENCE = Path(__file__).resolve().parents[2] / "inference"


def test_wind_curve_matches_the_websites_inference_service():
    sys.path.insert(0, str(INFERENCE))
    try:
        from power_curve import PowerCurve
    finally:
        sys.path.remove(str(INFERENCE))
    curve = PowerCurve()
    speeds = np.linspace(0, 30, 301)
    assert np.allclose(evaluation.wind_power_kw(speeds), [curve.power_kw(float(v)) for v in speeds])
    assert evaluation.wind_power_kw([2.9, 12, 24.9, 25])[[0, 3]].tolist() == [0.0, 0.0]


def test_power_errors_are_divided_by_capacity():
    e = evaluation.power_errors([1000, 500], [800, 500], capacity_kw=2000)
    assert e["power_mae_kw"] == 100 and e["power_nmae"] == pytest.approx(0.05)
    assert e["power_nrmse"] == pytest.approx(np.sqrt(20000) / 2000)


def test_errors_by_lead_with_persistence_skill():
    true = np.tile(np.arange(72, dtype=float), (3, 1)) + 5  # rising wind
    pred = true + 0.5  # 0.5 m/s off at every lead
    out = evaluation.wind_extras(pred, true, last_real=np.full(3, 5.0))
    assert out["test_mae_real_h1"] == pytest.approx(0.5) and out["ref_mae_real_h1"] == pytest.approx(0.0)
    assert out["ref_mae_real_h24"] == pytest.approx(23.0) and out["skill_h24"] == pytest.approx(1 - 0.5 / 23)
    assert "skill_h1" not in out  # persistence is perfect: no skill ratio
    short = evaluation.lead_errors(pred[:, :1], true[:, :1], true[:, :1])
    assert set(short) == {"test_mae_real_h1", "test_rmse_real_h1", "ref_mae_real_h1", "ref_rmse_real_h1"}


def test_solar_leads_use_daylight_and_rmse_skill():
    true = np.array([[0.0, 400.0, 600.0, 0.0, 0.0, 300.0]])
    pred = np.array([[50.0, 380.0, 620.0, 40.0, 0.0, 310.0]])
    smart = np.array([[0.0, 350.0, 500.0, 0.0, 0.0, 200.0]])
    day = true > 0
    out = evaluation.solar_extras(pred, true, smart, day)
    assert out["test_mae_real_h6"] == pytest.approx(10.0) and out["skill_h6"] == pytest.approx(1 - 10 / 100)
    assert "test_mae_real_h1" not in out  # hour 1 is night in every window
    assert out["power_capacity_kw"] == 1000.0


def test_result_reports_power_and_leads(tmp_path):
    lg = RunLogger.from_run_config({"runs-dir": str(tmp_path), "run-id": "r1", "pred-len": 72}, ["almaty"], [])
    ev = {
        "almaty": {
            "test_mae": 0.2,
            "test_rmse": 0.3,
            "test_mae_real": 1.0,
            "test_rmse_real": 1.5,
            "test_mean_real": 6.0,
            "persistence_mae_real": 2.0,
            "power_nmae": 0.08,
            "power_nrmse": 0.12,
            "power_capacity_kw": 2000.0,
            "test_mae_real_h6": 0.9,
            "ref_mae_real_h6": 1.5,
            "skill_h6": 0.4,
            "test_mae_real_h24": 1.1,
            "skill_h24": 0.3,
        }
    }
    res = lg.result(3, ev, 60.0, 3, 1000, 10000, False)
    real = json.loads((tmp_path / "r1" / "result.json").read_text())["metrics"]["real"]
    assert real["power_nmae"] == 0.08 and "2 MW" in real["power_basis"]
    assert real["by_lead"] == {
        "6": {"mae": 0.9, "rmse": None, "skill": 0.4},
        "24": {"mae": 1.1, "rmse": None, "skill": 0.3},
    }
    assert res["metrics"]["per_site"]["almaty"]["by_lead"]["6"]["reference_mae"] == 1.5
