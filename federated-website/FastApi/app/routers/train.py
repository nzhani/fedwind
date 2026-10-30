"""
Training Router - Triggers centralized or federated model training.

Endpoints:
  POST /api/train  -  Start training, returns job_id immediately
  GET  /api/job/{job_id}  -  Poll job status (in jobs.py)
"""

import threading
from fastapi import APIRouter, HTTPException, status
from app.schemas import TrainRequest
from app.services.job_store import job_store

router = APIRouter(prefix="/api")


def _run_training_job(job_id: str, filename: str, config):
    from app.services.training_service import start_training
    try:
        result = start_training(filename, config, job_id=job_id)
        job_store.complete(job_id, result.model_dump())
    except ValueError as e:
        job_store.fail(job_id, str(e))
    except RuntimeError as e:
        job_store.fail(job_id, str(e))
    except Exception as e:
        job_store.fail(job_id, f"Unexpected error: {str(e)}")


@router.post(
    "/train",
    summary="Start training (centralized or federated)",
    description=(
        "Triggers model training using a previously uploaded CSV file. "
        "Returns a job_id immediately. Poll GET /api/job/{job_id} for status and results."
    ),
)
async def train(request: TrainRequest):
    # Basic validation before spawning thread
    import os, csv
    from app.services.training_service import UPLOAD_DIR, validate_csv, validate_config

    file_path = os.path.abspath(os.path.join(UPLOAD_DIR, request.filename))
    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Uploaded file not found: {request.filename}",
        )

    try:
        validate_csv(file_path)
        validate_config(request.config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Create job and run training in background thread
    job_id = job_store.create()
    thread = threading.Thread(
        target=_run_training_job,
        args=(job_id, request.filename, request.config),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "running"}
