CREATE TABLE obs.tenants (
 tenant_id text PRIMARY KEY, display_name text NOT NULL,
 status text NOT NULL DEFAULT 'onboarding' CHECK(status IN ('onboarding','active','paused','offboarded')),
 has_mysql boolean NOT NULL DEFAULT true, has_mongo boolean NOT NULL DEFAULT true,
 airbyte_connections jsonb NOT NULL DEFAULT '{}', warehouse_schema text,
 freshness_sla_min integer NOT NULL DEFAULT 120 CHECK(freshness_sla_min > 0), owner_email text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE obs.pipeline_runs (
 run_key text PRIMARY KEY, tenant_id text NOT NULL REFERENCES obs.tenants(tenant_id),
 source_type text NOT NULL CHECK(source_type IN ('mysql','mongo')),
 load_type text NOT NULL CHECK(load_type IN ('initial','cdc')),
 status text NOT NULL CHECK(status IN ('queued','running','success','failed','cancelled','skipped')),
 failed_stage text CHECK(failed_stage IN ('airflow','airbyte','warehouse')),
 triggered_by text NOT NULL DEFAULT 'schedule', scheduled_for timestamptz, queued_at timestamptz,
 started_at timestamptz, ended_at timestamptz, duration_s integer, queue_delay_s integer,
 rows_synced bigint, bytes_synced bigint, dag_id text, dag_run_id text, task_id text,
 map_index integer DEFAULT -1, try_number integer, airbyte_connection_id text,
 airbyte_job_id bigint, airbyte_attempts integer, collected_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON obs.pipeline_runs(tenant_id, started_at DESC);
CREATE INDEX ON obs.pipeline_runs(status, started_at DESC);
CREATE INDEX ON obs.pipeline_runs(started_at DESC);
CREATE INDEX ON obs.pipeline_runs(airbyte_job_id);
CREATE INDEX ON obs.pipeline_runs(tenant_id,source_type,ended_at DESC) WHERE status='success';
CREATE TABLE obs.run_stream_stats (
 run_key text NOT NULL REFERENCES obs.pipeline_runs(run_key) ON DELETE CASCADE,
 stream_name text NOT NULL, records bigint, bytes bigint, PRIMARY KEY(run_key,stream_name)
);
CREATE TABLE obs.error_groups (
 fingerprint text PRIMARY KEY, error_class text NOT NULL, sample_message text,
 first_seen timestamptz NOT NULL, last_seen timestamptz NOT NULL, occurrences integer NOT NULL DEFAULT 1
);
CREATE TABLE obs.run_errors (
 run_key text PRIMARY KEY REFERENCES obs.pipeline_runs(run_key) ON DELETE CASCADE,
 tenant_id text NOT NULL, stage text NOT NULL, failure_origin text, error_class text NOT NULL,
 severity text NOT NULL DEFAULT 'error', fingerprint text REFERENCES obs.error_groups(fingerprint),
 error_message text, hint text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON obs.run_errors(fingerprint);
CREATE TABLE obs.run_logs (
 run_key text PRIMARY KEY REFERENCES obs.pipeline_runs(run_key) ON DELETE CASCADE,
 source text NOT NULL CHECK(source IN ('airflow','airbyte')), content text NOT NULL,
 tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple',content)) STORED
);
CREATE INDEX ON obs.run_logs USING gin(tsv);
