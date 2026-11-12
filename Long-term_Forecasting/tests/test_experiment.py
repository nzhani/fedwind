import tomllib
from pathlib import Path

import pytest
import torch

from my_flower_app.experiment import build_model_configs, client_data_file, is_selected, site_names

PYPROJECT = Path(__file__).resolve().parents[1] / "flower_app" / "pyproject.toml"


def run_config(**overrides):
    cfg = dict(tomllib.loads(PYPROJECT.read_text())["tool"]["flwr"]["app"]["config"])
    cfg.update(overrides)
    return cfg


def test_pyproject_uses_pretrained_backbone():
    # Bug 1: clients train adapters on the pretrained backbone; evaluation must use the same one.
    assert run_config()["is-pretrained"] is True
    assert build_model_configs(run_config()).pretrain is True


def test_server_and_clients_build_identical_configs():
    rc = run_config(**{"pred-len": 72, "llm-layers": 2, "model": "gpt4ts_linear"})
    server, train, evaluate = (vars(build_model_configs(dict(rc))) for _ in range(3))
    assert server == train == evaluate
    assert server["pred_len"] == 72 and server["llm_layers"] == 2 and server["model"] == "gpt4ts_linear"


def test_adalora_default_is_none():
    assert build_model_configs(run_config()).adalora_total_step is None


def test_site_names_parsing():
    assert site_names({"site-names": "almaty, aktau,,"}) == ["almaty", "aktau"]
    assert site_names({}) == []


def test_client_data_file_builtin_and_upload(tmp_path):
    root = tmp_path / "almaty"
    (root / "uploads").mkdir(parents=True)
    (root / "nasa_almaty.csv").write_text("x")
    (root / "uploads" / "run-1.csv").write_text("x")
    node = {"data-root": str(root), "site": "almaty"}

    assert client_data_file(node, {"data-source": "builtin"}) == str(root / "nasa_almaty.csv")
    assert client_data_file(node, {"data-source": "upload", "run-id": "run-1"}) == str(root / "uploads" / "run-1.csv")
    with pytest.raises(FileNotFoundError):
        client_data_file(node, {"data-source": "upload", "run-id": "other"})
    # Simulation mode: no data-root, fall back to the registry
    assert client_data_file({"partition-id": 0}, {}) is None


def test_is_selected():
    assert is_selected({"site": "almaty"}, {"site-names": "almaty,aktau"})
    assert not is_selected({"site": "taraz"}, {"site-names": "almaty,aktau"})
    assert is_selected({"site": "taraz"}, {"site-names": ""})
    assert is_selected({"partition-id": 3}, {"site-names": "almaty"})  # simulation nodes have no site


def test_trainable_payload_is_adapters_and_projections_only():
    # NFR-01: only LoRA adapters + in_layer/out_layer leave the client (random backbone: no download)
    from my_flower_app.task import Net, trainable_state_dict

    cfg = build_model_configs(run_config(**{"is-pretrained": False, "model": "gpt4ts_linear", "llm-layers": 2,
                                            "pred-len": 72, "seq-len": 96}))
    net = Net(device=torch.device("cpu"), configs=cfg)
    keys = trainable_state_dict(net).keys()
    assert keys
    assert all(("lora_" in k) or ("in_layer" in k) or ("out_layer" in k) for k in keys), sorted(keys)
    sent = sum(v.numel() for v in trainable_state_dict(net).values())
    total = sum(p.numel() for p in net.parameters())
    assert sent < total
