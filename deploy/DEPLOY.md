# Deploying FedWind on the lab GPU server

Everything runs from one Compose project: the web app, the API, Postgres, the Flower
SuperLink, one client container per site, one inference container per site and
`inference-central` (forecasts for registered plants from the window their agent shares). There
are five wind sites (almaty, zhezkazgan, aktau, taraz, aktobe) and five solar sites (konaev,
shymkent, kyzylorda, saran, turkistan), 25 containers in all. Wind and solar clients share
the one SuperLink; each run names its sites and the others sit it out.

```
web ─► api ─► db
        │  flwr run / stop / ls          (control API superlink:9093)
        ▼
     superlink  ◄── fleet API :9092 ──  client-almaty  client-zhezkazgan  client-aktau  client-taraz  client-aktobe   (GPU)
        │ writes data/runs/<run_id>/                     + client-konaev … client-turkistan (solar, GPU)
        │                                                each mounts only data/sites/<site>
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

`deploy/data/` already holds the wind and solar data (`sites/<site>/nasa_<site>.csv`,
2015–2024) and the GPT-2 weights (`hf-cache/`). If you copy the folder they come along.
Without them, on the server:

```bash
python3 Long-term_Forecasting/scripts/download_kzmet.py                  # wind (needs internet, NASA POWER)
python3 Long-term_Forecasting/scripts/download_kzmet.py --energy solar   # solar
deploy/scripts/prefetch_models.sh                                        # after the image is built (step 3)
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
- `GPU_<SITE>`: which GPU each client uses (ids from `nvidia-smi`), for all ten sites. With
  one GPU leave all at 0. Only the sites of the running run use their GPU, so wind and solar
  clients can share: e.g. wind almaty, zhezkazgan, aktau and solar konaev, shymkent,
  kyzylorda → 0; the other four → 1.

## 3. Build and start

```bash
docker compose -f deploy/docker-compose.yml -f deploy/compose.gpu.yml up --build -d
```

The first build downloads CUDA torch and takes a while. Then check:

```bash
docker compose -f deploy/docker-compose.yml ps
curl -s localhost:8001/api/federation          # "connected": true, "connected_nodes": 10
docker compose -f deploy/docker-compose.yml exec client-almaty python -c "import torch; print(torch.cuda.is_available())"
```

## 3b. Accounts (first admin)

The API creates its tables on start (`app/migrations/*.sql`). Create the first admin inside the
api container; the password is typed at a hidden prompt:

```bash
docker compose -f deploy/docker-compose.yml exec api python -m app.cli create-admin --email you@org.kz --name "Your Name"
docker compose -f deploy/docker-compose.yml exec api python -m app.cli list-users
```

Sites live in the database too. On first start the API imports the ten lab sites from
`deploy/seed/sites.json` (later edits of that file don't overwrite the database). Plant operators
register real plants under **My sites**; admins approve, reject, suspend, resume or revoke them on
**Sites**. Only active sites take part in runs and forecasts.

Then log in on the website. Admins can start and stop runs, use runs for forecasts, manage users
(**Admin** page) and read the audit log. Plant operators register themselves at `/register`
(set `ALLOW_REGISTRATION=false` in `.env` to close it). Behind HTTPS keep
`SESSION_COOKIE_SECURE=true`; on plain `http://` (laptop) set it to `false`, or the browser drops
the login cookie. Other CLI commands: `set-role`, `set-password`, `migrate`.

### Site CA (plant certificates)

The API creates the site CA on its first start, in the `site-ca` volume only the api mounts. When a
plant enrolls, its agent makes its keys on the plant, sends a certificate request and its Flower
public key, and gets a 90-day client certificate (CN = site id). Revoking or re-issuing a plant
puts its certificate into the revocation list (`crl.pem`, re-published every hour) and unregisters
its Flower node (`FLOWER_NODE_AUTH=on`). Back up `ca.key` offline: without it every plant has to
enroll again.

```bash
docker compose -f deploy/docker-compose.yml exec api python -m app.cli site-ca show   # CA validity, CRL entries
docker compose -f deploy/docker-compose.yml exec api python -m app.cli site-ca crl    # re-publish now
docker compose -f deploy/docker-compose.yml cp api:/secrets/site-ca/ca.key ./site-ca-backup.key   # keep offline
```

Until the mTLS gateway exists (SITE_NETWORK_PLAN.md M4) keep `SITE_AUTH_MODE=token` and
`FLOWER_NODE_AUTH=off`: plants still get certificates, and use their bearer site key.

## 4. First run

1. Open `PUBLIC_WEB_URL`, log in as admin, then **Experiments**.
2. Keep built-in data and all five sites. For a first run: 3 rounds, 1 local epoch,
   horizon 72 h, GPT-2, LLM layers 2. To check the wiring in a few minutes first, set
   **Train data used (%)** to 5 under advanced settings. Press **Start federated run**.
3. The run page shows each round as it finishes: validation error, which sites replied,
   uplink size, round time.
4. When it's **done**, press **Use for forecasts**. Then **Forecast** → pick a site and 72 h.

Each energy type and horizon (wind or solar × 1 / 72 / 432 h) needs its own finished and
promoted run before its forecasts work.

**Solar:** on Experiments choose **Solar federation**. The defaults forecast the clear-sky
index k* (converted back to GHI) and train on daylight hours only. The run page reports errors
in W/m² for daylight hours, with smart persistence (k* now × clear sky later) as the skill
reference, plus plain persistence and climatology. Solar runs use built-in data only (CSV
upload is wind-only for now). Forecast → Solar shows GHI, the clear-sky curve and PV power of
an assumed 1 MW plant (`PV_CAPACITY_KW` on the inference service).

The same can be done from a shell (start, stop and promote need an admin session: log in with
`POST /api/auth/login`, keep the cookie, and send the `csrf_token` from the response as
`X-CSRF-Token`):

```bash
curl -s -X POST localhost:8001/api/runs -F 'config={"rounds":3,"local_epochs":1,"horizon":72,"llm_layers":2}'
curl -s -X POST localhost:8001/api/runs -F 'config={"energy_type":"solar","rounds":3,"local_epochs":1,"horizon":72,"llm_layers":2}'
curl -s localhost:8001/api/runs
curl -s -X POST localhost:8001/api/models/promote -H 'Content-Type: application/json' -d '{"run_id":"<run_id>"}'
curl -s "localhost:8001/api/forecast?site=almaty&horizon=72"
curl -s "localhost:8001/api/forecast?energy_type=solar&site=saran&horizon=72"
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

## 6b. A public link from a laptop (for friends, not for real plants)

The browser talks to the API through the website's own address (`/api` is forwarded by the web
server, `next.config.mjs`), so one public link is enough:

```bash
deploy/tunnel.sh on       # prints https://….lhr.life: send that link
deploy/tunnel.sh status   # on or off, and the current link
deploy/tunnel.sh off      # the link stops working at once; localhost:3000 keeps working
```

- Uses **localhost.run** (an SSH tunnel, no account). Its free address **changes now and then**:
  run `status` before sending it again. The connection reconnects by itself if it drops.
- `TUNNEL=cloudflare deploy/tunnel.sh on` uses a Cloudflare quick tunnel instead; it needs outbound
  port 7844, which some networks (e.g. this laptop's) block.
- While it's on, Telegram messages and downloaded site kits link to the public address; `off`
  points them back at localhost.
- Anyone with the link can open the site and **register** (`ALLOW_REGISTRATION`). Keep the admin
  password strong. The laptop must stay awake with the stack running. Nothing starts after a reboot.
- localhost.run doesn't pass visitors' addresses, so the audit log shows the proxy's address for
  them (login throttling is per email, so that's unaffected).

## 6c. Central server for real plants (deploy/central)

`deploy/docker-compose.yml` is the lab stack (ten lab sites, per-site inference, experiments). Real
plants connect to a separate **central server** (SITE_NETWORK_PLAN.md M4): website, API, Postgres,
SuperLink with TLS and node authentication, central forecasting and an nginx gateway. Only the
gateway is published (80 for Let's Encrypt, 443).

```bash
cp deploy/central/.env.example deploy/central/.env   # WEB_HOST, SITES_HOST, ACME_EMAIL, passwords (openssl rand -hex 32)
docker compose -f deploy/central/docker-compose.yml up -d --build
deploy/central/certs.sh issue                         # Let's Encrypt for both names (DNS must point here)
docker compose -f deploy/central/docker-compose.yml exec api python -m app.cli create-admin --email you@org.kz --name "Your Name"
SITES_HOST=sites.example.kz deploy/central/check_ports.sh <public address>   # from outside: only 80/443, site API 403
```

- `pki-init` (one-shot, every `up`) makes the internal CA and the SuperLink certificate (renewed
  when < 30 days are left: restart superlink afterwards) and self-signed placeholders until
  `certs.sh issue` has run. Renew public certificates daily from cron: `certs.sh renew`.
- `https://WEB_HOST`: website and user API. `https://SITES_HOST`: plants only. A client
  certificate from the site CA is required except for `/site-api/enroll`; only `/site-api/` and
  the Flower Fleet API are routed. The gateway reloads within 30 s when the API publishes a new CRL.
- The API runs with `SITE_AUTH_MODE=mtls` and `FLOWER_NODE_AUTH=on`: an enrolled plant's SuperNode
  key is registered with the SuperLink, and revoking the plant unregisters it.
- Volumes to back up: `db-data`, `site-ca` (the site CA key), `internal-ca`, and `CENTRAL_DATA`
  (runs, models). Plant kits: `deploy/site/README.md`.

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
