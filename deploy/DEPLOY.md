# Deploying FedWind on the lab GPU server

Everything runs from one Compose project: the web app, the API, Postgres, the Flower
SuperLink, one client container per wind site and one inference container per site.

```
web ─► api ─► db
        │  flwr run / stop / ls          (control API superlink:9093)
        ▼
     superlink  ◄── fleet API :9092 ──  client-almaty  client-zhezkazgan  client-aktau  client-taraz  client-aktobe   (GPU)
        │ writes data/runs/<run_id>/                     each mounts only data/sites/<site>
     api ─► inference-<site> (CPU)                       reads data/sites/<site> + data/models
```

## 0. What the server needs

- Docker Engine with Compose v2 (`docker compose version`)
- NVIDIA driver, plus the NVIDIA Container Toolkit so containers can use the GPUs. Check with:
  ```bash
  docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
  ```
- About 25 GB of disk (images ≈ 12 GB with CUDA torch, GPT-2 cache 0.6 GB, data 0.05 GB, runs)
- Ports for the browser: 3000 (web) and 8001 (API), or others set in `.env`

## 1. Copy the project

The work isn't committed yet. Either commit and clone on the server, or copy the folder:

```bash
rsync -a --exclude node_modules --exclude .venv --exclude .next ~/fedwind/ USER@SERVER:~/fedwind/
```

`deploy/data/` already holds the wind data (`sites/<site>/nasa_<site>.csv`, 2015–2024) and
the GPT-2 weights (`hf-cache/`). If you copy the folder they come along. Without them, on
the server:

```bash
python3 Long-term_Forecasting/scripts/download_kzmet.py     # needs internet (NASA POWER)
deploy/scripts/prefetch_models.sh                           # after the image is built (step 3)
```

## 2. Configure `deploy/.env`

```bash
cp deploy/.env.example deploy/.env
```

Set:
- `POSTGRES_PASSWORD`: any random value.
- `PUBLIC_WEB_URL` and `PUBLIC_API_URL`: the server's address as the browser sees it, e.g.
  `http://10.1.2.3:3000` and `http://10.1.2.3:8001`.
- `TORCH_INDEX_URL`: `https://download.pytorch.org/whl/cu128` if `nvidia-smi` shows a
  driver ≥ 570 (CUDA 12.8). Use `.../cu126` for an older driver.
- `GPU_<SITE>`: which GPU each client uses (ids from `nvidia-smi`). With one GPU leave all
  at 0. With two, for example: almaty, zhezkazgan, aktau → 0; taraz, aktobe → 1.

## 3. Build and start

```bash
docker compose -f deploy/docker-compose.yml -f deploy/compose.gpu.yml up --build -d
```

The first build downloads CUDA torch and takes a while. Then check:

```bash
docker compose -f deploy/docker-compose.yml ps
curl -s localhost:8001/api/federation          # "connected": true, "connected_nodes": 5
docker compose -f deploy/docker-compose.yml exec client-almaty python -c "import torch; print(torch.cuda.is_available())"
```

## 4. First run

1. Open `PUBLIC_WEB_URL` → **Experiments**.
2. Keep built-in data and all five sites. For a first run: 3 rounds, 1 local epoch,
   horizon 72 h, GPT-2, LLM layers 2. To check the wiring in a few minutes first, set
   **Train data used (%)** to 5 under advanced settings. Press **Start federated run**.
3. The run page shows each round as it finishes: validation error, which sites replied,
   uplink size, round time.
4. When it's **done**, press **Use for forecasts**. Then **Forecast** → pick a site and 72 h.

Each horizon (1 / 72 / 432 h) needs its own finished and promoted run before its
forecasts work.

The same can be done from a shell:

```bash
curl -s -X POST localhost:8001/api/runs -F 'config={"rounds":3,"local_epochs":1,"horizon":72,"llm_layers":2}'
curl -s localhost:8001/api/runs
curl -s -X POST localhost:8001/api/models/promote -H 'Content-Type: application/json' -d '{"run_id":"<run_id>"}'
curl -s "localhost:8001/api/forecast?site=almaty&horizon=72"
```

## 5. Payload size and GPU memory

What each client sends per round grows with the horizon, because the output head is
768 × patches × horizon (measured at 336 h input, patch 4, stride 1, GPT-2 2 layers):

| Horizon | Uplink per client per round |
|---|---|
| 1 h | 1.8 MB |
| 72 h | 74.7 MB |
| 432 h | 444 MB |

On one server that's fine for the network. GPU memory grows the same way at 432 h. If
clients sharing a GPU run out of memory, lower batch size first. Patch 16 / stride 8 cuts
432 h to 57 MB, but that's a modelling change for the team to decide (FALL_2026_PLAN.md §10).

## 6. Watching and troubleshooting

```bash
docker compose -f deploy/docker-compose.yml logs -f superlink          # server rounds
docker compose -f deploy/docker-compose.yml logs -f client-aktau       # one site's training
tail -f deploy/data/runs/<run_id>/logs/serverapp.log
nvidia-smi -l 5                                                        # GPU memory per client
```

- **CUDA out of memory** on shared GPUs: lower batch size or LLM layers, or spread
  clients over more GPUs (`GPU_<SITE>`), then `up -d` again.
- **Run fails right away**: `deploy/data/runs/<run_id>/result.json` holds the error.
- **Only one run at a time**: a second start gets "busy" (409). Stop the active run from
  its page.
- **Files in `deploy/data` owned by root**: containers run as root; `sudo chown -R $USER deploy/data` if needed.
- **Fault-tolerance test**: `deploy/scripts/kill_client.sh aktau 120` during a run with
  "Minimum sites per round" ≤ 4. The site shows as dropped and rejoins later.

## 7. Without Docker

`deploy/scripts/run_local_federation.sh` starts the SuperLink and the five SuperNodes as
plain processes from a virtualenv (same flags as Compose). Point the API at it with
`FEDERATION_ADDRESS=127.0.0.1:9093 FLWR_FEDERATION=local-deployment FLOWER_APP_DIR=<repo>/Long-term_Forecasting/flower_app`.

## Simulation mode (research scripts)

`run_flower_experiment.sh` still runs the Ray simulation engine with the
`local-simulation-N` federations. It needs `pip install "flwr[simulation]==1.25.0"`, which
the Docker image doesn't include.

## Versions

Python 3.12, torch 2.8.0, flwr 1.25.0, transformers 4.56.1, peft 0.17.1
(`deploy/flower/requirements.lock.txt`). Flower is pinned to 1.25.0 on purpose: the
latest release checked (1.43) rewrites the app's `pyproject.toml` on `flwr run` and
installs app dependencies at run time.
