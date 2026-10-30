"""
Training Client - Bridge to the external centralized training repository.
"""

import os
import sys
import time
import logging
import tempfile
import subprocess
import shutil

import numpy as np
import pandas as pd

from app.schemas import TrainingInput, TrainingOutput

logger = logging.getLogger(__name__)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
TRAINING_REPO_ROOT = os.environ["TRAINING_REPO_ROOT"]
RUN_SCRIPT = os.environ.get("RUN_SCRIPT", os.path.join(TRAINING_REPO_ROOT, "run_centralized.py"))
TRAINING_PYTHON = os.environ["TRAINING_PYTHON"]

MODEL_NAME_MAP = {
    "GPT4TS":       "gpt4ts_nonlinear",
    "GPT4TS_LINEAR":"gpt4ts_linear",
    "LLAMA":        "llama_nonlinear",
    "LLAMA_LINEAR": "llama_linear",
    "BERT":         "bert_nonlinear",
    "BERT_LINEAR":  "bert_linear",
    "BART":         "bart_nonlinear",
    "BART_LINEAR":  "bart_linear",
    "OPT":          "opt_nonlinear",
    "OPT_LINEAR":   "opt_linear",
    "GEMMA":        "gemma_nonlinear",
    "GEMMA_LINEAR": "gemma_linear",
    "QWEN":         "qwen_nonlinear",
    "QWEN_LINEAR":  "qwen_linear",
}


def run_centralized_training(inp: TrainingInput, job_id: str = None) -> TrainingOutput:
    """
    Execute centralized training by calling run_centralized.py as a subprocess.
    """
    import subprocess
    start = time.time()
    logger.info("=" * 70)
    logger.info("CENTRALIZED TRAINING REQUEST RECEIVED")
    logger.info("=" * 70)
    logger.info(f"  model_name:        {inp.model_name}")
    logger.info(f"  prediction_length: {inp.prediction_length}")
    logger.info(f"  dropout_rate:      {inp.dropout_rate}")
    logger.info(f"  learning_rate:     {inp.learning_rate}")
    logger.info(f"  batch_size:        {inp.batch_size}")
    logger.info(f"  seq_len:           {inp.seq_len}")
    logger.info(f"  epochs:            {inp.epochs}")
    logger.info(f"  csv_path:          {getattr(inp, 'csv_path', 'N/A')}")
    logger.info("-" * 70)

    # ── STEP 1: Verify paths ──────────────────────────────────────────────
    logger.info("[STEP 1] Verifying paths...")
    logger.info(f"  TRAINING_REPO_ROOT: {TRAINING_REPO_ROOT}")
    logger.info(f"  RUN_SCRIPT:         {RUN_SCRIPT}")
    logger.info(f"  TRAINING_PYTHON:    {TRAINING_PYTHON}")

    if not os.path.isdir(TRAINING_REPO_ROOT):
        raise RuntimeError(f"Training repo directory NOT FOUND: {TRAINING_REPO_ROOT}")
    if not os.path.isfile(RUN_SCRIPT):
        raise RuntimeError(f"run_centralized.py NOT FOUND: {RUN_SCRIPT}")
    if not os.path.isfile(TRAINING_PYTHON) and not shutil.which(TRAINING_PYTHON):
        raise RuntimeError(f"Python interpreter NOT FOUND: {TRAINING_PYTHON}")
    logger.info("  ✓ All paths verified")

    # ── STEP 2: Check torch ───────────────────────────────────────────────
    logger.info("[STEP 2] Checking if TRAINING_PYTHON can import torch...")
    try:
        check = subprocess.run(
            [TRAINING_PYTHON, "-c", "import torch; print(torch.__version__)"],
            capture_output=True, text=True, timeout=30,
        )
        if check.returncode == 0:
            logger.info(f"  ✓ torch {check.stdout.strip()} available")
        else:
            raise RuntimeError(
                f"TRAINING_PYTHON cannot import torch!\n"
                f"  Python: {TRAINING_PYTHON}\n"
                f"  STDERR: {check.stderr.strip()}"
            )
    except subprocess.TimeoutExpired:
        logger.warning("  ⚠ torch check timed out — proceeding anyway")

    # ── STEP 3: Create experiment directory ──────────────────────────────
    exp_base = os.environ["CENTRALIZED_WEB_DIR"]
    os.makedirs(exp_base, exist_ok=True)
    exp_dir = tempfile.mkdtemp(prefix="centralized_web_", dir=exp_base)
    logger.info(f"[STEP 3] Experiment directory created: {exp_dir}")
    if job_id:
        from app.services.job_store import job_store
        total_rounds = inp.epochs or 20
        job_store.set_exp_dir(job_id, exp_dir, total_rounds)

    # ── STEP 4: Build command ─────────────────────────────────────────────
    internal_model = MODEL_NAME_MAP.get(inp.model_name, inp.model_name.lower())
    logger.info(f"[STEP 4] Model mapping: {inp.model_name} -> {internal_model}")

    # ── STEP 4a: Prepare uploaded CSV for the training pipeline ─────────
    # The dataloader expects NASA-format files (with -END HEADER- marker).
    # User-uploaded CSVs are clean CSVs, so we prepend the NASA header and
    # place the file into datasets/custom/ as all 5 KZMET client files.
    # Originals are backed up and restored after training.
    dataset_dir = os.path.join(TRAINING_REPO_ROOT, "..", "datasets", "custom")
    dataset_dir = os.path.abspath(dataset_dir)
    kzmet_files = [
        "nasa_almaty.csv", "nasa_zhezkazgan.csv", "nasa_aktau.csv",
        "nasa_taraz.csv", "nasa_aktobe.csv",
    ]
    backups = {}  # original_path -> backup_path

    if inp.csv_path and os.path.isfile(inp.csv_path):
        # Read the uploaded CSV content
        with open(inp.csv_path, "r") as f:
            csv_content = f.read()

        # Prepend NASA header if not already present
        if "-END HEADER-" not in csv_content:
            nasa_header = (
                "-BEGIN HEADER-\n"
                "NASA/POWER Source - user upload\n"
                "-END HEADER-\n"
            )
            csv_content = nasa_header + csv_content

        # Backup originals and write prepared file as all 5 client files
        os.makedirs(dataset_dir, exist_ok=True)
        for fname in kzmet_files:
            orig = os.path.join(dataset_dir, fname)
            if os.path.exists(orig):
                bak = orig + ".bak"
                shutil.copy2(orig, bak)
                backups[orig] = bak
            with open(orig, "w") as f:
                f.write(csv_content)
        logger.info(f"[STEP 4a] Prepared uploaded CSV into {dataset_dir} ({len(backups)} backups)")
    else:
        logger.info("[STEP 4a] No csv_path — training on existing KZMET data")

    cmd = [
        TRAINING_PYTHON,
        RUN_SCRIPT,
        "--exp-dir", exp_dir,
        "--rounds", str(inp.epochs),
        "--pred-len", str(inp.prediction_length),
        "--lr", str(inp.learning_rate),
        "--batch-size", str(inp.batch_size),
        "--seq-len", str(inp.seq_len),
        "--dropout", str(inp.dropout_rate),
        "--model", internal_model,
        "--llm-layers", str(inp.llm_layers),
        "--weight-decay", str(inp.weight_decay),
        "--warmup-rounds", str(inp.warmup_rounds),
        "--patch-size", str(inp.patch_size),
        "--stride", str(inp.patch_stride),
        "--hidden-size", str(inp.hidden_size),
        "--kernel-size", str(inp.kernel_size),
        "--dataset-name", "KZMET",
    ]

    env = os.environ.copy()
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = TRAINING_REPO_ROOT + (
        os.pathsep + existing_pypath if existing_pypath else ""
    )
    env["CUDA_VISIBLE_DEVICES"] = os.environ.get("CUDA_VISIBLE_DEVICES", "0")

    logger.info(f"[STEP 4] Full command: {' '.join(cmd)}")
    logger.info(f"  cwd: {TRAINING_REPO_ROOT}")

    # ── STEP 5: Launch subprocess ─────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("[STEP 5] LAUNCHING run_centralized.py ...")
    logger.info("=" * 70)
    try:
        result = subprocess.run(
            cmd,
            cwd=TRAINING_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3600 * 6,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Training timed out after 6 hours")
    except FileNotFoundError as e:
        raise RuntimeError(f"Could not launch: {e}")
    finally:
        # Restore original KZMET dataset files
        for orig, bak in backups.items():
            try:
                shutil.move(bak, orig)
            except Exception as restore_err:
                logger.error(f"Failed to restore {orig} from {bak}: {restore_err}")
        if backups:
            logger.info(f"[STEP 5] Restored {len(backups)} original dataset files")

    logger.info(f"[STEP 6] Subprocess finished. Return code: {result.returncode}")
    if result.stdout:
        logger.info(f"  STDOUT (last 2000 chars):\n{result.stdout[-2000:]}")
    if result.stderr:
        logger.info(f"  STDERR (last 2000 chars):\n{result.stderr[-2000:]}")

    if result.returncode != 0:
        raise RuntimeError(
            f"run_centralized.py exited with code {result.returncode}.\n"
            f"STDERR: {result.stderr[-2000:] if result.stderr else 'empty'}"
        )
    logger.info("[STEP 6] ✓ Training completed successfully")

    # ── STEP 7: Parse training_summary.csv ───────────────────────────────
    summary_path = os.path.join(exp_dir, "training_summary.csv")
    logger.info(f"[STEP 7] Looking for: {summary_path}")

    if not os.path.exists(summary_path):
        log_path = os.path.join(exp_dir, "training.log")
        if os.path.exists(log_path):
            with open(log_path) as f:
                log_tail = f.readlines()[-20:]
            logger.error(f"  training.log tail:\n{''.join(log_tail)}")
        raise RuntimeError(f"No training_summary.csv found in {exp_dir}")

    df_summary = pd.read_csv(summary_path)
    logger.info(f"  ✓ Loaded training_summary.csv: {len(df_summary)} rows")
    logger.info(f"  Columns: {list(df_summary.columns)}")

    if df_summary.empty:
        raise RuntimeError("training_summary.csv is empty")

    # Best round = lowest val_loss
    best_idx = df_summary["val_loss"].idxmin()
    best_row = df_summary.loc[best_idx]
    best_round = int(best_row["round"])
    mae  = round(float(best_row["test_mae"]),  4)
    rmse = round(float(best_row["test_rmse"]), 4)
    logger.info(f"  Best round: {best_round} | MAE: {mae} | RMSE: {rmse}")

    # ── STEP 8: Parse predictions ─────────────────────────────────────────
    pred_len    = inp.prediction_length
    predictions: list[float] = []
    actuals:     list[float] = []

    pred_dir = os.path.join(exp_dir, "predictions")
    # run_centralized.py saves: predictions/centralized_round{N}_test.csv
    # or: predictions/client0_round{N}_test.csv  (same helper as federated)
    for prefix in [f"centralized_round{best_round}", f"client0_round{best_round}"]:
        test_csv = os.path.join(pred_dir, f"{prefix}_test.csv")
        if os.path.exists(test_csv):
            logger.info(f"[STEP 8] Loading predictions: {test_csv}")
            df_pred = pd.read_csv(test_csv)
            if len(df_pred) > 0:
                # Take the last sample's horizon predictions
                last_sample = df_pred.iloc[-1]
                pred_cols = [f"pred_t{t}" for t in range(pred_len)]
                true_cols = [f"true_t{t}" for t in range(pred_len)]
                # Fallback: single-column format
                if not any(c in df_pred.columns for c in pred_cols):
                    if "predicted" in df_pred.columns:
                        predictions = [round(float(v), 4) for v in df_pred["predicted"].values[:pred_len]]
                    if "actual" in df_pred.columns:
                        actuals = [round(float(v), 4) for v in df_pred["actual"].values[:pred_len]]
                else:
                    predictions = [round(float(last_sample[c]), 4) for c in pred_cols if c in df_pred.columns]
                    actuals     = [round(float(last_sample[c]), 4) for c in true_cols if c in df_pred.columns]
            break
    else:
        logger.warning(f"[STEP 8] No predictions file found in {pred_dir}")
        if os.path.isdir(pred_dir):
            logger.warning(f"  Available: {os.listdir(pred_dir)[:20]}")

    # ── STEP 9: Build forecast from training_summary rows (fallback) ──────
    # If no predictions file, synthesise from the per-round test metrics so
    # the frontend still gets a graph.
    if not predictions:
        logger.info("[STEP 9] No predictions CSV — building forecast from training_summary rows")
        for _, row in df_summary.iterrows():
            predictions.append(round(float(row.get("test_mae", 0)), 4))
        actuals = []   # nothing to show as actuals in this fallback

    elapsed = round(time.time() - start, 2)
    logger.info("=" * 70)
    logger.info("TRAINING COMPLETE — RETURNING RESULTS")
    logger.info(f"  MAE:  {mae}  |  RMSE: {rmse}")
    logger.info(f"  Time: {elapsed}s  |  Predictions: {len(predictions)}")
    logger.info("=" * 70)

    return TrainingOutput(
        mae=mae,
        rmse=rmse,
        training_time_seconds=elapsed,
        predictions=predictions,
        actuals=actuals if actuals else None,
        exp_dir=exp_dir,        # passed through so service can expose download links
    )
