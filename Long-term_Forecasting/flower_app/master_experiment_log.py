#!/usr/bin/env python3
"""
Master Experiment Log — One Row Per Experiment
===============================================

Central registry for all federated learning runs. Unlike training_summary.csv
(one row per round) or timing_summary.csv (timing only), this table captures
the FINAL VERDICT of each experiment in a single row.

Designed for three workflows:
  1. FILTERING:  "Show me the best LR for BERT where horizon=72"
  2. RANKING:    "Which (model × algorithm) has the lowest test MAE?"
  3. DIAGNOSIS:  "Why did experiment X fail?" → check overfit_gap, client drift, fairness

Schema groups:
  A. Identity           — experiment_id, timestamp, seed
  B. Primary axes       — model, fl_algorithm, pred_len  (the 3 axes of your paper)
  C. Hyperparameters    — lr, local_epochs, batch_size, etc. (for HP search filtering)
  D. Architecture       — patch_size, stride, d_model, llm_layers, lora_*, num_params
  E. Performance        — best-round val/test MSE, MAE, RMSE
  F. Convergence        — overfit gap, improvement %, early stopping info
  G. Client fairness    — per-client MAE std, worst city, fairness ratio
  H. Communication      — payload size, total comm cost, rounds to best
  I. Timing             — wall-clock durations
  J. Status             — completed/failed/early_stopped, notes

Usage:
  # After an experiment finishes, call from server_app.py:
  from master_experiment_log import build_experiment_row, append_to_master_log
  row = build_experiment_row(exp_dir="/path/to/experiments_gpt4ts_20250101_120000")
  append_to_master_log(row, master_csv="master_experiment_log.csv")

  # Or run standalone to rebuild from all existing experiments:
  python master_experiment_log.py --scan-dir /path/to/flower_app --output master_experiment_log.csv
"""

import os
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import OrderedDict

import numpy as np
import pandas as pd

from my_flower_app.task import DATASET_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DEFINITION
# ─────────────────────────────────────────────────────────────────────────────
# Each entry: (column_name, dtype, default_value, description)
# Ordering here determines column order in the output CSV.

SCHEMA = OrderedDict([
    # ── A. IDENTITY ──────────────────────────────────────────────────────────
    ("experiment_id",            ("str",   None,  "Experiment folder name (unique key)")),
    ("timestamp",                ("str",   None,  "Run timestamp extracted from folder name")),
    ("seed",                     ("int",   None,  "Random seed (for multi-seed runs)")),

    # ── A2. DATASET INFORMATION ──────────────────────────────────────────────
    ("dataset_name",             ("str",   None,  "Dataset name (e.g., VNMET, custom, nasa_almaty)")),
    ("target_column",            ("str",   None,  "Target column name for forecasting")),

    # ── B. PRIMARY AXES (main comparison dimensions in the paper) ────────────
    ("model",                    ("str",   None,  "Model name: gpt4ts_nonlinear, bert_nonlinear, llama_nonlinear, bart_nonlinear, patchtst, dlinear, informer")),
    ("peft_method",              ("str",   None,  "Fine-tuning strategy: lora, loha, adalora, pft, fft")),
    ("is_pretrained",            ("bool",  None,  "Whether the backbone was kept pretrained (no fine-tuning)")),
    ("fl_algorithm",             ("str",   None,  "FL strategy: fedavg, fedprox, scaffold, fedln, fedper, centralized, local_only")),
    ("pred_len",                 ("int",   None,  "Forecast horizon: 1, 72, 432")),

    # ── C. HYPERPARAMETERS (for HP search filtering) ─────────────────────────
    ("learning_rate",            ("float", None,  "Client base learning rate")),
    ("local_epochs",             ("int",   None,  "Number of local training epochs per round (E)")),
    ("num_rounds_configured",    ("int",   None,  "Configured number of FL rounds")),
    ("num_rounds_completed",     ("int",   None,  "Actual rounds completed (may differ due to early stopping)")),
    ("batch_size",               ("int",   None,  "Training batch size")),
    ("num_clients",              ("int",   None,  "Number of federated clients")),
    ("weight_decay",             ("float", None,  "AdamW L2 regularization coefficient")),
    ("warmup_rounds",            ("int",   None,  "Number of LR warmup rounds")),
    ("proximal_mu",              ("float", None,  "FedProx proximal term coefficient (None if FedAvg)")),
    ("early_stop_patience",      ("int",   None,  "Early stopping patience (rounds without improvement)")),
    ("dropout",                  ("float", None,  "Model dropout rate")),

    # ── D. ARCHITECTURE (for reference / ablation studies) ───────────────────
    ("seq_len",                  ("int",   None,  "Input sequence length")),
    ("patch_size",               ("int",   None,  "Patch size for time series tokenization")),
    ("stride",                   ("int",   None,  "Patch stride")),
    ("num_patches",              ("int",   None,  "Computed number of patches = (seq_len - patch_size) / stride + 2")),
    ("d_model",                  ("int",   None,  "LLM embedding dimension")),
    ("hidden_size",              ("int",   None,  "ConvMLP hidden dimension")),
    ("kernel_size",              ("int",   None,  "Conv1D kernel size")),
    ("llm_layers",               ("int",   None,  "Number of LLM backbone layers used")),
    ("lora_r",                   ("int",   None,  "LoRA rank")),
    ("lora_alpha",               ("int",   None,  "LoRA scaling alpha")),
    ("lora_dropout",             ("float", None,  "LoRA dropout rate")),
    ("num_trainable_params",     ("int",   None,  "Number of trainable parameters")),
    ("num_total_params",         ("int",   None,  "Total model parameters (frozen + trainable)")),
    ("model_payload_mb",         ("float", None,  "Transmitted model size per round (MB)")),

    # ── E. PERFORMANCE AT BEST ROUND (the 'answer' — what goes in the paper) ─
    ("best_round",               ("int",   None,  "Round with lowest validation loss")),
    ("best_val_mse",             ("float", None,  "Validation MSE at best round")),
    ("best_val_mae",             ("float", None,  "Validation MAE at best round")),
    ("best_val_rmse",            ("float", None,  "Validation RMSE at best round")),
    ("best_test_mse",            ("float", None,  "Test MSE at best round")),
    ("best_test_mae",            ("float", None,  "Test MAE at best round")),
    ("best_test_rmse",           ("float", None,  "Test RMSE at best round")),
    ("best_train_mse",           ("float", None,  "Training MSE at best round (for overfit gap)")),

    # ── F. CONVERGENCE DIAGNOSTICS (why did it succeed or fail?) ─────────────
    ("first_round_val_loss",     ("float", None,  "Validation loss at round 1 (baseline)")),
    ("final_round_val_loss",     ("float", None,  "Validation loss at final round")),
    ("val_loss_improvement_pct", ("float", None,  "Pct improvement: (first - best) / first × 100")),
    ("overfit_gap",              ("float", None,  "best_val_mse - best_train_mse (positive = overfitting)")),
    ("overfit_ratio",            ("float", None,  "best_val_mse / best_train_mse (>1.0 = overfitting)")),
    ("converged",                ("bool",  None,  "True if val loss decreased by ≥5% from round 1")),
    ("loss_trend_last3",         ("str",   None,  "Trend of val_loss over last 3 rounds: 'decreasing' / 'increasing' / 'flat'")),
    ("early_stopped",            ("bool",  None,  "True if training stopped before configured rounds")),
    ("early_stop_round",         ("int",   None,  "Round at which early stopping triggered (None if not)")),

    # ── G. CLIENT FAIRNESS (per-client performance spread) ───────────────────
    ("client_val_mae_mean",      ("float", None,  "Mean of per-client validation MAEs at best round")),
    ("client_val_mae_std",       ("float", None,  "Std dev of per-client validation MAEs (lower = fairer)")),
    ("client_val_mae_min",       ("float", None,  "Best-performing client's validation MAE")),
    ("client_val_mae_max",       ("float", None,  "Worst-performing client's validation MAE")),
    ("client_val_mae_best_city", ("str",   None,  "City name of best-performing client")),
    ("client_val_mae_worst_city",("str",   None,  "City name of worst-performing client")),
    ("fairness_ratio",           ("float", None,  "worst_mae / best_mae (1.0 = perfectly fair, >2.0 = problematic)")),

    # ── H. COMMUNICATION EFFICIENCY ──────────────────────────────────────────
    ("payload_per_round_mb",     ("float", None,  "Model payload size per communication round (MB)")),
    ("total_comm_mb",            ("float", None,  "Total communication: payload × clients × rounds_completed × 2 (up+down)")),
    ("comm_to_best_mb",          ("float", None,  "Communication spent to reach best round")),
    ("rounds_per_mae_point",     ("float", None,  "Rounds needed per 0.01 MAE improvement (efficiency metric)")),

    # ── I. TIMING ────────────────────────────────────────────────────────────
    ("total_training_time_sec",  ("float", None,  "Total wall-clock training time (seconds)")),
    ("total_training_time_min",  ("float", None,  "Total wall-clock training time (minutes)")),
    ("avg_round_duration_sec",   ("float", None,  "Average wall-clock time per FL round")),
    ("avg_client_train_dur_sec", ("float", None,  "Average per-client training duration")),
    ("max_client_train_dur_sec", ("float", None,  "Slowest client's training duration (bottleneck)")),

    # ── J. STATUS ────────────────────────────────────────────────────────────
    ("status",                   ("str",   None,  "completed / early_stopped / failed")),
    ("experiment_dir",           ("str",   None,  "Full path to experiment directory")),
    ("notes",                    ("str",   "",    "Free-text notes or annotations")),
])


def get_client_names(dataset_name):
    if dataset_name and dataset_name.upper() in DATASET_REGISTRY:
        return DATASET_REGISTRY[dataset_name.upper()].get("client_names", {})
    return {i: f"client_{i}" for i in range(10)}


def get_empty_row() -> Dict[str, Any]:
    """Return a dict with all schema keys set to their default values."""
    return {col: info[1] for col, info in SCHEMA.items()}


def get_schema_docs() -> pd.DataFrame:
    """Return a DataFrame documenting the schema."""
    rows = []
    for col, (dtype, default, desc) in SCHEMA.items():
        rows.append({"column": col, "dtype": dtype, "default": default, "description": desc})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# PARSERS — Extract data from existing experiment artifacts
# ─────────────────────────────────────────────────────────────────────────────

def _parse_config_txt(config_path: str) -> Dict[str, Any]:
    """Parse a config.txt file (written by run_flower_experiment.sh)."""
    result = {}
    if not os.path.exists(config_path):
        return result

    with open(config_path, "r") as f:
        content = f.read()

    # Key-value patterns like "  lr: 0.0005" or "  model: gpt4ts_nonlinear"
    kv_pattern = re.compile(r"^\s+([\w-]+):\s+(.+)$", re.MULTILINE)
    for match in kv_pattern.finditer(content):
        key = match.group(1).strip()
        val = match.group(2).strip()
        # Try numeric conversion
        try:
            val = int(val)
        except ValueError:
            try:
                val = float(val)
            except ValueError:
                # Handle booleans
                if val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
        result[key] = val

    return result


def _parse_training_summary(csv_path: str) -> Optional[pd.DataFrame]:
    """Load training_summary.csv (one row per FL round)."""
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return None
        return df.sort_values("round").reset_index(drop=True)
    except Exception as e:
        logging.warning(f"Error reading {csv_path}: {e}")
        return None


def _parse_timing_summary(csv_path: str) -> Dict[str, Any]:
    """Load timing_summary.csv (single row)."""
    if not os.path.exists(csv_path):
        return {}
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return {}
        return df.iloc[0].to_dict()
    except Exception as e:
        logging.warning(f"Error reading {csv_path}: {e}")
        return {}


def _parse_client_eval_metrics(
    metrics_dir: str, best_round: int, dataset_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parse per-client eval metrics CSVs to compute fairness metrics.
    Reads: metrics/client{N}_eval_metrics.csv
    Returns per-client MAEs at the best round.
    """
    result = {}
    if not os.path.exists(metrics_dir):
        return result

    client_maes = {}
    for filename in sorted(os.listdir(metrics_dir)):
        if not filename.startswith("client") or "eval_metrics" not in filename:
            continue

        # Extract client ID from filename: client0_eval_metrics.csv -> 0
        match = re.match(r"client(\d+)_eval_metrics\.csv", filename)
        if not match:
            continue
        client_id = int(match.group(1))

        try:
            df = pd.read_csv(os.path.join(metrics_dir, filename))
            if df.empty:
                continue

            # Find the row for the best round
            round_df = df[df["round"] == best_round]
            if round_df.empty:
                # Fallback: use the last available round
                round_df = df.iloc[[-1]]

            val_mae = round_df["val_mae"].values[0] if "val_mae" in round_df.columns else None
            if val_mae is not None and not np.isnan(val_mae):
                client_maes[client_id] = float(val_mae)
        except Exception as e:
            logging.warning(f"Error reading {filename}: {e}")

    if not client_maes:
        return result

    mae_values = list(client_maes.values())
    result["client_val_mae_mean"] = float(np.mean(mae_values))
    result["client_val_mae_std"] = float(np.std(mae_values))
    result["client_val_mae_min"] = float(np.min(mae_values))
    result["client_val_mae_max"] = float(np.max(mae_values))

    # Identify best/worst cities
    best_client = min(client_maes, key=client_maes.get)
    worst_client = max(client_maes, key=client_maes.get)
    client_cities = get_client_names(dataset_name)
    result["client_val_mae_best_city"] = client_cities.get(best_client, f"client_{best_client}")
    result["client_val_mae_worst_city"] = client_cities.get(worst_client, f"client_{worst_client}")

    # Fairness ratio
    if result["client_val_mae_min"] > 0:
        result["fairness_ratio"] = round(result["client_val_mae_max"] / result["client_val_mae_min"], 4)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# BUILDER — Assemble one row from an experiment directory
# ─────────────────────────────────────────────────────────────────────────────

def build_experiment_row(exp_dir: str) -> Dict[str, Any]:
    """
    Build a single master log row from an experiment directory.

    Reads:
      - config.txt             → hyperparameters & architecture
      - training_summary.csv   → per-round metrics → best-round performance & convergence
      - timing_summary.csv     → wall-clock durations
      - metrics/client*_eval_metrics.csv → per-client fairness

    Returns:
      Dict with all SCHEMA columns populated (or None for missing data).
    """
    row = get_empty_row()
    exp_path = Path(exp_dir)

    if not exp_path.exists():
        logging.error(f"Experiment directory not found: {exp_dir}")
        row["status"] = "failed"
        return row

    # ── A. IDENTITY ──────────────────────────────────────────────────────
    row["experiment_id"] = exp_path.name
    row["experiment_dir"] = str(exp_path.resolve())

    # Extract timestamp from folder name: experiments_gpt4ts_20250101_120000
    ts_match = re.search(r"(\d{8}_\d{6})", exp_path.name)
    if ts_match:
        row["timestamp"] = ts_match.group(1)

    # ── Parse config.txt ─────────────────────────────────────────────────
    config = _parse_config_txt(str(exp_path / "config.txt"))

    # A2. SEED
    row["seed"] = config.get("random-seed", config.get("random_seed", None))

    # A2. DATASET INFORMATION
    row["dataset_name"] = config.get("dataset-name", config.get("dataset_name", None))
    row["target_column"] = config.get("target-column", config.get("target_column", None))

    # B. PRIMARY AXES
    row["model"] = config.get("model", None)
    row["peft_method"] = config.get("peft_method", config.get("peft-method", None))
    row["is_pretrained"] = config.get("is_pretrained", config.get("is-pretrained", None))
    row["fl_algorithm"] = config.get("strategy", None)
    row["pred_len"] = config.get("pred-len", config.get("pred_len", None))

    # C. HYPERPARAMETERS
    row["learning_rate"] = config.get("lr", None)
    row["local_epochs"] = config.get("local-epochs", config.get("local_epochs", None))
    row["num_rounds_configured"] = config.get("num-server-rounds", config.get("num_server_rounds", None))
    row["batch_size"] = config.get("batch-size", config.get("batch_size", None))
    row["num_clients"] = config.get("num-clients", config.get("num_clients", None))
    row["weight_decay"] = config.get("weight-decay", config.get("weight_decay", None))
    row["warmup_rounds"] = config.get("warmup-rounds", config.get("warmup_rounds", None))
    row["early_stop_patience"] = config.get("early-stop-patience", config.get("early_stop_patience", None))
    row["dropout"] = config.get("dropout", None)

    # Proximal mu (only for FedProx)
    if row["fl_algorithm"] == "fedprox":
        row["proximal_mu"] = config.get("proximal-mu", config.get("proximal_mu", None))

    # D. ARCHITECTURE
    row["seq_len"] = config.get("seq-len", config.get("seq_len", None))
    row["patch_size"] = config.get("patch-size", config.get("patch_size", None))
    row["stride"] = config.get("stride", None)
    row["d_model"] = config.get("d-model", config.get("d_model", None))
    row["hidden_size"] = config.get("hidden-size", config.get("hidden_size", None))
    row["kernel_size"] = config.get("kernel-size", config.get("kernel_size", None))
    row["llm_layers"] = config.get("llm-layers", config.get("llm_layers", None))
    row["lora_r"] = config.get("lora-r", config.get("lora_r", None))
    row["lora_alpha"] = config.get("lora-alpha", config.get("lora_alpha", None))
    row["lora_dropout"] = config.get("lora-dropout", config.get("lora_dropout", None))

    # Compute num_patches
    if row["seq_len"] is not None and row["patch_size"] is not None and row["stride"] is not None:
        row["num_patches"] = (row["seq_len"] - row["patch_size"]) // row["stride"] + 1 + 1  # +1 for padding

    # ── Parse training_summary.csv ───────────────────────────────────────
    ts_df = _parse_training_summary(str(exp_path / "training_summary.csv"))

    if ts_df is not None and len(ts_df) > 0:
        row["num_rounds_completed"] = int(ts_df["round"].max())

        # E. PERFORMANCE AT BEST ROUND
        # Best round = lowest val_loss
        val_loss_col = "val_loss"
        if val_loss_col in ts_df.columns:
            valid_mask = ts_df[val_loss_col].notna()
            if valid_mask.any():
                best_idx = ts_df.loc[valid_mask, val_loss_col].idxmin()
                best = ts_df.loc[best_idx]

                row["best_round"] = int(best["round"])
                row["best_val_mse"] = _safe_float(best.get("val_loss"))
                row["best_val_mae"] = _safe_float(best.get("val_mae"))
                row["best_val_rmse"] = _safe_float(best.get("val_rmse"))
                row["best_test_mse"] = _safe_float(best.get("test_loss"))
                row["best_test_mae"] = _safe_float(best.get("test_mae"))
                row["best_test_rmse"] = _safe_float(best.get("test_rmse"))
                row["best_train_mse"] = _safe_float(best.get("train_loss"))

        # F. CONVERGENCE DIAGNOSTICS
        first_row = ts_df.iloc[0]
        final_row = ts_df.iloc[-1]

        row["first_round_val_loss"] = _safe_float(first_row.get("val_loss"))
        row["final_round_val_loss"] = _safe_float(final_row.get("val_loss"))

        # Improvement %
        if row["first_round_val_loss"] is not None and row["best_val_mse"] is not None:
            if row["first_round_val_loss"] > 0:
                row["val_loss_improvement_pct"] = round(
                    (row["first_round_val_loss"] - row["best_val_mse"]) / row["first_round_val_loss"] * 100, 2
                )
                row["converged"] = row["val_loss_improvement_pct"] >= 5.0

        # Overfit gap
        if row["best_val_mse"] is not None and row["best_train_mse"] is not None:
            row["overfit_gap"] = round(row["best_val_mse"] - row["best_train_mse"], 6)
            if row["best_train_mse"] > 0:
                row["overfit_ratio"] = round(row["best_val_mse"] / row["best_train_mse"], 4)

        # Loss trend over last 3 rounds
        if val_loss_col in ts_df.columns and len(ts_df) >= 3:
            last3 = ts_df[val_loss_col].tail(3).dropna().values
            if len(last3) == 3:
                if last3[2] < last3[0] - 1e-6:
                    row["loss_trend_last3"] = "decreasing"
                elif last3[2] > last3[0] + 1e-6:
                    row["loss_trend_last3"] = "increasing"
                else:
                    row["loss_trend_last3"] = "flat"

        # Early stopping detection
        if row["num_rounds_configured"] is not None and row["num_rounds_completed"] is not None:
            if row["num_rounds_completed"] < row["num_rounds_configured"]:
                row["early_stopped"] = True
                row["early_stop_round"] = row["num_rounds_completed"]
            else:
                row["early_stopped"] = False

        # H. COMMUNICATION EFFICIENCY
        if "payload_sent_mb" in ts_df.columns:
            row["payload_per_round_mb"] = _safe_float(ts_df["payload_sent_mb"].iloc[0])
            row["model_payload_mb"] = row["payload_per_round_mb"]

        if row["payload_per_round_mb"] is not None and row["num_clients"] is not None:
            # Total comm = payload × clients × rounds × 2 (upload + download)
            n_clients = row["num_clients"]
            n_rounds = row["num_rounds_completed"] or 0
            payload = row["payload_per_round_mb"]
            row["total_comm_mb"] = round(payload * n_clients * n_rounds * 2, 2)

            if row["best_round"] is not None:
                row["comm_to_best_mb"] = round(payload * n_clients * row["best_round"] * 2, 2)

        # Rounds per MAE point
        if (row["first_round_val_loss"] is not None and row["best_val_mae"] is not None
                and row["best_round"] is not None):
            first_mae_cols = ts_df["val_mae"].dropna()
            if len(first_mae_cols) > 0:
                first_mae = first_mae_cols.iloc[0]
                mae_improvement = first_mae - (row["best_val_mae"] or first_mae)
                if mae_improvement > 0.001:
                    row["rounds_per_mae_point"] = round(row["best_round"] / (mae_improvement / 0.01), 2)

        # I. TIMING (from training_summary)
        if "round_duration_sec" in ts_df.columns:
            row["avg_round_duration_sec"] = round(float(ts_df["round_duration_sec"].mean()), 2)

        if "avg_client_train_duration_sec" in ts_df.columns:
            row["avg_client_train_dur_sec"] = round(float(ts_df["avg_client_train_duration_sec"].mean()), 2)

        if "max_client_train_duration_sec" in ts_df.columns:
            row["max_client_train_dur_sec"] = round(float(ts_df["max_client_train_duration_sec"].max()), 2)

    # ── Parse timing_summary.csv ─────────────────────────────────────────
    timing = _parse_timing_summary(str(exp_path / "timing_summary.csv"))
    if timing:
        row["total_training_time_sec"] = _safe_float(timing.get("total_training_time_sec"))
        row["total_training_time_min"] = _safe_float(timing.get("total_training_time_min"))

        # Extract num_trainable_params and model_size if saved
        if row.get("seed") is None:
            row["seed"] = timing.get("random_seed", timing.get("random-seed"))
        if "num_trainable_params" in timing:
            row["num_trainable_params"] = timing.get("num_trainable_params")
        if "num_total_params" in timing:
            row["num_total_params"] = timing.get("num_total_params")
        if "model_size_mb" in timing:
            row["model_payload_mb"] = _safe_float(timing["model_size_mb"])

    # ── Parse per-client eval metrics ────────────────────────────────────
    metrics_dir = str(exp_path / "metrics")
    best_round = row.get("best_round")
    if best_round is not None:
        client_fairness = _parse_client_eval_metrics(
            metrics_dir, best_round, dataset_name=row.get("dataset_name")
        )
        row.update(client_fairness)

    # ── J. STATUS ────────────────────────────────────────────────────────
    if ts_df is not None and len(ts_df) > 0:
        if row.get("early_stopped"):
            row["status"] = "early_stopped"
        else:
            row["status"] = "completed"
    else:
        row["status"] = "failed"

    return row


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None for NaN / None / missing."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else round(f, 6)
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# I/O — Read / Write / Append
# ─────────────────────────────────────────────────────────────────────────────

def append_to_master_log(row: Dict[str, Any], master_csv: str = "master_experiment_log.csv"):
    """
    Append a single experiment row to the master CSV.
    Creates the file with headers if it doesn't exist.
    Skips duplicates based on experiment_id.
    """
    columns = list(SCHEMA.keys())
    new_df = pd.DataFrame([row])[columns]

    if os.path.exists(master_csv):
        existing_df = pd.read_csv(master_csv)
        # Deduplicate by experiment_id
        if row["experiment_id"] in existing_df["experiment_id"].values:
            logging.info(f"Updating existing entry for {row['experiment_id']}")
            existing_df = existing_df[existing_df["experiment_id"] != row["experiment_id"]]
        master_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        master_df = new_df

    master_df.to_csv(master_csv, index=False)
    logging.info(f"Master log updated: {master_csv} ({len(master_df)} experiments)")


def load_master_log(master_csv: str = "master_experiment_log.csv") -> pd.DataFrame:
    """Load the master experiment log."""
    if not os.path.exists(master_csv):
        logging.warning(f"Master log not found: {master_csv}")
        return pd.DataFrame(columns=list(SCHEMA.keys()))
    return pd.read_csv(master_csv)


def scan_and_build(scan_dir: str, master_csv: str = "master_experiment_log.csv") -> pd.DataFrame:
    """
    Scan a directory for all experiment folders and rebuild the master log.
    Finds folders matching pattern: experiments_*
    """
    scan_path = Path(scan_dir)
    exp_folders = sorted([
        f for f in scan_path.iterdir()
        if f.is_dir() and f.name.startswith("experiments_")
    ])

    if not exp_folders:
        logging.warning(f"No experiment folders found in {scan_dir}")
        return pd.DataFrame(columns=list(SCHEMA.keys()))

    logging.info(f"Found {len(exp_folders)} experiment folders in {scan_dir}")

    rows = []
    for folder in exp_folders:
        logging.info(f"Processing: {folder.name}")
        try:
            row = build_experiment_row(str(folder))
            rows.append(row)
        except Exception as e:
            logging.error(f"Failed to process {folder.name}: {e}")
            row = get_empty_row()
            row["experiment_id"] = folder.name
            row["status"] = "failed"
            row["notes"] = str(e)
            rows.append(row)

    columns = list(SCHEMA.keys())
    master_df = pd.DataFrame(rows)[columns]
    master_df.to_csv(master_csv, index=False)
    logging.info(f"Master log saved: {master_csv} ({len(master_df)} experiments)")

    return master_df


# ─────────────────────────────────────────────────────────────────────────────
# QUERY HELPERS — Convenience filters for common lookups
# ─────────────────────────────────────────────────────────────────────────────

def best_config_for(
    df: pd.DataFrame,
    model: Optional[str] = None,
    fl_algorithm: Optional[str] = None,
    pred_len: Optional[int] = None,
    metric: str = "best_val_mae",
    top_k: int = 5,
) -> pd.DataFrame:
    """
    Filter and rank experiments.

    Examples:
        # Best LR for BERT with horizon=72
        best_config_for(df, model="bert_nonlinear", pred_len=72)

        # Best algorithm for GPT4TS
        best_config_for(df, model="gpt4ts_nonlinear")

        # Overall leaderboard
        best_config_for(df, top_k=10)
    """
    mask = pd.Series(True, index=df.index)
    if model is not None:
        mask &= df["model"] == model
    if fl_algorithm is not None:
        mask &= df["fl_algorithm"] == fl_algorithm
    if pred_len is not None:
        mask &= df["pred_len"] == pred_len

    filtered = df[mask].copy()
    if filtered.empty:
        logging.warning("No experiments match the filter criteria")
        return filtered

    # Sort by metric (ascending = lower is better for loss/MAE/RMSE)
    display_cols = [
        "experiment_id", "model", "fl_algorithm", "pred_len",
        "learning_rate", "local_epochs", "llm_layers",
        "best_val_mae", "best_val_rmse", "best_test_mae", "best_test_rmse",
        "fairness_ratio", "total_comm_mb",
        "converged", "overfit_ratio", "status",
    ]
    display_cols = [c for c in display_cols if c in filtered.columns]

    return filtered.sort_values(metric, ascending=True).head(top_k)[display_cols]


def leaderboard(
    df: pd.DataFrame,
    group_by: List[str] = None,
    metric: str = "best_test_mae",
    top_k: int = 1,
) -> pd.DataFrame:
    """
    Create a leaderboard grouped by (model × algorithm × pred_len).
    Shows the top-k best experiments per group.

    Usage:
        leaderboard(df)  # Default: group by model × algorithm × pred_len, top-1 per group
        leaderboard(df, group_by=["model", "pred_len"], top_k=5)  # Top-5 per group
    """
    if group_by is None:
        group_by = ["model", "fl_algorithm", "pred_len"]

    valid_groups = [g for g in group_by if g in df.columns]
    if not valid_groups:
        return df

    # For each group, keep the top-k rows with the best metric
    best_df = df.loc[df.groupby(valid_groups)[metric].apply(
        lambda x: x.nsmallest(top_k).index
    ).explode().values].copy()

    display_cols = [
        "experiment_id",
    ] + valid_groups + [
        metric,
        "best_val_mae", "best_test_mae",
        "learning_rate", "local_epochs",
        "fairness_ratio", "overfit_ratio",
        "total_comm_mb", "total_training_time_min",
        "converged", "status",
    ]
    display_cols = [c for c in display_cols if c in best_df.columns]

    return best_df.sort_values(metric, ascending=True)[display_cols].reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Master Experiment Log — One Row Per Experiment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rebuild master log from all experiments in flower_app/
  python master_experiment_log.py --scan-dir . --output master_experiment_log.csv

  # Process a single experiment
  python master_experiment_log.py --exp-dir experiments_gpt4ts_20250101_120000

  # Print schema documentation
  python master_experiment_log.py --schema
        """
    )
    parser.add_argument("--scan-dir", type=str, default=None,
                        help="Directory to scan for experiment_* folders")
    parser.add_argument("--exp-dir", type=str, default=None,
                        help="Single experiment directory to process")
    parser.add_argument("--output", type=str, default="master_experiment_log.csv",
                        help="Output CSV path (default: master_experiment_log.csv)")
    parser.add_argument("--schema", action="store_true",
                        help="Print schema documentation and exit")
    parser.add_argument("--leaderboard", nargs="?", const=1, type=int, default=None,
                        help="Print leaderboard from existing master log (optionally specify top-k per group, e.g., --leaderboard 5)")

    args = parser.parse_args()

    if args.schema:
        docs = get_schema_docs()
        # Group by prefix for display
        print("\n" + "=" * 100)
        print("MASTER EXPERIMENT LOG — SCHEMA DOCUMENTATION")
        print(f"Total columns: {len(SCHEMA)}")
        print("=" * 100)
        for _, row in docs.iterrows():
            print(f"  {row['column']:35s}  {row['dtype']:6s}  {row['description']}")
        print("=" * 100)
        return

    if args.leaderboard is not None:
        df = load_master_log(args.output)
        if df.empty:
            print("No master log found. Run --scan-dir first.")
            return
        print("\n" + "=" * 180)
        print(f"LEADERBOARD (Top {args.leaderboard} per group)")
        print("=" * 180)
        lb = leaderboard(df, top_k=args.leaderboard)
        with pd.option_context('display.max_columns', None, 'display.width', None, 'display.max_colwidth', None):
            print(lb.to_string(index=False))
        return

    if args.exp_dir:
        row = build_experiment_row(args.exp_dir)
        append_to_master_log(row, args.output)
        print(f"\nProcessed: {args.exp_dir}")
        print(f"Status: {row['status']}")
        if row["best_val_mae"] is not None:
            print(f"Best Val MAE: {row['best_val_mae']:.6f} (round {row['best_round']})")
        return

    if args.scan_dir:
        df = scan_and_build(args.scan_dir, args.output)
        print(f"\nProcessed {len(df)} experiments → {args.output}")

        # Print quick summary
        if not df.empty:
            completed = (df["status"] == "completed").sum()
            early_stopped = (df["status"] == "early_stopped").sum()
            failed = (df["status"] == "failed").sum()
            print(f"  Completed: {completed}  |  Early stopped: {early_stopped}  |  Failed: {failed}")

            if "best_val_mae" in df.columns and df["best_val_mae"].notna().any():
                best_idx = df["best_val_mae"].idxmin()
                best = df.loc[best_idx]
                print(f"\n  🏆 Best experiment: {best['experiment_id']}")
                print(f"     Model: {best['model']}  |  Algorithm: {best['fl_algorithm']}  |  Horizon: {best['pred_len']}")
                print(f"     Val MAE: {best['best_val_mae']:.6f}  |  Test MAE: {best.get('best_test_mae', 'N/A')}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
