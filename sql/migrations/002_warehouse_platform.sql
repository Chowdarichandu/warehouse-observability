CREATE TABLE obs.warehouse_snapshots (
 tenant_id text NOT NULL, table_name text NOT NULL, row_count bigint, last_loaded_at timestamptz,
 checked_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,table_name,checked_at)
);
CREATE TABLE obs.schema_snapshots (
 tenant_id text NOT NULL, table_name text NOT NULL, columns jsonb NOT NULL,
 columns_hash text NOT NULL, checked_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,table_name,checked_at)
);
CREATE TABLE obs.platform_health (
 component text NOT NULL, status text NOT NULL CHECK(status IN ('up','degraded','down')),
 details jsonb, checked_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(component,checked_at)
);
CREATE TABLE obs.collector_state (
 component text PRIMARY KEY, watermark timestamptz, last_success_at timestamptz,
 last_poll_ms integer, last_error text, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE obs.tenant_events (
 id bigserial PRIMARY KEY, tenant_id text NOT NULL, step text NOT NULL,
 status text NOT NULL CHECK(status IN ('started','ok','failed')), message text,
 at timestamptz NOT NULL DEFAULT now()
);
-- Durable simulator state lets workers restart safely without in-memory background jobs.
CREATE TABLE obs.demo_jobs (
 job_key text PRIMARY KEY, kind text NOT NULL, tenant_id text NOT NULL, payload jsonb NOT NULL,
 step integer NOT NULL DEFAULT 0, due_at timestamptz NOT NULL DEFAULT now(), done boolean NOT NULL DEFAULT false
);
