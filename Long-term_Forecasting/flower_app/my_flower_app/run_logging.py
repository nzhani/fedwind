"""
Run folder writers for the web platform (plan §5.2–5.5, T2.1–T2.3).

  runs/<run_id>/metrics.jsonl          one JSON line per finished round
  runs/<run_id>/checkpoints/*.pt       trainable state + run config (best.pt, round_NNNN.pt)
  runs/<run_id>/result.json            final result; {"status": "failed"} on error
  runs/<run_id>/logs/serverapp.log     server log

Active only when the run config sets `runs-dir` and `run-id` (the API does);
research runs through run_flower_experiment.sh keep their legacy outputs only.
Nothing here fills gaps with made-up numbers: missing values stay null.
"""

import json
import logging
import math
import os
import traceback
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import torch


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(v: Any) -> Optional[float]:
    """JSON-safe float: None for missing, NaN or infinite values."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _mean(values) -> Optional[float]:
    vals = [v for v in (_num(x) for x in values) if v is not None]
    return sum(vals) / len(vals) if vals else None


def array_bytes(state: Mapping[str, torch.Tensor]) -> int:
    return int(sum(t.numel() * t.element_size() for t in state.values()))


class RunLogger:
    def __init__(self, runs_dir: str, run_id: str, run_config: Mapping, partition_sites: list[str], selected: list[str]):
        self.dir = os.path.join(runs_dir, run_id)
        self.run_id = run_id
        self.run_config = dict(run_config)
        self.partition_sites = partition_sites
        self.selected = selected or partition_sites
        os.makedirs(os.path.join(self.dir, "checkpoints"), exist_ok=True)
        os.makedirs(os.path.join(self.dir, "logs"), exist_ok=True)
        handler = logging.FileHandler(os.path.join(self.dir, "logs", "serverapp.log"))
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(handler)

    @classmethod
    def from_run_config(cls, run_config: Mapping, partition_sites: list[str], selected: list[str]) -> Optional["RunLogger"]:
        runs_dir, run_id = run_config.get("runs-dir", ""), run_config.get("run-id", "")
        if not runs_dir or not run_id:
            return None
        return cls(runs_dir, run_id, run_config, partition_sites, selected)

    def site(self, pid: int) -> str:
        pid = int(pid)
        return self.partition_sites[pid] if 0 <= pid < len(self.partition_sites) else f"client_{pid}"

    # -- per round -------------------------------------------------------------

    def round(
        self,
        r: int,
        total_rounds: int,
        duration_s: float,
        train: Mapping[int, Mapping],
        evaluate: Mapping[int, Mapping],
        uplink_bytes: Optional[int],
        downlink_bytes: Optional[int],
    ) -> dict:
        clients = []
        replied_sites = set()
        for pid, m in sorted(train.items()):
            site = self.site(pid)
            replied_sites.add(site)
            ev = evaluate.get(pid, {})
            clients.append({
                "site": site,
                "status": "replied",
                "num_examples": int(m["num-examples"]) if "num-examples" in m else None,
                "train_loss": _num(m.get("train_loss")),
                "val_mae": _num(ev.get("val_mae")),
                "val_mae_real": _num(ev.get("val_mae_real")),
            })
        for site in self.selected:
            if site not in replied_sites:
                clients.append({"site": site, "status": "dropped"})

        evs = list(evaluate.values())
        line = {
            "round": r,
            "total_rounds": total_rounds,
            "finished_at": _utc_now(),
            "duration_s": _num(duration_s),
            "train_loss": _mean(m.get("train_loss") for m in train.values()),
            "val": {
                "mse": _mean(e.get("val_loss") for e in evs),
                "mae": _mean(e.get("val_mae") for e in evs),
                "rmse": _mean(e.get("val_rmse") for e in evs),
            },
            "val_real": {
                "mae": _mean(e.get("val_mae_real") for e in evs),
                "rmse": _mean(e.get("val_rmse_real") for e in evs),
                "unit": "m/s",
            },
            "clients": clients,
            "uplink_bytes": uplink_bytes,      # per client, trainable params only
            "downlink_bytes": downlink_bytes,  # per client
        }
        with open(os.path.join(self.dir, "metrics.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return line

    # -- checkpoints -----------------------------------------------------------

    def checkpoint(self, name: str, state: Mapping[str, torch.Tensor], r: int, metrics: Mapping) -> str:
        path = os.path.join(self.dir, "checkpoints", name)
        tmp = path + ".tmp"
        torch.save({
            "trainable_state": {k: v.detach().cpu() for k, v in state.items()},
            "run_config": self.run_config,
            "round": r,
            "metrics": dict(metrics),
        }, tmp)
        os.replace(tmp, path)
        return path

    # -- final result ----------------------------------------------------------

    def result(
        self,
        best_round: int,
        best_eval: Mapping[int, Mapping],
        total_s: float,
        rounds_done: int,
        uplink_bytes: Optional[int],
        backbone_bytes: int,
        stopped_early: bool,
    ) -> dict:
        per_site = {}
        for pid, e in sorted(best_eval.items()):
            mae, rmse = _num(e.get("test_mae_real")), _num(e.get("test_rmse_real"))
            mean_obs, persist = _num(e.get("test_mean_real")), _num(e.get("persistence_mae_real"))
            per_site[self.site(pid)] = {
                "mae": mae,
                "rmse": rmse,
                "nmae": mae / mean_obs if mae is not None and mean_obs else None,
                "nrmse": rmse / mean_obs if rmse is not None and mean_obs else None,
                "persistence_mae": persist,
                "skill_vs_persistence": 1 - mae / persist if mae is not None and persist else None,
            }
        evs = list(best_eval.values())
        sites = list(per_site.values())
        result = {
            "run_id": self.run_id,
            "status": "done",
            "finished_at": _utc_now(),
            "best_round": best_round,
            "rounds_completed": rounds_done,
            "stopped_early": stopped_early,
            "horizon": int(self.run_config.get("pred-len", 0)),
            "unit": "m/s",
            "metrics": {
                "normalized": {
                    "mae": _mean(e.get("test_mae") for e in evs),
                    "rmse": _mean(e.get("test_rmse") for e in evs),
                },
                # Means over sites; nMAE/nRMSE divide by each site's mean observed test speed.
                "real": {
                    "mae": _mean(s["mae"] for s in sites),
                    "rmse": _mean(s["rmse"] for s in sites),
                    "nmae": _mean(s["nmae"] for s in sites),
                    "nrmse": _mean(s["nrmse"] for s in sites),
                    "skill_vs_persistence": _mean(s["skill_vs_persistence"] for s in sites),
                },
                "per_site": per_site,
            },
            "model": {"checkpoint": "checkpoints/best.pt"},
            "timing": {"total_s": _num(total_s), "mean_round_s": _num(total_s / rounds_done) if rounds_done else None},
            "payload": {"uplink_bytes_per_client_round": uplink_bytes, "backbone_bytes": backbone_bytes},
        }
        self._write_result(result)
        return result

    def failed(self, error: BaseException) -> None:
        logging.error("Run failed: %s\n%s", error, traceback.format_exc())
        self._write_result({"run_id": self.run_id, "status": "failed", "finished_at": _utc_now(), "error": f"{type(error).__name__}: {error}"})

    def _write_result(self, result: dict) -> None:
        tmp = os.path.join(self.dir, "result.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        os.replace(tmp, os.path.join(self.dir, "result.json"))
