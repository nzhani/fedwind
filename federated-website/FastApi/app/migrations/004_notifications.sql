-- Telegram alerts (FEATURES: alerts). People connect their Telegram account with a one-time code;
-- plant events (taken from the audit log) and connection changes become queued messages.

CREATE TABLE telegram_links (
    user_id      BIGINT PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    chat_id      TEXT NOT NULL,
    tg_username  TEXT,
    linked_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE telegram_link_codes (
    code_hash    TEXT PRIMARY KEY,                   -- sha256 of the one-time code in the t.me link
    user_id      BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ
);

-- Outbox: written in the same transaction as what caused it, sent by the background loop
CREATE TABLE notifications (
    id           BIGSERIAL PRIMARY KEY,
    chat_id      TEXT NOT NULL,
    text         TEXT NOT NULL,
    event        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at      TIMESTAMPTZ,
    attempts     INT NOT NULL DEFAULT 0,
    last_error   TEXT
);
CREATE INDEX notifications_pending ON notifications (id) WHERE sent_at IS NULL;

-- Small key/value state: audit cursor, Telegram update offset
CREATE TABLE notify_state (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Last connection state each plant was alerted about (one message per change, not per heartbeat)
CREATE TABLE site_alert_state (
    site_id  TEXT PRIMARY KEY REFERENCES sites (id) ON DELETE CASCADE,
    state    TEXT NOT NULL,
    at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
