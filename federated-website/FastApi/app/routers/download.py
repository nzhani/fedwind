"""
Download router — serves training artefacts (CSV files) from a finished
experiment directory.  The exp_dir is passed as a URL-encoded query param
so the frontend can offer direct download links.
"""

import os
import urllib.parse
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/download", tags=["download"])

ALLOWED_FILES = {
    "training_summary": "training_summary.csv",
    "timing_summary":   "timing_summary.csv",
}

def _safe_path(exp_dir: str, filename: str) -> str:
    """Resolve and validate the file path to prevent path traversal."""
    exp_dir   = os.path.realpath(urllib.parse.unquote(exp_dir))
    file_path = os.path.realpath(os.path.join(exp_dir, filename))
    # Must stay inside exp_dir
    if not file_path.startswith(exp_dir):
        raise HTTPException(status_code=400, detail="Invalid path")
    return file_path


@router.get("/training_summary")
async def download_training_summary(exp_dir: str = Query(...)):
    path = _safe_path(exp_dir, "training_summary.csv")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="training_summary.csv not found")
    return FileResponse(
        path,
        media_type="text/csv",
        filename="training_summary.csv",
    )


@router.get("/timing_summary")
async def download_timing_summary(exp_dir: str = Query(...)):
    path = _safe_path(exp_dir, "timing_summary.csv")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="timing_summary.csv not found")
    return FileResponse(
        path,
        media_type="text/csv",
        filename="timing_summary.csv",
    )