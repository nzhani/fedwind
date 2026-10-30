"""
Upload Router - Handles CSV file uploads for centralized learning.

Endpoints:
  POST   /api/upload          - Upload one or more CSV files
  GET    /api/files            - List uploaded files
  DELETE /api/files/{filename} - Delete a file
"""

import os
import csv
import shutil
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, File, UploadFile, HTTPException, status
from app.schemas import UploadResponse, FileInfo, FileListResponse, FileListItem


router = APIRouter(prefix="/api")

UPLOAD_DIR = "uploads"


# ---------------------------------------------------------------------------
# POST /api/upload  -  Accept one or more CSV files
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a CSV file for centralized training",
    description=(
        "Accepts a single CSV file (NASA POWER hourly format: YEAR,MO,DY,HR,WS50M). "
        "The file is saved to the uploads/ directory. Use the returned `filename` "
        "when calling POST /api/train."
    ),
)
async def upload_file(file: UploadFile = File(...)):
    """Save an uploaded CSV and return file metadata."""

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are accepted.",
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Generate a unique filename to avoid collisions
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    # Save to disk
    try:
        with open(file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e}",
        )
    finally:
        await file.close()

    # Read CSV metadata
    size_bytes = os.path.getsize(file_path)
    rows = 0
    column_names: List[str] = []
    preview: list = []

    try:
        with open(file_path, "r") as f:
            reader = csv.DictReader(f)
            column_names = reader.fieldnames or []
            for i, row in enumerate(reader):
                if i < 5:
                    preview.append(dict(row))
                rows += 1
    except Exception:
        pass  # non-critical: metadata is best-effort

    return UploadResponse(
        success=True,
        message=f"File '{file.filename}' uploaded successfully",
        file=FileInfo(
            filename=safe_name,
            original_name=file.filename or "unknown",
            size_bytes=size_bytes,
            rows=rows,
            columns=len(column_names),
            column_names=column_names,
            preview=preview,
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/files  -  List all uploaded files
# ---------------------------------------------------------------------------

@router.get(
    "/files",
    response_model=FileListResponse,
    summary="List uploaded CSV files",
)
async def list_files():
    """Return all files in the uploads directory."""
    if not os.path.exists(UPLOAD_DIR):
        return FileListResponse(files=[], total=0)

    items: List[FileListItem] = []
    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        if os.path.isfile(path) and name.endswith(".csv"):
            stat = os.stat(path)
            items.append(FileListItem(
                filename=name,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            ))

    items.sort(key=lambda x: x.modified, reverse=True)
    return FileListResponse(files=items, total=len(items))


# ---------------------------------------------------------------------------
# DELETE /api/files/{filename}  -  Remove a file
# ---------------------------------------------------------------------------

@router.delete(
    "/files/{filename}",
    summary="Delete an uploaded file",
)
async def delete_file(filename: str):
    """Delete a specific file from the uploads directory."""

    # Security: block path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(UPLOAD_DIR, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    os.remove(file_path)
    return {"success": True, "message": f"File '{filename}' deleted successfully"}
