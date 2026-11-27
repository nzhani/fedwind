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
        self.window_calls = []

    def forecast_window(self, body):
        self.window_calls.append(body)
        return {"as_of": body["end_hour"], "unit": "m/s",
                "actual": [{"timestamp": body["end_hour"], "wind_speed": 6.0, "wind_power_kw": 30000.0}],
                "forecast": [{"timestamp": f"2026-11-18T{h:02d}:00:00Z", "wind_speed": 8.0, "wind_power_kw": 50000.0}
                             for h in range(3)]}

    def forecast(self, site, horizon, as_of, model_path):
        self.calls.append((site, horizon, as_of, model_path))
        if model_path.startswith("solar/"):
            return {
                "as_of": as_of or "2024-06-01T00:00:00Z",
                "unit": "W/m2",
                "actual": [{"timestamp": "2024-05-31T23:00:00Z", "ghi": 0.0, "clear_sky_ghi": 0.0, "pv_power_kw": 0.0}],
                "forecast": [{"timestamp": f"2024-06-01T{h:02d}:00:00Z", "ghi": 100.0 * h, "clear_sky_ghi": 150.0 * h,
                              "pv_power_kw": 80.0 * h} for h in range(min(horizon, 3))],
            }
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
    monkeypatch.setenv("NOTIFY_LOOP", "off")          # tests drive app.services.notifications themselves
    monkeypatch.setenv("SITE_MAINTENANCE_LOOP", "off")
    monkeypatch.setenv("SCHEDULER_LOOP", "off")
    monkeypatch.setenv("PLATFORM_JOBS_LOOP", "off")
    monkeypatch.setenv("RATE_LIMIT", "off")
    monkeypatch.delenv("TRAIN_SCHEDULE", raising=False)
    monkeypatch.delenv("SITE_CA_DIR", raising=False)  # the CA goes to <data>/site-ca
    monkeypatch.delenv("FLOWER_NODE_AUTH", raising=False)
    monkeypatch.delenv("SITE_AUTH_MODE", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("SUPPORT_CHAT_ID", raising=False)
    return tmp_path / "data"




def fake_admin():
    from app.services.accounts import User

    return User(id=1, email="admin@test.kz", name="Test Admin", role="admin", org_id=None, org_name=None, active=True)


@pytest.fixture
def client(data_dir, monkeypatch):
    """API client whose admin checks pass (route tests). Account tests use `db_client`."""
    from app.auth import require_admin
    from main import app

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("app.services.accounts.record", lambda *a, **k: None)
    app.dependency_overrides[require_admin] = fake_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Postgres for account tests: TEST_DATABASE_URL, or a throwaway postgres:16-alpine container
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_url():
    import os
    import subprocess
    import time

    import psycopg

    url = os.environ.get("TEST_DATABASE_URL")
    container = None
    if not url:
        try:
            container = subprocess.run(
                ["docker", "run", "-d", "--rm", "-e", "POSTGRES_PASSWORD=test", "-e", "POSTGRES_DB=fedwind_test",
                 "-p", "127.0.0.1::5432", "postgres:16-alpine"],
                check=True, capture_output=True, text=True, timeout=60,
            ).stdout.strip()
            port = subprocess.run(["docker", "port", container, "5432/tcp"], check=True, capture_output=True,
                                  text=True).stdout.strip().rsplit(":", 1)[1]
        except (OSError, subprocess.SubprocessError) as e:
            pytest.skip(f"Account tests need Postgres: set TEST_DATABASE_URL or make Docker available ({e})")
        url = f"postgresql://postgres:test@127.0.0.1:{port}/fedwind_test"
        for _ in range(60):
            try:
                psycopg.connect(url, connect_timeout=2).close()
                break
            except psycopg.OperationalError:
                time.sleep(0.5)
    yield url
    if container:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


@pytest.fixture
def db_client(data_dir, pg_url, monkeypatch):
    """API client on an empty, migrated database (no dependency overrides)."""
    import psycopg

    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")  # TestClient talks plain http
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    from app.db import migrate
    from main import app

    migrate()
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


def write_finished_run(data_dir: Path, run_id: str = "wind-fedavg-h72-20261101T000000Z", horizon: int = 72,
                       energy_type: str = "wind"):
    folder = data_dir / "runs" / run_id
    (folder / "checkpoints").mkdir(parents=True)
    sites = "[konaev, saran]" if energy_type == "solar" else "[almaty, aktau]"
    (folder / "config.yaml").write_text(
        f"run_id: {run_id}\nenergy_type: {energy_type}\nstrategy: fedavg\nhorizon: {horizon}\nrounds: 2\n"
        f"sites: {sites}\n"
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
