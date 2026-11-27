"""
Import a training run made elsewhere (a Slurm cluster such as Irgetas, a teammate's machine) so the
website shows it like its own runs: training dashboard, results, and a model version that can serve
forecasts.

The run folder must be what the Flower app writes when the run config sets `runs-dir` and `run-id`
(my_flower_app/run_logging.py):
  result.json              status "done", metrics, model.checkpoint
  checkpoints/best.pt      the checkpoint result.json names (trainable weights + run config)
  metrics.jsonl            one line per round (optional, for the dashboard)
  config.yaml              optional; otherwise built from run_config.toml or result.json

The checkpoint is copied as is: it must come from the same model code version as the website's
inference service, or forecasts from it fail (the run still shows its results).
"""

import json
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from app.platform_schemas import RunDetail
from app.services import run_store
from app.services.accounts import AccountError
from app.settings import Settings

RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _config_from_run_config(rc: dict, result: dict) -> dict:
    """The website's config.yaml fields from a Flower run config (run_config.toml)."""
    sites = [s for s in str(rc.get("site-names", "")).split(",") if s]
    out = {
        "energy_type": rc.get("energy-type", result.get("energy_type", "wind")),
        "horizon": int(rc.get("pred-len", result.get("horizon", 0))),
        "strategy": rc.get("strategy", "fedavg"),
        "rounds": int(rc.get("num-server-rounds", result.get("rounds_completed") or 0)),
        "local_epochs": rc.get("local-epochs"),
        "seq_len": rc.get("seq-len"),
        "data_percent": rc.get("data-percent", 100),
        "seed": rc.get("random-seed"),
        "model": rc.get("model"),
        "sites": sites or sorted(((result.get("metrics") or {}).get("per_site") or {}).keys()),
    }
    return {k: v for k, v in out.items() if v is not None}


def import_run(settings: Settings, source: Path, run_id: Optional[str] = None, note: Optional[str] = None) -> RunDetail:
    source = source.resolve()
    result = _read_json(source / "result.json")
    if result is None:
        raise AccountError(422, f"{source}/result.json is missing or not JSON")
    if result.get("status") != "done":
        raise AccountError(422, f"The run's result says '{result.get('status')}'; only finished runs are imported")
    checkpoint = (result.get("model") or {}).get("checkpoint")
    ckpt = (source / checkpoint).resolve() if checkpoint else None
    if ckpt is None or source not in ckpt.parents or not ckpt.is_file():
        raise AccountError(422, f"Checkpoint '{checkpoint}' named in result.json is not in the folder")

    run_id = run_id or result.get("run_id") or source.name
    if not RUN_ID.match(run_id):
        raise AccountError(422, f"Run id '{run_id}' may use letters, digits, '.', '_' and '-' only")
    target = settings.runs_dir / run_id
    if target.exists():
        raise AccountError(409, f"A run '{run_id}' already exists; pass another --run-id")

    config_path = source / "config.yaml"
    if config_path.is_file():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    else:
        rc = {}
        toml = source / "run_config.toml"
        if toml.is_file():
            rc = tomllib.loads(toml.read_text(encoding="utf-8"))
        config = _config_from_run_config(rc, result)
    config["run_id"] = run_id
    if not config.get("horizon"):
        raise AccountError(422, "Can't tell the run's horizon: add config.yaml or run_config.toml (pred-len)")

    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.tmp", "__pycache__"))
    with open(target / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (target / "run.json").write_text(json.dumps({
        "run_id": run_id, "status": "done", "created_at": result.get("finished_at") or now,
        "finished_at": result.get("finished_at") or now, "imported_at": now, "imported_from": str(source),
        **({"note": note} if note else {})}, indent=2))
    return run_store.get_run(settings, run_id)
