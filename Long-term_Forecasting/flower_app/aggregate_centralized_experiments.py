#!/usr/bin/env python3
"""
Aggregate centralized experiment results from /raid/tin_trungchau/tmp into a
master CSV with the same schema as master_experiment_log.csv.
"""

import argparse
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


DEFAULT_TMP_DIR = "/raid/tin_trungchau/tmp"
DEFAULT_OUTPUT = "/raid/tin_trungchau/federated_learning/Long-term_Forecasting/flower_app/centralized_experiment_log.csv"
DEFAULT_SCHEMA_CSV = "/raid/tin_trungchau/federated_learning/Long-term_Forecasting/flower_app/master_experiment_log.csv"


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else round(f, 6)
    except (ValueError, TypeError):
        return None


def _parse_config_txt(config_path: Path) -> Dict[str, Any]:
    """Parse config.txt in either 'key=value' or 'key: value' style."""
    result: Dict[str, Any] = {}
    if not config_path.exists():
        return result

    pattern_colon = re.compile(r"^([\w-]+)\s*:\s*(.+)$")
    pattern_equal = re.compile(r"^([\w-]+)\s*=\s*(.+)$")

    with config_path.open("r") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = pattern_colon.match(line) or pattern_equal.match(line)
            if not match:
                continue
            key, val = match.groups()
            key = key.strip()
            val = val.strip()

            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    if val.lower() == "true":
                        val = True
                    elif val.lower() == "false":
                        val = False
            result[key] = val

    return result


def _load_training_summary(csv_path: Path) -> Optional[pd.DataFrame]:
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return None
        return df.sort_values("round").reset_index(drop=True)
    except Exception:
        return None


def _load_timing_summary(csv_path: Path) -> Dict[str, Any]:
    if not csv_path.exists():
        return {}
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return {}
        return df.iloc[0].to_dict()
    except Exception:
        return {}


def _get_schema_columns(schema_csv: Optional[str]) -> List[str]:
    if schema_csv and os.path.exists(schema_csv):
        with open(schema_csv, "r") as f:
            header = f.readline().strip()
        if header:
            return header.split(",")

    try:
        import master_experiment_log  # type: ignore
        return list(master_experiment_log.SCHEMA.keys())
    except Exception:
        pass

    # Fallback minimal schema (should rarely happen)
    return [
        "experiment_id", "timestamp", "seed", "model", "fl_algorithm", "pred_len",
        "learning_rate", "local_epochs", "num_rounds_configured", "num_rounds_completed",
        "batch_size", "num_clients", "weight_decay", "warmup_rounds", "proximal_mu",
        "early_stop_patience", "dropout", "seq_len", "patch_size", "stride",
        "num_patches", "d_model", "hidden_size", "kernel_size", "llm_layers",
        "lora_r", "lora_alpha", "lora_dropout", "num_trainable_params",
        "num_total_params", "model_payload_mb", "best_round", "best_val_mse",
        "best_val_mae", "best_val_rmse", "best_test_mse", "best_test_mae",
        "best_test_rmse", "best_train_mse", "first_round_val_loss",
        "final_round_val_loss", "val_loss_improvement_pct", "overfit_gap",
        "overfit_ratio", "converged", "loss_trend_last3", "early_stopped",
        "early_stop_round", "client_val_mae_mean", "client_val_mae_std",
        "client_val_mae_min", "client_val_mae_max", "client_val_mae_best_city",
        "client_val_mae_worst_city", "fairness_ratio", "payload_per_round_mb",
        "total_comm_mb", "comm_to_best_mb", "rounds_per_mae_point",
        "total_training_time_sec", "total_training_time_min",
        "avg_round_duration_sec", "avg_client_train_dur_sec", "max_client_train_dur_sec",
        "status", "experiment_dir", "notes",
    ]


def _empty_row(columns: List[str]) -> Dict[str, Any]:
    row = {c: None for c in columns}
    if "notes" in row:
        row["notes"] = ""
    return row


def build_row(exp_dir: Path, columns: List[str]) -> Dict[str, Any]:
    row = _empty_row(columns)
    row["experiment_id"] = exp_dir.name
    row["experiment_dir"] = str(exp_dir.resolve())

    ts_match = re.search(r"(\d{8}_\d{6})", exp_dir.name)
    if ts_match:
        row["timestamp"] = ts_match.group(1)

    config = _parse_config_txt(exp_dir / "config.txt")

    row["seed"] = config.get("random-seed", config.get("random_seed"))
    row["model"] = config.get("model")
    row["fl_algorithm"] = config.get("strategy", "centralized")
    row["pred_len"] = config.get("pred_len", config.get("pred-len"))

    row["learning_rate"] = config.get("lr")
    row["local_epochs"] = config.get("local_epochs", config.get("local-epochs"))
    row["num_rounds_configured"] = config.get("rounds", config.get("num_server_rounds", config.get("num-server-rounds")))
    row["batch_size"] = config.get("batch_size", config.get("batch-size"))
    row["weight_decay"] = config.get("weight_decay", config.get("weight-decay"))
    row["warmup_rounds"] = config.get("warmup_rounds", config.get("warmup-rounds"))
    row["early_stop_patience"] = config.get("early_stop_patience", config.get("early-stop-patience"))
    row["dropout"] = config.get("dropout")

    row["seq_len"] = config.get("seq_len", config.get("seq-len"))
    row["patch_size"] = config.get("patch_size", config.get("patch-size"))
    row["stride"] = config.get("stride")
    row["d_model"] = config.get("d_model", config.get("d-model"))
    row["hidden_size"] = config.get("hidden_size", config.get("hidden-size"))
    row["kernel_size"] = config.get("kernel_size", config.get("kernel-size"))
    row["llm_layers"] = config.get("llm_layers", config.get("llm-layers"))
    row["lora_r"] = config.get("lora_r", config.get("lora-r"))
    row["lora_alpha"] = config.get("lora_alpha", config.get("lora-alpha"))
    row["lora_dropout"] = config.get("lora_dropout", config.get("lora-dropout"))
    row["peft_method"] = config.get("peft_method", config.get("peft-method"))
    row["is_pretrained"] = config.get("is_pretrained", config.get("is-pretrained"))
    row["dataset_name"] = config.get("dataset_name", config.get("dataset-name"))
    # target_column comes from DATASET_REGISTRY, not config
    ds_name = row.get("dataset_name")
    if ds_name:
        try:
            ds_cfg = DATASET_REGISTRY.get(ds_name.upper(), {})
            row["target_column"] = ds_cfg.get("target")
        except Exception:
            pass
    if row.get("seq_len") is not None and row.get("patch_size") is not None and row.get("stride") is not None:
        row["num_patches"] = (row["seq_len"] - row["patch_size"]) // row["stride"] + 2

    ts_df = _load_training_summary(exp_dir / "training_summary.csv")
    if ts_df is not None and len(ts_df) > 0:
        row["num_rounds_completed"] = int(ts_df["round"].max())

        if "val_loss" in ts_df.columns:
            valid_mask = ts_df["val_loss"].notna()
            if valid_mask.any():
                best_idx = ts_df.loc[valid_mask, "val_loss"].idxmin()
                best = ts_df.loc[best_idx]
                row["best_round"] = int(best["round"])
                row["best_val_mse"] = _safe_float(best.get("val_loss"))
                row["best_val_mae"] = _safe_float(best.get("val_mae"))
                row["best_val_rmse"] = _safe_float(best.get("val_rmse"))
                row["best_test_mse"] = _safe_float(best.get("test_loss"))
                row["best_test_mae"] = _safe_float(best.get("test_mae"))
                row["best_test_rmse"] = _safe_float(best.get("test_rmse"))
                row["best_train_mse"] = _safe_float(best.get("train_loss"))

        first_row = ts_df.iloc[0]
        final_row = ts_df.iloc[-1]
        row["first_round_val_loss"] = _safe_float(first_row.get("val_loss"))
        row["final_round_val_loss"] = _safe_float(final_row.get("val_loss"))

        if row.get("first_round_val_loss") is not None and row.get("best_val_mse") is not None:
            if row["first_round_val_loss"] > 0:
                row["val_loss_improvement_pct"] = round(
                    (row["first_round_val_loss"] - row["best_val_mse"]) / row["first_round_val_loss"] * 100, 2
                )
                row["converged"] = row["val_loss_improvement_pct"] >= 5.0

        if row.get("best_val_mse") is not None and row.get("best_train_mse") is not None:
            row["overfit_gap"] = round(row["best_val_mse"] - row["best_train_mse"], 6)
            if row["best_train_mse"] > 0:
                row["overfit_ratio"] = round(row["best_val_mse"] / row["best_train_mse"], 4)

        if "val_loss" in ts_df.columns and len(ts_df) >= 3:
            last3 = ts_df["val_loss"].tail(3).dropna().values
            if len(last3) == 3:
                if last3[2] < last3[0] - 1e-6:
                    row["loss_trend_last3"] = "decreasing"
                elif last3[2] > last3[0] + 1e-6:
                    row["loss_trend_last3"] = "increasing"
                else:
                    row["loss_trend_last3"] = "flat"

        if "val_mae" in ts_df.columns and row.get("best_round"):
            first_mae = ts_df["val_mae"].dropna().iloc[0] if not ts_df["val_mae"].dropna().empty else None
            if first_mae is not None and row.get("best_val_mae") is not None:
                mae_improvement = first_mae - row["best_val_mae"]
                if mae_improvement > 0.001:
                    row["rounds_per_mae_point"] = round(row["best_round"] / (mae_improvement / 0.01), 2)

        if "round_duration_sec" in ts_df.columns:
            row["avg_round_duration_sec"] = round(float(ts_df["round_duration_sec"].mean()), 2)

        if "train_duration_sec" in ts_df.columns:
            row["avg_client_train_dur_sec"] = round(float(ts_df["train_duration_sec"].mean()), 2)
            row["max_client_train_dur_sec"] = round(float(ts_df["train_duration_sec"].max()), 2)

    timing = _load_timing_summary(exp_dir / "timing_summary.csv")
    if timing:
        row["total_training_time_sec"] = _safe_float(timing.get("total_training_time_sec"))
        row["total_training_time_min"] = _safe_float(timing.get("total_training_time_min"))
        if row.get("seed") is None:
            row["seed"] = timing.get("random_seed", timing.get("random-seed"))
        if "num_trainable_params" in timing:
            row["num_trainable_params"] = timing.get("num_trainable_params")
        if "num_total_params" in timing:
            row["num_total_params"] = timing.get("num_total_params")
        if "model_size_mb" in timing:
            row["model_payload_mb"] = _safe_float(timing.get("model_size_mb"))
        if "num_clients" in timing:
            row["num_clients"] = timing.get("num_clients")
        if row.get("num_rounds_configured") is None and "num_rounds" in timing:
            row["num_rounds_configured"] = timing.get("num_rounds")
        if row.get("avg_round_duration_sec") is None and "avg_time_per_round_sec" in timing:
            row["avg_round_duration_sec"] = _safe_float(timing.get("avg_time_per_round_sec"))

    if row.get("num_rounds_completed") is not None and row.get("num_rounds_configured") is not None:
        row["early_stopped"] = row["num_rounds_completed"] < row["num_rounds_configured"]
        if row["early_stopped"]:
            row["early_stop_round"] = row["num_rounds_completed"]

    if row.get("model_payload_mb") is not None:
        row["payload_per_round_mb"] = row["model_payload_mb"]
    if row.get("total_comm_mb") is None:
        row["total_comm_mb"] = 0.0
    if row.get("comm_to_best_mb") is None:
        row["comm_to_best_mb"] = 0.0

    if ts_df is not None and len(ts_df) > 0:
        row["status"] = "early_stopped" if row.get("early_stopped") else "completed"
    else:
        row["status"] = "failed"

    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate centralized experiments into a master CSV.")
    parser.add_argument("--tmp-dir", type=str, default=DEFAULT_TMP_DIR)
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema-from", type=str, default=DEFAULT_SCHEMA_CSV)
    parser.add_argument("--pattern", type=str, default="centralized_")
    args = parser.parse_args()

    tmp_dir = Path(args.tmp_dir)
    if not tmp_dir.exists():
        raise SystemExit(f"tmp-dir not found: {tmp_dir}")

    columns = _get_schema_columns(args.schema_from)
    exp_dirs = sorted([p for p in tmp_dir.iterdir() if p.is_dir() and p.name.startswith(args.pattern)])
    if not exp_dirs:
        raise SystemExit(f"No experiment folders found in {tmp_dir} with prefix '{args.pattern}'")

    rows = [build_row(p, columns) for p in exp_dirs]
    df = pd.DataFrame(rows)
    df = df[columns]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} experiments to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
