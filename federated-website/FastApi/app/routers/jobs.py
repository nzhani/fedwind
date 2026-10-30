"""
Jobs Router - Async training job management.

Endpoints:
  GET /api/job/{job_id}           - Poll job status and get results when done
  GET /api/job/{job_id}/progress  - Get latest round predictions for live chart
"""

import os
import csv
from fastapi import APIRouter, HTTPException
from app.services.job_store import job_store

router = APIRouter(prefix="/api")


@router.get("/job/{job_id}", summary="Poll training job status")
async def get_job(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/job/{job_id}/progress", summary="Get latest round predictions for live chart")
async def get_job_progress(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    exp_dir = job.get("exp_dir")
    if not exp_dir:
        return {"round": 0, "total_rounds": 0, "forecast": []}

    predictions_dir = os.path.join(exp_dir, "predictions")
    if not os.path.isdir(predictions_dir):
        return {"round": 0, "total_rounds": job.get("total_rounds", 0), "forecast": []}

    # Find the latest round that has a test prediction file
    latest_round = 0
    for fname in os.listdir(predictions_dir):
        if fname.startswith("client0_round") and fname.endswith("_test.csv"):
            try:
                round_num = int(fname.split("_round")[1].split("_")[0])
                latest_round = max(latest_round, round_num)
            except (ValueError, IndexError):
                pass

    if latest_round == 0:
        return {"round": 0, "total_rounds": job.get("total_rounds", 0), "forecast": []}

    # Read the latest round's predictions — use first sample row
    pred_file = os.path.join(predictions_dir, f"client0_round{latest_round}_test.csv")
    forecast = []
    try:
        with open(pred_file, "r") as f:
            reader = csv.DictReader(f)
            row = next(reader, None)  # first sample
            if row:
                pred_keys = sorted([k for k in row if k.startswith("pred_t")],
                                   key=lambda x: int(x.split("pred_t")[1]))
                true_keys = sorted([k for k in row if k.startswith("true_t")],
                                   key=lambda x: int(x.split("true_t")[1]))
                for i, (pk, tk) in enumerate(zip(pred_keys, true_keys)):
                    forecast.append({
                        "step": i + 1,
                        "predicted": float(row[pk]),
                        "actual": float(row[tk]),
                    })
    except Exception:
        pass

    return {
        "round": latest_round,
        "total_rounds": job.get("total_rounds", 0),
        "forecast": forecast,
    }
