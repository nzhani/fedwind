
"""my-flower-app: A Flower / PyTorch app."""
import copy
import json
import pickle
import torch
import pandas as pd
import time
import sys
import numpy as np
from datetime import datetime
from collections import defaultdict
from flwr.app import ArrayRecord, ConfigRecord, Context, MetricRecord
from flwr.serverapp import Grid, ServerApp
from flwr.serverapp.strategy import FedAvg

import logging

logging.basicConfig(level=logging.INFO, format= '%(asctime)s - %(levelname)s - %(message)s')

from my_flower_app.task import get_default_configs, Net, trainable_state_dict

app = ServerApp()


def get_model_size_mb(arrays: ArrayRecord) -> float:
    """
    Calculate the size of model parameters in MB.

    Args:
        arrays: ArrayRecord containing model parameters

    Returns:
        Size in megabytes (MB)
    """
    state_dict = arrays.to_torch_state_dict()
    total_bytes = 0
    for param in state_dict.values():
        # Get size in bytes: num_elements * bytes_per_element
        total_bytes += param.numel() * param.element_size()

    # Convert bytes to MB
    size_mb = total_bytes / (1024 * 1024)
    return size_mb


def _personalization_keys_for_model(model_name: str):
    """Return per-backbone personalization keys used for FedLN/FedPer."""
    name = (model_name or "").lower()
    if name.startswith("gpt4ts"):
        return ["ln", "wpe", "out_layer"]
    if name.startswith("bart"):
        # Match BART LayerNorms and final projection head.
        return [
            "layernorm_embedding",
            "self_attn_layer_norm",
            "encoder.layernorm_embedding",
            "final_layer_norm",
            "layer_norm",
            "out_layer",
        ]
    if name.startswith("llama"):
        # LLaMA uses 'norm' naming; keep output head local.
        return ["norm", "out_layer"]
    if name.startswith("bert"):
        # BERT uses LayerNorm naming variants.
        return ["LayerNorm", "layer_norm", "out_layer"]
    # Fallback for unknown models.
    return ["ln", "wpe", "out_layer"]


class FedAvgWithMetrics(FedAvg):
    """Custom FedAvg that tracks client training and evaluation metrics."""

    def __init__(self, *args, personalize=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_train_losses = []
        self.client_train_durations = []
        self.client_val_losses = []
        self.client_val_maes = []
        self.client_val_rmses = []
        self.client_val_durations = []
        self.client_test_losses = []
        self.client_test_maes = []
        self.client_test_rmses = []
        self.client_test_durations = []
        # Optional: Per-client history (if we can extract client IDs)
        self.train_history = defaultdict(list)
        self.eval_history = defaultdict(list)
        # Set by outer training loop to expose the real round to eval configs.
        self.outer_round = 1

        # Drift tracking
        self.current_global_arrays = None
        self.avg_drift = None
        self.max_drift = None

        # FedBN/FedLN/FedPer personalization
        self.personalize = personalize
        self.personalized_params = {}  # node_id -> state_dict
        self.personalization_keys = (
            ['ln', 'wpe', 'out_layer'] if personalize else []
        )  # LayerNorm, Positional Embeddings, and Projection Head

    def aggregate_train(self, server_round, replies):
        """Override to collect training metrics and compute client drift."""
        self.avg_drift, self.max_drift = self._compute_drift(replies)
        self.client_train_losses = []
        self.client_train_durations = []

        logging.info(f"[DEBUG] aggregate_train called with {len(replies)} messages")

        for idx, msg in enumerate(replies):
            if not msg.has_content():
                logging.warning("[DEBUG] Message has no content, skipping")
                continue

            logging.info(f"[DEBUG] Message content keys: {msg.content.keys()}")
            if "metrics" in msg.content:
                metrics = msg.content["metrics"]
                if hasattr(metrics, 'data'):
                    metrics_dict = metrics.data
                else:
                    metrics_dict = metrics

                logging.info(f"[DEBUG] Metrics dict: {metrics_dict}")

                # Extract metrics
                train_loss = metrics_dict.get("train_loss")
                train_duration = metrics_dict.get("train_duration_sec")

                if train_loss is not None:
                    self.client_train_losses.append(float(train_loss))
                if train_duration is not None:
                    self.client_train_durations.append(float(train_duration))

                # Try to get client_id (if available in metrics)
                client_id = metrics_dict.get("client_id", f"client_{idx}")

                # Store in per-client history
                self.train_history[client_id].append({
                    "round": server_round,
                    "train_loss": float(train_loss) if train_loss is not None else None,
                    "train_duration_sec": float(train_duration) if train_duration is not None else None,
                })
            else:
                logging.warning(f"[DEBUG] No 'metrics' key found in message content")

            # --- FedBN/FedLN: Extract personalized parameters ---
            node_id = msg.metadata.src_node_id
            if "arrays" in msg.content:
                state = msg.content["arrays"].to_torch_state_dict()
                pers_dict = {k: v for k, v in state.items() if any(pk in k for pk in self.personalization_keys)}
                if pers_dict:
                    self.personalized_params[node_id] = pers_dict
                    logging.info(f"FedLN: Saved {len(pers_dict)} personalized layers for node {node_id}")

        logging.info(f"[DEBUG] Collected {len(self.client_train_losses)} train losses and {len(self.client_train_durations)} durations")

        return super().aggregate_train(server_round, replies)

    def configure_train(self, server_round, arrays, config, grid):
        """Override to restore personalized parameters to specific clients."""
        messages = super().configure_train(server_round, arrays, config, grid)
        for msg in messages:
            node_id = msg.metadata.dst_node_id
            if node_id in self.personalized_params:
                state = msg.content["arrays"].to_torch_state_dict()
                # Overwrite shared weights with client's personalized versions
                state.update(self.personalized_params[node_id])
                msg.content["arrays"] = ArrayRecord(state)
                logging.info(f"FedLN: Restored {len(self.personalized_params[node_id])} personalized layers for node {node_id}")
        return messages

    def configure_evaluate(self, server_round, arrays, config, grid):
        """Override to pass server_round to clients during evaluation."""
        messages = super().configure_evaluate(server_round, arrays, config, grid)
        for msg in messages:
            if "config" not in msg.content:
                msg.content["config"] = ConfigRecord({})
            if hasattr(msg.content["config"], "data"):
                msg.content["config"].data["server_round"] = self.outer_round
            else:
                msg.content["config"]["server_round"] = self.outer_round
        return messages

    def _compute_drift(self, messages):
        """Compute average and maximum L2 drift of client updates from global model."""
        if self.current_global_arrays is None or not messages:
            return None, None

        try:
            # Convert global state to float once for efficiency
            global_state = {k: v.float() for k, v in self.current_global_arrays.to_torch_state_dict().items()}
            drift_norms = []

            for msg in messages:
                if not msg.has_content() or "arrays" not in msg.content:
                    continue

                client_state = msg.content["arrays"].to_torch_state_dict()
                drift_sq = 0.0
                for k, v in client_state.items():
                    # Exclude personalized layers from drift calculation
                    if k in global_state and not any(pk in k for pk in self.personalization_keys):
                        diff = v.float() - global_state[k]
                        drift_sq += torch.sum(diff * diff).item()
                drift_norms.append(drift_sq ** 0.5)

            if not drift_norms:
                return None, None

            return sum(drift_norms) / len(drift_norms), max(drift_norms)
        except Exception as e:
            logging.warning(f"Error computing client drift: {e}")
            return None, None

    def aggregate_evaluate(self, server_round, replies):
        """Override to collect evaluation metrics from clients."""
        self.client_val_losses = []
        self.client_val_maes = []
        self.client_val_rmses = []
        self.client_val_durations = []
        self.client_test_losses = []
        self.client_test_maes = []
        self.client_test_rmses = []
        self.client_test_durations = []

        logging.info(f"[DEBUG] aggregate_evaluate called with {len(replies)} messages")

        for idx, msg in enumerate(replies):
            if not msg.has_content():
                logging.warning("[DEBUG] Message has no content in aggregate_evaluate, skipping")
                continue
            if "metrics" in msg.content:
                metrics = msg.content["metrics"]
                if hasattr(metrics, 'data'):
                    metrics_dict = metrics.data
                else:
                    metrics_dict = metrics

                logging.info(f"[DEBUG] Eval Metrics dict: {metrics_dict}")

                # Validation metrics
                val_loss = metrics_dict.get("val_loss")
                val_mae = metrics_dict.get("val_mae")
                val_rmse = metrics_dict.get("val_rmse")
                val_duration = metrics_dict.get("val_duration_sec")

                if val_loss is not None:
                    self.client_val_losses.append(float(val_loss))
                if val_mae is not None:
                    self.client_val_maes.append(float(val_mae))
                if val_rmse is not None:
                    self.client_val_rmses.append(float(val_rmse))
                if val_duration is not None:
                    self.client_val_durations.append(float(val_duration))

                # Test metrics
                test_loss = metrics_dict.get("test_loss")
                test_mae = metrics_dict.get("test_mae")
                test_rmse = metrics_dict.get("test_rmse")
                test_duration = metrics_dict.get("test_duration_sec")

                if test_loss is not None:
                    self.client_test_losses.append(float(test_loss))
                if test_mae is not None:
                    self.client_test_maes.append(float(test_mae))
                if test_rmse is not None:
                    self.client_test_rmses.append(float(test_rmse))
                if test_duration is not None:
                    self.client_test_durations.append(float(test_duration))

                # Try to get client_id (if available in metrics)
                client_id = metrics_dict.get("client_id", f"client_{idx}")

                # Store in per-client history
                self.eval_history[client_id].append({
                    "round": server_round,
                    "val_loss": float(val_loss) if val_loss is not None else None,
                    "val_mae": float(val_mae) if val_mae is not None else None,
                    "val_rmse": float(val_rmse) if val_rmse is not None else None,
                    "val_duration_sec": float(val_duration) if val_duration is not None else None,
                    "test_loss": float(test_loss) if test_loss is not None else None,
                    "test_mae": float(test_mae) if test_mae is not None else None,
                    "test_rmse": float(test_rmse) if test_rmse is not None else None,
                    "test_duration_sec": float(test_duration) if test_duration is not None else None,
                })

        logging.info(f"[DEBUG] Collected {len(self.client_val_losses)} val losses, {len(self.client_test_losses)} test losses")
        return super().aggregate_evaluate(server_round, replies)


class StatAvgWithMetrics(FedAvgWithMetrics):
    """StatAvg over FedAvgWithMetrics.

    Round 1: aggregate client local statistics into global statistics.
    Round 2: broadcast aggregated global stats through train config.
    Round 2+: optionally collect client scalers if provided.

    If clients do not provide StatAvg payloads, this strategy behaves like FedAvg.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats_global = None
        self.client_scalers = None

    @staticmethod
    def _metrics_to_dict(metrics_obj):
        if metrics_obj is None:
            return {}
        if hasattr(metrics_obj, "data"):
            return metrics_obj.data
        return metrics_obj

    @staticmethod
    def _extract_local_stats(metrics_dict):
        """Extract local stats from metrics payload.

        Supported forms:
        - {"statavg_stats": "{\"mean\": [...], \"var\": [...]}", ...}
        - {"statavg_stats": {"mean": [...], "var": [...]}, ...}
        - {"{\"mean\": [...], \"var\": [...]}": 0, ...}  # legacy baseline form
        """
        stats = metrics_dict.get("statavg_stats")
        if isinstance(stats, str):
            try:
                return json.loads(stats)
            except Exception:
                return None
        if isinstance(stats, dict):
            return stats

        # Legacy baseline payload: json-string as key
        for key in metrics_dict.keys():
            if isinstance(key, str) and "\"mean\"" in key and "\"var\"" in key:
                try:
                    return json.loads(key)
                except Exception:
                    continue
        return None

    @staticmethod
    def _extract_scaler(metrics_dict):
        scaler_blob = metrics_dict.get("scaler")
        if scaler_blob is None:
            return None
        if isinstance(scaler_blob, str):
            try:
                scaler_blob = scaler_blob.encode("latin1")
            except Exception:
                return None
        if isinstance(scaler_blob, (bytes, bytearray)):
            try:
                return pickle.loads(bytes(scaler_blob))
            except Exception:
                return None
        return None

    def aggregate_train(self, server_round, replies):
        if server_round == 1:
            local_means = []
            local_vars = []
            local_counts = []

            for msg in replies:
                if not msg.has_content() or "metrics" not in msg.content:
                    continue
                metrics_dict = self._metrics_to_dict(msg.content["metrics"])
                stats = self._extract_local_stats(metrics_dict)
                if not stats or "mean" not in stats or "var" not in stats:
                    continue
                n = metrics_dict.get("num-examples")
                if n is None:
                    continue

                local_means.append(np.array(stats["mean"]))
                local_vars.append(np.array(stats["var"]))
                local_counts.append(float(n))

            if local_counts:
                total = sum(local_counts)
                mean_global = sum(m * n for m, n in zip(local_means, local_counts)) / total
                var_global = sum(
                    n * v + n * (m - mean_global) ** 2
                    for v, m, n in zip(local_vars, local_means, local_counts)
                ) / total

                self.stats_global = {
                    "mean_global": mean_global.tolist() if isinstance(mean_global, np.ndarray) else mean_global,
                    "var_global": var_global.tolist() if isinstance(var_global, np.ndarray) else var_global,
                }
                logging.info("StatAvg: aggregated global statistics from %d clients", len(local_counts))
            else:
                logging.info("StatAvg: no local statistics received in round 1; continuing as FedAvg")

        if server_round == 2:
            scalers = []
            for msg in replies:
                if not msg.has_content() or "metrics" not in msg.content:
                    continue
                metrics_dict = self._metrics_to_dict(msg.content["metrics"])
                scaler = self._extract_scaler(metrics_dict)
                if scaler is not None:
                    scalers.append(scaler)
            if scalers:
                self.client_scalers = scalers
                logging.info("StatAvg: collected %d client scalers", len(scalers))

        return super().aggregate_train(server_round, replies)

    def configure_train(self, server_round, arrays, config, grid):
        messages = super().configure_train(server_round, arrays, config, grid)
        if server_round == 2 and self.stats_global is not None:
            for msg in messages:
                if "config" not in msg.content:
                    msg.content["config"] = ConfigRecord({})
                cfg = msg.content["config"]
                if hasattr(cfg, "data"):
                    cfg.data["mean_global"] = self.stats_global["mean_global"]
                    cfg.data["var_global"] = self.stats_global["var_global"]
                else:
                    cfg["mean_global"] = self.stats_global["mean_global"]
                    cfg["var_global"] = self.stats_global["var_global"]
            logging.info("StatAvg: broadcasted global statistics in round 2")
        return messages


class FedProxWithMetrics(FedAvgWithMetrics):
    """Custom FedProx that tracks client training and evaluation metrics.

    FedProx adds a proximal term on the client side: loss + (mu/2) * ||w - w_global||^2
    This keeps clients from drifting too far from the global model, improving stability
    with heterogeneous (non-IID) data.

    Server-side:
    - Aggregation is same as FedAvg (weighted average)
    - proximal_mu is passed to clients via train_config

    Client-side:
    - Clients receive proximal_mu and global weights
    - Add proximal term to local objective during training
    """

    def __init__(self, *args, proximal_mu=0.01, **kwargs):
        super().__init__(*args, **kwargs)
        self.proximal_mu = proximal_mu  # Proximal term coefficient


class ScaffoldWithMetrics(FedAvgWithMetrics):
    """SCAFFOLD strategy with metrics tracking and control variate management."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.c_global = None  # ArrayRecord
        self.c_locals = {}    # Dict[int, ArrayRecord]

    def configure_train(self, server_round, arrays, config, grid):
        """Inject global and local control variates into fit messages."""
        # 1. Get default messages from base FedAvg
        messages = super().configure_train(server_round, arrays, config, grid)

        # 2. Initialize c_global if it's the first round
        if self.c_global is None:
            # Initialize c_global with zeros (same structure as arrays)
            state_dict = arrays.to_torch_state_dict()
            # Exclude personalized layers from SCAFFOLD variates
            c_global_dict = {
                k: torch.zeros_like(v) 
                for k, v in state_dict.items() 
                if v.dtype != torch.int64 and not any(pk in k for pk in self.personalization_keys)
            }
            self.c_global = ArrayRecord(c_global_dict)
            logging.info(f"SCAFFOLD: Initialized c_global with zeros (excluding {len(state_dict)-len(c_global_dict)} personalized layers)")

        # 3. Add control variates to each message
        for msg in messages:
            node_id = msg.metadata.dst_node_id
            msg.content["c_global"] = self.c_global
            
            if node_id not in self.c_locals:
                # Initialize c_local for this node with zeros
                c_local_dict = {k: torch.zeros_like(v) for k, v in self.c_global.to_torch_state_dict().items()}
                self.c_locals[node_id] = ArrayRecord(c_local_dict)
                logging.info(f"SCAFFOLD: Initialized c_local for node {node_id}")
            
            msg.content["c_local"] = self.c_locals[node_id]

        return messages

    def aggregate_train(self, server_round, replies):
        """Update local and global control variates based on client replies."""
        new_c_locals = {}
        for msg in replies:
            node_id = msg.metadata.src_node_id
            if "c_local" in msg.content:
                new_c_locals[node_id] = msg.content["c_local"].to_torch_state_dict()
                self.c_locals[node_id] = msg.content["c_local"]

        # Update c_global = mean(c_locals) if we have new updates
        if new_c_locals:
            # Standard SCAFFOLD: c = mean(all c_locals)
            first_id = next(iter(self.c_locals))
            param_names = self.c_locals[first_id].to_torch_state_dict().keys()
            
            new_c_global_dict = {}
            num_clients = len(self.c_locals)
            for name in param_names:
                sum_c = None
                for n_id, c_rec in self.c_locals.items():
                    c_dict = c_rec.to_torch_state_dict()
                    if name in c_dict:
                        if sum_c is None:
                            sum_c = c_dict[name].clone()
                        else:
                            sum_c += c_dict[name]
                if sum_c is not None:
                    new_c_global_dict[name] = sum_c / num_clients
            
            self.c_global = ArrayRecord(new_c_global_dict)
            logging.info(f"SCAFFOLD: Updated c_global from {len(new_c_locals)} client updates (total clients: {num_clients})")

        return super().aggregate_train(server_round, replies)

@app.main()
def main(grid: Grid, context: Context) -> None:
    fraction_train: float = context.run_config["fraction-train"]
    total_rounds:   int   = context.run_config["num-server-rounds"]
    lr:             float = context.run_config["lr"]
    bs:             int   = context.run_config.get("batch-size", 32)
    pred_len:       int   = context.run_config.get("pred-len", 120)  # Default to 120 if not specified

    # Strategy selection: 'fedavg', 'fedprox', 'scaffold', or 'statavg'
    strategy_name:  str   = context.run_config.get("strategy", "fedavg").lower()
    proximal_mu:    float = context.run_config.get("proximal-mu", 0.01)

    # Early stopping parameters
    early_stop_patience: int = context.run_config.get("early-stop-patience", 5)
    early_stop_enabled: bool = context.run_config.get("early-stopping", True)

    # Model selection
    model: str = context.run_config.get("model", "gpt4ts_nonlinear")

    # Model architecture parameters
    seq_len: int = context.run_config.get("seq-len", 336)
    patch_size: int = context.run_config.get("patch-size", 4)
    stride: int = context.run_config.get("stride", 1)
    d_model: int = context.run_config.get("d-model", 768)
    hidden_size: int = context.run_config.get("hidden-size", 16)
    kernel_size: int = context.run_config.get("kernel-size", 3)
    llm_layers: int = context.run_config.get("llm-layers", 4)
    peft_method: str = context.run_config.get("peft-method", "lora")
    is_pretrained: bool = context.run_config.get("is-pretrained", True)
    lora_r: int = context.run_config.get("lora-r", 8)
    lora_alpha: int = context.run_config.get("lora-alpha", 16)
    lora_dropout: float = context.run_config.get("lora-dropout", 0.15)
    dropout: float = context.run_config.get("dropout", 0.15)
    adalora_total_step: int = context.run_config.get("adalora-total-step", -1)
    label_len: int = context.run_config.get("label-len", 48)
    enc_in: int = context.run_config.get("enc-in", 1)
    dec_in: int = context.run_config.get("dec-in", 1)
    c_out: int = context.run_config.get("c-out", 1)
    embed_type: int = context.run_config.get("embed-type", 0)
    embed: str = context.run_config.get("embed", "timeF")
    freq: str = context.run_config.get("freq", "h")
    factor: int = context.run_config.get("factor", 1)
    n_heads: int = context.run_config.get("n-heads", 4)
    e_layers: int = context.run_config.get("e-layers", 2)
    d_layers: int = context.run_config.get("d-layers", 1)
    d_ff: int = context.run_config.get("d-ff", 512)
    distil: bool = context.run_config.get("distil", True)
    activation: str = context.run_config.get("activation", "gelu")
    output_attention: bool = context.run_config.get("output-attention", False)
    fc_dropout: float = context.run_config.get("fc-dropout", 0.05)
    head_dropout: float = context.run_config.get("head-dropout", 0.0)
    patch_len: int = context.run_config.get("patch-len", 16)
    padding_patch: str = context.run_config.get("padding-patch", "end")
    revin: int = context.run_config.get("revin", 1)
    affine: int = context.run_config.get("affine", 0)
    subtract_last: int = context.run_config.get("subtract-last", 0)
    decomposition: int = context.run_config.get("decomposition", 0)
    individual: int = context.run_config.get("individual", 0)

    # Get experiment directory from environment variable (set by run_flower_experiment.sh)
    import os
    exp_dir = os.environ.get("FLOWER_EXP_DIR", ".")

    logging.info("Loading project configuration...")
    logging.info(f"Config: rounds={total_rounds}  fraction-train={fraction_train}  lr={lr}  batch-size={bs}  pred-len={pred_len}")
    logging.info(f"Strategy: {strategy_name}")
    if strategy_name == "fedprox":
        logging.info(f"FedProx proximal_mu: {proximal_mu}")
    if early_stop_enabled:
        logging.info(f"Early stopping enabled with patience: {early_stop_patience}")
    logging.info(f"Experiment directory: {exp_dir}")

    logging.info(f"Model: {model}")

    # Initialize model with configurable parameters
    configs = get_default_configs(
        pred_len=pred_len,
        model=model,
        seq_len=seq_len,
        patch_size=patch_size,
        stride=stride,
        d_model=d_model,
        hidden_size=hidden_size,
        kernel_size=kernel_size,
        llm_layers=llm_layers,
        label_len=label_len,
        enc_in=enc_in,
        dec_in=dec_in,
        c_out=c_out,
        embed_type=embed_type,
        embed=embed,
        freq=freq,
        factor=factor,
        n_heads=n_heads,
        e_layers=e_layers,
        d_layers=d_layers,
        d_ff=d_ff,
        distil=distil,
        activation=activation,
        output_attention=output_attention,
        fc_dropout=fc_dropout,
        head_dropout=head_dropout,
        patch_len=patch_len,
        padding_patch=padding_patch,
        revin=revin,
        affine=affine,
        subtract_last=subtract_last,
        decomposition=decomposition,
        individual=individual,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        dropout=dropout,
        peft_method=peft_method,
        is_pretrained=is_pretrained,
        adalora_total_step=adalora_total_step,
    )
    global_model = Net(configs=configs)
    arrays = ArrayRecord(trainable_state_dict(global_model))

    # Calculate model payload size
    model_size_mb = get_model_size_mb(arrays)
    logging.info(f"Model payload size: {model_size_mb:.2f} MB ({model_size_mb * 1024:.2f} KB)")
    logging.info("Server initialized - no server-side datasets. All training and testing happens on clients.")

    # Select strategy based on configuration
    personalize = strategy_name in ("fedln", "fedper")
    if strategy_name == "fedprox":
        strategy = FedProxWithMetrics(
            fraction_train=fraction_train,
            proximal_mu=proximal_mu,
            personalize=personalize,
        )
    elif strategy_name == "scaffold":
        strategy = ScaffoldWithMetrics(
            fraction_train=fraction_train,
            personalize=personalize,
        )
    elif strategy_name == "statavg":
        strategy = StatAvgWithMetrics(
            fraction_train=fraction_train,
            personalize=personalize,
        )
    else:
        strategy = FedAvgWithMetrics(
            fraction_train=fraction_train,
            personalize=personalize,
        )

    if personalize:
        strategy.personalization_keys = _personalization_keys_for_model(model)
        logging.info(
            "Personalization keys for model '%s': %s",
            model,
            strategy.personalization_keys,
        )

    best = {"round": 0, "loss": float("inf"), "arrays": None}
    logging.info("Starting federated training...")
    results = []

    # Early stopping tracking
    early_stop_counter = 0
    best_val_loss = float("inf")

    training_start_time = time.time()
    for r in range(1, total_rounds + 1):
        round_start_time = time.time()
        # CRITICAL FIX: Pass proximal_mu to clients for FedProx
        train_cfg = {
            "lr": lr,
            "model": model,
            "pred_len": pred_len,
            "seq_len": seq_len,
            "patch_size": patch_size,
            "stride": stride,
            "d_model": d_model,
            "hidden_size": hidden_size,
            "kernel_size": kernel_size,
            "llm_layers": llm_layers,
            "peft_method": peft_method,
            "lora_r": lora_r,
            "lora_alpha": lora_alpha,
            "lora_dropout": lora_dropout,
            "dropout": dropout,
            "adalora_total_step": adalora_total_step,
            "label_len": label_len,
            "enc_in": enc_in,
            "dec_in": dec_in,
            "c_out": c_out,
            "embed_type": embed_type,
            "embed": embed,
            "freq": freq,
            "factor": factor,
            "n_heads": n_heads,
            "e_layers": e_layers,
            "d_layers": d_layers,
            "d_ff": d_ff,
            "distil": distil,
            "activation": activation,
            "output_attention": output_attention,
            "fc_dropout": fc_dropout,
            "head_dropout": head_dropout,
            "patch_len": patch_len,
            "padding_patch": padding_patch,
            "revin": revin,
            "affine": affine,
            "subtract_last": subtract_last,
            "decomposition": decomposition,
            "individual": individual,
            "server_round": r
        }

        # Add proximal_mu if using FedProx strategy
        if strategy_name == "fedprox":
            train_cfg["proximal_mu"] = proximal_mu
            logging.info(f"[ROUND {r}] Sending proximal_mu={proximal_mu} to clients for FedProx")

        # Pass current global weights to strategy for drift calculation
        strategy.current_global_arrays = arrays

        # Provide outer loop round to strategy (Flower's server_round resets per start()).
        strategy.outer_round = r

        result = strategy.start(
            grid=grid,
            initial_arrays=arrays,
            train_config=ConfigRecord(train_cfg),
            num_rounds=1,
        )

        logging.info(f"[DEBUG Round {r}] result type: {type(result)}")
        logging.info(f"[DEBUG Round {r}] result attributes: {dir(result)}")
        if hasattr(result, 'metrics'):
            logging.info(f"[DEBUG Round {r}] result.metrics: {result.metrics}")
        if hasattr(result, 'metrics_aggregated'):
            logging.info(f"[DEBUG Round {r}] result.metrics_aggregated: {result.metrics_aggregated}")

        # Calculate payload sizes
        payload_sent_mb = get_model_size_mb(arrays)  # Size sent to clients before training

        new_arrays = result.arrays
        if new_arrays is None or len(new_arrays.to_torch_state_dict()) == 0:
            logging.error("WARNING: Strategy returned EMPTY weights. Keeping previous weights!")
            payload_received_mb = payload_sent_mb  # No update, same size
        else:
            payload_received_mb = get_model_size_mb(new_arrays)  # Size received after aggregation
            arrays = new_arrays

        logging.info(f"[Round {r}] Payload sent: {payload_sent_mb:.2f} MB, received: {payload_received_mb:.2f} MB")
        logging.info(f"[DEBUG Round {r}] strategy.client_train_losses = {strategy.client_train_losses}")
        logging.info(f"[DEBUG Round {r}] strategy.client_train_durations = {strategy.client_train_durations}")

        # Try to get from individual client metrics first
        if strategy.client_train_losses:
            avg_train_loss = sum(strategy.client_train_losses) / len(strategy.client_train_losses)
        else:
            avg_train_loss = None
            logging.warning(f"[Round {r}] No client train losses collected from messages!")

        if strategy.client_train_durations:
            avg_client_train_duration = sum(strategy.client_train_durations) / len(strategy.client_train_durations)
            max_client_train_duration = max(strategy.client_train_durations)
        else:
            avg_client_train_duration = None
            max_client_train_duration = None
            logging.warning(f"[Round {r}] No client train durations collected from messages!")

        # Fallback: Extract from aggregated train_metrics_clientapp in result
        if hasattr(result, 'train_metrics_clientapp') and result.train_metrics_clientapp:
            # train_metrics_clientapp is a dict: {round_num: {metric_name: value}}
            # Since we call strategy.start() with num_rounds=1, the metrics are always stored with key 1
            if 1 in result.train_metrics_clientapp:
                aggregated_metrics = result.train_metrics_clientapp[1]
                logging.info(f"[Round {r}] Found aggregated metrics: {aggregated_metrics}")

                if avg_train_loss is None and 'train_loss' in aggregated_metrics:
                    avg_train_loss = float(aggregated_metrics['train_loss'])
                    logging.info(f"[Round {r}] Using aggregated train_loss: {avg_train_loss}")

                if avg_client_train_duration is None and 'train_duration_sec' in aggregated_metrics:
                    avg_client_train_duration = float(aggregated_metrics['train_duration_sec'])
                    max_client_train_duration = avg_client_train_duration
                    logging.info(f"[Round {r}] Using aggregated train_duration: {avg_client_train_duration}")

        logging.info(f"[DEBUG Round {r}] strategy.client_val_losses = {strategy.client_val_losses}")
        logging.info(f"[DEBUG Round {r}] strategy.client_val_maes = {strategy.client_val_maes}")
        logging.info(f"[DEBUG Round {r}] strategy.client_val_rmses = {strategy.client_val_rmses}")
        logging.info(f"[DEBUG Round {r}] strategy.client_test_losses = {strategy.client_test_losses}")
        logging.info(f"[DEBUG Round {r}] strategy.client_test_maes = {strategy.client_test_maes}")
        logging.info(f"[DEBUG Round {r}] strategy.client_test_rmses = {strategy.client_test_rmses}")

        if strategy.client_val_losses:
            avg_val_loss = sum(strategy.client_val_losses) / len(strategy.client_val_losses)
        else:
            avg_val_loss = None
            logging.warning(f"[Round {r}] No client val losses collected!")

        if strategy.client_val_maes:
            avg_val_mae = sum(strategy.client_val_maes) / len(strategy.client_val_maes)
        else:
            avg_val_mae = None

        if strategy.client_val_rmses:
            avg_val_rmse = sum(strategy.client_val_rmses) / len(strategy.client_val_rmses)
        else:
            avg_val_rmse = None

        if strategy.client_val_durations:
            avg_client_val_duration = sum(strategy.client_val_durations) / len(strategy.client_val_durations)
            max_client_val_duration = max(strategy.client_val_durations)
        else:
            avg_client_val_duration = None
            max_client_val_duration = None

        if strategy.client_test_losses:
            avg_test_loss = sum(strategy.client_test_losses) / len(strategy.client_test_losses)
        else:
            avg_test_loss = None
            logging.warning(f"[Round {r}] No client test losses collected!")

        if strategy.client_test_maes:
            avg_test_mae = sum(strategy.client_test_maes) / len(strategy.client_test_maes)
        else:
            avg_test_mae = None

        if strategy.client_test_rmses:
            avg_test_rmse = sum(strategy.client_test_rmses) / len(strategy.client_test_rmses)
        else:
            avg_test_rmse = None

        if strategy.client_test_durations:
            avg_client_test_duration = sum(strategy.client_test_durations) / len(strategy.client_test_durations)
            max_client_test_duration = max(strategy.client_test_durations)
        else:
            avg_client_test_duration = None
            max_client_test_duration = None

        # Extract drift metrics from strategy (computed in aggregate_fit)
        avg_drift = getattr(strategy, "avg_drift", None)
        max_drift = getattr(strategy, "max_drift", None)

        round_duration = time.time() - round_start_time

        # Format metrics for logging
        val_loss_str = f"{avg_val_loss:.6f}" if avg_val_loss is not None else "N/A"
        val_mae_str = f"{avg_val_mae:.6f}" if avg_val_mae is not None else "N/A"
        val_rmse_str = f"{avg_val_rmse:.6f}" if avg_val_rmse is not None else "N/A"
        test_loss_str = f"{avg_test_loss:.6f}" if avg_test_loss is not None else "N/A"
        test_mae_str = f"{avg_test_mae:.6f}" if avg_test_mae is not None else "N/A"
        test_rmse_str = f"{avg_test_rmse:.6f}" if avg_test_rmse is not None else "N/A"

        logging.info(f"[Round {r}] Aggregated client val metrics: loss={val_loss_str}, MAE={val_mae_str}, RMSE={val_rmse_str}")
        logging.info(f"[Round {r}] Aggregated client test metrics: loss={test_loss_str}, MAE={test_mae_str}, RMSE={test_rmse_str}")
        if avg_drift is not None:
             logging.info(f"[Round {r}] Client drift: avg={avg_drift:.6f}, max={max_drift:.6f}")
        logging.info(f"[Round {r}] Round time: {round_duration:.2f}s")

        results.append({
            "round": r,
            "train_loss": float(avg_train_loss) if avg_train_loss is not None else None,
            "val_loss": float(avg_val_loss) if avg_val_loss is not None else None,
            "val_mae": float(avg_val_mae) if avg_val_mae is not None else None,
            "val_rmse": float(avg_val_rmse) if avg_val_rmse is not None else None,
            "test_loss": float(avg_test_loss) if avg_test_loss is not None else None,
            "test_mae": float(avg_test_mae) if avg_test_mae is not None else None,
            "test_rmse": float(avg_test_rmse) if avg_test_rmse is not None else None,
            "best_loss": float(best["loss"]),
            "round_duration_sec": float(round_duration),
            "payload_sent_mb": float(payload_sent_mb),
            "payload_received_mb": float(payload_received_mb),
            "avg_client_train_duration_sec": float(avg_client_train_duration) if avg_client_train_duration is not None else None,
            "max_client_train_duration_sec": float(max_client_train_duration) if max_client_train_duration is not None else None,
            "avg_client_val_duration_sec": float(avg_client_val_duration) if avg_client_val_duration is not None else None,
            "max_client_val_duration_sec": float(max_client_val_duration) if max_client_val_duration is not None else None,
            "avg_client_test_duration_sec": float(avg_client_test_duration) if avg_client_test_duration is not None else None,
            "max_client_test_duration_sec": float(max_client_test_duration) if max_client_test_duration is not None else None,
            "avg_client_drift": float(avg_drift) if avg_drift is not None else None,
            "max_client_drift": float(max_drift) if max_drift is not None else None,
        })


        if avg_val_loss is not None and avg_val_loss < best["loss"]:
            best["loss"] = float(avg_val_loss)
            best["round"] = r
            best["arrays"] = copy.deepcopy(arrays)
            logging.info(f"[ROUND {r}] Best checkpoint updated (Val Loss={avg_val_loss:.6f})")

        # Early stopping logic
        if early_stop_enabled and avg_val_loss is not None:
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                early_stop_counter = 0
                logging.info(f"[ROUND {r}] Validation loss improved to {avg_val_loss:.6f}. Resetting early stop counter.")
            else:
                early_stop_counter += 1
                logging.info(f"[ROUND {r}] Validation loss did not improve. Early stop counter: {early_stop_counter}/{early_stop_patience}")

                if early_stop_counter >= early_stop_patience:
                    logging.info(f"[ROUND {r}] Early stopping triggered! No improvement for {early_stop_patience} rounds.")
                    logging.info(f"[ROUND {r}] Best validation loss: {best_val_loss:.6f} at round {best['round']}")
                    break


    total_training_time = time.time() - training_start_time

    logging.info(f"Total training time: {total_training_time:.2f}s ({total_training_time/60:.2f} minutes)")
    logging.info(f"Average time per round: {total_training_time/total_rounds:.2f}s")

    # CRITICAL FIX: Restore best model weights instead of using final round weights
    if best["arrays"] is not None:
        logging.info(f"Restoring best model from round {best['round']} (Val Loss={best['loss']:.6f})")
        arrays = best["arrays"]
    else:
        logging.warning("No best checkpoint found, using final round weights")

    logging.info("Saving best model to disk...")
    final_model_path = os.path.join(exp_dir, "final_model.pt")
    # Merge best trainable weights back into full model for a self-contained checkpoint
    global_model.load_state_dict(arrays.to_torch_state_dict(), strict=False)
    torch.save(global_model.state_dict(), final_model_path)
    logging.info(f"Saved best model (from round {best['round']}) to: {final_model_path}")

    df = pd.DataFrame(results)
    training_summary_path = os.path.join(exp_dir, "training_summary.csv")
    df.to_csv(training_summary_path, index=False)
    logging.info(f"Saved training summary to: {training_summary_path}")

    num_trainable_params = sum(p.numel() for p in global_model.parameters() if p.requires_grad)
    num_total_params = sum(p.numel() for p in global_model.parameters())

    timing_summary = {
        "model_name": model,
        "fl_algorithm": strategy_name,
        "pred_len": pred_len,
        "learning_rate": lr,
        "local_epochs": context.run_config.get("local-epochs", 1),
        "num_clients": context.run_config.get("num-clients", 5),
        "num_trainable_params": num_trainable_params,
        "num_total_params": num_total_params,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "patch_size": patch_size,
        "stride": stride,
        "random_seed": context.run_config.get("random-seed", 2021),
        "total_training_time_sec": total_training_time,
        "total_training_time_min": total_training_time / 60,
        "num_rounds": total_rounds,
        "avg_time_per_round_sec": total_training_time / total_rounds,
        "model_size_mb": model_size_mb,
        "start_timestamp": datetime.fromtimestamp(training_start_time).strftime('%Y-%m-%d %H:%M:%S'),
        "end_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    timing_df = pd.DataFrame([timing_summary])
    timing_summary_path = os.path.join(exp_dir, "timing_summary.csv")
    timing_df.to_csv(timing_summary_path, index=False)
    logging.info(f"Saved timing summary to: {timing_summary_path}")

    # Update master experiment log — one row per experiment
    try:
        # master_experiment_log.py moved to flower_app/ (parent of my_flower_app/)
        import master_experiment_log
        row = master_experiment_log.build_experiment_row(exp_dir)
        # Save master log in the parent directory of experiment folders
        master_log_path = os.path.join(os.path.dirname(exp_dir), "master_experiment_log.csv")
        master_experiment_log.append_to_master_log(row, master_csv=master_log_path)
    except Exception as e:
        logging.warning(f"Failed to update master experiment log: {e}")


if __name__ == "__main__":
    main()
