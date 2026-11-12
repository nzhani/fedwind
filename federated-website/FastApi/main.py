"""
FedWind FastAPI Backend
=======================
Privacy-Preserving Wind Speed Forecasting with LLMs.

Architecture:  router  ->  service  ->  training_client (external repo)

Endpoints:
  GET    /health          Health check
  POST   /api/upload      Upload CSV file
  GET    /api/files        List uploaded files
  DELETE /api/files/{fn}   Delete a file
  POST   /api/train        Start centralized training
  *      /api/solar/*      Solar forecasting (skeleton, returns 501)
  GET    /api/sites        Site registry
  GET    /api/federation   Federation status
  *      /api/runs         Federated runs (start, stop, status, per-round metrics)
  GET    /api/forecast     Per-site forecast from the current global model
  *      /api/models       Promoted models per horizon

Start:  uvicorn main:app --reload
Docs:   http://localhost:8001/docs
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.health import router as health_router
from app.routers.upload import router as upload_router
from app.routers.train import router as train_router
from app.routers.jobs import router as jobs_router
from app.routers.federated import router as federated_router
from app.routers.feedback import router as feedback_router
from app.routers.solar import router as solar_router
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
        {"name": "Upload", "description": "CSV file upload and management"},
        {"name": "Training", "description": "Centralized model training"},
        {"name": "Federated", "description": "Federated learning (model updates)"},
        {"name": "Solar", "description": "Solar irradiance forecasting (skeleton - not implemented)"},
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
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health_router, tags=["Health"])
app.include_router(upload_router, tags=["Upload"])
app.include_router(train_router, tags=["Training"])
app.include_router(jobs_router, tags=["Training"])
app.include_router(federated_router, tags=["Federated"])
app.include_router(feedback_router, tags=["Feedback"])
app.include_router(solar_router, tags=["Solar"])
app.include_router(sites_router, tags=["Sites"])
app.include_router(runs_router, tags=["Runs"])
app.include_router(forecast_router, tags=["Forecast"])
app.include_router(models_router, tags=["Models"])
app.include_router(download.router)

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

    print()
    print("=" * 56)
    print("  FedWind API  v2.0.0")
    print("=" * 56)
    print("  Docs:   http://localhost:8001/docs")
    print()
    print("  POST /api/upload         Upload CSV")
    print("  GET  /api/files          List files")
    print("  DELETE /api/files/{fn}   Delete file")
    print("  POST /api/train          Start training")
    print("  POST /api/feedback       Submit feedback")
    print("  GET  /health             Health check")
    print("  *    /api/solar/*        Solar (skeleton, 501)")
    print("  GET  /api/sites          Site registry")
    print("  *    /api/runs           Federated runs")
    print("  GET  /api/forecast       Per-site forecast")
    print("  *    /api/models         Promoted models")
    print("=" * 56)
    print()


@app.on_event("shutdown")
async def shutdown_event():
    print("FedWind API shutting down.")
