"""Scheduled training and plant eligibility (SITE_NETWORK_PLAN.md §7.2–7.4)."""

from datetime import datetime, timezone

import psycopg
import pytest

from app.platform_schemas import EnergyType
from app.services import scheduler
from tests.conftest import FakeFederation


def test_schedule_parsing_and_slot_times(monkeypatch):
    slots = scheduler.parse_schedule("wind=SUN 02:00; solar=sun 3:30")
    assert [(s.energy_type, s.weekday, s.hour, s.minute) for s in slots] == [
        (EnergyType.WIND, 6, 2, 0), (EnergyType.SOLAR, 6, 3, 30)]
    with pytest.raises(ValueError):
        scheduler.parse_schedule("wind=SUNDAY 02:00")
    monkeypatch.setenv("TRAIN_SCHEDULE_TZ", "Asia/Almaty")             # UTC+5
    # Sunday 29 Nov 2026 02:00 Almaty = Saturday 21:00 UTC
    start = scheduler.latest_start(slots[0], datetime(2026, 11, 28, 22, 0, tzinfo=timezone.utc))
    assert start.isoformat() == "2026-11-29T02:00:00+05:00"
    before = scheduler.latest_start(slots[0], datetime(2026, 11, 28, 20, 0, tzinfo=timezone.utc))
    assert before.isoformat() == "2026-11-22T02:00:00+05:00"


def test_slot_starts_once_and_retries_when_too_few_sites(db_client, pg_url, monkeypatch, data_dir):
    monkeypatch.setenv("TRAIN_SCHEDULE", "wind=SUN 02:00")
    fed = FakeFederation()
    t0 = datetime(2026, 11, 28, 21, 10, tzinfo=timezone.utc)            # 10 min after the slot began

    monkeypatch.setenv("TRAIN_MIN_SITES", "6")                         # 5 lab wind sites: too few
    [r] = scheduler.tick(t0, fed)
    assert r["run_id"] is None and "only 5 wind sites" in r["reason"]
    assert scheduler.tick(t0.replace(minute=40), fed) == []            # not again within the hour

    monkeypatch.setenv("TRAIN_MIN_SITES", "3")
    [r] = scheduler.tick(t0.replace(hour=22, minute=15), fed)          # the hourly retry
    assert r["run_id"] and fed.started == [r["run_id"]]
    assert scheduler.tick(t0.replace(hour=23, minute=20), fed) == []   # the slot has its run

    with psycopg.connect(pg_url) as conn:
        attempts, run_id = conn.execute("SELECT attempts, run_id FROM training_schedule").fetchone()
        actions = [a for (a,) in conn.execute("SELECT action FROM audit_log WHERE action LIKE 'run.schedul%' ORDER BY id")]
    assert attempts == 2 and run_id == r["run_id"]
    assert actions == ["run.schedule_skipped", "run.scheduled"]


def test_window_closes_after_six_hours(db_client, monkeypatch, data_dir):
    monkeypatch.setenv("TRAIN_SCHEDULE", "solar=SUN 02:00")
    late = datetime(2026, 11, 29, 3, 30, tzinfo=timezone.utc)            # 8.5 h after the slot
    assert scheduler.tick(late, FakeFederation()) == []


def test_many_sites_are_sampled(db_client, monkeypatch):
    from app.platform_schemas import ExperimentConfig
    from app.services import run_launcher
    from app.settings import get_settings

    monkeypatch.setenv("TRAIN_SAMPLE_ABOVE", "3")
    cfg = run_launcher.resolve_sites(get_settings(), ExperimentConfig(min_train_clients=2))
    assert len(cfg.sites) == 5 and cfg.fraction_train == 0.5
    monkeypatch.setenv("TRAIN_SAMPLE_ABOVE", "30")
    assert run_launcher.resolve_sites(get_settings(), ExperimentConfig()).fraction_train == 1.0
