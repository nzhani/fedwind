"""
Per-site inference service (plan T3.2, T3.4).

One instance per site, next to that site's data: it mounts only /data (this site's
folder) and /models (promoted checkpoints), both read-only. The API calls

  POST /forecast  {"horizon": 72, "as_of": "<ISO UTC or null>", "model_path": "wind/h72/current.pt"}

and gets back the actual wind speed around the issue time and the model's forecast
for the next `horizon` hours, in m/s, plus power from a reference turbine curve.
History is the `seq_len` hours up to and including `as_of` (DR-04).

Env: SITE_ID, DATA_ROOT=/data, MODELS_ROOT=/models, TURBINE_RATED_KW, TURBINE_CUT_IN,
TURBINE_RATED_SPEED, TURBINE_CUT_OUT. Needs Long-term_Forecasting and its flower_app
on PYTHONPATH and FEDWIND_ML_ROOT set (the Flower image does this).
"""

import os
import threading
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sklearn.preprocessing import StandardScaler

from my_flower_app.dataloader import preprocess_nasa_data
from my_flower_app.experiment import build_model_configs
from my_flower_app.task import Net, get_dataset_config

from power_curve import PowerCurve

SITE_ID = os.environ.get("SITE_ID", "")
DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/data"))
MODELS_ROOT = Path(os.environ.get("MODELS_ROOT", "/models"))
HISTORY_SHOWN_H = 48  # actual values shown before the issue time

CURVE = PowerCurve(
    rated_kw=float(os.environ.get("TURBINE_RATED_KW", 2000)),
    cut_in=float(os.environ.get("TURBINE_CUT_IN", 3)),
    rated_speed=float(os.environ.get("TURBINE_RATED_SPEED", 12)),
    cut_out=float(os.environ.get("TURBINE_CUT_OUT", 25)),
)

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


@lru_cache(maxsize=1)
def site_series() -> SiteSeries:
    path = DATA_ROOT / f"nasa_{SITE_ID}.csv"
    if not path.is_file():
        raise HTTPException(503, f"Data file for site '{SITE_ID}' not found at {path}")
    return SiteSeries(path, get_dataset_config("KZMET")["target"])


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
            _models[key] = (net, configs)
        return _models[key]


def _iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


@app.get("/health")
def health():
    return {
        "site": SITE_ID,
        "data": (DATA_ROOT / f"nasa_{SITE_ID}.csv").is_file(),
        "models": sorted(str(p.relative_to(MODELS_ROOT)) for p in MODELS_ROOT.glob("*/h*/current.pt")) if MODELS_ROOT.is_dir() else [],
    }


@app.post("/forecast")
def forecast(req: ForecastRequest):
    series = site_series()
    net, configs = load_model(req.model_path)
    if configs.pred_len != req.horizon:
        raise HTTPException(422, f"Model predicts {configs.pred_len} steps, request asks for {req.horizon}")
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
