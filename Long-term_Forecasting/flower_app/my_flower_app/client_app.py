
"""my-flower-app: A Flower / PyTorch client that only trains locally."""
import torch
import time
import os
import sys
import pandas as pd
import numpy as np
from flwr.app import ArrayRecord, ConfigRecord, Context, Message, MetricRecord, RecordDict
from flwr.clientapp import ClientApp

from my_flower_app.task import Net, load_client_train, load_client_val, load_client_test, persistence_errors, train as train_fn, test as test_fn, trainable_state_dict
from my_flower_app.experiment import (build_model_configs, client_data_file, client_identity, client_label,
                                      client_seed, is_selected, seed_everything)
from my_flower_app.solar import evaluate_ghi, options as solar_options

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = ClientApp()


def _who(context: Context) -> ConfigRecord:
    """Who replies: the server keys per-client metrics by site id (MetricRecord holds numbers only).
    Flower's strategies count Array- and MetricRecords only, so this extra record is safe."""
    _, site = client_identity(context.node_config)
    return ConfigRecord({"site": site or ""})


def _skip_reply(msg: Message, pid: int, keep_arrays: bool, context: Context) -> Message:
    """
    Reply of a client whose site isn't selected for this run: weight 0, so it
    changes nothing in the weighted average; `skipped` lets the server leave it out.
    """
    content = {"metrics": MetricRecord({"num-examples": 0, "partition-id": pid, "skipped": 1}),
               "client": _who(context)}
    if keep_arrays:
        content["arrays"] = msg.content["arrays"]
    return Message(content=RecordDict(content), reply_to=msg)


@app.train()
def train(msg: Message, context: Context):
    conf = msg.content["config"]
    pid, _site = client_identity(context.node_config)
    label = client_label(context.node_config)
    if not is_selected(context.node_config, context.run_config):
        logging.info(f"[CLIENT {label}] Site not selected for this run; skipping training")
        return _skip_reply(msg, pid, keep_arrays=True, context=context)

    seed_everything(client_seed(int(context.run_config.get("random-seed", 2021)), context.node_config))
    # Same function as the server and evaluate(), so the backbone always matches (pretrained or not).
    # The server only transmits trainable params (adapters + projections);
    # loading with strict=False overlays them onto the backbone.
    configs = build_model_configs(context.run_config)
    configs.adalora_total_step = conf.get("adalora_total_step", configs.adalora_total_step)

    model = Net(configs=configs)
    state = msg.content["arrays"].to_torch_state_dict()
    if len(state) == 0:
        logging.error("Client received EMPTY weights. Skipping load_state_dict.")
    else:
        model.load_state_dict(state, strict=False)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model.to(device)

    npt = int(context.node_config.get("num-partitions", 1))
    bs  = context.run_config.get("batch-size", 32)
    dataset_name = context.run_config.get("dataset-name", "VNMET")
    data_file = client_data_file(context.node_config, context.run_config)
    percent = int(context.run_config.get("data-percent", 100))
    solar = solar_options(context.run_config)
    masked_loss = bool(solar and solar["daylight_mask"])
    trainloader = load_client_train(pid, npt, bs=bs, cfg=configs, dataset_name=dataset_name, data_file=data_file,
                                    percent=percent, solar=solar)
    
    # Get experiment directory from environment variable
    exp_dir = os.environ.get("FLOWER_EXP_DIR", ".")
    
    # Load validation set for tracking local overfitting
    valloader = load_client_val(pid, bs=bs, cfg=configs, dataset_name=dataset_name, data_file=data_file, solar=solar)
    logging.info(f"[CLIENT {pid}] Training on {len(trainloader.dataset)} samples, BatchSize={bs}")

    # --- Learning Rate Schedule: Warmup + Decay ---
    base_lr = msg.content["config"]["lr"]
    # CRITICAL FIX: Read server_round from msg.content["config"] where server sends it
    current_round = conf.get("server_round", 1)
    warmup_rounds = context.run_config.get("warmup-rounds", 3)  # Default 3 rounds warmup

    if current_round <= warmup_rounds:
        # Linear warmup: gradually increase LR from 0 to base_lr
        lr = base_lr * (current_round / warmup_rounds)
        logging.info(f"[CLIENT {pid}] Warmup phase: LR={lr:.6f} (round {current_round}/{warmup_rounds})")
    else:
        # After warmup: apply exponential decay
        decay_round = current_round - warmup_rounds
        lr = base_lr * (0.98 ** decay_round)  # decay 2% per round after warmup
        logging.info(f"[CLIENT {pid}] Decay phase: LR={lr:.6f} (round {current_round}, decay_round={decay_round})")

    # Get weight decay parameter for regularization
    weight_decay = context.run_config.get("weight-decay", 0.01)  # Default 0.01

    # Get proximal_mu for FedProx (if provided)
    proximal_mu = msg.content["config"].get("proximal_mu", None)

    # Save global model weights for FedProx proximal term
    global_weights = None
    if proximal_mu is not None:
        global_weights = {name: param.clone().detach() for name, param in model.named_parameters()}
        logging.info(f"[CLIENT {pid}] FedProx enabled with proximal_mu={proximal_mu}")

    # SCAFFOLD: Get control variates
    c_local = None
    c_global = None
    if "c_local" in msg.content:
        c_local = msg.content["c_local"].to_torch_state_dict()
        logging.info(f"[CLIENT {pid}] SCAFFOLD: Received local control variate")
    if "c_global" in msg.content:
        c_global = msg.content["c_global"].to_torch_state_dict()
        logging.info(f"[CLIENT {pid}] SCAFFOLD: Received global control variate")

    train_start_time = time.time()
    train_loss, history, new_c_local = train_fn(
        model,
        trainloader,
        context.run_config["local-epochs"],
        lr,
        device,
        valloader=valloader,
        weight_decay=weight_decay,
        global_weights=global_weights,
        proximal_mu=proximal_mu,
        c_local=c_local,
        c_global=c_global,
        masked_loss=masked_loss,
    )
    train_duration = time.time() - train_start_time

    logging.info(f"[CLIENT {pid}] Training complete. AvgTrainLoss={train_loss:.6f}, Duration={train_duration:.2f}s")
    
    # Save training history
    _save_metrics_history(history, exp_dir, label, current_round)

    arrays = ArrayRecord(trainable_state_dict(model))
    metrics = MetricRecord({
        "train_loss": float(train_loss),
        "train_duration_sec": float(train_duration),
        "num-examples": len(trainloader.dataset),
        "partition-id": pid,
    })
    
    content_dict = {"arrays": arrays, "metrics": metrics, "client": _who(context)}
    if new_c_local is not None:
        content_dict["c_local"] = ArrayRecord(new_c_local)
        logging.info(f"[CLIENT {pid}] SCAFFOLD: Returning updated local control variate")

    content = RecordDict(content_dict)
    return Message(content=content, reply_to=msg)


@app.evaluate()
def evaluate(msg: Message, context: Context):
    """
    Perform local validation and test evaluation on client's datasets.
    This is called by the server to get federated evaluation metrics.
    Evaluates on both the val and test splits; reports normalized and real-unit
    (m/s) errors plus the persistence baseline on the test windows.
    """
    pid, _site = client_identity(context.node_config)
    label = client_label(context.node_config)
    if not is_selected(context.node_config, context.run_config):
        return _skip_reply(msg, pid, keep_arrays=False, context=context)

    configs = build_model_configs(context.run_config)

    model = Net(configs=configs)
    state = msg.content["arrays"].to_torch_state_dict()
    if len(state) == 0:
        logging.error("Client received EMPTY weights for evaluation. Skipping load_state_dict.")
    else:
        model.load_state_dict(state, strict=False)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model.to(device)

    bs = context.run_config.get("batch-size", 32)
    dataset_name = context.run_config.get("dataset-name", "VNMET")
    data_file = client_data_file(context.node_config, context.run_config)
    save_predictions = bool(context.run_config.get("save-predictions", True))
    solar = solar_options(context.run_config)
    if solar is not None:
        return _evaluate_solar(msg, model, device, pid, bs, configs, dataset_name, data_file, solar, context)
    config_record = msg.content.get("config", None)
    if config_record is not None:
        if hasattr(config_record, "data"):
            current_round = config_record.data.get("server_round", 1)
        else:
            # Some ConfigRecord instances behave like dicts without .data
            current_round = config_record.get("server_round", 1)
    else:
        current_round = 1

    # Get experiment directory from environment variable
    exp_dir = os.environ.get("FLOWER_EXP_DIR", ".")

    # Validation evaluation
    valloader = load_client_val(pid, bs=bs, cfg=configs, dataset_name=dataset_name, data_file=data_file)
    logging.info(f"[CLIENT {pid}] Evaluating on {len(valloader.dataset)} validation samples")

    val_start_time = time.time()
    val_loss, val_mae, val_rmse, val_preds, val_trues = test_fn(model, valloader, device=device, return_predictions=True)
    val_duration = time.time() - val_start_time

    logging.info(f"[CLIENT {pid}] Validation complete. ValLoss={val_loss:.6f}, MAE={val_mae:.6f}, RMSE={val_rmse:.6f}, Duration={val_duration:.2f}s")

    if save_predictions:
        _save_predictions_to_csv(val_preds, val_trues, exp_dir, label, current_round, "val", configs.pred_len)

    # Test evaluation
    testloader = load_client_test(pid, bs=bs, cfg=configs, dataset_name=dataset_name, data_file=data_file)
    logging.info(f"[CLIENT {pid}] Evaluating on {len(testloader.dataset)} test samples")

    test_start_time = time.time()
    test_loss, test_mae, test_rmse, test_preds, test_trues = test_fn(model, testloader, device=device, return_predictions=True)
    test_duration = time.time() - test_start_time

    logging.info(f"[CLIENT {pid}] Test complete. TestLoss={test_loss:.6f}, MAE={test_mae:.6f}, RMSE={test_rmse:.6f}, Duration={test_duration:.2f}s")

    if save_predictions:
        _save_predictions_to_csv(test_preds, test_trues, exp_dir, label, current_round, "test", configs.pred_len)

    # Real units (plan T2.3): the target is scaled alone (features='S'), so errors scale
    # by the standard deviation of this site's train split, and values invert linearly.
    scaler = testloader.dataset.scaler
    std, mean = float(scaler.scale_[-1]), float(scaler.mean_[-1])
    persist_mae, persist_rmse = persistence_errors(testloader, configs.pred_len)
    test_mean_real = float(np.mean(test_trues) * std + mean) if test_trues.size else float("nan")

    # Save scalar metrics
    eval_metrics = {
        "client_id": pid,
        "round": current_round,
        "val_loss": float(val_loss),
        "val_mae": float(val_mae),
        "val_rmse": float(val_rmse),
        "val_duration": float(val_duration),
        "test_loss": float(test_loss),
        "test_mae": float(test_mae),
        "test_rmse": float(test_rmse),
        "test_duration": float(test_duration)
    }
    _save_eval_metrics(eval_metrics, exp_dir, label)

    num_examples = len(valloader.dataset) + len(testloader.dataset)
    metrics = MetricRecord({
        "num-examples": num_examples,
        "partition-id": pid,
        "val_loss": float(val_loss),
        "val_mae": float(val_mae),
        "val_rmse": float(val_rmse),
        "val_duration_sec": float(val_duration),
        "test_loss": float(test_loss),
        "test_mae": float(test_mae),
        "test_rmse": float(test_rmse),
        "test_duration_sec": float(test_duration),
        "val_mae_real": float(val_mae * std),
        "val_rmse_real": float(val_rmse * std),
        "test_mae_real": float(test_mae * std),
        "test_rmse_real": float(test_rmse * std),
        "test_mean_real": test_mean_real,
        "persistence_mae_real": float(persist_mae * std),
        "persistence_rmse_real": float(persist_rmse * std),
        "num-val-examples": len(valloader.dataset),
        "num-test-examples": len(testloader.dataset),
    })
    content = RecordDict({"metrics": metrics, "client": _who(context)})
    return Message(content=content, reply_to=msg)


def _evaluate_solar(msg, model, device, pid, bs, configs, dataset_name, data_file, solar, context):
    """
    Solar evaluation: errors in W/m2 of GHI (forecast k* x clear-sky GHI, or GHI directly),
    for daylight hours (main numbers) and all hours, plus three baselines on the same windows.
    The generic *_real keys carry the daylight numbers and smart persistence as the reference,
    so the run page and result.json read them like wind's.
    """
    masked = bool(solar["daylight_mask"])
    out = {}
    sizes = {}
    for split, loader_fn in (("val", load_client_val), ("test", load_client_test)):
        loader = loader_fn(pid, bs=bs, cfg=configs, dataset_name=dataset_name, data_file=data_file, solar=solar)
        start = time.time()
        loss, mae, rmse, preds, _trues, aux = test_fn(model, loader, device=device, return_predictions=True,
                                                     masked_loss=masked, return_aux=True)
        ds = loader.dataset
        std, mean = float(ds.scaler.scale_[-1]), float(ds.scaler.mean_[-1])
        ghi = evaluate_ghi(preds, aux, mean, std, solar["target_kind"], solar["kstar_max"], ds.kstar_climatology)
        out[split] = (loss, mae, rmse, time.time() - start, ghi)
        sizes[split] = len(ds)
        logging.info(f"[CLIENT {pid}] Solar {split}: daylight MAE={ghi['model']['mae']:.1f} W/m2, "
                     f"smart persistence MAE={ghi['smart_persistence']['mae']:.1f} W/m2")

    v_loss, v_mae, v_rmse, v_dur, v = out["val"]
    t_loss, t_mae, t_rmse, t_dur, t = out["test"]
    metrics = MetricRecord({
        "num-examples": sizes["val"] + sizes["test"],
        "partition-id": pid,
        "val_loss": float(v_loss), "val_mae": float(v_mae), "val_rmse": float(v_rmse), "val_duration_sec": float(v_dur),
        "test_loss": float(t_loss), "test_mae": float(t_mae), "test_rmse": float(t_rmse), "test_duration_sec": float(t_dur),
        "val_mae_real": v["model"]["mae"], "val_rmse_real": v["model"]["rmse"],
        "test_mae_real": t["model"]["mae"], "test_rmse_real": t["model"]["rmse"], "test_mbe_real": t["model"]["mbe"],
        "test_mae_all_real": t["model"]["mae_all"], "test_rmse_all_real": t["model"]["rmse_all"],
        "test_mean_real": t["mean_daylight_ghi"],
        "persistence_mae_real": t["smart_persistence"]["mae"], "persistence_rmse_real": t["smart_persistence"]["rmse"],
        "plain_persistence_mae_real": t["persistence"]["mae"], "plain_persistence_rmse_real": t["persistence"]["rmse"],
        "climatology_mae_real": t["climatology"]["mae"], "climatology_rmse_real": t["climatology"]["rmse"],
        "num-val-examples": sizes["val"],
        "num-test-examples": sizes["test"],
    })
    return Message(content=RecordDict({"metrics": metrics, "client": _who(context)}), reply_to=msg)


def _save_predictions_to_csv(preds, trues, exp_dir, client_id, round_num, split_name, pred_len):
    """
    Save predictions and true values to CSV file.

    Args:
        preds: numpy array of predictions [num_samples, pred_len, 1]
        trues: numpy array of true values [num_samples, pred_len, 1]
        exp_dir: experiment directory path
        client_id: client partition ID
        round_num: current federated learning round
        split_name: 'val' or 'test'
        pred_len: prediction length
    """
    if preds.size == 0:
        logging.warning(f"[CLIENT {client_id}] No predictions to save for {split_name} split")
        return

    # Reshape predictions and trues to 2D: [num_samples, pred_len]
    preds_2d = preds.reshape(-1, pred_len)
    trues_2d = trues.reshape(-1, pred_len)

    # Create DataFrame with columns for each timestep
    data = {}
    for t in range(pred_len):
        data[f"pred_t{t}"] = preds_2d[:, t]
        data[f"true_t{t}"] = trues_2d[:, t]

    # Add metadata columns
    data["sample_idx"] = np.arange(len(preds_2d))
    data["client_id"] = client_id
    data["round"] = round_num
    data["split"] = split_name

    # Reorder columns: metadata first, then predictions and trues
    metadata_cols = ["sample_idx", "client_id", "round", "split"]
    pred_true_cols = [f"pred_t{t}" for t in range(pred_len)] + [f"true_t{t}" for t in range(pred_len)]
    df = pd.DataFrame(data)
    df = df[metadata_cols + pred_true_cols]

    # Save to CSV
    predictions_dir = os.path.join(exp_dir, "predictions")
    os.makedirs(predictions_dir, exist_ok=True)
    csv_path = os.path.join(predictions_dir, f"client{client_id}_round{round_num}_{split_name}.csv")
    df.to_csv(csv_path, index=False)
    logging.info(f"[CLIENT {client_id}] Saved {len(df)} {split_name} predictions to {csv_path}")


def _save_metrics_history(history, exp_dir, client_id, round_num):
    """
    Save training history metrics to CSV.
    """
    if not history:
        return

    # Convert to DataFrame
    df = pd.DataFrame(history)
    df["client_id"] = client_id
    df["round"] = round_num
    
    # Reorder
    cols = ["client_id", "round"] + [c for c in df.columns if c not in ["client_id", "round"]]
    df = df[cols]

    metrics_dir = os.path.join(exp_dir, "metrics")
    os.makedirs(metrics_dir, exist_ok=True)
    csv_path = os.path.join(metrics_dir, f"client{client_id}_train_history.csv")
    
    # Append if exists, else write header
    mode = 'a' if os.path.exists(csv_path) else 'w'
    header = not os.path.exists(csv_path)
    df.to_csv(csv_path, mode=mode, header=header, index=False)
    logging.info(f"[CLIENT {client_id}] Saved training history to {csv_path}")


def _save_eval_metrics(metrics_dict, exp_dir, client_id):
    """
    Save evaluation metrics to CSV.
    """
    df = pd.DataFrame([metrics_dict])
    metrics_dir = os.path.join(exp_dir, "metrics")
    os.makedirs(metrics_dir, exist_ok=True)
    csv_path = os.path.join(metrics_dir, f"client{client_id}_eval_metrics.csv")
    
    mode = 'a' if os.path.exists(csv_path) else 'w'
    header = not os.path.exists(csv_path)
    df.to_csv(csv_path, mode=mode, header=header, index=False)
    logging.info(f"[CLIENT {client_id}] Saved eval metrics to {csv_path}")
