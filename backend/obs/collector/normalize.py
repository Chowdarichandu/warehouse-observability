import re
from datetime import UTC, datetime

from obs.integrations.airbyte import duration_seconds, timestamp

STATES = {
    "succeeded": "success",
    "success": "success",
    "failed": "failed",
    "upstream_failed": "failed",
    "running": "running",
    "restarting": "running",
    "incomplete": "running",
    "deferred": "running",
    "queued": "queued",
    "pending": "queued",
    "scheduled": "queued",
    "up_for_retry": "queued",
    "up_for_reschedule": "queued",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "skipped": "skipped",
}


def tenant_for(task: dict, job: dict, tenants: list[dict], pattern: str) -> dict | None:
    connection_id = job.get("connectionId")
    if connection_id:
        found = [t for t in tenants if connection_id in t["airbyte_connections"].values()]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise ValueError("Airbyte connection is assigned to multiple tenants")
    candidates = []
    match = re.search(pattern, task.get("task_id", ""))
    if match:
        candidates.append(match.groupdict().get("tenant"))
    candidates.extend([task.get("rendered_map_index"), job.get("namespace")])
    for candidate in candidates:
        for tenant in tenants:
            if candidate in {tenant["tenant_id"], tenant.get("warehouse_schema")}:
                return tenant
    return None


def normalize(task: dict | None, job: dict | None, tenant: str, source: str, load: str) -> dict:
    task, job = task or {}, job or {}
    af_state = STATES.get(task.get("state"), "queued")
    ab_state = STATES.get(job.get("status"), "queued")
    state = ab_state if job else af_state
    if "failed" in {af_state, ab_state}:
        state = "failed"
    elif task and af_state in {"cancelled", "skipped"}:
        state = af_state
    elif task and job and af_state != "success" and ab_state == "success":
        state = af_state
    start = timestamp(task.get("start_date") or job.get("startTime") or job.get("createdAt"))
    end = (
        timestamp(task.get("end_date") or job.get("lastUpdatedAt") or job.get("updatedAt"))
        if state in {"success", "failed", "cancelled", "skipped"}
        else None
    )
    queued = timestamp(
        task.get("queued_when") or task.get("queued_dttm") or task.get("scheduled_dttm")
    )
    key = (
        f"{task['dag_id']}|{task['dag_run_id']}|{task['task_id']}|{task.get('map_index', -1)}"
        if task
        else f"airbyte|{job['jobId']}"
    )
    return {
        "run_key": key,
        "tenant_id": tenant,
        "source_type": source,
        "load_type": load,
        "status": state,
        "failed_stage": ("airbyte" if ab_state == "failed" else "airflow")
        if state == "failed"
        else None,
        "triggered_by": "schedule" if task else "manual",
        "scheduled_for": timestamp(task.get("logical_date")),
        "queued_at": queued,
        "started_at": start,
        "ended_at": end,
        "duration_s": max(int((end - start).total_seconds()), 0)
        if start and end
        else duration_seconds(job.get("duration")),
        "queue_delay_s": max(int((start - queued).total_seconds()), 0)
        if start and queued
        else None,
        "rows_synced": job.get("rowsSynced"),
        "bytes_synced": job.get("bytesSynced"),
        "dag_id": task.get("dag_id"),
        "dag_run_id": task.get("dag_run_id"),
        "task_id": task.get("task_id"),
        "map_index": task.get("map_index", -1),
        "try_number": task.get("try_number"),
        "airbyte_connection_id": job.get("connectionId"),
        "airbyte_job_id": job.get("jobId"),
        "airbyte_attempts": len(job.get("attempts_detail", [])) or None,
        "collected_at": datetime.now(UTC),
    }


def failure(job: dict) -> tuple[str, str, str, list[dict]]:
    attempts = job.get("attempts_detail", [])
    wrapper = attempts[-1] if attempts else {}
    attempt = wrapper.get("attempt", wrapper)
    failures = attempt.get("failureSummary", {}).get("failures", [])
    message = "\n".join(
        f.get("externalMessage") or f.get("internalMessage") or "Airbyte sync failed"
        for f in failures
    )
    lines = wrapper.get("logs", {}).get("logLines", [])
    stats = attempt.get("streamStats", [])
    return (
        message or job.get("failureReason", ""),
        failures[-1].get("failureOrigin", "source") if failures else "source",
        "\n".join(lines),
        stats,
    )
