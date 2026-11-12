"""
One place that turns the Flower run config into model configs (plan T1.3, bug 1).

The server, client train and client evaluate all call build_model_configs(run_config),
so the backbone (pretrained or not) and every architecture setting are identical on
both sides. Checkpoints store the run config, so inference rebuilds the same model.

Also: seeding (bug 8) and where a client finds its own data (T1.4).
"""

import os
import random
from types import SimpleNamespace
from typing import Mapping, Optional

import numpy as np
import torch

from my_flower_app.task import get_default_configs

# run-config key -> (get_default_configs argument, default)
_MODEL_KEYS = {
    "pred-len": ("pred_len", 120),
    "model": ("model", "gpt4ts_nonlinear"),
    "seq-len": ("seq_len", 336),
    "patch-size": ("patch_size", 4),
    "stride": ("stride", 1),
    "d-model": ("d_model", 768),
    "hidden-size": ("hidden_size", 16),
    "kernel-size": ("kernel_size", 3),
    "llm-layers": ("llm_layers", 4),
    "peft-method": ("peft_method", "lora"),
    "lora-r": ("lora_r", 8),
    "lora-alpha": ("lora_alpha", 16),
    "lora-dropout": ("lora_dropout", 0.15),
    "dropout": ("dropout", 0.15),
    "is-pretrained": ("is_pretrained", True),
    "label-len": ("label_len", 48),
    "enc-in": ("enc_in", 1),
    "dec-in": ("dec_in", 1),
    "c-out": ("c_out", 1),
    "embed-type": ("embed_type", 0),
    "embed": ("embed", "timeF"),
    "freq": ("freq", "h"),
    "factor": ("factor", 1),
    "n-heads": ("n_heads", 4),
    "e-layers": ("e_layers", 2),
    "d-layers": ("d_layers", 1),
    "d-ff": ("d_ff", 512),
    "distil": ("distil", True),
    "activation": ("activation", "gelu"),
    "output-attention": ("output_attention", False),
    "fc-dropout": ("fc_dropout", 0.05),
    "head-dropout": ("head_dropout", 0.0),
    "patch-len": ("patch_len", 16),
    "padding-patch": ("padding_patch", "end"),
    "revin": ("revin", 1),
    "affine": ("affine", 0),
    "subtract-last": ("subtract_last", 0),
    "decomposition": ("decomposition", 0),
    "individual": ("individual", 0),
}


def build_model_configs(run_config: Mapping) -> SimpleNamespace:
    """Model configs from the run config; the only way server and clients build Net."""
    kwargs = {arg: run_config.get(key, default) for key, (arg, default) in _MODEL_KEYS.items()}
    adalora = run_config.get("adalora-total-step", -1)
    kwargs["adalora_total_step"] = None if adalora is None or adalora < 0 else adalora
    return get_default_configs(**kwargs)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def site_names(run_config: Mapping) -> list[str]:
    """Sites selected for this run, in partition-id order ("" -> no selection)."""
    raw = str(run_config.get("site-names", "") or "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def client_data_file(node_config: Mapping, run_config: Mapping) -> Optional[str]:
    """
    The one CSV this client may read, or None in simulation mode (registry by partition id).

    Deployment mode: each SuperNode gets `data-root` (its own mounted folder) and `site`
    through --node-config. The run picks built-in data or this run's upload.
    """
    root = node_config.get("data-root")
    if not root:
        return None
    site = node_config["site"]
    if run_config.get("data-source", "builtin") == "upload":
        path = os.path.join(root, "uploads", f"{run_config['run-id']}.csv")
    else:
        path = os.path.join(root, f"nasa_{site}.csv")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Site '{site}': data file {path} not found")
    return path


def is_selected(node_config: Mapping, run_config: Mapping) -> bool:
    """False when the run names its sites and this client's site isn't one of them."""
    selected = site_names(run_config)
    site = node_config.get("site")
    return not selected or site is None or site in selected
