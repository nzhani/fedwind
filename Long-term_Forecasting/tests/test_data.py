import numpy as np
import torch

from my_flower_app.experiment import build_model_configs
from my_flower_app.task import _client_dataset, load_client_test, persistence_errors
from tests.conftest import write_nasa_csv


def cfg(pred_len=24, seq_len=48):
    return build_model_configs({"pred-len": pred_len, "seq-len": seq_len, "is-pretrained": False})


def test_client_reads_only_its_file_and_scales_on_train(tmp_path):
    f = write_nasa_csv(tmp_path / "almaty" / "nasa_almaty.csv")
    train = _client_dataset("train", 0, cfg(), "KZMET", data_file=str(f))
    test = _client_dataset("test", 0, cfg(), "KZMET", data_file=str(f))
    # Same scaler (fit on this file's train split) for every split
    assert np.allclose(train.scaler.mean_, test.scaler.mean_)
    n = 24 * 60
    assert len(train.data_x) == int(n * 0.7)
    # Uploads without "nasa" in the name still parse as NASA POWER
    up = write_nasa_csv(tmp_path / "almaty" / "uploads" / "run-1.csv")
    assert len(_client_dataset("val", 0, cfg(), "KZMET", data_file=str(up))) > 0


def test_data_percent_limits_train_split(tmp_path):
    f = write_nasa_csv(tmp_path / "nasa_x.csv")
    full = _client_dataset("train", 0, cfg(), "KZMET", data_file=str(f), percent=100)
    part = _client_dataset("train", 0, cfg(), "KZMET", data_file=str(f), percent=10)
    assert 0 < len(part) < len(full)


def test_persistence_errors_on_constant_series_is_zero():
    x = torch.ones(4, 48, 1)
    y = torch.ones(4, 24 + 48, 1)
    mae, rmse = persistence_errors([(x, y)], pred_len=24)
    assert mae == 0 and rmse == 0


def test_persistence_errors_match_manual(tmp_path):
    f = write_nasa_csv(tmp_path / "nasa_x.csv")
    loader = load_client_test(0, bs=16, cfg=cfg(), dataset_name="KZMET", data_file=str(f))
    mae, _ = persistence_errors(loader, 24)
    xs, ys = zip(*[(b[0], b[1]) for b in loader])
    x, y = torch.cat(xs).float(), torch.cat(ys).float()[:, -24:, :]
    assert abs(mae - (x[:, -1:, :] - y).abs().mean().item()) < 1e-6
