"""
Extra test metrics computed on each client (requirements DR-06, FR-06/DR-08, DR-07).

Power errors normalised by installed capacity (DR-06)
  The model forecasts wind speed (m/s) or irradiance (W/m2). For comparable power errors every
  forecast and observation is converted with the same reference unit the website uses for lab
  sites: a generic 2 MW turbine (cut-in 3, rated 12, cut-out 25 m/s; inference/power_curve.py) or a
  1 MW PV plant with performance ratio 0.8. nMAE and nRMSE are divided by that capacity, over all
  test hours (night and calm hours included, as is usual for capacity-normalised errors).

Errors by lead time (FR-06, DR-08)
  The requirements name 1 h, 6 h and 24 h horizons; the platform trains 1 h, 72 h and 432 h
  models. A 72 h forecast contains the 6 h and 24 h values, so the test errors at those lead
  times are reported separately, each with persistence at the same lead (smart persistence and
  daylight hours for solar) and the skill against it.

All functions take arrays in physical units, shaped [windows, pred_len].
"""

from typing import Dict, Iterable, Optional

import numpy as np

LEADS = (1, 6, 24)
TURBINE = {"rated_kw": 2000.0, "cut_in": 3.0, "rated_speed": 12.0, "cut_out": 25.0}
PV_CAPACITY_KW = 1000.0
PV_PERFORMANCE_RATIO = 0.8


def wind_power_kw(
    speed,
    rated_kw=TURBINE["rated_kw"],
    cut_in=TURBINE["cut_in"],
    rated_speed=TURBINE["rated_speed"],
    cut_out=TURBINE["cut_out"],
) -> np.ndarray:
    """Vectorised version of inference/power_curve.PowerCurve.power_kw (DR-01, DR-03)."""
    v = np.asarray(speed, float)
    frac = (v**3 - cut_in**3) / (rated_speed**3 - cut_in**3)
    p = rated_kw * np.clip(frac, 0.0, 1.0)
    p = np.where(v >= rated_speed, rated_kw, p)
    return np.where((v < cut_in) | (v >= cut_out), 0.0, p)


def pv_power_kw(ghi, capacity_kw=PV_CAPACITY_KW, performance_ratio=PV_PERFORMANCE_RATIO) -> np.ndarray:
    """Same as solar.pv_power_kw: capacity x GHI / 1000 x PR, within [0, capacity]."""
    return np.clip(capacity_kw * np.asarray(ghi, float) / 1000.0 * performance_ratio, 0.0, capacity_kw)


def power_errors(pred_kw, true_kw, capacity_kw: float) -> Dict[str, float]:
    d = np.asarray(pred_kw, float) - np.asarray(true_kw, float)
    if d.size == 0:
        return {}
    mae, rmse = float(np.mean(np.abs(d))), float(np.sqrt(np.mean(d**2)))
    return {
        "power_mae_kw": mae,
        "power_rmse_kw": rmse,
        "power_nmae": mae / capacity_kw,
        "power_nrmse": rmse / capacity_kw,
        "power_capacity_kw": float(capacity_kw),
    }


def lead_errors(
    pred, true, reference, leads: Iterable[int] = LEADS, mask=None, skill_on: str = "mae"
) -> Dict[str, float]:
    """Flat metrics per lead h (1-based hours ahead) that fit in the horizon:
    test_mae_real_h{h}, test_rmse_real_h{h}, ref_mae_real_h{h}, ref_rmse_real_h{h}, skill_h{h}.
    mask (same shape, bool) keeps only some hours, e.g. daylight for solar."""
    pred, true, reference = (np.asarray(a, float) for a in (pred, true, reference))
    out: Dict[str, float] = {}
    for h in leads:
        if h > pred.shape[1]:
            continue
        i = h - 1
        p, t, r = pred[:, i], true[:, i], reference[:, i]
        if mask is not None:
            keep = np.asarray(mask, bool)[:, i]
            p, t, r = p[keep], t[keep], r[keep]
        if p.size == 0:
            continue
        mae, rmse = float(np.mean(np.abs(p - t))), float(np.sqrt(np.mean((p - t) ** 2)))
        rmae, rrmse = float(np.mean(np.abs(r - t))), float(np.sqrt(np.mean((r - t) ** 2)))
        out.update(
            {
                f"test_mae_real_h{h}": mae,
                f"test_rmse_real_h{h}": rmse,
                f"ref_mae_real_h{h}": rmae,
                f"ref_rmse_real_h{h}": rrmse,
            }
        )
        base, ref = (mae, rmae) if skill_on == "mae" else (rmse, rrmse)
        if ref > 0:
            out[f"skill_h{h}"] = 1.0 - base / ref
    return out


def wind_extras(preds_real, trues_real, last_real) -> Dict[str, float]:
    """Wind: power errors of the reference turbine and errors by lead vs persistence (MAE skill)."""
    preds_real, trues_real = np.asarray(preds_real, float), np.asarray(trues_real, float)
    persistence = np.repeat(np.asarray(last_real, float).reshape(-1, 1), preds_real.shape[1], axis=1)
    out = power_errors(wind_power_kw(preds_real), wind_power_kw(trues_real), TURBINE["rated_kw"])
    out.update(lead_errors(preds_real, trues_real, persistence, skill_on="mae"))
    return out


def solar_extras(model_ghi, true_ghi, smart_persistence_ghi, daylight) -> Dict[str, float]:
    """Solar: power errors of the reference 1 MW PV plant (all hours) and errors by lead vs smart
    persistence on daylight hours (RMSE skill, the solar convention)."""
    out = power_errors(pv_power_kw(model_ghi), pv_power_kw(true_ghi), PV_CAPACITY_KW)
    out.update(lead_errors(model_ghi, true_ghi, smart_persistence_ghi, mask=daylight, skill_on="rmse"))
    return out


def last_inputs(loader) -> Optional[np.ndarray]:
    """The last observed (scaled) value of every window, in loader order (persistence)."""
    import torch

    out = []
    for batch in loader:
        x = batch["x"] if isinstance(batch, dict) else batch[0]
        out.append(torch.as_tensor(x).float()[:, -1, -1].numpy())
    return np.concatenate(out) if out else None
