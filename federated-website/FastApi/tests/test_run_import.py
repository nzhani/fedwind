"""Importing a run trained elsewhere (Irgetas) into the website."""

import json

import pytest

from app.services import run_import
from app.services.accounts import AccountError
from app.settings import get_settings
from tests.conftest import write_finished_run


def outside_run(tmp_path, with_toml=True):
    """A run folder as the Flower app writes it on a cluster: no config.yaml, no run.json."""
    folder = write_finished_run(tmp_path / "cluster", "solar-fedavg-h72-irgetas1", energy_type="solar")
    (folder / "config.yaml").unlink()
    (folder / "run.json").unlink()
    result = json.loads((folder / "result.json").read_text())
    result.update(energy_type="solar", finished_at="2026-12-01T10:00:00Z",
                  metrics={"real": {"mae": 80.0, "skill_vs_persistence": 0.12},
                           "per_site": {"konaev": {"mae": 75.0}, "saran": {"mae": 85.0}}})
    (folder / "result.json").write_text(json.dumps(result))
    if with_toml:
        (folder / "run_config.toml").write_text('energy-type = "solar"\npred-len = 72\nstrategy = "fedprox"\n'
                                                'num-server-rounds = 15\nsite-names = "konaev,saran"\ndata-percent = 100\n')
    return folder


def test_imported_run_shows_up_like_our_own(client, data_dir, tmp_path):
    src = outside_run(tmp_path)
    run = run_import.import_run(get_settings(), src, note="H100, 15 rounds")
    assert run.status == "done" and run.horizon == 72 and run.strategy == "fedprox"
    assert run.sites == ["konaev", "saran"] and run.config["energy_type"] == "solar"
    listed = client.get("/api/runs").json()["runs"]
    assert any(r["run_id"] == "solar-fedavg-h72-irgetas1" for r in listed)
    detail = client.get("/api/runs/solar-fedavg-h72-irgetas1").json()
    assert detail["result"]["metrics"]["real"]["skill_vs_persistence"] == 0.12 and len(detail["history"]) == 2
    # It can serve forecasts like any finished run
    r = client.post("/api/models/promote", json={"run_id": "solar-fedavg-h72-irgetas1"})
    assert r.status_code == 200 and r.json()["energy_type"] == "solar"

    with pytest.raises(AccountError, match="already exists"):
        run_import.import_run(get_settings(), src)


def test_import_without_run_config_uses_the_result(data_dir, tmp_path):
    run = run_import.import_run(get_settings(), outside_run(tmp_path, with_toml=False), run_id="from-result")
    assert run.horizon == 72 and run.sites == ["konaev", "saran"]


def test_unfinished_or_broken_runs_are_refused(data_dir, tmp_path):
    src = outside_run(tmp_path)
    (src / "checkpoints" / "best.pt").unlink()
    with pytest.raises(AccountError, match="Checkpoint"):
        run_import.import_run(get_settings(), src)
    (src / "result.json").write_text(json.dumps({"status": "failed"}))
    with pytest.raises(AccountError, match="finished"):
        run_import.import_run(get_settings(), src)
    with pytest.raises(AccountError, match="Run id"):
        run_import.import_run(get_settings(), outside_run(tmp_path / "x"), run_id="../evil")
