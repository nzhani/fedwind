"""Test metrics of a baseline's predictions, as the same keys a federated client reports, then
summarised by the same code as federated runs (run_logging.site_summary / overall_real)."""

from typing import Dict

import numpy as np

from my_flower_app import evaluation
from my_flower_app.solar import (AUX_DAYLIGHT, AUX_GHI, AUX_GHI_CS, AUX_KSTAR_LAST, evaluate_ghi, forecast_ghi,
                                 kstar_to_ghi)
from baselines.data import SiteData


def client_metrics(site: SiteData, preds_scaled: np.ndarray) -> Dict[str, float]:
    """preds_scaled: [N, pred_len] for the site's test windows, in the scaled target units."""
    preds = np.asarray(preds_scaled, float).reshape(site.test.y.shape)
    if site.solar is not None:
        return _solar(site, preds)
    std, mean = site.std, site.mean
    pred_r, true_r = preds * std + mean, site.test.y * std + mean
    last_r = site.test.x[:, -1] * std + mean
    d, p = pred_r - true_r, last_r[:, None] - true_r
    out = {
        "test_mae_real": float(np.mean(np.abs(d))), "test_rmse_real": float(np.sqrt(np.mean(d ** 2))),
        "test_mean_real": float(np.mean(true_r)),
        "persistence_mae_real": float(np.mean(np.abs(p))), "persistence_rmse_real": float(np.sqrt(np.mean(p ** 2))),
    }
    out.update(evaluation.wind_extras(pred_r, true_r, last_r))
    return out


def _solar(site: SiteData, preds: np.ndarray) -> Dict[str, float]:
    s, aux = site.solar, site.test.aux
    ghi = evaluate_ghi(preds, aux, site.mean, site.std, s["target_kind"], s["kstar_max"], site.kstar_climatology)
    cs = aux[..., AUX_GHI_CS]
    out = {
        "test_mae_real": ghi["model"]["mae"], "test_rmse_real": ghi["model"]["rmse"], "test_mbe_real": ghi["model"]["mbe"],
        "test_mae_all_real": ghi["model"]["mae_all"], "test_rmse_all_real": ghi["model"]["rmse_all"],
        "test_mean_real": ghi["mean_daylight_ghi"],
        "persistence_mae_real": ghi["smart_persistence"]["mae"], "persistence_rmse_real": ghi["smart_persistence"]["rmse"],
        "plain_persistence_mae_real": ghi["persistence"]["mae"], "plain_persistence_rmse_real": ghi["persistence"]["rmse"],
        "climatology_mae_real": ghi["climatology"]["mae"], "climatology_rmse_real": ghi["climatology"]["rmse"],
    }
    out.update(evaluation.solar_extras(
        forecast_ghi(preds, cs, site.mean, site.std, s["target_kind"], s["kstar_max"]), aux[..., AUX_GHI],
        kstar_to_ghi(aux[..., AUX_KSTAR_LAST], cs, s["kstar_max"]), aux[..., AUX_DAYLIGHT] > 0.5))
    return out
