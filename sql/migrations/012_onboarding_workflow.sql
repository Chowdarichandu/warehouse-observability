CREATE TABLE IF NOT EXISTS obs.onboarding_workflows (
 workflow_id uuid PRIMARY KEY, tenant_id text UNIQUE NOT NULL REFERENCES obs.tenants(tenant_id),
 state text NOT NULL DEFAULT 'running' CHECK(state IN ('running','failed','uncertain','awaiting_initial','success')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS obs.onboarding_dag_attempts (
 workflow_id uuid NOT NULL REFERENCES obs.onboarding_workflows(workflow_id),
 node_id text NOT NULL, attempt integer NOT NULL DEFAULT 1 CHECK(attempt>0),
 dag_id text NOT NULL, dag_run_id text, parent_dag_run_id text,
 status text NOT NULL CHECK(status IN ('pending','queued','running','success','failed','blocked','skipped','uncertain','awaiting_initial')),
 request_state text NOT NULL DEFAULT 'unsubmitted' CHECK(request_state IN ('unsubmitted','submitting','confirmed','uncertain')),
 started_at timestamptz, ended_at timestamptz, blocked_reason text, last_error text,
 tasks jsonb NOT NULL DEFAULT '[]', updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workflow_id,node_id,attempt), UNIQUE(dag_id,dag_run_id)
);
CREATE INDEX IF NOT EXISTS onboarding_dag_attempts_workflow_id_node_id_attempt_idx ON obs.onboarding_dag_attempts(workflow_id,node_id,attempt DESC);
ALTER TABLE obs.provisioning_resources DROP CONSTRAINT IF EXISTS provisioning_resources_state_check;
ALTER TABLE obs.provisioning_resources ADD CHECK(state IN ('creating','ready','uncertain','failed'));
GRANT SELECT,INSERT,UPDATE,DELETE ON obs.onboarding_workflows,obs.onboarding_dag_attempts TO obs_app;
GRANT SELECT ON obs.onboarding_workflows,obs.onboarding_dag_attempts TO obs_ro;
