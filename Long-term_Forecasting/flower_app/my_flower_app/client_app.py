
"""my-flower-app: A Flower / PyTorch client that only trains locally."""
import torch
import time
import os
import sys
import pandas as pd
import numpy as np
from flwr.app import ArrayRecord, Context, Message, MetricRecord, RecordDict
from flwr.clientapp import ClientApp

from my_flower_app.task import get_default_configs, Net, load_client_train, load_client_val, load_client_test, train as train_fn, test as test_fn, trainable_state_dict

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = ClientApp()

@app.train()
def train(msg: Message, context: Context):
    # Get model parameters from train config (passed from server)
    conf = msg.content["config"]
    configs = get_default_configs(
        pred_len=conf.get("pred_len", 120),
        model=conf.get("model", "gpt4ts_nonlinear"),
        seq_len=conf.get("seq_len", 336),
        patch_size=conf.get("patch_size", 4),
        stride=conf.get("stride", 1),
        d_model=conf.get("d_model", 768),
        hidden_size=conf.get("hidden_size", 16),
        kernel_size=conf.get("kernel_size", 3),
        llm_layers=conf.get("llm_layers", 4),
        peft_method=conf.get("peft_method", "lora"),
        lora_r=conf.get("lora_r", 8),
        lora_alpha=conf.get("lora_alpha", 16),
        lora_dropout=conf.get("lora_dropout", 0.15),
        dropout=conf.get("dropout", 0.15),
        adalora_total_step=conf.get("adalora_total_step", None),
        label_len=conf.get("label_len", 48),
        enc_in=conf.get("enc_in", 1),
        dec_in=conf.get("dec_in", 1),
        c_out=conf.get("c_out", 1),
        embed_type=conf.get("embed_type", 0),
        embed=conf.get("embed", "timeF"),
        freq=conf.get("freq", "h"),
        factor=conf.get("factor", 1),
        n_heads=conf.get("n_heads", 4),
        e_layers=conf.get("e_layers", 2),
        d_layers=conf.get("d_layers", 1),
        d_ff=conf.get("d_ff", 512),
        distil=conf.get("distil", True),
        activation=conf.get("activation", "gelu"),
        output_attention=conf.get("output_attention", False),
        fc_dropout=conf.get("fc_dropout", 0.05),
        head_dropout=conf.get("head_dropout", 0.0),
        patch_len=conf.get("patch_len", 16),
        padding_patch=conf.get("padding_patch", "end"),
        revin=conf.get("revin", 1),
        affine=conf.get("affine", 0),
        subtract_last=conf.get("subtract_last", 0),
        decomposition=conf.get("decomposition", 0),
        individual=conf.get("individual", 0),
        # Must use pretrained=True so the frozen backbone has real weights.
        # The server only transmits trainable params (adapters + projections);
        # loading with strict=False overlays them onto the pretrained backbone.
        is_pretrained=conf.get("is_pretrained", True),
    )

    model = Net(configs=configs)
    state = msg.content["arrays"].to_torch_state_dict()
    if len(state) == 0:
        logging.error("Client received EMPTY weights. Skipping load_state_dict.")
    else:
        model.load_state_dict(state, strict=False)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model.to(device)

    pid = context.node_config["partition-id"]
    npt = context.node_config["num-partitions"]
    bs  = context.run_config.get("batch-size", 32)
    dataset_name = context.run_config.get("dataset-name", "VNMET")
    trainloader = load_client_train(pid, npt, bs=bs, cfg=configs, dataset_name=dataset_name)
    
    # Get experiment directory from environment variable
    exp_dir = os.environ.get("FLOWER_EXP_DIR", ".")
    
    # Load validation set for tracking local overfitting
    valloader = load_client_val(pid, bs=bs, cfg=configs, dataset_name=dataset_name)

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
    )
    train_duration = time.time() - train_start_time

    logging.info(f"[CLIENT {pid}] Training complete. AvgTrainLoss={train_loss:.6f}, Duration={train_duration:.2f}s")
    
    # Save training history
    _save_metrics_history(history, exp_dir, pid, current_round)

    arrays = ArrayRecord(trainable_state_dict(model))
    metrics = MetricRecord({
        "train_loss": float(train_loss),
        "train_duration_sec": float(train_duration),
        "num-examples": len(trainloader.dataset),
    })
    
    content_dict = {"arrays": arrays, "metrics": metrics}
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
    Evaluates on both val (20%) and test (10%) splits.
    """
    # Get model parameters from run_config (for evaluation)
    conf = context.run_config
    configs = get_default_configs(
        pred_len=conf.get("pred-len", 120),
        model=conf.get("model", "gpt4ts_nonlinear"),
        seq_len=conf.get("seq-len", 336),
        patch_size=conf.get("patch-size", 4),
        stride=conf.get("stride", 1),
        d_model=conf.get("d-model", 768),
        hidden_size=conf.get("hidden-size", 16),
        kernel_size=conf.get("kernel-size", 3),
        llm_layers=conf.get("llm-layers", 4),
        peft_method=conf.get("peft-method", "lora"),
        lora_r=conf.get("lora-r", 8),
        lora_alpha=conf.get("lora-alpha", 16),
        lora_dropout=conf.get("lora-dropout", 0.15),
        dropout=conf.get("dropout", 0.15),
        label_len=conf.get("label-len", 48),
        enc_in=conf.get("enc-in", 1),
        dec_in=conf.get("dec-in", 1),
        c_out=conf.get("c-out", 1),
        embed_type=conf.get("embed-type", 0),
        embed=conf.get("embed", "timeF"),
        freq=conf.get("freq", "h"),
        factor=conf.get("factor", 1),
        n_heads=conf.get("n-heads", 4),
        e_layers=conf.get("e-layers", 2),
        d_layers=conf.get("d-layers", 1),
        d_ff=conf.get("d-ff", 512),
        distil=conf.get("distil", True),
        activation=conf.get("activation", "gelu"),
        output_attention=conf.get("output-attention", False),
        fc_dropout=conf.get("fc-dropout", 0.05),
        head_dropout=conf.get("head-dropout", 0.0),
        patch_len=conf.get("patch-len", 16),
        padding_patch=conf.get("padding-patch", "end"),
        revin=conf.get("revin", 1),
        affine=conf.get("affine", 0),
        subtract_last=conf.get("subtract-last", 0),
        decomposition=conf.get("decomposition", 0),
        individual=conf.get("individual", 0),
        is_pretrained=conf.get("is-pretrained", True),
    )

    model = Net(configs=configs)
    state = msg.content["arrays"].to_torch_state_dict()
    if len(state) == 0:
        logging.error("Client received EMPTY weights for evaluation. Skipping load_state_dict.")
    else:
        model.load_state_dict(state, strict=False)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model.to(device)

    pid = context.node_config["partition-id"]
    bs = context.run_config.get("batch-size", 32)
    dataset_name = context.run_config.get("dataset-name", "VNMET")
    config_record = msg.content.get("config", None)
    logging.info(
        "[CLIENT %s] Eval config type=%s, value=%s, has_data=%s",
        pid,
        type(config_record),
        config_record,
        hasattr(config_record, "data"),
    )
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

    # Validation evaluation (20% of data)
    valloader = load_client_val(pid, bs=bs, cfg=configs, dataset_name=dataset_name)
    logging.info(f"[CLIENT {pid}] Evaluating on {len(valloader.dataset)} validation samples")

    val_start_time = time.time()
    val_loss, val_mae, val_rmse, val_preds, val_trues = test_fn(model, valloader, device=device, return_predictions=True)
    val_duration = time.time() - val_start_time

    logging.info(f"[CLIENT {pid}] Validation complete. ValLoss={val_loss:.6f}, MAE={val_mae:.6f}, RMSE={val_rmse:.6f}, Duration={val_duration:.2f}s")

    # Save validation predictions to CSV
    _save_predictions_to_csv(val_preds, val_trues, exp_dir, pid, current_round, "val", configs.pred_len)

    # Test evaluation (10% of data)
    testloader = load_client_test(pid, bs=bs, cfg=configs, dataset_name=dataset_name)
    logging.info(f"[CLIENT {pid}] Evaluating on {len(testloader.dataset)} test samples")

    test_start_time = time.time()
    test_loss, test_mae, test_rmse, test_preds, test_trues = test_fn(model, testloader, device=device, return_predictions=True)
    test_duration = time.time() - test_start_time

    logging.info(f"[CLIENT {pid}] Test complete. TestLoss={test_loss:.6f}, MAE={test_mae:.6f}, RMSE={test_rmse:.6f}, Duration={test_duration:.2f}s")

    # Save test predictions to CSV
    _save_predictions_to_csv(test_preds, test_trues, exp_dir, pid, current_round, "test", configs.pred_len)

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
    _save_eval_metrics(eval_metrics, exp_dir, pid)

    num_examples = len(valloader.dataset) + len(testloader.dataset)
    metrics = MetricRecord({
        "num-examples": num_examples,
        "val_loss": float(val_loss),
        "val_mae": float(val_mae),
        "val_rmse": float(val_rmse),
        "val_duration_sec": float(val_duration),
        "test_loss": float(test_loss),
        "test_mae": float(test_mae),
        "test_rmse": float(test_rmse),
        "test_duration_sec": float(test_duration),
    })
    content = RecordDict({"metrics": metrics})
    return Message(content=content, reply_to=msg)


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
