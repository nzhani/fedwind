"""Baselines (FR-19): same windows as the federated clients, same metric code, every method runs."""

import csv
import json

import numpy as np
import pytest
import torch

from baselines import methods, run
from baselines.data import load_site
from baselines.metrics import client_metrics
from baselines.models import LSTMForecaster, PatchTST
from my_flower_app.experiment import build_model_configs
from my_flower_app.run_logging import site_summary
from my_flower_app.task import _client_dataset
from tests.conftest import write_nasa_csv
from tests.test_solar import OPTS, write_solar_csv

pytest.importorskip("statsmodels")


def cfg(pred=24, seq=48):
    return build_model_configs({"pred-len": pred, "seq-len": seq, "is-pretrained": False, "model": "gpt4ts_linear",
                                "llm-layers": 1})


@pytest.fixture
def wind_sites(tmp_path):
    for i, name in enumerate(("aa", "bb")):
        write_nasa_csv(tmp_path / name / f"nasa_{name}.csv", hours=24 * 60, start_year=2023 + i)
    return tmp_path, [load_site(n, cfg(), "KZMET", str(tmp_path / n / f"nasa_{n}.csv")) for n in ("aa", "bb")]


def test_windows_are_the_federated_clients_windows(wind_sites):
    root, sites = wind_sites
    ds = _client_dataset("test", 0, cfg(), "KZMET", str(root / "aa" / "nasa_aa.csv"))
    s = sites[0]
    assert len(s.test.x) == len(ds)
    for i in (0, len(ds) // 2, len(ds) - 1):
        x, y = ds[i][0][:, 0], ds[i][1][-24:, 0]
        assert np.allclose(s.test.x[i], x) and np.allclose(s.test.y[i], y)
    assert s.std == pytest.approx(float(ds.scaler.scale_[-1]))


def test_persistence_has_zero_skill_against_itself(wind_sites):
    _, sites = wind_sites
    preds = methods.persistence(sites)
    m = site_summary(client_metrics(sites[0], preds["aa"]), solar=False)
    assert m["skill_vs_persistence"] == pytest.approx(0.0, abs=1e-6)
    assert m["by_lead"]["6"]["skill"] == pytest.approx(0.0, abs=1e-6) and 0 <= m["power_nmae"] <= 1


def test_solar_persistence_is_smart_persistence(tmp_path):
    write_solar_csv(tmp_path / "ss" / "nasa_ss.csv", days=60)
    site = load_site("ss", cfg(), "KZSOLAR", str(tmp_path / "ss" / "nasa_ss.csv"), OPTS)
    assert site.test.aux.shape == (len(site.test.x), 24, 5)
    m = site_summary(client_metrics(site, methods.persistence([site])["ss"]), solar=True)
    assert m["skill_vs_persistence"] == pytest.approx(0.0, abs=1e-6) and m["mae"] == pytest.approx(m["persistence_mae"])


def test_models_shapes():
    x = torch.randn(4, 48)
    assert LSTMForecaster(24)(x).shape == (4, 24)
    assert PatchTST(48, 24, patch_len=16, stride=8)(x).shape == (4, 24)
    assert PatchTST(50, 24, patch_len=16, stride=8)(torch.randn(3, 50)).shape == (3, 24)


def test_every_method_runs_and_learns_something(wind_sites):
    _, sites = wind_sites
    settings = methods.TrainSettings(epochs=3, lr=3e-3, rounds=2, local_epochs=1, batch_size=64)
    kw = dict(cfg=cfg(), settings=settings, device=torch.device("cpu"), arima_order=(1, 0, 0), arima_fit_hours=500)
    for name in methods.METHODS:
        preds = methods.METHODS[name](sites, **kw)
        assert set(preds) == {"aa", "bb"}, name
        assert preds["aa"].shape == sites[0].test.y.shape and np.isfinite(preds["aa"]).all(), name
    # The synthetic series is a clean sine: a trained LSTM should beat persistence
    lstm = methods.METHODS["lstm_central"](sites, **{**kw, "settings": methods.TrainSettings(epochs=15, lr=3e-3)})
    m = site_summary(client_metrics(sites[0], lstm["aa"]), solar=False)
    assert m["skill_vs_persistence"] > 0


def test_runner_writes_results_and_summary(wind_sites, tmp_path):
    root, _ = wind_sites
    out = tmp_path / "out"
    rc = run.main(["--energy", "wind", "--horizon", "24", "--seq-len", "48", "--sites", "aa,bb", "--data-root",
                   str(root), "--methods", "persistence,lstm_fedavg", "--rounds", "1", "--local-epochs", "1",
                   "--epochs", "1", "--out", str(out)])
    assert rc == 0
    res = json.loads((out / "wind_h24_lstm_fedavg_seed2021.json").read_text())
    assert set(res["metrics"]["per_site"]) == {"aa", "bb"} and res["metrics"]["real"]["mae"] > 0
    rows = list(csv.DictReader(open(out / "summary.csv")))
    assert {(r["method"], r["site"]) for r in rows} >= {("persistence", "mean"), ("lstm_fedavg", "aa")}
    assert all(abs(float(r["skill_vs_persistence"])) < 1e-4 for r in rows if r["method"] == "persistence")
