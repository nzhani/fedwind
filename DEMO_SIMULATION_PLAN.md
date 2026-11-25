# Demo simulation plan: a fully working website, built on the real contracts

Goal for the demo: show the whole plant journey on one laptop: a plant registers, an admin approves
it, the operator downloads the site kit, the "plant" starts, and the website shows it **online**
(and, Tier 2, forecasting) without the lab GPU server or real plants.

Rule that keeps it from becoming a riddle later: **only the plant is simulated, never the platform.**
Every endpoint, table, status and page is the real one from `SITE_NETWORK_PLAN.md`. The simulated part
is one actor: the **site agent running with a simulated data source** (NASA POWER at the plant's
coordinates instead of the plant's SCADA). Replacing it with a real plant later means pointing the same
agent at a real data folder and adding the Flower connection (M4–M6); no API, page or table changes.

Pages: `federated-website/APP_PAGES_SPEC.md`. Visual system: `federated-website/DESIGN_SPEC.md`.

---

## 1. What is real and what is simulated

| Piece | In the demo | Later (real plants) | What changes |
|---|---|---|---|
| Website, API, Postgres, accounts, roles, audit | real | same | nothing |
| Site registry, approval, history | real (M2, done) | same | nothing |
| Enrollment token, kit download, enroll, heartbeat, quality | **real endpoints** (this plan) | same | nothing |
| Site identity on `/site-api/*` | `SITE_AUTH_MODE=token`: per-site key issued at enrollment | `SITE_AUTH_MODE=mtls`: gateway-verified client certificate (M3/M4) | only the identity resolver (one function) |
| Site agent program | real code (`site_agent/`) | same program | data source plug-in: `nasa_power` → `csv_inbox` (M5); adds tunnel + SuperNode (M4–M6) |
| Plant data | NASA POWER at the plant's coordinates | the plant's own export | config value `DATA_SOURCE` |
| Plant in training runs | **not yet**: shown as "joins training after M6" | SuperNode keyed by site id (M6) | `can_train` becomes true when a Flower node is registered |
| Plant forecasts (Tier 2) | central forecasting from the window the agent pushes (D1 central mode) | same | nothing |
| Lab sites (10 builtin) | unchanged: train and forecast as today | same | nothing |

Every simulated record says so: the agent reports `agent_kind: "simulated"`, stored with each
heartbeat and shown as a **Simulated** pill. Nothing is faked server-side.

---

## 2. Endpoints

Legend: ✅ exists · 🛠 build for the demo · ⏭ later milestone.

### 2.1 User API (`/api`, session cookie + CSRF, roles)

| Method & path | Who | Status | Purpose |
|---|---|---|---|
| `POST /api/auth/register` · `login` · `logout` · `GET /api/auth/me` | anyone / user | ✅ | accounts (M1) |
| `GET /api/admin/users` · `POST` · `PATCH /{id}` | admin | ✅ | users (M1) |
| `GET /api/admin/audit` | admin | ✅ | add filters `action`, `actor`, `target`, cursor `before` (Audit page §3.6) |
| `GET /api/sites` | public | ✅ | active sites only |
| `POST /api/sites` | operator | ✅ | register a plant (M2) |
| `GET /api/my/sites` | operator / admin | ✅ → 🛠 | add `connection` summary per site; admin filters `status`, `type`, `source`, `q` |
| `GET /api/my/sites/{id}` | owner / admin | ✅ → 🛠 | add `progress` (registered/approved/enrolled/online timestamps), `connection`, `kit` (whether a kit can be downloaded, token expiry) |
| `PUT /api/my/sites/{id}` | owner | ✅ | edit while waiting |
| `POST /api/admin/sites/{id}/{approve·reject·suspend·resume·revoke}` | admin | ✅ | decisions (M2); revoke also revokes credentials 🛠 |
| `POST /api/my/sites/{id}/kit` | owner / admin | ✅ | download (POST + CSRF: it issues a token, so another site must not be able to trigger it) `fedwind-site-<id>.zip`; allowed while `approved` and not enrolled; **each download issues a new one-time token** (72 h) and invalidates the previous unused one (the database keeps only token hashes, so a kit can't be rebuilt) |
| `POST /api/admin/sites/{id}/reissue-kit` | admin | ✅ | lost kit or server: revoke the site's credentials, status `active`/`suspended` → `approved`, operator downloads a new kit |
| `GET /api/admin/overview` | admin | ✅ | stat tiles + "needs attention" list (§3.2 of the page spec) |
| `GET /api/forecast?site=&horizon=` | public (respecting consents) | ✅ | lab sites as today; plant sites from central forecasting (§2.3), owner/admin only unless the plant made forecasts public; adds `power_kw`, `capacity_kw`, `capacity_factor`, `power_basis`, `source`, `simulated` and the model card |
| runs, federation, models | admin for writes | ✅ | unchanged; runs only use sites with `can_train` 🛠 |

### 2.2 Site API (`/site-api`, used only by site agents)

Identity (`current_site` dependency) by `SITE_AUTH_MODE`:
- `token` (demo, development): `Authorization: Bearer fws_<random>`; the key is issued once at
  enrollment and stored as a SHA-256 hash in `site_credentials`.
- `mtls` (M4): the gateway verifies the client certificate and sets `X-Site-Id`; the API accepts
  that header only from the gateway (internal network + shared secret). The API refuses to start
  with `token` mode when `ENV=production`.

| Method & path | Auth | Status | Body → response |
|---|---|---|---|
| `POST /site-api/enroll` | one-time token | ✅ | `{token, agent: {kind, version}, flower_public_key?}` → `{site_id, site_key, config: {heartbeat_s, energy_type, lat, lon, timezone, capacity_kw}}`. Marks the token used, creates the credential, `approved → active`, audit `site.enroll`. In `mtls` mode the body also carries a CSR and the answer a certificate (M3). `flower_public_key` is stored now and registered with Flower in M6 |
| `POST /site-api/heartbeat` | site key | ✅ | `{agent_kind, agent_version, last_data_hour, rows_today, gaps_today, disk_free_gb, gpu?}` → `{status, heartbeat_s}`: the agent learns if it was suspended or revoked |
| `POST /site-api/quality` | site key | ✅ | `{day, rows, gaps, flagged, curtailed}` (counts only) → `{ok}` |
| `POST /site-api/forecast-input` | site key | ✅ | `{end_hour, values[1..720]}`, a missing hour is `null` (only if the site consented to central forecasting, and only while active) → `{stored_hours, window_end, valid_hours}`; kept 30 days |
| `GET /site-api/models/current` · `/models/{id}/download` | site key | ⏭ M7 (local mode) | model distribution |
| `POST /site-api/forecasts` | site key | ⏭ M7 (local mode) | forecasts computed at the plant |
| `POST /site-api/renew` | certificate | ⏭ M8 | certificate renewal |

Errors: unknown/used/expired token → 401 (same message for all, rate-limited); revoked credential →
401; suspended site → heartbeat still accepted (`status: "suspended"`), forecast inputs refused (409).

### 2.3 Central inference (Tier 2)

| Method & path | Status | Purpose |
|---|---|---|
| `POST /forecast-window` on a new `inference-central` service (same image as `inference/`) | ✅ | `{energy_type, horizon, model_path, end_hour, values[], lat, lon, capacity_kw, equipment, measured_at_m}` → forecast points. Wind: power from the plant's turbines (count × rated power, generic curve shape). Solar: GHI via clear sky at the plant's coordinates, PV power from capacity. It never reads site files: input comes only from the request |

The API's `GET /api/forecast` for a plant site: latest stored window ≥ `seq_len` hours → call
`/forecast-window` with the promoted model of that energy type and horizon → return the same
`ForecastResponse` shape as for lab sites (actuals = the window's last hours).

---

## 3. Data model (migration `003_site_connection.sql`)

| Table | Columns |
|---|---|
| `enrollment_tokens` | id, site_id, token_hash, created_by, created_at, expires_at, used_at, superseded_at |
| `site_credentials` | id, site_id, kind (`token` · `cert`), secret_hash (token) / cert_serial + not_after (cert), flower_pubkey, flower_node_id (M6), agent_kind, created_at, revoked_at |
| `site_heartbeats` | site_id, at, agent_kind, agent_version, last_data_hour, rows_today, gaps_today, payload jsonb (latest row per site kept + 7 days history) |
| `site_quality` | site_id, day, rows, gaps, flagged, curtailed (primary key site_id + day) |
| `forecast_inputs` (Tier 2) | site_id, hour, value, mask (30-day retention) |

Derived, not stored:
- `connection.state`: online if the last heartbeat is younger than 3 × `heartbeat_s` (demo 30 s;
  production 300 s); otherwise offline; "never" before enrollment.
- `progress`: registered (`created_at`), approved/rejected (`decided_at`), enrolled (credential
  `created_at`), first online (first heartbeat).
- `can_train`: builtin site with a partition id (today), or plant with a registered Flower node (M6).

---

## 4. The site agent (`site_agent/`, one program for simulation and real plants)

```
site_agent/
  agent.py           enroll once (token → site key, saved in secrets/), then every heartbeat_s:
                     read the newest data from the source → heartbeat; daily → quality;
                     hourly (if consented) → forecast-input. Obeys status "suspended"/"revoked".
  sources/
    nasa_power.py    SIMULATION: hourly data for the plant's lat/lon from NASA POWER
                     (wind WS50M / solar ALLSKY), cached; "now" = the newest hour NASA has
    csv_inbox.py     REAL (M5): files dropped in data/inbox/ by the plant, data contract checks
  Dockerfile         python:3.12-slim + requests (small; no torch)
```

The **kit** (`POST /api/my/sites/{id}/kit`) already has the final layout from `SITE_NETWORK_PLAN.md` §5.1:
`README.md` (personalised), `docker-compose.yml` (service `agent`; tunnel and SuperNode
commented as "added in M4–M6"), `.env` (SITE_ID, ENERGY_TYPE, PORTAL_URL, SITE_API_URL, LAT, LON,
`DATA_SOURCE=csv_inbox`), `enrollment.token`, `ca.crt` (placeholder until M3 PKI), `data/README.md`.

Demo command: `deploy/sim/run_site.sh <kit.zip>` unzips the kit into `deploy/sim/sites/<id>/`, sets
`DATA_SOURCE=nasa_power` and `PORTAL_URL=http://host.docker.internal:8001`, and runs the same
`docker compose up -d`. So the demo installs the kit exactly as a plant would, with one setting changed.

---

## 5. Pages that use these endpoints (see `APP_PAGES_SPEC.md`)

| Page | Endpoints |
|---|---|
| `/sites` | `GET /api/my/sites` (with connection) |
| `/sites/new` | `POST /api/sites` |
| `/sites/[id]` | `GET /api/my/sites/{id}`, `POST …/kit`, `PUT` (edit), admin decisions |
| `/admin` | `GET /api/admin/overview`, `GET /api/admin/audit?limit=8` |
| `/admin/approvals` | `GET /api/my/sites?status=registered`, approve/reject |
| `/admin/sites` | `GET /api/my/sites` (filters), decisions, `reissue-kit` |
| `/admin/users` | users endpoints |
| `/admin/audit` | `GET /api/admin/audit` (filters, cursor) |
| `/forecast` (Tier 2) | `GET /api/sites`, `GET /api/forecast` |
| `/experiments` | `GET /api/sites` + `can_train` (plants shown greyed: "joins training after M6") |

---

## 6. Demo script

1. **Home** (new design): the story in four bands.
2. **Register** as an operator ("Zhanatas Energy LLP") → **Register plant** "Zhanatas Wind Farm"
   (43.57 N, 69.75 E, 100 MW, 40 turbines) → plant page: stepper at *Registered*.
3. In a second browser profile, **log in as admin** → Overview shows "1 waiting" → **Approvals** →
   review sheet → **Approve**.
4. Operator's plant page: stepper at *Approved*, **Install the site kit** card → **Download kit**.
5. Terminal: `deploy/sim/run_site.sh ~/Downloads/fedwind-site-zhanatas-wind-farm-xxxx.zip`.
   Within ~30 s the plant page shows **Online · Simulated**, the stepper reaches *Online*, Activity lists
   *Kit installed* and *Online*; admin Overview "Online now +1".
6. (Tier 2) **Forecast** → Wind → Zhanatas Wind Farm → 72 h forecast from the global wind model,
   power for 40 × 2.5 MW turbines.
7. **Training**: finished wind and solar runs on the lab sites; explain that plants join runs when
   their Flower connection lands (M4–M6), which the plant page already says.
8. Admin **suspends** the plant with a reason → next heartbeat answers "suspended" → the plant
   page shows *Suspended* with the reason; **resume**.
9. **Audit log**: every step above, with actors and times.

---

## 7. Scope, order and effort (one developer)

| Tier | Work | Effort |
|---|---|---|
| **1 Backend** | migration 003; kit endpoint + zip builder; enroll, heartbeat, quality; identity resolver (`token` mode, `mtls` refusal stub); `can_train` filter for runs; connection/progress in site detail and list; admin overview; audit filters; revoke also revokes credentials; tests | 4–5 h |
| **1 Agent** | `site_agent/` with `nasa_power` source, Dockerfile, `deploy/sim/run_site.sh` | 2 h |
| **1 Frontend** | tokens + fonts + nav pill + footer; home page per `DESIGN_SPEC.md` §7.2; app shell; Sites list, Register plant, Plant page (stepper, kit card, connection card); Admin overview + approvals + users + audit | 8–10 h |
| **2** | central forecasting (`forecast-input`, `inference-central`, plant forecasts on `/forecast`) | 3–4 h |
| **later** | M3 PKI and mTLS, M4 gateway, M5 CSV source + tunnel, M6 plant SuperNodes in runs, M7 local mode | per `SITE_NETWORK_PLAN.md` |

If the time runs short, cut in this order:
1. Tier 2.
2. The admin Sites and Audit filters (the existing tables stay).
3. The home-page motion (keep the static design).

Never cut the things that make it honest:
- the Simulated labels
- the `can_train` filter
- the real endpoints

---

## 8. How it grows into the real system (no rewrites)
| Later step | Change |
|---|---|
| M3 PKI | enroll also signs a CSR; credential kind `cert`; `ca.crt` in the kit becomes real |
| M4 gateway | set `SITE_AUTH_MODE=mtls`; `/site-api` and Flower Fleet behind the mTLS gateway; the kit gains the tunnel service |
| M5 real data | kit default `DATA_SOURCE=csv_inbox` (already the default in the real kit); data contract checks in the agent |
| M6 training | agent starts the SuperNode with `site=<id>`; enroll's `flower_public_key` is registered with Flower; `can_train` true; runs select by site id |
| M7 forecasting | local mode endpoints for sites without the central consent |
