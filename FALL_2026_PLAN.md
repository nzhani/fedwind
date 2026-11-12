# FedWind — Fall 2026 implementation plan

Working plan for Claude (the coding agent) to execute across sessions. Read it fully before
starting work, follow the milestones in order, tick tasks off as they land, and add a line to
the status log at the bottom at the end of every session.

Source of truth for requirements: the team's design document
`CSCI408_Requirements_FL_LLM_Renewable_Energy_Forecasting.docx` (requirement IDs FR-xx, NFR-xx,
DR-xx below refer to it). Where this plan differs from it, this plan wins (see §2) and the
document gets updated by the team (task T5.2).

---

## 0. Rules for the agent

- **Never commit, push or open a PR unless the user asks.** The working tree already contains
  uncommitted work from an earlier session (solar skeleton, see §3.4). Never discard it.
  Before the first commit the user asks for, create a branch (e.g. `fall-2026`); don't commit on `main`.
- **Never handle passwords.** Lab-server access belongs to the user. The agent writes code,
  Compose files and scripts; the user deploys them on the lab server or sets up key-based SSH.
  No password, private key or token goes into a file, a commit or the chat. Secrets go in a
  `.env` file that is gitignored; commit only `.env.example`.
- **The lab GPU server is shared.** Cap GPU memory per container, never start more than one
  training run at a time, and stop containers that aren't needed. Ask the user before anything
  that could affect other lab users (driver changes, system packages, opening ports).
- **Laptop GPU is a GTX 1660 Ti (6 GB).** Use the laptop for development, smoke tests (1 round,
  tiny config) and as the demo fallback.
- **Keep research-code changes minimal** and limited to the tasks below. `run_flower_experiment.sh`
  and the experiment scripts must keep working (simulation mode).
- **Horizons are fixed: 1, 72, 432 hourly steps.** Nothing else in configs, API or UI.
- **Solar is frontend only this fall.** Don't implement solar training or solar inference.
- **Check Flower CLI flags against the installed version** (`flower-superlink --help`,
  `flower-supernode --help`, `flwr run --help`, `flwr ls --help`) before writing Compose files and
  launchers. The commands in this file are for Flower 1.2x and must be confirmed.
- After each task: run the relevant tests (§7). After each milestone: update §11.
- Each task has an owner from the team in brackets, which shows whose area it is. The agent may
  implement any of them when asked.

---

## 1. Goal and scope (fall 2026)

Deliver, by the end-of-semester demo (week of Dec 7–11, exact date: ask the user), a working
**federated wind forecasting system** that simulates an enterprise federation of separate data
owners, running on the lab GPU server with Docker Compose:

1. **Separated, always-on federation:** a Flower SuperLink (the aggregator) and one long-running
   client container (SuperNode) per wind site. Each client container mounts only its own site's
   data and plays one plant owner. Clients share the lab GPUs (one GPU each when there are
   enough). Later a client can move to another machine by changing the SuperLink address only.
2. **Web app on the same server** (same Compose project), driving the federation:
   - **Forecast:** energy type → site → horizon, forecast vs actual on one chart (FR-22, FR-23,
     FR-26). The forecast is computed next to the site's data by that site's inference service.
   - **Training dashboard:** current round, validation error per round, participating and
     dropped sites, updated live (FR-24). Read-only.
   - **Experiment page:** a researcher uploads one CSV per site (or picks the built-in data),
     chooses the settings and starts a run on the federation (kept from the legacy upload page,
     by user decision).
   - **Solar:** selectable in the energy-type step, marked “coming soon”, with the existing sample
     preview page. No backend.
3. **Evaluation:** baselines and FL on the same splits, metrics in real units, results tables.

Sites (from the legacy KZMET registry, NASA POWER hourly `WS50M`): Almaty, Zhezkazgan, Aktau,
Taraz, Aktobe.

---

## 2. Fixed decisions (don't revisit without the user)

| Topic | Decision | Design document says |
|---|---|---|
| Horizons | 1 / 72 / 432 hourly steps | 1 h / 6 h / 24 h (FR-06, DR-08, NFR-03) |
| Training hardware | Lab GPU server | Same |
| Site separation | Flower deployment mode: 1 SuperLink container + 1 SuperNode container per site, each mounting only its own data folder | One Docker container per site (same) |
| Hosting | Everything on the lab server in one Compose project; laptop runs the same stack for development and as demo fallback | Lab server (same) |
| Solar | Frontend only (“coming soon” + sample preview) | Full model |
| Upload page | Kept as a researcher experiment page that starts runs on the federation | Not in document |
| Run control | The API starts and stops runs through the SuperLink's control API (`flwr run` / `flwr stop`). **No job queue:** one active run at a time; a second start gets HTTP 409 | — |
| Results | The ServerApp writes run folders to a shared `runs` volume; the API reads them directly (no syncing) | — |
| Simulation mode | Kept for quick experiments from the CLI (NFR-08); not exposed on the website | Same |

---

## 3. Current state of the repo (verified facts)

### 3.1 Layout
- `Long-term_Forecasting/` — research ML core (keep):
  - `models/GPT4TS.py, LLAMA.py, BERT.py, BART.py, OPT.py, GEMMA.py, QWEN.py` — frozen LLM backbone +
    patch embedding (`in_layer`) + `out_layer`; `peft_utils.py` applies LoRA/LoHA/AdaLoRA/PFT/FFT.
  - `flower_app/my_flower_app/task.py` — `DATASET_REGISTRY` (hard-coded, KZMET at ~line 34),
    `MODEL_REGISTRY`, `get_default_configs`, `Net`, `trainable_state_dict` (:343), `train` (:360,
    FedProx term, SCAFFOLD correction), `test` (:532), client loaders (:599+).
  - `flower_app/my_flower_app/client_app.py` — `@app.train` / `@app.evaluate`.
  - `flower_app/my_flower_app/server_app.py` — strategies `FedAvgWithMetrics`, `FedProxWithMetrics`,
    `ScaffoldWithMetrics`, `StatAvgWithMetrics`, FedPer/FedLN personalisation; outer round loop in
    `main` (:526+), best-round tracking, early stopping, `final_model.pt`, `training_summary.csv`.
  - `flower_app/my_flower_app/dataloader.py` — `preprocess_nasa_data(file_path, target_column)`
    (:27), `Dataset_Custom` (StandardScaler fit on train split; split 70% train / 10% val / 20% test
    by time, matches DR-05; `inverse_transform` exists at :293).
  - `flower_app/pyproject.toml` — Flower app config and run-config defaults; federations
    `local-simulation-{1,2,3,4,5,7,10}` with `num-gpus = 1.0` per client.
  - `flower_app/run_centralized.py` — centralized training entry point.
- `federated-website/` — Next.js 15 / React 19 / Tailwind 4 / shadcn / recharts frontend:
  - `app/dashboard/page.tsx` — legacy wind upload-and-train page (~2,400 lines, also contains the
    feedback/Q&A UI).
  - `app/solar/page.tsx`, `lib/solar-api.ts`, `lib/solar-sample.ts` — solar skeleton (see 3.4).
  - `lib/api.ts` — legacy API client.
- `federated-website/FastApi/` — legacy FastAPI backend (to be rebuilt around new routers):
  - `app/services/federated_training_client.py` — runs `flwr run` as a subprocess, copies the
    upload over shared dataset files, parses CSVs.
  - `app/services/feedback_db.py` raises at import if `DATABASE_URL` is unset.
  - `app/routers/feedback.py` + `telegram_service.py` — working feedback feature (keep).
  - `.env.example` points at `/raid/tin_trungchau/...`, the previous team's paths on a lab
    server. Ask the user whether that is the server we will get.
- Root shell scripts: `run_flower_experiment.sh`, `experiments_*.sh` (paths under `/raid/...`).

### 3.2 Known bugs to fix (from code review)
1. **Critical — backbone mismatch:** `client_app.py:66` (train) defaults `is_pretrained=True`
   because the server's round config never sends it; `client_app.py:216` (evaluate) and
   `server_app.py:554` read `is-pretrained` from the run config, and `pyproject.toml:97` sets it to
   `false`. Evaluation, best-round selection and `final_model.pt` use a random GPT-2.
2. `fraction-train = 0.5` in `pyproject.toml` is never overridden by the website → ~half the
   clients train per round.
3. Metrics are computed on standardized values (no `inverse_transform` before MAE/RMSE).
4. Client loaders index `DATASET_REGISTRY[...]["files"][partition_id]`; client counts above the
   number of files crash.
5. `StatAvgWithMetrics` waits for `statavg_stats` that clients never send (behaves as FedAvg).
6. Legacy backend fabricates output: plotting MAE values as a forecast when the predictions
   file is missing; `/model-update/aggregate` returns a sine wave.
7. Legacy backend overwrites `datasets/custom/*.csv` per job (shared folder, unsafe).
8. Random init is not seeded; `random-seed` in run config is only recorded.

### 3.3 Environment facts
- `Long-term_Forecasting/datasets/` does **not** exist locally (gitignored). Data must be downloaded (T1.2).
- `Long-term_Forecasting/requirements_ss.txt` pins `flwr==1.11.1`, but the code imports
  `flwr.app`, `flwr.serverapp.strategy` (Message API from a newer Flower). The real working
  version is unknown: find it and pin it (T1.1). Root `requirements.txt` pins
  `torch==2.8.0, transformers==4.56.1, peft==0.3.0` (peft version conflicts with
  `requirements_ss.txt` `peft==0.8.2`).
- Laptop: GTX 1660 Ti 6 GB; Hugging Face reachable; no model cache yet.
- Lab GPU server: **access not confirmed yet.** Collect from the lab before M1 ends (T1.0):
  GPU count and model, free GPU memory, NVIDIA driver, Docker + Docker Compose v2 + NVIDIA
  Container Toolkit, whether long-running containers are allowed, internet access (Hugging Face,
  PyPI, NASA POWER), which port can be reached from the university network for the web app,
  disk space for the HF cache and runs.

### 3.4 Uncommitted work already in the tree (keep, build on it)
- Backend: `app/routers/solar.py` (10 `/api/solar/*` endpoints; `/health` live, rest 501),
  `app/services/solar_training_service.py` (stubs), solar schemas appended to `app/schemas.py`,
  router registered in `main.py`.
- Frontend: `/solar` page mirroring the wind dashboard, with a “Preview Sample Results” button;
  `lib/solar-api.ts`, `lib/solar-sample.ts`; Solar links in navbar and footer; dashboard badge
  and banner text changed (“Wind Forecasting”, “API Not Connected”).
- The user edited `app/solar/page.tsx` and `lib/solar-api.ts` after the agent did. **Read their
  current content before changing them.**

---

## 4. Target architecture

```
LAB GPU SERVER — docker compose (project "fedwind"), internal network, only `web` published
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  web (Next.js) ──► api (FastAPI) ──► db (Postgres: sites, runs, models, feedback)         │
│                      │  flwr run / flwr stop / flwr ls  (control API :9093)               │
│                      │  reads runs/ volume; writes per-site uploads                       │
│                      ▼                                                                    │
│                superlink  (aggregator; runs the ServerApp, writes runs/<run_id>/)         │
│                      ▲ fleet API :9092                                                    │
│      ┌───────────┬───┴───────┬───────────┬───────────┐                                   │
│  client-almaty client-zhezk. client-aktau client-taraz client-aktobe   (SuperNodes, GPU)  │
│      │ mounts only sites/<site>/ (ro) + its own outputs volume                            │
│  inference-almaty  …  inference-aktobe   (same site folder, ro; models/ ro; CPU)          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
LAPTOP: the same Compose project with a CPU/small-GPU override, for development and as the demo fallback.
```

Principles:
- One **experiment config** (§5.1) drives everything. One function turns it into the Flower
  run config. Server, client-train and client-evaluate build the model from the **same** config.
- **Sites are separated by containers:** each `client-<site>` mounts only `sites/<site>/` and gets
  its identity through `--node-config`. Only trainable parameters (LoRA adapters, `in_layer`,
  `out_layer`) and numeric metadata cross the container boundary (NFR-01).
- **The federation is always on.** Clients connect to the SuperLink at startup and wait. Starting
  a run from the website takes seconds: the API calls `flwr run` against the SuperLink.
- **No job queue.** Every client takes part in every run, so only one run can be active. The API
  holds the lock in the DB (one row with status `running`) and returns 409 for a second start.
- **Inference runs per site** (privacy boundary of the design doc): `inference-<site>` holds only
  that site's data and the registered model files.
- **Results have one format** (§5.4), written by the ServerApp into the shared `runs` volume;
  the API never parses ad-hoc CSVs and never invents numbers.
- **Only `web` is published** (and `api` if the frontend calls it directly; prefer a Next.js
  rewrite to `/api`). SuperLink and clients stay on the internal Compose network, so
  `--insecure` is acceptable this fall. TLS and node authentication come in spring, when
  clients move to other machines.

### 4.1 Volumes and data layout (on the host, under `deploy/data/`, gitignored)
```
sites/<site>/kzmet.csv              built-in data for the site (T1.2)
sites/<site>/uploads/<run_id>.csv   experiment-page upload for this site (written by api)
outputs/<site>/<run_id>/            client-side files (legacy per-client predictions)
runs/<run_id>/                      run folder (§5.2), written by the ServerApp in superlink
models/wind/h<horizon>/current.pt   promoted checkpoints, read by inference-<site>
hf-cache/                           Hugging Face cache shared read-only by model containers
```
Mounts: `client-<site>` → `sites/<site>` (ro), `outputs/<site>` (rw), `hf-cache` (ro).
`inference-<site>` → `sites/<site>` (ro), `models` (ro), `hf-cache` (ro). `superlink` → `runs`
(rw), `hf-cache` (ro). `api` → `runs` (rw), `models` (rw), `sites` (rw, uploads only).
The API sees every site folder because it stands in for the plant owners uploading their own
files; it never reads site data for training.

### 4.2 GPU assignment
`client-<site>` gets a GPU through Compose device reservations, set from `.env`
(e.g. `GPU_ALMATY=0`). With fewer GPUs than sites, clients share a GPU; keep `llm_layers` 2–4,
`batch_size` modest and set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. The superlink
gets a GPU only if server-side evaluation needs it (check in T1.5). Inference runs on CPU.

New files and folders (proposed):
```
FALL_2026_PLAN.md                         this file
configs/                                  experiment configs (YAML), e.g. wind_fedavg_h72.yaml
deploy/
  docker-compose.yml                      web, api, db, superlink, client-<site>, inference-<site>
  compose.lab.yml                         GPU reservations, published port (lab server)
  compose.laptop.yml                      CPU / single small GPU, tiny defaults (laptop)
  .env.example                            ports, GPU ids, DB password placeholder
  flower/Dockerfile                       one image: CUDA torch + pinned deps + flwr + the Flower app
  flower/requirements.lock.txt            frozen versions
  seed/sites.json                         site registry seed (wind sites + solar placeholders)
  scripts/prefetch_models.sh              fill hf-cache (gpt2) once
  scripts/kill_client.sh                  fault-tolerance test (stop one client mid-round)
Long-term_Forecasting/
  scripts/download_kzmet.py               NASA POWER downloader
  flower_app/datasets.yaml                dataset registry as data (replaces hard-coded dict)
  flower_app/my_flower_app/experiment.py  config schema + to_run_config + build_model_configs
  flower_app/my_flower_app/run_logging.py metrics.jsonl / result.json / checkpoint writers
  flower_app/baselines/                   persistence, ARIMA, LSTM runners
  tests/                                  pytest for ML core
inference/                                per-site inference service (FastAPI)
federated-website/FastApi/app/routers/{sites,forecast,runs}.py
federated-website/FastApi/app/services/{registry,inference_client,flower_control,run_store}.py
federated-website/FastApi/Dockerfile
federated-website/Dockerfile
federated-website/FastApi/tests/
federated-website/app/forecast/  app/training/  app/experiments/   new pages
```

---

## 5. Contracts

### 5.1 Experiment config (`configs/*.yaml`, FR-18)
```yaml
run_id: auto                 # auto → "<energy>-<strategy>-h<horizon>-<UTC timestamp>"
energy_type: wind            # only wind this fall
dataset: kzmet
data_source: builtin         # builtin → sites/<site>/kzmet.csv | upload → sites/<site>/uploads/<run_id>.csv
sites: [almaty, zhezkazgan, aktau, taraz, aktobe]
mode: federated              # federated | centralized | local
engine: deployment           # deployment (Compose federation) | simulation (CLI only)
strategy: fedavg             # fedavg | fedprox | scaffold | fedper | fedln  (statavg hidden, bug 5)
proximal_mu: 0.01            # fedprox only
rounds: 20
local_epochs: 2
fraction_train: 1.0
min_train_clients: 4         # FR-13
round_timeout_s: 900
horizon: 72                  # 1 | 72 | 432
seq_len: 336
model: gpt4ts_linear
llm_layers: 2
peft_method: lora
lora_r: 8
lora_alpha: 16
is_pretrained: true          # one value, read everywhere (bug 1)
lr: 1.0e-4
weight_decay: 0.01
warmup_rounds: 3
batch_size: 64
dropout: 0.2
seed: 2021
checkpoint_every: 5
resume_from: null            # path to a checkpoint (FR-14)
```
Validation (pydantic, in `experiment.py`): horizon ∈ {1, 72, 432}; strategy in the list; `sites`
exist in the dataset registry; `min_train_clients ≤ len(sites)`; `energy_type == "wind"`.
`sites` must match the clients that are connected (the API checks with the registry; FR-13
handles clients that drop during a run).

### 5.2 Run folder (`runs/<run_id>/`)
```
config.yaml
logs/serverapp.log              (client logs: `docker compose logs client-<site>`)
metrics.jsonl                   one line per finished round (5.3)
checkpoints/round_0005.pt ...   trainable state + config hash
result.json                     final result (5.4); its presence = run finished OK
```
Uploaded CSVs are not in the run folder; they stay in each site's folder (§4.1).

### 5.3 `metrics.jsonl` (one JSON object per line, written by the server after every round; FR-21, FR-24)
```json
{"round": 3, "total_rounds": 20, "finished_at": "2026-11-17T10:22:01Z", "duration_s": 84.2,
 "train_loss": 0.41,
 "val": {"mse": 0.31, "mae": 0.42, "rmse": 0.55},
 "val_real": {"mae": 1.21, "rmse": 1.63, "unit": "m/s"},
 "clients": [
   {"site": "almaty", "status": "replied", "num_examples": 6100, "train_loss": 0.39, "val_mae": 0.40},
   {"site": "aktau", "status": "dropped"}
 ],
 "uplink_bytes": 1830000, "downlink_bytes": 1830000}
```
Clients report their `partition-id` as a number (Flower metric values are numeric); the server
maps it to the site name using the config's `sites` list.

### 5.4 `result.json`
```json
{"run_id": "...", "status": "done", "best_round": 14, "horizon": 72, "unit": "m/s",
 "metrics": {"normalized": {"mae": 0.38, "rmse": 0.51},
             "real": {"mae": 1.10, "rmse": 1.49, "nmae": 0.16, "nrmse": 0.21, "skill_vs_persistence": 0.22},
             "per_site": {"almaty": {"mae": 1.02, "rmse": 1.37, "skill_vs_persistence": 0.25}}},
 "model": {"checkpoint": "checkpoints/best.pt", "config_hash": "..."},
 "timing": {"total_s": 1840, "mean_round_s": 92},
 "payload": {"uplink_bytes_per_client_round": 1830000, "backbone_bytes": 497000000}}
```
On any failure the ServerApp writes `{"status": "failed", "error": "..."}` instead. Never fill
gaps with placeholder numbers.

### 5.5 Checkpoint (`.pt`)
`{"trainable_state": <state dict of trainable params only>, "run_config": <Flower run config>,
"round": int, "metrics": {...}}`. The inference service rebuilds `Net` from `config` (with the
pretrained backbone) via `experiment.build_model_configs(run_config)` and loads
`trainable_state` with `strict=False`.

### 5.6 Flower wiring (confirm flags against the pinned version)
- `superlink`: `flower-superlink --insecure` (ServerAppIo :9091, Fleet :9092, Control :9093).
- `client-<site>`: `flower-supernode --insecure --superlink superlink:9092 --node-config
  "partition-id=<i> num-partitions=5 site='<site>' data-root='/data'"`.
  The client loader reads `<data-root>/kzmet.csv` or `<data-root>/uploads/<run_id>.csv`
  depending on `data_source` in the run config.
- Federation `lab` in `pyproject.toml` (or Flower's config file, depending on version):
  `address = "superlink:9093"`, `insecure = true`. The `api` image contains `flwr` and the
  Flower app source (no torch needed) to call `flwr run . lab --run-config <file>`.
- The ServerApp and ClientApps run as subprocesses inside the superlink and client containers,
  so the Flower image needs every training dependency.

### 5.7 REST API
| Method | Path | Purpose | Errors |
|---|---|---|---|
| GET | `/health` | status of api, db, superlink (reachable) and connected clients | — |
| GET | `/api/sites?energy_type=wind` | sites: `id, name, energy_type, lat, lon, timezone, capacity_kw, status, connected` | 422 unknown energy type |
| GET | `/api/forecast?energy_type=wind&site=almaty&horizon=72[&as_of=ISO]` | FR-22 | 422 unknown site / horizon ∉ {1,72,432}; 501 `energy_type=solar` (“solar forecasting is not available yet”); 503 no registered model or site inference down |
| GET | `/api/runs` | run list | — |
| GET | `/api/runs/{run_id}` | status, round, total, history (from metrics.jsonl), clients, result | 404 |
| POST | `/api/runs` | experiment page: config fields + optional one CSV per site | 422 bad CSV columns / config; 409 a run is active; 503 superlink unreachable or too few clients connected |
| POST | `/api/runs/{run_id}/stop` | stop the active run (`flwr stop`) | 404; 409 not running |
| POST | `/api/models/promote` | make a finished run's best checkpoint current for (energy_type, horizon) | 404; 409 run not done |
| * | `/api/solar/*` | existing skeleton, stays 501 except `/health` | — |
| * | `/api/feedback/*` | legacy feedback, kept | — |

Run status: `queued → running → done | failed | stopped`. The API stores the Flower run id
and derives the status from `flwr ls` plus `result.json`. On API start, it reconciles any run
left `running` (e.g. after a restart).

Forecast response:
```json
{"energy_type": "wind", "site": "almaty", "horizon": 72, "unit": "m/s", "as_of": "2024-06-01T00:00:00Z",
 "model": {"run_id": "...", "kind": "global"},
 "actual":   [{"timestamp": "...", "wind_speed": 6.1}],
 "forecast": [{"timestamp": "...", "wind_speed": 6.4, "wind_power_kw": 820.0}]}
```
`as_of` defaults to a fixed date inside the test split, so actual values exist after the issue
time and the chart can show forecast vs actual (FR-23). History is only data before `as_of` (DR-04).

---

## 6. Milestones

Week dates assume the demo is in the week of Dec 7–11. Confirm with the user. Everything in M1–M2
can be built and tested on the laptop with tiny configs; the lab server is needed for the real
runs (T1.6, T2.6, T4.4) and the demo.

### 6.0 Build order (user decision, 2026-11-05): application first, connect later
The lab part is skipped for now. Build two tracks that meet only through the contracts in §5:

- **Track A — application (now):** API (`/api/sites`, `/api/runs`, `/api/forecast`,
  `/api/models/promote`), web pages (Forecast, Training, Experiments) and Compose for
  `web`/`api`/`db`. The API talks to the federation and to inference only through two adapters:
  `FederationClient` (start/stop/status of runs) and `InferenceClient` (per-site forecast). Until
  they are connected, both report "not connected" and the API answers 503 with that message; it
  never invents runs or forecasts. The run store reads whatever run folders exist in `runs/`, so
  the dashboard works as soon as any real run folder appears.
  Tasks: T1.7, T1.8, T1.9, API parts of T3.5, T3.6, T3.7, T4.2, T4.3, adapter interfaces of T4.1.
- **Track B — training (later, separately):** T1.0–T1.6, M2, T3.1–T3.4 (inference service), T4.4.
- **Connect:** implement `FlwrCliFederation` (the `flwr` CLI against the SuperLink, §5.6) and
  `HttpInferenceClient` (`http://inference-<site>:8000`), set their env vars, run the end-to-end
  flow. No API or frontend changes should be needed.

Run records live as files in `runs/<run_id>/` (`run.json` written by the API next to the
ServerApp's files); Postgres stays for feedback. Revisit only if listing runs gets slow.

### M1 — Foundations (Nov 9–13)
- [ ] **T1.0 Lab server access** [Nurbol]: ask the lab for access and the facts in §3.3. Record
  them in §3.3. If Docker with GPU support is missing, tell the user at once (it changes T1.5).
- [x] **T1.1 Flower image** (2026-11-05; flwr pinned to 1.25.0, Python 3.12, torch 2.8.0; `deploy/flower/Dockerfile`, CUDA index chosen by `TORCH_INDEX_URL`) [Nursultan]: `deploy/flower/Dockerfile` (CUDA base matching the lab
  driver, Python 3.11, torch, transformers, peft, flwr, the Flower app). Find the Flower version
  that provides `flwr.serverapp.strategy` and works with the code; resolve the `peft` conflict;
  write `requirements.lock.txt`. `deploy/scripts/prefetch_models.sh` fills `hf-cache` with `gpt2`.
  *Done:* in the container, `python -c "import flwr, peft, transformers"` works and GPT-2 loads
  with `HF_HUB_OFFLINE=1`; `torch.cuda.is_available()` is true on a GPU host.
- [x] **T1.2 Wind data** (2026-11-05; 2015-2024 UTC, city-centre coordinates; files are `nasa_<site>.csv` so the NASA parser is used) [Aisha]: `scripts/download_kzmet.py` fetches NASA POWER hourly
  (`community=RE`, parameters `WS50M` plus `WD50M, T2M, PS` for FR-01), years 2015–2024 (split into
  per-year requests if the API limits range), UTC time standard if the API supports it (verify;
  DR-09), and writes `deploy/data/sites/<site>/kzmet.csv` in the format `preprocess_nasa_data`
  parses. Ask the user for the previous team's exact coordinates; else use city-centre coordinates
  and record them in `deploy/seed/sites.json`. Add `datasets/CATALOGUE.md` (source, licence,
  citation; DR-10). *Done:* five CSVs load through `Dataset_Custom` with target `WS50M`.
- [x] **T1.3 One config, read everywhere (bug 1, bug 8)** (2026-11-05; `experiment.build_model_configs`, tests in `Long-term_Forecasting/tests`) [Kanat]: add `experiment.py` with
  the config model (§5.1), `to_run_config()`, and `build_model_configs(run_config)`. Use
  `build_model_configs(context.run_config)` in `server_app.main`, `client_app.train` and
  `client_app.evaluate`. Keep only `lr`, `server_round`, `proximal_mu` in the per-round message.
  Set `is-pretrained = true` in `pyproject.toml`. Seed `random`, `numpy`, `torch` from
  `random-seed` at client and server start. *Done:* unit test shows all three paths build identical
  configs; a debug run logs the same backbone weight checksum in train and evaluate.
- [x] **T1.4 Data from node config + registry as data (bug 4)** (2026-11-05; `data-root` + `site` node config; registry stays in task.py) [Aisha/Kanat]: move
  `DATASET_REGISTRY` to `flower_app/datasets.yaml` (keep a Python fallback for old datasets);
  client loaders read `context.node_config["data-root"]` plus `data_source` when present, else
  the registry entry by `partition-id` (simulation mode). *Done:* a client container can only
  open its own site's files.
- [x] **T1.5 Compose federation** (2026-11-05; plus `compose.gpu.yml` and `deploy/scripts/run_local_federation.sh` for no-Docker hosts) [Nursultan]: in `deploy/docker-compose.yml` add `superlink`
  and `client-<site>` ×5 from the Flower image with the wiring in §5.6, mounts in §4.1, health
  checks, `restart: unless-stopped`; `compose.lab.yml` adds GPU reservations from `.env` (§4.2);
  `compose.laptop.yml` runs clients on CPU or the single GPU with tiny defaults. Add federation
  `lab` to the Flower app. *Done:* `docker compose up superlink client-almaty …` shows five
  connected nodes, and `flwr run . lab` with a 3-round config finishes with five separate client logs.
- [ ] **T1.6 Reference run** [Kanat]: after T1.3–T1.5, run `configs/reference_h72.yaml` (3 rounds,
  `llm_layers: 2`) in both engines on the lab server; save `result.json` files under `reference/`
  for regression checks.
- [x] **T1.7 Web stack in Compose** (2026-11-05; API published on :8001 for now, rewrite later) [Nurbol]: add `web` (Next.js Dockerfile), `api` (FastAPI
  Dockerfile, `DATABASE_URL` → `db`), `db` (Postgres 16, volume) to the same Compose file. Fix the
  backend so it starts with the DB from Compose. Next.js rewrites `/api/*` to `api`.
  *Done:* `docker compose up` serves the site and `/health`.
- [x] **T1.8 Site registry** (2026-11-05; served from the seed file, not Postgres; `connected` not yet) [Nursultan]: Postgres table `sites`, seeded from `deploy/seed/sites.json`
  (5 wind sites active; solar entries with `status: "coming_soon"`); `GET /api/sites`, with
  `connected` from the SuperLink's node list where the Flower version exposes it (else omit).
- [x] **T1.9 Forecast flow skeleton** (2026-11-05) [Nurbol]: new page `app/forecast/page.tsx`: step 1 energy
  type (Wind; Solar disabled, “coming soon”, links to `/solar`), step 2 site (from `/api/sites`),
  step 3 horizon (1 / 72 / 432). Navbar: Home, Forecast, Training, Experiments, then the info pages.

**M1 done when:** the whole stack comes up with one `docker compose up`, five clients connect,
a 3-round separated run finishes with the fixed config, and the web app lists the five wind sites.

### M2 — First federated results (Nov 16–20)
- [x] **T2.1 Per-round metrics** (2026-11-05; `run_logging.py`; uplink/downlink are per client) [Nursultan]: `run_logging.py`; the server appends a `metrics.jsonl`
  line after every round (§5.3) into `runs/<run_id>/`, including dropped clients and
  uplink/downlink bytes; clients add `partition-id` to their metrics. Pass `fraction_train=1.0`
  and `min_train_nodes` / `min_available_nodes` from the config to the strategy (bug 2, FR-13).
- [x] **T2.2 Checkpoints and resume** (2026-11-05; checkpoint key is `run_config` (not `config`)) [Nursultan]: save `checkpoints/round_NNNN.pt` every
  `checkpoint_every` rounds and `best.pt` (§5.5); `resume_from` restarts from a checkpoint (FR-14).
- [x] **T2.3 Real units and baselines in metrics** (2026-11-05; persistence on clients; nMAE divides by mean observed test speed per site) [Kanat]: in `test()`, apply the loader dataset's
  `inverse_transform` to predictions and truths (reshape to 2-D for the scaler), report MAE/RMSE in
  m/s plus normalized values; compute nMAE/nRMSE (divide by mean observed speed of the test split;
  write the choice in the results doc) and skill vs persistence (last observed value repeated over
  the horizon; DR-07). Write `result.json` at the end (§5.4); failures write `status: failed` (bug 6 for the ML side).
- [ ] **T2.4 Payload audit test** [Nursultan]: pytest: keys of `trainable_state_dict` are only
  LoRA/`in_layer`/`out_layer` params; message contents hold no data tensors; record uplink size vs
  full backbone size (NFR-01, NFR-02). **Check NFR-02 at horizon 432:** `out_layer` is
  `d_model × patch_num × pred_len` and may exceed 5% of the GPT-2 size. Measure, and if it does,
  report to the user with options (smaller projection, fewer patches, or a documented exception).
- [ ] **T2.5 Baselines** [Nurbol]: `flower_app/baselines/`: persistence, ARIMA (statsmodels), LSTM,
  local-only (same LLM model trained per site), centralized (`run_centralized.py`), all on the same
  splits and horizons (FR-19, DR-05). PatchTST: the legacy registry expects a `BASELINES/` folder
  that isn't in the repo; implement it or ask the team. Baselines run as one-off containers from
  the Flower image (`docker compose run --rm`), one at a time, not while a federated run is active.
- [ ] **T2.6 First experiments** [Aisha/Kanat]: FedAvg and FedProx, horizons 1/72/432, 3 seeds, on
  the lab federation (one run at a time; a small script submits them in sequence via `flwr run`);
  table `results/fall_prelim.csv` (mean ± std per site and overall).
- [ ] **T2.7 Remove fabricated outputs (bug 6)** [Nursultan]: delete the MAE-as-forecast fallback and
  make `/model-update/aggregate` return 501 or remove it.

**M2 done when:** a results table compares FL with the baselines for at least horizon 72.

### M3 — Forecasts in the web app (Nov 23–27)
- [x] **T3.1 Run store and model registry** (2026-11-05; reads the shared runs volume directly) [Nursultan]: `run_store.py` reads `runs/` (the shared
  volume) into Postgres tables `runs` and `models` (on API start and on each status request);
  `POST /api/models/promote` copies a finished run's `best.pt` to
  `models/wind/h<horizon>/current.pt` and records it. Inference services reload on change
  (file mtime) or on a `POST /reload`.
- [x] **T3.2 Inference service** (2026-11-05; `inference/app.py`) [Nurbol]: `inference/` FastAPI app from the Flower image, env
  `SITE_ID`, mounts per §4.1. `POST /forecast {horizon, as_of}` builds `Net` from the checkpoint
  config with the pretrained backbone, loads the trainable state, takes the `seq_len` window before
  `as_of`, inverse-transforms with the site's scaler (fit on the site's train split, same as
  training), and returns speed plus power. Keep models in memory; CPU by default (NFR-03: < 5 s; measure).
- [x] **T3.3 Wind power** (2026-11-05; generic 2 MW curve 3/12/25 m/s until site capacities are known) [Aisha]: reference turbine power curve (cut-in, rated, cut-out speed and
  rated power in config, e.g. 3 / 12 / 25 m/s and site `capacity_kw`): 0 below cut-in and above
  cut-out, capped at rated power, never negative (DR-01, DR-03). Unit tests.
- [x] **T3.4 Per-site inference in Compose** (2026-11-05) [Nurbol]: services `inference-almaty`, … each mounting
  only its own `sites/<site>` folder, on the internal network only.
- [x] **T3.5 Forecast API** (2026-11-05) [Nursultan]: `GET /api/forecast` (§5.7) with validation (FR-26), routing
  to `inference-<site>`; `GET /api/runs`, `GET /api/runs/{id}` from the DB and `metrics.jsonl`.
- [x] **T3.6 Forecast chart** (2026-11-05; UI done, needs a real inference service) [Nurbol]: on `/forecast`, recharts chart with actual (before and after
  `as_of`) and forecast, m/s axis, optional power view; clear error states; ≤ 3 steps (NFR-10).
- [x] **T3.7 Training dashboard** (2026-11-05; reads runs/ folders) [Nurbol]: `/training` lists runs; `/training/[runId]` shows status,
  round X of N, validation error per round (line chart), sites table (replied/dropped, samples,
  loss), uplink size, round time; polls every 5–10 s while running.
- [ ] **T3.8 Reproducibility** [Kanat]: same config and seed twice → metrics within ±1% (NFR-06).
  Record the result.

**M3 done when:** the web app shows a real wind forecast vs actual for every site and horizon in
under 5 s, and a finished run in the dashboard.

### M4 — Experiment page and reliability (Nov 30–Dec 4)
- [x] **T4.1 Flower control client** (2026-11-05; `FlwrCliFederation`) [Nursultan]: `flower_control.py` in the API: start a run
  (write `config.yaml`, call `flwr run . lab --run-config …`, store the Flower run id), stop it
  (`flwr stop`), read status (`flwr ls`, JSON output if the version supports it), check that the
  SuperLink is reachable and how many clients are connected. Use the DB lock so only one run is
  active (409 otherwise). Calls run with a timeout; errors become 503 with the message.
- [x] **T4.2 `POST /api/runs`** (2026-11-05) [Nursultan]: multipart form: config fields + optional one CSV per
  site; validate CSV columns (`YEAR, MO, DY, HR, WS50M`) and config; save each CSV into
  `sites/<site>/uploads/<run_id>.csv`; set `data_source`; start the run via T4.1.
- [x] **T4.3 Experiment page** (2026-11-05; feedback board moved to `components/feedback-board.tsx`) [Nurbol]: `/experiments`, refactored from the legacy
  `app/dashboard/page.tsx` (split into components; move the feedback UI to its own component or
  page; redirect `/dashboard` → `/experiments`): built-in data or one CSV per connected site;
  choose strategy, rounds, local epochs, horizon, model; shows whether the federation is busy;
  submit → go to `/training/<runId>`; stop button on the active run.
- [x] **T4.4 Fault tolerance** (2026-11-05; verified in Docker on CPU: client-aktau stopped mid-run, both rounds finished with 4 sites, marked dropped, rejoined after restart. 50-round run still to do on the GPU server) [Nursultan]: round timeout and minimum clients from the config;
  `deploy/scripts/kill_client.sh` stops one client container mid-round (`docker compose stop
  client-aktau`); the round completes and the dashboard shows the site as dropped (FR-13); the
  restarted client rejoins the next run. Then a 50-round, 5-site run completes (NFR-05).
- [ ] **T4.5 New site joins (stretch)** [Kanat]: register a new wind site with validated static info
  (UC-3) and add one `client-<site>`/`inference-<site>` pair to Compose; it gets forecasts from the
  current global model at once (FR-15) and takes part in the next run.
- [ ] **T4.6 Evaluation tables and plots** [Nurbol/Aisha]: per site and horizon, FL vs baselines
  (FR-20); save to `results/`.

**M4 done when:** a run started from `/experiments` appears in `/training`, updates every round,
survives a stopped client, and finishes with a result that can be promoted to the forecast page.

### M5 — Demo and report (Dec 7–11)
- [ ] **T5.1 Demo script** [All]: `docs/DEMO.md`: `docker compose up` on the lab server; show five
  connected clients; start a short live 5-site run from `/experiments`; show the dashboard; stop one
  client to show dropout; promote the result; show forecasts for each horizon; show Solar as
  “coming soon”. Backup: the same stack on the laptop with a finished recorded run imported into
  `runs/` and `models/`.
- [ ] **T5.2 Design-document changes** [All]: list the edits for FR-06, DR-08, NFR-03 (horizons) and
  the experiment page; the team updates the document. The deployment view already matches.
- [ ] **T5.3 Report inputs** [All]: results tables, architecture and deployment diagrams,
  payload numbers, reproducibility result.
- [ ] **T5.4 Spring plan** [All]: from §9.

---

## 7. Testing and quality (NFR-12)

- ML core: `pytest Long-term_Forecasting/tests` — config consistency (T1.3), loaders with node
  config (T1.4), real-unit metrics (T2.3), payload audit (T2.4), power curve (T3.3), result
  writers (T2.3).
- Backend: `pytest federated-website/FastApi/tests` — FastAPI `TestClient` for `/api/sites`,
  `/api/forecast` validation (FR-26), `/api/runs` with a mocked Flower control client (start,
  409 when busy, stop, status mapping, restart reconciliation).
- Inference: a test that loads a tiny checkpoint and returns `horizon` points.
- Compose: `docker compose config` validates; a smoke script brings the stack up with
  `compose.laptop.yml`, runs a 1-round tiny config and checks `result.json`.
- Lint: add `ruff` and `black` config; run both on new and changed Python files.
- Frontend: `npx tsc --noEmit` must pass (the legacy build sets `ignoreBuildErrors`; don't rely on
  it). Note: `npm run lint` calls ESLint, which isn't in devDependencies yet.
- End to end: before each milestone ends, run the stack and click through the flow in the browser.
- Optional: `.github/workflows/ci.yml` running the above on pull requests (only commit when asked).

---

## 8. Fall requirements coverage

| Covered this fall | Notes |
|---|---|
| FR-01–FR-04, FR-06–FR-08 | Wind only; horizons 1/72/432 |
| FR-11–FR-14 | Compose federation in deployment mode, checkpoints, dropout tolerance |
| FR-18–FR-24, FR-26 | Config runs, baselines, metrics, logs, API, forecast page, dashboard |
| NFR-01–NFR-03, NFR-05, NFR-06, NFR-08, NFR-10, NFR-12 | NFR-02 to be checked at 432; NFR-08 via one Compose project |
| DR-01, DR-03–DR-07, DR-09, DR-10 | Power curve, no leakage, splits, nMAE, persistence, UTC, catalogue |
| FR-15 | Stretch (T4.5) |

## 9. Deferred to spring
Solar training and inference (KZ-Solar from NASA POWER: `ALLSKY_SFC_SW_DWN`, clear-sky index target,
night mask, DR-02); FR-05 site text prompts and multimodal alignment; FR-09 joint wind+solar;
FR-10 prediction intervals; FR-16 personalisation; FR-17 DP-SGD; FedAdam and clustered strategies;
FR-25 LLM summaries; NFR-04/NFR-07/NFR-09 measurements; moving clients to separate machines with
TLS and SuperNode authentication; real plant owners running the client package themselves.

## 10. Risks and open questions
| Risk / question | Mitigation |
|---|---|
| Lab server access comes late or not at all | Build and test everything on the laptop with `compose.laptop.yml`; laptop is the demo fallback with a recorded run. Ask now (T1.0) |
| No NVIDIA Container Toolkit / Docker on the lab server | Ask the lab admin to install it; else run SuperLink and SuperNodes as plain processes with the same flags (systemd or a script) and keep Docker for web/api/db |
| GPU memory: five clients on one or two shared GPUs | Small backbone, `llm_layers` 2–4, modest batch, one GPU per client when available; measure peak memory in T1.6 |
| Other lab users need the GPUs | Agree on time slots; stop client containers when not training (`docker compose stop client-*`) |
| Long runs block the website (one run at a time) | Show "busy" on the experiment page; stop button; keep demo runs short (3–5 rounds) |
| Flower version unknown; CLI flags and federation config location differ between versions | Pin in T1.1; check `--help` before scripting |
| No internet from the lab server | Build images and fill `hf-cache` on the laptop, then copy them over (`docker save` / rsync) |
| NFR-02 fails at 72 and 432 with the default patching | **Measured 2026-11-05** (seq 336, patch 4, stride 1, GPT-2 2 layers): uplink per client per round 1.8 MB (1 h), 74.7 MB (72 h, 15% of GPT-2), 444 MB (432 h, 89%). `out_layer` = 768 × 334 patches × horizon dominates. Patch 16 / stride 8: 1.0 / 10.1 / 56.6 MB (0.2 / 2.0 / 11.4%). Team decides: change patching, a smaller head, or a documented exception |
| Coordinates of the previous team's KZMET data unknown | Ask the user; else document the coordinates used |
| Design document disagrees with this plan | T5.2 |
| Exact demo date unknown | Ask the user; shift weeks |

## 11. Status log
| Date | Session summary | Next step |
|---|---|---|
| 2026-11-05 | Plan written. Solar skeleton and dashboard text changes exist uncommitted in the tree. Nothing from M1 started. | T1.1 / T1.2 / T1.3 |
| 2026-11-05 | Switched the target from Irgetas Slurm jobs to an always-on Docker Compose federation on the lab GPU server (user decision); Irgetas dropped. API controls runs via the SuperLink control API, one run at a time, no queue. | T1.0 (ask for lab access), then T1.1 / T1.2 / T1.3 on the laptop |
| 2026-11-05 | Track A started (§6.0). Backend: `/api/sites`, `/api/federation`, `/api/runs` (start/stop/detail, 409 one-run lock, per-site uploads), `/api/forecast`, `/api/models` with "not connected" adapters; 16 pytest tests pass. `deploy/docker-compose.yml` (web, api, db) builds and serves; feedback DB made lazy. | Frontend pages: T1.9 forecast, T3.7 training, T4.3 experiments |
| 2026-11-05 | Track A frontend done: `/forecast`, `/training`, `/training/[runId]` (stop, promote), `/experiments` (+ feedback board), `/dashboard` redirects, new navbar/footer, `lib/platform-api.ts`. `tsc` clean, `next build` passes, all flows clicked through against a scratch API with test-only run folders and a fake inference server. Backend validates model names. | Track B (training) or the connect step: `FlwrCliFederation`, inference service |
| 2026-11-05 | Track B done up to the GPU: flwr pinned to 1.25.0; config mismatch fixed (`experiment.build_model_configs`, `is-pretrained = true`); per-site data via node config; `metrics.jsonl` / checkpoints / `result.json` in m/s with persistence skill; per-site inference service + power curve; `FlwrCliFederation` in the API; full Compose federation + GPU override; NASA data 2015-2024 and GPT-2 cache in `deploy/data`. Verified on laptop CPU: process federation (2 rounds) and Docker stack driven by the API (start, 409 lock, stop, dropped client, promote, forecast in 2.7 s, web pages). Tests: ML 17, inference 12, API 21. Fixed legacy `copy.deepcopy(ArrayRecord)` crash. | Deploy on the GPU server (`deploy/DEPLOY.md`); T1.6 reference run; decide NFR-02 patching; T2.5 baselines; T2.7 |
