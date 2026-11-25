"""
FedWind FastAPI Backend
=======================
Privacy-Preserving Wind Speed Forecasting with LLMs.

Architecture:  router  ->  service  ->  training_client (external repo)

Endpoints:
  GET    /health          Health check
  *      /api/auth/*      Register, log in, log out, current user (+ CSRF token)
  *      /api/admin/*     Users and audit log (admin)
  *      /api/sites        Active sites (public); register a site (operator)
  *      /api/my/sites     Own sites and their history; /api/admin/sites/{id}/{action} (admin)
  GET    /api/federation   Federation status
  *      /api/runs         Federated runs (start, stop, status, per-round metrics)
  GET    /api/forecast     Per-site forecast from the current global model
  *      /api/models       Promoted models per horizon (promote: admin)
  *      /api/feedback     Feedback board (delete and Telegram setup: admin)

Legacy upload/train/jobs/federated/download endpoints are mounted only with ENABLE_LEGACY_API=true,
and then only for admins: they include an open model-update endpoint (SITE_NETWORK_PLAN.md §2).

Start:  uvicorn main:app --reload
Docs:   http://localhost:8001/docs
"""

from dotenv import load_dotenv
load_dotenv()

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_admin
from app.db import DatabaseUnavailable, migrate
from app.routers.auth import router as auth_router
from app.routers.site_api import router as site_api_router
from app.routers.alerts import router as alerts_router

from app.routers.health import router as health_router
from app.routers.upload import router as upload_router
from app.routers.train import router as train_router
from app.routers.jobs import router as jobs_router
from app.routers.federated import router as federated_router
from app.routers.feedback import router as feedback_router
from app.routers.sites import router as sites_router
from app.routers.runs import router as runs_router
from app.routers.forecast import router as forecast_router
from app.routers.models import router as models_router

from app.services.feedback_db import init_feedback_db
from app.routers import download

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FedWind API",
    version="2.0.0",
    description="""
## Wind Speed Forecasting API

**Training Flow (Centralized & Federated):**
```
Frontend (CSV + config)
  -> POST /api/upload      (save file)
  -> POST /api/train       (run training - mode determines pipeline)
  <- TrainingResult        (metrics + forecast)
```

**Supported models:** GPT4TS, LLAMA, BERT, BART
**Training modes:** centralized, federated (FedAvg, FedProx, FedBN, FedPer, SCAFFOLD)
**CSV format:** NASA POWER hourly data (YEAR, MO, DY, HR, WS50M)
**Prediction lengths:** 1, 3, 6, 36, 72, 144, 432 steps
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Health", "description": "API health check"},
        {"name": "Accounts", "description": "Register, log in, users and audit log"},
        {"name": "Upload", "description": "CSV file upload and management"},
        {"name": "Training", "description": "Centralized model training"},
        {"name": "Federated", "description": "Federated learning (model updates)"},
        {"name": "Sites", "description": "Site registry"},
        {"name": "Runs", "description": "Federated runs on the always-on federation"},
        {"name": "Forecast", "description": "Per-site forecasts from the current global model"},
        {"name": "Models", "description": "Promoted global models"},
    ],
)


# ---------------------------------------------------------------------------
# CORS - allow frontend dev servers
# ---------------------------------------------------------------------------

import os as _os

_FRONTEND_URL = _os.environ.get("FRONTEND_URL", "")
_allow_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
]
if _FRONTEND_URL:
    _allow_origins.append(_FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # the site kit's file name
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health_router, tags=["Health"])
app.include_router(auth_router, tags=["Accounts"])
app.include_router(feedback_router, tags=["Feedback"])
# Before sites_router: its /api/admin/sites/{id}/{action} would otherwise catch /reissue-kit
app.include_router(site_api_router, tags=["Site connection"])
app.include_router(alerts_router, tags=["Alerts"])
app.include_router(sites_router, tags=["Sites"])
app.include_router(runs_router, tags=["Runs"])
app.include_router(forecast_router, tags=["Forecast"])
app.include_router(models_router, tags=["Models"])

# Legacy single-machine endpoints: off by default, admin-only when on
LEGACY_API = os.environ.get("ENABLE_LEGACY_API", "").lower() in ("1", "true", "yes")
if LEGACY_API:
    _admin_only = [Depends(require_admin)]
    app.include_router(upload_router, tags=["Upload"], dependencies=_admin_only)
    app.include_router(train_router, tags=["Training"], dependencies=_admin_only)
    app.include_router(jobs_router, tags=["Training"], dependencies=_admin_only)
    app.include_router(federated_router, tags=["Federated"], dependencies=_admin_only)
    app.include_router(download.router, dependencies=_admin_only)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    import os
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("models", exist_ok=True)
    os.makedirs("feedback", exist_ok=True)

    try:
        init_feedback_db()
    except Exception as e:
        print(f"WARNING: Could not connect to PostgreSQL — feedback DB unavailable. ({e})")
    try:
        applied = migrate()
        print(f"  Database migrations applied: {applied or 'none (up to date)'}")
        from app.services.site_registry import seed_from_file
        from app.settings import get_settings
        print(f"  Builtin sites imported from sites.json: {seed_from_file(get_settings())}")
    except DatabaseUnavailable as e:
        print(f"WARNING: accounts unavailable until the database is reachable ({e})")

    try:
        from app.services import site_ca
        from app.services.site_connection import start_maintenance
        created = site_ca.init_ca()
        print(f"  Site CA: {'created' if created else 'ready'} in {site_ca.ca_dir()}")
        print(f"  Site maintenance (CRL, Flower unregister): {'on' if start_maintenance() else 'off'}")
    except OSError as e:
        print(f"WARNING: site CA unavailable ({e}); kits and certificate enrollment will fail")

    try:
        from app.services import scheduler
        print(f"  Scheduled training: {'on (' + os.environ.get('TRAIN_SCHEDULE', '') + ')' if scheduler.start_background() else 'off (no TRAIN_SCHEDULE)'}")
    except ValueError as e:
        print(f"WARNING: scheduled training off: {e}")

    from app.services.notifications import start_background
    print(f"  Telegram alerts: {'on' if start_background() else 'off (no BOT_TOKEN, or NOTIFY_LOOP=off)'}")

    print()
    print("=" * 56)
    print("  FedWind API  v2.0.0")
    print("=" * 56)
    print("  Docs:   http://localhost:8001/docs")
    print()
    print("  *    /api/auth/*         Accounts and sessions")
    print("  *    /api/admin/*        Users, audit log (admin)")
    print("  POST /api/feedback       Submit feedback")
    if LEGACY_API:
        print("  *    legacy upload/train/federated endpoints (admin only)")
    print("  GET  /health             Health check")
    print("  GET  /api/sites          Site registry")
    print("  *    /api/runs           Federated runs")
    print("  GET  /api/forecast       Per-site forecast")
    print("  *    /api/models         Promoted models")
    print("=" * 56)
    print()


@app.on_event("shutdown")
async def shutdown_event():
    print("FedWind API shutting down.")
