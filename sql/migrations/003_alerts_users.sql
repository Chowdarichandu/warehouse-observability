CREATE TABLE obs.alert_rules (
 rule_id text PRIMARY KEY, name text NOT NULL,
 severity text NOT NULL CHECK(severity IN ('critical','high','medium','low')),
 params jsonb NOT NULL DEFAULT '{}', enabled boolean NOT NULL DEFAULT true,
 repeat_min integer NOT NULL DEFAULT 240 CHECK(repeat_min > 0), channels text[] NOT NULL DEFAULT '{}'
);
CREATE TABLE obs.alerts (
 id bigserial PRIMARY KEY, rule_id text NOT NULL REFERENCES obs.alert_rules(rule_id),
 fingerprint text NOT NULL, tenant_id text, severity text NOT NULL,
 state text NOT NULL CHECK(state IN ('firing','acked','resolved')), title text NOT NULL, details jsonb,
 first_fired_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
 last_notified_at timestamptz, acked_by text, acked_at timestamptz, resolved_at timestamptz
);
CREATE UNIQUE INDEX ON obs.alerts(fingerprint) WHERE state <> 'resolved';
CREATE TABLE obs.notification_channels (
 channel_id text PRIMARY KEY, kind text NOT NULL CHECK(kind IN ('slack','teams','email')),
 target_env text NOT NULL, enabled boolean NOT NULL DEFAULT true
);
CREATE TABLE obs.users (
 user_id bigserial PRIMARY KEY, email text UNIQUE NOT NULL, display_name text,
 role text NOT NULL CHECK(role IN ('viewer','operator','admin')), password_hash text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE obs.audit_log (
 id bigserial PRIMARY KEY, actor text NOT NULL, action text NOT NULL,
 target text, details jsonb, at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE obs.notification_deliveries (
 id bigserial PRIMARY KEY, channel_id text NOT NULL, alert_id bigint,
 kind text NOT NULL, status text NOT NULL, message text, at timestamptz NOT NULL DEFAULT now()
);
