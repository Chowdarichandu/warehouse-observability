-- Aggregate execution evidence once per tenant. Correlated EXISTS expressions in
-- the original view were repeated when callers sorted by the computed health,
-- inflating planner cost enough to trigger expensive JIT optimization even for
-- a ten-tenant console. Preserve the original health CASE and freshness rules.
CREATE INDEX pipeline_runs_latest_pipeline_idx ON obs.pipeline_runs
    (tenant_id, source_type, load_type, started_at DESC NULLS LAST, run_key DESC);

CREATE OR REPLACE VIEW obs.v_tenant_health AS
WITH freshness AS (
    SELECT tenant_id, max(minutes_stale) AS worst_stale_min,
        bool_or(last_success_at IS NULL) AS never_succeeded
    FROM obs.v_freshness GROUP BY tenant_id
), recent_failures AS (
    SELECT tenant_id, count(*) FILTER (WHERE status = 'failed') AS failures_24h
    FROM obs.pipeline_runs
    WHERE started_at > now() - interval '24 hours' GROUP BY tenant_id
), latest_cdc AS (
    SELECT tenant_id, bool_or(status = 'failed') AS failed
    FROM obs.v_latest_runs WHERE load_type = 'cdc' GROUP BY tenant_id
), stuck AS (
    SELECT DISTINCT tenant_id FROM obs.v_stuck_runs
)
SELECT t.tenant_id, t.display_name, t.status AS tenant_status, t.freshness_sla_min,
    coalesce(r.failures_24h, 0) AS failures_24h, f.worst_stale_min,
    CASE WHEN t.status <> 'active' THEN t.status
    WHEN l.failed OR f.never_succeeded OR f.worst_stale_min > t.freshness_sla_min THEN 'down'
    WHEN coalesce(r.failures_24h, 0) > 0
        OR f.worst_stale_min > 0.75 * t.freshness_sla_min
        OR s.tenant_id IS NOT NULL THEN 'degraded'
    ELSE 'healthy' END AS health
FROM obs.tenants t
LEFT JOIN freshness f USING (tenant_id)
LEFT JOIN recent_failures r USING (tenant_id)
LEFT JOIN latest_cdc l USING (tenant_id)
LEFT JOIN stuck s USING (tenant_id);
