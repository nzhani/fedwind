import math

import numpy as np
import pandas as pd
import pytest
import torch

from my_flower_app import solar
from my_flower_app.experiment import build_model_configs
from my_flower_app.task import Net, _client_dataset, test as run_test, train as train_fn

LAT, LON = 43.87, 77.07


def cloud(day: int) -> float:
    return 0.55 + 0.35 * math.sin(day)


def write_solar_csv(path, days=45, start="2024-06-01"):
    """NASA POWER-format solar file whose GHI is the Haurwitz clear sky x a known daily k*."""
    times = pd.date_range(start, periods=24 * days, freq="h")
    cs, _ = solar.clear_sky_hourly(times, LAT, LON)
    ghi = np.array([cs[i] * cloud(i // 24) for i in range(len(times))])
    lines = ["-BEGIN HEADER-", "NASA/POWER test file", f"Location: Latitude  {LAT}   Longitude {LON} ",
             "-END HEADER-", "YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,T2M"]
    for t, g, c in zip(times, ghi, cs):
        lines.append(f"{t.year},{t.month},{t.day},{t.hour},{g:.3f},{c:.3f},20.0")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def cfg(pred_len=24, seq_len=48):
    return build_model_configs({"pred-len": pred_len, "seq-len": seq_len, "is-pretrained": False,
                                "model": "gpt4ts_linear", "llm-layers": 1})


OPTS = {"target_kind": "kstar", "daylight_mask": True, "min_elevation": 5.0, "kstar_max": 1.2}


def test_sun_elevation_at_solar_noon_and_midnight():
    # Solar noon in Almaty on the June solstice is about 06:52 UTC: elevation = 90 - (lat - 23.44)
    noon = solar.sun_elevation(pd.DatetimeIndex(["2024-06-21 06:52"]), 43.24, 76.89)[0]
    assert abs(noon - (90 - (43.24 - 23.44))) < 1.0
    midnight = solar.sun_elevation(pd.DatetimeIndex(["2024-06-21 18:52"]), 43.24, 76.89)[0]
    assert midnight < -20


def test_clear_sky_is_zero_at_night_and_bounded():
    assert solar.haurwitz_ghi([-10.0, 0.0])[0] == 0
    assert 1000 < solar.haurwitz_ghi([90.0])[0] < 1100


def test_clear_sky_index_clips_and_repeats_last_daylight_value():
    ghi = [0, 100, 300, 50, 0, 0]
    cs = [0, 100, 200, 100, 0, 0]
    day = [0, 1, 1, 1, 0, 0]
    k = solar.clear_sky_index(ghi, cs, day, kstar_max=1.2)
    assert k[1] == 1.0 and k[2] == 1.2 and k[3] == 0.5
    assert k[4] == k[5] == 0.5          # night: last daylight value, never a later one
    assert k[0] == 1.0                  # only the very first night is back-filled


def test_solar_frame_recovers_the_clear_sky_index(tmp_path):
    f = solar.solar_frame(str(write_solar_csv(tmp_path / "nasa_konaev.csv")))
    assert f.attrs["lat"] == LAT and f.attrs["lon"] == LON
    day = f["DAYLIGHT"].to_numpy() > 0.5
    assert 0.3 < day.mean() < 0.8
    expected = np.array([cloud(i // 24) for i in range(len(f))])
    assert np.allclose(f["KSTAR"].to_numpy()[day], expected[day], atol=0.02)
    assert (f["GHI_CS"].to_numpy()[f["ELEV"].to_numpy() < -10] == 0).all()   # deep night; a sunrise hour can have mid-hour elevation < 0


def test_solar_dataset_items_and_scaling(tmp_path):
    p = write_solar_csv(tmp_path / "konaev" / "nasa_konaev.csv")
    tr = _client_dataset("train", 0, cfg(), "KZSOLAR", data_file=str(p), solar=OPTS)
    te = _client_dataset("test", 0, cfg(), "KZSOLAR", data_file=str(p), solar=OPTS)
    assert isinstance(tr, solar.SolarDataset)
    assert np.allclose(tr.scaler.mean_, te.scaler.mean_)       # fit on train only, shared
    x, y, xm, ym, aux = te[0]
    assert x.shape == (48, 1) and y.shape == (48 + 24, 1) and aux.shape == (24, 5)
    assert set(np.unique(aux[:, solar.AUX_DAYLIGHT])) <= {0.0, 1.0}
    assert 0.2 < tr.kstar_climatology < 0.9


def test_masked_mse_ignores_night_hours():
    pred = torch.tensor([[[1.0], [100.0]]])
    true = torch.tensor([[[0.0], [0.0]]])
    mask = torch.tensor([[[1.0], [0.0]]])
    assert solar.masked_mse(pred, true, mask).item() == 1.0


def test_perfect_forecast_and_baselines_in_watts(tmp_path):
    p = write_solar_csv(tmp_path / "nasa_konaev.csv")
    ds = _client_dataset("test", 0, cfg(), "KZSOLAR", data_file=str(p), solar=OPTS)
    items = [ds[i] for i in range(0, len(ds), 7)]
    aux = np.stack([it[4] for it in items])
    truth_scaled = np.stack([it[1][-24:] for it in items])     # the true k*, scaled
    std, mean = float(ds.scaler.scale_[0]), float(ds.scaler.mean_[0])
    m = solar.evaluate_ghi(truth_scaled, aux, mean, std, "kstar", 1.2, ds.kstar_climatology)
    assert m["model"]["mae"] < 5.0                             # W/m2: only k* < 5 deg noise
    assert m["mean_daylight_ghi"] > 100
    for ref in ("persistence", "smart_persistence", "climatology"):
        assert m[ref]["mae"] > m["model"]["mae"]


def test_pv_power_is_zero_at_night_and_capped():
    p = solar.pv_power_kw([0.0, 500.0, 2000.0], capacity_kw=1000)
    assert p[0] == 0 and p[1] == pytest.approx(400.0) and p[2] == 1000


def test_options_only_for_solar_runs():
    assert solar.options({"energy-type": "wind"}) is None
    o = solar.options({"energy-type": "solar", "solar-target": "GHI", "daylight-mask": False})
    assert o["target_kind"] == "ghi" and o["daylight_mask"] is False and o["kstar_max"] == 1.2


def test_masked_training_step_runs(tmp_path):
    p = write_solar_csv(tmp_path / "nasa_konaev.csv", days=20)
    c = cfg(pred_len=6, seq_len=24)
    ds = _client_dataset("train", 0, c, "KZSOLAR", data_file=str(p), solar=OPTS, percent=20)
    loader = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, range(8)), batch_size=4)
    net = Net(device=torch.device("cpu"), configs=c)
    loss, history, _ = train_fn(net, loader, 1, 1e-3, torch.device("cpu"), masked_loss=True)
    assert math.isfinite(loss)
    out = run_test(net, loader, torch.device("cpu"), return_predictions=True, masked_loss=True, return_aux=True)
    assert out[5].shape == (8, 6, 5) and math.isfinite(out[1])
