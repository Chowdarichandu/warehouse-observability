CREATE TABLE obs.onboarding_requests (
 tenant_id text PRIMARY KEY REFERENCES obs.tenants(tenant_id),
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT,INSERT,UPDATE,DELETE ON obs.onboarding_requests TO obs_app;
GRANT SELECT ON obs.onboarding_requests TO obs_ro;
