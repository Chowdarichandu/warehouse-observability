"""Bounded retention and daily rollups. Runs under the collector's leader lock."""

from obs.db import connection
from obs.settings import settings


def retain() -> None:
    if not settings().retention_enabled:
        return
    with connection() as conn:
        conn.execute("""INSERT INTO obs.daily_rollups(day,tenant_id,source_type,load_type,successes,failures,duration_sum_s)
            SELECT (started_at AT TIME ZONE 'UTC')::date,tenant_id,source_type,load_type,
                count(*) FILTER(WHERE status='success'),count(*) FILTER(WHERE status='failed'),
                coalesce(sum(duration_s) FILTER(WHERE status='success'),0)
            FROM obs.pipeline_runs WHERE started_at < date_trunc('day',now())
            AND started_at >= coalesce((SELECT max(day)::timestamptz-interval '1 day' FROM obs.daily_rollups),now()-interval '13 months')
            GROUP BY 1,2,3,4 ON CONFLICT(day,tenant_id,source_type,load_type) DO UPDATE SET
            successes=excluded.successes,failures=excluded.failures,duration_sum_s=excluded.duration_sum_s""")
        for table, column, age in [
            ("run_logs", "run_key", "90 days"),
            ("pipeline_runs", "run_key", "13 months"),
        ]:
            condition = "started_at<now()-%s::interval"
            if table == "run_logs":
                condition = "run_key IN (SELECT run_key FROM obs.pipeline_runs WHERE started_at<now()-%s::interval)"
            for _ in range(10):
                result = conn.execute(
                    f"DELETE FROM obs.{table} WHERE {column} IN (SELECT {column} FROM obs.{table} WHERE {condition} LIMIT 5000)",
                    (age,),
                )
                if result.rowcount < 5000:
                    break
        for table in ("warehouse_snapshots", "schema_snapshots", "platform_health"):
            for _ in range(10):
                result = conn.execute(
                    f"DELETE FROM obs.{table} WHERE ctid IN (SELECT ctid FROM obs.{table} WHERE checked_at<now()-interval '30 days' LIMIT 5000)"
                )
                if result.rowcount < 5000:
                    break
        conn.execute("DELETE FROM obs.oidc_states WHERE expires_at<now()")
        conn.execute("DELETE FROM obs.sessions WHERE expires_at<now()")
        conn.execute(
            "DELETE FROM obs.notification_deliveries WHERE at<now()-interval '90 days' AND status IN ('sent','simulated','cancelled')"
        )
        conn.execute(
            "DELETE FROM obs.error_groups WHERE NOT EXISTS (SELECT 1 FROM obs.run_errors WHERE fingerprint=obs.error_groups.fingerprint)"
        )
