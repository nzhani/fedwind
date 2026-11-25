-- M1 accounts (SITE_NETWORK_PLAN.md §3, §9): organizations, users, sessions, audit log.

CREATE TABLE organizations (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX organizations_name_ci ON organizations (lower(name));

CREATE TABLE users (
    id             BIGSERIAL PRIMARY KEY,
    org_id         BIGINT REFERENCES organizations (id) ON DELETE RESTRICT,
    email          TEXT NOT NULL,
    name           TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at  TIMESTAMPTZ
);
CREATE UNIQUE INDEX users_email_ci ON users (lower(email));

-- The cookie holds a random token; only its SHA-256 is stored here.
CREATE TABLE sessions (
    id_hash      TEXT PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    csrf_token   TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip           TEXT,
    user_agent   TEXT
);
CREATE INDEX sessions_user ON sessions (user_id);
CREATE INDEX sessions_expires ON sessions (expires_at);

-- Append-only record of security-relevant actions.
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_type  TEXT NOT NULL CHECK (actor_type IN ('user', 'site', 'system', 'anonymous')),
    actor_id    TEXT,
    action      TEXT NOT NULL,
    target      TEXT,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip          TEXT
);
CREATE INDEX audit_log_at ON audit_log (at DESC);
CREATE INDEX audit_log_action_target ON audit_log (action, target, at DESC);
