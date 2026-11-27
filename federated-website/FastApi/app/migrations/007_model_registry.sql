-- Model registry and stored forecasts (SITE_NETWORK_PLAN.md M7, §8).
--
-- model_versions: every finished run's best checkpoint, copied to models/<energy>/h<horizon>/v<N>.pt.
--   candidate -> promoted -> retired; rejected = vetoed by an admin. One promoted per (energy, horizon).
-- forecasts: forecasts made for plants, kept 30 days. source central = made here from the window the
--   plant shared; local = made at the plant with the downloaded model and sent back (no window shared).

CREATE TABLE model_versions (
    id                BIGSERIAL PRIMARY KEY,
    energy_type       TEXT NOT NULL CHECK (energy_type IN ('wind', 'solar')),
    horizon           INTEGER NOT NULL CHECK (horizon > 0),
    version           INTEGER NOT NULL,
    run_id            TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('candidate', 'promoted', 'retired', 'rejected')),
    origin            TEXT NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual', 'schedule', 'import')),
    path              TEXT NOT NULL,                -- relative to the models folder
    sha256            TEXT NOT NULL,
    size_bytes        BIGINT,
    metrics           JSONB,                        -- result.json "metrics"
    sites             JSONB NOT NULL DEFAULT '[]'::jsonb,
    strategy          TEXT,
    rounds_completed  INTEGER,
    data_percent      DOUBLE PRECISION,
    gates             JSONB,                        -- promotion gate report (model_registry.evaluate_gates)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at       TIMESTAMPTZ,
    promoted_by       TEXT,
    veto_until        TIMESTAMPTZ,                  -- automatic promotions: an admin may veto until then
    retired_at        TIMESTAMPTZ,
    note              TEXT,
    UNIQUE (energy_type, horizon, version),
    UNIQUE (run_id, energy_type, horizon)
);
CREATE UNIQUE INDEX model_versions_one_promoted ON model_versions (energy_type, horizon) WHERE status = 'promoted';

CREATE TABLE forecasts (
    id                BIGSERIAL PRIMARY KEY,
    site_id           TEXT NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
    horizon           INTEGER NOT NULL,
    source            TEXT NOT NULL CHECK (source IN ('central', 'local')),
    model_version_id  BIGINT REFERENCES model_versions (id) ON DELETE SET NULL,
    issued_at         TIMESTAMPTZ NOT NULL,         -- newest observed hour the forecast starts from
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    unit              TEXT NOT NULL,
    capacity_kw       DOUBLE PRECISION,
    actual            JSONB NOT NULL DEFAULT '[]'::jsonb,
    forecast          JSONB NOT NULL,               -- [{timestamp, value, power_kw, ...}]
    UNIQUE (site_id, horizon, source, issued_at, model_version_id)
);
CREATE INDEX forecasts_newest ON forecasts (site_id, horizon, issued_at DESC);
