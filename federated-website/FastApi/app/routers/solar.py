"""
Solar Router - SKELETON for solar irradiance forecasting.

Mirrors the wind endpoints under the /api/solar prefix.  Only /health is
live; every other endpoint calls a stub in solar_training_service.py that
raises NotImplementedError, returned here as HTTP 501.

Endpoints:
  GET    /api/solar/health                    Module status (skeleton)
  POST   /api/solar/upload                    Upload irradiance CSV
  GET    /api/solar/files                     List solar CSVs
  DELETE /api/solar/files/{filename}          Delete a solar CSV
  POST   /api/solar/train                     Start training -> job_id
  GET    /api/solar/job/{job_id}              Poll job status/result
  GET    /api/solar/job/{job_id}/progress     Live per-round forecast
  GET    /api/solar/model-update/skeleton     FL client model skeleton
  POST   /api/solar/model-update              FL client submits weights
  POST   /api/solar/model-update/aggregate    Aggregate a FL round
"""

from fastapi import APIRouter, File, UploadFile, HTTPException, status

from app.schemas import (
    UploadResponse,
    FileListResponse,
    SolarTarget,
    SolarTrainRequest,
    SolarJobResponse,
    SolarJobStatus,
    SolarProgressResponse,
    SolarHealthResponse,
    VALID_SOLAR_PREDICTION_LENGTHS,
)
from app.routers.federated import (
    ModelUpdate,
    ModelUpdateResponse,
    ModelSkeletonResponse,
    AggregateRequest,
    AggregateResponse,
)
from app.services import solar_training_service as solar


router = APIRouter(prefix="/api/solar")

ENDPOINTS = [
    "GET /api/solar/health",
    "POST /api/solar/upload",
    "GET /api/solar/files",
    "DELETE /api/solar/files/{filename}",
    "POST /api/solar/train",
    "GET /api/solar/job/{job_id}",
    "GET /api/solar/job/{job_id}/progress",
    "GET /api/solar/model-update/skeleton",
    "POST /api/solar/model-update",
    "POST /api/solar/model-update/aggregate",
]

NOT_IMPLEMENTED = {501: {"description": "Solar pipeline not implemented yet (skeleton)"}}


def _call(fn, *args, **kwargs):
    """Run a service stub and map NotImplementedError -> 501."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=SolarHealthResponse,
    summary="Solar module status",
    description="Returns solar module status, supported targets and prediction lengths.",
)
async def solar_health():
    return SolarHealthResponse(
        status="skeleton",
        implemented=False,
        module="solar",
        targets=[t.value for t in SolarTarget],
        prediction_lengths=VALID_SOLAR_PREDICTION_LENGTHS,
        endpoints=ENDPOINTS,
    )


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=UploadResponse,
    responses=NOT_IMPLEMENTED,
    summary="Upload a solar irradiance CSV",
    description="NASA POWER hourly CSV: YEAR, MO, DY, HR, ALLSKY_SFC_SW_DWN [, CLRSKY_SFC_SW_DWN, T2M].",
)
async def upload_solar_file(file: UploadFile = File(...)):
    content = await file.read()
    await file.close()
    return _call(solar.save_solar_upload, file.filename or "unknown.csv", content)


@router.get(
    "/files",
    response_model=FileListResponse,
    responses=NOT_IMPLEMENTED,
    summary="List uploaded solar CSV files",
)
async def list_solar_files():
    return _call(solar.list_solar_files)


@router.delete(
    "/files/{filename}",
    responses=NOT_IMPLEMENTED,
    summary="Delete an uploaded solar CSV file",
)
async def delete_solar_file(filename: str):
    return _call(solar.delete_solar_file, filename)


# ---------------------------------------------------------------------------
# Training jobs
# ---------------------------------------------------------------------------

@router.post(
    "/train",
    response_model=SolarJobResponse,
    responses=NOT_IMPLEMENTED,
    summary="Start solar training (centralized or federated)",
    description="Returns a job_id immediately. Poll GET /api/solar/job/{job_id}.",
)
async def train_solar(request: SolarTrainRequest):
    return _call(solar.start_solar_training, request.filename, request.config)


@router.get(
    "/job/{job_id}",
    response_model=SolarJobStatus,
    responses=NOT_IMPLEMENTED,
    summary="Poll solar training job status",
)
async def get_solar_job(job_id: str):
    return _call(solar.get_solar_job, job_id)


@router.get(
    "/job/{job_id}/progress",
    response_model=SolarProgressResponse,
    responses=NOT_IMPLEMENTED,
    summary="Latest round predictions for the live chart",
)
async def get_solar_job_progress(job_id: str):
    return _call(solar.get_solar_progress, job_id)


# ---------------------------------------------------------------------------
# Federated client flow
# ---------------------------------------------------------------------------

@router.get(
    "/model-update/skeleton",
    response_model=ModelSkeletonResponse,
    responses=NOT_IMPLEMENTED,
    summary="Get solar model skeleton for local training",
)
async def get_solar_model_skeleton():
    return _call(solar.get_solar_model_skeleton)


@router.post(
    "/model-update",
    response_model=ModelUpdateResponse,
    responses=NOT_IMPLEMENTED,
    summary="Submit solar model update from a federated client",
)
async def submit_solar_model_update(update: ModelUpdate):
    return _call(solar.submit_solar_model_update, update.model_dump())


@router.post(
    "/model-update/aggregate",
    response_model=AggregateResponse,
    responses=NOT_IMPLEMENTED,
    summary="Aggregate solar model updates for a round",
)
async def aggregate_solar_round(req: AggregateRequest):
    return _call(solar.aggregate_solar_round, req.round_number, req.prediction_length)
