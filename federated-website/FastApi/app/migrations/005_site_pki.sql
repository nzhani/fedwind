-- Site PKI (SITE_NETWORK_PLAN.md M3, §2.3): every revoked plant certificate and Flower node.
-- No foreign key on purpose: the row outlives the site, so a deleted plant's certificate stays in
-- the CRL until it expires and its Flower node is still unregistered if the first attempt failed.

CREATE TABLE site_revocations (
    id                      BIGSERIAL PRIMARY KEY,
    site_id                 TEXT NOT NULL,
    credential_id           BIGINT,                     -- site_credentials.id at revocation time
    cert_serial             TEXT UNIQUE,                -- upper-case hex, as nginx's $ssl_client_serial
    cert_not_after          TIMESTAMPTZ,                -- leaves the CRL after this
    flower_node_id          TEXT,
    revoked_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    flower_unregistered_at  TIMESTAMPTZ,                -- NULL with a node id: retried by the maintenance loop
    flower_error            TEXT
);
CREATE INDEX site_revocations_pending ON site_revocations (revoked_at)
    WHERE flower_node_id IS NOT NULL AND flower_unregistered_at IS NULL;

-- A Flower key can be registered once only (Flower refuses a key it has seen): a re-issued kit needs new keys
CREATE INDEX site_credentials_flower_pubkey ON site_credentials (flower_pubkey) WHERE flower_pubkey IS NOT NULL;
