from datetime import UTC, datetime

import psycopg

from obs.collector.classify import classify
from obs.collector.fingerprint import fingerprint
from obs.db import notify
from obs.demo.scenarios import upsert_run
from obs.redact import redact


def save(
    conn: psycopg.Connection,
    run: dict,
    *,
    message: str = "",
    origin: str = "source",
    log: str = "",
    streams: list[dict] | None = None,
) -> None:
    job_id = run.get("airbyte_job_id")
    if job_id is not None:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("airbyte-job:" + str(job_id),)
        )
        previous = conn.execute(
            "SELECT run_key,dag_id FROM obs.pipeline_runs WHERE airbyte_job_id=%s AND run_key<>%s",
            (job_id, run["run_key"]),
        ).fetchall()
        if previous and not run.get("dag_id"):
            return  # Already linked: never add an Airbyte-only duplicate.
        for old in previous:
            if old["dag_id"]:
                raise ValueError("Airbyte job already linked to another Airflow task")
            conn.execute("DELETE FROM obs.pipeline_runs WHERE run_key=%s", (old["run_key"],))
    if conn.execute(
        "SELECT 1 FROM obs.operations WHERE kind='retry' AND status='succeeded' AND (target=%s OR result->>'jobId'=%s)",
        (run["run_key"], str(run.get("airbyte_job_id"))),
    ).fetchone():
        run["triggered_by"] = "retry"
    old_error = conn.execute(
        "SELECT fingerprint FROM obs.run_errors WHERE run_key=%s", (run["run_key"],)
    ).fetchone()
    upsert_run(conn, run)
    if run["status"] == "success" and old_error:
        conn.execute("DELETE FROM obs.run_errors WHERE run_key=%s", (run["run_key"],))
        conn.execute("DELETE FROM obs.run_logs WHERE run_key=%s", (run["run_key"],))
    if run["status"] == "failed":
        message = redact(
            message or "Run failed; upstream did not provide a failure summary. Inspect task logs."
        )[:2048]
        info = classify(message, origin)
        fp = fingerprint(info["error_class"], message)
        at = run.get("ended_at") or datetime.now(UTC)
        conn.execute(
            """INSERT INTO obs.error_groups(fingerprint,error_class,sample_message,first_seen,last_seen)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(fingerprint) DO UPDATE SET last_seen=greatest(obs.error_groups.last_seen,excluded.last_seen)""",
            (fp, info["error_class"], message, at, at),
        )
        conn.execute(
            """INSERT INTO obs.run_errors(run_key,tenant_id,stage,failure_origin,error_class,severity,fingerprint,error_message,hint,created_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(run_key) DO UPDATE SET
            stage=excluded.stage,failure_origin=excluded.failure_origin,error_class=excluded.error_class,severity=excluded.severity,
            fingerprint=excluded.fingerprint,error_message=excluded.error_message,hint=excluded.hint""",
            (
                run["run_key"],
                run["tenant_id"],
                run["failed_stage"],
                origin,
                info["error_class"],
                info["severity"],
                fp,
                message,
                info["hint"],
                at,
            ),
        )
    if log:
        content = redact(log).encode()[-512 * 1024 :].decode(errors="replace")
        conn.execute(
            """INSERT INTO obs.run_logs(run_key,source,content) VALUES(%s,%s,%s)
            ON CONFLICT(run_key) DO UPDATE SET source=excluded.source,content=excluded.content""",
            (run["run_key"], "airflow" if run.get("dag_id") else "airbyte", content),
        )
    for stream in streams or []:
        values = stream.get("stats", stream)
        conn.execute(
            """INSERT INTO obs.run_stream_stats(run_key,stream_name,records,bytes) VALUES(%s,%s,%s,%s)
            ON CONFLICT(run_key,stream_name) DO UPDATE SET records=excluded.records,bytes=excluded.bytes""",
            (
                run["run_key"],
                stream.get("streamName", "unknown"),
                values.get("recordsCommitted", values.get("recordsEmitted")),
                values.get("bytesEmitted"),
            ),
        )
    # Recompute only groups touched by this batch, avoiding duplicate occurrence increments on re-poll.
    conn.execute(
        """UPDATE obs.error_groups g SET occurrences=(SELECT count(*) FROM obs.run_errors e WHERE e.fingerprint=g.fingerprint)
        WHERE fingerprint IN (SELECT fingerprint FROM obs.run_errors WHERE run_key=%s) OR fingerprint=%s""",
        (run["run_key"], old_error["fingerprint"] if old_error else None),
    )
    notify(
        conn,
        "run.updated",
        {k: run[k] for k in ("run_key", "tenant_id", "status", "source_type", "load_type")},
    )
