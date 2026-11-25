-- Site connection (DEMO_SIMULATION_PLAN.md §3, SITE_NETWORK_PLAN.md §2.3, §6):
-- one-time enrollment tokens, the credential a site agent gets at enrollment, heartbeats,
-- daily data-quality counts, and the recent forecast window for central forecasting.

CREATE TABLE enrollment_tokens (
    id             BIGSERIAL PRIMARY KEY,
    site_id        TEXT NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
    token_hash     TEXT NOT NULL UNIQUE,              -- SHA-256 of the token; the token itself is only in the kit
    created_by     BIGINT REFERENCES users (id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    used_at        TIMESTAMPTZ,
    superseded_at  TIMESTAMPTZ                        -- a newer kit was issued, or the site was revoked
);
CREATE INDEX enrollment_tokens_site ON enrollment_tokens (site_id);

-- kind token: a site API key (development / demo, SITE_AUTH_MODE=token)
-- kind cert: a client certificate signed by the site CA (M3, SITE_AUTH_MODE=mtls)
CREATE TABLE site_credentials (
    id              BIGSERIAL PRIMARY KEY,
    site_id         TEXT NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('token', 'cert')),
    secret_hash     TEXT UNIQUE,                     -- SHA-256 of the site key (kind token)
    cert_serial     TEXT UNIQUE,                     -- kind cert (M3)
    cert_not_after  TIMESTAMPTZ,
    flower_pubkey   TEXT,                            -- OpenSSH EC public key, registered with Flower in M6
    flower_node_id  TEXT,
    agent_kind      TEXT NOT NULL CHECK (agent_kind IN ('kit', 'simulated')),
    agent_version   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    first_seen_at   TIMESTAMPTZ,
    last_seen_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    CHECK ((kind = 'token' AND secret_hash IS NOT NULL) OR (kind = 'cert' AND cert_serial IS NOT NULL))
);
CREATE UNIQUE INDEX site_credentials_one_live ON site_credentials (site_id) WHERE revoked_at IS NULL;

CREATE TABLE site_heartbeats (
    id              BIGSERIAL PRIMARY KEY,
    site_id         TEXT NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
    at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent_kind      TEXT,
    agent_version   TEXT,
    last_data_hour  TIMESTAMPTZ,
    rows_today      INTEGER,
    gaps_today      INTEGER,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX site_heartbeats_site_at ON site_heartbeats (site_id, at DESC);

CREATE TABLE site_quality (
    site_id    TEXT NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
    day        DATE NOT NULL,
    rows       INTEGER NOT NULL CHECK (rows >= 0),
    gaps       INTEGER NOT NULL CHECK (gaps >= 0),
    flagged    INTEGER NOT NULL DEFAULT 0 CHECK (flagged >= 0),
    curtailed  INTEGER NOT NULL DEFAULT 0 CHECK (curtailed >= 0),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, day)
);

-- Central forecasting (consent "share_forecast_window"): the last hours of the forecast target only.
-- Kept 30 days.
CREATE TABLE forecast_inputs (
    site_id      TEXT NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
    hour         TIMESTAMPTZ NOT NULL,
    value        DOUBLE PRECISION,
    ok           BOOLEAN NOT NULL DEFAULT TRUE,      -- false: missing / flagged hour
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, hour)
);
