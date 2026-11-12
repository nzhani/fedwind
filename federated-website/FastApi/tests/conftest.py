import json
import shutil
from pathlib import Path
from typing import List, Optional

import pytest
from fastapi.testclient import TestClient

from app.platform_schemas import FederationStatus

SEED = Path(__file__).resolve().parents[3] / "deploy" / "seed" / "sites.json"


class FakeFederation:
    """Connected federation that records calls instead of running Flower."""

    def __init__(self, nodes: Optional[int] = 5):
        self.nodes = nodes
        self.started: List[str] = []
        self.stopped: List[str] = []
        self.state: Optional[str] = "running"

    def status(self):
        return FederationStatus(connected=True, detail="fake", connected_nodes=self.nodes)

    def start_run(self, run_id, config_path):
        assert config_path.is_file()
        self.started.append(run_id)
        return str(1000 + len(self.started))

    def stop_run(self, flower_run_id):
        self.stopped.append(flower_run_id)

    def run_state(self, flower_run_id):
        return self.state


class FakeInference:
    def __init__(self):
        self.calls = []

    def forecast(self, site, horizon, as_of, model_path):
        self.calls.append((site, horizon, as_of, model_path))
        return {
            "as_of": as_of or "2024-06-01T00:00:00Z",
            "unit": "m/s",
            "actual": [{"timestamp": "2024-05-31T23:00:00Z", "wind_speed": 5.0}],
            "forecast": [{"timestamp": f"2024-06-01T{h:02d}:00:00Z", "wind_speed": 5.5} for h in range(min(horizon, 3))],
        }


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    seed = tmp_path / "sites.json"
    shutil.copyfile(SEED, seed)
    monkeypatch.setenv("FEDWIND_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FEDWIND_SITES_SEED", str(seed))
    monkeypatch.delenv("FEDERATION_ADDRESS", raising=False)
    monkeypatch.delenv("INFERENCE_URL_TEMPLATE", raising=False)
    return tmp_path / "data"


@pytest.fixture
def client(data_dir):
    from main import app

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def write_csv(rows: int = 800, header: str = "YEAR,MO,DY,HR,WS50M", nasa_block: bool = True) -> bytes:
    lines = []
    if nasa_block:
        lines += ["-BEGIN HEADER-", "NASA/POWER test", "-END HEADER-"]
    lines.append(header)
    for i in range(rows):
        day, hour = divmod(i, 24)
        lines.append(f"2024,1,{day % 28 + 1},{hour},{5 + (i % 7) * 0.5}")
    return ("\n".join(lines) + "\n").encode()


def write_finished_run(data_dir: Path, run_id: str = "wind-fedavg-h72-20261101T000000Z", horizon: int = 72):
    folder = data_dir / "runs" / run_id
    (folder / "checkpoints").mkdir(parents=True)
    (folder / "config.yaml").write_text(
        f"run_id: {run_id}\nenergy_type: wind\nstrategy: fedavg\nhorizon: {horizon}\nrounds: 2\n"
        "sites: [almaty, aktau]\n"
    )
    (folder / "run.json").write_text(json.dumps({"run_id": run_id, "status": "running", "created_at": "2026-11-01T00:00:00Z"}))
    (folder / "metrics.jsonl").write_text(
        json.dumps({"round": 1, "total_rounds": 2, "val": {"mae": 0.5},
                    "clients": [{"site": "almaty", "status": "replied"}, {"site": "aktau", "status": "dropped"}]}) + "\n"
        + json.dumps({"round": 2, "total_rounds": 2, "val": {"mae": 0.4},
                      "clients": [{"site": "almaty", "status": "replied"}, {"site": "aktau", "status": "replied"}]}) + "\n"
        + '{"round": 3, "total'  # half-written line
    )
    (folder / "checkpoints" / "best.pt").write_bytes(b"checkpoint-bytes")
    (folder / "result.json").write_text(json.dumps({
        "run_id": run_id, "status": "done", "best_round": 2, "horizon": horizon,
        "metrics": {"real": {"mae": 1.1}}, "model": {"checkpoint": "checkpoints/best.pt"},
    }))
    return folder
