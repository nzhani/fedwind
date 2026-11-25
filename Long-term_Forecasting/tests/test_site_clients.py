"""Plant SuperNodes (SITE_NETWORK_PLAN.md M5–M6): site-id clients, the agent's store as training data,
robust update checks, run logs keyed by site."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import torch

from my_flower_app import robust
from my_flower_app.experiment import client_data_file, client_identity, client_label, client_seed, is_selected
from my_flower_app.run_logging import RunLogger

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))  # site_agent: the store writer the plant runs


# --- who a client is ---------------------------------------------------------------------------------

def test_plant_clients_have_a_site_and_no_partition_id():
    plant = {"site": "zhanatas-1ded", "energy": "wind", "data-root": "/data/store"}
    lab = {"partition-id": 2, "num-partitions": 10, "site": "aktau", "data-root": "/data/site"}
    assert client_identity(plant) == (-1, "zhanatas-1ded") and client_label(plant) == "zhanatas-1ded"
    assert client_identity(lab) == (2, "aktau")
    assert client_seed(2021, lab) == 2023
    assert client_seed(2021, plant) == client_seed(2021, dict(plant)) != client_seed(2021, {"site": "other"})
    assert is_selected(plant, {"site-names": "almaty,zhanatas-1ded"})
    assert not is_selected(plant, {"site-names": "almaty,aktau"})


# --- the store the agent writes is what the loader reads -----------------------------------------------

def _hourly_source(energy, hours, value):
    from site_agent.sources import HourlySource

    src = HourlySource(energy)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    src.values = {t0 + timedelta(hours=i): value(i) for i in range(hours)}
    return src


def test_wind_store_loads_as_training_data(tmp_path):
    from my_flower_app.dataloader import preprocess_nasa_data
    from site_agent.store import TrainingStore

    src = _hourly_source("wind", 24 * 30, lambda i: 6.0 + (i % 24) / 10)
    src.values[datetime(2025, 1, 2, 5, tzinfo=timezone.utc)] = 99.0          # implausible: stored as -999
    TrainingStore(tmp_path, "zh-1", 43.5, 69.7).update(src)

    path = client_data_file({"site": "zh-1", "data-root": str(tmp_path / "store")}, {})
    df = preprocess_nasa_data(path, "WS50M")
    assert len(df) == 24 * 30 and df["WS50M"].between(0, 40).all()          # the bad hour was interpolated
    assert str(df["date"].iloc[0]) == "2025-01-01 00:00:00"


def test_solar_store_loads_with_its_location(tmp_path):
    from my_flower_app.solar import solar_frame
    from site_agent.store import TrainingStore

    src = _hourly_source("solar", 24 * 10, lambda i: max(0.0, 600.0 - abs((i % 24) - 7) * 120))
    TrainingStore(tmp_path, "shu-1", 43.6, 73.8).update(src)
    frame = solar_frame(str(tmp_path / "store" / "nasa_shu-1.csv"))
    assert frame.attrs["lat"] == 43.6 and frame.attrs["lon"] == 73.8
    assert len(frame) == 240 and frame["GHI"].max() == 600.0 and "KSTAR" in frame


# --- robust aggregation ---------------------------------------------------------------------------------

def test_screen_rejects_broken_and_outlying_updates():
    g = {"a": torch.zeros(4), "b": torch.zeros(2, 2)}
    ok = lambda s: {"a": torch.full((4,), s), "b": torch.full((2, 2), s)}
    states = {"almaty": ok(0.1), "aktau": ok(0.12), "taraz": ok(0.09), "plant-x": ok(10.0),
              "plant-nan": {"a": torch.tensor([0.0, float("nan"), 0, 0]), "b": torch.zeros(2, 2)},
              "plant-shape": {"a": torch.zeros(5), "b": torch.zeros(2, 2)}}
    kept, rejected = robust.screen(states, g, ratio=5.0)
    assert kept == ["almaty", "aktau", "taraz"]
    assert "median" in rejected["plant-x"] and "non-finite" in rejected["plant-nan"]
    assert "shape" in rejected["plant-shape"]
    # Two updates: no median check, finite checks still on
    kept, rejected = robust.screen({"a": ok(0.1), "b": ok(10.0)}, g, ratio=5.0)
    assert kept == ["a", "b"] and rejected == {}
    kept, _ = robust.screen(states, g, ratio=0)                                # norm check off
    assert "plant-x" in kept


def test_server_keys_clients_by_site():
    from flwr.app import ConfigRecord, MetricRecord, RecordDict
    from my_flower_app.server_app import FedAvgWithMetrics

    def msg(content, node=7):
        return SimpleNamespace(has_content=lambda: True, content=RecordDict(content),
                               metadata=SimpleNamespace(src_node_id=node))

    plant = msg({"metrics": MetricRecord({"partition-id": -1}), "client": ConfigRecord({"site": "zh-1"})})
    lab_old = msg({"metrics": MetricRecord({"partition-id": 3})})
    unknown = msg({"metrics": MetricRecord({"partition-id": -1}), "client": ConfigRecord({"site": ""})}, node=42)
    key = FedAvgWithMetrics._client_key
    assert key(plant, {"partition-id": -1}) == "zh-1"
    assert key(lab_old, {"partition-id": 3}) == 3
    assert key(unknown, {"partition-id": -1}) == "node-42"


# --- run logs -------------------------------------------------------------------------------------------

def test_round_log_by_site_with_rejected_updates(tmp_path):
    lg = RunLogger.from_run_config({"runs-dir": str(tmp_path), "run-id": "r1"}, ["almaty"],
                                   ["almaty", "zh-1", "shu-1", "plant-x"])
    train = {0: {"num-examples": 10, "train_loss": 0.5}, "zh-1": {"num-examples": 20, "train_loss": 0.4}}
    lg.round(1, 2, 5.0, train, {}, 100, 100, rejected={"plant-x": "update norm 9 is more than 5 x the round median 1"})
    line = json.loads((tmp_path / "r1" / "metrics.jsonl").read_text())
    status = {c["site"]: c["status"] for c in line["clients"]}
    assert status == {"almaty": "replied", "zh-1": "replied", "plant-x": "rejected", "shu-1": "dropped"}
    assert next(c for c in line["clients"] if c["site"] == "plant-x")["reason"].startswith("update norm")
