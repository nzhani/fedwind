#!/usr/bin/env python3
"""
Centralized baseline that mirrors the federated setup for direct comparison.

Every detail that affects the metrics is kept identical to the Flower pipeline:
  - LR schedule: linear warmup then exponential decay (same formula as client_app.py)
  - Each "round" = local_epochs training epochs (matches one FL round)
  - Evaluation: per-city val + test, then simple-averaged across 5 cities
    (matches how server_app.py aggregates client metrics)
  - Early stopping: same patience logic on avg val_loss, best checkpoint restored
  - Output: training_summary.csv with the same columns as the federated run

FedProx / strategy params in the .conf file are ignored — they are federated-specific.

Usage:
    python run_centralized.py --config experiment_config_OPTIMIZED_ANTI_OVERFIT.conf
    python run_centralized.py --rounds 20 --lr 0.0003 --pred-len 72
    python run_centralized.py --config my.conf --pred-len 96   # conf + CLI override
"""

import os
import sys
import argparse
import copy
import time
import logging
from datetime import datetime

import torch
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from my_flower_app.task import (
    get_default_configs,
    get_dataset_config,
    Net,
    load_centralized_train,
    load_client_val,
    load_client_test,
    train as train_fn,
    test as test_fn,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------------------------------------------------------------------
# Config resolution: defaults <- .conf file <- CLI args
# ---------------------------------------------------------------------------

DEFAULTS = {
    "rounds": 20,
    "local_epochs": 1,
    "lr": 0.0003,
    "batch_size": 32,
    "warmup_rounds": 3,
    "weight_decay": 0.01,
    "early_stop_patience": 5,
    "seq_len": 336,
    "pred_len": 120,
    "patch_size": 16,
    "stride": 16,
    "d_model": 768,
    "hidden_size": 16,
    "kernel_size": 3,
    "llm_layers": 4,
    "n_heads": 4,
    "e_layers": 3,
    "d_layers": 1,
    "d_ff": 768,
    "peft_method": "lora",
    "is_pretrained": True,
    "lora_r": 8,
    "lora_alpha": 16,
    "lora_dropout": 0.15,
    "dropout": 0.15,
    "model": "gpt4ts_nonlinear",
    "dataset_name": "vnmet",
}

# Maps .conf shell-variable names  ->  (internal key, type)
CONF_KEY_MAP = {
    "NUM_ROUNDS": ("rounds", int),
    "LOCAL_EPOCHS": ("local_epochs", int),
    "LEARNING_RATE": ("lr", float),
    "BATCH_SIZE": ("batch_size", int),
    "WARMUP_ROUNDS": ("warmup_rounds", int),
    "WEIGHT_DECAY": ("weight_decay", float),
    "EARLY_STOP_PATIENCE": ("early_stop_patience", int),
    "SEQ_LEN": ("seq_len", int),
    "PRED_LEN": ("pred_len", int),
    "PATCH_SIZE": ("patch_size", int),
    "STRIDE": ("stride", int),
    "D_MODEL": ("d_model", int),
    "HIDDEN_SIZE": ("hidden_size", int),
    "KERNEL_SIZE": ("kernel_size", int),
    "LLM_LAYERS": ("llm_layers", int),
    "N_HEADS": ("n_heads", int),
    "E_LAYERS": ("e_layers", int),
    "D_LAYERS": ("d_layers", int),
    "D_FF": ("d_ff", int),
    "PEFT_METHOD": ("peft_method", str),
    "IS_PRETRAINED": ("is_pretrained", lambda v: v.lower() == "true"),
    "LORA_R": ("lora_r", int),
    "LORA_ALPHA": ("lora_alpha", int),
    "LORA_DROPOUT": ("lora_dropout", float),
    "DROPOUT": ("dropout", float),
    "MODEL": ("model", str),
    "DATASET_NAME": ("dataset_name", str),
}


def parse_conf_file(path):
    """Read shell-style KEY=VALUE lines, skip comments and blanks."""
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            val = val.strip().strip('"').strip("'")
            if val:
                out[key.strip()] = val
    return out


def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=str, default=None)
    p.add_argument("--rounds", type=int, default=None)
    p.add_argument("--local-epochs", type=int, default=None)
    p.add_argument("--lr", type=float, default=None)
    p.add_argument("--batch-size", type=int, default=None)
    p.add_argument("--warmup-rounds", type=int, default=None)
    p.add_argument("--weight-decay", type=float, default=None)
    p.add_argument("--early-stop-patience", type=int, default=None)
    p.add_argument("--seq-len", type=int, default=None)
    p.add_argument("--pred-len", type=int, default=None)
    p.add_argument("--patch-size", type=int, default=None)
    p.add_argument("--stride", type=int, default=None)
    p.add_argument("--d-model", type=int, default=None)
    p.add_argument("--hidden-size", type=int, default=None)
    p.add_argument("--kernel-size", type=int, default=None)
    p.add_argument("--llm-layers", type=int, default=None)
    p.add_argument("--n-heads", type=int, default=None)
    p.add_argument("--e-layers", type=int, default=None)
    p.add_argument("--d-layers", type=int, default=None)
    p.add_argument("--d-ff", type=int, default=None)
    p.add_argument("--lora-r", type=int, default=None)
    p.add_argument("--lora-alpha", type=int, default=None)
    p.add_argument("--lora-dropout", type=float, default=None)
    p.add_argument("--dropout", type=float, default=None)
    p.add_argument("--peft-method", type=str, default=None)
    p.add_argument("--is-pretrained", type=lambda v: v.lower() == "true", default=None)
    p.add_argument("--model", type=str, default=None)
    p.add_argument("--dataset-name", type=str, default=None)
    p.add_argument("--exp-dir", type=str, default=None)
    return p


# argparse dest names (dashes become underscores) -> internal config keys
CLI_KEY_MAP = {k.replace("-", "_"): k for k in DEFAULTS}


def resolve_config(args):
    """Merge: defaults <- .conf <- CLI."""
    cfg = dict(DEFAULTS)

    if args.config:
        conf = parse_conf_file(args.config)
        for conf_key, (param, typ) in CONF_KEY_MAP.items():
            if conf_key in conf:
                cfg[param] = typ(conf[conf_key])

    for cli_dest, param in CLI_KEY_MAP.items():
        val = getattr(args, cli_dest, None)
        if val is not None:
            cfg[param] = val

    return cfg


# ---------------------------------------------------------------------------
# LR schedule (identical to client_app.py lines 66-74)
# ---------------------------------------------------------------------------


def compute_lr(base_lr, current_round, warmup_rounds):
    if current_round <= warmup_rounds:
        return base_lr * (current_round / warmup_rounds)
    decay_round = current_round - warmup_rounds
    return base_lr * (0.98**decay_round)


# ---------------------------------------------------------------------------
# Per-city evaluation (matches server_app.py simple-average aggregation)
# ---------------------------------------------------------------------------


def _save_predictions_to_csv(preds, trues, exp_dir, city_id, round_num, split_name, pred_len):
    """Save predictions vs ground truth in the same CSV format as client_app.py."""
    if preds.size == 0:
        logging.warning(f"[CENTRALIZED city {city_id}] No predictions to save for {split_name} split")
        return

    preds_2d = preds.reshape(-1, pred_len)
    trues_2d = trues.reshape(-1, pred_len)

    data = {}
    for t in range(pred_len):
        data[f"pred_t{t}"] = preds_2d[:, t]
        data[f"true_t{t}"] = trues_2d[:, t]

    data["sample_idx"] = np.arange(len(preds_2d))
    data["client_id"] = city_id
    data["round"] = round_num
    data["split"] = split_name

    metadata_cols = ["sample_idx", "client_id", "round", "split"]
    pred_true_cols = [f"pred_t{t}" for t in range(pred_len)] + [f"true_t{t}" for t in range(pred_len)]
    df = pd.DataFrame(data)[metadata_cols + pred_true_cols]

    predictions_dir = os.path.join(exp_dir, "predictions")
    os.makedirs(predictions_dir, exist_ok=True)
    csv_path = os.path.join(predictions_dir, f"client{city_id}_round{round_num}_{split_name}.csv")
    df.to_csv(csv_path, index=False)
    logging.info(f"[CENTRALIZED city {city_id}] Saved {len(df)} {split_name} predictions to {csv_path}")


def evaluate_per_city(model, device, cfg_ns, bs, exp_dir, round_num, dataset_name="VNMET"):
    ds_cfg = get_dataset_config(dataset_name)
    val_losses, val_maes, val_rmses = [], [], []
    test_losses, test_maes, test_rmses = [], [], []
    val_durations, test_durations = [], []

    for city_id in range(ds_cfg["num_clients"]):
        valloader = load_client_val(city_id, bs=bs, cfg=cfg_ns, dataset_name=dataset_name)
        testloader = load_client_test(city_id, bs=bs, cfg=cfg_ns, dataset_name=dataset_name)

        t0 = time.time()
        v_loss, v_mae, v_rmse, val_preds, val_trues = test_fn(model, valloader, device, return_predictions=True)
        val_durations.append(time.time() - t0)
        _save_predictions_to_csv(val_preds, val_trues, exp_dir, city_id, round_num, "val", cfg_ns.pred_len)

        t0 = time.time()
        t_loss, t_mae, t_rmse, test_preds, test_trues = test_fn(model, testloader, device, return_predictions=True)
        test_durations.append(time.time() - t0)
        _save_predictions_to_csv(test_preds, test_trues, exp_dir, city_id, round_num, "test", cfg_ns.pred_len)

        val_losses.append(v_loss)
        val_maes.append(v_mae)
        val_rmses.append(v_rmse)
        test_losses.append(t_loss)
        test_maes.append(t_mae)
        test_rmses.append(t_rmse)

        logging.info(
            f"  City {city_id}: val_loss={v_loss:.6f} val_mae={v_mae:.6f} "
            f"test_loss={t_loss:.6f} test_mae={t_mae:.6f}"
        )

    return {
        "val_loss": sum(val_losses) / len(val_losses),
        "val_mae": sum(val_maes) / len(val_maes),
        "val_rmse": sum(val_rmses) / len(val_rmses),
        "test_loss": sum(test_losses) / len(test_losses),
        "test_mae": sum(test_maes) / len(test_maes),
        "test_rmse": sum(test_rmses) / len(test_rmses),
        "val_duration_sec": sum(val_durations) / len(val_durations),
        "test_duration_sec": sum(test_durations) / len(test_durations),
    }


# ---------------------------------------------------------------------------
# Main training loop
# ---------------------------------------------------------------------------


def main():
    args = build_parser().parse_args()
    cfg = resolve_config(args)
    ds_cfg = get_dataset_config(cfg["dataset_name"])
    num_cities = ds_cfg["num_clients"]

    exp_dir = args.exp_dir or os.path.join(
        "/raid/tin_trungchau/tmp",
        f"centralized_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(exp_dir, exist_ok=True)

    # Add file handler so everything also goes to training.log
    log_path = os.path.join(exp_dir, "training.log")
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(file_handler)

    logging.info("=" * 60)
    logging.info("CENTRALIZED TRAINING  (mirrors federated setup)")
    logging.info("=" * 60)
    logging.info("DATASET CONFIGURATION (from DATASET_REGISTRY):")
    logging.info(f"  dataset_name: {cfg['dataset_name']}")
    logging.info(f"  folder: {ds_cfg['folder']}")
    logging.info(f"  target: {ds_cfg['target']}")
    logging.info(f"  num_clients: {num_cities}")
    logging.info("=" * 60)
    for k, v in sorted(cfg.items()):
        logging.info(f"  {k}: {v}")
    logging.info(f"  exp_dir: {exp_dir}")
    logging.info("=" * 60)

    # Save config for reproducibility
    with open(os.path.join(exp_dir, "config.txt"), "w") as f:
        f.write("# Centralized experiment config\n")
        for k, v in sorted(cfg.items()):
            f.write(f"{k}={v}\n")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    logging.info(f"Device: {device}")

    cfg_ns = get_default_configs(
        model=cfg["model"],
        pred_len=cfg["pred_len"],
        seq_len=cfg["seq_len"],
        patch_size=cfg["patch_size"],
        stride=cfg["stride"],
        d_model=cfg["d_model"],
        hidden_size=cfg["hidden_size"],
        kernel_size=cfg["kernel_size"],
        llm_layers=cfg["llm_layers"],
        n_heads=cfg["n_heads"],
        e_layers=cfg["e_layers"],
        d_layers=cfg["d_layers"],
        d_ff=cfg["d_ff"],
        peft_method=cfg["peft_method"],
        is_pretrained=cfg["is_pretrained"],
        lora_r=cfg["lora_r"],
        lora_alpha=cfg["lora_alpha"],
        lora_dropout=cfg["lora_dropout"],
        dropout=cfg["dropout"],
    )

    model = Net(configs=cfg_ns, device=device)
    trainloader = load_centralized_train(
        bs=cfg["batch_size"], cfg=cfg_ns, dataset_name=cfg["dataset_name"]
    )
    logging.info(
        f"Training samples: {len(trainloader.dataset)} across {num_cities} datasets from {cfg['dataset_name']}"
    )

    best = {"round": 0, "loss": float("inf"), "state": None}
    best_val_loss = float("inf")
    early_stop_counter = 0
    results = []

    training_start = time.time()

    for r in range(1, cfg["rounds"] + 1):
        round_start = time.time()
        lr = compute_lr(cfg["lr"], r, cfg["warmup_rounds"])
        logging.info(f"\n[Round {r}/{cfg['rounds']}] LR={lr:.8f}")

        # Train for local_epochs epochs — one round = one FL round
        train_start = time.time()
        train_loss, _, _ = train_fn(
            model,
            trainloader,
            epochs=cfg["local_epochs"],
            lr=lr,
            device=device,
            weight_decay=cfg["weight_decay"],
        )
        train_duration = time.time() - train_start

        # Evaluate per city, average equally
        eval_metrics = evaluate_per_city(
            model, device, cfg_ns, cfg["batch_size"], exp_dir, r, dataset_name=cfg["dataset_name"]
        )
        round_duration = time.time() - round_start

        row = {
            "round": r,
            "train_loss": train_loss,
            "val_loss": eval_metrics["val_loss"],
            "val_mae": eval_metrics["val_mae"],
            "val_rmse": eval_metrics["val_rmse"],
            "test_loss": eval_metrics["test_loss"],
            "test_mae": eval_metrics["test_mae"],
            "test_rmse": eval_metrics["test_rmse"],
            "best_loss": best["loss"],
            "round_duration_sec": round_duration,
            "train_duration_sec": train_duration,
            "val_duration_sec": eval_metrics["val_duration_sec"],
            "test_duration_sec": eval_metrics["test_duration_sec"],
        }
        results.append(row)

        logging.info(
            f"[Round {r}] train={train_loss:.6f}  "
            f"val_loss={eval_metrics['val_loss']:.6f}  val_mae={eval_metrics['val_mae']:.6f}  "
            f"test_loss={eval_metrics['test_loss']:.6f}  test_mae={eval_metrics['test_mae']:.6f}  "
            f"({round_duration:.1f}s)"
        )

        # Best checkpoint (on val_loss)
        if eval_metrics["val_loss"] < best["loss"]:
            best["loss"] = eval_metrics["val_loss"]
            best["round"] = r
            best["state"] = copy.deepcopy(model.state_dict())
            logging.info(f"[Round {r}] Best checkpoint updated (val_loss={best['loss']:.6f})")

        # Early stopping (same logic as server_app.py)
        if eval_metrics["val_loss"] < best_val_loss:
            best_val_loss = eval_metrics["val_loss"]
            early_stop_counter = 0
        else:
            early_stop_counter += 1
            logging.info(f"[Round {r}] Early stop counter: {early_stop_counter}/{cfg['early_stop_patience']}")
            if early_stop_counter >= cfg["early_stop_patience"]:
                logging.info(f"[Round {r}] Early stopping triggered.")
                break

    total_time = time.time() - training_start

    # Restore best model
    if best["state"] is not None:
        model.load_state_dict(best["state"])
        logging.info(f"Restored best model from round {best['round']} (val_loss={best['loss']:.6f})")

    # Save outputs (same structure as federated experiments)
    torch.save(model.state_dict(), os.path.join(exp_dir, "final_model.pt"))

    pd.DataFrame(results).to_csv(os.path.join(exp_dir, "training_summary.csv"), index=False)

    num_completed = len(results)
    num_trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    num_total_params = sum(p.numel() for p in model.parameters())
    model_size_mb = sum(p.numel() * p.element_size() for p in model.parameters()) / (1024 * 1024)


    pd.DataFrame(
        [
            {
                "model_name": cfg["model"],
                "fl_algorithm": "centralized",
                "pred_len": cfg["pred_len"],
                "learning_rate": cfg["lr"],
                "local_epochs": cfg["local_epochs"],
                "num_clients": num_cities,
                "num_trainable_params": num_trainable_params,
                "num_total_params": num_total_params,
                "model_size_mb": model_size_mb,
                "lora_r": cfg["lora_r"],
                "lora_alpha": cfg["lora_alpha"],
                "patch_size": cfg["patch_size"],
                "stride": cfg["stride"],
                "random_seed": 2021,
                "total_training_time_sec": total_time,
                "total_training_time_min": total_time / 60,
                "num_rounds": num_completed,
                "avg_time_per_round_sec": total_time / max(1, num_completed),
                "start_timestamp": datetime.fromtimestamp(training_start).strftime("%Y-%m-%d %H:%M:%S"),
                "end_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    ).to_csv(os.path.join(exp_dir, "timing_summary.csv"), index=False)

    logging.info(f"\nDone. {num_completed} rounds in {total_time:.1f}s. Results: {exp_dir}")


if __name__ == "__main__":
    main()
