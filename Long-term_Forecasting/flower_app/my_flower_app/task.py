import os
import sys
import importlib.util
from types import SimpleNamespace

import torch
from torch.utils.data import Dataset, DataLoader, Subset, ConcatDataset
from my_flower_app.dataloader import Dataset_Custom
import torch.nn as nn
from torch.utils.data import random_split

import pandas as pd
import numpy as np

import logging

logging.basicConfig(level=logging.INFO, format= '%(asctime)s - %(levelname)s - %(message)s')

# Dataset registry for client and centralized loading
DATASET_REGISTRY = {
    "VNMET": {
        "folder": "datasets/VNMET",
        "files": ["001.csv", "002.csv", "003.csv", "004.csv", "005.csv"],
        "target": "Vavg80 [m/s]",
        "num_clients": 5,
        "client_names": {
            0: "Station_001",
            1: "Station_002",
            2: "Station_003",
            3: "Station_004",
            4: "Station_005",
        },
    },
    "KZMET": {
        "folder": "datasets/custom",
        "files": ["nasa_almaty.csv", "nasa_zhezkazgan.csv", "nasa_aktau.csv", "nasa_taraz.csv", "nasa_aktobe.csv"],
        "target": "WS50M",
        "num_clients": 5,
        "client_names": {
            0: "Almaty",
            1: "Zhezkazgan",
            2: "Aktau",
            3: "Taraz",
            4: "Aktobe",
        },
    },
    "GREECE": {
        "folder": "datasets/greece",
        "files": ["WT01.csv", "WT02.csv", "WT03.csv", "WT04.csv", "WT05.csv",
                  "WT06.csv", "WT07.csv", "WT08.csv", "WT09.csv", "WT10.csv"],
        "target": "Ambient WindSpeed Avg. [m/s]",
        "num_clients": 10,
        "client_names": {
            0: "WT01", 1: "WT02", 2: "WT03", 3: "WT04", 4: "WT05",
            5: "WT06", 6: "WT07", 7: "WT08", 8: "WT09", 9: "WT10",
        },
    },
    "CAPITALS": {
        "folder": "datasets/capitals-nasa",
        "files": ["astana_nasa.csv", "canberra_nasa.csv", "london_nasa.csv",
                  "paris_nasa.csv", "washington_nasa.csv"],
        "target": "WS50M",
        "num_clients": 5,
        "client_names": {
            0: "Astana", 1: "Canberra", 2: "London", 3: "Paris", 4: "Washington",
        },
    },
    "MIXED5": {
        "folder": "datasets/mixed5",
        "files": ["kz_astana.csv", "kz_almaty.csv", "kz_aktau.csv",
                  "vn_station001.csv", "gr_wt01.csv"],
        "target": "wind_speed",
        "num_clients": 5,
        "client_names": {
            0: "KZ_Astana", 1: "KZ_Almaty", 2: "KZ_Aktau",
            3: "VN_Station001", 4: "GR_WT01",
        },
    },
}


def get_dataset_config(dataset_name: str) -> dict:
    name = dataset_name.upper()
    if name not in DATASET_REGISTRY:
        raise ValueError(
            f"Unknown dataset '{dataset_name}'. Available: {list(DATASET_REGISTRY.keys())}"
        )
    return DATASET_REGISTRY[name]

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
# Repo root is two levels above project_root (Long-term_Forecasting -> federated_learning -> repo)
repo_root = os.path.abspath(os.path.join(project_root, "..", ".."))
baselines_root = os.path.join(repo_root, "BASELINES")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if baselines_root not in sys.path:
    sys.path.insert(0, baselines_root)
if baselines_root not in sys.path:
    sys.path.insert(0, baselines_root)

# ---------------------------------------------------------------------------
# Model registry:
#   model_name -> (module_filename, class_name, backbone_flag, base_dir, model_family)
#   backbone_flag is the configs attribute that gates the LLM backbone
#   base_dir: "llm" (project_root/models) or "baselines" (baselines_root/models)
# ---------------------------------------------------------------------------
MODEL_REGISTRY = {
    "gpt4ts_nonlinear": ("GPT4TS", "GPT4TS_Nonlinear", "is_gpt",   "llm",      "llm"),
    "gpt4ts_nonlinear_attnres": ("GPT4TS", "GPT4TS_Nonlinear_AttnRes", "is_gpt", "llm", "llm"),
    "gpt4ts_linear":    ("GPT4TS", "GPT4TS_Linear",    "is_gpt",   "llm",      "llm"),
    "bart_nonlinear":   ("BART",   "BART_Nonlinear",   "is_bart",  "llm",      "llm"),
    "bart_linear":      ("BART",   "BART_Linear",      "is_bart",  "llm",      "llm"),
    "bert_nonlinear":   ("BERT",   "BERT_Nonlinear",   "is_bert",  "llm",      "llm"),
    "bert_linear":      ("BERT",   "BERT_Linear",      "is_bert",  "llm",      "llm"),
    "llama_nonlinear":  ("LLAMA",  "Llama_Nonlinear",  "is_llama", "llm",      "llm"),
    "llama_linear":     ("LLAMA",  "Llama_Linear",     "is_llama", "llm",      "llm"),
    "opt_nonlinear":    ("OPT",    "Opt_Nonlinear",    "is_opt",   "llm",      "llm"),
    "opt_linear":       ("OPT",    "Opt_Linear",       "is_opt",   "llm",      "llm"),
    "gemma_nonlinear":  ("GEMMA",  "Gemma_Nonlinear",  "is_gemma", "llm",      "llm"),
    "gemma_linear":     ("GEMMA",  "Gemma_Linear",     "is_gemma", "llm",      "llm"),
    "qwen_nonlinear":   ("QWEN",   "Qwen_Nonlinear",   "is_qwen",  "llm",      "llm"),
    "qwen_linear":      ("QWEN",   "Qwen_Linear",      "is_qwen",  "llm",      "llm"),
    "informer":         ("Informer", "Model",         None,       "baselines","informer"),
    "patchtst":         ("PatchTST", "Model",         None,       "baselines","patchtst"),
}


def _load_model_class(model_name: str):
    if model_name not in MODEL_REGISTRY:
        raise ValueError(
            f"Unknown model '{model_name}'. Available: {list(MODEL_REGISTRY.keys())}"
        )
    module_filename, class_name, _, base_dir, _ = MODEL_REGISTRY[model_name]
    if base_dir == "baselines":
        model_root = os.path.join(baselines_root, "models")
        if baselines_root not in sys.path:
            sys.path.insert(0, baselines_root)
        # Ensure baseline "utils" wins over other utils modules
        existing_utils = sys.modules.get("utils")
        if existing_utils is not None:
            utils_file = getattr(existing_utils, "__file__", "")
            if utils_file and not utils_file.startswith(baselines_root):
                sys.modules.pop("utils", None)
                sys.modules.pop("utils.masking", None)
    else:
        model_root = os.path.join(project_root, "models")
    model_path = os.path.join(model_root, f"{module_filename}.py")

    spec = importlib.util.spec_from_file_location(module_filename, model_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)

def get_default_configs(
    pred_len,
    model="gpt4ts_nonlinear",
    seq_len=336,
    patch_size=4,
    stride=1,
    d_model=768,
    hidden_size=16,
    kernel_size=3,
    llm_layers=4,
    lora_r=8,
    lora_alpha=16,
    lora_dropout=0.15,
    dropout=0.15,
    is_pretrained=True,
    # baseline params
    label_len=48,
    enc_in=1,
    dec_in=1,
    c_out=1,
    embed_type=0,
    embed="timeF",
    freq="h",
    factor=1,
    n_heads=4,
    e_layers=2,
    d_layers=1,
    d_ff=512,
    distil=True,
    activation="gelu",
    output_attention=False,
    fc_dropout=0.05,
    head_dropout=0.0,
    patch_len=16,
    padding_patch="end",
    revin=1,
    affine=0,
    subtract_last=0,
    decomposition=0,
    individual=0,
    peft_method="lora",  # Fine-tuning strategy: "lora", "loha", "adalora", "pft", "fft"
    adalora_total_step=None,  # Total steps for AdaLoRA rank pruning schedule (None = PEFT default)
):
    """
    Get model configurations.

    Args:
        pred_len: Prediction length (forecast horizon). REQUIRED - must be specified.
        model: Which model to use.
        peft_method: Fine-tuning strategy for the LLM backbone.
            - "lora": LoRA (Low-Rank Adaptation) — default
            - "loha": LoHA (Low-Rank Hadamard Adaptation)
            - "adalora": AdaLoRA (Adaptive LoRA with rank allocation)
            - "pft": Partial Fine-Tuning (freeze backbone, train LayerNorm + embeddings only)
            - "fft": Full Fine-Tuning (all parameters trainable)
        ... other parameters are optional and have defaults matching the baseline.
    """
    if model not in MODEL_REGISTRY:
        raise ValueError(
            f"Unknown model '{model}'. Available: {list(MODEL_REGISTRY.keys())}"
        )

    # Determine which backbone flag to enable based on the selected model
    _, _, backbone_flag, _, model_family = MODEL_REGISTRY[model]
    is_llm = model_family == "llm"

    # Override d_model to match LLM hidden_size for models that differ from default 768
    _d_model_override = {
        "is_opt": 512,     # facebook/opt-350m word_embed_proj_dim=512 (inputs_embeds dim)
        "is_qwen": 1024,   # Qwen/Qwen3-0.6B hidden_size=1024
        "is_gemma": 1536,  # google/gemma-3-270m hidden_size=1536
    }
    if backbone_flag in _d_model_override:
        d_model = _d_model_override[backbone_flag]

    return SimpleNamespace(
        model=model,
        model_family=model_family,
        is_gpt=(backbone_flag == "is_gpt"),
        is_bart=(backbone_flag == "is_bart"),
        is_bert=(backbone_flag == "is_bert"),
        is_llama=(backbone_flag == "is_llama"),
        is_opt=(backbone_flag == "is_opt"),
        is_gemma=(backbone_flag == "is_gemma"),
        is_qwen=(backbone_flag == "is_qwen"),
        pretrain=is_pretrained,
        freeze=(peft_method != "fft"),  # FFT unfreezes all; others freeze backbone
        peft_method=(peft_method if is_llm else "pft"),
        use_lora=(peft_method in ("lora", "loha", "adalora") if is_llm else False),
        # data/patching
        seq_len=seq_len,
        label_len=label_len,
        pred_len=pred_len,
        patch_size=patch_size,
        stride=stride,
        d_model=d_model,
        hidden_size=hidden_size,
        kernel_size=kernel_size,
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
        llm_layers=llm_layers,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        lora_target_modules=["c_attn", "c_fc", "c_proj"],
        dropout=dropout,
        adalora_total_step=adalora_total_step,
    )


class Net(nn.Module):
    """
    A thin wrapper so instantiating Net() works in your Flower server/client code.
    The wrapper holds any model from MODEL_REGISTRY and forwards calls:
      - forward(x): expects x.shape == [B, seq_len, 1]
      returns predictions shape [B, pred_len, 1]
    """

    def __init__(self, device=None, configs=None):
        super(Net, self).__init__()
        if configs is None:
            raise ValueError("configs must be provided to Net(). Use get_default_configs(pred_len=1X) to create configs.")
        if device is None:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        model_name = getattr(configs, "model", "gpt4ts_nonlinear")
        logging.info(f"Initializing Net wrapper: model={model_name}, device={device}")
        self.device = device
        self.configs = configs

        model_class = _load_model_class(model_name)
        model_family = getattr(configs, "model_family", "llm")
        if model_family == "llm":
            self.model = model_class(configs, device)
        else:
            self.model = model_class(configs)
        self.to(device)

    def forward(self, x, x_mark=None, y=None, y_mark=None):
        """
        x: tensor [B, seq_len, 1]
        GPT4TS expects shape [B, L, M] where M is number of features (here 1).
        The underlying model returns [B, pred_len, M]
        """
        # ensure on device and float
        x = x.to(self.device).float()
        model_family = getattr(self.configs, "model_family", "llm")
        if model_family == "llm":
            return self.model(x, itr=0)
        if model_family == "informer":
            if x_mark is None or y is None or y_mark is None:
                raise ValueError("Informer requires x_mark, y, and y_mark inputs.")
            x_mark = x_mark.to(self.device).float()
            y = y.to(self.device).float()
            y_mark = y_mark.to(self.device).float()

            pred_len = self.configs.pred_len
            label_len = self.configs.label_len
            dec_inp = torch.zeros_like(y[:, -pred_len:, :]).float()
            dec_inp = torch.cat([y[:, :label_len, :], dec_inp], dim=1).float().to(self.device)

            outputs = self.model(x, x_mark, dec_inp, y_mark)
            if getattr(self.configs, "output_attention", False):
                outputs = outputs[0]
            return outputs
        return self.model(x)


def trainable_state_dict(model):
    """Return state dict containing only parameters with requires_grad=True.

    When PEFT adapters are active, this returns only adapter weights (+
    in_layer/out_layer), reducing the payload transmitted in federated rounds
    from the full backbone size to just the trainable parameters.
    When no parameters are frozen (e.g. FFT), this returns the full state dict.
    """
    full = model.state_dict()
    trainable_keys = {n for n, p in model.named_parameters() if p.requires_grad}
    filtered = {k: v for k, v in full.items() if k in trainable_keys}
    # Fallback: if nothing is trainable (shouldn't happen), return full state
    if not filtered:
        return full
    return filtered


def train(net, trainloader, epochs, lr, device, valloader=None, weight_decay=0.01, global_weights=None, proximal_mu=None, c_local=None, c_global=None):
    """
    Train loop expects `net` to be an instance of Net (wrapper above).
    trainloader yields dicts {"x": [B, seq_len, 1], "y": [B, pred_len, 1]}
    Optionally evaluates on valloader after each epoch.

    Args:
        net: model to train
        trainloader: training data loader
        epochs: number of local training epochs
        lr: learning rate
        device: torch device
        valloader: optional validation data loader
        weight_decay: L2 regularization coefficient for AdamW optimizer (default: 0.01)
        global_weights: global model weights for FedProx proximal term (optional)
        proximal_mu: FedProx proximal term coefficient (optional, e.g., 0.01)
        c_local: local control variate for SCAFFOLD
        c_global: global control variate for SCAFFOLD
    """
    net.to(device)
    trainable_params = [p for p in net.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=lr, weight_decay=weight_decay)
    criterion = nn.MSELoss()
    total_loss = 0.0
    count = 0
    history = []

    # SCAFFOLD setup
    use_scaffold = (c_local is not None and c_global is not None)
    if use_scaffold:
        logging.info("SCAFFOLD enabled")
        c_local_device = {k: v.to(device) for k, v in c_local.items()}
        c_global_device = {k: v.to(device) for k, v in c_global.items()}
        # Store initial weights to compute c_i update: c_i+ = c_i - c + 1/(K*eta)(x - y_i)
        w_global_initial = {k: p.clone().detach() for k, p in net.named_parameters() if p.requires_grad}
    
    # Check if FedProx is enabled
    use_fedprox = (proximal_mu is not None and global_weights is not None and proximal_mu > 0)
    if use_fedprox:
        logging.info(f"FedProx enabled: proximal_mu={proximal_mu}")
        # CRITICAL FIX: Move global weights to device ONCE before training loop
        # Only move trainable parameters to save memory
        global_weights_device = {}
        for name, param in net.named_parameters():
            if param.requires_grad and name in global_weights:
                global_weights_device[name] = global_weights[name].to(device)
        logging.info(f"FedProx: Moved {len(global_weights_device)} global weight tensors to {device}")
    else:
        global_weights_device = None

    total_steps = epochs * len(trainloader)

    for epoch in range(epochs):
        epoch_mse_loss = 0.0  # Track MSE separately
        epoch_prox_loss = 0.0  # Track proximal term separately
        epoch_total_loss = 0.0  # Track total loss (MSE + proximal)
        epoch_count = 0

        # Training phase
        net.train()
        for batch in trainloader:
            x_mark = None
            y_mark = None
            if isinstance(batch, dict):
                x = batch["x"].to(device).float()
                y_true = batch["y"].to(device).float()
                x_mark = batch.get("x_mark", None)
                y_mark = batch.get("y_mark", None)
            else:
                if len(batch) >= 4:
                    x, y_true, x_mark, y_mark = batch[:4]
                else:
                    x, y_true = batch[:2]
                x = x.to(device).float()
                y_true = y_true.to(device).float()
                if x_mark is not None:
                    x_mark = x_mark.to(device).float()
                if y_mark is not None:
                    y_mark = y_mark.to(device).float()

            optimizer.zero_grad()
            y_pred = net(x, x_mark=x_mark, y=y_true, y_mark=y_mark)

            pred_len = net.configs.pred_len
            if y_true.size(1) > pred_len:
                y_true = y_true[:, -pred_len:, :]

            # Base loss (MSE)
            mse_loss = criterion(y_pred, y_true)
            total_batch_loss = mse_loss

            # CRITICAL: Add FedProx proximal term: (mu/2) * ||w - w_global||^2
            # CRITICAL FIX: Use pre-moved global_weights_device (no .to() in loop)
            if use_fedprox:
                proximal_term = 0.0
                for name, param in net.named_parameters():
                    if name in global_weights_device:
                        proximal_term += torch.sum((param - global_weights_device[name]) ** 2)
                proximal_term = (proximal_mu / 2.0) * proximal_term
                total_batch_loss = mse_loss + proximal_term
                epoch_prox_loss += proximal_term.item()

            total_batch_loss.backward()

            # SCAFFOLD: Correct gradient before step
            if use_scaffold:
                for name, p in net.named_parameters():
                    if p.grad is not None and name in c_local_device and name in c_global_device:
                        # Correction: grad = grad - c_i + c
                        p.grad.data.add_(c_global_device[name] - c_local_device[name])

            optimizer.step()

            # CRITICAL FIX: Track MSE and total loss separately
            epoch_mse_loss += mse_loss.item()
            epoch_total_loss += total_batch_loss.item()
            total_loss += total_batch_loss.item()  # For backward compat with return value
            count += 1
            epoch_count += 1

        # CRITICAL FIX: Separate MSE from total loss for fair comparison with val/test
        avg_epoch_mse = epoch_mse_loss / max(1, epoch_count)
        avg_epoch_total = epoch_total_loss / max(1, epoch_count)

        # Validation phase (if valloader provided)
        # IMPORTANT: Use MSE as primary "train_loss" for fair comparison with val/test
        metrics = {
            "epoch": epoch + 1,
            "train_loss": avg_epoch_mse,  # MSE only (comparable to val/test)
            "train_total_loss": avg_epoch_total  # MSE + proximal (actual optimized loss)
        }

        # Add proximal term info if FedProx is used
        if use_fedprox:
            avg_prox_loss = epoch_prox_loss / max(1, epoch_count)
            metrics["proximal_loss"] = avg_prox_loss

        if valloader is not None:
            # Reusing the existing test function for validation
            # Note: test() sets net.eval(), so we ensure to set net.train() back at start of loop
            val_loss, val_mae, val_rmse = test(net, valloader, device, return_predictions=False)
            metrics["val_loss"] = val_loss
            metrics["val_mae"] = val_mae
            metrics["val_rmse"] = val_rmse
            if use_fedprox:
                logging.info(f"Epoch {epoch+1}/{epochs}: TrainMSE={avg_epoch_mse:.6f}, TrainTotal={avg_epoch_total:.6f}, ProxLoss={avg_prox_loss:.6f}, ValLoss={val_loss:.6f}")
            else:
                logging.info(f"Epoch {epoch+1}/{epochs}: TrainMSE={avg_epoch_mse:.6f}, ValLoss={val_loss:.6f}")
        else:
            if use_fedprox:
                logging.info(f"Epoch {epoch+1}/{epochs}: TrainMSE={avg_epoch_mse:.6f}, TrainTotal={avg_epoch_total:.6f}, ProxLoss={avg_prox_loss:.6f}")
            else:
                logging.info(f"Epoch {epoch+1}/{epochs}: TrainMSE={avg_epoch_mse:.6f}")

        history.append(metrics)

    new_c_local = None
    if use_scaffold:
        # c_i_new = c_i - c_global + (1/(K*η)) * (w_global - w_local)
        new_c_local = {}
        # η = lr (using base lr as η for SCAFFOLD update is standard if η is fixed)
        scale = 1.0 / (total_steps * lr) if total_steps * lr > 0 else 0.0

        for name, p in net.named_parameters():
            if p.requires_grad:
                diff = w_global_initial[name].to(device) - p.data
                new_c_local[name] = (c_local_device[name] - c_global_device[name] + scale * diff).cpu()

    avg_mse_loss = sum(epoch["train_loss"] for epoch in history) / max(1, len(history))
    logging.info(f"Training completed over {epochs} epochs. Average MSE: {avg_mse_loss:.6f}")
    return avg_mse_loss, history, new_c_local

def test(net, testloader, device, return_predictions=False):
    """
    Evaluate model on validation/test set.
    Returns (avg_loss, mae, rmse) or (avg_loss, mae, rmse, predictions, trues) if return_predictions=True
    """
    net.to(device)
    net.eval()
    criterion = nn.MSELoss()

    total_loss = 0.0
    count = 0
    all_preds = []
    all_trues = []

    with torch.no_grad():
        for batch in testloader:
            x_mark = None
            y_mark = None
            if isinstance(batch, dict):
                x = batch["x"].to(device).float()
                y_true = batch["y"].to(device).float()
                x_mark = batch.get("x_mark", None)
                y_mark = batch.get("y_mark", None)
            else:
                if len(batch) >= 4:
                    x, y_true, x_mark, y_mark = batch[:4]
                else:
                    x, y_true = batch[:2]
                x = x.to(device).float()
                y_true = y_true.to(device).float()
                if x_mark is not None:
                    x_mark = x_mark.to(device).float()
                if y_mark is not None:
                    y_mark = y_mark.to(device).float()

            y_pred = net(x, x_mark=x_mark, y=y_true, y_mark=y_mark)
            pred_len = net.configs.pred_len
            if y_true.size(1) > pred_len:
                y_true = y_true[:, -pred_len:, :]
            loss = criterion(y_pred, y_true)

            # if count < 5:  # print only first 5 batches to avoid spam
            #     logging.info(f"[TEST] y_pred: {y_pred[0].detach().cpu().numpy().flatten()}")
            #     logging.info(f"[TEST] y_true: {y_true[0].detach().cpu().numpy().flatten()}")

            total_loss += loss.item()
            count += 1

            all_preds.append(y_pred.cpu().numpy())
            all_trues.append(y_true.cpu().numpy())

    avg_loss = total_loss / max(1, count)

    preds = np.concatenate(all_preds, axis=0) if all_preds else np.zeros((0,))
    trues = np.concatenate(all_trues, axis=0) if all_trues else np.zeros((0,))
    if preds.size:
        mae = float(np.mean(np.abs(preds - trues)))
        rmse = float(np.sqrt(np.mean((preds - trues) ** 2)))
    else:
        mae = float("nan")
        rmse = float("nan")

    if return_predictions:
        return avg_loss, mae, rmse, preds, trues
    return avg_loss, mae, rmse


def load_client_train(
    partition_id: int,
    num_partitions: int,
    bs: int = 32,
    cfg: SimpleNamespace = None,
    dataset_name: str = "VNMET",
):
    """
    Each client loads a different partition of the *training* data (70% of full dataset).
    cfg must be provided with pred_len specified.
    Uses dataset configuration from DATASET_REGISTRY.
    """
    if cfg is None:
        raise ValueError("cfg must be provided to load_client_train(). Use get_default_configs(pred_len=1X) to create cfg.")

    ds_cfg = get_dataset_config(dataset_name)
    root_path = os.path.join(project_root, ds_cfg["folder"])
    client_datasets = ds_cfg["files"]
    data_path = client_datasets[partition_id]
    label_len = getattr(cfg, "label_len", 48)
    seq_len, pred_len = cfg.seq_len, cfg.pred_len
    target = ds_cfg["target"]

    full_train = Dataset_Custom(
        root_path=root_path,
        flag='train',
        size=(seq_len, label_len, pred_len),
        data_path=data_path,
        target=target,
        scale=True,
        percent=100
    )

    logging.info(f"Client {partition_id}: Loaded {len(full_train.data_x)} raw CSV rows for training.")
    logging.info(f"Client {partition_id}: Total dataset size before partitioning: {len(full_train)}")
    logging.info(f"Client {partition_id}: Partition ID: {partition_id}, Num partitions: {num_partitions}")
    trainloader = DataLoader(full_train, batch_size=bs, shuffle=True, drop_last=False)
    return trainloader


def load_client_val(
    partition_id: int,
    bs: int = 32,
    cfg: SimpleNamespace = None,
    dataset_name: str = "VNMET",
):
    """
    Each client loads their local validation data (20% of their local dataset).
    cfg must be provided with pred_len specified.
    Uses dataset configuration from DATASET_REGISTRY.
    """
    if cfg is None:
        raise ValueError("cfg must be provided to load_client_val(). Use get_default_configs(pred_len=1X) to create cfg.")

    ds_cfg = get_dataset_config(dataset_name)
    root_path = os.path.join(project_root, ds_cfg["folder"])
    client_datasets = ds_cfg["files"]
    data_path = client_datasets[partition_id]
    label_len = getattr(cfg, "label_len", 48)
    seq_len, pred_len = cfg.seq_len, cfg.pred_len
    target = ds_cfg["target"]

    val_dataset = Dataset_Custom(
        root_path=root_path,
        flag='val',
        size=(seq_len, label_len, pred_len),
        data_path=data_path,
        target=target,
        scale=True
    )

    logging.info(f"Client {partition_id}: Loaded {len(val_dataset.data_x)} raw CSV rows for validation.")
    valloader = DataLoader(val_dataset, batch_size=bs, shuffle=False, drop_last=False)
    return valloader


def load_client_test(
    partition_id: int,
    bs: int = 32,
    cfg: SimpleNamespace = None,
    dataset_name: str = "VNMET",
):
    """
    Each client loads their local test data (10% of their local dataset).
    cfg must be provided with pred_len specified.
    Uses dataset configuration from DATASET_REGISTRY.
    """
    if cfg is None:
        raise ValueError("cfg must be provided to load_client_test(). Use get_default_configs(pred_len=1X) to create cfg.")

    ds_cfg = get_dataset_config(dataset_name)
    root_path = os.path.join(project_root, ds_cfg["folder"])
    client_datasets = ds_cfg["files"]
    data_path = client_datasets[partition_id]
    label_len = getattr(cfg, "label_len", 48)
    seq_len, pred_len = cfg.seq_len, cfg.pred_len
    target = ds_cfg["target"]

    test_dataset = Dataset_Custom(
        root_path=root_path,
        flag='test',
        size=(seq_len, label_len, pred_len),
        data_path=data_path,
        target=target,
        scale=True
    )

    logging.info(f"Client {partition_id}: Loaded {len(test_dataset.data_x)} raw CSV rows for testing.")
    testloader = DataLoader(test_dataset, batch_size=bs, shuffle=False, drop_last=False)
    return testloader


def _load_centralized(
    flag: str,
    bs: int,
    cfg: SimpleNamespace,
    shuffle: bool,
    dataset_name: str = "VNMET",
):
    """
    Load all configured datasets with the same per-dataset temporal split as federated,
    then concatenate. Each dataset's 70/10/20 boundary is computed independently,
    so the combined dataset is directly comparable to the federated setup.
    Uses dataset configuration from DATASET_REGISTRY.
    """
    if cfg is None:
        raise ValueError("cfg must be provided. Use get_default_configs(pred_len=...) to create cfg.")

    ds_cfg = get_dataset_config(dataset_name)
    root_path = os.path.join(project_root, ds_cfg["folder"])
    client_datasets = ds_cfg["files"]
    label_len = getattr(cfg, "label_len", 48)
    seq_len, pred_len = cfg.seq_len, cfg.pred_len
    target = ds_cfg["target"]

    datasets = []
    for i, data_path in enumerate(client_datasets):
        ds = Dataset_Custom(
            root_path=root_path,
            flag=flag,
            size=(seq_len, label_len, pred_len),
            data_path=data_path,
            target=target,
            scale=True,
            percent=100
        )
        logging.info(f"Centralized [{flag}] city {i} ({data_path}): {len(ds.data_x)} rows, {len(ds)} samples")
        datasets.append(ds)

    combined = ConcatDataset(datasets)
    logging.info(f"Centralized [{flag}] total: {len(combined)} samples across {len(datasets)} cities")
    return DataLoader(combined, batch_size=bs, shuffle=shuffle, drop_last=False)


def load_centralized_train(
    bs: int = 32, cfg: SimpleNamespace = None, dataset_name: str = "VNMET"
):
    return _load_centralized('train', bs, cfg, shuffle=True, dataset_name=dataset_name)


def load_centralized_val(
    bs: int = 32, cfg: SimpleNamespace = None, dataset_name: str = "VNMET"
):
    return _load_centralized('val', bs, cfg, shuffle=False, dataset_name=dataset_name)


def load_centralized_test(
    bs: int = 32, cfg: SimpleNamespace = None, dataset_name: str = "VNMET"
):
    return _load_centralized('test', bs, cfg, shuffle=False, dataset_name=dataset_name)

