"""
Runs Router - federated runs on the always-on federation (plan §5.7, T4.1, T4.2).

Endpoints:
  GET  /api/federation              Is the SuperLink reachable, how many clients
  GET  /api/runs                    Run list (newest first) + active run id
  GET  /api/runs/{run_id}           Status, per-round history, clients, result
  POST /api/runs                    Start a run: form field `config` (JSON) +
                                    optional files `file_<site>` (one CSV per site)
  POST /api/runs/{run_id}/stop      Stop the active run

One run at a time: a second start returns 409.  When the federation isn't
connected, starting returns 503 and no run is created.
"""

import json
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from app.platform_schemas import (
    ACTIVE_STATUSES,
    EnergyType,
    ExperimentConfig,
    FederationStatus,
    RunDetail,
    RunListResponse,
)
from app.services import run_store
from app.services.federation_client import FederationClient, FederationUnavailable, get_federation
from app.services.site_registry import active_site_ids
from app.services.wind_csv import CsvValidationError, validate_wind_csv
from app.settings import get_settings

router = APIRouter(prefix="/api")


def _refresh(run: RunDetail, federation: FederationClient) -> RunDetail:
    """A run Flower reports as finished, but without result.json, failed."""
    if run.status in ACTIVE_STATUSES and run.flower_run_id and run.result is None:
        state = federation.run_state(run.flower_run_id)
        if state is not None and state.startswith("finished"):
            settings = get_settings()
            run_store.update_run(
                settings, run.run_id, status="failed", finished_at=run_store.utc_now(),
                error=f"Flower reports '{state}' but the ServerApp wrote no result.json",
            )
            return run_store.get_run(settings, run.run_id) or run
    return run


@router.get("/federation", response_model=FederationStatus, summary="Federation status")
def federation_status(federation: FederationClient = Depends(get_federation)):
    return federation.status()


@router.get("/runs", response_model=RunListResponse, summary="List runs")
def list_runs():
    settings = get_settings()
    runs = run_store.list_runs(settings)
    active = next((r.run_id for r in runs if r.status in ACTIVE_STATUSES), None)
    return RunListResponse(runs=runs, active_run_id=active)


@router.get("/runs/{run_id}", response_model=RunDetail, summary="Run detail")
def get_run(run_id: str, federation: FederationClient = Depends(get_federation)):
    run = run_store.get_run(get_settings(), run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run '{run_id}' not found")
    return _refresh(run, federation)


@router.post("/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED, summary="Start a run")
async def start_run(request: Request, federation: FederationClient = Depends(get_federation)):
    settings = get_settings()
    form = await request.form()

    # 1. Config
    try:
        config = ExperimentConfig(**json.loads(form.get("config") or "{}"))
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Field 'config' must be JSON")
    except ValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, json.loads(e.json(include_url=False)))

    known = set(active_site_ids(settings, EnergyType.WIND))
    unknown = [s for s in config.sites if s not in known]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown or inactive sites: {', '.join(unknown)}")

    # 2. Uploads: all or nothing, one per selected site
    uploads: Dict[str, bytes] = {}
    for key, value in form.multi_items():
        if key.startswith("file_") and hasattr(value, "read"):
            uploads[key[len("file_"):]] = await value.read()
    if uploads:
        extra = sorted(set(uploads) - set(config.sites))
        missing = sorted(set(config.sites) - set(uploads))
        if extra or missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Upload one CSV per selected site. Missing: {missing or 'none'}; not selected: {extra or 'none'}",
            )
        for site, content in uploads.items():
            try:
                validate_wind_csv(content)
            except CsvValidationError as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{site}: {e}")
        config = config.model_copy(update={"data_source": "upload"})
    elif config.data_source == "upload":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "data_source is 'upload' but no files were sent")

    with run_store.create_lock:
        # 3. One run at a time
        active = run_store.active_run(settings)
        if active is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Run '{active.run_id}' is still {active.status}")

        # 4. Federation reachable with enough clients
        fed = federation.status()
        if not fed.connected:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, fed.detail)
        if fed.connected_nodes is not None and fed.connected_nodes < config.min_train_clients:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"Only {fed.connected_nodes} clients connected; the config needs {config.min_train_clients}",
            )

        # 5. Create the run, place uploads in each site's own folder, start it
        run_id = run_store.new_run_id(config)
        folder = run_store.create_run(settings, run_id, config)
        for site, content in uploads.items():
            site_uploads = settings.sites_dir / site / "uploads"
            site_uploads.mkdir(parents=True, exist_ok=True)
            (site_uploads / f"{run_id}.csv").write_bytes(content)

        try:
            flower_run_id = federation.start_run(run_id, folder / "config.yaml")
        except FederationUnavailable as e:
            run_store.update_run(settings, run_id, status="failed", error=str(e), finished_at=run_store.utc_now())
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
        run_store.update_run(
            settings, run_id, status="running", flower_run_id=flower_run_id, started_at=run_store.utc_now()
        )

    return run_store.get_run(settings, run_id)


@router.post("/runs/{run_id}/stop", response_model=RunDetail, summary="Stop the active run")
def stop_run(run_id: str, federation: FederationClient = Depends(get_federation)):
    settings = get_settings()
    run = run_store.get_run(settings, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run '{run_id}' not found")
    if run.status not in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run '{run_id}' is {run.status}, not running")
    if run.flower_run_id:
        try:
            federation.stop_run(run.flower_run_id)
        except FederationUnavailable as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    run_store.update_run(settings, run_id, status="stopped", finished_at=run_store.utc_now())
    return run_store.get_run(settings, run_id)
