-- Scheduled training runs (SITE_NETWORK_PLAN.md §7.4): one row per scheduled slot, e.g.
-- "wind@2026-11-29T02:00:00+05:00". A slot starts at most one run; when too few sites can train
-- or another run is active it is retried hourly, up to 6 times, and the reason is kept.
CREATE TABLE training_schedule (
    slot             TEXT PRIMARY KEY,
    energy_type      TEXT NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    last_attempt_at  TIMESTAMPTZ,
    last_reason      TEXT,
    run_id           TEXT                       -- set once the slot's run started
);
