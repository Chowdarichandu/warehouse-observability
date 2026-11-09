CREATE VIEW obs.v_latest_runs AS
SELECT DISTINCT ON(tenant_id,source_type,load_type) * FROM obs.pipeline_runs
ORDER BY tenant_id,source_type,load_type,started_at DESC NULLS LAST,run_key DESC;

CREATE VIEW obs.v_freshness AS
SELECT t.tenant_id,t.display_name,s.source_type,t.freshness_sla_min,
 max(r.ended_at) AS last_success_at,
 round(extract(epoch FROM now()-max(r.ended_at))/60) AS minutes_stale
FROM obs.tenants t CROSS JOIN (VALUES ('mysql'),('mongo')) s(source_type)
LEFT JOIN obs.pipeline_runs r ON r.tenant_id=t.tenant_id AND r.source_type=s.source_type AND r.status='success'
WHERE t.status='active' AND ((s.source_type='mysql' AND t.has_mysql) OR (s.source_type='mongo' AND t.has_mongo))
GROUP BY t.tenant_id,t.display_name,s.source_type,t.freshness_sla_min;

CREATE VIEW obs.v_stuck_runs AS
WITH baseline AS (
 SELECT tenant_id,source_type,load_type,percentile_cont(0.5) WITHIN GROUP(ORDER BY duration_s) AS median_s
 FROM obs.pipeline_runs WHERE status='success' AND started_at > now()-interval '7 days' GROUP BY 1,2,3
)
SELECT r.run_key,r.tenant_id,r.source_type,r.load_type,r.started_at,
 round(extract(epoch FROM now()-r.started_at)/60) AS running_min,
 round((b.median_s/60)::numeric,1) AS usual_min
FROM obs.pipeline_runs r JOIN baseline b USING(tenant_id,source_type,load_type)
WHERE r.status='running' AND extract(epoch FROM now()-r.started_at)>3*b.median_s;

CREATE VIEW obs.v_tenant_health AS
SELECT t.tenant_id,t.display_name,t.status AS tenant_status,t.freshness_sla_min,
 coalesce(r.failures_24h,0) AS failures_24h,f.worst_stale_min,
 CASE WHEN t.status<>'active' THEN t.status
 WHEN EXISTS(SELECT 1 FROM obs.v_latest_runs l WHERE l.tenant_id=t.tenant_id AND l.load_type='cdc' AND l.status='failed')
 OR f.never_succeeded OR f.worst_stale_min>t.freshness_sla_min THEN 'down'
 WHEN coalesce(r.failures_24h,0)>0 OR f.worst_stale_min>0.75*t.freshness_sla_min
 OR EXISTS(SELECT 1 FROM obs.v_stuck_runs s WHERE s.tenant_id=t.tenant_id) THEN 'degraded'
 ELSE 'healthy' END AS health
FROM obs.tenants t
LEFT JOIN (SELECT tenant_id,max(minutes_stale) AS worst_stale_min,bool_or(last_success_at IS NULL) AS never_succeeded
 FROM obs.v_freshness GROUP BY tenant_id) f USING(tenant_id)
LEFT JOIN (SELECT tenant_id,count(*) FILTER(WHERE status='failed') AS failures_24h FROM obs.pipeline_runs
 WHERE started_at>now()-interval '24 hours' GROUP BY tenant_id) r USING(tenant_id);
