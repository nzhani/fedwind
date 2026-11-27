"""One site's train / val / test windows as arrays, taken from the same Dataset classes the
federated clients use (my_flower_app.task._client_dataset), so splits, scaling and windows match."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from my_flower_app.task import _client_dataset


@dataclass
class Split:
    x: np.ndarray            # [N, seq_len] scaled inputs
    y: np.ndarray            # [N, pred_len] scaled targets
    aux: Optional[np.ndarray] = None   # solar: [N, pred_len, 5] (solar.AUX_*)


@dataclass
class SiteData:
    site: str
    train: Split
    val: Split
    test: Split
    mean: float              # scaler of the site's train part (target column)
    std: float
    train_series: np.ndarray  # scaled train part as one series (ARIMA)
    solar: Optional[dict] = None
    kstar_climatology: Optional[float] = None


def _split(ds, seq_len: int, pred_len: int, stride: int = 1) -> Split:
    series = np.asarray(ds.data_y, dtype=np.float32)
    series = series[:, -1] if series.ndim == 2 else series
    n = len(ds)
    idx = np.arange(0, n, stride)
    x = sliding_window_view(series, seq_len)[: n][idx]
    y = sliding_window_view(series[seq_len:], pred_len)[: n][idx]
    aux = None
    if hasattr(ds, "daylight"):
        aux = np.stack([ds[i][4] for i in idx]).astype(np.float32)
    return Split(np.ascontiguousarray(x), np.ascontiguousarray(y), aux)


def load_site(site: str, cfg, dataset_name: str, data_file: Optional[str] = None, solar: Optional[dict] = None,
              percent: int = 100, test_stride: int = 1) -> SiteData:
    """cfg: build_model_configs(run_config); data_file: the site's CSV (as a deployment client reads it).
    test_stride > 1 keeps every n-th test window (quick runs); every method then uses the same ones."""
    seq, pred = cfg.seq_len, cfg.pred_len
    tr = _client_dataset("train", 0, cfg, dataset_name, data_file, percent, solar)
    va = _client_dataset("val", 0, cfg, dataset_name, data_file, solar=solar)
    te = _client_dataset("test", 0, cfg, dataset_name, data_file, solar=solar)
    train_series = np.asarray(tr.data_y, dtype=np.float32)
    train_series = train_series[:, -1] if train_series.ndim == 2 else train_series
    return SiteData(
        site=site, train=_split(tr, seq, pred), val=_split(va, seq, pred), test=_split(te, seq, pred, test_stride),
        mean=float(tr.scaler.mean_[-1]), std=float(tr.scaler.scale_[-1]), train_series=train_series,
        solar=solar, kstar_climatology=getattr(te, "kstar_climatology", None))
