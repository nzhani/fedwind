"""
Federation client - the API's only way to talk to the Flower federation.

The API starts, stops and checks runs through this interface (plan §5.6, T4.1).
FEDERATION_ADDRESS unset -> NotConnectedFederation, whose calls raise
FederationUnavailable; the routers turn that into HTTP 503.  Set -> FlwrCliFederation,
which calls the `flwr` CLI against the SuperLink's control API:

  flwr run   <FLOWER_APP_DIR> <FLWR_FEDERATION> --run-config runs/<id>/run_config.toml
  flwr stop  <flower_run_id> <FLOWER_APP_DIR> <FLWR_FEDERATION>
  flwr ls    <FLOWER_APP_DIR> <FLWR_FEDERATION> --run-id <flower_run_id> --format json
  flwr supernode ls <FLOWER_APP_DIR> <FLWR_FEDERATION> --format json

The federation's address comes from [tool.flwr.federations.<FLWR_FEDERATION>] in the
Flower app's pyproject.toml ("lab" = superlink:9093 in Compose); FEDERATION_ADDRESS
must point at the same SuperLink and is used for a quick reachability check.
"""

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import yaml

from app.platform_schemas import EnergyType, FederationStatus
from app.services.site_registry import list_sites
from app.settings import get_settings


class FederationUnavailable(Exception):
    """The federation can't be reached; the message is shown to the user."""


class FederationClient(Protocol):
    def status(self) -> FederationStatus: ...

    def start_run(self, run_id: str, config_path: Path) -> str:
        """Start a run from runs/<run_id>/config.yaml; returns the Flower run id."""
        ...

    def stop_run(self, flower_run_id: str) -> None: ...

    def run_state(self, flower_run_id: str) -> Optional[str]:
        """Flower's state for the run ('running', 'finished:completed', ...), or None if unknown."""
        ...


class NotConnectedFederation:
    def __init__(self, detail: str = "Federation not connected: no SuperLink is configured (FEDERATION_ADDRESS is unset)."):
        self.detail = detail

    def status(self) -> FederationStatus:
        return FederationStatus(connected=False, detail=self.detail)

    def start_run(self, run_id: str, config_path: Path) -> str:
        raise FederationUnavailable(self.detail)

    def stop_run(self, flower_run_id: str) -> None:
        raise FederationUnavailable(self.detail)

    def run_state(self, flower_run_id: str) -> Optional[str]:
        return None


# ---------------------------------------------------------------------------
# Experiment config (plan §5.1) -> Flower run config (pyproject.toml keys)
# ---------------------------------------------------------------------------

_RUN_CONFIG_KEYS = {
    "rounds": "num-server-rounds",
    "local_epochs": "local-epochs",
    "fraction_train": "fraction-train",
    "min_train_clients": "min-train-clients",
    "round_timeout_s": "round-timeout",
    "horizon": "pred-len",
    "seq_len": "seq-len",
    "model": "model",
    "llm_layers": "llm-layers",
    "peft_method": "peft-method",
    "lora_r": "lora-r",
    "lora_alpha": "lora-alpha",
    "is_pretrained": "is-pretrained",
    "lr": "lr",
    "weight_decay": "weight-decay",
    "warmup_rounds": "warmup-rounds",
    "batch_size": "batch-size",
    "dropout": "dropout",
    "seed": "random-seed",
    "strategy": "strategy",
    "proximal_mu": "proximal-mu",
    "checkpoint_every": "checkpoint-every",
    "data_source": "data-source",
    "data_percent": "data-percent",
}


def to_run_config(config: Dict[str, Any], run_id: str, server_runs_dir: str, partition_sites: List[str]) -> Dict[str, Any]:
    rc: Dict[str, Any] = {flwr: config[key] for key, flwr in _RUN_CONFIG_KEYS.items() if key in config}
    rc["round-timeout"] = float(rc.get("round-timeout", 900))
    rc.update({
        "dataset-name": str(config.get("dataset", "kzmet")).upper(),
        "target-column": "WS50M",
        "run-id": run_id,
        "runs-dir": server_runs_dir,
        "site-names": ",".join(config["sites"]),
        "partition-sites": ",".join(partition_sites),
        "num-clients": len(config["sites"]),
        "resume-from": config.get("resume_from") or "",
        "save-predictions": False,
    })
    return rc


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v))  # a JSON string is a valid TOML basic string


def write_run_config_toml(path: Path, rc: Dict[str, Any]) -> None:
    path.write_text("".join(f"{k} = {_toml_value(v)}\n" for k, v in rc.items()), encoding="utf-8")


class FlwrCliFederation:
    def __init__(self, address: str, app_dir: str, federation: str, flwr_bin: str, server_runs_dir: str, timeout_s: float = 120):
        self.address = address
        self.app_dir = app_dir
        self.federation = federation
        self.flwr_bin = flwr_bin
        self.server_runs_dir = server_runs_dir
        self.timeout_s = timeout_s

    def _flwr(self, *args: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        cmd = [self.flwr_bin, *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or self.timeout_s, cwd=self.app_dir)
        except FileNotFoundError as e:
            raise FederationUnavailable(f"Flower CLI not found ({self.flwr_bin})") from e
        except subprocess.TimeoutExpired as e:
            raise FederationUnavailable(f"`flwr {args[0]}` timed out after {e.timeout:.0f} s") from e
        out = proc.stdout.strip()
        # --format json prints one JSON object; anything before it is a notice
        start = out.find("{")
        try:
            data = json.loads(out[start:]) if start >= 0 else {}
        except json.JSONDecodeError:
            data = {}
        if proc.returncode != 0 or not data.get("success", False):
            detail = data.get("error-message") or (proc.stderr or out).strip()[-500:]
            raise FederationUnavailable(f"`flwr {args[0]}` failed: {detail}")
        return data

    def _reachable(self) -> bool:
        host, _, port = self.address.rpartition(":")
        try:
            with socket.create_connection((host or "localhost", int(port)), timeout=2):
                return True
        except (OSError, ValueError):
            return False

    def status(self) -> FederationStatus:
        if not self._reachable():
            return FederationStatus(connected=False, detail=f"SuperLink at {self.address} is not reachable")
        try:
            nodes = self._flwr("supernode", "ls", self.app_dir, self.federation, "--format", "json", timeout=20).get("nodes", [])
        except FederationUnavailable as e:
            return FederationStatus(connected=True, detail=f"SuperLink reachable; node list unavailable: {e}")
        online = sum(1 for n in nodes if n.get("status") == "online")
        return FederationStatus(connected=True, detail=f"SuperLink at {self.address}", connected_nodes=online)

    def start_run(self, run_id: str, config_path: Path) -> str:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        sites = sorted(
            (s for s in list_sites(get_settings(), EnergyType.WIND) if s.partition_id is not None),
            key=lambda s: s.partition_id,
        )
        rc = to_run_config(config, run_id, self.server_runs_dir, [s.id for s in sites])
        toml_path = config_path.parent / "run_config.toml"
        write_run_config_toml(toml_path, rc)
        data = self._flwr("run", self.app_dir, self.federation, "--run-config", str(toml_path), "--format", "json")
        return str(data["run-id"])

    def stop_run(self, flower_run_id: str) -> None:
        self._flwr("stop", flower_run_id, self.app_dir, self.federation, "--format", "json")

    def run_state(self, flower_run_id: str) -> Optional[str]:
        try:
            data = self._flwr("ls", self.app_dir, self.federation, "--run-id", flower_run_id, "--format", "json", timeout=20)
        except FederationUnavailable:
            return None
        runs = data.get("runs", [])
        return runs[0].get("status") if runs else None


def get_federation() -> FederationClient:
    settings = get_settings()
    if not settings.federation_address:
        return NotConnectedFederation()
    return FlwrCliFederation(
        address=settings.federation_address,
        app_dir=os.environ.get("FLOWER_APP_DIR", "/flower_app"),
        federation=os.environ.get("FLWR_FEDERATION", "lab"),
        flwr_bin=os.environ.get("FLWR_BIN", "flwr"),
        # Where the ServerApp (in the superlink container) sees the runs folder
        server_runs_dir=os.environ.get("SERVER_RUNS_DIR", str(settings.runs_dir)),
    )
