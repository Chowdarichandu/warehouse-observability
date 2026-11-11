-- R1 expands the original console schema into the durable v3 data model.
-- Existing columns and tables remain available while consumers migrate.

ALTER TABLE obs.tenants
    ADD COLUMN sources jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN alert_channel_id text,
    ADD COLUMN size_class text NOT NULL DEFAULT 'M',
    ADD COLUMN registered_at timestamptz NOT NULL DEFAULT now();

UPDATE obs.tenants
SET registered_at = created_at,
    warehouse_schema = coalesce(nullif(warehouse_schema, ''), tenant_id),
    sources = jsonb_strip_nulls(jsonb_build_object(
        'mysql', CASE WHEN has_mysql THEN jsonb_build_object('database_per_tenant', true) END,
        'mongo', CASE WHEN has_mongo THEN jsonb_build_object(
            'shared', true, 'tenant_field', 'tenant_id'
        ) END
    ));

CREATE OR REPLACE FUNCTION obs.default_warehouse_schema()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.warehouse_schema IS NULL OR NEW.warehouse_schema = '' THEN
        NEW.warehouse_schema := NEW.tenant_id;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tenants_default_warehouse_schema
BEFORE INSERT OR UPDATE OF tenant_id, warehouse_schema ON obs.tenants
FOR EACH ROW EXECUTE FUNCTION obs.default_warehouse_schema();

ALTER TABLE obs.tenants
    ALTER COLUMN warehouse_schema SET NOT NULL,
    ADD CONSTRAINT tenants_size_class_check CHECK (size_class IN ('S', 'M', 'L'));

ALTER TABLE obs.pipeline_runs
    ADD COLUMN in_maintenance boolean NOT NULL DEFAULT false,
    ADD COLUMN in_retry_backoff boolean NOT NULL DEFAULT false,
    ADD COLUMN operation_id uuid,
    ALTER COLUMN map_index SET DEFAULT -1;
UPDATE obs.pipeline_runs SET map_index = -1 WHERE map_index IS NULL;
ALTER TABLE obs.pipeline_runs ALTER COLUMN map_index SET NOT NULL;
ALTER TABLE obs.pipeline_runs
    ADD CONSTRAINT pipeline_runs_operation_id_fkey
    FOREIGN KEY (operation_id) REFERENCES obs.operations(id) ON DELETE SET NULL;
CREATE INDEX pipeline_runs_operation_idx ON obs.pipeline_runs(operation_id) WHERE operation_id IS NOT NULL;

ALTER TABLE obs.run_errors ADD COLUMN failure_type text;

CREATE TABLE obs.incidents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id text REFERENCES obs.tenants(tenant_id) ON DELETE SET NULL,
    source_type text CHECK (source_type IN ('mysql', 'mongo')),
    severity text NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    state text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'acknowledged', 'resolved')),
    title text NOT NULL,
    cause_rule text,
    opened_at timestamptz NOT NULL DEFAULT now(),
    acknowledged_by text,
    acknowledged_at timestamptz,
    resolved_by text,
    resolved_at timestamptz,
    assignee text,
    root_cause_category text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (state <> 'acknowledged' OR acknowledged_at IS NOT NULL),
    CHECK (state <> 'resolved' OR resolved_at IS NOT NULL)
);
CREATE INDEX incidents_opened_idx ON obs.incidents(opened_at DESC);
CREATE INDEX incidents_tenant_state_idx ON obs.incidents(tenant_id, state, opened_at DESC);

CREATE TABLE obs.incident_notes (
    id bigserial PRIMARY KEY,
    incident_id uuid NOT NULL REFERENCES obs.incidents(id) ON DELETE CASCADE,
    author text NOT NULL,
    body text NOT NULL CHECK (length(body) BETWEEN 1 AND 10000),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX incident_notes_timeline_idx ON obs.incident_notes(incident_id, created_at, id);

ALTER TABLE obs.alerts
    ADD COLUMN incident_id uuid REFERENCES obs.incidents(id) ON DELETE SET NULL;
ALTER TABLE obs.alerts DROP CONSTRAINT IF EXISTS alerts_state_check;
ALTER TABLE obs.alerts ADD CONSTRAINT alerts_state_check
    CHECK (state IN ('firing', 'acked', 'resolved', 'open', 'acknowledged'));
CREATE INDEX alerts_incident_idx ON obs.alerts(incident_id) WHERE incident_id IS NOT NULL;

ALTER TABLE obs.notification_channels
    ADD COLUMN target_secret_ref text;
ALTER TABLE obs.notification_channels DROP CONSTRAINT IF EXISTS notification_channels_kind_check;
ALTER TABLE obs.notification_channels ADD CONSTRAINT notification_channels_kind_check
    CHECK (kind IN ('slack', 'teams', 'email', 'smtp', 'ses', 'sns'));
UPDATE obs.notification_channels
SET target_secret_ref = 'env:' || target_env
WHERE target_secret_ref IS NULL AND target_env <> '';

CREATE TABLE obs.notification_outbox (
    id bigserial PRIMARY KEY,
    channel_id text NOT NULL REFERENCES obs.notification_channels(channel_id) ON DELETE CASCADE,
    payload jsonb NOT NULL,
    thread_key text,
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'sending', 'delivered', 'dead')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    delivered_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'delivered') = (delivered_at IS NOT NULL))
);
CREATE INDEX notification_outbox_delivery_idx ON obs.notification_outbox(next_attempt_at, id)
    WHERE state IN ('pending', 'sending');
CREATE INDEX notification_outbox_retention_idx ON obs.notification_outbox(delivered_at)
    WHERE state = 'delivered';

CREATE TABLE obs.maintenance_windows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id text NOT NULL REFERENCES obs.tenants(tenant_id) ON DELETE CASCADE,
    starts_at timestamptz,
    ends_at timestamptz,
    rrule text,
    timezone text NOT NULL DEFAULT 'UTC',
    reason text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (starts_at IS NOT NULL AND ends_at IS NOT NULL AND starts_at < ends_at AND rrule IS NULL)
        OR (starts_at IS NULL AND ends_at IS NULL AND rrule IS NOT NULL AND length(rrule) <= 2000)
    )
);
CREATE INDEX maintenance_windows_tenant_time_idx ON obs.maintenance_windows(tenant_id, starts_at, ends_at);

CREATE TABLE obs.silences (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope text NOT NULL CHECK (scope IN ('tenant', 'rule')),
    tenant_id text REFERENCES obs.tenants(tenant_id) ON DELETE CASCADE,
    rule_id text REFERENCES obs.alert_rules(rule_id) ON DELETE CASCADE,
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 1000),
    expires_at timestamptz NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (scope = 'tenant' AND tenant_id IS NOT NULL AND rule_id IS NULL)
        OR (scope = 'rule' AND tenant_id IS NULL AND rule_id IS NOT NULL)
    )
);
CREATE INDEX silences_expiration_idx ON obs.silences(expires_at);

ALTER TABLE obs.operations
    ADD COLUMN requested_by text NOT NULL DEFAULT 'system',
    ADD COLUMN state text NOT NULL DEFAULT 'requested',
    ADD COLUMN request jsonb NOT NULL DEFAULT '{}'::jsonb;
UPDATE obs.operations
SET requested_by = coalesce(actor, 'system'),
    state = CASE status
        WHEN 'pending' THEN 'requested'
        WHEN 'sending' THEN 'running'
        WHEN 'succeeded' THEN 'succeeded'
        WHEN 'failed' THEN 'failed'
        WHEN 'uncertain' THEN 'needs_review'
        ELSE 'needs_review'
    END,
    request = coalesce(payload, '{}'::jsonb);
ALTER TABLE obs.operations
    ADD CONSTRAINT operations_state_check
        CHECK (state IN ('requested', 'running', 'succeeded', 'failed', 'needs_review'));
CREATE INDEX operations_state_updated_idx ON obs.operations(state, updated_at DESC);

CREATE OR REPLACE FUNCTION obs.sync_operation_contract()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
        NEW.state := CASE NEW.status
            WHEN 'pending' THEN 'requested'
            WHEN 'sending' THEN 'running'
            WHEN 'succeeded' THEN 'succeeded'
            WHEN 'failed' THEN 'failed'
            WHEN 'uncertain' THEN 'needs_review'
            ELSE 'needs_review'
        END;
    END IF;
    IF NEW.requested_by = 'system' AND NEW.actor IS NOT NULL THEN
        NEW.requested_by := NEW.actor;
    END IF;
    IF NEW.request = '{}'::jsonb AND NEW.payload IS NOT NULL THEN
        NEW.request := NEW.payload;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER operations_sync_contract
BEFORE INSERT OR UPDATE OF actor, payload, status ON obs.operations
FOR EACH ROW EXECUTE FUNCTION obs.sync_operation_contract();

ALTER TABLE obs.quality_checks DROP CONSTRAINT IF EXISTS quality_checks_kind_check;
ALTER TABLE obs.quality_checks ADD CONSTRAINT quality_checks_kind_check
    CHECK (kind IN ('null_rate', 'duplicate_keys', 'accepted_values', 'schema_contract', 'tenant_isolation'));

CREATE TABLE obs.dependency_edges (
    from_asset text NOT NULL,
    to_asset text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('configured', 'observed')),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_seen timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (from_asset, to_asset, kind),
    CHECK (from_asset <> to_asset)
);
CREATE INDEX dependency_edges_to_asset_idx ON obs.dependency_edges(to_asset, last_seen DESC);

CREATE TABLE obs.runbooks (
    error_class text PRIMARY KEY,
    hint text NOT NULL,
    url text,
    updated_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE obs.saved_views
    ADD COLUMN page text NOT NULL DEFAULT 'overview',
    ADD COLUMN query jsonb NOT NULL DEFAULT '{}'::jsonb;
UPDATE obs.saved_views SET query = filters;
ALTER TABLE obs.saved_views ADD CONSTRAINT saved_views_page_check
    CHECK (page IN ('overview', 'tenants', 'runs', 'errors', 'freshness', 'metrics', 'quality', 'dependencies'));

ALTER TABLE obs.users
    ADD COLUMN status text NOT NULL DEFAULT 'active',
    ADD COLUMN last_sign_in_at timestamptz;
ALTER TABLE obs.users ADD CONSTRAINT users_status_check
    CHECK (status IN ('active', 'invited', 'disabled'));

ALTER TABLE obs.sessions
    ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN last_seen_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN ip inet,
    ADD COLUMN user_agent text;
CREATE INDEX sessions_user_active_idx ON obs.sessions(user_id, expires_at DESC) WHERE revoked_at IS NULL;

CREATE TABLE obs.password_reset_tokens (
    token_hash text PRIMARY KEY,
    user_id bigint REFERENCES obs.users(user_id) ON DELETE CASCADE,
    email text NOT NULL,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(token_hash) >= 32)
);
CREATE INDEX password_reset_tokens_expiration_idx ON obs.password_reset_tokens(expires_at);

CREATE TABLE obs.invites (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    display_name text,
    role text NOT NULL CHECK (role IN ('viewer', 'operator', 'admin')),
    role_name text REFERENCES obs.roles(name) ON DELETE SET NULL,
    token_hash text NOT NULL UNIQUE,
    invited_by text NOT NULL,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(token_hash) >= 32)
);
CREATE INDEX invites_email_idx ON obs.invites(lower(email), expires_at DESC);

CREATE TABLE obs.api_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    token_hash text NOT NULL UNIQUE,
    scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_by bigint NOT NULL REFERENCES obs.users(user_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);
CREATE INDEX api_tokens_creator_idx ON obs.api_tokens(created_by, created_at DESC);

ALTER TABLE obs.audit_log
    ADD COLUMN request_id text,
    ADD COLUMN outcome text NOT NULL DEFAULT 'success';
CREATE INDEX audit_log_retention_idx ON obs.audit_log(at);

CREATE TABLE obs.app_settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE obs.daily_rollups
    ADD COLUMN cancelled bigint NOT NULL DEFAULT 0,
    ADD COLUMN skipped bigint NOT NULL DEFAULT 0,
    ADD COLUMN run_count bigint NOT NULL DEFAULT 0;

CREATE TABLE obs.warehouse_daily_rollups (
    day date NOT NULL,
    tenant_id text NOT NULL,
    table_name text NOT NULL,
    samples bigint NOT NULL,
    min_row_count bigint,
    max_row_count bigint,
    avg_row_count numeric,
    last_loaded_at timestamptz,
    PRIMARY KEY (day, tenant_id, table_name)
);

CREATE TABLE obs.platform_daily_rollups (
    day date NOT NULL,
    component text NOT NULL,
    up_count bigint NOT NULL,
    degraded_count bigint NOT NULL,
    down_count bigint NOT NULL,
    last_status text NOT NULL CHECK (last_status IN ('up', 'degraded', 'down')),
    last_checked_at timestamptz NOT NULL,
    PRIMARY KEY (day, component)
);

-- Module visibility is an authorization concern, not a client-side filter.
-- Pravah is active by default; future suite areas remain disabled until shipped.
CREATE TABLE obs.modules (
    module_id text PRIMARY KEY,
    display_name text NOT NULL,
    enabled boolean NOT NULL DEFAULT false,
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (module_id ~ '^[a-z][a-z0-9_-]{1,49}$')
);
INSERT INTO obs.modules(module_id, display_name, enabled, sort_order) VALUES
    ('pravah', 'Pravah', true, 10),
    ('hrms', 'HRMS', false, 20),
    ('finance', 'Finance', false, 30),
    ('sap', 'SAP', false, 40),
    ('pos', 'POS', false, 50),
    ('inventory', 'Inventory', false, 60),
    ('support', 'Support', false, 70),
    ('hospitality', 'Hospitality', false, 80)
ON CONFLICT (module_id) DO NOTHING;

CREATE TABLE obs.role_modules (
    role_name text NOT NULL REFERENCES obs.roles(name) ON DELETE CASCADE,
    module_id text NOT NULL REFERENCES obs.modules(module_id) ON DELETE CASCADE,
    granted_by text NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (role_name, module_id)
);
CREATE TABLE obs.user_module_overrides (
    user_id bigint NOT NULL REFERENCES obs.users(user_id) ON DELETE CASCADE,
    module_id text NOT NULL REFERENCES obs.modules(module_id) ON DELETE CASCADE,
    effect text NOT NULL CHECK (effect IN ('grant', 'revoke')),
    updated_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, module_id)
);

CREATE OR REPLACE FUNCTION obs.metric_success_rate(success_count bigint, failure_count bigint)
RETURNS numeric LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT round(100.0 * success_count / nullif(success_count + failure_count, 0), 2)
$$;

CREATE OR REPLACE FUNCTION obs.metric_data_age_minutes(as_of timestamptz, last_success timestamptz)
RETURNS numeric LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN last_success IS NULL THEN NULL
        ELSE round((extract(epoch FROM as_of - last_success) / 60)::numeric, 1) END
$$;

CREATE OR REPLACE FUNCTION obs.metric_is_fresh(
    as_of timestamptz, last_success timestamptz, sla_minutes integer
)
RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT last_success IS NOT NULL
       AND as_of - last_success <= make_interval(mins => sla_minutes)
$$;

CREATE OR REPLACE FUNCTION obs.metric_stuck_threshold(median_seconds double precision, mad_seconds double precision)
RETURNS double precision LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT greatest(median_seconds + 4 * coalesce(mad_seconds, 0), 3 * median_seconds)
$$;

CREATE OR REPLACE VIEW obs.v_metric_runs AS
SELECT r.*,
       coalesce(extract(epoch FROM r.started_at - r.queued_at)::integer, r.queue_delay_s) AS metric_queue_delay_s,
       (r.in_maintenance OR EXISTS (
           SELECT 1 FROM obs.maintenance_windows w
           WHERE w.tenant_id = r.tenant_id
             AND w.rrule IS NULL
             AND r.started_at >= w.starts_at AND r.started_at < w.ends_at
       )) AS metric_in_maintenance
FROM obs.pipeline_runs r;

CREATE OR REPLACE VIEW obs.v_freshness AS
WITH configured_sources AS (
    SELECT t.tenant_id, t.display_name, t.freshness_sla_min, t.registered_at,
           s.source_type
    FROM obs.tenants t
    CROSS JOIN (VALUES ('mysql'), ('mongo')) s(source_type)
    WHERE t.status = 'active'
      AND CASE WHEN t.sources = '{}'::jsonb
          THEN (s.source_type = 'mysql' AND t.has_mysql)
            OR (s.source_type = 'mongo' AND t.has_mongo)
          ELSE t.sources ? s.source_type
      END
), latest_success AS (
    SELECT tenant_id, source_type, max(ended_at) AS last_success_at
    FROM obs.pipeline_runs
    WHERE load_type = 'cdc' AND status = 'success'
    GROUP BY tenant_id, source_type
)
SELECT s.tenant_id, s.display_name, s.source_type, s.freshness_sla_min,
       r.last_success_at, obs.metric_data_age_minutes(now(), r.last_success_at) AS minutes_stale,
       s.registered_at
FROM configured_sources s
LEFT JOIN latest_success r USING (tenant_id, source_type);

CREATE OR REPLACE VIEW obs.v_stuck_runs AS
WITH duration_28d AS (
    SELECT tenant_id, source_type, load_type,
           extract(hour FROM started_at AT TIME ZONE 'UTC')::integer AS hour_of_day,
           duration_s::double precision AS duration_s
    FROM obs.pipeline_runs
    WHERE status = 'success' AND duration_s > 0 AND started_at >= now() - interval '28 days'
), median_28d AS (
    SELECT tenant_id, source_type, load_type, hour_of_day,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_s) AS median_s,
           count(*) AS sample_count
    FROM duration_28d GROUP BY tenant_id, source_type, load_type, hour_of_day
), mad_28d AS (
    SELECT d.tenant_id, d.source_type, d.load_type, d.hour_of_day,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(d.duration_s - m.median_s)) AS mad_s
    FROM duration_28d d JOIN median_28d m USING (tenant_id, source_type, load_type, hour_of_day)
    GROUP BY d.tenant_id, d.source_type, d.load_type, d.hour_of_day
), duration_7d AS (
    SELECT tenant_id, source_type, load_type, duration_s::double precision AS duration_s
    FROM obs.pipeline_runs
    WHERE status = 'success' AND duration_s > 0 AND started_at >= now() - interval '7 days'
), median_7d AS (
    SELECT tenant_id, source_type, load_type,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_s) AS median_s
    FROM duration_7d GROUP BY tenant_id, source_type, load_type
), mad_7d AS (
    SELECT d.tenant_id, d.source_type, d.load_type,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(d.duration_s - m.median_s)) AS mad_s
    FROM duration_7d d JOIN median_7d m USING (tenant_id, source_type, load_type)
    GROUP BY d.tenant_id, d.source_type, d.load_type
), baselines AS (
    SELECT m.tenant_id, m.source_type, m.load_type, m.hour_of_day,
           CASE WHEN m.sample_count >= 4 THEN m.median_s ELSE s.median_s END AS median_s,
           CASE WHEN m.sample_count >= 4 THEN d.mad_s ELSE sd.mad_s END AS mad_s
    FROM median_28d m
    LEFT JOIN mad_28d d USING (tenant_id, source_type, load_type, hour_of_day)
    LEFT JOIN median_7d s USING (tenant_id, source_type, load_type)
    LEFT JOIN mad_7d sd USING (tenant_id, source_type, load_type)
)
SELECT r.run_key, r.tenant_id, r.source_type, r.load_type, r.started_at,
       round((extract(epoch FROM now() - r.started_at) / 60)::numeric, 1) AS running_min,
       round((b.median_s / 60)::numeric, 1) AS usual_min,
       b.median_s AS baseline_median_s,
       b.mad_s AS mad_s,
       obs.metric_stuck_threshold(b.median_s, b.mad_s) AS threshold_s
FROM obs.pipeline_runs r
JOIN baselines b ON b.tenant_id = r.tenant_id
    AND b.source_type = r.source_type AND b.load_type = r.load_type
    AND b.hour_of_day = extract(hour FROM r.started_at AT TIME ZONE 'UTC')::integer
WHERE r.status = 'running'
  AND NOT r.in_retry_backoff
  AND b.median_s IS NOT NULL
  AND extract(epoch FROM now() - r.started_at) > obs.metric_stuck_threshold(b.median_s, b.mad_s);

CREATE OR REPLACE VIEW obs.v_tenant_health AS
WITH freshness AS (
    SELECT tenant_id, max(minutes_stale) AS worst_stale_min,
           bool_or(last_success_at IS NULL) AS never_succeeded,
           bool_or(NOT obs.metric_is_fresh(now(), last_success_at, freshness_sla_min)) AS sla_breached,
           bool_or(last_success_at IS NULL OR
               now() - last_success_at > make_interval(secs => freshness_sla_min * 45.0)) AS sla_warning
    FROM obs.v_freshness GROUP BY tenant_id
), recent_failures AS (
    SELECT tenant_id, count(*) AS failures_24h
    FROM obs.v_metric_runs
    WHERE status = 'failed' AND started_at > now() - interval '24 hours'
      AND NOT metric_in_maintenance
    GROUP BY tenant_id
), latest_cdc AS (
    SELECT tenant_id, bool_or(status = 'failed') AS failed
    FROM obs.v_latest_runs WHERE load_type = 'cdc' GROUP BY tenant_id
), stuck AS (
    SELECT DISTINCT tenant_id FROM obs.v_stuck_runs
), isolation AS (
    SELECT tenant_id, bool_or(status = 'fail') AS failing
    FROM (
        SELECT DISTINCT ON (q.tenant_id, q.id) q.tenant_id, r.status
        FROM obs.quality_checks q
        JOIN obs.quality_results r ON r.check_id = q.id
        WHERE q.kind = 'tenant_isolation'
        ORDER BY q.tenant_id, q.id, r.checked_at DESC, r.id DESC
    ) latest GROUP BY tenant_id
), warning_incidents AS (
    SELECT DISTINCT tenant_id FROM obs.incidents
    WHERE state IN ('open', 'acknowledged') AND severity IN ('medium', 'low')
)
SELECT t.tenant_id, t.display_name, t.status AS tenant_status, t.freshness_sla_min,
       coalesce(r.failures_24h, 0) AS failures_24h, f.worst_stale_min,
       CASE WHEN t.status <> 'active' THEN t.status
       WHEN l.failed OR f.never_succeeded OR f.sla_breached
            OR i.failing THEN 'down'
       WHEN coalesce(r.failures_24h, 0) > 0
            OR f.sla_warning
            OR s.tenant_id IS NOT NULL OR w.tenant_id IS NOT NULL THEN 'degraded'
       ELSE 'healthy' END AS health
FROM obs.tenants t
LEFT JOIN freshness f USING (tenant_id)
LEFT JOIN recent_failures r USING (tenant_id)
LEFT JOIN latest_cdc l USING (tenant_id)
LEFT JOIN stuck s USING (tenant_id)
LEFT JOIN isolation i USING (tenant_id)
LEFT JOIN warning_incidents w USING (tenant_id);

CREATE OR REPLACE VIEW obs.v_mttr AS
SELECT f.run_key, f.tenant_id, f.source_type, f.load_type, f.ended_at AS failure_ended_at,
       s.ended_at AS recovered_at,
       extract(epoch FROM s.ended_at - f.ended_at) / 60 AS recovery_minutes
FROM obs.pipeline_runs f
LEFT JOIN LATERAL (
    SELECT r.ended_at
    FROM obs.pipeline_runs r
    WHERE r.tenant_id = f.tenant_id AND r.source_type = f.source_type
      AND r.load_type = f.load_type AND r.status = 'success'
      AND r.started_at > f.started_at AND r.ended_at >= f.ended_at
    ORDER BY r.ended_at LIMIT 1
) s ON true
WHERE f.status = 'failed' AND f.ended_at IS NOT NULL;

-- Application code may append/read audit events; only the retention function can prune them.
CREATE OR REPLACE FUNCTION obs.prune_audit_log()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, obs AS $$
DECLARE deleted_count integer;
BEGIN
    WITH expired AS (
        SELECT id FROM obs.audit_log
        WHERE at < now() - interval '2 years'
        ORDER BY at LIMIT 5000
    )
    DELETE FROM obs.audit_log a USING expired e WHERE a.id = e.id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;
REVOKE ALL ON FUNCTION obs.prune_audit_log() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION obs.prune_audit_log() TO obs_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA obs TO obs_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA obs TO obs_app;
GRANT SELECT ON ALL TABLES IN SCHEMA obs TO obs_ro;
GRANT SELECT, INSERT ON obs.audit_log TO obs_app;
REVOKE UPDATE, DELETE ON obs.audit_log FROM obs_app;

