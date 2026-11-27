"""
Starting a training run (plan T4.2; SITE_NETWORK_PLAN.md §7.2–7.4). Used by POST /api/runs
(an admin) and by the scheduler. One run at a time.

Sites: the config names them, or every site that can train now is used: lab sites with a
SuperNode and plants that pass the eligibility rules (site_connection.training_status).
Sampling: with more than TRAIN_SAMPLE_ABOVE eligible sites and no fraction chosen, each round
trains on half of them (at least min_train_clients).
"""

import os
from typing import Dict, Optional

from app.platform_schemas import EnergyType, ExperimentConfig, RunDetail
from app.services import demo_runs, run_store
from app.services.federation_client import FederationClient, FederationUnavailable
from app.services.site_registry import list_sites
from app.services.wind_csv import CsvValidationError, validate_wind_csv
from app.settings import Settings


class LaunchError(Exception):
    def __init__(self, status: int, message):
        super().__init__(str(message))
        self.status, self.message = status, message


def sample_above() -> int:
    return int(os.environ.get("TRAIN_SAMPLE_ABOVE", "30"))


def resolve_sites(settings: Settings, config: ExperimentConfig) -> ExperimentConfig:
    """Fill or check config.sites against the sites that can train now; apply sampling."""
    sites = [s for s in list_sites(settings, config.energy_type, {"active", "suspended"})]
    trainable = [s.id for s in sites if s.can_train]
    if config.sites is None:
        if config.min_train_clients > len(trainable):
            raise LaunchError(422, f"min_train_clients is {config.min_train_clients} but only {len(trainable)} "
                                   f"{config.energy_type.value} sites can train now")
        update = {"sites": trainable}
        if len(trainable) > sample_above() and config.fraction_train == 1.0:
            update["fraction_train"] = max(0.5, config.min_train_clients / len(trainable))
        return config.model_copy(update=update)
    by_id = {s.id: s for s in sites}
    problems = []
    for sid in config.sites:
        s = by_id.get(sid)
        if s is None:
            problems.append(f"{sid}: unknown {config.energy_type.value} site")
        elif not s.can_train:
            problems.append(f"{sid}: {s.train_note or 'cannot train now'}")
    if problems:
        raise LaunchError(422, "Some sites can't train now. " + "; ".join(problems))
    return config


def launch(settings: Settings, config: ExperimentConfig, federation: FederationClient,
           uploads: Optional[Dict[str, bytes]] = None) -> RunDetail:
    """Validate, create the run folder and start it on the federation. Raises LaunchError."""
    uploads = uploads or {}
    config = resolve_sites(settings, config)

    # Uploads: all or nothing, one per selected site
    if uploads and config.energy_type != EnergyType.WIND:
        raise LaunchError(422, "CSV upload is available for wind runs only")
    if uploads:
        extra = sorted(set(uploads) - set(config.sites))
        missing = sorted(set(config.sites) - set(uploads))
        if extra or missing:
            raise LaunchError(422, f"Upload one CSV per selected site. Missing: {missing or 'none'}; "
                                   f"not selected: {extra or 'none'}")
        for site, content in uploads.items():
            try:
                validate_wind_csv(content)
            except CsvValidationError as e:
                raise LaunchError(422, f"{site}: {e}")
        config = config.model_copy(update={"data_source": "upload"})
    elif config.data_source == "upload":
        raise LaunchError(422, "data_source is 'upload' but no files were sent")

    with run_store.create_lock:
        active = run_store.active_run(settings)
        if active is not None:
            raise LaunchError(409, f"Run '{active.run_id}' is still {active.status}")

        if demo_runs.enabled():
            # Presentation laptop (DEMO_RUNS=1): no training; the run's files are played back
            run_id = run_store.new_run_id(config)
            run_store.create_run(settings, run_id, config)
            demo_runs.start(settings, run_id, config)
            return run_store.get_run(settings, run_id)

        fed = federation.status()
        if not fed.connected:
            raise LaunchError(503, fed.detail)
        if fed.connected_nodes is not None and fed.connected_nodes < config.min_train_clients:
            raise LaunchError(503, f"Only {fed.connected_nodes} clients connected; the config needs "
                                   f"{config.min_train_clients}")

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
            raise LaunchError(503, str(e))
        run_store.update_run(settings, run_id, status="running", flower_run_id=flower_run_id,
                             started_at=run_store.utc_now())
    return run_store.get_run(settings, run_id)
