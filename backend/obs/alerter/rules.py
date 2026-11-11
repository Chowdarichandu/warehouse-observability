from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from obs.alerter.notify import deliver
from obs.db import connection, notify
from obs.repositories.analytics import anomalies, schema_changes

PARAMS = {
    "cdc_consecutive_failures": {"n"},
    "cdc_position_lost": set(),
    "freshness_breach": {"pct"},
    "stuck_run": {"multiplier"},
    "volume_anomaly": {"drop_pct"},
    "schema_drift": set(),
    "queue_backlog": {"minutes"},
    "dag_import_errors": set(),
    "platform_down": set(),
    "collector_silent": {"minutes"},
    "tenant_isolation": set(),
}

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _incident(
    conn: psycopg.Connection,
    *,
    tenant_id: str | None,
    source_type: str | None,
    severity: str,
    title: str,
    rule_id: str,
) -> dict:
    """Return the open incident for a tenant/source, creating one atomically."""
    # Incidents intentionally use source_type only for the two source systems.
    # Platform rules are grouped at workspace scope with a NULL source.
    source = source_type if source_type in {"mysql", "mongo"} else None
    incident = conn.execute(
        """SELECT * FROM obs.incidents
        WHERE tenant_id IS NOT DISTINCT FROM %s
          AND source_type IS NOT DISTINCT FROM %s
          AND state IN ('open','acknowledged')
        ORDER BY opened_at DESC LIMIT 1 FOR UPDATE""",
        (tenant_id, source),
    ).fetchone()
    if incident:
        if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(incident["severity"], 0):
            incident = conn.execute(
                """UPDATE obs.incidents SET severity=%s,title=%s,cause_rule=%s,updated_at=now()
                WHERE id=%s RETURNING *""",
                (severity, title, rule_id, incident["id"]),
            ).fetchone()
        else:
            conn.execute("UPDATE obs.incidents SET updated_at=now() WHERE id=%s", (incident["id"],))
        return incident
    return conn.execute(
        """INSERT INTO obs.incidents(tenant_id,source_type,severity,title,cause_rule)
        VALUES(%s,%s,%s,%s,%s) RETURNING *""",
        (tenant_id, source, severity, title, rule_id),
    ).fetchone()


def conditions(conn: psycopg.Connection, rule: dict) -> list[dict]:
    key = rule["rule_id"]
    params = rule["params"]
    found = []
    if key == "cdc_position_lost":
        found = conn.execute("""SELECT DISTINCT ON(r.tenant_id,r.source_type)
            r.tenant_id,r.source_type,e.error_class AS reason,e.hint FROM obs.pipeline_runs r
            JOIN obs.run_errors e USING(run_key) JOIN obs.tenants t ON t.tenant_id=r.tenant_id
            WHERE t.status='active' AND r.load_type='cdc' AND r.status='failed'
            AND e.error_class IN('MYSQL_BINLOG_PURGED','MONGO_CHANGE_STREAM_LOST')
            AND NOT EXISTS(SELECT 1 FROM obs.pipeline_runs recovered
                WHERE recovered.tenant_id=r.tenant_id AND recovered.source_type=r.source_type
                AND recovered.load_type='cdc' AND recovered.status='success'
                AND recovered.started_at>r.started_at)
            ORDER BY r.tenant_id,r.source_type,r.started_at DESC""").fetchall()
    elif key == "cdc_consecutive_failures":
        n = int(params.get("n", 2))
        found = conn.execute(
            """WITH recent AS(SELECT r.*,row_number() OVER(PARTITION BY r.tenant_id,source_type ORDER BY started_at DESC) AS rn
            FROM obs.pipeline_runs r JOIN obs.tenants t USING(tenant_id) WHERE t.status='active' AND load_type='cdc')
            SELECT tenant_id,source_type,'Consecutive CDC runs failed' AS reason FROM recent
            WHERE rn<=%s GROUP BY 1,2 HAVING count(*)=%s AND bool_and(status='failed')""",
            (n, n),
        ).fetchall()
    elif key == "freshness_breach":
        found = conn.execute(
            """SELECT tenant_id,source_type,'Freshness SLA exceeded' AS reason FROM obs.v_freshness
            WHERE last_success_at IS NULL OR now() - last_success_at >
                freshness_sla_min * (%s / 100.0) * interval '1 minute'""",
            (params.get("pct", 100),),
        ).fetchall()
    elif key == "stuck_run":
        found = conn.execute(
            """SELECT tenant_id,source_type,
                'Run is taking longer than its robust duration baseline' AS reason,run_key
            FROM obs.v_stuck_runs
            WHERE extract(epoch FROM now()-started_at) >
                greatest(threshold_s,baseline_median_s*%s)""",
            (max(3, float(params.get("multiplier", 3))),),
        ).fetchall()
    elif key == "volume_anomaly":
        found = [
            {
                **row,
                "source_type": row["table_name"],
                "reason": f"{row['table_name']}: {row['change_pct']}% row-count change",
            }
            for row in anomalies()
            if float(row["change_pct"]) < -params.get("drop_pct", 30)
            or float(row["change_pct"]) > 0
        ]
    elif key == "schema_drift":
        found = [
            {
                **row,
                "source_type": row["table_name"],
                "reason": f"Columns changed on {row['table_name']}",
            }
            for row in schema_changes()
        ]
    elif key == "queue_backlog":
        found = conn.execute(
            """SELECT 'global' AS source_type,'Airflow p95 queue delay is elevated' AS reason
            FROM obs.pipeline_runs WHERE started_at>now()-interval '1 hour'
            HAVING percentile_cont(.95) WITHIN GROUP(ORDER BY queue_delay_s)>%s*60""",
            (params.get("minutes", 15),),
        ).fetchall()
    elif key == "dag_import_errors":
        found = conn.execute("""SELECT component AS source_type,'DAG import error' AS reason FROM
           (SELECT DISTINCT ON(component) * FROM obs.platform_health ORDER BY component,checked_at DESC) x
           WHERE component='airflow_import_errors' AND status<>'up'""").fetchall()
    elif key == "platform_down":
        found = conn.execute("""WITH recent AS(SELECT *,row_number() OVER(PARTITION BY component ORDER BY checked_at DESC) AS rn
          FROM obs.platform_health) SELECT component AS source_type,'Component down in two consecutive checks' AS reason
          FROM recent WHERE rn<=2 GROUP BY component HAVING count(*)=2 AND bool_and(status='down')""").fetchall()
    elif key == "collector_silent":
        found = conn.execute(
            """SELECT component AS source_type,'Collector heartbeat missing' AS reason
            FROM obs.collector_state WHERE last_success_at IS NULL OR last_success_at<now()-%s*interval '1 minute'""",
            (params.get("minutes", 10),),
        ).fetchall()
    elif key == "tenant_isolation":
        found = conn.execute(
            """SELECT q.tenant_id, 'mongo' AS source_type,
                      'Tenant isolation check failed' AS reason, r.details
               FROM obs.quality_results r
               JOIN obs.quality_checks q ON q.id=r.check_id
               JOIN obs.tenants t ON t.tenant_id=q.tenant_id
              WHERE q.kind='tenant_isolation' AND r.status IN ('fail','error')
                AND t.sources->'mongo'->>'shared'='true'
                AND r.checked_at=(SELECT max(r2.checked_at) FROM obs.quality_results r2 WHERE r2.check_id=r.check_id)"""
        ).fetchall()
    return found


def evaluate() -> None:
    now = datetime.now(UTC)
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110529)")
        rules = conn.execute("SELECT * FROM obs.alert_rules").fetchall()
        for rule in rules:
            # A broken rule is isolated to a savepoint; the other rules still run.
            try:
                with conn.transaction():
                    active = conditions(conn, rule) if rule["enabled"] else []
                    fingerprints = set()
                    for item in active:
                        tenant = item.get("tenant_id")
                        fp = f"{rule['rule_id']}|{tenant or 'platform'}|{item.get('source_type', '')}"
                        fingerprints.add(fp)
                        details = {
                            k: str(v) if not isinstance(v, str | int | float | type(None)) else v
                            for k, v in item.items()
                        }
                        title = f"{rule['name']} · {tenant or item.get('source_type', 'platform')}"
                        incident = _incident(
                            conn,
                            tenant_id=tenant,
                            source_type=item.get("source_type"),
                            severity=rule["severity"],
                            title=title,
                            rule_id=rule["rule_id"],
                        )
                        alert = conn.execute(
                            "SELECT * FROM obs.alerts WHERE fingerprint=%s AND state<>'resolved' FOR UPDATE",
                            (fp,),
                        ).fetchone()
                        if not alert:
                            alert = conn.execute(
                                """INSERT INTO obs.alerts(
                                    rule_id,fingerprint,tenant_id,severity,state,title,details,incident_id
                                ) VALUES(%s,%s,%s,%s,'firing',%s,%s,%s) RETURNING *""",
                                (
                                    rule["rule_id"],
                                    fp,
                                    tenant,
                                    rule["severity"],
                                    title,
                                    Jsonb(details),
                                    incident["id"],
                                ),
                            ).fetchone()
                            notify(
                                conn,
                                "alert.fired",
                                {
                                    "id": alert["id"],
                                    "tenant_id": tenant,
                                    "title": title,
                                    "severity": rule["severity"],
                                },
                            )
                        else:
                            conn.execute(
                                """UPDATE obs.alerts SET last_seen_at=%s,details=%s,severity=%s,
                                incident_id=coalesce(incident_id,%s) WHERE id=%s""",
                                (
                                    now,
                                    Jsonb(details),
                                    rule["severity"],
                                    incident["id"],
                                    alert["id"],
                                ),
                            )
                        if alert["state"] != "acked" and (
                            not alert["last_notified_at"]
                            or now - alert["last_notified_at"]
                            >= timedelta(minutes=rule["repeat_min"])
                        ):
                            for channel in rule["channels"]:
                                deliver(
                                    conn,
                                    channel,
                                    "firing",
                                    title + " · " + item.get("reason", ""),
                                    alert["id"],
                                )
                            conn.execute(
                                "UPDATE obs.alerts SET last_notified_at=%s WHERE id=%s",
                                (now, alert["id"]),
                            )
                    for alert in conn.execute(
                        "SELECT * FROM obs.alerts WHERE rule_id=%s AND state<>'resolved'",
                        (rule["rule_id"],),
                    ).fetchall():
                        if alert["fingerprint"] not in fingerprints:
                            conn.execute(
                                "UPDATE obs.alerts SET state='resolved',resolved_at=%s WHERE id=%s",
                                (now, alert["id"]),
                            )
                            if alert.get("incident_id"):
                                conn.execute(
                                    """UPDATE obs.incidents SET state='resolved',resolved_at=%s,updated_at=now()
                                    WHERE id=%s AND NOT EXISTS(
                                        SELECT 1 FROM obs.alerts WHERE incident_id=%s AND state<>'resolved'
                                    )""",
                                    (now, alert["incident_id"], alert["incident_id"]),
                                )
                            for channel in rule["channels"]:
                                deliver(conn, channel, "resolved", alert["title"], alert["id"])
                            notify(
                                conn,
                                "alert.resolved",
                                {"id": alert["id"], "tenant_id": alert["tenant_id"]},
                            )
                    conn.execute(
                        "DELETE FROM obs.collector_state WHERE component=%s",
                        ("alerter:" + rule["rule_id"],),
                    )
            except Exception as exc:
                from obs.redact import redact

                conn.execute(
                    """INSERT INTO obs.collector_state(component,last_error) VALUES(%s,%s)
                    ON CONFLICT(component) DO UPDATE SET last_error=excluded.last_error,updated_at=now()""",
                    ("alerter:" + rule["rule_id"], redact(str(exc))),
                )
        conn.execute(
            "INSERT INTO obs.platform_health(component,status,details) VALUES('alerter','up',%s)",
            (Jsonb({"message": "10 built-in rules evaluated"}),),
        )
