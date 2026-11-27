"""
Model registry (plan T3.1; SITE_NETWORK_PLAN.md M7, §8).

Every finished run can become a model version: its best checkpoint is copied to
  models/<energy_type>/h<horizon>/v<N>.pt        (immutable, with its SHA-256 in the database)
and the promoted one is also copied to
  models/<energy_type>/h<horizon>/current.pt     (+ current.json; what older readers use)
Inference loads the promoted version's own path, so promoting or rolling back takes effect at the
next forecast.

Statuses: candidate -> promoted -> retired; rejected = vetoed. One promoted per (energy, horizon).

Promotion gates (decision D3: automatic with an admin veto)
  1. trained on all data (data_percent 100)
  2. beats persistence (skill > 0)
  3. beats the promoted model's mean skill
  4. no site more than 10 % worse (MAE) than with the promoted model
Runs started by the scheduler are promoted automatically when every gate passes (AUTO_PROMOTE=off
turns that off); an admin can veto for 24 h, which puts the previous model back. Admins can promote
any version by hand (the gate report is shown, not enforced): that is also how a rollback works.

Without a database (DATABASE_URL unset) the registry is the current.json files only, as before.
"""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from app.platform_schemas import RegisteredModel, RunDetail
from app.services.run_store import utc_now
from app.settings import Settings

log = logging.getLogger("fedwind.models")

VETO_WINDOW = timedelta(hours=24)
WORSE_SITE_LIMIT = 0.10


class PromoteError(ValueError):
    pass


def _db() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def model_path(energy_type: str, horizon: int) -> str:
    """Path of the promoted checkpoint copy, relative to models/ (file mode and older readers)."""
    return f"{energy_type}/h{horizon}/current.pt"


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _checkpoint(settings: Settings, run: RunDetail) -> Path:
    if run.status != "done" or not run.result:
        raise PromoteError(f"Run '{run.run_id}' is {run.status}; only finished runs become models")
    checkpoint = (run.result.get("model") or {}).get("checkpoint")
    if not checkpoint:
        raise PromoteError("result.json has no model.checkpoint")
    run_folder = (settings.runs_dir / run.run_id).resolve()
    source = (run_folder / checkpoint).resolve()
    if run_folder not in source.parents or not source.is_file():
        raise PromoteError(f"Checkpoint '{checkpoint}' not found in the run folder")
    return source


def _data_percent(run: RunDetail) -> Optional[float]:
    try:
        v = (run.config or {}).get("data_percent")
        return float(v) if v is not None else 100.0
    except (TypeError, ValueError):
        return None


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    shutil.copyfile(source, tmp)
    tmp.replace(target)


def _write_current(settings: Settings, m: RegisteredModel) -> None:
    """current.pt / current.json next to the versions: file-mode readers and backups see the promoted model."""
    folder = settings.models_dir / m.energy_type.value / f"h{m.horizon}"
    if m.model_path and m.model_path != model_path(m.energy_type.value, m.horizon):
        _copy(settings.models_dir / m.model_path, folder / "current.pt")
    with open(folder / "current.json", "w", encoding="utf-8") as f:
        json.dump(m.model_dump(mode="json"), f, indent=2)


def _row(r: dict) -> RegisteredModel:
    return RegisteredModel(
        id=r["id"], energy_type=r["energy_type"], horizon=r["horizon"], version=r["version"], run_id=r["run_id"],
        status=r["status"], origin=r["origin"], model_path=r["path"], sha256=r["sha256"], size_bytes=r["size_bytes"],
        metrics=r["metrics"], sites=r["sites"] or [], strategy=r["strategy"], rounds_completed=r["rounds_completed"],
        data_percent=r["data_percent"], gates=r["gates"], created_at=_iso(r["created_at"]),
        promoted_at=_iso(r["promoted_at"]) or "", promoted_by=r["promoted_by"], veto_until=_iso(r["veto_until"]),
        retired_at=_iso(r["retired_at"]), note=r["note"])


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _file_model(settings: Settings, energy_type: str, horizon: int) -> Optional[RegisteredModel]:
    meta = settings.models_dir / energy_type / f"h{horizon}" / "current.json"
    try:
        with open(meta, encoding="utf-8") as f:
            m = RegisteredModel(**json.load(f))
    except FileNotFoundError:
        return None
    return m if m.model_path else m.model_copy(update={"model_path": model_path(energy_type, horizon)})


def current_model(settings: Settings, energy_type: str, horizon: int) -> Optional[RegisteredModel]:
    """The promoted model for (energy type, horizon), or None."""
    if not _db():
        return _file_model(settings, energy_type, horizon)
    from app.db import connect

    import_files(settings)
    with connect() as conn:
        r = conn.execute("SELECT * FROM model_versions WHERE energy_type = %s AND horizon = %s AND status = 'promoted'",
                         (energy_type, horizon)).fetchone()
    return _row(r) if r else None


def list_models(settings: Settings) -> List[RegisteredModel]:
    """Promoted models, one per (energy type, horizon)."""
    if not _db():
        if not settings.models_dir.is_dir():
            return []
        return [m for meta in sorted(settings.models_dir.glob("*/h*/current.json"))
                if (m := _file_model(settings, meta.parent.parent.name, int(meta.parent.name[1:])))]
    from app.db import connect

    import_files(settings)
    with connect() as conn:
        rows = conn.execute("SELECT * FROM model_versions WHERE status = 'promoted' ORDER BY energy_type, horizon").fetchall()
    return [_row(r) for r in rows]


def list_versions(settings: Settings, energy_type: Optional[str] = None, horizon: Optional[int] = None) -> List[RegisteredModel]:
    if not _db():
        return list_models(settings)
    from app.db import connect

    import_files(settings)
    sql, args = "SELECT * FROM model_versions WHERE TRUE", []
    if energy_type:
        sql, args = sql + " AND energy_type = %s", args + [energy_type]
    if horizon:
        sql, args = sql + " AND horizon = %s", args + [horizon]
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY energy_type, horizon, version DESC", args).fetchall()
    return [_row(r) for r in rows]


def get_version(version_id: int) -> Optional[RegisteredModel]:
    from app.db import connect

    with connect() as conn:
        r = conn.execute("SELECT * FROM model_versions WHERE id = %s", (version_id,)).fetchone()
    return _row(r) if r else None


_imported: set = set()     # (database, models folder) pairs already checked in this process


def import_files(settings: Settings) -> int:
    """Once per process: models promoted before the registry existed (current.json without a version)
    become version 1, promoted, origin 'import'."""
    key = (os.environ.get("DATABASE_URL"), str(settings.models_dir))
    if key in _imported or not _db() or not settings.models_dir.is_dir():
        return 0
    from app.db import connect

    n = 0
    with connect() as conn:
        for meta in sorted(settings.models_dir.glob("*/h*/current.json")):
            energy, horizon = meta.parent.parent.name, int(meta.parent.name[1:])
            m = _file_model(settings, energy, horizon)
            pt = settings.models_dir / energy / f"h{horizon}" / "current.pt"
            if m is None or m.version is not None or not pt.is_file():
                continue
            if conn.execute("SELECT 1 FROM model_versions WHERE energy_type = %s AND horizon = %s",
                            (energy, horizon)).fetchone():
                continue
            target = f"{energy}/h{horizon}/v1.pt"
            _copy(pt, settings.models_dir / target)
            conn.execute(
                "INSERT INTO model_versions (energy_type, horizon, version, run_id, status, origin, path, sha256,"
                " size_bytes, metrics, sites, strategy, rounds_completed, promoted_at, promoted_by)"
                " VALUES (%s, %s, 1, %s, 'promoted', 'import', %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (energy, horizon, m.run_id, target, _sha256(pt), pt.stat().st_size, json.dumps(m.metrics),
                 json.dumps(m.sites), m.strategy, m.rounds_completed, m.promoted_at or None, m.promoted_by))
            n += 1
    _imported.add(key)
    return n


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def _skill(metrics: Optional[dict]) -> Optional[float]:
    v = ((metrics or {}).get("real") or {}).get("skill_vs_persistence")
    return float(v) if isinstance(v, (int, float)) else None


def evaluate_gates(candidate: RegisteredModel, current: Optional[RegisteredModel]) -> dict:
    """The promotion gates (module docstring). Both models are judged on their own runs' test windows."""
    gates = []
    skill = _skill(candidate.metrics)
    gates.append({"name": "Trained on all data", "passed": (candidate.data_percent or 0) >= 100,
                  "detail": f"{candidate.data_percent:g} % of each site's training data" if candidate.data_percent
                  is not None else "unknown"})
    gates.append({"name": "Beats persistence", "passed": skill is not None and skill > 0,
                  "detail": f"skill {skill:+.3f}" if skill is not None else "no skill in result.json"})
    if current is not None:
        cur_skill = _skill(current.metrics)
        gates.append({"name": f"Beats v{current.version or 1}", "passed": skill is not None and
                      (cur_skill is None or skill > cur_skill),
                      "detail": f"skill {skill if skill is not None else float('nan'):+.3f} vs "
                                f"{cur_skill if cur_skill is not None else float('nan'):+.3f}"})
        new_sites = (candidate.metrics or {}).get("per_site") or {}
        old_sites = (current.metrics or {}).get("per_site") or {}
        worse = []
        for site in sorted(set(new_sites) & set(old_sites)):
            a, b = (new_sites[site] or {}).get("mae"), (old_sites[site] or {}).get("mae")
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b > 0 and a > b * (1 + WORSE_SITE_LIMIT):
                worse.append(f"{site} {a / b - 1:+.0%}")
        gates.append({"name": f"No site more than {WORSE_SITE_LIMIT:.0%} worse", "passed": not worse,
                      "detail": ", ".join(worse) if worse else
                      f"{len(set(new_sites) & set(old_sites))} sites compared"})
    return {"passed": all(g["passed"] for g in gates), "gates": gates,
            "compared_with": current.version if current else None,
            "evaluated_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def register(settings: Settings, run: RunDetail, origin: str = "manual") -> RegisteredModel:
    """Make a finished run a candidate version (idempotent: returns the existing version)."""
    source = _checkpoint(settings, run)
    energy = str(run.config.get("energy_type", "wind"))
    from app.db import connect

    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7340007)")       # one writer assigns version numbers
        r = conn.execute("SELECT * FROM model_versions WHERE run_id = %s AND energy_type = %s AND horizon = %s",
                         (run.run_id, energy, run.horizon)).fetchone()
        if r:
            return _row(r)
        version = conn.execute("SELECT COALESCE(max(version), 0) + 1 AS v FROM model_versions WHERE energy_type = %s"
                               " AND horizon = %s", (energy, run.horizon)).fetchone()["v"]
        target = f"{energy}/h{run.horizon}/v{version}.pt"
        _copy(source, settings.models_dir / target)
        candidate = RegisteredModel(energy_type=energy, horizon=run.horizon, run_id=run.run_id, promoted_at="",
                                    metrics=run.result.get("metrics"), sites=list(run.sites), version=version,
                                    data_percent=_data_percent(run), strategy=run.strategy)
        cur = conn.execute("SELECT * FROM model_versions WHERE energy_type = %s AND horizon = %s AND status = 'promoted'",
                           (energy, run.horizon)).fetchone()
        gates = evaluate_gates(candidate, _row(cur) if cur else None)
        r = conn.execute(
            "INSERT INTO model_versions (energy_type, horizon, version, run_id, status, origin, path, sha256, size_bytes,"
            " metrics, sites, strategy, rounds_completed, data_percent, gates)"
            " VALUES (%s, %s, %s, %s, 'candidate', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (energy, run.horizon, version, run.run_id, origin, target, _sha256(source), source.stat().st_size,
             json.dumps(run.result.get("metrics")), json.dumps(list(run.sites)), run.strategy,
             run.result.get("rounds_completed") or run.current_round or None, _data_percent(run), json.dumps(gates))
        ).fetchone()
    return _row(r)


def promote_version(settings: Settings, version_id: int, promoted_by: Optional[str], note: Optional[str] = None,
                    automatic: bool = False) -> RegisteredModel:
    """Make this version the promoted one; the previous one is retired. Also the way to roll back."""
    from app.db import connect

    with connect() as conn:
        r = conn.execute("SELECT * FROM model_versions WHERE id = %s FOR UPDATE", (version_id,)).fetchone()
        if r is None:
            raise PromoteError("Model version not found")
        if r["status"] == "promoted":
            return _row(r)
        if not (settings.models_dir / r["path"]).is_file():
            raise PromoteError(f"Model file {r['path']} is missing")
        conn.execute("UPDATE model_versions SET status = 'retired', retired_at = now(), veto_until = NULL"
                     " WHERE energy_type = %s AND horizon = %s AND status = 'promoted'", (r["energy_type"], r["horizon"]))
        r = conn.execute(
            "UPDATE model_versions SET status = 'promoted', promoted_at = now(), promoted_by = %s, retired_at = NULL,"
            " veto_until = %s, note = COALESCE(%s, note) WHERE id = %s RETURNING *",
            (promoted_by, datetime.now(timezone.utc) + VETO_WINDOW if automatic else None, note, version_id)).fetchone()
    m = _row(r)
    _write_current(settings, m)
    return m


def veto(settings: Settings, version_id: int, by: str, note: str) -> RegisteredModel:
    """Undo an automatic promotion within its veto window: this version is rejected, the version it
    replaced is promoted again. Returns the model now serving."""
    from app.db import connect

    with connect() as conn:
        r = conn.execute("SELECT * FROM model_versions WHERE id = %s FOR UPDATE", (version_id,)).fetchone()
        if r is None:
            raise PromoteError("Model version not found")
        if r["status"] != "promoted" or not r["veto_until"] or r["veto_until"] < datetime.now(timezone.utc):
            raise PromoteError("Only an automatic promotion can be vetoed, within 24 hours")
        prev = conn.execute("SELECT * FROM model_versions WHERE energy_type = %s AND horizon = %s AND status = 'retired'"
                            " ORDER BY retired_at DESC NULLS LAST LIMIT 1", (r["energy_type"], r["horizon"])).fetchone()
        conn.execute("UPDATE model_versions SET status = 'rejected', veto_until = NULL, retired_at = now(), note = %s"
                     " WHERE id = %s", (note, version_id))
    if prev is None:
        meta = settings.models_dir / r["energy_type"] / f"h{r['horizon']}"
        for name in ("current.json", "current.pt"):
            (meta / name).unlink(missing_ok=True)
        raise PromoteError("Vetoed; there is no earlier model, so no forecasts until another is promoted")
    return promote_version(settings, prev["id"], by, note=f"restored after veto of v{r['version']}")


def promote(settings: Settings, run: RunDetail, promoted_by: Optional[str] = None) -> RegisteredModel:
    """Promote a finished run (the run page's button, demo-reset). With a database: register it as a
    version (if new) and promote that version; the gate report is kept but not enforced."""
    if not _db():
        return _promote_files(settings, run, promoted_by)
    import_files(settings)
    m = register(settings, run)
    return promote_version(settings, m.id, promoted_by)


def _promote_files(settings: Settings, run: RunDetail, promoted_by: Optional[str]) -> RegisteredModel:
    source = _checkpoint(settings, run)
    energy_type = str(run.config.get("energy_type", "wind"))
    target_dir = settings.models_dir / energy_type / f"h{run.horizon}"
    _copy(source, target_dir / "current.pt")
    model = RegisteredModel(
        energy_type=energy_type, horizon=run.horizon, run_id=run.run_id, promoted_at=utc_now(),
        metrics=run.result.get("metrics"), sites=list(run.sites),
        rounds_completed=run.result.get("rounds_completed") or run.current_round or None,
        strategy=run.strategy, promoted_by=promoted_by, model_path=model_path(energy_type, run.horizon),
        data_percent=_data_percent(run))
    with open(target_dir / "current.json", "w", encoding="utf-8") as f:
        json.dump(model.model_dump(mode="json"), f, indent=2)
    return model


# ---------------------------------------------------------------------------
# Automatic: new runs become candidates; scheduled ones are promoted when the gates pass
# ---------------------------------------------------------------------------

def sync(settings: Settings) -> List[dict]:
    """Register every finished run that isn't a version yet; promote scheduled runs whose gates pass."""
    if not _db():
        return []
    from app.db import connect
    from app.services import run_store
    from app.services.accounts import audit

    import_files(settings)
    with connect() as conn:
        known = {(r["run_id"]) for r in conn.execute("SELECT run_id FROM model_versions").fetchall()}
        scheduled = {r["run_id"] for r in conn.execute(
            "SELECT run_id FROM training_schedule WHERE run_id IS NOT NULL").fetchall()}
    done = []
    for summary in run_store.list_runs(settings):
        if summary.status != "done" or summary.run_id in known:
            continue
        run = run_store.get_run(settings, summary.run_id)
        try:
            m = register(settings, run, origin="schedule" if run.run_id in scheduled else "manual")
        except PromoteError as e:
            log.warning("run %s not registered: %s", summary.run_id, e)
            continue
        event = {"run_id": run.run_id, "version": m.version, "status": "candidate", "gates": m.gates["passed"]}
        if m.origin == "schedule" and m.gates["passed"] and os.environ.get("AUTO_PROMOTE", "on").lower() != "off":
            m = promote_version(settings, m.id, "automatic (all gates passed)", automatic=True)
            event["status"] = "promoted"
        with connect() as conn:
            audit(conn, "model.auto_promote" if event["status"] == "promoted" else "model.candidate",
                  target=f"{m.energy_type.value}-h{m.horizon}-v{m.version}",
                  details={"run_id": run.run_id, "gates_passed": m.gates["passed"], "origin": m.origin})
        done.append(event)
    return done
