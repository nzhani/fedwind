# Demo day plan: new frontend + a working simulation of the whole platform

Execution plan for the demo. It pulls together:
- `federated-website/DESIGN_SPEC.md`: visual system and marketing pages
- `federated-website/APP_PAGES_SPEC.md`: Sites, Admin, Login/Register pages
- `DEMO_SIMULATION_PLAN.md`: endpoints, data model, simulated site agent

Everything here runs on one laptop (CPU, Docker).

---

## 0. The story the audience sees (≈ 12 minutes)

> Plants in Kazakhstan train one forecasting model together without sharing their data. A new plant
> registers, the FedWind team approves it, the plant installs a kit, and within a minute it is
> online and gets **power forecasts from the newest shared model**. When the federation trains a
> better model, every plant's forecast switches to it.

Three roles, two browser windows (normal + private) and one terminal:

| Role | Who | Window |
|---|---|---|
| Visitor | anyone | window A, logged out |
| Plant owner (operator) | "Zhanatas Energy LLP" | window A after registering |
| Admin | FedWind team | window B (private window) |
| The plant itself | simulated site agent | terminal |

---

## 1. Locked decisions for the demo
| Topic | Decision |
|---|---|
| Accent | signal orange family (`DESIGN_SPEC.md` §2.1); accent-dark for small text |
| Fonts | Instrument Serif (one hero line), Geist Sans (everything), Fragment Mono (numbers, ids) |
| **What we forecast** | **Power first**: every forecast shows MW and % of capacity; wind speed / irradiance as the second tab. Lab sites: power of a 2 MW reference turbine (labelled). Plants: from their registered capacity (turbines × rated power, or PV MW) |
| Model behind a forecast | always the **newest promoted model** for that energy type and horizon, shown with its version, sites, rounds, skill and promotion time |
| Plant forecasts | central forecasting from the recent window the agent sends (consent "Central forecasting") |
| Plants in training | not yet (needs M6); plants appear greyed in Experiments: "joins training after the Flower connection (M6)" |
| Simulation | only the plant (site agent with NASA POWER data at the plant's coordinates); every simulated thing is labelled **Simulated** |
| Accuracy numbers | from small CPU demo runs, labelled "demo model (CPU)"; real numbers come from the GPU runs |

---

## 2. Work list (in order)

Each item ends with its check. Estimates are for one developer.

### A. Backend for the plant journey (`DEMO_SIMULATION_PLAN.md` Tier 1): ✅ done 2026-11-20 (API tests 55)
- [x] Migration `003_site_connection.sql`: `enrollment_tokens`, `site_credentials`, `site_heartbeats`, `site_quality`, `forecast_inputs`.
- [x] `POST /api/my/sites/{id}/kit` (POST + CSRF, it issues a token): zip with personalised README, `docker-compose.yml`, `.env`, one-time token (72 h; a new download replaces the old token).
- [x] `/site-api/enroll`, `/site-api/heartbeat`, `/site-api/quality`; site identity resolver (`SITE_AUTH_MODE=token`, refused in production).
- [x] Site detail and list gain `progress`, `connection` (online if heartbeat < 3 × 30 s), `kit`, `can_train`.
- [x] Revoke and `reissue-kit` revoke credentials; suspended sites get `status: suspended` in the heartbeat answer.
- [x] `GET /api/admin/overview` (tiles + "needs attention"); audit filters (`action`, `target`, `before`).
- [x] Runs and Experiments only use sites with `can_train`.
- **Check:** API tests for token reuse, expiry, revoked key, suspended heartbeat, roles; all existing tests still pass.

### B. Site agent and simulation command: ✅ done 2026-11-20 (agent tests 6)
- [x] `site_agent/` (enroll → heartbeat loop → daily quality → hourly forecast window), `nasa_power` source (cached per plant), small Docker image.
- [x] `deploy/sim/run_site.sh <kit.zip>`: unzip to `deploy/sim/sites/<id>/`, set `DATA_SOURCE=nasa_power`, `docker compose up -d`; `deploy/sim/stop_site.sh <id>`.
- **Check:** a kit downloaded from the website turns the plant Online within 60 s; stopping it shows Offline within 90 s.

### C. Power forecasts from the newest model: ✅ done 2026-11-20 (API tests 58, inference 17, agent 7)
- [x] `inference-central` service: `POST /forecast-window` (wind: speed → power with the plant's turbines, hub-height shear for 50 m data; solar: k* → GHI → PV power), reads no files.
- [x] `/site-api/forecast-input` stores the window the agent sends (consent + active only, 30-day retention, out-of-range hours flagged).
- [x] `GET /api/forecast` for plant sites via `inference-central` (private unless the plant made forecasts public); every response adds `power_kw`, `capacity_kw`, `capacity_factor`, `power_basis` (plant / reference 2 MW wind, 1 MW PV for lab sites), `source`, `simulated`, and `model` {run id, energy, horizon, sites, rounds, strategy, skill, promoted_at, promoted_by}. The frontend shows MW.
- **Check:** ✅ live: Zhanatas (simulated, 100 MW) forecast through `inference-central` with the promoted wind run (h1, the only wind model so far); anonymous callers get 422. Promoting a newer run changes the `model` block (API test). 72 h wind and solar plant forecasts need the item F runs.

### D. Frontend foundation: ✅ done 2026-11-20
- [x] Tokens (colours, radii, spacing, shadows) as CSS variables in `app/globals.css`; the shadcn variables are mapped onto them, so older pages follow. Fonts are **self-hosted** with `next/font/local` (`app/fonts/`, OFL), so builds and the demo need no internet.
- [x] Components in `components/fw/`: nav pill (with account menu), pill buttons S/M/L (+ text-roll hover), page header, card, stat tile, status pill (dot), table, form fields, segmented control, toggle card, sticky action bar, toast, empty state, skeleton, confirm-with-reason, stepper; plant panels in `components/site-panels.tsx`.
- **Check:** ✅ `tsc` clean; `next build` passes (22 routes). No separate component sheet: every component is in use on the pages.

### E. Pages: ✅ done 2026-11-20 (Home uses a drawn product mock-up instead of a screenshot; the info pages got the token restyle only)

| Page | Changes |
|---|---|
| **Home** `/` | rebuilt in the reference's band rhythm: orange hero with glow + serif line + FedWind mark; two-tone statement; orange "Forecasts" band with a screenshot of the Forecast page; ink band with three stacked cards (Train at the plant · Only model updates travel · One shared model forecasts every site); marquee of federation sites; inset orange CTA "Register your plant"; footer with big links |
| **Login / Register** | split layout (orange panel + form); Register shows "what happens next" |
| **Forecast** `/forecast` | **power-first**: Wind/Solar switch → site list includes approved plants that are online (Simulated pill); chart power (MW) with % capacity axis; second tab speed / irradiance; **model card** ("Global wind model · run … · 5 sites · 3 rounds · skill +0.02 · promoted 2 min ago by Admin"); history + forecast |
| **Training** `/training`, run page | restyled tables and cards; run page keeps "Use for forecasts" (admin) and shows "Currently serving forecasts" when promoted |
| **Experiments** | restyle; plants greyed with the M6 note |
| **Sites** `/sites`, `/sites/new`, `/sites/[id]` | per `APP_PAGES_SPEC.md` §2: stat tiles, table with Connection; two-column form; plant page with **progress stepper**, **Install the site kit** card, **Connection** card, **Forecast** card (sparkline in MW + "Open forecast →"), Activity |
| **Admin** `/admin/*` | Overview (tiles, needs attention, recent activity), Approvals (master–detail), Sites (filters, ⋯ menu), Users (side sheet), Audit (filters) |
| Solar / About / Architecture / Data source / Instructions | restyle with the new tokens only (no layout work) |

- **Check:** ✅ `next build` passes; focus ring on every control; no horizontal scroll at 375 px (Forecast, plant page). Checked live in the browser: register a plant → Approvals → approve → kit card → kit download (POST, file name header) → revoke with a reason; plant page Online with connection, quality bars and forecast; Forecast with the model card; all admin tabs; Training, run page ("Currently serving …"), Experiments (plant greyed, M6 note).

### F. Demo data and reset: ✅ done 2026-11-20 (API tests 62, agent tests 8)
- [x] The demo stack's data lives in **`~/fedwind-demo-data`** (runs, promoted models, lab site data, model cache), outside the repo and outside any temp folder. Every compose command during the demo needs `FEDWIND_DATA=$HOME/fedwind-demo-data` (it's in `deploy/sim/demo.env`).
- [x] Short CPU runs (5 sites, 72 h, 2 rounds, seq_len 48, 1 LLM layer, seed 2021; ≈ 5 min each):

  | Run | Id | Data | MAE | Skill vs persistence | Role |
  |---|---|---|---|---|---|
  | wind **A** | `wind-fedavg-h72-20261119T201846Z` | 10 % | 2.40 m/s | +0.075 (every site positive) | promoted; forecasts start here |
  | wind **B** | `wind-fedavg-h72-20261119T203047Z` | 20 % | 2.34 m/s | +0.097 (better at every site) | **not** promoted: step 9 switches to it |
  | solar **C** | `solar-fedavg-h72-20261119T150357Z` | 10 % | 71 W/m² | +0.02 vs smart persistence | promoted |

  Checked live: promoting B changes Zhanatas' 72 h forecast (model card run/data/skill, peak 53.8 → 40.1 MW); A was promoted back. The model card labels these "Demo model · N % of the data".
  `wind-fedavg-h72-20261119T202331Z` (3 rounds, same seed) is unused: its best checkpoint is round 2, i.e. identical to A.
- [x] `deploy/sim/demo_reset.sh` (settings in `deploy/sim/demo.env`, copied from `demo.env.example`):
  - stops every simulated plant and keeps its NASA POWER data in `deploy/sim/nasa-cache/`; `run_site.sh` reuses it for a plant at the same coordinates, so a re-registered Zhanatas works offline
  - removes the registered plants, their organizations and every non-admin account (`python -m app.cli demo-reset`, dry run without `--yes`; refused with `ENV=production`)
  - promotes run A and run C again ("promoted by FedWind team")
  - keeps admins, lab sites, all runs and the audit log (the reset is logged as `demo.reset`)
  - shows what would go and asks you to type `reset`
- [x] **Example solar plant, already online when the demo starts:** *Shu Valley Solar Park* (`shu-valley-solar-park-0eb0`, 50 MW, 43.60 N 73.76 E, organization *Steppe Sun Energy LLP*, operator `operator@steppesun.test`), registered → approved → kit → simulated through the real API flow. Central forecasting and public forecasts are on, so visitors see it under Forecast → Solar. The reset keeps it (`DEMO_KEEP_PLANTS` in `demo.env`, `demo-reset --keep`). Its operator password was generated and discarded; to log in as that operator, set one with `python -m app.cli set-password --email operator@steppesun.test`.
  - NASA POWER's hourly irradiance lags about **3 months** (newest: 31 Aug 2026), so the solar agent looks back 150 days and the plant's "now" is 31 Aug. Wind lags about 3 days.
- [x] Simulated plants now run as your user (`compose.sim.yml`), so `stop_site.sh --forget` can delete their folders (it falls back to a container for older root-owned ones).
- [ ] Admin account for the demo: `python -m app.cli create-admin` (password typed by you, kept out of chat and git), or the existing `admin@fedwind.test` from `deploy/.env`.
- **Check:** `demo-reset` tested (dry run changes nothing; reset keeps admins, lab sites, runs; re-promotes; refused in production); live dry run lists 2 plants, 3 non-admin accounts, 2 organizations, keeps 2 admins. The live reset and the full script (§3) twice are item G.
- Lab sites' data ends on 25 Nov 2024 (trimmed NASA files), so lab forecasts are issued then (the page shows the year); the simulated plant uses recent NASA data.

### F+. Telegram alerts and the federation map: ✅ done 2026-11-20 (API tests 65)
- [x] **Telegram alerts** (`app/services/notifications.py`, migration 004): people connect from the account menu → *Telegram alerts* (one-time `t.me` link, press Start). Operators hear about their plant: approved / rejected / suspended / resumed / revoked / kit re-issued, online, offline, back online. Admins (and `SUPPORT_CHAT_ID`) hear about new plants waiting for approval and plants going offline. Events come from the audit log; a background loop queues and sends them with retries, polling Telegram for Start (no public address needed; the feedback webhook handles it when one is set). Messages carry names, states, reasons and links only.
- [x] **Map of the federation** (`components/federation-map.tsx`, Natural Earth outline embedded by `scripts/make_kz_map.py`, no tiles, works offline): on Home (lab sites + plants with public forecasts, click → forecast) and on Admin → Overview (every site, live: online plants pulse green, offline grey, not-active dashed; click → plant page).
- **To switch alerts on for the pitch** (you, not in chat): create a bot with @BotFather, put its token in `deploy/.env` as `BOT_TOKEN=…` (optionally `SUPPORT_CHAT_ID` for a team group), restart the API (`docker compose -f deploy/docker-compose.yml up -d api`; its log says `Telegram alerts: on`), then connect Telegram from the account menu as the admin (window B) and as the operator right after registering (window A). Your phone then buzzes on **Approve** (step 4) and when the plant comes **online** (step 7). Telegram needs internet; without it the demo works the same, just silent.

### G. Rehearsal and checks: ≈ 1 h
- [x] All tests: ML 28, inference 17, API 65, agent 8 (all pass, 2026-11-20); `tsc` clean; `next build` passes (web image).
- [ ] Full demo run in two browser windows with a timer.
- [ ] Screenshots of every step as a fallback (`docs/demo/`).

**Total ≈ 21–26 h.** It won't all fit in one sitting, so the must-have line is:
- **Must:** A, B, C, D, Home, Forecast, Sites pages, Admin Overview + Approvals, Login/Register, F, G
- **Should:** Admin Sites/Users/Audit polish, Training/Experiments restyle, text-roll hover
- **Could:** Home motion (stacking cards, marquee), restyle of the info pages

---

## 3. Demo script (with what each step proves)

| # | Window | Action | What it shows |
|---|---|---|---|
| 1 | A (visitor) | Home: scroll the four bands | the idea: data stays at the plant, one shared model |
| 2 | A | Forecast → Wind → Almaty → 72 h; then Solar → *Shu Valley Solar Park* | power forecast (MW, % capacity) from the **newest shared model**; model card; a solar plant already in the federation (Simulated, public) |
| 3 | A | Register "Zhanatas Energy LLP" → Register plant "Zhanatas Wind Farm" (43.57 N, 69.75 E, 40 × 2.5 MW, central forecasting on) | onboarding; plant page at *Waiting for approval* |
| 4 | B (admin) | Admin Overview: "1 waiting" → Approvals → review → **Approve** | governance; audit trail starts |
| 5 | A | Plant page: stepper *Approved* → **Download kit** | the kit (open the zip briefly: README, compose, token) |
| 6 | Terminal | `deploy/sim/run_site.sh ~/Downloads/fedwind-site-zhanatas-wind-farm-….zip` | the plant installs the kit like a real plant would |
| 7 | A | Plant page turns **Online · Simulated**; Connection: heartbeat, data until, quality bars | the plant is connected; only counts are reported |
| 8 | A | Plant page Forecast card → Forecast page for Zhanatas: **100 MW plant, next 72 h** | the plant gets power forecasts from the shared model on day one (cold start, FR-15) |
| 9 | B | Training → wind run B → **Use for forecasts** | the federation trained a newer model |
| 10 | A | Refresh the forecast: model card now says run B, "promoted 1 min ago"; curve changes | every plant switches to the newest model automatically |
| 11 | B | Sites → Zhanatas → **Suspend** "Maintenance" | control; A's plant page shows *Suspended* with the reason; the agent is told on its next heartbeat |
| 12 | B | **Resume**; Audit log filtered to the plant | everything recorded: who, what, when |
| 13 | Talk | "What's real vs simulated" (§4) + next steps (GPU runs, mTLS, plants in training) | honesty |

---

## 4. What to say about the simulation
- **Real:** website, accounts and roles, registration and approval, kit, enrollment, heartbeats, the
  shared models, forecasting, the audit log. The same endpoints serve real plants later.
- **Simulated:** the plant. Its "measurements" are NASA POWER weather for its coordinates, and its
  power is computed from its registered turbines or panels. NASA publishes wind speed about 3 days
  late and hourly irradiance about 3 months late, so the simulated solar plant lives at the end of
  August; a real plant sends its own measurements from today.
- **Not yet:** plants training in the federation (Flower connection, M4–M6) and certificate-based
  plant identity (M3/M4). Today's demo models are small CPU runs; accuracy comes from the GPU runs.

---

## 5. Fallbacks
| If | Then |
|---|---|
| Docker or the agent misbehaves | `stop_site.sh`; show the pre-enrolled backup plant (enrolled during the rehearsal) |
| A page breaks | screenshots in `docs/demo/` in the same order as §3 |
| Laptop is slow | stop training containers; the demo needs only db, api, web, inference (lab + central) and the agent |
| Network is down | nothing in the demo needs the internet; NASA data for the demo plants is cached during the rehearsal |

---

## 6. After the demo
`SITE_NETWORK_PLAN.md` continues where this leaves off:
- M3/M4: certificates and the gateway; the identity resolver switches to `mtls`.
- M5: the real CSV data source.
- M6: plants train in runs (`can_train`).
- M7: local forecasting mode.
- GPU runs for real accuracy, measured power where available.
