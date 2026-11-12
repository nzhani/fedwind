import json

import torch

from my_flower_app.run_logging import RunLogger

SITES = ["almaty", "zhezkazgan", "aktau"]


def logger(tmp_path, selected=None):
    rc = {"runs-dir": str(tmp_path), "run-id": "r1", "pred-len": 72}
    return RunLogger.from_run_config(rc, SITES, selected or [])


def test_inactive_without_run_id():
    assert RunLogger.from_run_config({"runs-dir": "", "run-id": ""}, SITES, []) is None


def test_round_line_marks_dropped_and_maps_sites(tmp_path):
    lg = logger(tmp_path, ["almaty", "aktau"])
    train = {0: {"num-examples": 100, "train_loss": 0.5, "partition-id": 0}}
    ev = {0: {"val_loss": 0.3, "val_mae": 0.4, "val_rmse": 0.5, "val_mae_real": 1.2, "val_rmse_real": 1.5}}
    lg.round(1, 3, 12.0, train, ev, 1000, 1000)
    line = json.loads((tmp_path / "r1" / "metrics.jsonl").read_text().splitlines()[0])
    assert line["round"] == 1 and line["val"]["mae"] == 0.4 and line["val_real"]["mae"] == 1.2
    assert {c["site"]: c["status"] for c in line["clients"]} == {"almaty": "replied", "aktau": "dropped"}


def test_checkpoint_round_trip(tmp_path):
    lg = logger(tmp_path)
    path = lg.checkpoint("best.pt", {"w": torch.ones(2)}, 3, {"mae": 0.1})
    ckpt = torch.load(path)
    assert ckpt["round"] == 3 and ckpt["run_config"]["pred-len"] == 72
    assert torch.equal(ckpt["trainable_state"]["w"], torch.ones(2))


def test_result_real_units_and_skill(tmp_path):
    lg = logger(tmp_path)
    best_eval = {
        0: {"test_mae": 0.2, "test_rmse": 0.3, "test_mae_real": 1.0, "test_rmse_real": 1.5,
            "test_mean_real": 5.0, "persistence_mae_real": 2.0},
        2: {"test_mae": 0.4, "test_rmse": 0.5, "test_mae_real": 2.0, "test_rmse_real": 2.5,
            "test_mean_real": 10.0, "persistence_mae_real": 2.0},
    }
    res = lg.result(2, best_eval, 100.0, 4, 1000, 10_000, False)
    assert res["status"] == "done" and res["best_round"] == 2 and res["horizon"] == 72
    assert res["metrics"]["per_site"]["almaty"] == {"mae": 1.0, "rmse": 1.5, "nmae": 0.2, "nrmse": 0.3,
                                                    "persistence_mae": 2.0, "skill_vs_persistence": 0.5}
    assert res["metrics"]["real"]["mae"] == 1.5 and res["metrics"]["real"]["skill_vs_persistence"] == 0.25
    assert json.loads((tmp_path / "r1" / "result.json").read_text())["status"] == "done"


def test_failed_result(tmp_path):
    lg = logger(tmp_path)
    lg.failed(RuntimeError("boom"))
    res = json.loads((tmp_path / "r1" / "result.json").read_text())
    assert res["status"] == "failed" and "boom" in res["error"]


def test_nan_becomes_null(tmp_path):
    lg = logger(tmp_path)
    lg.round(1, 1, 1.0, {0: {"num-examples": 1, "train_loss": float("nan")}}, {}, None, None)
    line = json.loads((tmp_path / "r1" / "metrics.jsonl").read_text())
    assert line["train_loss"] is None
