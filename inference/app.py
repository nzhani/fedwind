"""
Per-site inference service (plan T3.2, T3.4).

One instance per site, next to that site's data: it mounts only /data (this site's
folder) and /models (promoted checkpoints), both read-only. The API calls

  POST /forecast  {"horizon": 72, "as_of": "<ISO UTC or null>", "model_path": "wind/h72/current.pt"}

and gets back the actual values around the issue time and the model's forecast for the
next `horizon` hours. History is the `seq_len` hours up to and including `as_of` (DR-04).

  wind   wind speed in m/s, power from a reference turbine curve (DR-01)
  solar  GHI in W/m2 (forecast k* x clear-sky GHI of each future hour, or GHI directly),
         the clear-sky GHI, and AC power of a simple PV plant (DR-02, DR-03)

Env: SITE_ID, ENERGY_TYPE=wind|solar, DATA_ROOT=/data, MODELS_ROOT=/models,
TURBINE_RATED_KW, TURBINE_CUT_IN, TURBINE_RATED_SPEED, TURBINE_CUT_OUT (wind),
PV_CAPACITY_KW, PV_PERFORMANCE_RATIO (solar). Needs Long-term_Forecasting and its
flower_app on PYTHONPATH and FEDWIND_ML_ROOT set (the Flower image does this).
"""

import os
import threading
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sklearn.preprocessing import StandardScaler

from my_flower_app import solar
from my_flower_app.dataloader import preprocess_nasa_data
from my_flower_app.experiment import build_model_configs
from my_flower_app.task import Net, get_dataset_config

from power_curve import PowerCurve

SITE_ID = os.environ.get("SITE_ID", "")
ENERGY_TYPE = os.environ.get("ENERGY_TYPE", "wind").lower()
DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/data"))
MODELS_ROOT = Path(os.environ.get("MODELS_ROOT", "/models"))
HISTORY_SHOWN_H = 48  # actual values shown before the issue time

CURVE = PowerCurve(
    rated_kw=float(os.environ.get("TURBINE_RATED_KW", 2000)),
    cut_in=float(os.environ.get("TURBINE_CUT_IN", 3)),
    rated_speed=float(os.environ.get("TURBINE_RATED_SPEED", 12)),
    cut_out=float(os.environ.get("TURBINE_CUT_OUT", 25)),
)
PV_CAPACITY_KW = float(os.environ.get("PV_CAPACITY_KW", 1000))
PV_PERFORMANCE_RATIO = float(os.environ.get("PV_PERFORMANCE_RATIO", 0.8))

app = FastAPI(title=f"FedWind inference ({SITE_ID or 'unset'})")
_lock = threading.Lock()
torch.set_num_threads(int(os.environ.get("TORCH_THREADS", 4)))


class ForecastRequest(BaseModel):
    horizon: int
    as_of: Optional[str] = None
    model_path: str


class SiteSeries:
    """This site's series and the scaler fit on its train split (same as training)."""

    def __init__(self, path: Path, target: str):
        df = preprocess_nasa_data(str(path), target)
        self.dates = pd.DatetimeIndex(df["date"])
        self.values = df[target].to_numpy(dtype=np.float64)
        num_train = int(len(df) * 0.7)
        num_test = int(len(df) * 0.2)
        self.scaler = StandardScaler().fit(self.values[:num_train].reshape(-1, 1))
        self.scaled = self.scaler.transform(self.values.reshape(-1, 1))[:, 0]
        test_start = len(df) - num_test
        self.default_index = test_start + num_test // 2  # fixed issue time inside the test split


class SolarSeries:
    """This site's solar frame (GHI, clear sky, k*) and the scaler fit on its train split."""

    def __init__(self, path: Path, opts: dict):
        frame = solar.solar_frame(str(path), opts["min_elevation"], opts["kstar_max"])
        self.lat, self.lon = frame.attrs["lat"], frame.attrs["lon"]
        self.dates = pd.DatetimeIndex(frame["date"])
        self.ghi = frame["GHI"].to_numpy(dtype=np.float64)
        self.ghi_cs = frame["GHI_CS"].to_numpy(dtype=np.float64)
        target = frame["KSTAR" if opts["target_kind"] == "kstar" else "GHI"].to_numpy(dtype=np.float64)
        num_train = int(len(frame) * 0.7)
        num_test = int(len(frame) * 0.2)
        self.scaler = StandardScaler().fit(target[:num_train].reshape(-1, 1))
        self.scaled = self.scaler.transform(target.reshape(-1, 1))[:, 0]
        self.default_index = len(frame) - num_test + num_test // 2


def _data_path() -> Path:
    path = DATA_ROOT / f"nasa_{SITE_ID}.csv"
    if not path.is_file():
        raise HTTPException(503, f"Data file for site '{SITE_ID}' not found at {path}")
    return path


@lru_cache(maxsize=1)
def site_series() -> SiteSeries:
    return SiteSeries(_data_path(), get_dataset_config("KZMET")["target"])


@lru_cache(maxsize=4)
def solar_series(target_kind: str, min_elevation: float, kstar_max: float) -> SolarSeries:
    return SolarSeries(_data_path(), {"target_kind": target_kind, "min_elevation": min_elevation,
                                      "kstar_max": kstar_max})


_models: dict = {}


def load_model(model_path: str):
    """Rebuild Net from the checkpoint's run config and overlay the trainable state; cached by mtime."""
    path = (MODELS_ROOT / model_path).resolve()
    if MODELS_ROOT.resolve() not in path.parents or not path.is_file():
        raise HTTPException(503, f"Model '{model_path}' not found")
    key = (str(path), path.stat().st_mtime)
    with _lock:
        if key not in _models:
            ckpt = torch.load(path, map_location="cpu")
            configs = build_model_configs(ckpt["run_config"])
            net = Net(device=torch.device("cpu"), configs=configs)
            net.load_state_dict(ckpt["trainable_state"], strict=False)
            net.eval()
            _models.clear()
            _models[key] = (net, configs, ckpt["run_config"])
        return _models[key]


def _iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


@app.get("/health")
def health():
    return {
        "site": SITE_ID,
        "energy_type": ENERGY_TYPE,
        "data": (DATA_ROOT / f"nasa_{SITE_ID}.csv").is_file(),
        "models": sorted(str(p.relative_to(MODELS_ROOT)) for p in MODELS_ROOT.glob("*/h*/current.pt")) if MODELS_ROOT.is_dir() else [],
    }


def _issue_index(series, as_of: Optional[str], seq_len: int) -> int:
    if as_of:
        ts = pd.Timestamp(as_of)
        ts = (ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo else ts).floor("h")
        idx = int(series.dates.searchsorted(ts, side="right")) - 1
        if idx < 0 or ts > series.dates[-1]:
            raise HTTPException(422, f"No data at {ts} for site '{SITE_ID}' "
                                     f"(data covers {series.dates[0]} to {series.dates[-1]})")
    else:
        idx = series.default_index
    if idx + 1 < seq_len:
        raise HTTPException(422, f"Need {seq_len} hours of history before the issue time")
    return idx


def _predict(net, scaled: np.ndarray, idx: int, seq_len: int) -> np.ndarray:
    x = torch.tensor(scaled[idx + 1 - seq_len: idx + 1], dtype=torch.float32).view(1, seq_len, 1)
    with torch.no_grad():
        return net(x).view(-1).numpy()


@app.post("/forecast")
def forecast(req: ForecastRequest):
    net, configs, run_config = load_model(req.model_path)
    if configs.pred_len != req.horizon:
        raise HTTPException(422, f"Model predicts {configs.pred_len} steps, request asks for {req.horizon}")
    model_energy = str(run_config.get("energy-type", "wind")).lower()
    if model_energy != ENERGY_TYPE:
        raise HTTPException(422, f"Model '{req.model_path}' is a {model_energy} model; site '{SITE_ID}' is {ENERGY_TYPE}")
    if ENERGY_TYPE == "solar":
        return _forecast_solar(req, net, configs, solar.options(run_config))
    series = site_series()
    seq_len = configs.seq_len

    if req.as_of:
        as_of = pd.Timestamp(req.as_of)
        as_of = (as_of.tz_convert("UTC").tz_localize(None) if as_of.tzinfo else as_of).floor("h")
        idx = int(series.dates.searchsorted(as_of, side="right")) - 1
        if idx < 0 or as_of > series.dates[-1]:
            raise HTTPException(422, f"No data at {as_of} for site '{SITE_ID}' "
                                     f"(data covers {series.dates[0]} to {series.dates[-1]})")
    else:
        idx = series.default_index
    if idx + 1 < seq_len:
        raise HTTPException(422, f"Need {seq_len} hours of history before the issue time")

    x = torch.tensor(series.scaled[idx + 1 - seq_len: idx + 1], dtype=torch.float32).view(1, seq_len, 1)
    with torch.no_grad():
        y = net(x).view(-1).numpy()
    speeds = series.scaler.inverse_transform(y.reshape(-1, 1))[:, 0]
    issue = series.dates[idx]

    forecast_points = []
    for k, v in enumerate(speeds, start=1):
        v = max(0.0, float(v))  # wind speed can't be negative
        forecast_points.append({
            "timestamp": _iso(issue + timedelta(hours=k)),
            "wind_speed": round(v, 3),
            "wind_power_kw": round(CURVE.power_kw(v), 1),
        })

    lo, hi = max(0, idx - HISTORY_SHOWN_H), min(len(series.values), idx + 1 + req.horizon)
    actual = [
        {"timestamp": _iso(series.dates[i]), "wind_speed": round(float(series.values[i]), 3),
         "wind_power_kw": round(CURVE.power_kw(float(series.values[i])), 1)}
        for i in range(lo, hi)
    ]
    return {"as_of": _iso(issue), "unit": "m/s", "actual": actual, "forecast": forecast_points}


def _forecast_solar(req: ForecastRequest, net, configs, opts: dict):
    series = solar_series(opts["target_kind"], opts["min_elevation"], opts["kstar_max"])
    idx = _issue_index(series, req.as_of, configs.seq_len)
    y = _predict(net, series.scaled, idx, configs.seq_len)
    issue = series.dates[idx]

    # Clear sky depends only on time and place, so it is known for every forecast hour
    times = pd.DatetimeIndex([issue + timedelta(hours=k) for k in range(1, req.horizon + 1)])
    cs, _ = solar.clear_sky_hourly(times, series.lat, series.lon)
    std, mean = float(series.scaler.scale_[0]), float(series.scaler.mean_[0])
    ghi = solar.forecast_ghi(y, cs, mean, std, opts["target_kind"], opts["kstar_max"])
    power = solar.pv_power_kw(ghi, PV_CAPACITY_KW, PV_PERFORMANCE_RATIO)
    forecast_points = [
        {"timestamp": _iso(t), "ghi": round(float(g), 1), "clear_sky_ghi": round(float(c), 1),
         "pv_power_kw": round(float(p), 1)}
        for t, g, c, p in zip(times, ghi, cs, power)
    ]

    lo, hi = max(0, idx - HISTORY_SHOWN_H), min(len(series.ghi), idx + 1 + req.horizon)
    actual_power = solar.pv_power_kw(series.ghi[lo:hi], PV_CAPACITY_KW, PV_PERFORMANCE_RATIO)
    actual = [
        {"timestamp": _iso(series.dates[i]), "ghi": round(float(series.ghi[i]), 1),
         "clear_sky_ghi": round(float(series.ghi_cs[i]), 1), "pv_power_kw": round(float(p), 1)}
        for i, p in zip(range(lo, hi), actual_power)
    ]
    return {"as_of": _iso(issue), "unit": "W/m2", "actual": actual, "forecast": forecast_points}


# ---------------------------------------------------------------------------
# Central forecasting (DEMO_SIMULATION_PLAN.md §2.3, SITE_NETWORK_PLAN.md §8 "central mode")
# ---------------------------------------------------------------------------
# The newest promoted model forecasts from a window a consenting plant shared. Nothing is read from
# files except the model: the window, location, capacity and equipment come with the request. The
# model normalises each input window itself (mean/std inside GPT4TS.forward), so a plant's own recent
# window is enough; no training-split scaler is needed.


WIND_SHEAR_ALPHA = 1 / 7          # power-law wind profile, open terrain
MAX_MISSING_SHARE = 0.25


class WindowRequest(BaseModel):
    energy_type: Literal["wind", "solar"]
    horizon: int
    model_path: str
    end_hour: str                                   # ISO UTC hour of the last value
    values: List[Optional[float]]                   # oldest first; wind speed (m/s) or GHI (W/m2)
    lat: float
    lon: float
    capacity_kw: float
    equipment: Dict[str, Any] = {}
    measured_at_m: Optional[float] = None           # wind: height of the values (50 for NASA POWER)


def _fill(values: List[Optional[float]]) -> np.ndarray:
    s = pd.Series([np.nan if v is None else float(v) for v in values], dtype=float)
    if s.isna().mean() > MAX_MISSING_SHARE:
        raise HTTPException(422, f"Too many missing hours in the window ({int(s.isna().sum())} of {len(s)})")
    return s.ffill().bfill().to_numpy()


def _wind_power_kw(speed_hub: np.ndarray, equipment: Dict[str, Any], capacity_kw: float) -> np.ndarray:
    """The plant's turbines: count x a generic curve (3 / 12 / 25 m/s) at their rated power."""
    count = max(1, int(equipment.get("turbine_count") or 1))
    rated = float(equipment.get("rated_power_kw") or capacity_kw / count)
    curve = PowerCurve(rated_kw=rated, cut_in=3.0, rated_speed=12.0, cut_out=25.0)
    return np.array([min(count * curve.power_kw(float(v)), capacity_kw) for v in speed_hub])


@app.post("/forecast-window")
def forecast_window(req: WindowRequest):
    net, configs, run_config = load_model(req.model_path)
    if configs.pred_len != req.horizon:
        raise HTTPException(422, f"Model predicts {configs.pred_len} steps, request asks for {req.horizon}")
    model_energy = str(run_config.get("energy-type", "wind")).lower()
    if model_energy != req.energy_type:
        raise HTTPException(422, f"Model '{req.model_path}' is a {model_energy} model, not {req.energy_type}")
    seq_len = configs.seq_len
    if len(req.values) < seq_len:
        raise HTTPException(422, f"The model needs {seq_len} hours of history; the window has {len(req.values)}")
    end = pd.Timestamp(req.end_hour)
    end = (end.tz_convert("UTC").tz_localize(None) if end.tzinfo else end).floor("h")
    values = _fill(req.values[-seq_len:])
    hist_times = pd.DatetimeIndex([end - timedelta(hours=seq_len - 1 - i) for i in range(seq_len)])
    times = pd.DatetimeIndex([end + timedelta(hours=k) for k in range(1, req.horizon + 1)])

    if req.energy_type == "wind":
        y = _predict(net, values, seq_len - 1, seq_len)
        speed = np.clip(y, 0.0, None)
        factor = 1.0
        hub = req.equipment.get("hub_height_m")
        if req.measured_at_m and hub:
            factor = (float(hub) / float(req.measured_at_m)) ** WIND_SHEAR_ALPHA
        power = _wind_power_kw(speed * factor, req.equipment, req.capacity_kw)
        hist_power = _wind_power_kw(values * factor, req.equipment, req.capacity_kw)
        forecast_points = [{"timestamp": _iso(t), "wind_speed": round(float(v), 3), "wind_power_kw": round(float(p), 1)}
                           for t, v, p in zip(times, speed, power)]
        actual = [{"timestamp": _iso(t), "wind_speed": round(float(v), 3), "wind_power_kw": round(float(p), 1)}
                  for t, v, p in list(zip(hist_times, values, hist_power))[-HISTORY_SHOWN_H:]]
        return {"as_of": _iso(end), "unit": "m/s", "actual": actual, "forecast": forecast_points,
                "hub_height_factor": round(factor, 4)}

    opts = solar.options(run_config)
    cs_hist, elev_hist = solar.clear_sky_hourly(hist_times, req.lat, req.lon)
    if opts["target_kind"] == "kstar":
        x = solar.clear_sky_index(values, cs_hist, elev_hist >= opts["min_elevation"], opts["kstar_max"])
    else:
        x = values
    y = _predict(net, x, seq_len - 1, seq_len)
    cs, _ = solar.clear_sky_hourly(times, req.lat, req.lon)
    ghi = solar.forecast_ghi(y, cs, 0.0, 1.0, opts["target_kind"], opts["kstar_max"])
    power = solar.pv_power_kw(ghi, req.capacity_kw, PV_PERFORMANCE_RATIO)
    hist_power = solar.pv_power_kw(values, req.capacity_kw, PV_PERFORMANCE_RATIO)
    forecast_points = [{"timestamp": _iso(t), "ghi": round(float(g), 1), "clear_sky_ghi": round(float(c), 1),
                        "pv_power_kw": round(float(p), 1)} for t, g, c, p in zip(times, ghi, cs, power)]
    actual = [{"timestamp": _iso(t), "ghi": round(float(g), 1), "clear_sky_ghi": round(float(c), 1),
               "pv_power_kw": round(float(p), 1)}
              for t, g, c, p in list(zip(hist_times, values, cs_hist, hist_power))[-HISTORY_SHOWN_H:]]
    return {"as_of": _iso(end), "unit": "W/m2", "actual": actual, "forecast": forecast_points}
