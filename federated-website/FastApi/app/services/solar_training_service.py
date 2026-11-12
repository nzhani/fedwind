"""
Solar Training Service - SKELETON (not implemented).

Mirrors training_service.py for wind.  Every public function raises
NotImplementedError; the solar router turns that into HTTP 501, which
the solar dashboard shows as an error (same as any failed wind call).

Planned flow (same as wind, different target column):
  1. Validate the uploaded CSV  (YEAR, MO, DY, HR + an irradiance column)
  2. Build a SolarTrainingInput from the user config + saved file path
  3. Call the training client:
       centralized -> run_centralized.py  with --target ALLSKY_SFC_SW_DWN
       federated   -> flwr run (flower_app) with target=ALLSKY_SFC_SW_DWN
     The Flower dataloader already accepts a target column
     (Long-term_Forecasting/flower_app/my_flower_app/dataloader.py:
      preprocess_nasa_data(file_path, target_column='WS50M')).
  4. Convert the output into SolarTrainingResult (adds clear_sky,
     daytime_mae, skill_score)
"""

import os
from typing import List

from app.schemas import (
    SolarTrainingConfig,
    SolarTrainingResult,
    SolarTarget,
    SOLAR_TIME_COLUMNS,
    VALID_SOLAR_PREDICTION_LENGTHS,
)


SOLAR_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "solar")


def _todo(what: str):
    raise NotImplementedError(f"Solar {what} is not implemented yet (skeleton).")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def required_solar_columns(target: SolarTarget) -> set:
    """Time columns + the selected irradiance column."""
    return SOLAR_TIME_COLUMNS | {target.value}


def validate_solar_csv(file_path: str, target: SolarTarget) -> dict:
    """
    TODO: same checks as training_service.validate_csv, but against
    required_solar_columns(target), and reject files whose target column is
    all zeros / NASA fill values (-999).
    """
    _todo("CSV validation")


def validate_solar_config(config: SolarTrainingConfig) -> None:
    """TODO: check prediction_length in VALID_SOLAR_PREDICTION_LENGTHS, dropout range, etc."""
    _todo("config validation")


# ---------------------------------------------------------------------------
# File management  (uploads/solar/)
# ---------------------------------------------------------------------------

def save_solar_upload(filename: str, content: bytes) -> dict:
    """TODO: write to SOLAR_UPLOAD_DIR with a timestamp prefix, return FileInfo fields."""
    _todo("upload")


def list_solar_files() -> List[dict]:
    """TODO: list *.csv in SOLAR_UPLOAD_DIR (see routers/upload.py:list_files)."""
    _todo("file listing")


def delete_solar_file(filename: str) -> None:
    """TODO: path-traversal check + os.remove (see routers/upload.py:delete_file)."""
    _todo("file deletion")


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def start_solar_training(filename: str, config: SolarTrainingConfig, job_id: str = None) -> SolarTrainingResult:
    """
    TODO: unified centralized/federated pipeline for solar.

    Suggested implementation:
      inp = SolarTrainingInput(csv_path=..., model_name=config.training_model.value,
                               target_column=config.target.value, ...)
      output = run_centralized_training(inp)  or  run_federated_training(inp)
      -> build SolarForecastPoint list (attach clear_sky from CLRSKY_SFC_SW_DWN)
      -> compute daytime_mae / skill_score
    """
    _todo("training")


def get_solar_job(job_id: str) -> dict:
    """TODO: read from job_store (shared with wind) once start_solar_training exists."""
    _todo("job status")


def get_solar_progress(job_id: str) -> dict:
    """TODO: same as routers/jobs.py:get_job_progress — read clientN_roundK_test.csv."""
    _todo("job progress")


# ---------------------------------------------------------------------------
# Federated client endpoints  (weights only, raw data never leaves the site)
# ---------------------------------------------------------------------------

def get_solar_model_skeleton() -> dict:
    """TODO: architecture + hyper-params for a PV-site client (see routers/federated.py)."""
    _todo("model skeleton")


def submit_solar_model_update(update: dict) -> dict:
    """TODO: queue a client's weights for the given round (separate queue from wind)."""
    _todo("model update")


def aggregate_solar_round(round_number: int, prediction_length: int) -> dict:
    """TODO: FedAvg/FedProx/... over queued solar updates for one round."""
    _todo("aggregation")
