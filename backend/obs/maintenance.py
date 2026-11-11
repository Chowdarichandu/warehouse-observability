"""Bounded retention and daily rollups. Runs under the collector's leader lock."""

from obs.db import connection
from obs.settings import settings


def retain() -> None:
    if not settings().retention_enabled:
        return
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.daily_rollups(
                day,tenant_id,source_type,load_type,successes,failures,duration_sum_s,
                cancelled,skipped,run_count
            )
            SELECT (started_at AT TIME ZONE 'UTC')::date,tenant_id,source_type,load_type,
                count(*) FILTER(WHERE status='success'),count(*) FILTER(WHERE status='failed'),
                coalesce(sum(duration_s) FILTER(WHERE status='success'),0),
                count(*) FILTER(WHERE status='cancelled'),count(*) FILTER(WHERE status='skipped'),count(*)
            FROM obs.pipeline_runs
            WHERE started_at < date_trunc('day',now())
              AND (
                  started_at >= date_trunc('day',now()) - interval '2 days'
                  OR NOT EXISTS (
                      SELECT 1 FROM obs.daily_rollups d
                      WHERE d.day=(obs.pipeline_runs.started_at AT TIME ZONE 'UTC')::date
                        AND d.tenant_id=obs.pipeline_runs.tenant_id
                        AND d.source_type=obs.pipeline_runs.source_type
                        AND d.load_type=obs.pipeline_runs.load_type
                  )
              )
            GROUP BY 1,2,3,4
            ON CONFLICT(day,tenant_id,source_type,load_type) DO UPDATE SET
                successes=excluded.successes,failures=excluded.failures,
                duration_sum_s=excluded.duration_sum_s,cancelled=excluded.cancelled,
                skipped=excluded.skipped,run_count=excluded.run_count"""
        )

        # Preserve daily history before pruning the high-resolution snapshots.
        conn.execute(
            """INSERT INTO obs.warehouse_daily_rollups(
                day,tenant_id,table_name,samples,min_row_count,max_row_count,avg_row_count,last_loaded_at
            )
            SELECT (w.checked_at AT TIME ZONE 'UTC')::date,w.tenant_id,w.table_name,count(*),
                min(w.row_count),max(w.row_count),avg(w.row_count),max(w.last_loaded_at)
            FROM obs.warehouse_snapshots w
            WHERE w.checked_at < date_trunc('day',now())
              AND ((w.checked_at >= now()-interval '31 days') OR NOT EXISTS (
                  SELECT 1 FROM obs.warehouse_daily_rollups d
                  WHERE d.day=(w.checked_at AT TIME ZONE 'UTC')::date
                    AND d.tenant_id=w.tenant_id AND d.table_name=w.table_name
              ))
            GROUP BY 1,2,3
            ON CONFLICT(day,tenant_id,table_name) DO UPDATE SET
                samples=excluded.samples,min_row_count=excluded.min_row_count,
                max_row_count=excluded.max_row_count,avg_row_count=excluded.avg_row_count,
                last_loaded_at=excluded.last_loaded_at"""
        )
        conn.execute(
            """INSERT INTO obs.platform_daily_rollups(
                day,component,up_count,degraded_count,down_count,last_status,last_checked_at
            )
            SELECT day,component,up_count,degraded_count,down_count,last_status,last_checked_at
            FROM (
                SELECT (h.checked_at AT TIME ZONE 'UTC')::date AS day,h.component,
                    count(*) FILTER(WHERE h.status='up') AS up_count,
                    count(*) FILTER(WHERE h.status='degraded') AS degraded_count,
                    count(*) FILTER(WHERE h.status='down') AS down_count,
                    (array_agg(h.status ORDER BY h.checked_at DESC))[1] AS last_status,
                    max(h.checked_at) AS last_checked_at
                FROM obs.platform_health h
                WHERE h.checked_at < date_trunc('day',now())
                  AND ((h.checked_at >= now()-interval '31 days') OR NOT EXISTS (
                      SELECT 1 FROM obs.platform_daily_rollups d
                      WHERE d.day=(h.checked_at AT TIME ZONE 'UTC')::date
                        AND d.component=h.component
                  ))
                GROUP BY 1,2
            ) history
            ON CONFLICT(day,component) DO UPDATE SET
                up_count=excluded.up_count,degraded_count=excluded.degraded_count,
                down_count=excluded.down_count,last_status=excluded.last_status,
                last_checked_at=excluded.last_checked_at"""
        )

        for _ in range(10):
            result = conn.execute(
                """WITH batch AS (
                    SELECT l.run_key FROM obs.run_logs l
                    JOIN obs.pipeline_runs r USING(run_key)
                    WHERE r.started_at < now()-interval '90 days'
                    LIMIT 5000
                ) DELETE FROM obs.run_logs l USING batch b WHERE l.run_key=b.run_key"""
            )
            if result.rowcount < 5000:
                break

        for _ in range(10):
            result = conn.execute(
                """WITH batch AS (
                    SELECT run_key FROM obs.pipeline_runs
                    WHERE started_at < now()-interval '13 months'
                    ORDER BY started_at LIMIT 5000
                ) DELETE FROM obs.pipeline_runs r USING batch b WHERE r.run_key=b.run_key"""
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
            "DELETE FROM obs.password_reset_tokens WHERE expires_at<now()-interval '30 days'"
        )
        conn.execute("DELETE FROM obs.invites WHERE expires_at<now()-interval '30 days'")
        conn.execute("DELETE FROM obs.silences WHERE expires_at<now()-interval '30 days'")
        conn.execute(
            "DELETE FROM obs.notification_outbox WHERE state='delivered' AND delivered_at<now()-interval '30 days'"
        )
        conn.execute(
            "DELETE FROM obs.notification_deliveries WHERE at<now()-interval '90 days' AND status IN ('sent','simulated','cancelled')"
        )
        for _ in range(10):
            if conn.execute("SELECT obs.prune_audit_log() AS deleted").fetchone()["deleted"] < 5000:
                break
        conn.execute(
            "DELETE FROM obs.error_groups WHERE NOT EXISTS (SELECT 1 FROM obs.run_errors WHERE fingerprint=obs.error_groups.fingerprint)"
        )
