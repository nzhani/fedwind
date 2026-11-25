-- M2 sites (SITE_NETWORK_PLAN.md §4, §9): the site registry moves from deploy/seed/sites.json to Postgres.
--
-- kind     builtin: the lab's simulated plants (NASA POWER data), imported from sites.json at start
--          plant:   registered by an operator of an organization
-- status   registered -> approved | rejected            (admin decision)
--          approved   -> active (enrolled, M3)  | revoked
--          active    <-> suspended;  active | suspended -> revoked
--          Only "active" sites take part in runs and forecasts.

CREATE TABLE sites (
    id                  TEXT PRIMARY KEY CHECK (id ~ '^[a-z][a-z0-9-]{1,62}$'),
    kind                TEXT NOT NULL CHECK (kind IN ('builtin', 'plant')),
    org_id              BIGINT REFERENCES organizations (id) ON DELETE RESTRICT,
    name                TEXT NOT NULL,
    energy_type         TEXT NOT NULL CHECK (energy_type IN ('wind', 'solar')),
    lat                 DOUBLE PRECISION NOT NULL,
    lon                 DOUBLE PRECISION NOT NULL,
    timezone            TEXT NOT NULL,
    capacity_kw         DOUBLE PRECISION CHECK (capacity_kw IS NULL OR capacity_kw > 0),
    equipment           JSONB NOT NULL DEFAULT '{}'::jsonb,
    data_source         TEXT,
    contact             TEXT,
    consents            JSONB NOT NULL DEFAULT '{}'::jsonb,
    coordinates_source  TEXT,
    partition_id        INTEGER UNIQUE,          -- builtin sites only; goes away with M6
    status              TEXT NOT NULL CHECK (status IN
                          ('registered', 'approved', 'rejected', 'active', 'suspended', 'revoked')),
    decision_note       TEXT,
    created_by          BIGINT REFERENCES users (id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_by          BIGINT REFERENCES users (id) ON DELETE SET NULL,
    decided_at          TIMESTAMPTZ,
    CHECK (kind = 'builtin' OR org_id IS NOT NULL)
);
CREATE INDEX sites_org ON sites (org_id);
CREATE INDEX sites_status ON sites (status);
CREATE UNIQUE INDEX sites_org_name_ci ON sites (org_id, lower(name)) WHERE org_id IS NOT NULL;
