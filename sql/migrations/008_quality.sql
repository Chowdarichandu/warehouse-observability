CREATE TABLE obs.quality_checks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES obs.tenants(tenant_id),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    table_name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('null_rate','duplicate_keys','accepted_values','schema_contract')),
    params jsonb NOT NULL,
    sample_limit integer NOT NULL DEFAULT 1000 CHECK(sample_limit BETWEEN 1 AND 10000),
    interval_sec integer NOT NULL DEFAULT 900 CHECK(interval_sec BETWEEN 60 AND 86400),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz,
    UNIQUE(tenant_id,name)
);
CREATE TABLE obs.quality_results (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    check_id bigint NOT NULL REFERENCES obs.quality_checks(id) ON DELETE CASCADE,
    tenant_id text NOT NULL REFERENCES obs.tenants(tenant_id),
    status text NOT NULL CHECK(status IN ('pass','fail','error')),
    sampled_rows integer NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    simulated boolean NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX quality_results_check_time ON obs.quality_results(check_id,checked_at DESC);
CREATE INDEX quality_results_tenant_time ON obs.quality_results(tenant_id,checked_at DESC);
GRANT SELECT,INSERT,UPDATE,DELETE ON obs.quality_checks,obs.quality_results TO obs_app;
GRANT SELECT ON obs.quality_checks,obs.quality_results TO obs_ro;
GRANT USAGE,SELECT ON SEQUENCE obs.quality_checks_id_seq,obs.quality_results_id_seq TO obs_app;
