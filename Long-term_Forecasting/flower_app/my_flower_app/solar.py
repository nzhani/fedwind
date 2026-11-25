"""
Solar irradiance support (FR-01, FR-06, DR-02, DR-03, DR-04).

Same model and federation as wind; what changes is the data around it:

  sun position   computed from the site's coordinates and the UTC time (NOAA formulas)
  clear-sky GHI  Haurwitz model, averaged over each data hour; known for any future hour
  k*             clear-sky index GHI / GHI_cs in daylight, clipped to [0, kstar_max];
                 outside daylight it repeats the last daylight value (causal: no future data)
  daylight       mid-hour sun elevation >= min_elevation (default 5 degrees)

The model forecasts k* (or raw GHI); forecasts become GHI with the clear-sky values of the
target hours, and PV power with a simple plant model. Night hours stay in the series so it
is continuous, but the training loss and the "daylight" metrics leave them out.

NASA POWER hourly irradiance is an average over the hour that starts at the timestamp
(checked against NASA's own clear-sky series: see HOUR_WINDOW_START_MIN).
"""

import os
import re
from typing import Mapping, Optional

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch.utils.data import Dataset

GHI_COLUMN = "ALLSKY_SFC_SW_DWN"
NASA_CLEAR_SKY_COLUMN = "CLRSKY_SFC_SW_DWN"

# The hour a NASA POWER hourly value averages: [t + start, t + start + 60 min).
HOUR_WINDOW_START_MIN = 0.0
SAMPLES_PER_HOUR = 12

# Columns of the per-sample auxiliary array returned by SolarDataset (one row per target hour)
AUX_DAYLIGHT, AUX_GHI_CS, AUX_GHI, AUX_GHI_LAST, AUX_KSTAR_LAST = range(5)

DEFAULTS = {"target_kind": "kstar", "daylight_mask": True, "min_elevation": 5.0, "kstar_max": 1.2}


# ---------------------------------------------------------------------------
# Sun position and clear sky
# ---------------------------------------------------------------------------

def sun_elevation(times_utc, lat: float, lon: float) -> np.ndarray:
    """Solar elevation angle in degrees (NOAA general solar position equations, ~0.5 deg)."""
    t = pd.DatetimeIndex(times_utc)
    if t.tz is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    doy = t.dayofyear.to_numpy(dtype=float)
    hours = t.hour.to_numpy(dtype=float) + t.minute.to_numpy(dtype=float) / 60 + t.second.to_numpy(dtype=float) / 3600
    days_in_year = np.where(t.is_leap_year, 366.0, 365.0)
    g = 2 * np.pi / days_in_year * (doy - 1 + (hours - 12) / 24)

    eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                       - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    true_solar_min = hours * 60 + eqtime + 4 * lon
    hour_angle = np.radians(true_solar_min / 4 - 180)
    phi = np.radians(lat)
    cos_zen = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(hour_angle)
    return 90 - np.degrees(np.arccos(np.clip(cos_zen, -1, 1)))


def haurwitz_ghi(elevation_deg) -> np.ndarray:
    """Clear-sky GHI in W/m2 from the sun elevation (Haurwitz 1945); 0 when the sun is down."""
    cos_zen = np.sin(np.radians(np.asarray(elevation_deg, dtype=float)))
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        ghi = 1098.0 * cos_zen * np.exp(-0.059 / cos_zen)
    return np.where(cos_zen > 0, ghi, 0.0)


def clear_sky_hourly(times_utc, lat: float, lon: float,
                     window_start_min: float = HOUR_WINDOW_START_MIN,
                     samples: int = SAMPLES_PER_HOUR):
    """
    (clear-sky GHI averaged over each data hour, sun elevation at the middle of that hour).
    Only depends on time and place, so it is known for future hours too (DR-04).
    """
    t = pd.DatetimeIndex(times_utc)
    offsets = window_start_min + (np.arange(samples) + 0.5) * 60.0 / samples
    ghi = np.zeros(len(t))
    for off in offsets:
        ghi += haurwitz_ghi(sun_elevation(t + pd.to_timedelta(off, unit="min"), lat, lon))
    mid = sun_elevation(t + pd.to_timedelta(window_start_min + 30.0, unit="min"), lat, lon)
    return ghi / samples, mid


# ---------------------------------------------------------------------------
# Site data
# ---------------------------------------------------------------------------

_LOCATION = re.compile(r"Latitude\s+(-?\d+(?:\.\d+)?)\s+Longitude\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE)


def read_nasa_location(path: str):
    """(lat, lon) from the 'Location:' line of a NASA POWER CSV header."""
    with open(path, "r", errors="ignore") as f:
        for line in f:
            m = _LOCATION.search(line)
            if m:
                return float(m.group(1)), float(m.group(2))
            if "-END HEADER-" in line:
                break
    raise ValueError(f"{path}: no 'Location: Latitude .. Longitude ..' line in the NASA POWER header")


def solar_frame(path: str, min_elevation: float = 5.0, kstar_max: float = 1.2) -> pd.DataFrame:
    """
    One site's hourly series with everything solar needs:
      date (UTC), GHI, GHI_CS, ELEV, DAYLIGHT (0/1), KSTAR, plus NASA's own clear-sky GHI if present.
    """
    from my_flower_app.dataloader import preprocess_nasa_data  # avoid an import cycle

    lat, lon = read_nasa_location(path)
    raw = preprocess_nasa_data(path, GHI_COLUMN)
    out = pd.DataFrame({"date": pd.to_datetime(raw["date"])})
    out["GHI"] = raw[GHI_COLUMN].clip(lower=0).to_numpy(dtype=float)
    if NASA_CLEAR_SKY_COLUMN in raw.columns:
        out["NASA_GHI_CS"] = raw[NASA_CLEAR_SKY_COLUMN].clip(lower=0).to_numpy(dtype=float)
    ghi_cs, elev = clear_sky_hourly(out["date"], lat, lon)
    out["GHI_CS"] = ghi_cs
    out["ELEV"] = elev
    out["DAYLIGHT"] = (elev >= min_elevation).astype(float)
    out["KSTAR"] = clear_sky_index(out["GHI"].to_numpy(), ghi_cs, out["DAYLIGHT"].to_numpy() > 0.5, kstar_max)
    out.attrs.update(lat=lat, lon=lon)
    return out


def clear_sky_index(ghi, ghi_cs, daylight, kstar_max: float = 1.2) -> np.ndarray:
    """k* = GHI / GHI_cs in daylight, clipped; other hours repeat the last daylight value."""
    ghi, ghi_cs, daylight = np.asarray(ghi, float), np.asarray(ghi_cs, float), np.asarray(daylight, bool)
    k = np.full(len(ghi), np.nan)
    ok = daylight & (ghi_cs > 0)
    k[ok] = np.clip(ghi[ok] / ghi_cs[ok], 0.0, kstar_max)
    k = pd.Series(k).ffill()
    # Only the very first night of the file has no earlier daylight hour
    first = k.first_valid_index()
    return k.fillna(k[first] if first is not None else 1.0).to_numpy()


# ---------------------------------------------------------------------------
# From forecast to irradiance and power
# ---------------------------------------------------------------------------

def kstar_to_ghi(kstar, ghi_cs, kstar_max: float = 1.2) -> np.ndarray:
    """Forecast GHI = clipped k* x clear-sky GHI; zero when the sun is down (DR-02)."""
    ghi_cs = np.asarray(ghi_cs, float)
    return np.clip(np.asarray(kstar, float), 0.0, kstar_max) * np.clip(ghi_cs, 0.0, None)


def pv_power_kw(ghi, capacity_kw: float, performance_ratio: float = 0.8) -> np.ndarray:
    """
    Simple PV plant: AC power = capacity x GHI / 1000 W/m2 x performance ratio,
    never negative, never above capacity (DR-02, DR-03).
    """
    p = capacity_kw * np.asarray(ghi, float) / 1000.0 * performance_ratio
    return np.clip(p, 0.0, capacity_kw)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class SolarDataset(Dataset):
    """
    One site's split (70 / 10 / 20 by time, like wind) of the solar target.

    Items: (x, y, x_mark, y_mark, aux)
      x, y      scaled target (k* or GHI), shapes [seq_len, 1] and [label_len + pred_len, 1]
      aux       [pred_len, 5] for the target hours: daylight flag, clear-sky GHI, true GHI,
                last observed GHI and last k* at issue time (for the baselines)
    """

    def __init__(self, root_path: str, flag: str = "train", size=(336, 48, 72), data_path: str = "",
                 target_kind: str = "kstar", percent: int = 100, min_elevation: float = 5.0,
                 kstar_max: float = 1.2, **_ignored):
        if target_kind not in ("kstar", "ghi"):
            raise ValueError(f"solar target must be 'kstar' or 'ghi', got {target_kind!r}")
        self.seq_len, self.label_len, self.pred_len = size
        self.target_kind, self.kstar_max = target_kind, kstar_max

        frame = solar_frame(os.path.join(root_path, data_path), min_elevation, kstar_max)
        n = len(frame)
        num_train, num_test = int(n * 0.7), int(n * 0.2)
        num_vali = n - num_train - num_test
        border1s = [0, num_train - self.seq_len, n - num_test - self.seq_len]
        border2s = [num_train, num_train + num_vali, n]
        set_type = {"train": 0, "val": 1, "test": 2}[flag]
        b1, b2 = border1s[set_type], border2s[set_type]
        if set_type == 0:
            b2 = (b2 - self.seq_len) * percent // 100 + self.seq_len

        series = frame["KSTAR" if target_kind == "kstar" else "GHI"].to_numpy(dtype=float).reshape(-1, 1)
        self.scaler = StandardScaler().fit(series[: border2s[0]])
        data = self.scaler.transform(series)
        self.data_x = data[b1:b2]
        self.data_y = data[b1:b2]

        dates = frame["date"].iloc[b1:b2]
        self.dates = dates.reset_index(drop=True)
        self.data_stamp = np.stack([dates.dt.month, dates.dt.day, dates.dt.weekday, dates.dt.hour], axis=1)

        self.daylight = frame["DAYLIGHT"].to_numpy(float)[b1:b2]
        self.ghi_cs = frame["GHI_CS"].to_numpy(float)[b1:b2]
        self.ghi = frame["GHI"].to_numpy(float)[b1:b2]
        self.kstar = frame["KSTAR"].to_numpy(float)[b1:b2]

        train_day = frame["DAYLIGHT"].to_numpy()[:num_train] > 0.5
        self.kstar_climatology = float(frame["KSTAR"].to_numpy()[:num_train][train_day].mean())
        self.mean_daylight_ghi = float(frame["GHI"].to_numpy()[:num_train][train_day].mean())
        self.lat, self.lon = frame.attrs["lat"], frame.attrs["lon"]

    def __len__(self):
        return max(0, len(self.data_x) - self.seq_len - self.pred_len + 1)

    def __getitem__(self, i):
        s_end = i + self.seq_len
        r_begin = s_end - self.label_len
        r_end = s_end + self.pred_len
        tgt = slice(s_end, r_end)
        aux = np.stack([
            self.daylight[tgt],
            self.ghi_cs[tgt],
            self.ghi[tgt],
            np.full(self.pred_len, self.ghi[s_end - 1]),
            np.full(self.pred_len, self.kstar[s_end - 1]),
        ], axis=1).astype(np.float32)
        return (self.data_x[i:s_end], self.data_y[r_begin:r_end],
                self.data_stamp[i:s_end], self.data_stamp[r_begin:r_end], aux)

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)


# ---------------------------------------------------------------------------
# Training loss and evaluation
# ---------------------------------------------------------------------------

def masked_mse(pred: torch.Tensor, true: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Mean squared error over daylight target hours only (mask 1 = daylight)."""
    mask = mask.to(pred.dtype)
    return ((pred - true) ** 2 * mask).sum() / mask.sum().clamp(min=1.0)


def options(run_config: Mapping) -> Optional[dict]:
    """Solar settings of a run, or None for wind runs."""
    if str(run_config.get("energy-type", "wind")).lower() != "solar":
        return None
    return {
        "target_kind": str(run_config.get("solar-target", DEFAULTS["target_kind"])).lower(),
        "daylight_mask": bool(run_config.get("daylight-mask", DEFAULTS["daylight_mask"])),
        "min_elevation": float(run_config.get("min-elevation", DEFAULTS["min_elevation"])),
        "kstar_max": float(run_config.get("kstar-max", DEFAULTS["kstar_max"])),
    }


def _errors(forecast: np.ndarray, truth: np.ndarray, day: np.ndarray) -> dict:
    d = forecast - truth
    out = {"mae_all": float(np.mean(np.abs(d))), "rmse_all": float(np.sqrt(np.mean(d ** 2))),
           "mbe_all": float(np.mean(d))}
    if day.any():
        dd = d[day]
        out.update(mae=float(np.mean(np.abs(dd))), rmse=float(np.sqrt(np.mean(dd ** 2))), mbe=float(np.mean(dd)))
    else:
        out.update(mae=float("nan"), rmse=float("nan"), mbe=float("nan"))
    return out


def forecast_ghi(pred_scaled: np.ndarray, ghi_cs: np.ndarray, mean: float, std: float,
                 target_kind: str, kstar_max: float) -> np.ndarray:
    """Scaled model output -> GHI in W/m2 for the target hours (0 when the sun is down)."""
    raw = np.asarray(pred_scaled, float) * std + mean
    if target_kind == "kstar":
        return kstar_to_ghi(raw, ghi_cs, kstar_max)
    return np.where(np.asarray(ghi_cs) > 0, np.clip(raw, 0.0, None), 0.0)


def evaluate_ghi(preds_scaled: np.ndarray, aux: np.ndarray, mean: float, std: float, target_kind: str,
                 kstar_max: float, kstar_climatology: float) -> dict:
    """
    Errors in W/m2 of the model and three baselines on the same windows, for daylight hours
    (mae, rmse, mbe) and for all hours (*_all):
      persistence        last observed GHI repeated
      smart_persistence  last k* x clear-sky GHI of each target hour (main reference)
      climatology        mean daylight k* of the train split x clear-sky GHI
    """
    preds = np.asarray(preds_scaled, float).reshape(aux.shape[0], aux.shape[1])
    day = aux[..., AUX_DAYLIGHT] > 0.5
    cs, truth = aux[..., AUX_GHI_CS], aux[..., AUX_GHI]
    candidates = {
        "model": forecast_ghi(preds, cs, mean, std, target_kind, kstar_max),
        "persistence": aux[..., AUX_GHI_LAST],
        "smart_persistence": kstar_to_ghi(aux[..., AUX_KSTAR_LAST], cs, kstar_max),
        "climatology": kstar_to_ghi(np.full_like(cs, kstar_climatology), cs, kstar_max),
    }
    out = {name: _errors(f, truth, day) for name, f in candidates.items()}
    out["mean_daylight_ghi"] = float(truth[day].mean()) if day.any() else float("nan")
    return out
