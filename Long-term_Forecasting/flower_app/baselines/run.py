"""
Run baselines on the lab sites and write results comparable with the federated runs (FR-19, FR-20).

  cd Long-term_Forecasting/flower_app
  python -m baselines.run --energy wind --horizon 72 --data-root ~/fedwind-demo-data/sites
  python -m baselines.run --energy solar --horizon 72 --methods persistence,arima,lstm_fedavg --seed 1
  python -m baselines.run ... --data-percent 10 --test-stride 24      # quick check

Each method writes  results/baselines/<energy>_h<horizon>_<method>_seed<seed>.json  with the same
per-site and overall metrics as a federated run's result.json (run_logging.site_summary), and one
line per site and method is appended to  results/baselines/summary.csv.

Data: <data-root>/<site>/nasa_<site>.csv (the files the lab clients mount) or <data-root>/nasa_<site>.csv. Model settings (input
length, horizon, LLM layers, LoRA rank) come from the same run-config keys as federated runs, so a
baseline and a federated run with the same values are comparable.
"""

import argparse
import csv
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from baselines.data import load_site
from baselines.methods import METHODS, TrainSettings
from baselines.metrics import client_metrics
from my_flower_app.experiment import build_model_configs, seed_everything
from my_flower_app.run_logging import overall_real, site_summary
from my_flower_app.solar import options as solar_options

SITES = {"wind": ["almaty", "zhezkazgan", "aktau", "taraz", "aktobe"],
         "solar": ["konaev", "shymkent", "kyzylorda", "saran", "turkistan"]}
DEFAULT_METHODS = "persistence,arima,lstm_local,lstm_central,lstm_fedavg,patchtst_local,patchtst_central"


def run_config(args) -> dict:
    solar = args.energy == "solar"
    rc = {"pred-len": args.horizon, "seq-len": args.seq_len, "model": args.model, "llm-layers": args.llm_layers,
          "lora-r": args.lora_r, "is-pretrained": not args.random_backbone, "energy-type": args.energy,
          "dataset-name": "KZSOLAR" if solar else "KZMET", "target-column": "KSTAR" if solar else "WS50M"}
    if solar:
        rc.update({"solar-target": args.solar_target, "daylight-mask": True})
    return rc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--energy", choices=["wind", "solar"], default="wind")
    p.add_argument("--horizon", type=int, default=72)
    p.add_argument("--seq-len", type=int, default=336)
    p.add_argument("--sites", default="", help="comma-separated (default: the five lab sites of the energy type)")
    p.add_argument("--data-root", default=os.environ.get("FEDWIND_DATA", str(Path.home() / "fedwind-demo-data"))
                   + "/sites")
    p.add_argument("--methods", default=DEFAULT_METHODS, help=f"comma-separated from: {', '.join(METHODS)}")
    p.add_argument("--seed", type=int, default=2021)
    p.add_argument("--data-percent", type=int, default=100, help="share of each site's train part (quick runs)")
    p.add_argument("--test-stride", type=int, default=1, help="keep every n-th test window (quick runs)")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--local-epochs", type=int, default=2)
    p.add_argument("--lr", type=float, default=1e-3, help="LSTM / PatchTST (LLM baselines use --llm-lr)")
    p.add_argument("--llm-lr", type=float, default=1e-4)
    p.add_argument("--batch-size", type=int, default=256, help="LSTM / PatchTST")
    p.add_argument("--llm-batch-size", type=int, default=32,
                   help="LLM baselines (train and eval; GPT-2 over 336 h windows needs a GPU or small batches)")
    p.add_argument("--arima-order", default="2,0,1")
    p.add_argument("--arima-fit-hours", type=int, default=24 * 365)
    p.add_argument("--model", default="gpt4ts_linear")
    p.add_argument("--llm-layers", type=int, default=2)
    p.add_argument("--lora-r", type=int, default=8)
    p.add_argument("--random-backbone", action="store_true", help="LLM baselines without GPT-2 weights (tests)")
    p.add_argument("--solar-target", choices=["kstar", "ghi"], default="kstar")
    p.add_argument("--out", default="results/baselines")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seed_everything(args.seed)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    rc = run_config(args)
    cfg = build_model_configs(rc)
    solar = solar_options(rc)
    names = [s for s in (args.sites.split(",") if args.sites else SITES[args.energy]) if s]
    sites = [load_site(n, cfg, rc["dataset-name"], site_file(Path(args.data_root), n), solar,
                       args.data_percent, args.test_stride) for n in names]
    logging.info("%d sites, %s windows in test", len(sites), [len(s.test.x) for s in sites])

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = out_dir / "summary.csv"
    fields = ["finished_at", "energy", "horizon", "method", "seed", "site", "mae", "rmse", "nmae", "skill_vs_persistence",
              "power_nmae", "power_nrmse", "skill_h1", "skill_h6", "skill_h24", "train_s", "data_percent", "test_stride"]
    new_file = not summary.exists()
    for method in [m.strip() for m in args.methods.split(",") if m.strip()]:
        if method not in METHODS:
            raise SystemExit(f"unknown method {method}; choose from {', '.join(METHODS)}")
        llm = method.startswith("llm_")
        bs = args.llm_batch_size if llm else args.batch_size
        settings = TrainSettings(epochs=args.epochs, lr=args.llm_lr if llm else args.lr, batch_size=bs,
                                 eval_batch_size=bs if llm else 1024, rounds=args.rounds, local_epochs=args.local_epochs)
        seed_everything(args.seed)
        start = time.time()
        preds = METHODS[method](sites, cfg=cfg, settings=settings, device=device,
                                arima_order=tuple(int(v) for v in args.arima_order.split(",")),
                                arima_fit_hours=args.arima_fit_hours)
        took = time.time() - start
        per_site = {s.site: site_summary(client_metrics(s, preds[s.site]), solar is not None) for s in sites}
        result = {
            "method": method, "energy_type": args.energy, "horizon": args.horizon, "seed": args.seed,
            "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "train_s": round(took, 1),
            "settings": {**vars(args), "run_config": rc},
            "metrics": {"real": overall_real(per_site, solar is not None), "per_site": per_site,
                        "reference": ("smart persistence, RMSE skill, daylight hours" if solar
                                      else "persistence (last value), MAE skill")},
        }
        path = out_dir / f"{args.energy}_h{args.horizon}_{method}_seed{args.seed}.json"
        path.write_text(json.dumps(result, indent=2, default=float))
        with open(summary, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if new_file:
                w.writeheader()
                new_file = False
            for site, m in [*per_site.items(), ("mean", result["metrics"]["real"])]:
                lead = m.get("by_lead", {})
                w.writerow({"finished_at": result["finished_at"], "energy": args.energy, "horizon": args.horizon,
                            "method": method, "seed": args.seed, "site": site,
                            **{k: _fmt(m.get(k)) for k in ("mae", "rmse", "nmae", "skill_vs_persistence",
                                                           "power_nmae", "power_nrmse")},
                            **{f"skill_h{h}": _fmt(lead.get(str(h), {}).get("skill")) for h in (1, 6, 24)},
                            "train_s": round(took, 1), "data_percent": args.data_percent,
                            "test_stride": args.test_stride})
        real = result["metrics"]["real"]
        logging.info("%s: MAE %.3f, skill %s (%.0f s) -> %s", method, real["mae"] or float("nan"),
                     _fmt(real["skill_vs_persistence"]), took, path)
    return 0


def site_file(root: Path, site: str) -> str:
    """<root>/<site>/nasa_<site>.csv (the lab clients' layout) or <root>/nasa_<site>.csv (a flat folder,
    e.g. Long-term_Forecasting/datasets/custom)."""
    for path in (root / site / f"nasa_{site}.csv", root / f"nasa_{site}.csv"):
        if path.is_file():
            return str(path)
    raise SystemExit(f"no data for {site}: expected {root / site / f'nasa_{site}.csv'} or {root / f'nasa_{site}.csv'}")


def _fmt(v):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 5)


if __name__ == "__main__":
    raise SystemExit(main())
