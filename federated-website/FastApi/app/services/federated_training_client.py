"""
Federated Training Client - Bridge to the Flower federated simulation.

Runs `flwr run . local-simulation-{N}` with --run-config overrides,
reads training_summary.csv + predictions/ from the experiment directory,
and returns structured output for the frontend.
"""

import os
import time
import logging
import tempfile
import subprocess
import shutil

import numpy as np
import pandas as pd

from app.schemas import FederatedTrainingInput, FederatedTrainingOutput

logger = logging.getLogger(__name__)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

TRAINING_REPO_ROOT = os.environ["TRAINING_REPO_ROOT"]
TRAINING_PYTHON = os.environ["TRAINING_PYTHON"]

MODEL_NAME_MAP = {
    "GPT4TS":        "gpt4ts_nonlinear",
    "GPT4TS_LINEAR": "gpt4ts_linear",
    "LLAMA":         "llama_nonlinear",
    "LLAMA_LINEAR":  "llama_linear",
    "BERT":          "bert_nonlinear",
    "BERT_LINEAR":   "bert_linear",
    "BART":          "bart_nonlinear",
    "BART_LINEAR":   "bart_linear",
    "OPT":           "opt_nonlinear",
    "OPT_LINEAR":    "opt_linear",
    "GEMMA":         "gemma_nonlinear",
    "GEMMA_LINEAR":  "gemma_linear",
    "QWEN":          "qwen_nonlinear",
    "QWEN_LINEAR":   "qwen_linear",
}

ALGORITHM_MAP = {
    "FedAvg":   "fedavg",
    "FedProx":  "fedprox",
    "SCAFFOLD": "scaffold",
    "StatAvg":  "statavg",
    "FedPer":   "fedper",
    "FedLN":    "fedln",
}

# Supported num-clients federations defined in pyproject.toml
SUPPORTED_CLIENT_COUNTS = {1, 2, 3, 4, 5, 7, 10}


def run_federated_training(inp: FederatedTrainingInput) -> FederatedTrainingOutput:
    start = time.time()

    logger.info("=" * 70)
    logger.info("FEDERATED TRAINING REQUEST RECEIVED")
    logger.info("=" * 70)
    logger.info(f"  model_name:          {inp.model_name}")
    logger.info(f"  prediction_length:   {inp.prediction_length}")
    logger.info(f"  dropout_rate:        {inp.dropout_rate}")
    logger.info(f"  federated_algorithm: {inp.federated_algorithm}")
    logger.info(f"  num_clients:         {inp.num_clients}")
    logger.info(f"  rounds:              {inp.rounds}")
    logger.info(f"  learning_rate:       {inp.learning_rate}")
    logger.info(f"  batch_size:          {inp.batch_size}")
    logger.info(f"  seq_len:             {inp.seq_len}")
    logger.info(f"  csv_path:            {inp.csv_path}")
    logger.info("-" * 70)

    # ── STEP 1: Verify repo ───────────────────────────────────────────────────
    logger.info(f"[STEP 1] Verifying TRAINING_REPO_ROOT: {TRAINING_REPO_ROOT}")
    if not os.path.isdir(TRAINING_REPO_ROOT):
        raise RuntimeError(f"flower_app directory not found: {TRAINING_REPO_ROOT}")
    pyproject = os.path.join(TRAINING_REPO_ROOT, "pyproject.toml")
    if not os.path.isfile(pyproject):
        raise RuntimeError(f"pyproject.toml not found in {TRAINING_REPO_ROOT}")
    logger.info("  ✓ Repo verified")

    # ── STEP 2: Create experiment directory ──────────────────────────────────
    exp_base = os.environ["CENTRALIZED_WEB_DIR"]
    os.makedirs(exp_base, exist_ok=True)
    exp_dir = tempfile.mkdtemp(prefix="federated_web_", dir=exp_base)
    logger.info(f"[STEP 2] Experiment directory: {exp_dir}")

    # ── STEP 3: Prepare uploaded CSV ─────────────────────────────────────────
    dataset_dir = os.path.abspath(os.path.join(TRAINING_REPO_ROOT, "..", "datasets", "custom"))
    kzmet_files = [
        "nasa_almaty.csv", "nasa_zhezkazgan.csv", "nasa_aktau.csv",
        "nasa_taraz.csv", "nasa_aktobe.csv",
    ]
    backups = {}

    if inp.csv_path and os.path.isfile(inp.csv_path):
        with open(inp.csv_path, "r") as f:
            csv_content = f.read()

        if "-END HEADER-" not in csv_content:
            nasa_header = "-BEGIN HEADER-\nNASA/POWER Source - user upload\n-END HEADER-\n"
            csv_content = nasa_header + csv_content

        os.makedirs(dataset_dir, exist_ok=True)
        for fname in kzmet_files:
            orig = os.path.join(dataset_dir, fname)
            if os.path.exists(orig):
                bak = orig + ".bak"
                shutil.copy2(orig, bak)
                backups[orig] = bak
            with open(orig, "w") as f:
                f.write(csv_content)
        logger.info(f"[STEP 3] Prepared uploaded CSV into {dataset_dir} ({len(backups)} backups)")
    else:
        logger.info("[STEP 3] No csv_path — training on existing KZMET data")

    # ── STEP 4: Map model + algorithm names ───────────────────────────────────
    internal_model = MODEL_NAME_MAP.get(inp.model_name, inp.model_name.lower())
    internal_algo  = ALGORITHM_MAP.get(inp.federated_algorithm, inp.federated_algorithm.lower())
    logger.info(f"[STEP 4] Model:     {inp.model_name} -> {internal_model}")
    logger.info(f"         Algorithm: {inp.federated_algorithm} -> {internal_algo}")

    # ── STEP 5: Choose federation (num-supernodes must match pyproject.toml) ──
    n = inp.num_clients
    if n not in SUPPORTED_CLIENT_COUNTS:
        # Pick the nearest supported count
        n = min(SUPPORTED_CLIENT_COUNTS, key=lambda x: abs(x - n))
        logger.warning(f"  num_clients {inp.num_clients} not in supported set — using {n}")
    federation = f"local-simulation-{n}"
    logger.info(f"[STEP 5] Federation: {federation}")

    # ── STEP 6: Build --run-config override string ───────────────────────────
    local_epochs  = getattr(inp, "local_epochs", 1)
    llm_layers    = getattr(inp, "llm_layers", 4)
    proximal_mu   = getattr(inp, "proximal_mu", None)
    warmup_rounds = getattr(inp, "warmup_rounds", None)
    weight_decay  = getattr(inp, "weight_decay", None)
    run_config = (
        f'num-server-rounds={inp.rounds} '
        f'local-epochs={local_epochs} '
        f'lr={inp.learning_rate} '
        f'batch-size={inp.batch_size} '
        f'pred-len={inp.prediction_length} '
        f'seq-len={inp.seq_len} '
        f'llm-layers={llm_layers} '
        f'strategy="{internal_algo}" '
        f'model="{internal_model}" '
        f'dropout={inp.dropout_rate} '
        f'num-clients={n} '
        f'dataset-name="KZMET"'
    )
    if proximal_mu is not None:
        run_config += f' proximal-mu={proximal_mu}'
    if warmup_rounds is not None:
        run_config += f' warmup-rounds={warmup_rounds}'
    if weight_decay is not None:
        run_config += f' weight-decay={weight_decay}'
    logger.info(f"[STEP 6] run-config: {run_config}")

    # ── STEP 7: Build command ─────────────────────────────────────────────────
    # flwr run must be called from inside the flower_app directory

    env = os.environ.copy()
    env["FLOWER_EXP_DIR"] = exp_dir  # server_app.py reads this to know where to save results
    env["PYTHONPATH"] = TRAINING_REPO_ROOT + (
        os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else ""
    )

    # flwr executable: explicit override > auto-derive from TRAINING_PYTHON
    flwr_exe = os.environ.get(
        "FLWR_EXE",
        os.path.join(os.path.dirname(TRAINING_PYTHON), "Scripts", "flwr.exe"),
    )
    env["RAY_TMPDIR"] = os.path.join(tempfile.gettempdir(), "ray")
    os.makedirs(env["RAY_TMPDIR"], exist_ok=True)
    cmd = [flwr_exe, "run", ".", federation, "--run-config", run_config]

    logger.info("=" * 70)
    logger.info(f"[STEP 7] LAUNCHING flwr run in {TRAINING_REPO_ROOT} ...")
    logger.info("=" * 70)

    stdout_lines = []
    stderr_lines = []

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=TRAINING_REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            stdin=subprocess.DEVNULL,
            env=env,
        )

        import threading

        def stream_pipe(pipe, log_fn, buf):
            for line in pipe:
                line = line.rstrip()
                log_fn(line)
                buf.append(line)

        t_out = threading.Thread(target=stream_pipe, args=(proc.stdout, logger.info,  stdout_lines), daemon=True)
        t_err = threading.Thread(target=stream_pipe, args=(proc.stderr, logger.warning, stderr_lines), daemon=True)
        t_out.start()
        t_err.start()

        try:
            proc.wait(timeout=3600 * 6)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("Federated training timed out after 6 hours")

        t_out.join()
        t_err.join()

        class _Result:
            returncode = proc.returncode
            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)

        result = _Result()

    except FileNotFoundError as e:
        raise RuntimeError(f"Could not launch flwr: {e}")
    finally:
        for orig, bak in backups.items():
            try:
                shutil.move(bak, orig)
            except Exception as restore_err:
                logger.error(f"Failed to restore {orig}: {restore_err}")
        if backups:
            logger.info(f"[STEP 7] Restored {len(backups)} original dataset files")

    logger.info(f"[STEP 8] Return code: {result.returncode}")

    if result.returncode != 0:
        raise RuntimeError(
            f"flwr run exited with code {result.returncode}.\n"
            f"STDERR: {result.stderr[-2000:] if result.stderr else 'empty'}"
        )
    logger.info("[STEP 8] ✓ Federated training completed successfully")

    # ── STEP 9: Parse training_summary.csv ───────────────────────────────────
    summary_path = os.path.join(exp_dir, "training_summary.csv")
    logger.info(f"[STEP 9] Looking for: {summary_path}")

    if not os.path.exists(summary_path):
        raise RuntimeError(f"No training_summary.csv found in {exp_dir}")

    df_summary = pd.read_csv(summary_path)
    if df_summary.empty:
        raise RuntimeError("training_summary.csv is empty")

    best_idx   = df_summary["val_loss"].idxmin()
    best_row   = df_summary.loc[best_idx]
    best_round = int(best_row["round"])
    mae  = round(float(best_row["test_mae"]),  4)
    rmse = round(float(best_row["test_rmse"]), 4)
    logger.info(f"  Best round: {best_round} | MAE: {mae} | RMSE: {rmse}")

    # ── STEP 10: Parse predictions ────────────────────────────────────────────
    pred_len    = inp.prediction_length
    predictions: list[float] = []
    actuals:     list[float] = []

    pred_dir = os.path.join(exp_dir, "predictions")
    test_csv = os.path.join(pred_dir, f"client0_round{best_round}_test.csv")
    logger.info(f"[STEP 10] Looking for predictions: {test_csv}")

    if os.path.exists(test_csv):
        df_pred = pd.read_csv(test_csv)
        if len(df_pred) > 0:
            last_sample = df_pred.iloc[-1]
            pred_cols = [f"pred_t{t}" for t in range(pred_len)]
            true_cols = [f"true_t{t}" for t in range(pred_len)]
            predictions = [round(float(last_sample[c]), 4) for c in pred_cols if c in df_pred.columns]
            actuals     = [round(float(last_sample[c]), 4) for c in true_cols if c in df_pred.columns]
    else:
        logger.warning(f"  Predictions file not found: {test_csv}")
        if os.path.isdir(pred_dir):
            logger.warning(f"  Available: {os.listdir(pred_dir)[:20]}")

    # Fallback: synthesise from training_summary if no predictions file
    if not predictions:
        logger.info("[STEP 10] Fallback — building forecast from training_summary rows")
        for _, row in df_summary.iterrows():
            predictions.append(round(float(row.get("test_mae", 0)), 4))
        actuals = []

    # ── STEP 11: Compute MAPE ─────────────────────────────────────────────────
    mape = None
    if actuals and predictions and len(actuals) == len(predictions):
        mape_vals = [abs((a - p) / a) for a, p in zip(actuals, predictions) if a != 0]
        if mape_vals:
            mape = round(100.0 * sum(mape_vals) / len(mape_vals), 2)

    elapsed = round(time.time() - start, 2)
    logger.info("=" * 70)
    logger.info("FEDERATED TRAINING COMPLETE")
    logger.info(f"  MAE: {mae}  RMSE: {rmse}  MAPE: {mape}  Time: {elapsed}s")
    logger.info("=" * 70)

    return FederatedTrainingOutput(
        mae=mae,
        rmse=rmse,
        mape=mape,
        training_time_seconds=elapsed,
        predictions=predictions,
        actuals=actuals if actuals else None,
        best_round=best_round,
        num_clients=n,
        federated_algorithm=inp.federated_algorithm,
        exp_dir=exp_dir,
    )
