from uuid import uuid4

from psycopg.types.json import Jsonb

from obs.audit import audit
from obs.auth import fail
from obs.collector.normalize import normalize
from obs.collector.store import save
from obs.db import connection, one
from obs.integrations.airbyte import Airbyte
from obs.integrations.airflow import Airflow
from obs.integrations.http import UpstreamError
from obs.redact import redact
from obs.settings import require_live, settings


def enabled() -> None:
    require_live()
    if not settings().live_actions_enabled:
        fail(
            403,
            "live_actions_disabled",
            "Live actions are disabled by the deployment configuration.",
        )


def execute(kind: str, target: str, actor: str, payload: dict, idempotency_key: str) -> dict:
    enabled()
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (idempotency_key,))
        old = conn.execute(
            "SELECT * FROM obs.operations WHERE idempotency_key=%s", (idempotency_key,)
        ).fetchone()
        if old:
            if old["status"] in {"pending", "sending"}:
                fail(
                    409,
                    "operation_in_progress",
                    f"Operation {old['id']} is already being processed. Check Operations for its outcome.",
                )
            if old["status"] in {"failed", "uncertain"}:
                fail(
                    409,
                    "operation_review",
                    f"Operation {old['id']} requires administrator review before another attempt.",
                )
            return old
        operation_id = str(uuid4())
        operation = conn.execute(
            """INSERT INTO obs.operations(id,idempotency_key,kind,target,actor,payload,status)
            VALUES(%s,%s,%s,%s,%s,%s,'sending') RETURNING *""",
            (operation_id, idempotency_key, kind, target, actor, Jsonb(payload)),
        ).fetchone()
        audit(conn, actor, kind + "_requested", target, {"operation_id": operation_id})
    try:
        if kind == "retry":
            if payload.get("dag_id"):
                result = Airflow(write=True).retry(payload)
            else:
                result = Airbyte(write=True).sync(payload["airbyte_connection_id"])
        elif kind == "onboard":
            result = Airflow(write=True).trigger_onboarding(operation_id, payload)
        else:
            raise ValueError("Unsupported operation")
    except Exception as exc:
        ambiguous = isinstance(exc, UpstreamError) and exc.ambiguous
        # SDK transport failures and process deaths must be reconciled, never replayed blindly.
        if type(exc).__name__ in {
            "ReadTimeoutError",
            "ConnectTimeoutError",
            "EndpointConnectionError",
            "ConnectionClosedError",
        }:
            ambiguous = True
        with connection() as conn:
            conn.execute(
                "UPDATE obs.operations SET status=%s,last_error=%s,updated_at=now() WHERE id=%s",
                ("uncertain" if ambiguous else "failed", redact(str(exc))[:2048], operation_id),
            )
            audit(
                conn,
                actor,
                kind + "_failed",
                target,
                {"operation_id": operation_id, "uncertain": ambiguous},
            )
        fail(
            502,
            "upstream_action",
            f"Operation {operation_id} could not be confirmed. Review Operations before retrying.",
        )
    with connection() as conn:
        operation = conn.execute(
            "UPDATE obs.operations SET status='succeeded',result=%s,updated_at=now() WHERE id=%s RETURNING *",
            (Jsonb(result), operation_id),
        ).fetchone()
        audit(conn, actor, kind + "_accepted", target, {"operation_id": operation_id})
    return operation


def retry(key: str, actor: str) -> dict:
    enabled()
    run = one("SELECT * FROM obs.pipeline_runs WHERE run_key=%s", (key,))
    if not run:
        fail(404, "run_not_found", "Run not found.")
    if run["status"] not in {"failed", "cancelled"}:
        fail(409, "retry_not_allowed", "Only failed or cancelled runs can be retried.")
    if (
        run.get("dag_id")
        and run.get("map_index", -1) >= 0
        and settings().airflow_api_version == "v1"
    ):
        fail(
            409,
            "mapped_retry_unsupported",
            "This Airflow 2 API cannot isolate a mapped retry. Retry the specific tenant in Airflow.",
        )
    operation = execute(
        "retry",
        key,
        actor,
        {
            k: run[k]
            for k in ("dag_id", "dag_run_id", "task_id", "map_index", "airbyte_connection_id")
        },
        f"retry:{key}:{run.get('try_number') or 0}",
    )
    job_id = (operation.get("result") or {}).get("jobId")
    if job_id:
        job = {
            **operation["result"],
            "jobId": job_id,
            "connectionId": run["airbyte_connection_id"],
            "status": operation["result"].get("status", "pending"),
        }
        attempt = normalize(None, job, run["tenant_id"], run["source_type"], run["load_type"])
        attempt["triggered_by"] = "retry"
        with connection() as conn:
            save(conn, attempt)
    return {
        "run_key": f"airbyte|{job_id}" if job_id else key,
        "message": "Retry accepted upstream. The collector will confirm the next attempt.",
        "simulated": False,
    }
