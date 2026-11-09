ALTER TABLE obs.notification_channels DROP CONSTRAINT notification_channels_kind_check;
ALTER TABLE obs.notification_channels ADD CHECK (kind IN ('slack','teams','email','ses','sns'));
ALTER TABLE obs.notification_deliveries ADD COLUMN attempts integer NOT NULL DEFAULT 0;
ALTER TABLE obs.notification_deliveries ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE obs.notification_deliveries ADD COLUMN lease_until timestamptz;
ALTER TABLE obs.notification_deliveries ADD COLUMN last_error text;
ALTER TABLE obs.notification_deliveries ADD COLUMN delivered_at timestamptz;
CREATE INDEX ON obs.notification_deliveries(next_attempt_at) WHERE status IN ('pending','sending');
CREATE TABLE obs.operations (
 id uuid PRIMARY KEY, idempotency_key text UNIQUE NOT NULL, kind text NOT NULL,
 target text NOT NULL, actor text NOT NULL, status text NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','sending','succeeded','failed','uncertain')),
 payload jsonb NOT NULL DEFAULT '{}', result jsonb, last_error text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE obs.oidc_states (
 state_hash text PRIMARY KEY, nonce text NOT NULL, verifier text NOT NULL,
 expires_at timestamptz NOT NULL
);
CREATE TABLE obs.oidc_identities (
 issuer text NOT NULL, subject text NOT NULL, user_id bigint NOT NULL REFERENCES obs.users(user_id),
 PRIMARY KEY(issuer,subject)
);
CREATE TABLE obs.sessions (
 id uuid PRIMARY KEY, user_id bigint NOT NULL REFERENCES obs.users(user_id),
 expires_at timestamptz NOT NULL, revoked_at timestamptz
);
CREATE INDEX ON obs.sessions(expires_at);
CREATE TABLE obs.daily_rollups (
 day date NOT NULL, tenant_id text NOT NULL, source_type text NOT NULL, load_type text NOT NULL,
 successes bigint NOT NULL, failures bigint NOT NULL, duration_sum_s bigint NOT NULL,
 PRIMARY KEY(day,tenant_id,source_type,load_type)
);
CREATE TABLE obs.provisioning_resources (
 tenant_id text NOT NULL, resource_key text NOT NULL, remote_id text,
 state text NOT NULL CHECK(state IN ('creating','ready','uncertain')),
 updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,resource_key)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA obs TO obs_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA obs TO obs_app;
GRANT SELECT ON ALL TABLES IN SCHEMA obs TO obs_ro;
