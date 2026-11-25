"""
Scheduled training (SITE_NETWORK_PLAN.md §7.4): weekly runs per energy type, so the model keeps
learning from the plants without anyone pressing Start.

  TRAIN_SCHEDULE="wind=SUN 02:00; solar=SUN 03:00"   weekly slots (empty: no scheduled runs)
  TRAIN_SCHEDULE_TZ=Asia/Almaty                      time zone of those times
  TRAIN_MIN_SITES=3                                  fewer eligible sites: skip, retry later
  TRAIN_SCHEDULE_CONFIG_WIND / _SOLAR                JSON overrides of the experiment config
                                                     (default: ExperimentConfig defaults, every site
                                                     that can train, min_train_clients <= sites)

A slot that can't start (too few sites, a run already active, federation down) is retried every
hour for up to 6 hours, then left; each attempt's reason is kept in training_schedule and the
audit log. Manual starts by admins stay possible at any time.
"""

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.db import connect
from app.platform_schemas import EnergyType, ExperimentConfig
from app.services import run_launcher
from app.services.accounts import audit
from app.settings import get_settings

log = logging.getLogger("fedwind.scheduler")

DAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
RETRY_EVERY = timedelta(hours=1)
MAX_ATTEMPTS = 6
TICK_S = 300


@dataclass(frozen=True)
class Slot:
    energy_type: EnergyType
    weekday: int
    hour: int
    minute: int


def parse_schedule(text: str) -> List[Slot]:
    """"wind=SUN 02:00; solar=SUN 03:00" -> slots. Raises ValueError on anything else."""
    slots = []
    for part in filter(None, (p.strip() for p in (text or "").split(";"))):
        m = re.fullmatch(r"(wind|solar)\s*=\s*(MON|TUE|WED|THU|FRI|SAT|SUN)\s+(\d{1,2}):(\d{2})", part, re.I)
        if not m or int(m.group(3)) > 23 or int(m.group(4)) > 59:
            raise ValueError(f"TRAIN_SCHEDULE: can't read '{part}' (expected e.g. 'wind=SUN 02:00')")
        slots.append(Slot(EnergyType(m.group(1).lower()), DAYS[m.group(2).upper()], int(m.group(3)), int(m.group(4))))
    return slots


def tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("TRAIN_SCHEDULE_TZ", "Asia/Almaty"))


def latest_start(slot: Slot, now: datetime) -> datetime:
    """The most recent time this weekly slot began, at or before now."""
    local = now.astimezone(tz())
    start = local.replace(hour=slot.hour, minute=slot.minute, second=0, microsecond=0)
    start -= timedelta(days=(local.weekday() - slot.weekday) % 7)
    if start > local:
        start -= timedelta(days=7)
    return start


def config_for(energy: EnergyType, eligible: int) -> ExperimentConfig:
    overrides = json.loads(os.environ.get(f"TRAIN_SCHEDULE_CONFIG_{energy.value.upper()}", "") or "{}")
    base = ExperimentConfig(energy_type=energy, **overrides)
    if base.sites is None and base.min_train_clients > eligible:
        base = base.model_copy(update={"min_train_clients": max(1, eligible)})
    return base


def tick(now: Optional[datetime] = None, federation=None) -> List[dict]:
    """One pass: start every due slot that hasn't run. Returns what happened (for logs and tests)."""
    from app.services.federation_client import get_federation
    from app.services.site_registry import list_sites

    now = now or datetime.now(timezone.utc)
    slots = parse_schedule(os.environ.get("TRAIN_SCHEDULE", ""))
    min_sites = int(os.environ.get("TRAIN_MIN_SITES", "3"))
    settings = get_settings()
    done = []
    for slot in slots:
        start = latest_start(slot, now)
        if now - start >= RETRY_EVERY * MAX_ATTEMPTS:
            continue                                              # this week's window has passed
        key = f"{slot.energy_type.value}@{start.isoformat()}"
        with connect() as conn:
            conn.execute("INSERT INTO training_schedule (slot, energy_type) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (key, slot.energy_type.value))
            row = conn.execute("SELECT * FROM training_schedule WHERE slot = %s FOR UPDATE", (key,)).fetchone()
            if row["run_id"] or row["attempts"] >= MAX_ATTEMPTS or (
                    row["last_attempt_at"] and now - row["last_attempt_at"] < RETRY_EVERY - timedelta(minutes=5)):
                continue
            eligible = [s.id for s in list_sites(settings, slot.energy_type, {"active"}) if s.can_train]
            run_id, reason = None, None
            if len(eligible) < min_sites:
                reason = f"only {len(eligible)} {slot.energy_type.value} sites can train (need {min_sites})"
            else:
                try:
                    run = run_launcher.launch(settings, config_for(slot.energy_type, len(eligible)),
                                              federation or get_federation())
                    run_id = run.run_id
                except run_launcher.LaunchError as e:
                    reason = e.message if isinstance(e.message, str) else json.dumps(e.message)
            conn.execute("UPDATE training_schedule SET attempts = attempts + 1, last_attempt_at = %s,"
                         " last_reason = %s, run_id = %s WHERE slot = %s", (now, reason, run_id, key))
            attempt = row["attempts"] + 1
            if run_id:
                audit(conn, "run.scheduled", actor_type="system", target=run_id,
                      details={"slot": key, "sites": len(eligible), "attempt": attempt})
                log.info("scheduled run %s started (%s, %d sites)", run_id, key, len(eligible))
            else:
                audit(conn, "run.schedule_skipped", actor_type="system", target=key,
                      details={"reason": reason, "attempt": attempt, "final": attempt >= MAX_ATTEMPTS})
                log.info("scheduled slot %s not started: %s (attempt %d of %d)", key, reason, attempt, MAX_ATTEMPTS)
        done.append({"slot": key, "run_id": run_id, "reason": reason})
    return done


def start_background() -> bool:
    """Off without TRAIN_SCHEDULE or with SCHEDULER_LOOP=off."""
    text = os.environ.get("TRAIN_SCHEDULE", "")
    if not text.strip() or os.environ.get("SCHEDULER_LOOP", "on").lower() == "off":
        return False
    parse_schedule(text)  # fail at start, not at 2 a.m.

    def loop():
        wait = threading.Event()
        while True:
            try:
                tick()
            except Exception as e:  # never kill the API; the next tick tries again
                log.warning("scheduler: %s: %s", type(e).__name__, e)
            wait.wait(TICK_S)

    threading.Thread(target=loop, name="training-scheduler", daemon=True).start()
    return True
