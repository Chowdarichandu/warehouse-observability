from datetime import UTC, datetime, timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from obs.audit import audit
from obs.auth import fail
from obs.db import connection, notify
from obs.demo.scenarios import upsert_run
from obs.demo.seed import make_run
from obs.settings import require_demo, settings


def retry(key: str, actor: str) -> dict:
    require_demo()
    now = datetime.now(UTC)
    with connection() as conn:
        original = conn.execute(
            "SELECT * FROM obs.pipeline_runs WHERE run_key=%s FOR UPDATE", (key,)
        ).fetchone()
        if not original:
            fail(404, "run_not_found", "Run not found.")
        if original["status"] not in {"failed", "cancelled"}:
            fail(409, "retry_not_allowed", "Only failed or cancelled runs can be retried.")
        existing = conn.execute(
            "SELECT payload FROM obs.demo_jobs WHERE kind='retry' AND payload->>'original'=%s AND NOT done",
            (key,),
        ).fetchone()
        if existing:
            return {
                "run_key": existing["payload"]["run_key"],
                "message": "Retry already in progress.",
                "simulated": True,
            }
        run = make_run(
            original["tenant_id"],
            original["source_type"],
            original["load_type"],
            now,
            0,
            int(now.timestamp() * 1000),
            "running",
            "retry",
        )
        run["run_key"] = f"retry|{uuid4()}"
        upsert_run(conn, run)
        conn.execute(
            "INSERT INTO obs.demo_jobs(job_key,kind,tenant_id,payload,due_at) VALUES(%s,'retry',%s,%s,%s)",
            (
                run["run_key"],
                run["tenant_id"],
                Jsonb({"run_key": run["run_key"], "original": key}),
                now + timedelta(seconds=settings().demo_retry_sec),
            ),
        )
        audit(conn, actor, "retry_run", key, {"new_run_key": run["run_key"], "simulated": True})
        notify(
            conn,
            "run.updated",
            {k: run[k] for k in ("run_key", "tenant_id", "status", "source_type", "load_type")},
        )
    return {
        "run_key": run["run_key"],
        "message": "Demo retry started. It will complete in about 30 seconds.",
        "simulated": True,
    }
