"""
Demo runs, for a presentation laptop that can't train (DEMO_RUNS=1; off by default).

A started run is not sent to the federation. A background thread writes its files the way the
ServerApp does (metrics.jsonl one round every DEMO_ROUND_SECONDS, then result.json), so the
website shows the whole flow: rounds, the selected sites replying, a finished run, Promote.

The numbers are derived from the newest real finished run of the same energy type (same horizon
preferred), with small variation, and its checkpoint is reused when the horizon matches, so a
promoted demo run serves a real model's forecasts. run.json records "demo": true and the source
run, so demo runs can always be told apart from real ones; never use them as results.
"""

import json
import logging
import os
import random
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.platform_schemas import ExperimentConfig, RunDetail
from app.services import run_store
from app.settings import Settings

log = logging.getLogger(__name__)

_MODEL_ERRORS = {"mae", "rmse", "nmae", "nrmse", "mse", "mae_all_hours", "rmse_all_hours"}


def enabled() -> bool:
    return os.environ.get("DEMO_RUNS", "").strip().lower() in ("1", "true", "yes", "on")


def round_seconds() -> float:
    return float(os.environ.get("DEMO_ROUND_SECONDS", "25"))


def is_demo(folder: Path) -> bool:
    return bool((run_store._read_json(folder / "run.json") or {}).get("demo"))


def source_run(settings: Settings, energy: str, horizon: int) -> Optional[RunDetail]:
    """Newest real finished run of this energy type with round metrics; same horizon preferred."""
    best = None
    if not settings.runs_dir.is_dir():
        return None
    for folder in settings.runs_dir.iterdir():
        if not folder.is_dir() or is_demo(folder):
            continue
        run = run_store._load(folder)
        if run is None or run.status != "done" or not run.result or not run.history:
            continue
        if str(run.config.get("energy_type")) != energy:
            continue
        key = (run.horizon == horizon, run.result.get("finished_at") or run.created_at)
        if best is None or key > best[0]:
            best = (key, run)
    return best[1] if best else None


def start(settings: Settings, run_id: str, config: ExperimentConfig) -> None:
    src = source_run(settings, config.energy_type.value, config.horizon)
    run_store.update_run(settings, run_id, status="running", started_at=run_store.utc_now(), demo=True,
                         demo_source=src.run_id if src else None)
    threading.Thread(target=_play, args=(settings, run_id, config, src), daemon=True,
                     name=f"demo-run-{run_id}").start()


# ---------------------------------------------------------------------------

def _stopped(settings: Settings, run_id: str) -> bool:
    record = run_store._read_json(settings.runs_dir / run_id / "run.json") or {}
    return record.get("status") == "stopped"


def _j(rng: random.Random, v: float, spread: float) -> float:
    return v * (1 + rng.uniform(-spread, spread))


def _pick(site: str, entries: Dict[str, Any], i: int) -> Any:
    """The source entry for a site: same city name if there is one, else round-robin."""
    names = sorted(entries)
    for name in names:
        if name in site or site in name:
            return entries[name]
    return entries[names[i % len(names)]]


def _errors(rng: random.Random, metrics: Dict[str, Any], factor: float, spread: float) -> Dict[str, Any]:
    """Scale model errors by factor (with variation), keep baselines near the source, recompute skills."""
    out: Dict[str, Any] = {}
    for k, v in metrics.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            out[k] = v
        elif k in _MODEL_ERRORS:
            out[k] = _j(rng, v * factor, spread)
        elif "skill" in k:
            out[k] = v
        else:                                   # baselines (persistence, climatology), bias
            out[k] = _j(rng, v, 0.04)
    for skill, base in (("skill_vs_persistence", "persistence_rmse"), ("skill_vs_climatology", "climatology_rmse")):
        if skill in out and out.get(base) and out.get("rmse") is not None:
            out[skill] = 1 - out["rmse"] / out[base]
        elif skill in out and isinstance(out[skill], (int, float)):
            out[skill] = out[skill] + rng.uniform(-0.008, 0.008)
    return out


def _improvement(rng: random.Random, rounds: int) -> List[float]:
    """Error factor per round relative to the source's first round: falls a little each round."""
    f, out = 1.0, []
    for r in range(rounds):
        if r:
            f *= 1 - rng.uniform(0.018, 0.04)
        out.append(max(f, 0.85))
    return out


def _play(settings: Settings, run_id: str, config: ExperimentConfig, src: Optional[RunDetail]) -> None:
    try:
        _play_inner(settings, run_id, config, src)
    except Exception as e:                      # never leave the run "running" forever
        log.exception("demo run %s failed", run_id)
        run_store.update_run(settings, run_id, status="failed", error=f"Run failed: {e}",
                             finished_at=run_store.utc_now())


def _play_inner(settings: Settings, run_id: str, config: ExperimentConfig, src: Optional[RunDetail]) -> None:
    folder = settings.runs_dir / run_id
    rng = random.Random(run_id)
    sites = list(config.sites or [])
    rounds = config.rounds
    first = src.history[0] if src else None
    src_clients = {c.site: c.model_dump() for c in (first.clients if first else [])} or {
        "site": {"train_loss": 2.2, "val_mae": 1.0, "val_mae_real": 98.0}}
    per_site = {s: _pick(s, src_clients, i) for i, s in enumerate(sites)}
    windows = max(60, int(6100 * config.data_percent / 100))
    examples = {s: int(_j(rng, windows, 0.03)) for s in sites}
    factors = _improvement(rng, rounds)
    same_horizon = src is not None and src.horizon == config.horizon

    t0 = time.monotonic()
    last = t0
    with open(folder / "metrics.jsonl", "a", encoding="utf-8") as out:
        for r in range(1, rounds + 1):
            due = t0 + r * round_seconds() * rng.uniform(0.9, 1.1)
            while time.monotonic() < due:
                if _stopped(settings, run_id):
                    return
                time.sleep(min(1.0, max(0.0, due - time.monotonic())))
            if _stopped(settings, run_id):
                return
            f = factors[r - 1]
            clients = []
            for s in sites:
                c = per_site[s]
                row = {"site": s, "status": "replied", "num_examples": examples[s],
                       "train_loss": _j(rng, (c.get("train_loss") or 2.2) * f, 0.04),
                       "val_mae": _j(rng, (c.get("val_mae") or 1.0) * f, 0.03)}
                if c.get("val_mae_real") is not None:
                    row["val_mae_real"] = _j(rng, c["val_mae_real"] * f, 0.03)
                clients.append(row)
            now = time.monotonic()
            line: Dict[str, Any] = {
                "round": r, "total_rounds": rounds, "finished_at": run_store.utc_now(), "duration_s": now - last,
                "train_loss": sum(c["train_loss"] for c in clients) / max(1, len(clients)),
                "clients": clients,
            }
            last = now
            if first and first.val:
                line["val"] = {k: _j(rng, v * f, 0.015) for k, v in first.val.items()}
            if first and first.val_real:
                line["val_real"] = {k: (_j(rng, v * f, 0.015) if isinstance(v, (int, float)) else v)
                                    for k, v in first.val_real.items()}
            if same_horizon and first and first.uplink_bytes:
                line["uplink_bytes"], line["downlink_bytes"] = first.uplink_bytes, first.downlink_bytes
            out.write(json.dumps(line) + "\n")
            out.flush()

    result: Dict[str, Any] = {
        "run_id": run_id, "status": "done", "finished_at": run_store.utc_now(), "best_round": rounds,
        "rounds_completed": rounds, "stopped_early": False, "horizon": config.horizon,
        "energy_type": config.energy_type.value,
        "timing": {"total_s": time.monotonic() - t0, "mean_round_s": (time.monotonic() - t0) / max(1, rounds)},
    }
    if src:
        sm = src.result.get("metrics") or {}
        metrics: Dict[str, Any] = {}
        if sm.get("normalized"):
            metrics["normalized"] = _errors(rng, sm["normalized"], 1.0, 0.03)
        if sm.get("real"):
            metrics["real"] = _errors(rng, sm["real"], 1.0, 0.03)
        if sm.get("per_site"):
            metrics["per_site"] = {s: _errors(rng, _pick(s, sm["per_site"], i), 1.0, 0.04)
                                   for i, s in enumerate(sites)}
        if "reference" in sm:
            metrics["reference"] = sm["reference"]
        result["metrics"] = metrics
        result["unit"] = src.result.get("unit")
        if same_horizon:
            if src.result.get("payload"):
                result["payload"] = src.result["payload"]
            checkpoint = (src.result.get("model") or {}).get("checkpoint")
            source_file = settings.runs_dir / src.run_id / checkpoint if checkpoint else None
            if source_file and source_file.is_file():
                (folder / "checkpoints").mkdir(exist_ok=True)
                shutil.copyfile(source_file, folder / "checkpoints" / "best.pt")
                result["model"] = {"checkpoint": "checkpoints/best.pt"}
    if _stopped(settings, run_id):
        return
    run_store._write_json(folder / "result.json", result)
    run_store.update_run(settings, run_id, finished_at=result["finished_at"])
