from datetime import UTC, datetime

import psycopg

from obs.collector.classify import classify
from obs.collector.fingerprint import fingerprint
from obs.redact import redact

MESSAGES = {
    "MYSQL_BINLOG_PURGED": "Error 1236: MySQL binlog mysql-bin.004291 has been purged; requested position 881204 is no longer available.",
    "MONGO_CHANGE_STREAM_LOST": "ChangeStreamHistoryLost: resume token is no longer in the oplog.",
    "SOURCE_AUTH": "Access denied for user 'replication_reader'. password=old-secret owner=ops@example.org",
    "SOURCE_UNREACHABLE": "ServerSelectionTimeout: Connection refused by source database after 30000 ms, attempt 3 of 3.",
    "SCHEMA_CHANGE": "Schema mismatch: column 'customer_segment' does not exist in destination table.",
    "DESTINATION_ERROR": "Warehouse permission denied: destination write failed for staging table.",
    "OUT_OF_MEMORY": "OOMKilled: sync worker terminated with exit code 137.",
    "AIRFLOW_INFRA": "Executor reports task instance as zombie; task terminated by SIGTERM.",
}


def enrich_failure(
    conn: psycopg.Connection, run: dict, message: str, origin: str = "source"
) -> None:
    previous = conn.execute(
        "SELECT fingerprint FROM obs.run_errors WHERE run_key=%s", (run["run_key"],)
    ).fetchone()
    message = redact(message)[:2048]
    info = classify(message, origin)
    fp = fingerprint(info["error_class"], message)
    at = run.get("ended_at") or datetime.now(UTC)
    conn.execute(
        """INSERT INTO obs.error_groups(fingerprint,error_class,sample_message,first_seen,last_seen)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(fingerprint) DO UPDATE SET
        first_seen=least(obs.error_groups.first_seen,excluded.first_seen),
        last_seen=greatest(obs.error_groups.last_seen,excluded.last_seen)""",
        (fp, info["error_class"], message, at, at),
    )
    conn.execute(
        """INSERT INTO obs.run_errors(run_key,tenant_id,stage,failure_origin,error_class,severity,fingerprint,error_message,hint,created_at)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(run_key) DO UPDATE SET
        error_class=excluded.error_class,severity=excluded.severity,fingerprint=excluded.fingerprint,
        error_message=excluded.error_message,hint=excluded.hint""",
        (
            run["run_key"],
            run["tenant_id"],
            run.get("failed_stage") or "airbyte",
            origin,
            info["error_class"],
            info["severity"],
            fp,
            message,
            info["hint"],
            at,
        ),
    )
    log = redact(f"""{at.isoformat()} INFO  Starting {run["source_type"]} {run["load_type"]} sync
{at.isoformat()} INFO  Tenant {run["tenant_id"]} · connection {run.get("airbyte_connection_id", "demo")}
{at.isoformat()} INFO  Secret resolved: mysql://reader:demo-password@source.internal/app
{at.isoformat()} INFO  Contact data-team@example.org · Authorization: Bearer demo-sensitive-token
{at.isoformat()} INFO  Discovering streams: customers, orders, products, payments, events
{at.isoformat()} INFO  Opening source replication cursor
{at.isoformat()} WARN  Attempt {run.get("airbyte_attempts", 1)} could not complete
{at.isoformat()} ERROR {message}
{at.isoformat()} ERROR {info["error_class"]}: sync terminated
{at.isoformat()} INFO  Next action: {info["hint"]}
{at.isoformat()} INFO  Checkpoint retained. No credentials written to the log.
""")
    conn.execute(
        """INSERT INTO obs.run_logs(run_key,source,content) VALUES(%s,%s,%s)
        ON CONFLICT(run_key) DO UPDATE SET content=excluded.content""",
        (run["run_key"], "airflow" if run.get("failed_stage") == "airflow" else "airbyte", log),
    )
    conn.execute(
        """UPDATE obs.error_groups g SET occurrences=(SELECT count(*) FROM obs.run_errors e
        WHERE e.fingerprint=g.fingerprint) WHERE fingerprint=ANY(%s)""",
        ([fp, previous["fingerprint"]] if previous else [fp],),
    )


RUN_COLUMNS = (
    "run_key",
    "tenant_id",
    "source_type",
    "load_type",
    "status",
    "failed_stage",
    "triggered_by",
    "scheduled_for",
    "queued_at",
    "started_at",
    "ended_at",
    "duration_s",
    "queue_delay_s",
    "rows_synced",
    "bytes_synced",
    "dag_id",
    "dag_run_id",
    "task_id",
    "map_index",
    "try_number",
    "airbyte_connection_id",
    "airbyte_job_id",
    "airbyte_attempts",
    "collected_at",
)


def upsert_run(conn: psycopg.Connection, run: dict) -> None:
    cols = ",".join(RUN_COLUMNS)
    placeholders = ",".join(["%s"] * len(RUN_COLUMNS))
    updates = ",".join(f"{c}=excluded.{c}" for c in RUN_COLUMNS if c != "run_key")
    conn.execute(
        f"INSERT INTO obs.pipeline_runs({cols}) VALUES({placeholders}) ON CONFLICT(run_key) DO UPDATE SET {updates}",
        tuple(run.get(c) for c in RUN_COLUMNS),
    )
