"""The baseline methods. Each returns {site: scaled predictions [N, pred_len] for its test windows}."""

import copy
import logging
import warnings
from dataclasses import dataclass
from typing import Callable, Dict, List

import numpy as np
import torch
from torch import nn

from baselines.data import SiteData, Split
from baselines.models import LSTMForecaster, PatchTST
from my_flower_app.solar import AUX_DAYLIGHT, AUX_GHI_CS, AUX_KSTAR_LAST, kstar_to_ghi

log = logging.getLogger("baselines")


@dataclass
class TrainSettings:
    epochs: int = 30
    lr: float = 1e-3
    batch_size: int = 256
    eval_batch_size: int = 1024      # LLM baselines: small (GPT-2 activations over every patch)
    patience: int = 5
    weight_decay: float = 1e-4
    # FedAvg
    rounds: int = 20
    local_epochs: int = 2


# ---------------------------------------------------------------------------
# Persistence and ARIMA
# ---------------------------------------------------------------------------

def persistence(sites: List[SiteData], **_) -> Dict[str, np.ndarray]:
    """Wind: last value repeated. Solar: smart persistence (k* now x clear sky of each target hour),
    expressed in the target the model forecasts (k* or GHI)."""
    out = {}
    for s in sites:
        if s.solar is None:
            out[s.site] = np.repeat(s.test.x[:, -1:], s.test.y.shape[1], axis=1)
        else:
            aux = s.test.aux
            k_last = aux[..., AUX_KSTAR_LAST]
            raw = k_last if s.solar["target_kind"] == "kstar" else kstar_to_ghi(k_last, aux[..., AUX_GHI_CS],
                                                                                 s.solar["kstar_max"])
            out[s.site] = (raw - s.mean) / s.std
    return out


def arima(sites: List[SiteData], order=(2, 0, 1), fit_hours: int = 24 * 365, **_) -> Dict[str, np.ndarray]:
    """ARIMA(order) per site: parameters fitted once on the last `fit_hours` of the train part, then
    applied unchanged (no refit) to each test window, which is forecast `pred_len` steps ahead."""
    from statsmodels.tsa.arima.model import ARIMA

    out = {}
    for s in sites:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = ARIMA(s.train_series[-fit_hours:].astype(float), order=order, trend="c").fit()
            h = s.test.y.shape[1]
            preds = np.empty_like(s.test.y, dtype=float)
            for i, window in enumerate(s.test.x):
                preds[i] = res.apply(window.astype(float)).forecast(h)
        log.info("arima %s: %s fitted, %d windows", s.site, order, len(preds))
        out[s.site] = preds
    return out


# ---------------------------------------------------------------------------
# Neural baselines
# ---------------------------------------------------------------------------

def _tensors(split: Split, solar: bool):
    x, y = torch.from_numpy(split.x), torch.from_numpy(split.y)
    w = torch.from_numpy(split.aux[..., AUX_DAYLIGHT]) if solar and split.aux is not None else torch.ones_like(y)
    return x, y, w


def _loss(model, x, y, w):
    """MSE; for solar only daylight target hours count (as the federated model's masked loss)."""
    err = (model(x) - y) ** 2 * w
    return err.sum() / w.sum().clamp(min=1.0)


def _epoch(model, splits: List[Split], solar: bool, opt, settings: TrainSettings, device):
    model.train()
    x = torch.cat([_tensors(s, solar)[0] for s in splits])
    y = torch.cat([_tensors(s, solar)[1] for s in splits])
    w = torch.cat([_tensors(s, solar)[2] for s in splits])
    order = torch.randperm(len(x))
    for i in range(0, len(x), settings.batch_size):
        b = order[i: i + settings.batch_size]
        opt.zero_grad()
        loss = _loss(model, x[b].to(device), y[b].to(device), w[b].to(device))
        loss.backward()
        opt.step()


@torch.no_grad()
def _val_loss(model, splits: List[Split], solar: bool, device, batch: int = 1024) -> float:
    model.eval()
    total, weight = 0.0, 0.0
    for s in splits:
        x, y, w = _tensors(s, solar)
        for i in range(0, len(x), batch):
            xb, yb, wb = x[i: i + batch].to(device), y[i: i + batch].to(device), w[i: i + batch].to(device)
            total += float((((model(xb) - yb) ** 2) * wb).sum())
            weight += float(wb.sum())
    return total / max(weight, 1.0)


@torch.no_grad()
def predict(model, split: Split, device, batch: int = 1024) -> np.ndarray:
    model.eval()
    x = torch.from_numpy(split.x)
    return np.concatenate([model(x[i: i + batch].to(device)).cpu().numpy() for i in range(0, len(x), batch)])


def _optimizer(model, settings: TrainSettings):
    return torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=settings.lr,
                             weight_decay=settings.weight_decay)


def fit(model, train: List[Split], val: List[Split], solar: bool, settings: TrainSettings, device):
    """Train with early stopping on the validation loss; returns the best model."""
    model.to(device)
    opt = _optimizer(model, settings)
    best, best_state, bad = float("inf"), None, 0
    for epoch in range(settings.epochs):
        _epoch(model, train, solar, opt, settings, device)
        v = _val_loss(model, val, solar, device, settings.eval_batch_size)
        if v < best:
            best, best_state, bad = v, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= settings.patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model


def fedavg(make: Callable[[], nn.Module], sites: List[SiteData], settings: TrainSettings, device) -> nn.Module:
    """FedAvg simulated in one process: every round each site trains a copy of the global model for
    `local_epochs` on its own train part; the server averages the weights by number of windows.
    Early stopping on the mean of the sites' validation losses, as in the federated runs."""
    solar = sites[0].solar is not None
    global_model = make().to(device)
    best, best_state, bad = float("inf"), None, 0
    for r in range(settings.rounds):
        states, counts = [], []
        for s in sites:
            local = copy.deepcopy(global_model)
            opt = _optimizer(local, settings)
            for _ in range(settings.local_epochs):
                _epoch(local, [s.train], solar, opt, settings, device)
            states.append({k: v.detach().float() for k, v in local.state_dict().items()})
            counts.append(len(s.train.x))
        total = float(sum(counts))
        global_model.load_state_dict({k: sum(st[k] * (n / total) for st, n in zip(states, counts))
                                      for k in states[0]})
        v = float(np.mean([_val_loss(global_model, [s.val], solar, device, settings.eval_batch_size) for s in sites]))
        log.info("fedavg round %d: mean val loss %.5f", r + 1, v)
        if v < best:
            best, best_state, bad = v, copy.deepcopy(global_model.state_dict()), 0
        else:
            bad += 1
            if bad >= settings.patience:
                break
    global_model.load_state_dict(best_state)
    return global_model


class LLMAdapter(nn.Module):
    """The federated model's own architecture (my_flower_app.task.Net: frozen GPT-2 + LoRA) behind the
    baselines' [B, seq_len] -> [B, pred_len] interface."""

    def __init__(self, cfg, device):
        super().__init__()
        from my_flower_app.task import Net

        self.net = Net(device=device, configs=cfg)
        self.pred_len = cfg.pred_len

    def forward(self, x):
        return self.net(x.unsqueeze(-1))[:, -self.pred_len:, 0]


def neural(kind: str, scope: str, sites: List[SiteData], cfg, settings: TrainSettings, device,
           **_) -> Dict[str, np.ndarray]:
    """kind: lstm | patchtst | llm; scope: local (one model per site) | central (pooled) | fedavg."""
    seq, pred = cfg.seq_len, cfg.pred_len
    solar = sites[0].solar is not None

    def make():
        if kind == "lstm":
            return LSTMForecaster(pred)
        if kind == "patchtst":
            return PatchTST(seq, pred)
        return LLMAdapter(cfg, device)

    if scope == "local":
        return {s.site: predict(fit(make(), [s.train], [s.val], solar, settings, device), s.test, device,
                                settings.eval_batch_size)
                for s in sites}
    if scope == "central":
        model = fit(make(), [s.train for s in sites], [s.val for s in sites], solar, settings, device)
    elif scope == "fedavg":
        model = fedavg(make, sites, settings, device)
    else:
        raise ValueError(f"unknown scope {scope}")
    return {s.site: predict(model, s.test, device, settings.eval_batch_size) for s in sites}


METHODS = {
    "persistence": lambda sites, **kw: persistence(sites),
    "arima": lambda sites, **kw: arima(sites, order=kw.get("arima_order", (2, 0, 1)),
                                       fit_hours=kw.get("arima_fit_hours", 24 * 365)),
    **{f"{kind}_{scope}": (lambda kind, scope: lambda sites, **kw: neural(kind, scope, sites, **kw))(kind, scope)
       for kind, scopes in (("lstm", ("local", "central", "fedavg")), ("patchtst", ("local", "central")),
                            ("llm", ("local", "central")))
       for scope in scopes},
}
