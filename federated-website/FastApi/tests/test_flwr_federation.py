import json
import socket
import stat
import threading
import tomllib

import pytest

from app.services.federation_client import FlwrCliFederation, FederationUnavailable, to_run_config, write_run_config_toml
from app.services import run_store
from app.platform_schemas import ExperimentConfig
from app.settings import get_settings

FAKE_FLWR = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
with open(sys.argv[0] + ".calls", "a") as f:
    f.write(json.dumps(args) + "\n")
if args[0] == "run":
    print("notice before json")
    print(json.dumps({"success": True, "run-id": "4242"}))
elif args[:2] == ["supernode", "ls"]:
    print(json.dumps({"success": True, "nodes": [{"status": "online"}, {"status": "online"}, {"status": "offline"}]}))
elif args[0] == "ls":
    print(json.dumps({"success": True, "runs": [{"run-id": "4242", "status": "finished:completed"}]}))
elif args[0] == "stop":
    print(json.dumps({"success": False, "error-message": "run already finished"}))
    sys.exit(1)
'''


@pytest.fixture
def listener():
    """A TCP port that accepts connections, standing in for the SuperLink control API."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    stop = threading.Event()

    def loop():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                srv.accept()[0].close()
            except OSError:
                pass

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    yield f"127.0.0.1:{srv.getsockname()[1]}"
    stop.set()
    srv.close()


@pytest.fixture
def fake_flwr(tmp_path):
    path = tmp_path / "flwr"
    path.write_text(FAKE_FLWR)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def calls(fake_flwr):
    return [json.loads(l) for l in (fake_flwr.parent / "flwr.calls").read_text().splitlines()]


def test_to_run_config_maps_keys_and_sites():
    cfg = ExperimentConfig(sites=["aktau", "almaty"], horizon=432, rounds=7, min_train_clients=2).model_dump(mode="json")
    rc = to_run_config(cfg, "run-1", "/data/runs", ["almaty", "zhezkazgan", "aktau", "taraz", "aktobe"])
    assert rc["pred-len"] == 432 and rc["num-server-rounds"] == 7 and rc["strategy"] == "fedavg"
    assert rc["site-names"] == "aktau,almaty" and rc["partition-sites"].startswith("almaty,zhezkazgan")
    assert rc["runs-dir"] == "/data/runs" and rc["run-id"] == "run-1"
    assert rc["is-pretrained"] is True and rc["save-predictions"] is False and rc["dataset-name"] == "KZMET"
    assert isinstance(rc["round-timeout"], float)
    assert rc["data-percent"] == 100


def test_run_config_toml_round_trips(tmp_path):
    rc = {"a": 1, "b": 0.5, "c": True, "d": 'x "quoted"', "e": ""}
    write_run_config_toml(tmp_path / "rc.toml", rc)
    assert tomllib.loads((tmp_path / "rc.toml").read_text()) == rc


def test_start_status_state_stop(data_dir, fake_flwr, listener, tmp_path):
    settings = get_settings()
    fed = FlwrCliFederation(listener, str(tmp_path), "lab", str(fake_flwr), "/server/runs")

    status = fed.status()
    assert status.connected and status.connected_nodes == 2

    cfg = ExperimentConfig(rounds=3)
    folder = run_store.create_run(settings, "wind-fedavg-h72-x", cfg)
    assert fed.start_run("wind-fedavg-h72-x", folder / "config.yaml") == "4242"
    rc = tomllib.loads((folder / "run_config.toml").read_text())
    assert rc["runs-dir"] == "/server/runs" and rc["num-server-rounds"] == 3
    run_call = calls(fake_flwr)[-1]
    assert run_call[:3] == ["run", str(tmp_path), "lab"] and "--run-config" in run_call

    assert fed.run_state("4242") == "finished:completed"
    with pytest.raises(FederationUnavailable, match="already finished"):
        fed.stop_run("4242")


def test_unreachable_superlink(fake_flwr, tmp_path):
    fed = FlwrCliFederation("127.0.0.1:1", str(tmp_path), "lab", str(fake_flwr), "/runs")
    status = fed.status()
    assert not status.connected and "not reachable" in status.detail


def test_missing_cli(tmp_path, listener):
    fed = FlwrCliFederation(listener, str(tmp_path), "lab", str(tmp_path / "nope"), "/runs")
    with pytest.raises(FederationUnavailable, match="not found"):
        fed.stop_run("1")
