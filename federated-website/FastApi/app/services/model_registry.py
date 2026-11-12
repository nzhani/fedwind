"""
Model registry - promoted checkpoints per (energy_type, horizon) (plan T3.1).

  models/<energy_type>/h<horizon>/current.pt     copy of the run's best checkpoint
  models/<energy_type>/h<horizon>/current.json   which run it came from

Inference services mount models/ read-only and load current.pt.
"""

import json
import shutil
from typing import List, Optional

from app.platform_schemas import RegisteredModel, RunDetail
from app.services.run_store import utc_now
from app.settings import Settings


class PromoteError(ValueError):
    pass


def model_path(energy_type: str, horizon: int) -> str:
    """Path of the current checkpoint, relative to models/."""
    return f"{energy_type}/h{horizon}/current.pt"


def current_model(settings: Settings, energy_type: str, horizon: int) -> Optional[RegisteredModel]:
    meta = settings.models_dir / energy_type / f"h{horizon}" / "current.json"
    try:
        with open(meta, encoding="utf-8") as f:
            return RegisteredModel(**json.load(f))
    except FileNotFoundError:
        return None


def list_models(settings: Settings) -> List[RegisteredModel]:
    if not settings.models_dir.is_dir():
        return []
    models = []
    for meta in sorted(settings.models_dir.glob("*/h*/current.json")):
        with open(meta, encoding="utf-8") as f:
            models.append(RegisteredModel(**json.load(f)))
    return models


def promote(settings: Settings, run: RunDetail) -> RegisteredModel:
    if run.status != "done" or not run.result:
        raise PromoteError(f"Run '{run.run_id}' is {run.status}; only finished runs can be promoted")

    checkpoint = (run.result.get("model") or {}).get("checkpoint")
    if not checkpoint:
        raise PromoteError("result.json has no model.checkpoint")
    run_folder = (settings.runs_dir / run.run_id).resolve()
    source = (run_folder / checkpoint).resolve()
    if run_folder not in source.parents or not source.is_file():
        raise PromoteError(f"Checkpoint '{checkpoint}' not found in the run folder")

    energy_type = str(run.config.get("energy_type", "wind"))
    target_dir = settings.models_dir / energy_type / f"h{run.horizon}"
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp = target_dir / "current.pt.tmp"
    shutil.copyfile(source, tmp)
    tmp.replace(target_dir / "current.pt")

    model = RegisteredModel(
        energy_type=energy_type,
        horizon=run.horizon,
        run_id=run.run_id,
        promoted_at=utc_now(),
        metrics=run.result.get("metrics"),
    )
    with open(target_dir / "current.json", "w", encoding="utf-8") as f:
        json.dump(model.model_dump(mode="json"), f, indent=2)
    return model
