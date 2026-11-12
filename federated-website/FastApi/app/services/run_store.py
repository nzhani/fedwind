"""
Run store - run records as folders in runs/<run_id>/ (plan §5.2, §6.0).

  config.yaml     experiment config (written here)
  run.json        API record: status, flower_run_id, timestamps, error (written here)
  metrics.jsonl   one line per finished round (written by the ServerApp)
  result.json     final result (written by the ServerApp); wins over run.json

Nothing here invents data: a run without metrics.jsonl has an empty history.
"""

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.platform_schemas import (
    ACTIVE_STATUSES,
    ExperimentConfig,
    RoundMetrics,
    RunDetail,
    RunSummary,
)
from app.settings import Settings

# One API process; this lock makes "check no active run + create run" atomic.
create_lock = threading.Lock()

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id(config: ExperimentConfig) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{config.energy_type}-{config.strategy.value}-h{config.horizon}-{stamp}"


def run_dir(settings: Settings, run_id: str) -> Optional[Path]:
    """Folder for run_id, or None if the id isn't a safe folder name."""
    if not _RUN_ID_RE.match(run_id):
        return None
    return settings.runs_dir / run_id


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def read_metrics(folder: Path) -> List[RoundMetrics]:
    """Parse metrics.jsonl; skips a half-written last line or malformed lines."""
    history: List[RoundMetrics] = []
    try:
        with open(folder / "metrics.jsonl", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    history.append(RoundMetrics(**json.loads(line)))
                except (json.JSONDecodeError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return sorted(history, key=lambda m: m.round)


def create_run(settings: Settings, run_id: str, config: ExperimentConfig) -> Path:
    folder = settings.runs_dir / run_id
    folder.mkdir(parents=True, exist_ok=False)
    with open(folder / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({"run_id": run_id, **config.model_dump(mode="json")}, f, sort_keys=False)
    _write_json(folder / "run.json", {"run_id": run_id, "status": "queued", "created_at": utc_now()})
    return folder


def update_run(settings: Settings, run_id: str, **fields: Any) -> None:
    path = settings.runs_dir / run_id / "run.json"
    record = _read_json(path) or {"run_id": run_id}
    record.update(fields)
    _write_json(path, record)


def _load(folder: Path) -> Optional[RunDetail]:
    record = _read_json(folder / "run.json")
    try:
        with open(folder / "config.yaml", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    if record is None and not config:
        return None
    record = record or {}

    result = _read_json(folder / "result.json")
    status = record.get("status", "queued")
    error = record.get("error")
    # A run the user stopped stays "stopped": Flower ends it with RunNotRunningException,
    # which the ServerApp records as a failure on its way out.
    if result is not None and not (status == "stopped" and result.get("status") == "failed"):
        status = result.get("status", "done")
        error = result.get("error", error)

    history = read_metrics(folder)
    last = history[-1] if history else None
    created_at = record.get("created_at") or datetime.fromtimestamp(
        folder.stat().st_mtime, timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    return RunDetail(
        run_id=folder.name,
        status=status,
        created_at=created_at,
        strategy=str(config.get("strategy", "unknown")),
        horizon=int(config.get("horizon", 0)),
        sites=list(config.get("sites", [])),
        current_round=last.round if last else 0,
        total_rounds=int(config.get("rounds", last.total_rounds if last else 0)),
        error=error,
        config=config,
        flower_run_id=record.get("flower_run_id"),
        started_at=record.get("started_at"),
        finished_at=record.get("finished_at"),
        history=history,
        clients=list(last.clients) if last else [],
        result=result,
    )


def get_run(settings: Settings, run_id: str) -> Optional[RunDetail]:
    folder = run_dir(settings, run_id)
    if folder is None or not folder.is_dir():
        return None
    return _load(folder)


def list_runs(settings: Settings) -> List[RunSummary]:
    if not settings.runs_dir.is_dir():
        return []
    runs = []
    for folder in settings.runs_dir.iterdir():
        if folder.is_dir():
            detail = _load(folder)
            if detail is not None:
                runs.append(RunSummary(**detail.model_dump(include=set(RunSummary.model_fields))))
    return sorted(runs, key=lambda r: r.created_at, reverse=True)


def active_run(settings: Settings) -> Optional[RunSummary]:
    return next((r for r in list_runs(settings) if r.status in ACTIVE_STATUSES), None)
