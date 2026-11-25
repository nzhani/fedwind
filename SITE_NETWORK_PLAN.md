# FedWind site network plan: registration, site kit, secure federation (Kazakhstan)

Written 2026-11-19. Builds on the working system in `FALL_2026_PLAN.md` (wind + solar, Flower 1.25.0
deployment mode, Compose). This plan turns the "all sites on one server" setup into a real network:
plants anywhere in Kazakhstan register on the website, receive a personal **site kit**, run it at the
plant, and from then on train and forecast automatically. Every connection is authenticated and
encrypted, and nothing that touches model updates is reachable from the open internet.

---

## 0. Goals, scope and fixed decisions

**Goals**
1. A plant registers on the website, an admin approves it, the plant downloads a site kit with
   instructions, runs one command, and appears **online** within minutes.
2. Not a fixed list of 5 sites: sites come and go through the website. Design target **up to ~100
   sites**, tested with **20**.
3. Every site and every data flow is secured. The federation endpoints (model updates) are **not open
   endpoints**: a client without a valid, unrevoked site certificate is refused by the gateway before
   anything reaches Flower or the API (verified in M0).
4. The website runs on a public central server, which also keeps the **newest promoted model** and
   serves forecasts with it.
5. Training stays automatic: always-on site clients, scheduled runs, gated promotion.

**Scope:** plants in Kazakhstan only (wind and solar). Time stays UTC; site time zones are metadata.

**Fixed decisions** (change only with the user)

| # | Decision |
|---|---|
| F1 | Raw training history never leaves a plant. Only model updates (weights, sample counts, metrics) go to the server during training. |
| F2 | Every connection is opened **by the plant, outbound, on TCP 443 only** (one port; firewall-friendly). No inbound ports at plants. |
| F3 | Plants are identified by **three credentials**: a client TLS certificate (network access), a Flower SuperNode key (federation access), both generated at the plant; the private keys never leave it. A one-time enrollment token links them to the approved site. |
| F4 | The SuperLink's Control API (9093) and ServerAppIo API (9091), Postgres, and all internal services are **never exposed** outside the central server's private Docker network. |
| F5 | Sites, users, credentials, models and forecasts live in **Postgres** (replaces `deploy/seed/sites.json`). |
| F6 | The central server needs no GPU: training happens at the plants; the server aggregates and forecasts on CPU. |
| F7 | Host the central server **in Kazakhstan** (user accounts are personal data; check the data-localisation rules of the Law on Personal Data before launch). |

**Open decisions** (defaults in bold; see §8)

| # | Question | Options |
|---|---|---|
| D1 | Where are forecasts computed? | **Central, from a short recent window the plant shares (consent per site)** · local at the plant, forecast pushed |
| D2 | Network hardening beyond mTLS | **mTLS gateway + Flower node auth** · plus per-site IP allowlist · plus WireGuard VPN |
| D3 | Promotion | **Automatic when all gates pass, admin can veto within 24 h** · always manual |
| D4 | Site software updates | **Operator runs one update command when the portal says so** · auto-update (opt-in) |
| D5 | Domain names | e.g. `fedwind.kz` (website) and `sites.fedwind.kz` (site gateway) |

---

## 1. Target architecture

```
                     PUBLIC INTERNET
   people (browsers)          │                 plants (site kits), outbound 443 only
          │ https://fedwind.kz│                         │ https://sites.fedwind.kz  (mTLS)
          ▼                   │                         ▼
┌──────────────────────────── CENTRAL SERVER (Kazakhstan) ────────────────────────────────────┐
│  gateway (nginx or Caddy) :443                                                              │
│   ├─ fedwind.kz          → web (Next.js) + user API (/api/*)   server TLS, login sessions    │
│   └─ sites.fedwind.kz    → client certificate REQUIRED (mTLS), except /site-api/enroll       │
│        ├─ /site-api/*    → site API   (heartbeat, model download, forecast inputs/outputs)   │
│        └─ gRPC Fleet     → superlink:9092 (re-encrypted TLS; Flower node auth on)            │
│                                                                                             │
│  private Docker network (nothing below is published):                                       │
│   api (user API + site API) ── postgres (users, sites, creds, models, forecasts, audit)     │
│   superlink (9091 ServerAppIo, 9092 Fleet, 9093 Control)  ← api uses flwr CLI over 9093     │
│   scheduler (in api)  · model registry (models volume) · central inference (CPU)            │
│   ca (site certificate authority: signs CSRs at enrollment, keeps a revocation list)        │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                        ▲
┌──────────────── PLANT (Linux server or VM, Docker) ────┴────────────────────────────────────┐
│ site kit  (docker compose up -d)                                                            │
│  enroll     first start only: makes keys + CSR, redeems the one-time token                  │
│  tunnel     nginx: SuperNode ──TLS──► tunnel ══mTLS (plant cert)══► gateway (M0 finding)    │
│  agent      reads plant data (CSV drop folder → later OPC UA / PI) → local hourly UTC store  │
│             quality checks · heartbeat · shares the forecast window (if D1 = central)       │
│  supernode  Flower client: TLS to the tunnel + its node key; trains on local store          │
│  status     local page http://localhost:8080: status, consent switches, logs (no internet)  │
│  volumes    secrets/ (keys, certs; 0600) · store/ (hourly data) · logs/                     │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Why one door (443) for plants:** plant IT departments usually allow outbound HTTPS. The gateway
routes gRPC (Flower) and REST (site API) on the same hostname. Clients without a plant certificate get
an HTTP 400 from the gateway; only `/flwr.proto.Fleet/` and `/site-api/` are routed at all.

**Why a tunnel at the plant (M0):** Flower 1.25's SuperNode can't present a client certificate (it only
has `--root-certificates`), and node authentication refuses to run without TLS to the next hop. So the
site kit runs a tiny nginx (~10 MB RAM) that the SuperNode reaches over TLS (trusting a plant-local CA
made at enrollment) and that connects to the gateway with the plant certificate.

**Compose split:** `deploy/docker-compose.yml` today holds clients and inference per site. It becomes:
- `deploy/central/docker-compose.yml`: gateway, web, api, postgres, superlink, inference, (ca).
- `deploy/site/docker-compose.yml`: the site kit template (enroll, agent, supernode, status).
- `deploy/dev/`: a script that starts N site kits on one machine for testing (§11).

---

## 2. Security model

### 2.1 Layers (defence in depth)

| Layer | What | Stops |
|---|---|---|
| L1 Network | Only 443 open on the central server (plus 22 for admins from fixed IPs). Docker network private. Optional (D2): IP allowlist per site, or WireGuard. | Port scans, direct access to SuperLink/DB |
| L2 mTLS gateway | `sites.fedwind.kz` demands a client certificate signed by the FedWind site CA and not revoked (nginx `ssl_verify_client on` + `ssl_crl`). nginx answers bad clients with HTTP 400 after the handshake; only Fleet and site-API paths are routed. | Anyone without an enrolled site certificate, including for the Flower endpoint |
| L3 Flower node auth | SuperLink started with TLS + `--enable-supernode-auth`; each SuperNode key registered with `flwr supernode register` at enrollment; revoked with `flwr supernode unregister`. | A stolen client certificate alone; a SuperNode that isn't registered |
| L4 Site API auth | Site API reads the site id from the verified client certificate (gateway forwards subject/serial in headers it sets itself); every call checked against the site's status. | A site acting as another site |
| L5 Authorization | User API: sessions + roles (admin, operator, viewer). Operators see only their organization's sites. Admin-only: approve, revoke, start/stop runs, promote. | Users acting beyond their role |
| L6 Model safety | Server-side checks on each update: shape, finite values, norm within k × median of the round; outliers dropped and logged. | Broken or poisoned updates |
| L7 Audit | Append-only audit log of logins, approvals, enrollments, revocations, runs, promotions, downloads. | Silent misuse |

### 2.2 What is public, what is not

| Endpoint | Reachable by | Auth |
|---|---|---|
| `https://fedwind.kz/` pages | anyone | public pages; app pages need login |
| `https://fedwind.kz/api/auth/*`, `/api/public/*` | anyone | rate-limited |
| `https://fedwind.kz/api/*` (rest) | logged-in users | session cookie (httpOnly, Secure, SameSite=Lax) + role |
| `https://sites.fedwind.kz/site-api/enroll` | anyone **with a valid one-time token** | server TLS + token; rate-limited; token single-use, expires in 72 h |
| `https://sites.fedwind.kz/site-api/*` (rest) | enrolled sites only | **client certificate** |
| `sites.fedwind.kz` gRPC (Flower Fleet) | enrolled sites only | **client certificate** + Flower node key |
| SuperLink 9091 / 9093, Postgres, inference, CA | nobody outside the server | not published |
| Model files | never public | site API (mTLS) or admin download |

### 2.3 Credentials and their life

| Credential | Created where | Stored where | Lifetime | Revocation |
|---|---|---|---|---|
| User password | user | Postgres, argon2id hash | until changed | disable account |
| Enrollment token | API at approval (or re-issue) | shown once in the kit; Postgres keeps only its hash | single use, 72 h | delete / expires |
| Site TLS key + client cert | key at plant; cert signed by FedWind CA | plant `secrets/` (0600); cert serial in Postgres | 90 days, auto-renewed at 60 days via mTLS | CRL reloaded by gateway; site status `revoked` |
| Flower SuperNode key (EC P-384, OpenSSH format) | plant | plant `secrets/`; public key + Flower node id in Postgres | until rotated | `flwr supernode unregister` (permanent: the same key can't be registered again, so re-issue = new keys) |
| Plant-local CA + tunnel cert | plant (at enrollment) | plant `secrets/` | 1 year | regenerate locally |
| CA key | central server | central `secrets/` (0600), offline backup | 5 years | rotate CA (re-enroll all) |
| Server TLS (public) | Let's Encrypt | gateway | auto | — |
| SuperLink TLS (internal) | FedWind CA | central `secrets/` | 1 year | — |

Private keys of a plant **never leave the plant**: enrollment sends only a CSR and a public key.

### 2.4 Threats checked in tests (§11)
- No client cert → refused by the gateway on `sites.fedwind.kz` (both REST and gRPC). ✅ M0
- Cert from another CA, expired cert, revoked cert → rejected. ✅ M0 (other CA, revoked)
- Valid cert but Flower key not registered → SuperLink refuses the node. ✅ M0
- Reused or expired enrollment token → 401; token brute force → rate-limited, logged.
- Operator of org A reads org B's site → 404.
- 9091/9093/5432 not reachable from outside (port scan in CI script). ✅ M0 (9091–9093)
- Poisoned update (huge norm, NaN) → dropped, run continues, audit entry.

---

## 3. Accounts and roles

| Role | Who | Can |
|---|---|---|
| admin | federation operators (team) | everything: approve/suspend/revoke sites, start/stop/schedule runs, promote/veto models, see all sites |
| operator | staff of one plant owner (organization) | register sites for their org, download kits, see their sites' status, data quality, forecasts, run participation; pause participation; leave |
| viewer | professor, grid operator, guests | read-only: public results, forecasts the owner marked public |

Implementation (user API, FastAPI): email + password (argon2id), server-side sessions in Postgres,
CSRF token for state-changing requests, password reset by email later. 2FA (TOTP) for admins in M8.
The Next.js app adds login/logout, a session check, and role-aware navigation.

---

## 4. Site lifecycle

```
 registered ──approve──► approved ──enroll──► online ⇄ offline
     │                       │                   │
   reject                 re-issue kit         suspend (admin/operator) ─► suspended ─resume─► online
                                                 │
                                               revoke ─► revoked (certificate in CRL, Flower node unregistered; final)
```

1. **Register** (operator, website): organization (first time), then site: name, energy type (wind or
   solar), latitude/longitude (validated inside Kazakhstan's bounding box), capacity (kW), equipment
   (turbine model and hub height, or PV module type/tilt/azimuth), data source type, contact, and the
   **consents**: train with the federation (required), share the forecast window (D1), show forecasts
   publicly (optional).
2. **Approve** (admin): checks the details; status `approved`; API issues the enrollment token and
   builds the kit.
3. **Download kit** (operator): one zip, available while the token is unused (§5).
4. **Install and enroll** (plant IT): `docker compose up -d`. The `enroll` step generates keys, sends
   CSR + Flower public key + token. API verifies the token, signs the cert (CN = site id), runs
   `flwr supernode register` with the public key, stores the Flower node id, marks the token used,
   returns the cert. Site status `online` after the first heartbeat.
5. **Operate** (automatic): heartbeats every 5 min, hourly data, training when runs come, forecasts.
6. **Pause / leave**: the status page or the website can pause training participation; leaving revokes.
7. **Re-issue**: lost server or keys → admin re-issues a kit (old credentials revoked first).

---

## 5. Site kit

### 5.1 Contents of `fedwind-site-<site_id>.zip`

```
fedwind-site-<site_id>/
├── README.md                 personalised install instructions (site name, steps, checks, support contact)
├── docker-compose.yml        enroll, tunnel, agent, supernode, status (images pinned by digest)
├── .env                      SITE_ID, ENERGY_TYPE, SITES_HOST=sites.fedwind.kz, PORTAL=https://fedwind.kz,
│                             DATA_SOURCE=csv, CAPACITY_KW, LAT, LON, TZ — no secrets
├── enrollment.token          one-time token (deleted by enroll after use)
├── ca.crt                    FedWind site CA (public) — to trust sites.fedwind.kz's internal chain
├── data/inbox/               drop CSV exports here (csv mode)
└── data/README.md            the data contract (§5.3) with an example file
```

### 5.2 Plant requirements (in README)
- Linux server or VM (Ubuntu 22.04/24.04) with Docker Engine + Compose v2; Windows Server with
  WSL2 possible later.
- Training: NVIDIA GPU (≥ 8 GB) with the NVIDIA Container Toolkit recommended; CPU-only allowed
  (slower; the scheduler gives CPU sites a longer round timeout).
- 4+ CPU cores, 16 GB RAM, 30 GB disk (images ≈ 6–12 GB, GPT-2 cache 0.6 GB, data, logs).
- Outbound TCP 443 to `fedwind.kz` and `sites.fedwind.kz`. No inbound ports.
- Access to plant data: a folder where SCADA/historian exports land (CSV mode, M5), later OPC UA or
  PI Web API credentials (read-only).

### 5.3 Data contract (hourly UTC; the agent converts finer data)

| Column | Wind | Solar | Notes |
|---|---|---|---|
| `timestamp_utc` | ✓ | ✓ | ISO 8601, hour start, UTC |
| `wind_speed_ms` | ✓ (hub height) | — | m/s |
| `ghi_wm2` | — | ✓ | W/m², hour average |
| `power_kw` | ✓ | ✓ | AC export, hour average |
| `available` | ✓ | ✓ | 0–1 share of capacity available (maintenance) |
| `curtailed` | ✓ | ✓ | 1 if output was limited by the grid/operator |
| `temperature_c` | optional | optional | |

Agent rules: resample 10-min → 1 h (mean; ≥ 4 of 6 values required), drop duplicates, flag gaps,
range checks (wind 0–40 m/s, GHI 0–1400 W/m², power 0–1.1 × capacity), stuck-sensor check
(same value ≥ 6 h in daylight/wind), exclude curtailed and unavailable hours from training targets,
keep the series continuous with a mask. A daily quality summary goes to the portal (counts only).

### 5.4 Install (what the README says)
```bash
unzip fedwind-site-<site_id>.zip && cd fedwind-site-<site_id>
docker compose up -d            # first start enrolls the site (once)
docker compose logs -f enroll   # expect: "Enrolled as <site_id>, Flower node <id>"
open http://localhost:8080      # status page: online, data OK, waiting for a run
```
Then copy (or schedule an export of) plant data into `data/inbox/`. The website shows the site as
online and the data quality within minutes.

---

## 6. Every message between a plant and the server

All over TLS to `sites.fedwind.kz:443`; all opened by the plant.

| When | From → to | Channel | Content | Auth |
|---|---|---|---|---|
| first start | enroll → site API `POST /site-api/enroll` | HTTPS | token, CSR, Flower public key, kit version | token |
| every 5 min | agent → `POST /site-api/heartbeat` | HTTPS | status, software version, last data hour, disk/GPU free, consent flags | mTLS |
| daily | agent → `POST /site-api/quality` | HTTPS | counts: rows, gaps, flagged, curtailed hours | mTLS |
| every few s | supernode → Fleet (pull) | gRPC | "any work?" | mTLS + node key |
| in a run | Fleet → supernode | gRPC | global trainable weights, run config | mTLS + node key |
| in a run | supernode → Fleet (push) | gRPC | updated weights, sample count, loss, val/test errors | mTLS + node key |
| hourly (D1 central) | agent → `POST /site-api/forecast-input` | HTTPS | last `seq_len` hourly values of the target (+ mask) | mTLS |
| hourly (D1 local) | agent → `GET /site-api/models/current` (+ download) and `POST /site-api/forecasts` | HTTPS | model version check / weights / forecast values | mTLS |
| at 60 days | enroll → `POST /site-api/renew` | HTTPS | new CSR | mTLS (old cert) |

Never sent: training history, raw SCADA tags, credentials, private keys.

---

## 7. Training at scale (dynamic sites)

Changes from today's code:
1. **No fixed partition ids.** SuperNodes start with `--node-config 'site="<id>" energy="<type>" data-root="/store"'`.
   `client_app.py` reports `site` in its metrics; seeds derive from a stable hash of the site id.
   `run_logging.py` keys clients by site id. `partition-sites`, `num-partitions` and
   `DATASET_REGISTRY`-by-index go away for deployment runs (simulation mode keeps them).
2. **Selection by rule, not by hand.** A run's config names its energy type and an eligibility rule;
   the API resolves it to site ids at start: approved, online in the last 10 min, consented to train,
   data quality OK (≥ N clean days), software version compatible. `site-names` carries the list
   (fine for hundreds). A SuperNode not in the list replies "skipped" (already implemented).
3. **Sampling.** `fraction_train` < 1 when more than ~30 sites are eligible (e.g. 0.5, at least
   `min_train_clients`); timeouts per round from the slowest expected site class (GPU/CPU).
4. **Scheduler** (in the API, APScheduler): per energy type, e.g. Sunday 02:00 Asia/Almaty. Starts a
   run only if ≥ `min_sites` eligible and no run active; otherwise logs why and retries next hour
   (max 6). Manual start stays for admins (experiments).
5. **Robust aggregation** (L6): drop updates with non-finite values or norm > 5 × round median;
   log dropped sites. Option later: trimmed-mean strategy.
6. **Payload:** the 72/432 h output head (75 / 444 MB per site per round) must be fixed before many
   sites join (patch 16 / stride 8 or a smaller head; FALL_2026_PLAN §10). With 50 sites at 75 MB that
   is 3.75 GB per round into the server.
7. **Rolling splits for real data:** train on the site's history except the last 8 weeks, validate on
   weeks −8…−4, test on the last 4 weeks; keeps evaluation current.

---

## 8. Model registry and forecasting on the central server

**Registry.** Every finished run's best checkpoint is stored in `models/<energy>/<horizon>/<version>.pt`
with its run config, metrics and a SHA-256. Postgres `model_versions` records status:
`candidate → promoted → retired`. Exactly one promoted version per (energy type, horizon).

**Promotion gates (D3).** A candidate is promoted when, on the latest validation windows of the sites
that took part: (a) mean skill beats the current promoted model, (b) beats persistence (wind) / smart
persistence (solar), (c) no site worse than the current model by > 10 %. Default: promote
automatically, notify admins, admin can roll back with one click (previous version stays stored).

**Forecasting (D1).** The newest promoted model lives on the central server and the central inference
service (today's `inference/app.py`, reworked to read from Postgres instead of a site CSV) uses it:

- **Central mode (default):** each hour the site agent sends the last `seq_len` hourly values of the
  forecast target (with the mask). Central inference forecasts for every horizon with a promoted model,
  converts to power with the site's capacity (wind curve / PV model), stores the forecast; the
  website reads stored forecasts (fast, no per-request model run). Retention of shared windows:
  30 days, then deleted. **This is an exception to NFR-01** (a short recent window of one variable leaves
  the site), so it's a per-site consent and stated in the kit README.
- **Local mode (for sites that don't consent):** the site downloads the promoted model through the
  site API, forecasts locally, and posts only the forecast values. Same website view.
- **Cold start (FR-15):** a newly approved site gets forecasts from the global model as soon as it
  shares its first window (central) or downloads the model (local); no training needed first.

The website's Forecast page lists sites from Postgres (with a Kazakhstan map), shows the latest stored
forecast and actuals (from the shared window), and the model version that produced it.

---

## 9. Data model (Postgres)

| Table | Key columns |
|---|---|
| `organizations` | id, name, contact, created_at |
| `users` | id, org_id (null for admins), email, password_hash, role, active, last_login |
| `sessions` | id (random), user_id, expires_at, csrf_token |
| `sites` | id (slug), org_id, name, energy_type, lat, lon, timezone, capacity_kw, equipment (json), data_source, status, consents (json), created_at, approved_by/at |
| `enrollment_tokens` | site_id, token_hash, expires_at, used_at |
| `site_credentials` | site_id, cert_serial, cert_not_after, flower_node_id, flower_pubkey_fpr, revoked_at |
| `heartbeats` | site_id, at, software_version, last_data_hour, gpu, disk_free, consents (latest kept per site + 7 days history) |
| `data_quality` | site_id, day, rows, gaps, flagged, curtailed |
| `runs` | id, energy_type, trigger (schedule/manual), config (json), status, eligible_sites, started/finished (run folders stay for logs and checkpoints) |
| `model_versions` | id, energy_type, horizon, run_id, path, sha256, metrics (json), status, promoted_at/by |
| `forecast_inputs` | site_id, hour, value, mask (30-day retention) |
| `forecasts` | site_id, model_version_id, issued_at, horizon, values (json), power_kw (json) |
| `audit_log` | at, actor (user/site/system), action, target, details (json), ip |

Migrations with Alembic (already pinned in the image).

---

## 10. API surface

**User API** (`fedwind.kz/api`, session):
`POST /auth/register|login|logout`, `GET /auth/me` ·
`GET/POST /orgs`, `GET/POST /sites`, `GET /sites/{id}` (status, quality, participation) ·
`POST /sites/{id}/approve|reject|suspend|resume|revoke|reissue-kit` (admin) ·
`POST /my/sites/{id}/kit` (operator, until enrolled; POST because it issues a token) ·
`GET/POST /runs`, `POST /runs/{id}/stop`, `GET/PUT /schedule` (admin) ·
`GET /models`, `POST /models/{id}/promote|rollback` (admin) ·
`GET /forecast?site=&horizon=` (role/consent-aware) · `GET /audit` (admin).

**Site API** (`sites.fedwind.kz/site-api`, mTLS except enroll):
`POST /enroll`, `POST /renew`, `POST /heartbeat`, `POST /quality`, `POST /forecast-input`,
`GET /models/current?energy=&horizon=`, `GET /models/{id}/download`, `POST /forecasts`.

---

## 11. Milestones

Estimates are working days for one developer with this codebase. Each milestone ends with its
checks passing and a short entry in the status log.

| M | Work | Done when | Est. |
|---|---|---|---|
| **M0 Spike ✅ done 2026-11-19** | Flower 1.25 behind the gateway: SuperLink TLS + `--enable-supernode-auth`; nginx gateway (`ssl_verify_client`, CRL, `grpc_pass grpcs://superlink:9092`); plant tunnel; register/unregister over the TLS Control API. **Result:** 1-round solar run through the gateway; 8/8 probes pass; unregistered key refused; unregister cuts a plant off. See `deploy/gateway-spike/README.md`. | done | 1 |
| **M1 Accounts ✅ done 2026-11-19** | Postgres schema (plain SQL migrations in `app/migrations/`, run at API start, instead of Alembic: no new framework); users, orgs, sessions (hashed tokens, 12 h), argon2id, CSRF, roles, login throttling, audit log; `/login`, `/register`, `/admin`; `python -m app.cli create-admin`; admin-only start/stop/promote. Also closed: legacy upload/train/jobs/federated/download routers (incl. an open `POST /model-update`) unmounted unless `ENABLE_LEGACY_API=true` (then admin-only); feedback delete and Telegram webhook setup admin-only; webhook secret check. Read endpoints (runs, sites, forecasts) stay public until M2/M7 add per-site visibility. | 15 new API tests (41 total) on a throwaway Postgres; browser: register → operator view → admin view → promote → log out | 1 |
| **M2 Sites ✅ done 2026-11-19** | Sites in Postgres (`002_sites.sql`; the 10 lab sites imported once from `sites.json` as kind `builtin`; JSON stays the no-database fallback); operator registration (Kazakhstan bounds, equipment checked per energy type, consents with training required, Kazakh/Russian names → Latin ids); edit while waiting; admin approve / reject / suspend / resume / revoke with required reasons; history from the audit log; public `/api/sites` lists active sites only; suspended sites leave runs and forecasts. Pages `/sites`, `/sites/new`, `/sites/[id]`. | 6 new API tests (47 total); browser: operator registers → admin approves → suspend with reason → resume | 1 |
| **M3 PKI + enrollment + kit ✅ code done 2026-11-24 (unit-tested; live check on the lab server pending)** | Small CA (Python `cryptography`): sign CSR, CRL; enrollment token; `POST /site-api/enroll` (sign cert, `flwr supernode register`, store node id); kit zip generator with personalised README; re-issue and revoke (CRL + unregister). **Result:** `app/services/site_ca.py` (EC P-384 CA in its own volume, 90-day client certs with CN = site id from a checked CSR, CRL re-published hourly), `flower_nodes.py` (`flwr supernode register/unregister`, `FLOWER_NODE_AUTH=on`), migration 005 `site_revocations` (outlives deleted sites; unregister retried), enrollment rolls back on any failure so the token stays usable, mtls identity = CN + serial of the live certificate, `site-ca init|show|crl` CLI; site agent 0.2.0 makes TLS + Flower keys at the plant and sends only the CSR and public key. 6 API + 3 agent tests. Open for M4: the gateway must let `/site-api/enroll` through without a client certificate. | Kit downloads; a site enrolls once; second use of token fails; revoke cuts the site off | 3 |
| **M4 Central/site split ✅ code done 2026-11-24 (gateway checked with nginx + stub backends; full stack not run)** | `deploy/central` (gateway with Let's Encrypt + mTLS vhost, superlink TLS + node auth, internal network only) and `deploy/site` template; remove per-site services from central Compose; DEPLOY.md rewritten for both sides. | Central stack up with only 443 published; port scan clean. **Result:** `deploy/central/` (compose with only the gateway published on 80/443, `pki_init.py` internal CA + SuperLink TLS + placeholder certs, nginx gateway: web vhost and plant vhost with `ssl_verify_client optional` + CRL, enroll without a certificate (rate-limited), forged X-Site-Id/X-Forwarded-For/CF-Connecting-IP replaced, reload within 30 s of a new CRL; `certs.sh` Let's Encrypt, `check_ports.sh`), API publishes ca.crt + crl.pem to a gateway-only volume, flwr federation `central` with TLS; site kit gains `tunnel` + `supernode` (profile `federation`), GPU override, plant-local CA + tunnel cert made by the agent. The lab stack `deploy/docker-compose.yml` stays for experiments. Checked: compose configs, `nginx -t`, gateway against stubs (no cert 403, revoked 400, forged headers replaced, Control API 404, revocation live in 25 s). | 2–3 |
| **M5 Site agent ✅ code done 2026-11-24 (unit-tested; not run on a second machine yet)** | `enroll`, `agent` (CSV inbox → hourly UTC store, data contract checks, quality summary, heartbeat, forecast-input push), `status` page; SuperNode reads the store. | A site kit from the portal runs on a second machine/VM and trains in a run. **Result:** `site_agent/store.py` keeps `data/store/nasa_<site>.csv` in the NASA POWER layout the Flower app reads unchanged (implausible hours -999, starts after the newest gap > 72 h, atomic rewrite on change); heartbeat reports `train_hours`; simulated plants fetch `SIM_HISTORY_YEARS` past years + this year from NASA POWER (cached per year); read-only status page `site_agent/status.py` on 127.0.0.1:8080. Tests: store parsed by the real loaders (wind and solar). Consent switches on the status page not done. | 4 |
| **M6 Dynamic training ✅ code done 2026-11-24 (unit-tested; no 20-site run yet)** | Site-id based clients and logging (no partition ids); eligibility resolver; sampling; scheduler; robust update checks; rolling splits for site stores. | Scheduled run with 20 simulated sites, one dropped, one poisoned update rejected. **Result:** clients without partition ids (`experiment.client_identity`, seed from a hash of the site id), replies carry a `client` ConfigRecord with the site, server and `metrics.jsonl` keyed by site; `robust.py` drops non-finite / mis-shaped updates and norms > `max-update-norm-ratio` (5) x round median, logged as `rejected` with the reason; eligibility `site_connection.training_status` (active, consent, Flower node, online 10 min, agent 0.2+, `TRAIN_MIN_HOURS` in the store) with a `train_note` per site; `run_launcher.py` (shared by the API and the scheduler), sampling above `TRAIN_SAMPLE_ABOVE`; `scheduler.py` weekly slots `TRAIN_SCHEDULE`, hourly retries up to 6, migration 006. Rolling splits for site stores not done (still 70/10/20 by time). | 3 |
| **M7 Registry + forecasting** | `model_versions`, promotion gates, rollback; central inference reading `forecast_inputs`; stored forecasts; Forecast page from Postgres + map; local mode endpoints. | New model promoted automatically; every site has fresh hourly forecasts | 3 |
| **M8 Ops + hardening** | Cert auto-renewal, admin TOTP, rate limits, backups (Postgres dump + models + CA key), health/metrics page, update notices for site kits, log retention. | Renewal test with short-lived certs; restore from backup works | 2–3 |
| **M9 Scale + security test** | `deploy/dev/spawn_sites.sh N`: registers, approves, enrolls N simulated Kazakh sites (NASA POWER data at real plant regions) as separate Compose projects; §2.4 security checks as a script; load test 20 sites × 3 rounds. | 20 sites train and forecast; all security checks pass; results written up | 2–3 |

Total ≈ 25–30 days. **Order matters:** M0 first (it decides whether the gateway design works with
Flower 1.25; fallback in §12), then M1→M3 (who may do what, how sites get credentials), then M4→M5
(real separation), then M6→M7, then M8→M9.

**Demo simulation:** `DEMO_SIMULATION_PLAN.md` builds the real enrollment, kit, heartbeat and
quality endpoints now (token identity mode) and simulates only the plant (site agent with NASA POWER
data), so M3–M7 extend it without rewrites.

**Relation to the December demo:** GPU runs, the patching decision and baselines stay first. If time
allows, a demo slice is M0 + M1 (minimal) + M2 + M3 + M5 with one extra site kit on a second machine:
"a new plant registers, is approved, installs the kit, appears online and joins a run". The rest is
spring work.

---

## 12. Risks and fallbacks

| Risk | Fallback |
|---|---|
| ~~Flower 1.25 node auth doesn't work through an mTLS proxy~~ | Resolved in M0: it works with a plant-side tunnel. Still to test in M4: 75 MB / 444 MB updates through the gateway, certificate renewal during a run |
| Plants block outbound gRPC through their proxy | gRPC already runs on 443; if a TLS-inspecting proxy breaks it, ask for a bypass for `sites.fedwind.kz`, or WireGuard over UDP 51820 |
| Plants can't run Docker | Native packages later (systemd service on Linux; Windows service) from the same Python code |
| No GPU at plants | CPU profile: fewer LLM layers, smaller head, longer round timeout; still works for 1 h and (after the patch fix) 72 h |
| Payload too large for many sites | Fix the head (NFR-02) before scaling; 8-bit update compression as a second step |
| Very different sites (north vs south, wind vs solar) | One model per energy type; later clustered models (e.g. by region) and per-site fine-tuned heads (FR-16) |
| Central-mode window sharing not acceptable to a plant | Local mode (§8) |
| CA key compromise | Offline backup, rotate CA, re-issue kits; audit log shows enrollments |
| Personal data / localisation rules | Host in Kazakhstan; store only work emails and names; privacy notice on registration |

---

## 13. What stays the same
- The model, `my_flower_app` training code, wind and solar processing, metrics, run folders.
- Flower 1.25.0 pin (re-check before any upgrade).
- Simulation mode (`run_flower_experiment.sh`) for research; the 10-site Compose stack stays as a
  local demo profile (`deploy/dev`).
